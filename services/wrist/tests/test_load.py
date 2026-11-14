"""Reading Sensor Logger exports (MOCK data from wrist.synth)."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import numpy as np
import pytest

from wrist.load import LoadError, load_recording
from wrist.metrics import gyro_convention
from wrist.synth import make_session


def _rewrite(path: Path, keep: list[str]) -> None:
    """Rewrite a CSV with only `keep` columns, in that order."""
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keep, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


@pytest.fixture()
def export(tmp_path: Path) -> Path:
    truth = make_session(tmp_path / "s", labels=("none", "rolled_wrist", "none"))
    return Path(truth["export"])


def test_uniform_grid_unit_quaternions_and_mock_flag(session) -> None:
    rec = session.rec
    assert rec.rate_hz == 100.0
    assert np.allclose(np.diff(rec.t), 0.01)
    assert rec.acc.shape == rec.gyro.shape == (rec.t.size, 3) and rec.quat.shape == (rec.t.size, 4)
    assert np.allclose(np.linalg.norm(rec.quat, axis=1), 1.0)
    assert np.all(np.einsum("ij,ij->i", rec.quat[1:], rec.quat[:-1]) > 0), "sign-continuous"
    assert rec.orientation == "quaternion" and rec.mock is True


def test_zip_and_folder_load_the_same(tmp_path: Path) -> None:
    truth = make_session(tmp_path, labels=("none", "none", "rolled_wrist"), zip_export=True)
    a, b = load_recording(truth["export"]), load_recording(tmp_path / "export")
    assert truth["export"].endswith(".zip")
    assert np.array_equal(a.t, b.t) and np.allclose(a.gyro, b.gyro) and np.allclose(a.quat, b.quat)


def test_columns_are_read_by_name_not_position(export: Path, tmp_path: Path) -> None:
    other = tmp_path / "reordered"
    shutil.copytree(export, other)
    _rewrite(other / "Gyroscope.csv", ["x", "seconds_elapsed", "y", "time", "z"])
    _rewrite(other / "Orientation.csv", ["qw", "qx", "seconds_elapsed", "qy", "qz"])
    a, b = load_recording(export), load_recording(other)
    assert np.allclose(a.gyro, b.gyro) and np.allclose(a.quat, b.quat)


def test_unix_time_only_still_lines_the_sensors_up(export: Path, tmp_path: Path) -> None:
    other = tmp_path / "epoch"
    shutil.copytree(export, other)
    for name, cols in (("Accelerometer", ["time", "z", "y", "x"]), ("Gyroscope", ["time", "z", "y", "x"]),
                       ("Orientation", ["time", "qz", "qy", "qx", "qw"])):
        _rewrite(other / f"{name}.csv", cols)
    a, b = load_recording(export), load_recording(other)
    shift = b.t[0] - a.t[0]
    assert np.allclose(b.t - a.t, shift, atol=1e-6), "same grid, one shared zero"
    # ns vs us timestamps differ by ~1 us, so the resampled values differ in the 6th decimal.
    assert np.allclose(a.gyro, b.gyro, atol=1e-4) and np.allclose(a.quat, b.quat, atol=1e-4)


def test_roll_pitch_yaw_used_when_there_is_no_quaternion(export: Path, tmp_path: Path) -> None:
    other = tmp_path / "euler"
    shutil.copytree(export, other)
    _rewrite(other / "Orientation.csv", ["time", "seconds_elapsed", "roll", "pitch", "yaw"])
    rec = load_recording(other)
    assert rec.orientation == "euler (assumed ZXY)"
    assert gyro_convention(rec)["ok"], "the Euler fallback still matches the gyro"


def test_orientation_file_is_optional(export: Path, tmp_path: Path) -> None:
    gone = tmp_path / "no-orientation"
    shutil.copytree(export, gone)
    (gone / "Orientation.csv").unlink()
    rec = load_recording(gone)
    full = load_recording(export)
    assert rec.quat is None and rec.orientation == "none" and rec.mock is True
    assert gyro_convention(rec)["ok"] is False and gyro_convention(rec)["convention"] is None
    assert rec.t.size == pytest.approx(full.t.size, abs=2), "accelerometer and gyro still line up"


def test_no_metadata_means_not_mock(export: Path) -> None:
    (export / "Metadata.csv").unlink()
    assert load_recording(export).mock is False


def test_errors_name_what_is_missing(export: Path, tmp_path: Path) -> None:
    gone = tmp_path / "no-gyro"
    shutil.copytree(export, gone)
    (gone / "Gyroscope.csv").unlink()
    with pytest.raises(LoadError, match="Gyroscope.csv"):
        load_recording(gone)

    bad = tmp_path / "bad-cols"
    shutil.copytree(export, bad)
    _rewrite(bad / "Gyroscope.csv", ["seconds_elapsed", "x", "y"])
    with pytest.raises(LoadError, match=r"missing columns \['z'\]"):
        load_recording(bad)

    with pytest.raises(LoadError, match="folder or .zip"):
        load_recording(export / "Accelerometer.csv")
