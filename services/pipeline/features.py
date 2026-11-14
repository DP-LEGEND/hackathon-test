"""Per-swing measurements from world landmarks. Owner: Dev (feeds physics/metrics).

All angles in degrees. World landmarks are hip-centred and oriented to the camera,
so with a fixed camera, rotation angles are comparable between swings.
Right-handed player assumed (pass hand="L" for a lefty).
"""

from __future__ import annotations

import numpy as np

from pipeline.pose import smooth

IDX = {"L": dict(sh=11, el=13, wr=15, idx=19, hip=23, kn=25, an=27),
       "R": dict(sh=12, el=14, wr=16, idx=20, hip=24, kn=26, an=28)}


def _angle(a, b, c):
    """Angle at b (degrees) for arrays of shape (n, 3)."""
    u, v = a - b, c - b
    cos = np.sum(u * v, -1) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1) + 1e-9)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def _yaw(a, b):
    """Heading of the line a->b in the floor plane (x, z), degrees."""
    d = b - a
    yaw = np.arctan2(d[:, 2], d[:, 0])
    finite = np.flatnonzero(np.isfinite(yaw))
    for span in np.split(finite, np.where(np.diff(finite) > 1)[0] + 1):
        yaw[span] = np.unwrap(yaw[span])
    return np.degrees(yaw)


def swing_features(world: np.ndarray, impact: int, fps_real: float, hand: str = "R") -> dict:
    """world: (n, 33, 3) for one swing window; impact: index of contact inside it."""
    W = smooth(world, 5)
    h, o = IDX[hand], IDX["L" if hand == "R" else "R"]
    sh, el, wr, ix = (W[:, h[k]] for k in ("sh", "el", "wr", "idx"))
    elbow = _angle(sh, el, wr)
    wrist_ang = _angle(el, wr, ix)
    shoulders = _yaw(W[:, o["sh"]], W[:, h["sh"]])
    hips = _yaw(W[:, o["hip"]], W[:, h["hip"]])
    feet = _yaw(W[:, o["an"]], W[:, h["an"]])
    i = int(np.clip(impact, 0, len(W) - 1))
    pre = slice(0, i + 1)
    v_wr = np.linalg.norm(np.diff(wr, axis=0), axis=1) * fps_real
    v_el = np.linalg.norm(np.diff(el, axis=0), axis=1) * fps_real
    def _argmax(v):
        v = v[: i + 3]
        return int(np.nanargmax(v)) if i > 2 and np.isfinite(v).any() else 0

    pk_wr, pk_el = _argmax(v_wr), _argmax(v_el)
    wa = wrist_ang[pre]
    return {
        "elbow_at_impact": float(elbow[i]),
        "elbow_min_before": float(np.nanmin(elbow[pre])),
        "wrist_angle_at_impact": float(wrist_ang[i]),
        "wrist_angle_change_pre": float(np.nanmax(wa) - np.nanmin(wa)),
        "shoulder_turn_range": float(np.nanmax(shoulders) - np.nanmin(shoulders)),
        "shoulder_yaw_at_impact": float(shoulders[i]),
        "shoulder_yaw_end": float(np.nanmean(shoulders[-5:])),
        "hip_turn_range": float(np.nanmax(hips) - np.nanmin(hips)),
        "x_factor_max": float(np.nanmax(np.abs(shoulders - hips))),
        "stance_yaw": float(np.nanmedian(feet[pre])),
        "stance_width_m": float(np.nanmedian(np.linalg.norm(W[pre, h["an"]] - W[pre, o["an"]], axis=1))),
        "wrist_speed_peak": float(v_wr[pk_wr]) if len(v_wr) else float("nan"),
        "elbow_leads_wrist_ms": float((pk_wr - pk_el) / fps_real * 1000),
    }
