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
    fit_video_clock, find_shadow_swings, find_tap_events, place_segments, read_segments, shadow_report, to_sensor,
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
