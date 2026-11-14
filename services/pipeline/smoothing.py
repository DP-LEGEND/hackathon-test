"""Calm the limbs where the camera couldn't see them. Owner: Dev (pipeline).

smooth_guessed_arms(P, filled, protect):
1. Limb directions, not positions: every limb segment (upper arm, forearm, hand points,
   hand points) is a unit direction from its parent joint. On a guessed run of a
   joint, its direction is re-drawn with a shape-preserving spline (PCHIP) between the
   last and next measured frames, so the arm swings along a natural arc instead of
   following the noisy fill.
2. A light Savitzky-Golay filter on those directions removes triangulation jitter.
3. Bone-length lock: every arm segment is rebuilt at its median length over measured frames,
   walking out from the torso, so limbs no longer stretch with jittery depth.
The torso (shoulders, hips, head) and the legs are never moved, and frames inside `protect` (around
contact) are returned exactly as given, so contact measurements, racket speed, the ball
prediction and shoulder/hip metrics don't change. `blend` frames fade in either side.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.signal import savgol_filter

# parent -> child segments, walked outwards from the (fixed) torso
SEGMENTS = (
    (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),   # left arm + hand
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),   # right arm + hand
)
# Legs are left alone: they are seen well from behind, and the lowest foot sets the floor
# (and so every court height), which must not move.
LIMB_JOINTS = sorted({c for _, c in SEGMENTS})
ARM_JOINTS = [j for j in LIMB_JOINTS if j <= 22]


def _runs(mask: np.ndarray):
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            yield i, j
            i = j
        else:
            i += 1


def _unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def smooth_guessed_arms(P: np.ndarray, filled: np.ndarray, protect: tuple[int, int] | None = None,
                        window: int = 21, poly: int = 3, blend: int = 4) -> np.ndarray:
    """P: (frames, 33, 3) joints; filled: (frames, 33) bool (guessed). Returns a smoothed copy."""
    P = np.asarray(P, float)
    filled = np.asarray(filled, bool)
    n = len(P)
    t = np.arange(n)
    dirs, lengths = {}, {}
    for a, b in SEGMENTS:
        seg = P[:, b] - P[:, a]
        measured = ~(filled[:, a] | filled[:, b]) & np.isfinite(seg).all(axis=1)
        L = np.linalg.norm(seg, axis=1)
        lengths[(a, b)] = float(np.median(L[measured])) if measured.any() else float(np.nanmedian(L))
        d = _unit(seg)
        if measured.sum() >= 2:
            spline = PchipInterpolator(t[measured], d[measured], axis=0, extrapolate=False)
            for i, j in _runs(~measured):
                if i > 0 and j < n:  # interior gap: draw the arc between measured ends
                    d[i:j] = spline(t[i:j])
        if n >= window:
            d = savgol_filter(d, window, poly, axis=0, mode="interp")
        dirs[(a, b)] = _unit(d)
    out = P.copy()
    for a, b in SEGMENTS:  # parents before children, so lengths chain outwards
        out[:, b] = out[:, a] + dirs[(a, b)] * lengths[(a, b)]
    w = np.ones(n)
    if protect is not None:
        lo, hi = max(0, protect[0]), min(n - 1, protect[1])
        w[lo:hi + 1] = 0.0
        for k in range(1, blend + 1):
            if lo - k >= 0:
                w[lo - k] = min(w[lo - k], k / (blend + 1))
            if hi + k < n:
                w[hi + k] = min(w[hi + k], k / (blend + 1))
    res = P.copy()
    res[:, LIMB_JOINTS] = w[:, None, None] * out[:, LIMB_JOINTS] + (1 - w[:, None, None]) * P[:, LIMB_JOINTS]
    return res
