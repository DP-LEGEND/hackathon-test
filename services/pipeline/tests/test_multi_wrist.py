"""Optional CSV/ZIP attachment with dominant swing sequence timing."""
import copy
import csv
import json
from pathlib import Path
import wave
import zipfile

import numpy as np
import pytest

from pipeline import multi_audio, multi_wrist
from pipeline.video import VideoInfo
from wrist.fuse import read_swings
from wrist.load import load_recording
from wrist.synth import make_session


@pytest.fixture
def session(tmp_path):
    truth = make_session(tmp_path / "mock", labels=("none", "rolled_wrist", "none"),
                         camera=True, video_jitter_s=0, shadow=(1,), zip_export=True)
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


def video_hits(truth):
    return np.asarray([row["impact_s"] - truth["video_offset_s"] for row in truth["swings"].values()])


@pytest.mark.parametrize("mock", [True, False])
@pytest.mark.parametrize("filename", ["sensor.csv", "sensor.ZIP", "sensor.bin"])
def test_sequence_synced_sensor_preserves_camera_contact(session, tmp_path, monkeypatch, mock, filename):
    truth, rec, swings = session
    original = copy.deepcopy(swings)
    sensor = tmp_path / filename
    if sensor.suffix == ".csv":
        flat_csv(sensor, rec, mock=mock)
    else:
        with zipfile.ZipFile(sensor, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for source in (Path(truth["export"]).parent / "export").glob("*.csv"):
                if source.name != "Metadata.csv":
                    archive.write(source, f"recording/{source.name}")
            archive.writestr("recording/Metadata.csv", f"mock\n{str(mock).lower()}\n")
    monkeypatch.setattr(multi_wrist, "_video_swing_times", lambda *args: video_hits(truth))
    debug = {}
    enriched, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                  slowdown=1, work=tmp_path, info=info(), debug=debug)
    assert swings == original
    assert enriched is not swings, warnings
    for before, after in zip(swings, enriched):
        wrist = after["wrist"]
        assert wrist["usable"] and wrist["mock"] is mock
        assert wrist["contact_source"] == "gyro peak"
        assert wrist["timing"]["found_from"] == "dominant swing sequence"
        assert after["contactFrame"] == before["contactFrame"]
        assert after["metadata"]["sourceContactSeconds"] == before["metadata"]["sourceContactSeconds"]
        assert wrist["racket_speed_sensor"]["contact_source"] == "gyro peak"
        assert after["metadata"]["wristSync"]["offsetSeconds"] == pytest.approx(truth["video_offset_s"], abs=.08)
        assert wrist["racket_speed_sensor"]["value"] > 0
    assert debug["status"] == "attached" and debug["matchedCount"] == 3
    assert len(debug["chosenGyroTimesSeconds"]) == 3
    assert debug["residualMs"] <= 120
    assert not any(warning.startswith("Sensor data ignored") for warning in warnings)
    assert not list(tmp_path.glob(".wrist-*"))
    json.dumps({"swings": enriched, "debug": debug}, allow_nan=False)


def test_low_gyro_movements_before_swings_do_not_move_clock(session, tmp_path):
    truth, rec, swings = session
    contacts = [row["impact_s"] for row in truth["swings"].values()]
    for contact in contacts:
        for lead in (.95, .65, .35):
            rec.gyro[:, 0] += 2 * np.exp(-((rec.t - (contact - lead)) / .025) ** 2)
    selected, _ = multi_wrist._gyro_swings(rec)
    assert len(selected) == 3
    assert selected == pytest.approx(contacts, abs=.08)
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
        slowdown=1, work=tmp_path, info=info(), debug=debug, video_swing_times=video_hits(truth).tolist())
    assert result is not swings, warnings
    assert debug["offsetSeconds"] == pytest.approx(truth["video_offset_s"], abs=.08)
    assert debug["chosenGyroTimesSeconds"] == pytest.approx(selected)


def test_flat_loader_short_aliases_preserve_units_and_mock(session, tmp_path):
    _, rec, _ = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec, aliases=True)
    work = tmp_path / "decoded"
    work.mkdir()
    result = multi_wrist._flat_recording(sensor, work)
    assert result.mock is True and result.rate_hz == 100
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
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info(), debug=debug)
    assert result is swings and swings == original
    assert warnings[0].startswith("Sensor data ignored:")
    assert debug["status"] == "ignored" and debug["reason"]
    assert not list(tmp_path.glob(".wrist-*"))


@pytest.mark.parametrize("hits", [[], [2.1], [0.1, .55], [1, 4, 9]])
def test_insufficient_or_inconsistent_audio_ignores_sensor(session, tmp_path, hits):
    _, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
        slowdown=1, work=tmp_path, info=info(), debug=debug, video_swing_times=hits)
    assert result is swings and all("wrist" not in swing for swing in result)
    assert debug["status"] == "ignored" and "offset not found" in debug["reason"]
    assert "provide offset_b_s" not in str(warnings)


def test_ambiguous_repeated_sequence_never_picks_a_clock(session):
    truth, rec, swings = session
    gyro, _ = multi_wrist._gyro_swings(rec)
    contacts = [(s["id"], s["metadata"]["sourceContactSeconds"]) for s in swings]
    with pytest.raises(ValueError, match="ambiguous"):
        multi_wrist._sequence_sync(rec, contacts, np.r_[gyro + 1, gyro + 40], {})


def test_invalid_video_times_leave_serializable_warning_debug(session, tmp_path):
    _, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
        slowdown=1, work=tmp_path, info=info(), debug=debug, video_swing_times=[1, float("nan"), 4])
    assert result is swings and warnings
    assert debug["status"] == "ignored" and "finite" in debug["reason"]
    json.dumps(debug, allow_nan=False)


def test_no_audio_or_decoder_failure_is_only_a_warning(session, tmp_path, monkeypatch):
    _, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)

    def unavailable(*args):
        raise RuntimeError("private decoder configuration")

    monkeypatch.setattr(multi_wrist, "_video_swing_times", unavailable)
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info(), debug=debug)
    assert result is swings and "private" not in str(warnings)
    assert debug["status"] == "ignored" and "private" not in str(debug)


def test_audio_and_gyro_small_events_before_big_swings_sync(session, tmp_path, monkeypatch):
    truth, rec, swings = session
    sensor = flat_csv(tmp_path / "sensor.csv", rec)
    hits = video_hits(truth)

    def decoded_audio(arguments, **kwargs):
        rng = np.random.default_rng(42)
        rate = 16_000
        samples = rng.normal(0, .00005, 30 * rate)
        for hit in hits:
            for lead, amplitude in ((1.0, .025), (.65, .04), (.3, .03), (0, .5)):
                index = int(round((hit - lead) * rate))
                samples[index:index + 80] += rng.normal(0, amplitude, 80)
        with wave.open(str(arguments[-1]), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        return ""

    monkeypatch.setattr(multi_audio, "run_tool", decoded_audio)
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info(), debug=debug)
    assert result is not swings, warnings
    assert debug["chosenVideoTimesSeconds"] == pytest.approx(hits, abs=.015)
    assert debug["offsetSeconds"] == pytest.approx(truth["video_offset_s"], abs=.08)
    assert all(s["wrist"]["usable"] and s["wrist"]["mock"] for s in result)


def test_sensor_failure_after_partial_processing_discards_all_mutations(session, tmp_path, monkeypatch):
    truth, rec, swings = session
    original = copy.deepcopy(swings)
    sensor = flat_csv(tmp_path / "sensor.csv", rec)

    def broken_report(*args, **kwargs):
        first = next(iter(kwargs["swings"].values()))
        first["metadata"]["mutated"] = True
        raise ValueError("sensor measurement failed")

    monkeypatch.setattr(multi_wrist, "wrist_report", broken_report)
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
        slowdown=1, work=tmp_path, info=info(), debug=debug, video_swing_times=video_hits(truth).tolist())
    assert result is swings and swings == original
    assert debug["status"] == "ignored" and debug["reason"] == "sensor measurement failed"
    assert warnings[0].startswith("Sensor data ignored:")


@pytest.mark.parametrize("failure", ["corrupt", "missing_gyro", "expanded_size", "time_grid"])
def test_unreadable_or_unbounded_zip_is_only_a_warning(session, tmp_path, monkeypatch, failure):
    _, _, swings = session
    original = copy.deepcopy(swings)
    sensor = tmp_path / "bad.zip"
    if failure == "corrupt":
        sensor.write_bytes(b"PK\x03\x04broken archive")
    else:
        with zipfile.ZipFile(sensor, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if failure == "expanded_size":
                archive.writestr("Accelerometer.csv", "0" * 2048)
                monkeypatch.setattr(multi_wrist, "MAX_SENSOR_BYTES", 512)
            else:
                times = [0, .01, .02, 1e12] if failure == "time_grid" else np.arange(101) / 100
                archive.writestr("Accelerometer.csv", "seconds_elapsed,x,y,z\n" +
                                 "".join(f"{t},0,0,0\n" for t in times))
    debug = {}
    result, warnings = multi_wrist.attach_sensor(swings, tmp_path / "clip.mov", sensor,
                                                slowdown=1, work=tmp_path, info=info(), debug=debug)
    assert result is swings and swings == original
    assert warnings[0].startswith("Sensor data ignored:") and debug["status"] == "ignored"
    if failure == "expanded_size":
        assert "expands beyond" in warnings[0]
    elif failure == "time_grid":
        assert "1000 Hz" in warnings[0]
    assert not list(tmp_path.glob(".wrist-*"))
