"""Synthetic Sensor Logger export: MOCK data for tests and for trying the pipeline. Owner: Henoch.

Not real squash data. It exists so load/sync/metrics/tune can be built and tested before
aryan's real recording. Metadata.csv marks it mock, so every output says "mock": true.

The model: the phone sits on the forearm with its long axis (y) along the forearm.
Orientation R(t) = B * Rz(phi(t)) * Ry(psi(t)): phi is the swing (about the phone's z),
psi is forearm ROLL (about y). Each swing's phi peaks in speed at contact; psi ramps by
the swing's roll amount around contact (small for a normal swing, large when the wrist
rolls). The gyro is the exact body-frame angular velocity of that rotation, so
roll rate about y is psi'(t). The accelerometer has noise, the swing's centripetal pull
along -y, two finger taps at the start, a sharp spike at each racket impact, and one
"footstep" spike with the arm still (sync must reject it).

Video side: contact times = impact time - video offset + a little marking jitter, as
if someone noted contacts in QuickTime. Truth (exact roll change etc.) is returned.

Try it (from inside services/):

    python -m wrist.synth /tmp/wrist-mock
"""

from __future__ import annotations

import argparse
import csv
import json
import zipfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.spatial.transform import Rotation
from scipy.special import expit

WINDOW_S = (-0.150, 0.100)  # the metric window, for the truth values
ARM_RADIUS_M = 0.25
EPOCH_NS = 1_731_600_000_000_000_000
DEFAULT_LABELS = ("none",) * 5 + ("rolled_wrist",) * 5


def _sig(u: np.ndarray) -> np.ndarray:
    return expit(u)


class _Motion:
    """phi(t), psi(t) (radians) and their rates for a list of swings."""

    def __init__(self, impacts: np.ndarray, swing_deg: np.ndarray, roll_deg: np.ndarray):
        self.c, self.A, self.D = impacts, np.radians(swing_deg), np.radians(roll_deg)
        self.s_phi, self.s_psi, self.back, self.s_back = 0.04, 0.035, 1.2, 0.25

    def _ramp(self, t: np.ndarray, amp: np.ndarray, s: float, lead: float) -> tuple[np.ndarray, np.ndarray]:
        t = np.asarray(t, float)[:, None]
        u, ub = (t - self.c - lead) / s, (t - self.c - self.back) / self.s_back
        g, gb = _sig(u), _sig(ub)
        val = (amp * (g - gb)).sum(axis=1)
        rate = (amp * (g * (1 - g) / s - gb * (1 - gb) / self.s_back)).sum(axis=1)
        return val, rate

    def angles(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        phi, dphi = self._ramp(t, self.A, self.s_phi, 0.0)
        psi, dpsi = self._ramp(t, self.D, self.s_psi, 0.010)
        w1, w2 = 2 * np.pi * 0.3, 2 * np.pi * 0.23  # slow wobble between swings
        phi = phi + np.radians(3) * np.sin(w1 * t)
        dphi = dphi + np.radians(3) * w1 * np.cos(w1 * t)
        psi = psi + np.radians(2) * np.sin(w2 * t + 1)
        dpsi = dpsi + np.radians(2) * w2 * np.cos(w2 * t + 1)
        return phi, dphi, psi, dpsi

    def rotation(self, t: np.ndarray, base: Rotation) -> Rotation:
        phi, _, psi, _ = self.angles(t)
        z, y = np.zeros_like(phi), np.zeros_like(psi)
        return base * Rotation.from_rotvec(np.column_stack([z, z, phi])) * \
            Rotation.from_rotvec(np.column_stack([y, psi, y]))

    def gyro(self, t: np.ndarray) -> np.ndarray:
        """Body-frame angular velocity: Ry(psi)^T (0, 0, phi') + (0, psi', 0)."""
        _, dphi, psi, dpsi = self.angles(t)
        swing = Rotation.from_rotvec(np.column_stack([np.zeros_like(psi), psi, np.zeros_like(psi)])).inv() \
            .apply(np.column_stack([np.zeros_like(dphi), np.zeros_like(dphi), dphi]))
        return swing + np.column_stack([np.zeros_like(dpsi), dpsi, np.zeros_like(dpsi)])


def _write_xyz(path: Path, t: np.ndarray, v: np.ndarray) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "seconds_elapsed", "z", "y", "x"])  # Sensor Logger's order
        for ti, (x, y, z) in zip(t, v):
            w.writerow([EPOCH_NS + int(round(ti * 1e9)), f"{ti:.6f}", f"{z:.6f}", f"{y:.6f}", f"{x:.6f}"])


def _write_orientation(path: Path, t: np.ndarray, rot: Rotation) -> None:
    q = rot.as_quat()  # x, y, z, w
    ypr = rot.as_euler("ZXY")  # yaw (z), pitch (x), roll (y)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time", "seconds_elapsed", "qz", "qy", "qx", "qw", "roll", "pitch", "yaw"])
        for ti, (qx, qy, qz, qw), (yaw, pitch, roll) in zip(t, q, ypr):
            w.writerow([EPOCH_NS + int(round(ti * 1e9)), f"{ti:.6f}",
                        f"{qz:.8f}", f"{qy:.8f}", f"{qx:.8f}", f"{qw:.8f}",
                        f"{roll:.6f}", f"{pitch:.6f}", f"{yaw:.6f}"])


def make_session(
    out_dir: str | Path,
    labels: Sequence[str] = DEFAULT_LABELS,
    seed: int = 0,
    rate: float = 100.0,
    quat_convention: str = "body_to_world",
    video_offset_s: float = -1.3,
    video_jitter_s: float = 0.008,
    footstep: bool = True,
    zip_export: bool = False,
    normal_roll: tuple[float, float] = (22.0, 5.0),
    rolled_roll: tuple[float, float] = (70.0, 6.0),
) -> dict[str, Any]:
    """Write a mock export plus contacts.csv and labels.csv into out_dir. Returns the truth.

    quat_convention: "body_to_world" (quaternion maps phone axes to world) or
    "world_to_body" (its inverse), so tests can check that metrics detect either.
    """
    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    export = out / "export"
    export.mkdir(parents=True, exist_ok=True)

    n = len(labels)
    taps = np.array([2.0, 2.45])
    impacts = 6.0 + 7.0 * np.arange(n) + rng.uniform(-0.5, 0.5, n)
    rolls = np.array([rng.normal(*(rolled_roll if lab == "rolled_wrist" else normal_roll)) for lab in labels])
    swings = rng.normal(200.0, 10.0, n)
    footstep_t = float((impacts[1] + impacts[2]) / 2) if footstep and n >= 3 else None
    end = float(impacts[-1] + 4.0) if n else 10.0
    motion = _Motion(impacts, swings, rolls)
    base = Rotation.from_euler("xyz", [20, -35, 60], degrees=True)

    def grid(offset: float) -> np.ndarray:
        t = np.arange(-0.05, end, 1.0 / rate) + offset
        return t + rng.normal(0, 0.0007, t.size)

    # Accelerometer: noise + wobble + centripetal pull along -y + spikes.
    t_acc = grid(0.0)
    acc = rng.normal(0, 0.25, (t_acc.size, 3))
    acc[:, 0] += 0.8 * np.sin(2 * np.pi * 1.7 * t_acc)
    _, dphi, _, _ = motion.angles(t_acc)
    acc[:, 1] -= ARM_RADIUS_M * dphi**2

    def spike(at: float, amp: float, direction: Sequence[float]) -> None:
        i = int(np.argmin(np.abs(t_acc - at)))
        d = np.asarray(direction, float) / np.linalg.norm(direction)
        for k, f in enumerate((1.0, -0.45, 0.15)):
            if i + k < t_acc.size:
                acc[i + k] += amp * f * d

    for tap in taps:
        spike(tap, 45.0, (0.1, 0.2, 1.0))
    for c in impacts:
        spike(c, rng.uniform(140, 180), (0.8, 0.3, 0.5))
    if footstep_t is not None:
        spike(footstep_t, 70.0, (0.0, 1.0, 0.3))

    t_gyro = grid(0.003)
    gyro = motion.gyro(t_gyro) + rng.normal(0, 0.02, (t_gyro.size, 3))
    t_or = grid(0.006)
    rot = motion.rotation(t_or, base)
    if quat_convention == "world_to_body":
        rot = rot.inv()
    elif quat_convention != "body_to_world":
        raise ValueError(f"quat_convention must be body_to_world or world_to_body, got {quat_convention!r}")

    _write_xyz(export / "Accelerometer.csv", t_acc, acc)
    _write_xyz(export / "Gyroscope.csv", t_gyro, gyro)
    _write_orientation(export / "Orientation.csv", t_or, rot)
    (export / "Metadata.csv").write_text("version,device name,mock\n1,SYNTHETIC wrist sensor (mock),true\n")

    export_path: Path = export
    if zip_export:
        export_path = out / "export.zip"
        with zipfile.ZipFile(export_path, "w") as z:
            for p in sorted(export.glob("*.csv")):
                z.write(p, f"wrist-mock/{p.name}")

    ids = [f"synth-{k + 1:02d}" for k in range(n)]
    contacts = impacts - video_offset_s + rng.normal(0, video_jitter_s, n)
    video_tap = float(taps[0] - video_offset_s + rng.normal(0, video_jitter_s))
    with (out / "contacts.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["swing", "contact_s"])
        w.writerows([sid, f"{c:.3f}"] for sid, c in zip(ids, contacts))
    with (out / "labels.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["swing", "intended_fault"])
        w.writerows(zip(ids, labels))

    truth_swings = {}
    for sid, c, lab in zip(ids, impacts, labels):
        fine = c + np.linspace(*WINDOW_S, 2501)
        _, _, psi, dpsi = motion.angles(fine)
        speed = np.linalg.norm(motion.gyro(fine), axis=1)
        truth_swings[sid] = {
            "label": lab, "impact_s": float(c),
            "roll_change_deg": float(np.degrees(psi[-1] - psi[0])),
            "peak_roll_rate_dps": float(np.degrees(np.max(np.abs(dpsi)))),
            "peak_angular_speed_dps": float(np.degrees(speed.max())),
        }
    return {
        "export": str(export_path), "contacts": str(out / "contacts.csv"), "labels": str(out / "labels.csv"),
        "taps_s": taps.tolist(), "video_tap_s": round(video_tap, 3), "video_offset_s": video_offset_s,
        "footstep_s": footstep_t, "quat_convention": quat_convention, "swings": truth_swings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a MOCK Sensor Logger export to try the wrist pipeline.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--zip", action="store_true", help="also zip the export, like Sensor Logger does")
    args = parser.parse_args()
    truth = make_session(args.out_dir, seed=args.seed, zip_export=args.zip)
    (args.out_dir / "truth.json").write_text(json.dumps(truth, indent=2))
    print(f"Mock export: {truth['export']}")
    print(f"Contacts:    {truth['contacts']}  (video tap at {truth['video_tap_s']} s)")
    print(f"Labels:      {truth['labels']}")
    print("Next:\n  python -m wrist.run " + truth["export"] + f" --contacts {truth['contacts']} "
          f"--video-tap {truth['video_tap_s']} --out {args.out_dir / 'wrist_metrics.json'} "
          f"--series-out {args.out_dir / 'wrist_series.json'}")


if __name__ == "__main__":
    main()
