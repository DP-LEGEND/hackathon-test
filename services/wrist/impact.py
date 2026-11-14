"""Impact from the forearm phone: how hard the knock was and how long the arm rang. Owner: Henoch.

ESTIMATE, REPORTED BUT NOT JUDGED: nobody has labelled real clean hits and mishits yet, so
nothing here says "clean" or "mishit". A phone at 100 Hz on the forearm also can't resolve
racket-frame vibration directly (that's hundreds of Hz), only its slower echo in the arm, and
it samples every 10 ms: resolution_ms says so.

Per impact (the sensor's own spike, sync.py), after the same high-pass sync uses (the
swing's own smooth acceleration removed):
- peak_g: the spike's height in g.
- width_ms: how long the spike stays at or above half its height (first to last sample,
  within +-WIDTH_LIMIT_MS).
- ring_down_ms: from the peak until the shaking dies away: the last sample at or above
  threshold_g (RING_FRACTION of the peak, or the recording's noise floor if that's higher)
  before the signal stays below it for RING_QUIET_MS. Ringing passes through zero between
  shakes, so short dips don't end it, and a lone noise blip after a quiet stretch doesn't
  extend it. A clean knock dies in a sample or two; an off-centre hit keeps the racket and
  arm shaking. ring_down_capped: still shaking at RING_LIMIT_MS.
- clipped: the accelerometer reached its range limit during the spike, so peak_g is only
  a floor.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from wrist.load import Recording

G = 9.80665
PEAK_SEARCH_MS = 40.0       # the spike's peak is looked for this close to the impact time
WIDTH_LIMIT_MS = 100.0      # a spike can't be wider than this either side of its peak
RING_FRACTION = 0.1         # ring-down ends when the shaking stays below this fraction of the peak
RING_LIMIT_MS = 300.0       # ...looked for this long after the peak
RING_QUIET_MS = 50.0        # ...and must stay below it this long to count as over
NOISE_K = 3.0               # noise floor = median + NOISE_K x MAD of the high-passed signal
CLIP_FRACTION, CLIP_MIN_SAMPLES = 0.995, 3   # a flat top this close to the max, this often = saturated


def clip_levels(rec: Recording) -> np.ndarray:
    """Per phone axis, the |acceleration| at which the sensor saturated (inf if it never did)."""
    a = np.abs(rec.acc)
    top = a.max(axis=0)
    flat = (a >= CLIP_FRACTION * top).sum(axis=0) >= CLIP_MIN_SAMPLES
    return np.where(flat, top, np.inf)


def noise_floor(hp: np.ndarray) -> float:
    """The high-passed signal's ordinary level (m/s^2): ring-down never counts noise as shaking."""
    med = float(np.median(hp))
    return med + NOISE_K * 1.4826 * float(np.median(np.abs(hp - med)))


def impact_shape(rec: Recording, hp: np.ndarray, impact_s: float, clip: np.ndarray,
                 floor: float = 0.0) -> dict[str, Any]:
    """peak_g, width_ms (full width at half maximum), ring-down and clipped for the spike at impact_s.

    hp: sync.spike_signal(rec), the high-passed acceleration magnitude. floor: noise_floor(hp).
    """
    t, n, dt = rec.t, rec.t.size, 1.0 / rec.rate_hz
    i0 = int(np.argmin(np.abs(t - impact_s)))
    k = max(1, int(round(PEAK_SEARCH_MS / 1000 * rec.rate_hz)))
    lo = max(0, i0 - k)
    i = lo + int(np.argmax(hp[lo:i0 + k + 1]))
    peak, half = float(hp[i]), float(hp[i]) / 2
    # Width = first to last sample at or above half height within the limit, not just the
    # contiguous run: a ringing racket's shake passes through zero between its swings.
    lim = int(round(WIDTH_LIMIT_MS / 1000 * rec.rate_hz))
    a0 = max(0, i - lim)
    above = np.flatnonzero(hp[a0:min(n, i + lim + 1)] >= half) + a0
    left, right = int(above[0]), int(above[-1])
    # Interpolate the outer half-height crossings between samples.
    t_left = t[left] - dt * (hp[left] - half) / (hp[left] - hp[left - 1]) \
        if left > 0 and hp[left - 1] < half else t[left]
    t_right = t[right] + dt * (hp[right] - half) / (hp[right] - hp[right + 1]) \
        if right < n - 1 and hp[right + 1] < half else t[right]
    # Ring-down: walk on from the peak until RING_QUIET_MS in a row below the threshold.
    thr = max(RING_FRACTION * peak, floor)
    ring_lim = int(round(RING_LIMIT_MS / 1000 * rec.rate_hz))
    quiet = max(1, int(round(RING_QUIET_MS / 1000 * rec.rate_hz)))
    end = min(n - 1, i + ring_lim)
    last, below, settled = i, 0, False
    for k in range(i + 1, end + 1):
        if hp[k] >= thr:
            last, below = k, 0
        else:
            below += 1
            if below >= quiet:
                settled = True
                break
    t_end = t[last] + dt * (hp[last] - thr) / (hp[last] - hp[last + 1]) \
        if last < n - 1 and hp[last + 1] < thr <= hp[last] else t[last]
    near = rec.acc[max(0, i - 2): i + 3]
    return {"peak_g": round(peak / G, 2), "width_ms": round(float(t_right - t_left) * 1000, 1),
            "ring_down_ms": round(min(float(t_end - t[i]) * 1000, RING_LIMIT_MS), 1),
            "ring_down_capped": not settled and end == i + ring_lim,  # still shaking at the limit
            "threshold_g": round(thr / G, 2),
            "clipped": bool((np.abs(near) >= CLIP_FRACTION * clip).any())}


def impact_report(rec: Recording, hp: np.ndarray, impact_s: float, clip: np.ndarray, floor: float) -> dict[str, Any]:
    """One impact's numbers, labelled ESTIMATE and explicitly not judged."""
    return {"estimate": True, "label": "ESTIMATE", **impact_shape(rec, hp, impact_s, clip, floor),
            "resolution_ms": round(1000.0 / rec.rate_hz, 1), "judged": False,
            "note": "reported only: not judged as clean or mishit until real labelled hits exist"}
