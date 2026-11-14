"""Read a Sensor Logger export (phone strapped to the forearm). Owner: Henoch.

Sensor Logger (iOS/Android) exports one CSV per sensor, as a folder or a .zip:

    Accelerometer.csv   time,seconds_elapsed,z,y,x            m/s^2, gravity removed
    Gyroscope.csv       time,seconds_elapsed,z,y,x            rad/s, phone axes
    Orientation.csv     time,seconds_elapsed,qz,qy,qx,qw,roll,pitch,yaw   (radians); optional
    Metadata.csv        optional; our synthetic exports mark themselves mock here

Columns are read by NAME, so their order doesn't matter. `time` is Unix nanoseconds;
`seconds_elapsed` is seconds since Start Recording (can be slightly negative). If
Accelerometer.csv is missing, TotalAcceleration.csv is used (gravity is a slow
offset, which the spike detector's high-pass ignores).

The three streams have their own timestamps, so load_recording() resamples them onto
one uniform grid (the accelerometer's median rate, 100 Hz in Sensor Logger's fastest
setting). Orientation is kept as unit quaternions (x, y, z, w), sign-continuous, so
interpolating between neighbours is safe at 100 Hz. If there are no quaternion
columns, roll/pitch/yaw are converted assuming iOS's Z-X-Y order; Recording.orientation
says which was used, and metrics.gyro_convention() checks it against the gyro anyway.
Without Orientation.csv, quat is None (orientation "none") and metrics integrates the gyro
instead (orient.py).

Never commit real exports: put them in data/raw/ (git-ignored).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.spatial.transform import Rotation

ACCEL_FILES = ("Accelerometer", "TotalAcceleration")
GYRO_FILES = ("Gyroscope",)
ORIENT_FILES = ("Orientation",)
QUAT_COLS = ("qx", "qy", "qz", "qw")
EULER_COLS = ("roll", "pitch", "yaw")


class LoadError(ValueError):
    """The export is missing a file or a column we need."""


@dataclass
class Recording:
    t: np.ndarray        # (N,) seconds since Start Recording, uniform grid
    acc: np.ndarray      # (N, 3) phone x, y, z acceleration, m/s^2
    gyro: np.ndarray     # (N, 3) phone x, y, z angular velocity, rad/s
    quat: Optional[np.ndarray]  # (N, 4) orientation x, y, z, w (unit, sign-continuous); None without one
    rate_hz: float
    orientation: str     # "quaternion", "euler (assumed ZXY)" or "none" (no Orientation.csv)
    mock: bool           # True for synthetic exports: say so on screen
    source: str


def _read_table(text: str, name: str) -> dict[str, np.ndarray]:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        raise LoadError(f"{name}: needs a header and at least two rows")
    header = [h.strip().lower() for h in rows[0]]
    data = [r for r in rows[1:] if r and any(c.strip() for c in r)]
    out: dict[str, np.ndarray] = {}
    for j, col in enumerate(header):
        try:
            out[col] = np.array([float(r[j]) for r in data])
        except (ValueError, IndexError):
            continue  # text columns (Metadata) aren't needed as numbers
    return out


def _times(cols: dict[str, np.ndarray], name: str) -> np.ndarray:
    if "seconds_elapsed" in cols:
        return cols["seconds_elapsed"]
    if "time" in cols:
        return cols["time"] / 1e9  # Unix ns -> s; made relative in load_recording
    raise LoadError(f"{name}: no 'seconds_elapsed' or 'time' column (has {sorted(cols)})")


def _need(cols: dict[str, np.ndarray], keys: tuple[str, ...], name: str) -> np.ndarray:
    missing = [k for k in keys if k not in cols]
    if missing:
        raise LoadError(f"{name}: missing columns {missing} (has {sorted(cols)})")
    return np.column_stack([cols[k] for k in keys])


class _Source:
    """A folder or a .zip of CSVs, looked up by file stem, case-insensitively."""

    def __init__(self, path: Path):
        self.path = path
        if path.is_dir():
            self.files = {p.stem.lower(): p for p in path.rglob("*.csv")}
            self.zip = None
        elif path.suffix.lower() == ".zip":
            self.zip = zipfile.ZipFile(path)
            self.files = {Path(n).stem.lower(): n for n in self.zip.namelist() if n.lower().endswith(".csv")}
        else:
            raise LoadError(f"{path}: expected a Sensor Logger export folder or .zip")

    def read(self, stems: tuple[str, ...]) -> tuple[Optional[str], Optional[str]]:
        for stem in stems:
            key = self.files.get(stem.lower())
            if key is None:
                continue
            if self.zip is not None:
                return stem, self.zip.read(key).decode("utf-8-sig")
            return stem, Path(key).read_text(encoding="utf-8-sig")
        return None, None


def _is_mock(text: Optional[str]) -> bool:
    if not text:
        return False
    rows = list(csv.DictReader(io.StringIO(text)))
    for row in rows:
        for k, v in row.items():
            if (k or "").strip().lower() == "mock" and str(v).strip().lower() in ("1", "true", "yes"):
                return True
            if "synthetic" in str(v).lower():
                return True
    return False


def _continuous(q: np.ndarray) -> np.ndarray:
    """Flip signs so neighbouring quaternions agree (q and -q are the same rotation)."""
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    flips = np.sign(np.einsum("ij,ij->i", q[1:], q[:-1]))
    flips[flips == 0] = 1
    signs = np.concatenate([[1.0], np.cumprod(flips)])
    return q * signs[:, None]


def _interp(t_new: np.ndarray, t: np.ndarray, v: np.ndarray) -> np.ndarray:
    order = np.argsort(t, kind="stable")
    t, v = t[order], v[order]
    return np.column_stack([np.interp(t_new, t, v[:, k]) for k in range(v.shape[1])])


def load_recording(path: str | Path) -> Recording:
    """Load accelerometer, gyroscope and (if exported) orientation onto one uniform time grid."""
    src = _Source(Path(path))
    streams = {}
    for key, stems in (("acc", ACCEL_FILES), ("gyro", GYRO_FILES), ("orient", ORIENT_FILES)):
        stem, text = src.read(stems)
        if text is None and key == "orient":
            continue  # optional: metrics integrates the gyro instead
        if text is None:
            raise LoadError(f"{path}: no {' or '.join(s + '.csv' for s in stems)} in the export")
        cols = _read_table(text, f"{stem}.csv")
        streams[key] = (cols, _times(cols, f"{stem}.csv"), f"{stem}.csv")

    uses_epoch = any("seconds_elapsed" not in c for c, _, _ in streams.values())
    if uses_epoch:  # make Unix times relative, with ONE shared zero
        t0 = min(t.min() for _, t, _ in streams.values())
        streams = {k: (c, t - t0, n) for k, (c, t, n) in streams.items()}

    acc_cols, t_acc, acc_name = streams["acc"]
    gyro_cols, t_gyro, gyro_name = streams["gyro"]
    acc = _need(acc_cols, ("x", "y", "z"), acc_name)
    gyro = _need(gyro_cols, ("x", "y", "z"), gyro_name)
    quat: Optional[np.ndarray] = None
    orientation = "none"
    if "orient" in streams:
        o_cols, t_o, o_name = streams["orient"]
        if all(k in o_cols for k in QUAT_COLS):
            quat = _need(o_cols, QUAT_COLS, o_name)
            orientation = "quaternion"
        else:
            rpy = _need(o_cols, EULER_COLS, o_name)
            # iOS CMAttitude: yaw about z, pitch about x, roll about y, applied in that order.
            quat = Rotation.from_euler("ZXY", rpy[:, [2, 1, 0]]).as_quat()
            orientation = "euler (assumed ZXY)"

    dt = np.median(np.diff(np.sort(t_acc)))
    if not np.isfinite(dt) or dt <= 0:
        raise LoadError(f"{acc_name}: timestamps don't increase")
    rate = float(round(1.0 / dt))
    times = [t for _, t, _ in streams.values()]
    start = max(t.min() for t in times)
    end = min(t.max() for t in times)
    if end - start < 1.0:
        raise LoadError(f"{path}: the sensors overlap for less than a second")
    t = start + np.arange(int(np.floor((end - start) * rate)) + 1) / rate

    q = None
    if quat is not None:
        order = np.argsort(t_o, kind="stable")
        q = _interp(t, t_o[order], _continuous(quat[order]))
        q = _continuous(q / np.linalg.norm(q, axis=1, keepdims=True))

    _, meta = src.read(("Metadata",))
    return Recording(
        t=t, acc=_interp(t, t_acc, acc), gyro=_interp(t, t_gyro, gyro), quat=q,
        rate_hz=rate, orientation=orientation, mock=_is_mock(meta), source=str(path),
    )
