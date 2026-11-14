"""Calm the arm on frames the camera couldn't see. Owner: Dev (pipeline).

smooth_guessed_arms(P, filled, protect) only changes GUESSED frames (filled):
- Each arm segment (upper arm, forearm, hand points) is a unit direction from its parent
  joint. Over a guessed run with measured frames at both ends, the direction is slerped
  from the measured direction before the run to the one after it (eased), so the arm moves
  along a smooth arc and a bone can't collapse through the middle. If the two ends are more
  than 120 degrees apart, a slerp would guess the wrong way round, so those frames keep the
  pipeline's fill, only lightly filtered.
- Guessed runs at the start or end of the clip (one measured end) keep the fill, lightly
  filtered (Savitzky-Golay on the direction, guessed frames only).
- Guessed frames are rebuilt at the segment's median measured length.
Measured frames, the torso, the legs and frames inside `protect` (around contact) are
returned exactly as given. Walking parent before child keeps a guessed wrist attached to a
re-drawn elbow.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

SEGMENTS = (
    (11, 13), (13, 15), (15, 17), (15, 19), (15, 21),   # left arm + hand
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22),   # right arm + hand
)
LIMB_JOINTS = sorted({c for _, c in SEGMENTS})
ARM_JOINTS = LIMB_JOINTS
MAX_SLERP_DEG = 120.0
BLEND = 4


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


def slerp(u: np.ndarray, v: np.ndarray, s: np.ndarray) -> np.ndarray:
    """Spherical interpolation between unit vectors u and v at fractions s (shape (k,))."""
    u, v = _unit(u), _unit(v)
    dot = float(np.clip(u @ v, -1.0, 1.0))
    theta = np.arccos(dot)
    s = np.asarray(s, float)[:, None]
    if theta < 1e-6:
        return np.repeat(u[None], len(s), axis=0)
    return (np.sin((1 - s) * theta) * u + np.sin(s * theta) * v) / np.sin(theta)


def smooth_guessed_arms(P: np.ndarray, filled: np.ndarray, protect: tuple[int, int] | None = None,
                        window: int = 21, poly: int = 3) -> np.ndarray:
    """P: (frames, 33, 3) joints; filled: (frames, 33) bool (guessed). Returns a smoothed copy."""
    P = np.asarray(P, float)
    filled = np.asarray(filled, bool)
    n = len(P)
    keep = np.zeros(n, bool)
    if protect is not None:
        keep[max(0, protect[0]):min(n, protect[1] + 1)] = True
    out = P.copy()
    for a, b in SEGMENTS:  # parents first
        seg = P[:, b] - P[:, a]
        d = _unit(seg)
        guessed = filled[:, b] & ~keep
        measured = ~filled[:, b] & np.isfinite(seg).all(axis=1)
        L = np.linalg.norm(seg, axis=1)
        length = float(np.median(L[measured])) if measured.any() else float(np.nanmedian(L))
        new = d.copy()
        filtered = _unit(savgol_filter(d, window, poly, axis=0, mode="interp")) if n >= window else d
        anchor = measured  # only seen directions anchor a slerp (a guessed frame kept for contact does not)
        for i, j in _runs(guessed):
            if i > 0 and j < n and anchor[i - 1] and anchor[j]:
                u, v = d[i - 1], d[j]
                if np.degrees(np.arccos(np.clip(u @ v, -1, 1))) <= MAX_SLERP_DEG:
                    s = (np.arange(i, j) - (i - 1)) / (j - (i - 1))
                    s = s * s * (3 - 2 * s)  # ease in/out: no kink at the measured ends
                    new[i:j] = slerp(u, v, s)
                    continue
            # no usable slerp: the filtered fill, faded in over BLEND frames from each edge
            # that touches as-given data, so the run doesn't jump at its ends
            ramp = np.ones(j - i)
            for k in range(min(BLEND, j - i)):
                f = (k + 1) / (BLEND + 1)
                if i > 0:
                    ramp[k] = min(ramp[k], f)
                if j < n:
                    ramp[j - i - 1 - k] = min(ramp[j - i - 1 - k], f)
            new[i:j] = _unit(ramp[:, None] * filtered[i:j] + (1 - ramp[:, None]) * d[i:j])
        rebuilt = out[:, a] + new * length
        out[guessed, b] = rebuilt[guessed]
        # a measured child keeps its measured position; a re-drawn parent doesn't move it
    return out
