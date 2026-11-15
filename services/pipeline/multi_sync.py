"""Dominant swing peaks and sequence clocks, used only by multi uploads.

Strength is amplitude (audio RMS or gyro magnitude), never amplitude squared.
The session reference is the median of its five strongest candidates (or all
candidates if fewer). A candidate must reach half that reference and be the
strongest event within two real seconds; equal peaks keep the earlier event.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np


def select_swing_peaks(times, strength, top_n: int = 5, window_s: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Remove small taps/movements and weaker neighbors without moving contacts."""
    times, strength = np.asarray(times, dtype=float), np.asarray(strength, dtype=float)
    if times.ndim != 1 or strength.shape != times.shape:
        raise ValueError('Swing peak times and strengths must be matching one-dimensional arrays')
    if not isinstance(top_n, int) or top_n < 1 or not math.isfinite(window_s) or window_s <= 0:
        raise ValueError('Swing peak selection needs a positive top-N and time window')
    valid = np.isfinite(times) & np.isfinite(strength) & (strength > 0)
    times, strength = times[valid], strength[valid]
    if not len(times):
        return times, strength
    order = np.argsort(times, kind='stable')
    times, strength = times[order], strength[order]
    threshold = .5 * float(np.median(np.sort(strength)[-top_n:]))
    admitted = strength >= threshold
    times, strength = times[admitted], strength[admitted]
    # A monotone deque makes local suppression linear after sorting, including
    # long sensor exports with many candidate movements. Equal strengths retain
    # the earlier index, rather than retaining two peaks from the same window.
    keep, window, right = [], deque(), 0
    for index, when in enumerate(times):
        while right < len(times) and times[right] < when + window_s - 1e-9:
            while window and strength[window[-1]] < strength[right]:
                window.pop()
            window.append(right)
            right += 1
        while window and times[window[0]] <= when - window_s + 1e-9:
            window.popleft()
        if window and index == window[0]:
            keep.append(index)
    return times[keep], strength[keep]


def _pairs(a: np.ndarray, b: np.ndarray, offset: float, tolerance: float) -> list[tuple[int, int]]:
    """Monotonic, one-to-one nearest matches for a proposed clock offset."""
    candidates = []
    for i, when in enumerate(a + offset):
        right = int(np.searchsorted(b, when))
        for j in (right - 1, right):
            if 0 <= j < len(b) and abs(b[j] - when) <= tolerance + 1e-9:
                candidates.append((abs(float(b[j] - when)), i, j))
    used_a, used_b, selected = set(), set(), []
    for _, i, j in sorted(candidates):
        if i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
            selected.append((i, j))
    selected.sort()
    # Dominant swings are separated by 2 s, making crossed matches impossible
    # at our tolerance. Keep this guard for independent callers of the helper.
    if any(right[1] <= left[1] for left, right in zip(selected, selected[1:])):
        return []
    return selected


def match_sequence(a, b, tolerance_s: float = .12, min_matches: int = 3) -> dict:
    """Fit B = A + offset from several swings; never synchronize one loud tap.

    Missing leading/trailing events and occasional missed swings are allowed.
    At least 60% of the shorter sequence must match. Equally supported, similarly
    accurate distinct offsets (for example repeated regular runs) are ambiguous.
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if (a.ndim != 1 or b.ndim != 1 or not np.isfinite(a).all() or not np.isfinite(b).all()
            or np.any(np.diff(a) <= 0) or np.any(np.diff(b) <= 0)):
        raise ValueError('offset not found: swing times must be finite and strictly increasing')
    if not math.isfinite(tolerance_s) or tolerance_s <= 0 or min_matches < 3:
        raise ValueError('Sequence sync needs positive tolerance and at least three matches')
    if min(len(a), len(b)) < min_matches:
        raise ValueError(f'offset not found: need at least {min_matches} dominant swings in each source; provide offset_b_s')
    if len(a) * len(b) > 100_000:
        raise ValueError('offset not found: too many swing candidates for reliable sequence sync')
    required = max(min_matches, math.ceil(.6 * min(len(a), len(b))))
    candidates = {}
    for proposed in np.unique(np.round((b[:, None] - a).ravel(), 4)):
        pairs = _pairs(a, b, float(proposed), tolerance_s)
        if len(pairs) < required:
            continue
        differences = np.asarray([b[j] - a[i] for i, j in pairs])
        offset = float(np.median(differences))
        pairs = _pairs(a, b, offset, tolerance_s)
        if len(pairs) < required:
            continue
        differences = np.asarray([b[j] - a[i] for i, j in pairs])
        offset = float(np.median(differences))
        residual = differences - offset
        key = tuple(pairs)
        candidates[key] = (len(pairs), float(np.sqrt(np.mean(residual ** 2))),
                           offset, float(np.max(abs(residual))), pairs)
    ranked = sorted(candidates.values(), key=lambda row: (-row[0], row[1], abs(row[2]), row[2]))
    if not ranked:
        raise ValueError('offset not found: dominant swing spacing does not agree across sources; provide offset_b_s')
    best = ranked[0]
    uncertainty = max(.01, tolerance_s / 4)
    if any(row[0] == best[0] and abs(row[2] - best[2]) > 2 * tolerance_s
           and row[1] <= best[1] + uncertainty for row in ranked[1:]):
        raise ValueError('offset not found: swing sequence is ambiguous; provide offset_b_s')
    return {'offsetSeconds': best[2], 'pairs': [[i, j] for i, j in best[4]],
            'residualMs': best[3] * 1000, 'matchedCount': best[0]}
