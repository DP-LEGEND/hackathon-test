"""A made-up but anatomically plausible right-handed swing for tests. MOCK DATA.

Bone lengths are constant by construction. The shoulders coil to a backswing top at
0.20 s and unwind; the elbow extends and the wrist uncocks shortly before peak wrist
speed (contact). No real clip needed, so tests run anywhere.
"""

from __future__ import annotations

import numpy as np

from physics.skeleton import ARM, L_HIP, R_HIP, mid, speed


def _rot(v: np.ndarray, axis: np.ndarray, ang: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    c, s = np.cos(ang), np.sin(ang)
    return v * c + np.cross(axis, v) * s + axis * (axis @ v) * (1 - c)


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def make_swing(fps: float = 240.0, duration: float = 0.8, y_up: bool = False,
               racket: bool = True, lean: float = 0.12) -> dict:
    """Swing dict in the lib/ghost/types.ts shape. y points down unless y_up=True (MediaPipe-like)."""
    n = int(round(duration * fps))
    t = np.arange(n) / fps
    S = lambda x: 1.0 / (1.0 + np.exp(-x))  # noqa: E731
    yaw = np.radians(-40 - 35 * np.exp(-(((t - 0.20) / 0.08) ** 2)) + 90 * S((t - 0.40) / 0.035))
    arm_swing = np.radians(-60 + 100 * S((t - 0.40) / 0.04))
    elbow_bend = np.radians(80 - 60 * S((t - 0.38) / 0.03))  # inside elbow angle 100 -> 160 deg
    wrist_bend = np.radians(55 - 45 * S((t - 0.36) / 0.012))  # inside wrist angle 125 -> 170 deg
    up = np.array([0.0, 1.0, 0.0])

    J = np.zeros((n, 33, 3))
    tip = np.zeros((n, 3))
    throat = np.zeros((n, 3))
    for i in range(n):
        # Upper body in a torso frame (x right, y up, z forward), turned by `yaw` about the hips.
        U = {}
        U[0] = np.array([0.0, 0.72, lean + 0.08])
        for k in range(1, 11):
            U[k] = U[0] + np.array([0.03 * np.cos(k), 0.02 + 0.01 * (k % 3), -0.02 * np.sin(k)])
        U[11] = np.array([-0.18, 0.5, lean])
        U[12] = np.array([0.18, 0.5, lean])
        # Hitting (right) arm.
        a = _rot(_unit([0.7, -0.6, 0.0]), up, arm_swing[i])
        hinge = _unit(np.cross(a, up))
        f = _rot(a, hinge, elbow_bend[i])
        h = _rot(f, hinge, wrist_bend[i])
        U[14] = U[12] + 0.30 * a
        U[16] = U[14] + 0.26 * f
        U[20] = U[16] + 0.09 * h
        U[18] = U[16] + 0.08 * _unit(h + 0.35 * hinge)
        U[22] = U[16] + 0.06 * _unit(h - 0.5 * hinge)
        U["throat"] = U[16] + 0.22 * h
        U["tip"] = U[16] + 0.68 * h
        # Other arm, held still relative to the torso.
        U[13] = U[11] + 0.30 * _unit([-0.3, -0.9, 0.2])
        U[15] = U[13] + 0.26 * _unit([0.1, -0.7, 0.6])
        U[19] = U[15] + 0.09 * _unit([0.1, -0.5, 0.8])
        U[17] = U[15] + 0.08 * _unit([0.3, -0.5, 0.7])
        U[21] = U[15] + 0.06 * _unit([-0.2, -0.4, 0.8])
        R = lambda v: _rot(v, up, yaw[i])  # noqa: E731
        for k, v in U.items():
            if k == "tip":
                tip[i] = R(v)
            elif k == "throat":
                throat[i] = R(v)
            else:
                J[i, k] = R(v)
        # Hips and legs don't move.
        J[i, 23], J[i, 24] = [-0.10, 0, 0], [0.10, 0, 0]
        J[i, 25], J[i, 26] = [-0.14, -0.45, 0.06], [0.14, -0.45, 0.06]
        J[i, 27], J[i, 28] = [-0.20, -0.88, 0.0], [0.20, -0.88, 0.0]
        J[i, 29], J[i, 30] = J[i, 27] + [0, -0.05, -0.06], J[i, 28] + [0, -0.05, -0.06]
        J[i, 31], J[i, 32] = J[i, 27] + [0, -0.06, 0.15], J[i, 28] + [0, -0.06, 0.15]

    if not y_up:
        J[..., 1] *= -1
        tip[:, 1] *= -1
        throat[:, 1] *= -1

    wr = J[:, ARM["R"]["wr"]] - mid(J, L_HIP, R_HIP)
    contact = int(np.argmax(speed(wr, fps)))
    frames = []
    for i in range(n):
        fr = {"t": float(t[i]), "joints": J[i].tolist()}
        if racket:
            fr["racketTip"] = tip[i].tolist()
            fr["racketThroat"] = throat[i].tolist()
        frames.append(fr)
    return {"id": "mock-forehand", "fps": fps, "contactFrame": contact, "frames": frames}
