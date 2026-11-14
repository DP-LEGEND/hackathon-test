"""Forearm orientation from the gyro alone: the fallback when the phone's own is missing or bad.

The phone's fused orientation (Orientation.csv) is preferred, because the phone already
corrects its drift with gravity. metrics.choose_orientation() falls back to this module
when that file is missing or its quaternions fail the gyro check (metrics.gyro_convention).

1. Bias. A phone gyro reads a small constant offset even when still, and integrating it
   gives drift. The offset is measured as the median gyro over the STILL samples around
   the two sync taps (the strapped arm rests while the other hand taps), skipping the
   taps themselves, and subtracted. Without taps, the first STILL_SEARCH_S of the
   recording is searched instead. With too few still samples the bias stays zero and the
   report says so.
2. Integration. R(t + dt) = R(t) * exp(w dt), with w the body-frame angular velocity
   (what Sensor Logger's gyro gives), starting from the identity. The absolute heading
   is arbitrary, and that's fine: the camera alignment (fuse.py) refits sensor-world ->
   camera for every swing, so a constant offset and slow leftover drift cancel there.
3. Roll. With this orientation, metrics measures roll as the gyro (less the bias from
   step 1) integrated about the forearm axis, not as the twist of the window's rotation. The forearm turns ~180 deg
   about another axis in that window, where the twist is ill-conditioned: on the mock a
   0.5 deg error in the integrated rotation moved the twist 20-30 deg, while the axial
   integral matches the truth.

The taps sit at the start of the session, so they can't bound drift for a swing a minute
later. What they give is a still stretch to measure the bias.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.spatial.transform import Rotation

from wrist.load import Recording

STILL_DPS = 20.0               # smoothed |gyro| below this counts as still
STILL_SMOOTH_S = 0.1
STILL_BEFORE_S, STILL_AFTER_S = 2.0, 1.0   # the bias window around the two taps
TAP_EXCLUDE_S = 0.15           # the taps themselves jolt the gyro: skip this long around each
STILL_SEARCH_S = 3.0           # without taps: the start of the recording
MIN_STILL_S = 0.3              # still samples needed to trust a bias
SUBSTEPS = 4                   # integration steps per gyro sample


def still_bias(rec: Recording, taps_s: Optional[Sequence[float]]) -> tuple[np.ndarray, dict[str, Any]]:
    """(gyro bias in rad/s, phone axes; how it was measured)."""
    t = rec.t
    speed = uniform_filter1d(np.degrees(np.linalg.norm(rec.gyro, axis=1)),
                             size=max(1, int(round(STILL_SMOOTH_S * rec.rate_hz))), mode="nearest")
    if taps_s:
        window = (t >= taps_s[0] - STILL_BEFORE_S) & (t <= taps_s[-1] + STILL_AFTER_S)
        for tap in taps_s:
            window &= np.abs(t - tap) > TAP_EXCLUDE_S
        where = "around the sync taps"
    else:
        window = t <= t[0] + STILL_SEARCH_S
        where = f"in the first {STILL_SEARCH_S:g} s (no sync taps found)"
    still = window & (speed < STILL_DPS)
    n = int(still.sum())
    info: dict[str, Any] = {"bias_from": where, "still_samples": n, "bias_dps": None,
                            "drift_if_uncorrected_deg_per_min": None, "warning": None}
    if n < MIN_STILL_S * rec.rate_hz:
        info["warning"] = (f"only {n} still gyro samples {where}: the gyro bias isn't removed, so the "
                           "integrated orientation drifts (roll over 250 ms and the per-swing camera fit "
                           "barely notice)")
        return np.zeros(3), info
    bias = np.median(rec.gyro[still], axis=0)
    info.update(bias_dps=[round(float(v), 3) for v in np.degrees(bias)],
                drift_if_uncorrected_deg_per_min=round(float(np.degrees(np.linalg.norm(bias))) * 60, 1))
    return bias, info


def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product of (..., 4) quaternions in scipy's (x, y, z, w) order: a then b in body axes."""
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], axis=-1)


def integrate_gyro(rec: Recording, bias: np.ndarray, substeps: int = SUBSTEPS) -> Rotation:
    """Phone-to-world rotations from the bias-corrected gyro, starting at the identity.

    Each sample interval is split into `substeps` steps with the rate interpolated linearly,
    then the steps are chained R_k = R_(k-1) * step (right-multiplied: the rate is in body
    axes) by a prefix scan, so it's vectorised.
    """
    f = (np.arange(substeps) + 0.5) / substeps
    g = rec.gyro - bias
    w = g[:-1, None, :] * (1 - f)[None, :, None] + g[1:, None, :] * f[None, :, None]
    dt = (np.diff(rec.t) / substeps)[:, None, None]
    q = np.vstack([[0.0, 0.0, 0.0, 1.0], Rotation.from_rotvec((w * dt).reshape(-1, 3)).as_quat()])
    d = 1
    while d < len(q):   # prefix products q_0 * q_1 * ... * q_i (Hillis-Steele scan)
        q[d:] = _qmul(q[:-d], q[d:])
        d *= 2
    return Rotation.from_quat(q[::substeps])


def gyro_orientation(rec: Recording, taps_s: Optional[Sequence[float]]
                     ) -> tuple[Rotation, dict[str, Any], np.ndarray]:
    """(phone-to-world rotations, report, the bias removed in rad/s) from the integrated gyro.

    The bias comes back so metrics can take the same one off the gyro before its axial roll
    integrals (zero when still_bias found too few still samples, as the report says).
    """
    bias, info = still_bias(rec, taps_s)
    return integrate_gyro(rec, bias), {"source": "integrated gyro", **info}, bias
