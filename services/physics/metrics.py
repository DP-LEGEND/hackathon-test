"""Swing metrics computed from the skeleton. Owner: aryan.

Each metric is a small pure function: skeleton in, number out. Claude never guesses
these numbers; it only quotes what `measure` returns.

Timing uses `fps_real`, the REAL capture rate. A 4x slow-mo clip rendered at 30 fps
has fps_real = 120. If `fps_real` isn't given we use swing["fps"].
"""

from __future__ import annotations

import numpy as np

from physics.skeleton import (
    ARM, L_ANKLE, L_SH, R_ANKLE, R_SH, RACKET_TIP, floor_basis, mid, speed, swing_hand, to_array,
    up_vector, L_HIP, R_HIP,
)

# Window (ms around contact) in which we look for the wrist release.
RELEASE_WINDOW_MS = (250.0, 50.0)
# The wrist angle is smoothed over this many ms before finding its fastest change.
# MediaPipe hand points are noisy (they blur near contact); smoothing doesn't move a
# genuine time shift, so injected wrist timing still re-measures correctly.
WRIST_SMOOTH_MS = 25.0


def _smooth(x: np.ndarray, win: int) -> np.ndarray:
    """Centred moving average that ignores NaNs."""
    if win <= 1:
        return x
    k = np.ones(win)
    valid = np.isfinite(x)
    num = np.convolve(np.where(valid, x, 0.0), k, "same")
    den = np.convolve(valid.astype(float), k, "same")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def real_fps(swing: dict, fps_real: float | None = None) -> float:
    fps = float(fps_real if fps_real is not None else swing["fps"])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    return fps


def contact_frame(swing: dict, P: np.ndarray | None = None, hand: str | None = None) -> int:
    """Frame of ball contact.

    Uses swing["contactFrame"] when it's there. Otherwise the frame where the racket tip
    moves fastest (if the racket is tracked in most frames), else the frame where the
    hitting wrist moves fastest relative to the hips.
    """
    n = len(swing["frames"])
    if n == 0:
        raise ValueError("swing has no frames")
    cf = swing.get("contactFrame")
    if isinstance(cf, (int, np.integer)) and 0 <= cf < n:
        return int(cf)
    P = to_array(swing) if P is None else P
    tip = P[:, RACKET_TIP]
    if np.isfinite(tip).all(axis=1).mean() > 0.8:
        v = speed(tip, 1.0)
    else:
        hand = hand or swing_hand(swing, P)
        v = speed(P[:, ARM[hand]["wr"]] - mid(P, L_HIP, R_HIP), 1.0)
    if not np.isfinite(v).any():
        return n // 2
    return int(np.nanargmax(v))


def joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle at b (degrees) for point series of shape (frames, 3). 180 = straight."""
    u, v = a - b, c - b
    cos = np.sum(u * v, -1) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1))
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def elbow_angle(P: np.ndarray, hand: str) -> np.ndarray:
    """Inside angle of the hitting elbow (shoulder-elbow-wrist), degrees. Smaller = more bent."""
    j = ARM[hand]
    return joint_angle(P[:, j["sh"]], P[:, j["el"]], P[:, j["wr"]])


def wrist_angle(P: np.ndarray, hand: str) -> np.ndarray:
    """Inside angle at the hitting wrist (elbow-wrist-index), degrees. Same as pipeline/features.py."""
    j = ARM[hand]
    return joint_angle(P[:, j["el"]], P[:, j["wr"]], P[:, j["index"]])


def shoulder_yaw(P: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Heading of the left->right shoulder line in the floor plane, degrees, unwrapped."""
    e1, e2 = floor_basis(up)
    d = P[:, R_SH] - P[:, L_SH]
    yaw = np.arctan2(d @ e2, d @ e1)
    ok = np.flatnonzero(np.isfinite(yaw))
    for span in np.split(ok, np.where(np.diff(ok) > 1)[0] + 1):
        if len(span):
            yaw[span] = np.unwrap(yaw[span])
    return np.degrees(yaw)


def shoulder_coil(yaw: np.ndarray, contact: int) -> tuple[int, float]:
    """(top_frame, signed turn in degrees) from the top of the backswing to contact.

    The top of the backswing is the frame before contact whose shoulder heading is
    furthest from the heading at contact.
    """
    d = yaw[: contact + 1] - yaw[contact]
    if contact == 0 or not np.isfinite(d).any() or not np.isfinite(yaw[contact]):
        return contact, 0.0
    top = int(np.nanargmax(np.abs(d)))
    return top, float(d[top])


def stance_angle(P: np.ndarray, hand: str, contact: int, up: np.ndarray) -> float:
    """Signed floor-plane angle from the hitting direction to the feet line at contact, degrees.

    Folded to -90..90: 0 = feet in line with the shot (side-on, closed), +-90 = feet square
    to it (fully open). The sign follows floor_basis: turning the feet by +a about `up`
    adds a. NaN if unmeasurable.

    Hitting direction = racket tip velocity at contact if the racket is tracked in most
    frames, else the hitting wrist's velocity. Same definition as
    coach/measure_extra.py stance_open_deg.
    """
    if len(P) < 2:
        return float("nan")
    tip = P[:, RACKET_TIP]
    point = tip if np.isfinite(tip).all(axis=1).mean() > 0.8 else P[:, ARM[hand]["wr"]]
    e1, e2 = floor_basis(up)
    d = np.gradient(point, axis=0)[contact]
    f = P[contact, R_ANKLE] - P[contact, L_ANKLE]
    d2, f2 = np.array([d @ e1, d @ e2]), np.array([f @ e1, f @ e2])
    nd, nf = np.linalg.norm(d2), np.linalg.norm(f2)
    if not (np.isfinite(nd) and np.isfinite(nf)) or nd < 1e-9 or nf < 1e-9:
        return float("nan")
    diff = np.degrees(np.arctan2(f2[1], f2[0]) - np.arctan2(d2[1], d2[0]))
    return float((diff + 90.0) % 180.0 - 90.0)


def wrist_release_ms(P: np.ndarray, hand: str, contact: int, fps: float) -> float:
    """How many ms before contact the wrist uncocks fastest (peak wrist angular speed).

    Positive = before contact, negative = after. Sub-frame accurate (parabola through the peak).
    Noisy on real MediaPipe hands; racket tracking would make it reliable.
    """
    win = max(1, int(round(WRIST_SMOOTH_MS * fps / 1000)) | 1)
    th = _smooth(wrist_angle(P, hand), win)
    if len(th) < 3:
        return float("nan")
    rate = np.abs(np.gradient(th)) * fps
    lo = max(1, contact - int(round(RELEASE_WINDOW_MS[0] * fps / 1000)))
    hi = min(len(th) - 2, contact + int(round(RELEASE_WINDOW_MS[1] * fps / 1000)))
    if hi < lo or not np.isfinite(rate[lo : hi + 1]).any():
        return float("nan")
    k = lo + int(np.nanargmax(rate[lo : hi + 1]))
    y0, y1, y2 = rate[k - 1], rate[k], rate[k + 1]
    den = y0 - 2 * y1 + y2
    off = 0.5 * (y0 - y2) / den if np.isfinite(den) and abs(den) > 1e-12 else 0.0
    off = float(np.clip(off, -0.5, 0.5))
    return (contact - (k + off)) / fps * 1000


def measure(swing: dict, fps_real: float | None = None, hand: str | None = None) -> dict:
    """The numbers the coach is allowed to quote for one swing."""
    P = to_array(swing)
    fps = real_fps(swing, fps_real)
    hand = hand or swing_hand(swing, P)
    c = contact_frame(swing, P, hand)
    up = up_vector(P)
    _, turn = shoulder_coil(shoulder_yaw(P, up), c)
    return {
        "hand": hand,
        "contact_frame": c,
        "fps_real": fps,
        "elbow_at_contact_deg": float(elbow_angle(P, hand)[c]),
        "wrist_at_contact_deg": float(wrist_angle(P, hand)[c]),
        "shoulder_turn_deg": abs(turn),
        "wrist_release_ms": wrist_release_ms(P, hand, c, fps),
        "stance_open_deg": abs(stance_angle(P, hand, c, up)),
    }


def describe(m: dict) -> str:
    """Short plain-text version of `measure` output (used as fine-tune input)."""
    side = {"R": "right", "L": "left"}[m["hand"]]
    rel = m["wrist_release_ms"]
    when = f"{abs(rel):.0f} ms {'before' if rel >= 0 else 'after'} contact"
    return (
        f"{side}-handed swing; elbow at contact {m['elbow_at_contact_deg']:.0f} deg; "
        f"shoulder turn {m['shoulder_turn_deg']:.0f} deg; wrist release {when}"
    )
