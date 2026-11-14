"""Swing tempo from the forearm phone's gyro. Owner: Henoch.

ESTIMATE. Times are ms from contact (the sensor's impact spike), read off the forearm's
total turn rate |gyro| (smoothed over SMOOTH_MS):
- backswing_start_ms: the forearm starts moving back (its speed rises past `rest`).
- forward_start_ms: the forward swing starts, i.e. the top of the backswing. That's either
  the end of a pause at the top, or the dip in speed where a looped swing turns forward.
  None when the gyro shows no turn-around (the backswing was all shoulders, not forearm).
- follow_through_end_ms: the forearm settles after contact (speed back under `rest`).
- backswing_ms, forward_swing_ms and follow_through_ms are the gaps between those events.
  tempo_ratio = backswing_ms / forward_swing_ms.
- backswing_to_contact_ms: backswing start to contact, the whole swing's duration. It needs
  only the backswing start, so it exists even when the top of the backswing can't be found.

rest = max(REST_DPS, REST_FRACTION x the swing's peak speed). "Moving" stretches closer
together than MERGE_GAP_MS count as one. A separate earlier stretch counts as the
backswing when it ended at most MAX_PAUSE_S before the forward swing. Events that can't be
found (the arm never settled within the look-back or look-ahead) are None, with a reason.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy.ndimage import uniform_filter1d

from wrist.load import Recording

SMOOTH_MS = 30.0
REST_DPS = 50.0
REST_FRACTION = 0.05
MERGE_GAP_MS = 60.0
MAX_PAUSE_S = 0.8
MIN_BACKSWING_MS = 80.0
LOOK_BACK_S, LOOK_AHEAD_S = 2.0, 1.0
PEAK_SEARCH_MS = 60.0
LOOP_DIP = 0.5             # a looped swing's turn-around: speed below this fraction of both peaks
SERIES_MS = (-1500, 1000)  # the exported angular-speed graph
SERIES_STEP_MS = 20


def speed_dps(rec: Recording) -> np.ndarray:
    """The forearm's total turn rate, deg/s, smoothed over SMOOTH_MS."""
    w = max(1, int(round(SMOOTH_MS / 1000 * rec.rate_hz)))
    return uniform_filter1d(np.degrees(np.linalg.norm(rec.gyro, axis=1)), size=w, mode="nearest")


def _runs(mask: np.ndarray, merge: int) -> list[tuple[int, int]]:
    """(first, last) index of each True run, joining runs separated by fewer than `merge` samples."""
    edges = np.flatnonzero(np.diff(np.r_[0, mask.astype(int), 0]))
    runs = [(int(a), int(b) - 1) for a, b in zip(edges[::2], edges[1::2])]
    merged: list[tuple[int, int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] - 1 < merge:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def tempo(rec: Recording, impact_s: float, speed: Optional[np.ndarray] = None) -> dict[str, Any]:
    """Backswing start, top of backswing and follow-through end around one impact."""
    s = speed_dps(rec) if speed is None else speed
    t, rate = rec.t, rec.rate_hz
    ic = int(np.argmin(np.abs(t - impact_s)))
    k = max(1, int(round(PEAK_SEARCH_MS / 1000 * rate)))
    ipk = max(0, ic - k) + int(np.argmax(s[max(0, ic - k): ic + k + 1]))
    peak = float(s[ipk])
    rest = max(REST_DPS, REST_FRACTION * peak)
    lo = max(0, int(np.searchsorted(t, impact_s - LOOK_BACK_S)))
    hi = min(t.size - 1, int(np.searchsorted(t, impact_s + LOOK_AHEAD_S)))

    def ms(i: Optional[float]) -> Optional[float]:
        return None if i is None else round((float(np.interp(i, np.arange(t.size), t)) - impact_s) * 1000)

    def crossing(i: int) -> float:
        """Fractional index where speed crosses `rest` between samples i and i + 1."""
        a, b = s[i], s[i + 1]
        return i + (rest - a) / (b - a) if a != b else i + 0.5

    runs = [(a + lo, b + lo) for a, b in _runs(s[lo:hi + 1] > rest, max(1, int(round(MERGE_GAP_MS / 1000 * rate))))]
    out: dict[str, Any] = {"estimate": True, "label": "ESTIMATE", "backswing_start_ms": None, "forward_start_ms": None,
                           "contact_ms": 0, "follow_through_end_ms": None, "backswing_ms": None,
                           "forward_swing_ms": None, "follow_through_ms": None, "tempo_ratio": None,
                           "backswing_to_contact_ms": None,
                           "peak_dps": round(peak), "rest_dps": round(rest), "reasons": []}
    fwd = next((r for r in runs if r[0] <= ipk <= r[1]), None)
    if fwd is None:
        out["reasons"].append("the forearm never moved faster than the rest level around contact")
        return out
    a, b = fwd
    if b < hi:
        out["follow_through_end_ms"] = ms(crossing(b))
    else:
        out["reasons"].append(f"the forearm was still moving {LOOK_AHEAD_S:g} s after contact")

    before = [r for r in runs if r[1] < a]
    prev = before[-1] if before else None
    if a <= lo:
        out["reasons"].append(f"the forearm never settled in the {LOOK_BACK_S:g} s before contact")
    elif (prev is not None and prev[0] > lo and (t[a] - t[prev[1]]) <= MAX_PAUSE_S
          and (t[prev[1]] - t[prev[0]]) * 1000 >= MIN_BACKSWING_MS):
        out["backswing_start_ms"] = ms(crossing(prev[0] - 1))
        out["forward_start_ms"] = ms(crossing(a - 1))          # the end of the pause at the top
    else:
        out["backswing_start_ms"] = ms(crossing(a - 1))
        # A looped swing: walk back from the peak down to the dip, stopping once the speed
        # clearly climbs again (to twice the dip, and at least `rest` above it).
        m = i = ipk
        while i > a:
            i -= 1
            if s[i] < s[m]:
                m = i
            elif s[i] > s[m] + max(rest, s[m]):
                break
        back_peak = float(s[a:m + 1].max())
        if s[m] < LOOP_DIP * min(back_peak, peak) and back_peak > 1.5 * rest:
            out["forward_start_ms"] = ms(float(m))             # the turn-around at the top
        if out["forward_start_ms"] is None:
            out["reasons"].append("no turn-around at the top of the backswing in the gyro")

    bs, fs, fe = out["backswing_start_ms"], out["forward_start_ms"], out["follow_through_end_ms"]
    if bs is not None:
        out["backswing_to_contact_ms"] = -bs
    if bs is not None and fs is not None:
        out["backswing_ms"] = fs - bs
        out["forward_swing_ms"] = -fs
        if fs < 0:
            out["tempo_ratio"] = round((fs - bs) / -fs, 2)
    if fe is not None:
        out["follow_through_ms"] = fe
    return out


def speed_series(rec: Recording, impact_s: float, speed: np.ndarray) -> list[Optional[int]]:
    """Smoothed |gyro| (deg/s) every SERIES_STEP_MS over SERIES_MS around contact; None off the recording."""
    grid = impact_s + np.arange(SERIES_MS[0], SERIES_MS[1] + 1, SERIES_STEP_MS) / 1000
    vals = np.interp(grid, rec.t, speed)
    inside = (grid >= rec.t[0]) & (grid <= rec.t[-1])
    return [int(round(float(v))) if ok else None for v, ok in zip(vals, inside)]


def series_grid_ms() -> list[int]:
    return list(range(SERIES_MS[0], SERIES_MS[1] + 1, SERIES_STEP_MS))
