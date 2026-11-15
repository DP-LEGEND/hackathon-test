"""Optional CSV attachment: generated sensor motion, real sync/metrics/fusion code."""
import copy
import csv
import json
from pathlib import Path
import wave

import numpy as np
import pytest

from pipeline import multi_wrist
from pipeline.video import VideoInfo
from wrist.fuse import read_swings
from wrist.load import load_recording
from wrist.synth import make_session


@pytest.fixture
def session(tmp_path):
    truth = make_session(tmp_path / "mock", labels=("none", "rolled_wrist"),
                         camera=True, video_jitter_s=0, shadow=(1,))
    rec = load_recording(truth["export"])
    swings = list(read_swings(truth["swings_dir"]).values())
    return truth, rec, swings


def flat_csv(path, rec, *, mock=True, aliases=False):
    fields = (["ax", "ay", "az", "gx", "gy", "gz"] if aliases else
              ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z"])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["seconds_elapsed", *fields, "qx", "qy", "qz", "qw", "mock"])
        for i, t in enumerate(rec.t):
            writer.writerow([t, *rec.acc[i], *rec.gyro[i], *rec.quat[i], str(mock).lower()])
    return path


def info(slowdown=1, edits=None):
    return VideoInfo(fps=30, base_fps=30, duration=30, capture_fps=30 * slowdown,
                     slowdown=slowdown, source="manual", edits=edits or [])


@pytest.mark.parametrize("mock", [True, False])
def test_tap_synced_csv_attaches_wrist_and_preserves_camera_contact(session, tmp_path, monkeypatch, mock):
    truth, rec, swings = session
    original = copy.deepcopy(swings)
    sensor = flat_csv(tmp_path / "sensor.csv", rec, mock=mock)
    hits = np.asarray(truth["taps_s"]) - truth["video_offset_s"]
    monkeypatch.setattr(multi_wrist, "_video_taps", lambda *args: hits)
    enriched, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                  slowdown=1, work=tmp_path, info=info())
    assert swings == original, "attachment never mutates the caller's originals"
    assert enriched is not swings
    for before, after in zip(swings, enriched):
        wrist = after["wrist"]
        assert wrist["usable"] and wrist["mock"] is mock
        assert wrist["contact_source"] == "gyro peak"
        assert wrist["timing"]["found_from"] in ("impact spike", "double tap")
        assert after["contactFrame"] == before["contactFrame"]
        assert after["metadata"]["sourceContactSeconds"] == before["metadata"]["sourceContactSeconds"]
        assert wrist["racket_speed_sensor"]["contact_source"] == wrist["timing"]["found_from"]
        assert after["metadata"]["wristSync"]["offsetSeconds"] == pytest.approx(truth["video_offset_s"], abs=.02)
        assert wrist["racket_speed_sensor"]["value"] > 0
    assert not any(warning.startswith("Sensor CSV ignored") for warning in warnings)
    assert not list(tmp_path.glob(".wrist-*")), "decoded optional inputs are temporary"
    json.dumps(enriched, allow_nan=False)


def test_flat_loader_short_aliases_preserve_units_and_mock(session, tmp_path):
    _, rec, _ = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec, aliases=True)
    work = tmp_path / "decoded"
    work.mkdir()
    result = multi_wrist._flat_recording(sensor, work)
    assert result.mock is True
    assert result.rate_hz == 100
    assert result.gyro == pytest.approx(rec.gyro)
    assert result.acc == pytest.approx(rec.acc)


@pytest.mark.parametrize("contents", [
    "not,a,sensor\n1,2,3\n",
    "seconds_elapsed,ax,ay,az,gx,gy,gz\n0,0,0,0,0,0,0\n0,0,0,0,0,0,0\n",
    "seconds_elapsed,ax,ay,az,gx,gy,gz\n0,nan,0,0,0,0,0\n1,0,0,0,0,0,0\n",
])
def test_bad_csv_is_ignored_without_mutating_swings(session, tmp_path, contents):
    _, _, swings = session
    original = copy.deepcopy(swings)
    sensor = tmp_path / "bad.csv"
    sensor.write_text(contents, encoding="utf-8")
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info())
    assert result is swings and swings == original
    assert warnings and warnings[0].startswith("Sensor CSV ignored:")
    assert not list(tmp_path.glob(".wrist-*"))


@pytest.mark.parametrize("hits", [[], [2.1], [0.1, 0.55]])
def test_missing_or_unmatched_audio_taps_ignore_csv(session, tmp_path, monkeypatch, hits):
    _, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    monkeypatch.setattr(multi_wrist, "_video_taps", lambda *args: np.asarray(hits))
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info())
    assert result is swings
    assert "no matching audio double tap" in warnings[0]
    assert all("wrist" not in swing for swing in result)


def test_ambiguous_audio_double_tap_never_picks_a_clock(session, monkeypatch):
    truth, rec, swings = session
    hits = np.asarray(truth["taps_s"]) - truth["video_offset_s"]
    contacts = [(s["id"], s["metadata"]["sourceContactSeconds"]) for s in swings]
    # Two identical tap intervals with independently plausible alignment must be rejected.
    monkeypatch.setattr(multi_wrist, "align", lambda *args, **kwargs: {
        "error_ms": {"n_ok": 1}, "tap_only": [], "pairs": [], "offset_s": 0})
    with pytest.raises(ValueError, match="ambiguous audio double tap"):
        multi_wrist._tap_sync(rec, contacts, np.r_[hits - 2, hits])


def test_no_audio_or_decoder_failure_is_only_a_warning(session, tmp_path, monkeypatch):
    _, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)

    def unavailable(*args):
        raise RuntimeError("private decoder configuration")

    monkeypatch.setattr(multi_wrist, "_video_taps", unavailable)
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info())
    assert result is swings and "private" not in str(warnings)
    assert "Sensor CSV ignored" in warnings[0]


def test_quicktime_audio_taps_use_existing_real_time_mapping(tmp_path, monkeypatch):
    mapped_info = info(4, [{"playbackStart": 0, "playbackEnd": 8, "rate": .5}])
    monkeypatch.setattr(multi_wrist, "run_tool", lambda *args, **kwargs: "")
    monkeypatch.setattr(multi_wrist, "audio_hits", lambda *args, **kwargs: np.array([2., 4.]))
    assert multi_wrist._video_taps(tmp_path / "clip.mov", tmp_path, mapped_info) == pytest.approx([.25, .5])


def test_detected_audio_taps_sync_generated_sensor_without_a_manual_time(session, tmp_path, monkeypatch):
    truth, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    taps = np.asarray(truth["taps_s"]) - truth["video_offset_s"]

    def decoded_audio(arguments, **kwargs):
        # Stand in only for video decoding; transient detection, timing, sync,
        # wrist measurement and attachment run for real on labelled MOCK data.
        rng = np.random.default_rng(42)
        rate = 16_000
        samples = rng.normal(0, .0001, 10 * rate)
        for t in taps:
            index = int(round(t * rate))
            samples[index:index + 80] += rng.normal(0, .2, 80)
        with wave.open(str(arguments[-1]), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return ""

    monkeypatch.setattr(multi_wrist, "run_tool", decoded_audio)
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info())
    assert result is not swings, warnings
    assert all(s["wrist"]["usable"] and s["wrist"]["mock"] for s in result)
    assert result[0]["metadata"]["wristSync"]["videoTapSeconds"] == pytest.approx(taps[0], abs=.01)


def test_sensor_failure_after_partial_processing_discards_all_mutations(session, tmp_path, monkeypatch):
    truth, rec, swings = session
    original = copy.deepcopy(swings)
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    monkeypatch.setattr(multi_wrist, "_video_taps", lambda *args: np.asarray(truth["taps_s"]) - truth["video_offset_s"])

    def broken_report(*args, **kwargs):
        first = next(iter(kwargs["swings"].values()))
        first["metadata"]["mutated"] = True
        raise ValueError("sensor measurement failed")

    monkeypatch.setattr(multi_wrist, "wrist_report", broken_report)
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info())
    assert result is swings and swings == original
    assert warnings[0].startswith("Sensor CSV ignored:")
