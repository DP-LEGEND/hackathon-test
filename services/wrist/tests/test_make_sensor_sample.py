"""scripts/make_sensor_sample.py: the pieces that don't need a real clip. Videos here are MOCK frames."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

import wrist.metrics as wm
from coach.faults import WRIST_MOCK
from physics.skeleton import ARM, L_SH, R_SH

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "make_sensor_sample.py"


@pytest.fixture(scope="module")
def mss():
    before = (wm.swing_metrics, wm.roll_series)
    spec = importlib.util.spec_from_file_location("make_sensor_sample", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Importing must not switch every later wrist test to the gyro roll (it used to, at import).
    assert (wm.swing_metrics, wm.roll_series) == before
    return module


def mock_clip(path: Path, frames: int = 60, size: tuple[int, int] = (160, 90), fps: float = 30.0) -> Path:
    """MOCK video: frame k is a flat grey of brightness 2k, so a tile shows which frame it came from."""
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    for k in range(frames):
        out.write(np.full((size[1], size[0], 3), 2 * k, np.uint8))
    out.release()
    return path


def test_gyro_roll_is_only_switched_on_inside_and_always_restored(mss):
    before = (wm.swing_metrics, wm.roll_series)
    with pytest.raises(RuntimeError):
        with mss.gyro_roll():
            assert wm.swing_metrics is not before[0] and wm.roll_series is not before[1]
            raise RuntimeError("a step failed")
    assert (wm.swing_metrics, wm.roll_series) == before


@pytest.mark.parametrize("text,seconds", [
    ("166.6", 166.6), ("  12 ", 12.0), ("2:46.6", 166.6), ("02:46", 166.0), ("f4998", 166.6), ("F30", 1.0),
])
def test_times_read_as_seconds_minutes_or_frames(mss, text, seconds):
    assert mss.playback_seconds(text, 30.0) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["2:61", "1:2:3", "f", "f12.5", "abc", "-3", ""])
def test_unreadable_times_stop_with_the_formats(mss, text):
    with pytest.raises(mss.SampleError, match="166.6|f4998"):
        mss.playback_seconds(text, 30.0)


def test_native_logs_go_to_the_file_and_the_terminal_comes_back(mss, tmp_path):
    log = tmp_path / "pipeline.log"
    stderr_before = os.fstat(2).st_ino
    with mss.native_log(log):
        os.write(2, b"WARNING: Sparsity tensors may not yet be fully supported.\n")
    assert os.fstat(2).st_ino == stderr_before
    assert "Sparsity tensors" in log.read_text()


def _pose(shoulders, wrists) -> np.ndarray:
    p = np.full((33, 3), np.nan)
    p[[L_SH, R_SH], :2] = shoulders
    p[[ARM["L"]["wr"], ARM["R"]["wr"]], :2] = wrists
    return p


def test_hands_box_is_three_shoulder_widths_around_the_wrists(mss):
    box = mss.hands_box(_pose([(500, 300), (560, 300)], [(520, 400), (540, 410)]), (1920, 1080))
    assert box == (440, 315, 620, 495)  # half side 1.5 x 60 px, centred between the wrists
    # Kept inside the frame near an edge, and None when a wrist wasn't found.
    assert mss.hands_box(_pose([(0, 300), (60, 300)], [(5, 400), (15, 400)]), (1920, 1080))[0] == 0
    assert mss.hands_box(_pose([(500, 300), (560, 300)], [(520, 400), (np.nan, np.nan)]), (1920, 1080)) is None


def test_tap_check_rows_show_the_frame_and_the_zoom_before_it(mss, tmp_path):
    clip = mock_clip(tmp_path / "clip.avi")
    out = tmp_path / "tapcheck.jpg"
    # Sensor taps 0.28 s apart at 4x land 1.12 playback s apart: frames 6 and 40 (6 + 33.6, rounded).
    times = mss.tap_check_image(clip, 0.2, [10.0, 10.28], 4.0, out, box=(40, 20, 100, 80))
    assert times == pytest.approx([0.2, 1.32])
    img = cv2.imread(str(out))
    full_w = round(160 * mss.TILE_H / 90)
    assert img.shape[:2] == (2 * mss.TILE_H, full_w + 2 * mss.TILE_H)  # one row per tap
    # The last tile is BEFORE_FRAMES earlier: tap 1 at frame 6 -> frame 3 (brightness 6 vs 12).
    zoom_at, zoom_before = img[200, full_w + 180].mean(), img[200, full_w + mss.TILE_H + 180].mean()
    assert zoom_at == pytest.approx(12, abs=4) and zoom_before == pytest.approx(6, abs=4)
    # Without a zoom (find_hands_box found no player) every row still has the earlier frame, whole.
    mss.tap_check_image(clip, 0.2, [10.0, 10.28], 4.0, out)
    img = cv2.imread(str(out))
    assert img.shape[:2] == (2 * mss.TILE_H, 2 * full_w)  # per tap: the frame, then BEFORE_FRAMES earlier
    assert img[200, full_w // 2].mean() == pytest.approx(12, abs=4)            # tap 1: frame 6
    assert img[200, full_w + full_w // 2].mean() == pytest.approx(6, abs=4)    # frame 3, not a black tile


def test_sheet_labels_frames_and_refuses_too_many(mss, tmp_path, monkeypatch):
    clip = mock_clip(tmp_path / "clip.avi")
    monkeypatch.setattr(mss, "find_hands_box", lambda *a: None)  # no pose model needed
    out = tmp_path / "sheet.jpg"
    assert mss.frame_sheet(clip, 0.0, 0.5, 1, out, tmp_path / "sheet.log") == 16  # frames 0..15
    assert cv2.imread(str(out)).shape[0] == 4 * mss.TILE_H  # 16 whole frames, 4 per row
    with pytest.raises(mss.SampleError, match="narrow START END"):
        mss.frame_sheet(clip, 0.0, 1.9, 1, out, tmp_path / "sheet.log")  # 58 frames > 48


def test_mock_thresholds_on_a_real_recording_are_called_out(mss):
    faults = [{"id": "rolled_wrist", "source": WRIST_MOCK, "threshold": 39.3, "unit": "deg"},
              {"id": "under_rotation", "source": "labelled clips", "threshold": 70.0, "unit": "deg"}]
    warnings = mss.mock_rule_warnings(faults, sensor_is_mock=False)
    assert len(warnings) == 1 and "rolled_wrist" in warnings[0] and "MOCK threshold" in warnings[0]
    assert mss.mock_rule_warnings(faults, sensor_is_mock=True) == []  # a MOCK export is labelled already


def test_a_sound_timed_contact_on_a_shadow_swing_is_called_out(mss):
    assert "no ball" in mss.shadow_contact_warning(True, "audio-transient")
    assert mss.shadow_contact_warning(True, "wrist-speed-peak") is None
    assert mss.shadow_contact_warning(False, "audio-transient") is None  # a real hit's sound is the ball


def test_cli_needs_the_sensor_tap_window_and_stroke_unless_it_only_makes_a_sheet(mss, tmp_path, capsys):
    with pytest.raises(SystemExit):
        mss.main([str(tmp_path / "clip.mov")])
    assert "missing sensor, --tap, --window, --stroke" in capsys.readouterr().err
    assert mss.main([str(tmp_path / "missing.mov"), "--sheet", "1", "2"]) == 1  # sheet mode: no sensor needed
    assert "doesn't exist" in capsys.readouterr().err


# ---- Wrist timing: the real rolled_wrist lines judge only rolls centred on the gyro peak ----

def _turn_recording(peaks: list[tuple[float, float]], seconds: float = 20.0, rate: float = 100.0):
    """A still forearm with a turn-rate bump (deg/s, about the forearm axis) at each (time s, peak)."""
    from wrist.load import Recording
    t = np.arange(int(seconds * rate)) / rate
    dps = sum(peak * np.exp(-0.5 * ((t - at) / 0.06) ** 2) for at, peak in peaks)
    gyro = np.zeros((t.size, 3))
    gyro[:, 1] = np.radians(dps)
    acc = np.tile([0.0, 0.0, 1.0], (t.size, 1))
    return Recording(t=t, acc=acc, gyro=gyro, quat=None, rate_hz=rate, orientation="none", mock=True, source="test")


def test_the_gyro_peak_is_the_fastest_turn_near_the_impact(mss):
    rec = _turn_recording([(10.0, 1200.0), (10.25, 450.0)])  # the swing, then a recovery bump
    assert mss.gyro_peak_near(rec, 10.08) == pytest.approx(10.0, abs=0.011)  # impact 80 ms after the turn
    assert mss.gyro_peak_near(rec, 9.80) == pytest.approx(10.0, abs=0.011)
    with pytest.raises(mss.SampleError, match="no forearm-turn peak .* within 300 ms .* --wrist-timing impact"):
        mss.gyro_peak_near(rec, 10.6)  # 600 ms away: not this swing


@pytest.fixture(scope="module")
def mock_session(tmp_path_factory):
    """wrist.synth's MOCK export with its impacts paired to the video contacts (wrist.sync)."""
    from wrist.load import load_recording
    from wrist.sync import read_contacts, synchronise
    from wrist.synth import make_session
    truth = make_session(tmp_path_factory.mktemp("wrist_timing"))
    rec = load_recording(truth["export"])
    sync = synchronise(rec, read_contacts(truth["contacts"]), video_tap_s=truth["video_tap_s"])
    sid = next(p["swing"] for p in sync["alignment"]["pairs"] if p["ok"])
    return rec, sync, sid


def test_gyro_peak_timing_is_a_wrist_shadow_entry_found_from_the_impact(mss, mock_session):
    from wrist.shadow import shadow_sync
    rec, sync, sid = mock_session
    imp, imp_series, _, none = mss.wrist_for_sample(rec, sync, "y", sid, None, "impact")
    assert none is None and imp["swings"][sid]["contact_source"] == "impact spike"
    gp, gp_series, _, info = mss.wrist_for_sample(rec, sync, "y", sid, None)  # the default
    e, i = gp["swings"][sid], imp["swings"][sid]
    assert e["usable"] and e["contact_source"] == "gyro peak" and e["impact_s"] is None
    assert info["found_from"] == "impact spike" and info["found_from_s"] == i["contact_s"]
    assert e["contact_s"] == info["gyro_peak_s"] and abs(info["gyro_peak_minus_found_from_ms"]) <= 300
    assert e["timing"] == info
    # The same numbers wrist.shadow gives for a block holding just this swing.
    shadow, _ = shadow_sync(rec, [{"segment": "s", "start_s": info["gyro_peak_s"] - 0.5,
                                   "end_s": info["gyro_peak_s"] + 0.5}])
    ref = wrist_report_entry(rec, shadow, "s-01")
    for key in ("contact_s", "roll_change_deg", "roll_change_abs_deg", "peak_roll_rate_abs_dps", "peak_angular_speed_dps"):
        assert e[key] == ref[key], key
    # The ball's speed still comes from the impact-timed racket speed, and says so.
    assert e["racket_speed_sensor"]["value"] == i["racket_speed_sensor"]["value"]
    assert e["racket_speed_sensor"]["contact_source"] == "impact spike"
    s = gp_series["swings"][sid]
    assert s["contact_source"] == "gyro peak" and s["racket_speed_sensor"] == imp_series["swings"][sid]["racket_speed_sensor"]
    mss.check_wrist_series(gp_series, sid)  # the panel reads it


def wrist_report_entry(rec, sync, sid):
    from wrist.metrics import wrist_report
    return wrist_report(rec, sync, "y")[0]["swings"][sid]


@pytest.mark.parametrize("stroke, roll", [("forehand", 158.8), ("backhand", 137.3)])
def test_a_real_hit_is_wrist_checked_with_gyro_peak_timing_and_not_with_impact_timing(mss, mock_session, stroke, roll):
    """#74's real lines judge only gyro-peak-timed entries: the default makes a real hit checkable."""
    import json
    from coach.agent import coach_swing
    from coach.faults import NOT_GYRO_PEAK
    rec, sync, sid = mock_session
    sample = json.loads((SCRIPT.parents[1] / "data" / "samples" / "swing_sample.json").read_text())
    for timing in ("gyro-peak", "impact"):
        entry = dict(mss.wrist_for_sample(rec, sync, "y", sid, None, timing)[0]["swings"][sid])
        entry.update(mock=False, roll_change_abs_deg=roll)  # a real forearm's rolled roll
        result = coach_swing({**sample, "wrist": entry}, stroke)
        fired = [result["fault"]["id"], *result["other_faults"]] if result["fault"] else []
        line = mss.rolled_wrist_line(result, stroke)
        if timing == "gyro-peak":
            assert "rolled_wrist" in fired and "rolled_wrist" not in result["not_measured"]
            assert line.startswith(f"rolled_wrist: checked, ROLLED, past the real {stroke} line: forearm roll {roll:.1f}")
        else:
            assert "rolled_wrist" not in fired and result["disabled_faults"]["rolled_wrist"] == NOT_GYRO_PEAK
            assert line == f"rolled_wrist: NOT CHECKED, so don't quote a wrist call: {NOT_GYRO_PEAK}"


def test_the_rolled_wrist_line_says_checked_and_not_rolled_and_names_the_line(mss, mock_session):
    """The 14 Nov dry run: a backhand at 117.7 deg, under the real 124.3 line. And mock data says MOCK."""
    import json
    from coach.agent import coach_swing
    rec, sync, sid = mock_session
    sample = json.loads((SCRIPT.parents[1] / "data" / "samples" / "swing_sample.json").read_text())
    entry = dict(mss.wrist_for_sample(rec, sync, "y", sid, None)[0]["swings"][sid])
    real = coach_swing({**sample, "wrist": {**entry, "mock": False, "roll_change_abs_deg": 117.7}}, "backhand")
    assert mss.rolled_wrist_line(real, "backhand").startswith(
        "rolled_wrist: checked, not rolled, under the real backhand line: forearm roll 117.7 deg vs 124.3 deg (ESTIMATE")
    mock = coach_swing({**sample, "wrist": {**entry, "mock": True, "roll_change_abs_deg": 62.0}}, "backhand")
    assert mss.rolled_wrist_line(mock, "backhand").startswith(
        "rolled_wrist: checked, ROLLED, past the MOCK line: forearm roll 62.0 deg vs 39.2 deg")
    none = coach_swing(sample, "backhand")
    assert mss.rolled_wrist_line(none, "backhand").startswith("rolled_wrist: NOT CHECKED")


def test_the_open_line_names_the_folder_whose_web_app_lists_the_sample(mss, tmp_path):
    swings = tmp_path / "checkout" / "public" / "swings"
    assert mss.open_line(swings, "s1") == (f"open: /ghost?swing=s1 on the web app run from {tmp_path / 'checkout'} "
                                           "(Wrist sensor panel on the coach's call step)")
    other = mss.open_line(tmp_path / "dryrun", "s1")
    assert "no web app lists this sample" in other and other.endswith(f"--swings-dir {tmp_path / 'dryrun'}")


def test_the_cli_defaults_to_gyro_peak_timing(mss, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(mss, "make_sample", lambda args: seen.append(args.wrist_timing) or 0)
    base = [str(tmp_path / "clip.mov"), str(tmp_path / "s.zip"), "--tap", "f10", "--window", "1", "5",
            "--stroke", "forehand"]
    assert mss.main(base) == 0 and mss.main([*base, "--wrist-timing", "impact"]) == 0
    assert seen == ["gyro-peak", "impact"]


def test_a_gyro_peak_before_the_impact_moves_the_roll_window_and_the_fill_markers(mss, mock_session, monkeypatch):
    """The mock swings turn fastest right at their impact; a real hit may not. Force a peak 50 ms early."""
    rec, sync, sid = mock_session
    contact = mss.wrist_for_sample(rec, sync, "y", sid, None, "impact")[0]["swings"][sid]["contact_s"]
    monkeypatch.setattr(mss, "gyro_peak_near", lambda r, c: c - 0.05)
    real_report = mss.wrist_report

    def with_fill(rec_, sync_, axis, swings=None, lever=None):  # the impact pass, as if the camera were filled
        metrics, series, filled = real_report(rec_, sync_, axis, swings, lever)
        if sync_["alignment"]["pairs"]:
            series["swings"][sid]["forearm_fill"] = {"estimate": True, "label": "ESTIMATE", "frames": [1, 2, 3],
                                                     "t_ms": [-20, 0, 20], "elbow": [], "wrist": []}
        return metrics, series, filled

    monkeypatch.setattr(mss, "wrist_report", with_fill)
    gp, series, _, info = mss.wrist_for_sample(rec, sync, "y", sid, None)
    e = gp["swings"][sid]
    assert info["gyro_peak_minus_found_from_ms"] == -50.0 and e["contact_s"] == round(contact - 0.05, 3)
    assert e["roll_change_abs_deg"] == wrist_report_entry(rec, mss.gyro_peak_sync(sync, sid, contact - 0.05), sid)[
        "roll_change_abs_deg"]
    assert series["swings"][sid]["forearm_fill"]["t_ms"] == [30, 50, 70]  # ms from the gyro peak now


# ---- Codex on #93: taken file names, and --sensor-tap as the tap run ----

def _cli_inputs(tmp_path):
    """A MOCK clip, a MOCK sensor export (wrist.synth) and a copy of the demo's catalogue + backhand files."""
    import json
    import shutil
    from wrist.synth import make_session
    truth = make_session(tmp_path / "session")
    out = tmp_path / "swings"
    out.mkdir()
    swings = SCRIPT.parents[1] / "public" / "swings"
    catalogue = json.loads((swings / "catalogue.json").read_text())
    shutil.copy(swings / "catalogue.json", out / "catalogue.json")
    backhand = next(e for e in catalogue["swings"] if e["id"] == "sample_2116_backhand_stereo")
    names = [backhand["swing"], backhand["coach"], *(f["file"] for f in backhand["fixes"].values() if f.get("file"))]
    for name in names:
        shutil.copy(swings / name, out / name)
    return mock_clip(tmp_path / "clip.avi"), truth, out, names


def test_an_id_whose_files_another_entry_names_is_refused_before_anything_is_written(mss, tmp_path, capsys):
    """--id 2116_bh_stereo passed the id check, then overwrote the demo backhand's swing and coach files."""
    clip, truth, out, names = _cli_inputs(tmp_path)
    before = {n: (out / n).read_bytes() for n in ["catalogue.json", *names]}
    check = tmp_path / "tapcheck.jpg"
    args = [str(clip), str(truth["export"]), "--tap", "0.5", "--window", "1", "5", "--stroke", "backhand",
            "--id", "2116_bh_stereo", "--out-dir", str(out), "--check-image", str(check)]
    assert mss.main(args) == 1
    err = capsys.readouterr().err
    assert "_2116_bh_stereo.json belongs to catalogue entry 'sample_2116_backhand_stereo'" in err
    assert "nothing written" in err and not check.exists() and not check.with_name("pipeline_2116_bh_stereo.log").exists()
    assert {n: (out / n).read_bytes() for n in before} == before
    assert sorted(p.name for p in out.iterdir()) == sorted(before)


def test_taken_files_allow_only_this_scripts_own_sample_being_replaced(mss, tmp_path):
    out = tmp_path / "swings"
    out.mkdir()
    mine = {"id": "s1", "swing": "swing_s1.json", "coach": "coach_s1.json", "wristSeries": "wrist_s1.json",
            "fixes": {"bend_elbow": {"file": "compare_s1_bend_elbow.json"}}, "madeBy": mss.MADE_BY}
    catalogue = {"swings": [mine, {"id": "other", "swing": "swing_x.json", "coach": "coach_x.json", "fixes": {}}]}
    for name in mss.entry_files(mine):
        (out / name).write_text("{}")
    names = mss.sample_files("s1", ["bend_elbow"])
    mss.refuse_taken_files(names, catalogue, out, mine)            # replacing its own: allowed
    with pytest.raises(mss.SampleError, match="_s1.json belongs to catalogue entry 's1'"):
        mss.refuse_taken_files(names, catalogue, out, None)        # not replacing: it's s1's file
    (out / "coach_s2.json").write_text("{}")                       # on disk, in no entry
    with pytest.raises(mss.SampleError, match="coach_s2.json already exists"):
        mss.refuse_taken_files(mss.sample_files("s2", []), catalogue, out, None)
    with pytest.raises(mss.SampleError, match="swing_x.json belongs to catalogue entry 'other'"):
        mss.refuse_taken_files(["swing_x.json"], catalogue, out, mine)


def test_sensor_tap_replaces_a_false_early_tap_run(mss, tmp_path, monkeypatch, capsys):
    """A false run found first (1.9 s early): --sensor-tap names the real first tap, and the tap check
    and the impact guard (max(taps)) get the run that starts there, not the false one."""
    import dataclasses
    from wrist.load import load_recording
    clip, truth, out, _ = _cli_inputs(tmp_path)
    rec = load_recording(truth["export"])
    spikes = mss.find_spikes(rec, mss.SPIKE_K)
    real = mss.first_tap_event(rec, spikes)
    assert real is not None and len(real) >= 2 and real[0] - 1.9 > rec.t[0]
    tap = next(s for s in spikes if abs(s.t - real[0]) < 0.1)
    # more than TAP_GAP_S[1] (1.5 s) before the real run, so it is a run of its own
    false_run = [dataclasses.replace(tap, t=real[0] - 1.9), dataclasses.replace(tap, t=real[0] - 1.6)]
    with_false = sorted(false_run + spikes, key=lambda s: s.t)
    detected = mss.first_tap_event(rec, with_false)
    assert detected[0] < real[0] - 1.5  # the detection now picks the false run
    assert mss.operator_tap_run(rec, with_false, real[0]) == real
    assert mss.operator_tap_run(rec, with_false, real[0] + 30.0) == [real[0] + 30.0]  # no run there: the tap alone

    seen = {}
    monkeypatch.setattr(mss, "find_spikes", lambda r, k: with_false)
    monkeypatch.setattr(mss, "tap_frames", lambda *a: [])  # the mock clip is 2 s long; frames aren't the point here
    monkeypatch.setattr(mss, "find_hands_box", lambda *a: None)

    def stop(clip_, tap_play, taps, slowdown, out_, box):
        seen["taps"] = list(taps)
        raise mss.SampleError("stop after the tap check")
    monkeypatch.setattr(mss, "tap_check_image", stop)
    args = [str(clip), str(truth["export"]), "--tap", "0.5", "--window", "1", "5", "--stroke", "backhand",
            "--sensor-tap", str(real[0]), "--out-dir", str(out), "--check-image", str(tmp_path / "check.jpg")]
    assert mss.main(args) == 1  # the stop above
    assert seen["taps"] == real and max(seen["taps"]) == real[-1]
    assert f"replaces the detected tap run at {detected[0]:.3f} s" in capsys.readouterr().out


def test_a_tap_past_the_clip_is_refused_and_no_tap_check_is_written(mss, tmp_path, monkeypatch, capsys):
    """Codex P1 on #93: a tap check silently missing a row hid a wrong --slowdown or a short clip."""
    clip = mock_clip(tmp_path / "clip.avi")  # 60 frames at 30 fps: f0-f59
    out = tmp_path / "tapcheck.jpg"
    # At 4x the taps land at 0.2, 1.32 and 2.6 playback s: frames 6, 40 and 78, past f59.
    with pytest.raises(mss.SampleError) as e:
        mss.tap_check_image(clip, 0.2, [10.0, 10.28, 10.6], 4.0, out, box=(40, 20, 100, 80))
    msg = str(e.value)
    assert "tap 3 at 2.600 playback s (f78)" in msg and "tap 1" not in msg and "tap 2" not in msg
    assert "f0-f59" in msg and "--tap" in msg and "--slowdown" in msg and "covers every tap" in msg
    assert not out.exists()
    # Through the CLI: refused before anything is written, not even the pipeline log.
    clip_, truth, swings, _ = _cli_inputs(tmp_path / "cli")
    monkeypatch.setattr(mss, "first_tap_event", lambda rec, spikes, from_s=None: [10.0, 10.28, 10.6])
    monkeypatch.setattr(mss, "find_hands_box", lambda *a: pytest.fail("ran past the tap frames"))
    check = tmp_path / "cli" / "check.jpg"
    args = [str(clip_), str(truth["export"]), "--tap", "0.2", "--window", "1", "5", "--stroke", "backhand",
            "--id", "taps_past_clip", "--out-dir", str(swings), "--check-image", str(check)]
    assert mss.main(args) == 1
    assert "tap 3 at 2.600 playback s (f78)" in capsys.readouterr().err
    assert not check.exists() and not check.with_name("pipeline_taps_past_clip.log").exists()


@pytest.mark.parametrize("box", [None, (40, 20, 100, 80)])
def test_a_tap_within_before_frames_of_the_clip_start_is_refused_and_nothing_is_written(mss, tmp_path, box):
    """Codex P1 on #93: tap 1 at frame 2 has no frame 3 earlier; that tile was black (or, with no hands
    box, missing), so nobody could confirm tap 1 was the first contact."""
    clip = mock_clip(tmp_path / "clip.avi")
    out = tmp_path / "tapcheck.jpg"
    with pytest.raises(mss.SampleError, match=r"tap 1's frame 3 frames before \(f-1, tap at 0.067 playback s, f2\)"):
        mss.tap_check_image(clip, 2 / 30, [10.0, 10.28], 4.0, out, box=box)
    assert not out.exists()


def test_a_tap_near_the_clip_start_stops_the_cli_before_anything_is_written(mss, tmp_path, monkeypatch, capsys):
    clip, truth, swings, _ = _cli_inputs(tmp_path)
    monkeypatch.setattr(mss, "first_tap_event", lambda rec, spikes, from_s=None: [10.0, 10.28])
    monkeypatch.setattr(mss, "find_hands_box", lambda *a: pytest.fail("ran past the tap frames"))
    check = tmp_path / "check.jpg"
    args = [str(clip), str(truth["export"]), "--tap", "f2", "--window", "1", "5", "--stroke", "backhand",
            "--id", "tap_at_start", "--out-dir", str(swings), "--check-image", str(check)]
    assert mss.main(args) == 1
    assert "tap 1's frame 3 frames before (f-1" in capsys.readouterr().err
    assert not check.exists() and not check.with_name("pipeline_tap_at_start.log").exists()


def _window_md() -> dict:
    """A pipeline swing's metadata for a cut window, as the 14 Nov dry run saved it (times from the cut)."""
    return {"realStartSeconds": 0.3, "sourceStartSeconds": 0.3, "sourcePeakSeconds": 1.075,
            "sourceContactSeconds": 0.9, "sourceStartFrame": 36, "sourceContactFrame": 108,
            "sourceStartPlaybackSeconds": 1.2, "sourceContactPlaybackSeconds": 3.6,
            "sourceTimeBase": "normalized-real-time", "slowdown": 4.0, "captureFps": 120.0,
            "contactMethod": "audio-transient"}


def test_source_times_are_rebased_to_the_original_clip(mss):
    md = _window_md()
    mss.rebase_to_clip(md, 10.0, 4.0, 120.0)  # --window starting at 10 playback s, 4x, 120 fps real
    assert md["sourceContactSeconds"] == pytest.approx(0.9 + 10 / 4)
    assert (md["realStartSeconds"], md["sourceStartSeconds"], md["sourcePeakSeconds"]) == pytest.approx((2.8, 2.8, 3.575))
    assert (md["sourceStartPlaybackSeconds"], md["sourceContactPlaybackSeconds"]) == pytest.approx((11.2, 13.6))
    assert (md["sourceStartFrame"], md["sourceContactFrame"]) == (36 + 300, 108 + 300)
    assert md["sourceContactPlaybackSeconds"] == pytest.approx(md["sourceContactSeconds"] * 4)
    assert md["sourceContactFrame"] == round(md["sourceContactSeconds"] * 120)
    assert (md["slowdown"], md["captureFps"], md["sourceTimeBase"]) == (4.0, 120.0, "normalized-real-time")


def test_a_window_starting_at_10_s_saves_contact_in_the_original_clip(mss, tmp_path, monkeypatch):
    """Codex P2 on #93: sourceClip names the original movie, so its times must be the movie's."""
    clip, truth, swings, _ = _cli_inputs(tmp_path)
    seen = {}
    fake = {"metadata": _window_md(), "fpsReal": 120.0, "frames": [], "contactFrame": 0}
    monkeypatch.setattr(mss, "tap_frames", lambda *a: [])
    monkeypatch.setattr(mss, "find_hands_box", lambda *a: None)
    monkeypatch.setattr(mss, "tap_check_image", lambda clip_, tap_play, taps, *a: [tap_play])
    monkeypatch.setattr(mss, "cut_window", lambda *a: None)
    monkeypatch.setattr(mss, "run_pipeline", lambda *a: [fake])

    def stop(shadow, method):  # called just after the metadata is set (--shadow)
        seen["md"] = dict(fake["metadata"])
        raise mss.SampleError("stop after the metadata")
    monkeypatch.setattr(mss, "shadow_contact_warning", stop)
    args = [str(clip), str(truth["export"]), "--tap", "0.2", "--window", "10", "14", "--stroke", "backhand",
            "--shadow", "--id", "window_at_10", "--out-dir", str(swings), "--check-image", str(tmp_path / "c.jpg")]
    assert mss.main(args) == 1
    md = seen["md"]
    assert md["sourceClip"] == clip.name and md["sourceWindowPlaybackSeconds"] == [10.0, 14.0]
    assert md["sourceContactSeconds"] == pytest.approx(0.9 + 10 / 4)  # the window's value + 10 / slowdown
    assert md["sourceContactFrame"] == 108 + 300 and md["sourceContactPlaybackSeconds"] == pytest.approx(13.6)
