"""Shadow-swing sessions: taps, video clock, gyro-peak swings and per-block summaries (MOCK data)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from wrist.impact import G
from wrist.load import Recording, load_recording
from wrist.metrics import ROLL_METHODS, wrist_metrics
from wrist.shadow import (
    _cell, fit_video_clock, find_shadow_swings, find_tap_events, place_segments, read_segments, shadow_report, to_sensor,
)
from wrist.synth import make_session


def _rec(acc: np.ndarray, gyro: np.ndarray, quat: np.ndarray | None = None, rate: float = 100.0) -> Recording:
    return Recording(t=np.arange(len(acc)) / rate, acc=acc, gyro=gyro, quat=quat, rate_hz=rate,
                     orientation="none" if quat is None else "quaternion", mock=True, source="test")


def test_tap_events_are_runs_of_still_knocks() -> None:
    rng = np.random.default_rng(0)
    acc, gyro = rng.normal(0, 0.05, (1500, 3)), np.zeros((1500, 3))

    def knock(t: float, g: float) -> None:
        acc[int(round(t * 100)), 0] += g * G

    knock(1.0, 1.5); knock(1.3, 2.0)                 # a double tap
    for t in (5.0, 5.28, 5.56):                      # three taps...
        knock(t, 1.2)
    knock(5.65, 0.7)                                 # ...the last ringing 90 ms later: still one tap
    knock(8.0, 2.0)                                  # a lone knock is not an event
    knock(9.0, 0.3); knock(9.3, 0.3)                 # too soft for taps
    gyro[1150:1250, 2] = np.radians(800.0)
    knock(12.0, 2.0); knock(12.3, 2.0)               # knocks mid-swing are not taps
    events = find_tap_events(_rec(acc, gyro))
    assert [e["t_s"] for e in events] == [1.0, 5.0]
    assert [e["n_taps"] for e in events] == [2, 3]
    assert events[1]["taps_s"] == [5.0, 5.28, 5.56]
    assert events[0]["heights_g"] == pytest.approx([1.5, 2.0], abs=0.1)


def test_a_tap_is_timed_from_its_onset_not_its_rebound() -> None:
    # Each knock: the screen-normal push (0.6 g), then the phone's bigger rebound 10 ms later.
    rng = np.random.default_rng(1)
    acc, gyro = rng.normal(0, 0.02, (600, 3)), np.zeros((600, 3))
    for t in (2.0, 2.3):
        i = int(round(t * 100))
        acc[i, 2] += 0.6 * G
        acc[i + 1, 0] += 2.0 * G
        acc[i + 2, 0] -= 1.0 * G
    events = find_tap_events(_rec(acc, gyro))
    assert len(events) == 1
    assert events[0]["peaks_s"] == [2.01, 2.31], "the biggest sample is the rebound"
    assert events[0]["taps_s"] == [2.0, 2.3] and events[0]["t_s"] == 2.0, "the tap is when the push starts"


def test_video_clock_fits_scale_and_offset_from_the_taps() -> None:
    video = [133.1, 274.4, 368.4, 506.0]
    sensor = [v * 0.25 - 18.4 for v in video]
    sensor[2] += 0.004                               # 4 ms of tap-timing noise
    clock = fit_video_clock(video, sensor)
    assert clock["scale"] == pytest.approx(0.25, abs=1e-4) and clock["offset_s"] == pytest.approx(-18.4, abs=0.01)
    assert clock["n_taps"] == 4 and clock["max_abs_residual_ms"] < 4
    assert to_sensor(200.0, clock) == pytest.approx(200 * 0.25 - 18.4, abs=0.01)
    one = fit_video_clock([100.0], [7.0], scale=0.25)
    assert one["offset_s"] == pytest.approx(-18.0) and one["residuals_ms"] == [0.0]
    with pytest.raises(ValueError, match="scale"):
        fit_video_clock([100.0], [7.0])
    with pytest.raises(ValueError, match="matching"):
        fit_video_clock([1.0, 2.0], [1.0])


def test_segments_from_video_times_run_to_the_next_block(tmp_path: Path) -> None:
    path = tmp_path / "segments.csv"
    path.write_text("segment,stroke,fault,video_start_s,video_end_s\n"
                    "bh-good,backhand,none,132,264\nbh-rolled,backhand,rolled_wrist,367,\n")
    segs = read_segments(path)
    assert [s["fault"] for s in segs] == ["none", "rolled_wrist"] and segs[1]["video_end_s"] is None
    rec = _rec(np.zeros((12001, 3)), np.zeros((12001, 3)))   # 0..120 s
    placed = place_segments(segs, rec, {"scale": 0.25, "offset_s": -18.0})
    assert [(s["start_s"], s["end_s"]) for s in placed] == [(15.0, 48.0), (73.75, 120.0)]
    with pytest.raises(ValueError, match="video clock"):
        place_segments(segs, rec)
    path.write_text("segment,stroke,fault,start_s\nx,lob,none,1\n")
    with pytest.raises(ValueError, match="stroke"):
        read_segments(path)


def test_a_reused_segment_name_is_refused_with_both_lines(tmp_path: Path) -> None:
    """Swing ids are <segment>-NN, so two 'good' blocks would overwrite each other's swings."""
    path = tmp_path / "segments.csv"
    path.write_text("segment,stroke,fault,start_s\ngood,forehand,none,10\nrolled,forehand,rolled_wrist,40\n"
                    "\ngood,backhand,none,70\n")  # the blank line still counts: the reuse is on line 5
    with pytest.raises(ValueError, match=r"segment 'good' is used twice: lines 2 and 5; give each block a unique name"):
        read_segments(path)


def test_an_excel_csv_with_a_byte_order_mark_parses(tmp_path: Path) -> None:
    """Codex P2 on #75: Excel's "CSV UTF-8" starts with a BOM, which would glue itself to 'segment'."""
    path = tmp_path / "segments.csv"
    path.write_bytes(b"\xef\xbb\xbfsegment,stroke,fault,start_s,end_s\r\n"
                     b"bh-good,backhand,none,14.889,\r\nbh-rolled,backhand,rolled_wrist,74.149,\r\n")
    segs = read_segments(path)
    assert [(s["segment"], s["stroke"], s["start_s"]) for s in segs] == [
        ("bh-good", "backhand", 14.889), ("bh-rolled", "backhand", 74.149)]


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf"])
def test_a_non_finite_segment_time_is_refused_naming_the_segment(tmp_path: Path, bad: str) -> None:
    """Codex P2 on #74: float() takes "nan", every comparison with it is False, and the block finds no swings."""
    path = tmp_path / "segments.csv"
    path.write_text(f"segment,stroke,fault,start_s,end_s\nbh-good,backhand,none,10,40\n"
                    f"bh-rolled,backhand,rolled_wrist,{bad},80\n")
    with pytest.raises(ValueError, match=rf"segments.csv:3: segment 'bh-rolled': start_s must be a finite number, "
                                         rf"got '{bad}'"):
        read_segments(path)
    rec = _rec(np.zeros((12001, 3)), np.zeros((12001, 3)))   # 0..120 s
    segs = [{"segment": "fh-good", "stroke": "forehand", "fault": "none", "start_s": 10.0, "end_s": float(bad)}]
    with pytest.raises(ValueError, match=r"segment 'fh-good': end_s must be a finite number"):
        place_segments(segs, rec)   # built in code, not read from a CSV


def test_a_block_starting_before_the_recording_is_refused() -> None:
    """Codex P2 on #80: it would be cut silently to the samples there are."""
    rec = _rec(np.zeros((12001, 3)), np.zeros((12001, 3)))   # 0..120 s at 100 Hz
    segs = [{"segment": "bh-good", "stroke": "backhand", "fault": "none", "start_s": -5.0, "end_s": 30.0}]
    with pytest.raises(ValueError, match=r"segment 'bh-good' starts at -5.0 s, before the recording: "
                                         r"the recording runs 0.000 .. 120.000 s"):
        place_segments(segs, rec)
    segs[0]["start_s"] = -0.01   # one sample early: within tolerance
    assert place_segments(segs, rec)[0]["start_s"] == -0.01


def test_a_block_ending_after_the_recording_is_refused() -> None:
    rec = _rec(np.zeros((12001, 3)), np.zeros((12001, 3)))   # 0..120 s at 100 Hz
    segs = [{"segment": "fh-good", "stroke": "forehand", "fault": "none", "start_s": 10.0, "end_s": 40.0},
            {"segment": "fh-rolled", "stroke": "forehand", "fault": "rolled_wrist", "start_s": 40.0, "end_s": 130.0}]
    with pytest.raises(ValueError, match=r"segment 'fh-rolled' ends at 130.0 s, after the recording: "
                                         r"the recording runs 0.000 .. 120.000 s"):
        place_segments(segs, rec)
    vsegs = [{"segment": "late", "stroke": "forehand", "fault": "none", "video_start_s": 100.0, "video_end_s": 600.0}]
    with pytest.raises(ValueError, match="'late' ends at 132.0 s, after the recording"):   # 600 x 0.25 - 18
        place_segments(vsegs, rec, {"scale": 0.25, "offset_s": -18.0})
    segs[1]["end_s"] = None   # a blank end runs to the end of the recording, never past it
    assert place_segments(segs, rec)[1]["end_s"] == 120.0


def test_overlapping_blocks_are_refused_naming_both() -> None:
    rec = _rec(np.zeros((12001, 3)), np.zeros((12001, 3)))   # 0..120 s
    segs = [{"segment": "fh-good", "stroke": "forehand", "fault": "none", "start_s": 10.0, "end_s": 45.0},
            {"segment": "fh-rolled", "stroke": "forehand", "fault": "rolled_wrist", "start_s": 40.0, "end_s": None}]
    with pytest.raises(ValueError, match=r"'fh-good' \(10.0 .. 45.0 s\) and 'fh-rolled' \(40.0 .. 120.0 s\) overlap"):
        place_segments(segs, rec)
    segs[0]["end_s"] = 40.0  # touching is fine: a block ends where the next one starts
    assert [(s["start_s"], s["end_s"]) for s in place_segments(segs, rec)] == [(10.0, 40.0), (40.0, 120.0)]


def test_out_of_order_blocks_are_refused_naming_both() -> None:
    rec = _rec(np.zeros((12001, 3)), np.zeros((12001, 3)))   # 0..120 s
    segs = [{"segment": "bh-rolled", "stroke": "backhand", "fault": "rolled_wrist", "start_s": 60.0, "end_s": None},
            {"segment": "bh-good", "stroke": "backhand", "fault": "none", "start_s": 20.0, "end_s": None}]
    with pytest.raises(ValueError, match=r"'bh-rolled' \(starts 60.0 s\) and 'bh-good' \(starts 20.0 s\) are out of order"):
        place_segments(segs, rec)
    # video times are checked after mapping to the sensor clock, the same way
    vsegs = [{"segment": "a", "stroke": "forehand", "fault": "none", "video_start_s": 300.0},
             {"segment": "b", "stroke": "forehand", "fault": "none", "video_start_s": 300.0}]
    with pytest.raises(ValueError, match="out of order"):
        place_segments(vsegs, rec, {"scale": 0.25, "offset_s": -18.0})


@pytest.fixture(scope="module")
def shadow_session(tmp_path_factory: pytest.TempPathFactory):
    """5 normal then 5 rolled swings, none with a ball (all shadow swings)."""
    truth = make_session(tmp_path_factory.mktemp("wrist-shadow-session"), shadow=tuple(range(10)))
    return truth, load_recording(truth["export"])


def test_shadow_report_times_every_swing_and_separates_the_rolled_block(shadow_session) -> None:
    truth, rec = shadow_session
    taps = find_tap_events(rec)
    assert len(taps) == 1 and taps[0]["t_s"] == pytest.approx(2.0, abs=0.011), "the start double tap; no footstep"
    impacts = sorted(t["impact_s"] for t in truth["swings"].values())
    mid = (impacts[4] + impacts[5]) / 2
    segs = place_segments([{"segment": "good", "stroke": "forehand", "fault": "none", "start_s": 3.0, "end_s": mid},
                           {"segment": "rolled", "stroke": "forehand", "fault": "rolled_wrist", "start_s": mid,
                            "end_s": None}], rec)
    metrics, series = shadow_report(rec, segs, taps=taps)

    entries = metrics["swings"]
    assert len(entries) == 10 and set(series["swings"]) == set(entries)
    for sid, e in entries.items():
        assert e["usable"] and e["contact_source"] == "gyro peak" and e["impact"] is None and e["impact_s"] is None
        assert e["segment"] == sid.rsplit("-", 1)[0] and e["roll_method"] == ROLL_METHODS["gyro"]
    contacts = sorted(e["contact_s"] for e in entries.values())
    assert np.abs(np.array(contacts) - impacts).max() <= 0.03, "the fastest turn is within 30 ms of real contact"
    rolls = sorted((e["contact_s"], e["roll_change_deg"]) for e in entries.values())
    truth_rolls = [t["roll_change_deg"] for t in sorted(truth["swings"].values(), key=lambda t: t["impact_s"])]
    assert [r for _, r in rolls] == pytest.approx(truth_rolls, abs=4.0)

    sh = metrics["shadow"]
    assert sh["label"] == "MOCK (sensor)" and "gyro peak" in sh["contact"]
    blocks = {b["segment"]: b for b in sh["blocks"]}
    assert blocks["good"]["n_swings"] == blocks["rolled"]["n_swings"] == 5
    assert blocks["rolled"]["numbers"]["roll_change_abs_deg"]["mean"] > 2 * blocks["good"]["numbers"]["roll_change_abs_deg"]["mean"]
    roll = next(c for c in sh["comparisons"] if c["number"] == "roll_change_abs_deg")
    assert roll["auc"] == 1.0 and not roll["overlap"] and roll["difference"] > 30 and roll["cohens_d"] > 3
    assert metrics["sensor"]["axis_hint"]["agrees"] is True, "shadow swings still pull along the forearm"
    json.dumps(metrics, allow_nan=False)
    json.dumps(series, allow_nan=False)


def test_recovery_bumps_between_swings_are_not_swings() -> None:
    t = np.arange(1000) / 100.0
    speed = np.zeros_like(t)
    for c in (2.0, 4.0, 6.0):
        speed += 1200.0 * np.exp(-0.5 * ((t - c) / 0.05) ** 2)          # swings
        speed += 450.0 * np.exp(-0.5 * ((t - c - 0.85) / 0.08) ** 2)    # the recovery after each
    rec = _rec(np.zeros((t.size, 3)), np.zeros((t.size, 3)))
    assert find_shadow_swings(rec, 0.0, 10.0, speed) == [2.0, 4.0, 6.0]


def test_recovery_bumps_a_full_gap_after_each_swing_are_not_swings() -> None:
    """Codex P1 on #75: recoveries SWING_GAP_S or more after their swing reach the height filter.
    With one per swing the median (825 here) sits between them; a swing-sized reference drops them."""
    t = np.arange(2000) / 100.0
    speed = np.zeros_like(t)
    swings = (2.0, 5.0, 8.0, 11.0, 14.0)
    for c in swings:
        speed += 1200.0 * np.exp(-0.5 * ((t - c) / 0.05) ** 2)          # swings
        speed += 450.0 * np.exp(-0.5 * ((t - c - 1.3) / 0.08) ** 2)     # recovery 1.3 s later (gap 1.0 s)
    rec = _rec(np.zeros((t.size, 3)), np.zeros((t.size, 3)))
    assert find_shadow_swings(rec, 0.0, 20.0, speed) == list(swings)


def test_a_weaker_real_swing_is_still_a_swing() -> None:
    t = np.arange(1500) / 100.0
    speed = np.zeros_like(t)
    for c, h in ((2.0, 1500.0), (5.0, 1300.0), (8.0, 800.0), (11.0, 1400.0)):   # 800 is 57% of the 75th pct
        speed += h * np.exp(-0.5 * ((t - c) / 0.05) ** 2)
    rec = _rec(np.zeros((t.size, 3)), np.zeros((t.size, 3)))
    assert find_shadow_swings(rec, 0.0, 15.0, speed) == [2.0, 5.0, 8.0, 11.0]


def test_one_swing_blocks_print_the_sd_as_n_a_not_zero() -> None:
    """Codex P2 on #75: a sample SD can't be computed from one swing."""
    assert _cell({"n": 1, "mean": 61.04, "sd": None}) == "61.0 ± n/a"
    assert _cell({"n": 3, "mean": 61.04, "sd": 0.0}) == "61.0 ± 0.0"
    assert _cell({"n": 0, "mean": None, "sd": None}) == "n/a"


def test_roll_is_the_gyro_integral_even_where_the_twist_breaks_down() -> None:
    # Constant body rate: 60 deg of roll about the forearm (y) and a 170 deg swing about z per
    # 250 ms window, with the exact phone-to-world quaternions, so the phone path is used.
    rate, c = 100.0, 4.0
    t = np.arange(800) / rate
    w = np.radians([0.0, 60.0, 170.0]) / 0.25
    quat = Rotation.from_rotvec(np.outer(t, w)).as_quat()
    rec = _rec(np.zeros((t.size, 3)), np.tile(w, (t.size, 1)), quat)
    sync = {"taps_s": None, "warnings": [], "alignment": {
        "pairs": [], "unpaired_swings": [], "tap_only": [], "gyro_peak": [{"swing": "s1", "contact_s": c}],
        "tolerance_ms": 100.0}}
    metrics, series = wrist_metrics(rec, sync)
    assert metrics["sensor"]["orientation_used"]["source"] == "phone"
    m = metrics["swings"]["s1"]
    assert m["contact_source"] == "gyro peak" and m["impact"] is None
    assert m["roll_change_deg"] == pytest.approx(60.0, abs=0.5) and m["roll_change_gyro_deg"] == m["roll_change_deg"]
    assert abs(m["roll_change_twist_deg"] - 60.0) > 90, "the twist of a ~180 deg turn says nothing about roll"
    ser = series["swings"]["s1"]
    assert ser["roll_deg"][ser["t_ms"].index(100)] == pytest.approx(m["roll_change_deg"], abs=0.11)
