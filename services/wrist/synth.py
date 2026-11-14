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

With camera=True it also writes MOCK pipeline swing JSONs: the same arm seen by a camera
(hip-centred, y up, metres), with the wrist or elbow marked "filled" over an occlusion near
contact and replaced by straight-line interpolation (what the pipeline does with a gap). The
truth carries the real positions, the camera's contact-frame error and the racket-head speed.

Try it (from inside services/):

    python -m wrist.synth /tmp/wrist-mock --camera
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
CLEAN_SPIKE = (1.0, -0.45, 0.15)                               # a clean impact: one sharp knock
# A mishit: the racket and arm keep shaking (~25 Hz, slowly dying away) after the knock.
RING_SPIKE = tuple(float(np.cos(np.pi / 2 * k) * np.exp(-k / 8)) for k in range(10))

# ---- Mock camera swings (camera=True) ----
CAMERA_SPAN_S = (-1.0, 0.6)            # frames from 1 s before contact to 0.6 s after
FOREARM_M, UPPER_ARM_M = 0.26, 0.30
# Sensor world (z up) -> camera (hip-centred, y up): a yaw, then z up -> y up. A proper rotation.
CAMERA_FROM_WORLD = Rotation.from_euler("zx", [37, -90], degrees=True)
# The forearm in phone axes: the long edge (y), but strapped 6 deg off, as real straps are.
STRAP_AXIS = Rotation.from_euler("x", 6, degrees=True).apply([0.0, 1.0, 0.0])
HAND_OFFSETS = {18: (0.02, 0.08, 0.0), 20: (-0.02, 0.09, 0.0), 22: (-0.03, 0.05, 0.01)}  # R pinky, index, thumb
R_SH, R_EL, R_WR = 12, 14, 16
UPPER_ARM_DIR = np.array([-0.3, -0.8, 0.5]) / np.linalg.norm([-0.3, -0.8, 0.5])


def _sig(u: np.ndarray) -> np.ndarray:
    return expit(u)


class _Motion:
    """phi(t), psi(t) (radians) and their rates for a list of swings.

    Each angle is a sum of smooth steps (amp, centre, width). phi per swing: a backswing
    (-back) ending ~0.4 s before contact, the forward swing (+swing) peaking in speed at
    contact, and a slow recovery. psi per swing: the roll ramp just after contact, undone
    in the recovery. With back = 0 this is exactly the model before backswings existed.
    """

    def __init__(self, impacts: np.ndarray, swing_deg: np.ndarray, roll_deg: np.ndarray,
                 back_deg: np.ndarray | None = None, back_lead_s: np.ndarray | None = None):
        c, A, D = impacts, np.radians(swing_deg), np.radians(roll_deg)
        B = np.zeros_like(A) if back_deg is None else np.radians(back_deg)
        lead = np.full_like(c, 0.6) if back_lead_s is None else back_lead_s
        self.phi_steps = [(-B, c - lead, 0.06), (A, c, 0.04), (-(A - B), c + 1.2, 0.25)]
        self.psi_steps = [(D, c + 0.010, 0.035), (-D, c + 1.2, 0.25)]

    @staticmethod
    def _steps(t: np.ndarray, steps: list[tuple[np.ndarray, np.ndarray, float]]) -> tuple[np.ndarray, np.ndarray]:
        t = np.asarray(t, float)[:, None]
        val, rate = np.zeros(t.shape[0]), np.zeros(t.shape[0])
        for amp, centre, s in steps:
            g = _sig((t - centre) / s)
            val += (amp * g).sum(axis=1)
            rate += (amp * g * (1 - g) / s).sum(axis=1)
        return val, rate

    def angles(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        phi, dphi = self._steps(t, self.phi_steps)
        psi, dpsi = self._steps(t, self.psi_steps)
        w1, w2 = 2 * np.pi * 0.3, 2 * np.pi * 0.23  # slow wobble between swings
        phi = phi + np.radians(3) * np.sin(w1 * t)
        dphi = dphi + np.radians(3) * w1 * np.cos(w1 * t)
        psi = psi + np.radians(2) * np.sin(w2 * t + 1)
        dpsi = dpsi + np.radians(2) * w2 * np.cos(w2 * t + 1)
        return phi, dphi, psi, dpsi

    def rotation(self, t: np.ndarray, base: Rotation) -> Rotation:
        """Phone axes -> world axes."""
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


def _still_body() -> np.ndarray:
    """33 MediaPipe joints of a standing player, hip-centred, y up, facing +z (metres)."""
    J = np.zeros((33, 3))
    J[0] = (0.0, 0.65, 0.08)
    for k in range(1, 11):  # eyes, ears, mouth around the nose
        J[k] = J[0] + (0.02 * (k % 5 - 2), 0.02 - 0.01 * (k // 5), -0.01 * (k % 3))
    left = {11: (0.18, 0.5, 0.0), 13: (0.22, 0.22, 0.02), 15: (0.24, -0.02, 0.08), 17: (0.25, -0.08, 0.09),
            19: (0.23, -0.09, 0.10), 21: (0.22, -0.06, 0.11), 23: (0.1, 0.0, 0.0), 25: (0.12, -0.45, 0.05),
            27: (0.13, -0.88, 0.0), 29: (0.13, -0.92, -0.05), 31: (0.14, -0.93, 0.12)}
    for k, (x, y, z) in left.items():
        J[k] = (x, y, z)
        J[k + 1] = (-x, y, z)  # the right side mirrors the left
    return J


def _camera_arm(motion: "_Motion", base: Rotation, t: np.ndarray) -> dict[str, np.ndarray]:
    """True right-arm positions (camera axes) at sensor times t."""
    rot = CAMERA_FROM_WORLD * motion.rotation(t, base)  # phone -> camera
    phi = motion.angles(t)[0]
    shoulder = _still_body()[R_SH]
    elbow = shoulder + UPPER_ARM_M * Rotation.from_rotvec(np.outer(0.4 * phi, [0, 1, 0])).apply(UPPER_ARM_DIR)
    wrist = elbow + FOREARM_M * rot.apply(STRAP_AXIS)
    out = {"rot": rot, "elbow": elbow, "wrist": wrist}
    for k, off in HAND_OFFSETS.items():
        out[k] = wrist + rot.apply(off)
    return out


def _racket_truth(motion: "_Motion", base: Rotation, c: float, lever_m: float, window_ms: Sequence[float]) -> float:
    """True racket-head speed (m/s): wrist velocity + forearm angular velocity x lever, averaged
    over the same pre-contact window the estimate uses (locked wrist, racket along the forearm)."""
    ts = c + np.linspace(*window_ms, 5) / 1000
    h = 1e-4
    v_wrist = (_camera_arm(motion, base, ts + h)["wrist"] - _camera_arm(motion, base, ts - h)["wrist"]) / (2 * h)
    rot = CAMERA_FROM_WORLD * motion.rotation(ts, base)
    w = rot.apply(motion.gyro(ts))
    head = v_wrist + np.cross(w, lever_m * rot.apply(STRAP_AXIS))
    return float(np.linalg.norm(head, axis=1).mean())


def _camera_swing(sid: str, c: float, contact_video_s: float, motion: "_Motion", base: Rotation,
                  rng: np.random.Generator, fps: float, occlude: str, lever_m: float,
                  window_ms: Sequence[float]) -> tuple[dict[str, Any], dict[str, Any]]:
    """One MOCK pipeline swing JSON (with filled flags over an occlusion) and its truth."""
    n = int(round((CAMERA_SPAN_S[1] - CAMERA_SPAN_S[0]) * fps))
    tau = c + CAMERA_SPAN_S[0] + rng.uniform(0, 1 / fps) + np.arange(n) / fps  # sensor time of each frame
    true_cf = int(np.argmin(np.abs(tau - c)))
    cf = true_cf + int(rng.integers(-2, 3))  # the video's contact frame is a frame or two off
    arm = _camera_arm(motion, base, tau)
    J = np.repeat(_still_body()[None], n, axis=0)
    J[:, R_EL], J[:, R_WR] = arm["elbow"], arm["wrist"]
    for k in HAND_OFFSETS:
        J[:, k] = arm[k]
    filled = np.zeros((n, 33), bool)
    lo, hi = (true_cf - 10, true_cf + 2) if occlude == "wrist" else (true_cf - 6, true_cf + 4)
    joints = [R_WR, *HAND_OFFSETS] if occlude == "wrist" else [R_EL]
    truth_pos = {j: J[lo:hi + 1, j].copy() for j in joints}
    for j in joints:  # what the pipeline does with a gap: straight-line interpolation
        a, b = J[lo - 1, j], J[hi + 1, j]
        f = (np.arange(lo, hi + 1) - (lo - 1)) / (hi + 1 - (lo - 1))
        J[lo:hi + 1, j] = a + f[:, None] * (b - a)
        filled[lo:hi + 1, j] = True
    swing = {
        "id": sid, "fps": fps, "fpsReal": fps, "contactFrame": cf, "synthetic": True, "source": "synthetic",
        "metadata": {"hand": "R", "mock": True, "contactMethod": "synthetic (a frame or two off on purpose)",
                     "sourceContactSeconds": round(contact_video_s, 3),
                     "coordinateSystem": "hip-centred-y-up-metres"},
        "frames": [{"t": round(float(k / fps), 6), "joints": np.round(J[k], 5).tolist(),
                    "filled": filled[k].tolist()} for k in range(n)],
    }
    truth = {"contact_frame": cf, "true_contact_frame": true_cf, "frame_sensor_s": tau.tolist(),
             "occluded": occlude, "filled_frames": list(range(lo, hi + 1)),
             "true_positions": {str(j): v.tolist() for j, v in truth_pos.items()},
             "racket_speed_ms": _racket_truth(motion, base, c, lever_m, window_ms)}
    return swing, truth


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
    backswing: bool = True,
    mishit: Sequence[int] = (),
    camera: bool = False,
    camera_fps: float = 120.0,
) -> dict[str, Any]:
    """Write a mock export plus contacts.csv and labels.csv into out_dir. Returns the truth.

    quat_convention: "body_to_world" (quaternion maps phone axes to world) or
    "world_to_body" (its inverse), so tests can check that metrics detect either.
    backswing: each swing starts with a backswing (for tempo). mishit: indexes of swings
    whose impact rings like an off-centre hit. camera: also write MOCK pipeline swing JSONs
    (swings/<id>.json, filled flags over an occlusion near contact) for the fusion tests.
    """
    # Lazy import: fuse imports physics, which the sensor-only mock doesn't need.
    from wrist.fuse import LEVER_M, SPEED_WINDOW_MS

    rng = np.random.default_rng(seed)
    extra = np.random.default_rng([seed, 7])  # new features draw here, so old mocks stay identical
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
    back = extra.normal(70.0, 5.0, n) if backswing else None
    back_lead = extra.uniform(0.55, 0.65, n)
    motion = _Motion(impacts, swings, rolls, back, back_lead)
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

    def spike(at: float, amp: float, direction: Sequence[float], profile: Sequence[float] = CLEAN_SPIKE) -> None:
        i = int(np.argmin(np.abs(t_acc - at)))
        d = np.asarray(direction, float) / np.linalg.norm(direction)
        for k, f in enumerate(profile):
            if i + k < t_acc.size:
                acc[i + k] += amp * f * d

    for tap in taps:
        spike(tap, 45.0, (0.1, 0.2, 1.0))
    for k, c in enumerate(impacts):
        amp = rng.uniform(140, 180)
        if k in mishit:
            spike(c, amp, (0.8, 0.3, 0.5), RING_SPIKE)  # a normal height: only the shaking gives it away
        else:
            spike(c, amp, (0.8, 0.3, 0.5))
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
    for k, (sid, c, lab) in enumerate(zip(ids, impacts, labels)):
        fine = c + np.linspace(*WINDOW_S, 2501)
        _, _, psi, dpsi = motion.angles(fine)
        speed = np.linalg.norm(motion.gyro(fine), axis=1)
        truth_swings[sid] = {
            "label": lab, "impact_s": float(c),
            "roll_change_deg": float(np.degrees(psi[-1] - psi[0])),
            "peak_roll_rate_dps": float(np.degrees(np.max(np.abs(dpsi)))),
            "peak_angular_speed_dps": float(np.degrees(speed.max())),
            "impact": "mishit" if k in mishit else "clean",
        }

    swings_dir = None
    if camera:
        swings_dir = out / "swings"
        swings_dir.mkdir(exist_ok=True)
        for k, (sid, c, cv) in enumerate(zip(ids, impacts, contacts)):
            swing, cam_truth = _camera_swing(sid, float(c), float(cv), motion, base, extra, camera_fps,
                                             "elbow" if k % 3 == 1 else "wrist", LEVER_M, SPEED_WINDOW_MS)
            (swings_dir / f"{sid}.json").write_text(json.dumps(swing, separators=(",", ":")))
            truth_swings[sid]["camera"] = cam_truth
    return {
        "export": str(export_path), "contacts": str(out / "contacts.csv"), "labels": str(out / "labels.csv"),
        "taps_s": taps.tolist(), "video_tap_s": round(video_tap, 3), "video_offset_s": video_offset_s,
        "footstep_s": footstep_t, "quat_convention": quat_convention, "swings": truth_swings,
        "swings_dir": None if swings_dir is None else str(swings_dir),
        "motion": motion, "base": base,  # for tests; not JSON (the CLI drops them)
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write a MOCK Sensor Logger export to try the wrist pipeline.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--zip", action="store_true", help="also zip the export, like Sensor Logger does")
    parser.add_argument("--camera", action="store_true", help="also write MOCK pipeline swing JSONs (swings/)")
    parser.add_argument("--mishit", type=int, nargs="*", default=[], help="swing indexes (0-based) to mishit")
    args = parser.parse_args(argv)
    truth = make_session(args.out_dir, seed=args.seed, zip_export=args.zip, camera=args.camera, mishit=args.mishit)
    saved = {k: v for k, v in truth.items() if k not in ("motion", "base")}
    (args.out_dir / "truth.json").write_text(json.dumps(saved, indent=2))
    print(f"Mock export: {truth['export']}")
    print(f"Contacts:    {truth['contacts']}  (video tap at {truth['video_tap_s']} s)")
    print(f"Labels:      {truth['labels']}")
    if truth["swings_dir"]:
        print(f"Swings:      {truth['swings_dir']}  (MOCK camera swings)")
    swings = f" --swings {truth['swings_dir']}" if truth["swings_dir"] else ""
    print("Next:\n  python -m wrist.run " + truth["export"] + f" --contacts {truth['contacts']}{swings} "
          f"--video-tap {truth['video_tap_s']} --out {args.out_dir / 'wrist_metrics.json'} "
          f"--series-out {args.out_dir / 'wrist_series.json'}")


if __name__ == "__main__":
    main()
