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
    # Without a zoom it is the old grid of whole frames, 3 per row.
    mss.tap_check_image(clip, 0.2, [10.0, 10.28], 4.0, out)
    assert cv2.imread(str(out)).shape[:2] == (mss.TILE_H, 3 * full_w)


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
