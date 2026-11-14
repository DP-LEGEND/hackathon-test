"""Conservative articulated pose repair; missing evidence stays missing."""
from __future__ import annotations

import numpy as np

# A tree rooted at the left hip, ordered parent before child.
PARENTS = {24: 23, 11: 23, 12: 24, 13: 11, 14: 12, 15: 13, 16: 14,
           0: 11, **{j: 0 for j in range(1, 11)},
           17: 15, 19: 15, 21: 15, 18: 16, 20: 16, 22: 16,
           25: 23, 26: 24, 27: 25, 28: 26, 29: 27, 31: 27, 30: 28, 32: 28}


def gap_limit(fps_real: float, seconds: float = .25) -> int:
    """Match the session's gap tolerance on its real capture clock."""
    return max(0, int(seconds * fps_real))


def runs(mask: np.ndarray):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))


def slerp(a: np.ndarray, b: np.ndarray, weight: float) -> np.ndarray:
    """Shortest angular path between unit bone directions, including antipodes."""
    cosine = float(np.clip(np.dot(a, b), -1, 1))
    if cosine > .9995:
        direction = (1 - weight) * a + weight * b
        return direction / np.linalg.norm(direction)
    if cosine < -.9995:
        axis = np.eye(3)[np.argmin(np.abs(a))]
        axis -= a * np.dot(a, axis)
        axis /= np.linalg.norm(axis)
        return np.cos(np.pi * weight) * a + np.sin(np.pi * weight) * axis
    angle = np.arccos(cosine)
    return (np.sin((1 - weight) * angle) * a + np.sin(weight * angle) * b) / np.sin(angle)


def repair_pose(points: np.ndarray, max_gap: int = 12, win: int = 5,
                *, filled: np.ndarray | None = None, provenance: bool = False):
    """Fill bounded bone angles, then smooth each observed run independently.

    Never extrapolate a gap or smooth across an unfilled gap. The translating
    root uses bounded position interpolation; limbs interpolate bone directions.
    """
    from pipeline.pose import smooth

    original = np.asarray(points, dtype=float)
    result = original.copy()
    repaired = ~np.isfinite(original).all(axis=2)
    if filled is not None:
        repaired |= filled
    for start, end in runs(~np.isfinite(original[:, 23]).all(axis=1)):
        if start == 0 or end == len(result) or end - start > max_gap:
            continue
        weight = np.arange(1, end - start + 1)[:, None] / (end - start + 1)
        result[start:end, 23] = ((1 - weight) * original[start - 1, 23]
                                  + weight * original[end, 23])
    result[:, 23] = smooth(result[:, 23], win)
    for child, parent in PARENTS.items():
        vectors = original[:, child] - original[:, parent]
        lengths = np.linalg.norm(vectors, axis=1)
        observed = np.isfinite(vectors).all(axis=1)
        if not observed.any():
            continue
        length = float(np.median(lengths[observed]))
        directions = np.full_like(vectors, np.nan)
        if length < 1e-9:
            # Degenerate optional points may already repeat their parent.
            directions[observed] = [1., 0., 0.]
        else:
            observed &= lengths > 1e-9
            directions[observed] = vectors[observed] / lengths[observed, None]
        for start, end in runs(~observed):
            if (start == 0 or end == len(result) or end - start > max_gap
                    or not np.isfinite(result[start:end, parent]).all()):
                continue
            repaired[start:end, child] = True
            for frame in range(start, end):
                directions[frame] = slerp(directions[start - 1], directions[end],
                                          (frame - start + 1) / (end - start + 1))
        directions = smooth(directions, win)
        norms = np.linalg.norm(directions, axis=1)
        valid = np.isfinite(norms) & (norms > 1e-9) & np.isfinite(result[:, parent]).all(axis=1)
        result[:, child] = np.nan
        result[valid, child] = result[valid, parent] + directions[valid] / norms[valid, None] * length
        repaired[:, child] |= repaired[:, parent]
    return (result, repaired) if provenance else result
