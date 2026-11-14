"""Impact quality from the forearm phone: clean hit or mishit. Owner: Henoch.

ESTIMATE, and RELATIVE: each impact is judged against the same player's other impacts in
the session, because nobody has labelled real mishits yet. A phone at 100 Hz on the
forearm also can't resolve racket-frame vibration directly, only its echo in the arm.

Per impact (the sensor's own spike, sync.py), after the same high-pass sync uses (the
swing's own smooth acceleration removed):
- peak_g: the spike's height in g.
- width_ms: how long the spike stays at or above half its height (first to last sample,
  within +-WIDTH_LIMIT_MS). A clean hit is one sharp knock. An off-centre hit sets the racket
  and arm shaking, so the spike lasts longer, and its height is often unusual.
- clipped: the accelerometer reached its range limit during the spike, so peak_g is only
  a floor.

judge() turns these into robust z-scores against the session's OTHER impacts (median and
MAD, with floors so identical swings don't divide by zero):
    z_peak  = (peak - usual) / spread      both ways: a frame hit jolts harder, a shank barely touches
    z_width = (width - usual) / spread     one way: only a longer spike is worse
An impact is a mishit when |z_peak| or z_width passes MISHIT_Z. Its score runs from 100
(your usual impact) through 50 (on the mishit line) to 0 (twice as far out).
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from wrist.load import Recording

G = 9.80665
PEAK_SEARCH_MS = 40.0       # the spike's peak is looked for this close to the impact time
WIDTH_LIMIT_MS = 100.0      # a spike can't be wider than this either side of its peak
MISHIT_Z = 3.0              # robust SDs from your usual impact
MIN_BASELINE = 4            # other impacts needed to judge one
CLIP_FRACTION, CLIP_MIN_SAMPLES = 0.995, 3   # a flat top this close to the max, this often = saturated


def clip_levels(rec: Recording) -> np.ndarray:
    """Per phone axis, the |acceleration| at which the sensor saturated (inf if it never did)."""
    a = np.abs(rec.acc)
    top = a.max(axis=0)
    flat = (a >= CLIP_FRACTION * top).sum(axis=0) >= CLIP_MIN_SAMPLES
    return np.where(flat, top, np.inf)


def impact_shape(rec: Recording, hp: np.ndarray, impact_s: float, clip: np.ndarray) -> dict[str, Any]:
    """peak_g, width_ms (full width at half maximum) and clipped for the spike at impact_s.

    hp: sync.spike_signal(rec), the high-passed acceleration magnitude.
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
    near = rec.acc[max(0, i - 2): i + 3]
    return {"peak_g": round(peak / G, 2), "width_ms": round(float(t_right - t_left) * 1000, 1),
            "clipped": bool((np.abs(near) >= CLIP_FRACTION * clip).any())}


def _usual(values: list[float], floor: float) -> tuple[float, float]:
    v = np.asarray(values, float)
    med = float(np.median(v))
    return med, max(1.4826 * float(np.median(np.abs(v - med))), floor)


def judge(shapes: dict[str, Optional[dict[str, Any]]], rate_hz: float) -> dict[str, dict[str, Any]]:
    """Each impact against the session's other (unclipped) impacts: quality, score, why."""
    ids = [k for k, v in shapes.items() if v is not None]
    out: dict[str, dict[str, Any]] = {}
    for sid in ids:
        s = shapes[sid]
        assert s is not None
        others = [shapes[o] for o in ids if o != sid and not shapes[o]["clipped"]]  # type: ignore[index]
        entry: dict[str, Any] = {"estimate": True, "label": "ESTIMATE", **s, "quality": None, "score": None,
                                 "z_peak": None, "z_width": None, "baseline_n": len(others), "reasons": [],
                                 "relative_to": "this session's other impacts"}
        if len(others) < MIN_BASELINE:
            entry["reasons"] = [f"needs {MIN_BASELINE} other impacts to compare with, has {len(others)}"]
            out[sid] = entry
            continue
        peak_med, peak_sd = _usual([o["peak_g"] for o in others], 0.05 * np.median([o["peak_g"] for o in others]))
        widths = [o["width_ms"] for o in others]
        width_med, width_sd = _usual(widths, max(0.1 * float(np.median(widths)), 500.0 / rate_hz))
        zp = (s["peak_g"] - peak_med) / peak_sd
        zw = (s["width_ms"] - width_med) / width_sd
        z = max(abs(zp), zw)
        reasons = []
        if zp > MISHIT_Z:
            reasons.append(f"spike {s['peak_g']:.1f} g, far above your usual {peak_med:.1f} g")
        elif zp < -MISHIT_Z:
            reasons.append(f"spike {s['peak_g']:.1f} g, far below your usual {peak_med:.1f} g")
        if zw > MISHIT_Z:
            reasons.append(f"spike {s['width_ms']:.0f} ms wide vs your usual {width_med:.0f} ms (the racket rang)")
        if s["clipped"]:
            reasons.append("the accelerometer hit its limit, so the real peak was higher")
        entry.update(quality="mishit" if z > MISHIT_Z else "clean",
                     score=int(round(100 * float(np.clip(1 - z / (2 * MISHIT_Z), 0.0, 1.0)))),
                     z_peak=round(float(zp), 1) + 0.0, z_width=round(float(zw), 1) + 0.0,  # no -0.0
                     reasons=reasons)
        out[sid] = entry
    return out
