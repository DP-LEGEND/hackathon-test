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
                        window: int = 21, poly: int = 3, smooth_measured: bool = False,
                        measured_window: int = 15,
                        blend: int = BLEND) -> np.ndarray:
    """P: (frames, 33, 3) joints; filled: (frames, 33) bool (guessed). Returns a smoothed copy.

    smooth_measured=True (the demo samples' "middle ground"): after the guessed runs are
    re-drawn, every arm joint outside `protect` is also lightly filtered (Savitzky-Golay,
    `measured_window` frames, on hip-relative positions) and rebuilt at median bone lengths, fading back
    to the as-given data over `blend` frames at the edges of `protect`. Frames inside
    `protect` are still returned exactly as given.
    """
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
    if not smooth_measured:
        return out
    w = (~keep).astype(float)
    if protect is not None:
        lo, hi = max(0, protect[0]), min(n - 1, protect[1])
        for k in range(1, blend + 1):
            if lo - k >= 0:
                w[lo - k] = min(w[lo - k], k / (blend + 1))
            if hi + k < n:
                w[hi + k] = min(w[hi + k], k / (blend + 1))
    # light Savitzky-Golay on hip-relative arm positions, then lock each segment's length
    hip = (out[:, 23] + out[:, 24]) / 2
    calm = out.copy()
    if n >= measured_window:
        for j in LIMB_JOINTS:
            calm[:, j] = savgol_filter(out[:, j] - hip, measured_window, poly, axis=0, mode="interp") + hip
    for a, b in SEGMENTS:  # parents first
        L = np.linalg.norm(P[:, b] - P[:, a], axis=1)
        measured = ~filled[:, b] & np.isfinite(L)
        length = float(np.median(L[measured])) if measured.any() else float(np.nanmedian(L))
        calm[:, b] = calm[:, a] + _unit(calm[:, b] - calm[:, a]) * length
    res = out.copy()
    res[:, LIMB_JOINTS] = w[:, None, None] * calm[:, LIMB_JOINTS] + (1 - w[:, None, None]) * out[:, LIMB_JOINTS]
    return res


def frontal_plane(Pk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(normal pointing where the chest faces, centre) of the shoulder-hip plane, y up."""
    n = np.cross([0.0, 1.0, 0.0], Pk[12] - Pk[11])
    n = _unit(n)
    centre = (Pk[11] + Pk[12] + Pk[23] + Pk[24]) / 4
    if (Pk[0] - (Pk[11] + Pk[12]) / 2) @ n < 0:
        n = -n
    return n, centre


def keep_wrist_behind(P: np.ndarray, frames: np.ndarray, hand: str = "R", margin: float = 0.01,
                      length: float | None = None, iterations: int = 20) -> np.ndarray:
    """Postcondition for the backhand backswing: on `frames`, a hitting wrist that is across the
    body (free-arm side) must not be in front of the shoulder-hip plane. Moves it to `margin`
    behind, re-projected to forearm `length` from the (fixed) elbow, repeating until it holds;
    the hand points move with the wrist."""
    out = np.asarray(P, float).copy()
    el, wr = (14, 16) if hand == "R" else (13, 15)
    hand_pts = (18, 20, 22) if hand == "R" else (17, 19, 21)
    free_sh, hit_sh = (11, 12) if hand == "R" else (12, 11)
    for k in np.where(np.asarray(frames, bool))[0]:
        L = length if length is not None else float(np.linalg.norm(out[k, wr] - out[k, el]))
        w0 = out[k, wr].copy()
        for _ in range(iterations):
            nrm, c = frontal_plane(out[k])
            across = (out[k, wr] - c) @ _unit(out[k, hit_sh] - out[k, free_sh]) < 0
            depth = (out[k, wr] - c) @ nrm
            if not across or depth <= -margin + 1e-9:
                break
            w = out[k, wr] - (depth + margin) * nrm
            out[k, wr] = out[k, el] + _unit(w - out[k, el]) * L
        else:  # still in front: clamp the depth (may shorten the drawn forearm slightly)
            out[k, wr] = out[k, wr] - (depth + margin) * nrm
        for h in hand_pts:
            out[k, h] = out[k, h] + (out[k, wr] - w0)
    return out


def fix_occluded_hitting_wrist(P: np.ndarray, filled: np.ndarray, evidence: np.ndarray | None = None,
                               evidence_ok: np.ndarray | None = None, protect: tuple[int, int] | None = None,
                               hand: str = "R", window: int = 9, blend: int = BLEND) -> tuple[np.ndarray, np.ndarray]:
    """Backhand backswing: put a guessed hitting wrist where the evidence says, usually behind the body.

    On a backhand backswing the free arm hides the hitting arm from a camera behind the
    player, and a naive fill draws the hitting wrist extended IN FRONT of the body. For each
    guessed hitting-wrist frame outside `protect`:
    - with evidence (e.g. a low-confidence two-camera triangulation where the second camera
      still sees the wrist, evidence_ok), the forearm points from the (seen) elbow toward it;
    - without evidence, a wrist that is in front of the shoulder-hip plane while across the
      body (past the body's midline toward the free shoulder) is mirrored to the behind side.
    The forearm keeps its median length (the elbow stays put, so the arm stays folded), the
    direction is lightly filtered over each run and faded into the seen frames at the ends,
    and the hand points move with the wrist. Returns (new P, mask of frames changed).
    """
    P = np.asarray(P, float)
    n = len(P)
    el, wr = (14, 16) if hand == "R" else (13, 15)
    hand_pts = (18, 20, 22) if hand == "R" else (17, 19, 21)
    free_sh, hit_sh = (11, 12) if hand == "R" else (12, 11)
    keep = np.zeros(n, bool)
    if protect is not None:
        keep[max(0, protect[0]):min(n, protect[1] + 1)] = True
    guessed = np.asarray(filled, bool)[:, wr] & ~keep
    L = np.linalg.norm(P[:, wr] - P[:, el], axis=1)
    length = float(np.median(L[~np.asarray(filled, bool)[:, wr]])) if (~filled[:, wr]).any() else float(np.median(L))
    d = _unit(P[:, wr] - P[:, el])
    target = d.copy()
    for k in np.where(guessed)[0]:
        if evidence is not None and evidence_ok is not None and evidence_ok[k] and np.isfinite(evidence[k]).all():
            target[k] = _unit(evidence[k] - P[k, el])
            continue
        nrm, c = frontal_plane(P[k])
        side = _unit(P[k, hit_sh] - P[k, free_sh])
        across = (P[k, wr] - c) @ side < 0  # on the free-arm side of the body
        depth = (P[k, wr] - c) @ nrm
        if across and depth > 0:
            w2 = P[k, wr] - 2 * depth * nrm
            target[k] = _unit(w2 - P[k, el])
    new = d.copy()
    for i, j in _runs(guessed):
        seg = target[i:j]
        if j - i >= window:
            seg = _unit(savgol_filter(seg, window, 2, axis=0, mode="interp"))
        ramp = np.ones(j - i)
        for k in range(min(blend, j - i)):
            f = (k + 1) / (blend + 1)
            if i > 0:
                ramp[k] = min(ramp[k], f)
            if j < n:
                ramp[j - i - 1 - k] = min(ramp[j - i - 1 - k], f)
        new[i:j] = _unit(ramp[:, None] * seg + (1 - ramp[:, None]) * d[i:j])
    out = P.copy()
    w_new = P[:, el] + new * length
    delta = w_new - P[:, wr]
    out[guessed, wr] = w_new[guessed]
    for h in hand_pts:
        out[guessed, h] = P[guessed, h] + delta[guessed]
    # the filter and end ramps can pull a frame back in front: enforce "behind" again
    out = keep_wrist_behind(out, guessed, hand, length=length)
    return out, guessed
