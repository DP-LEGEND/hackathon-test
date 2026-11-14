"""Measurements the coach needs that physics/metrics.py doesn't have yet. Owners: aryan and Dev.

Code measures, Claude explains: every number here is computed from the skeleton.
These belong in physics/metrics.py eventually; they live here so the coach can use
them now without editing physics. Both reuse the physics skeleton helpers.

- stroke_side: forehand or backhand, from which side of the body the hitting wrist
  is on during the backswing. LOW confidence: on data/samples/swing_sample.json
  (labelled backhand) it says forehand, so either the label or the skeleton's
  left/right shoulders are off. An explicit stroke always wins over this.
- stance_open_deg: angle between the feet line and the hitting direction at contact.
  0 = fully side-on (closed), 90 = feet square to the shot (fully open).
"""

from __future__ import annotations

import numpy as np

# _smooth, WRIST_SMOOTH_MS and RELEASE_WINDOW_MS: the exact smoothing and window physics
# uses for wrist_release_ms, so the directional timing below matches it on clean swings.
from physics.metrics import (
    RELEASE_WINDOW_MS, WRIST_SMOOTH_MS, _smooth, contact_frame, shoulder_coil, shoulder_yaw, wrist_angle,
)
from physics.skeleton import (
    ARM, L_ANKLE, L_KNEE, L_SH, R_ANKLE, R_KNEE, R_SH, RACKET_TIP, to_array, up_vector,
)
from physics.skeleton import swing_hand as physics_swing_hand

STROKES = ("forehand", "backhand")

# Stance is measured from the ankles. The pipeline fills a missing ankle by copying its
# knee (pipeline/process.py complete_optional_joints) and lists it in
# metadata.approximatedJoints. A filled ankle is a placeholder, not a measurement.
STANCE_JOINTS = {L_ANKLE: L_KNEE, R_ANKLE: R_KNEE}


def stance_joints_filled(swing: dict, contact: int) -> dict[int, str]:
    """Ankles we can't trust for stance on this swing: {joint id: why}. Empty = OK.

    - "approximated": listed in metadata.approximatedJoints. That list is per swing,
      not per frame, so we can't rule out contact and treat it as filled there.
    - "missing at contact": no finite position at the contact frame.
    - "copied from knee at contact": exactly the knee's position, the pipeline's fill
      signature (real ankle and knee points never coincide).
    Short gaps the pipeline interpolates aren't flagged in the swing JSON, so they
    can't be detected here.
    """
    listed = set((swing.get("metadata") or {}).get("approximatedJoints") or [])
    P = to_array(swing)
    out: dict[int, str] = {}
    for ankle, knee in STANCE_JOINTS.items():
        a, k = P[contact, ankle], P[contact, knee]
        if ankle in listed:
            out[ankle] = "approximated"
        elif not np.isfinite(a).all():
            out[ankle] = "missing at contact"
        elif np.isfinite(k).all() and np.array_equal(a, k):
            out[ankle] = "copied from knee at contact"
    return out


def wrist_uncock(swing: dict, hand: str, contact: int, fps: float) -> tuple[float, float | None]:
    """(uncock_deg, uncock_ms): how the wrist RELEASES before contact, with direction.

    The wrist angle is elbow-wrist-index: smaller = more cocked, 180 = racket in line,
    so uncocking (releasing) makes it grow. Cocking, or holding the cock, never counts.
    - uncock_deg: how far the angle has opened by contact from its most-cocked point
      before contact (>= 0). A held or still-increasing cock gives ~0. Never more than
      the max - min range of the same curve; on a real release it is close to the
      range pipeline.features reports (which smooths slightly differently).
    - uncock_ms: ms before contact of the fastest OPENING of the angle, in the same
      window and smoothing as physics wrist_release_ms (negative = after contact).
      None if the angle never opens there.
    """
    P = to_array(swing)
    win = max(1, int(round(WRIST_SMOOTH_MS * fps / 1000)) | 1)
    th = _smooth(wrist_angle(P, hand), win)
    c = int(np.clip(contact, 0, len(th) - 1))
    before = th[: c + 1]
    uncock_deg = (float(max(0.0, th[c] - np.nanmin(before)))
                  if np.isfinite(th[c]) and np.isfinite(before).any() else float("nan"))

    if len(th) < 3:
        return uncock_deg, None
    rate = np.gradient(th) * fps  # signed: + = opening (uncocking)
    lo = max(1, c - int(round(RELEASE_WINDOW_MS[0] * fps / 1000)))
    hi = min(len(th) - 2, c + int(round(RELEASE_WINDOW_MS[1] * fps / 1000)))
    window = rate[lo : hi + 1]
    if hi < lo or not np.isfinite(window).any() or np.nanmax(window) <= 0:
        return uncock_deg, None
    k = lo + int(np.nanargmax(window))
    # Sub-frame peak, as physics does.
    y0, y1, y2 = rate[k - 1], rate[k], rate[k + 1]
    den = y0 - 2 * y1 + y2
    off = 0.5 * (y0 - y2) / den if np.isfinite(den) and abs(den) > 1e-12 else 0.0
    off = float(np.clip(off, -0.5, 0.5))
    return uncock_deg, (c - (k + off)) / fps * 1000


def wrist_index_filled(swing: dict, hand: str, contact: int) -> str | None:
    """Why the hitting-side index finger can't be trusted for wrist angles, or None if it can.

    The wrist angle is elbow-wrist-index. The pipeline fills a missing index finger
    by copying the wrist (pipeline/process.py complete_optional_joints); the hand
    segment then has zero length and pipeline.features reads a fake 90 deg angle.
    - "approximated": listed in metadata.approximatedJoints (per swing, so any frame).
    - "copied from wrist at frame N": exactly the wrist's position on a frame up to
      contact, the fill signature (a real fingertip never sits on the wrist).
    """
    index, wrist = ARM[hand]["index"], ARM[hand]["wr"]
    listed = set((swing.get("metadata") or {}).get("approximatedJoints") or [])
    if index in listed:
        return f"joint {index} approximated"
    P = to_array(swing)
    for f in range(min(contact, len(P) - 1) + 1):
        i, w = P[f, index], P[f, wrist]
        if np.isfinite(i).all() and np.isfinite(w).all() and np.array_equal(i, w):
            return f"joint {index} copied from wrist at frame {f}"
    return None


def _flat(v: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Project vector(s) onto the floor plane."""
    return v - np.outer(v @ up, up) if v.ndim > 1 else v - (v @ up) * up


def wrist_side_offset(P: np.ndarray, hand: str, contact: int, up: np.ndarray) -> float:
    """Median sideways position of the hitting wrist during the backswing, in shoulder widths.

    + = on the hitting-arm side of the body (forehand preparation),
    - = across the body (backhand preparation). NaN if it can't be measured.
    """
    top, _ = shoulder_coil(shoulder_yaw(P, up), contact)
    end = top if top > 0 else contact
    wr = ARM[hand]["wr"]
    # For a left-hander the hitting side is the left, so flip the sign.
    sign = 1.0 if hand == "R" else -1.0
    offsets = []
    for f in range(0, end + 1):
        lr = _flat(P[f, R_SH] - P[f, L_SH], up)
        width = np.linalg.norm(lr)
        if not np.isfinite(width) or width < 1e-6:
            continue
        rel = _flat(P[f, wr] - (P[f, L_SH] + P[f, R_SH]) / 2, up)
        val = sign * float(rel @ lr) / width**2
        if np.isfinite(val):
            offsets.append(val)
    return float(np.median(offsets)) if offsets else float("nan")


def recorded_hand(swing: dict) -> str | None:
    """The hand the pipeline recorded, or None if it would have to be guessed.

    Same sources, in the same order, as physics.skeleton.swing_hand (metadata.hand, then
    swing["hand"]); only used to report whether the hand was recorded or guessed.
    """
    meta = swing.get("metadata")
    for hand in ((meta.get("hand") if isinstance(meta, dict) else None), swing.get("hand")):
        if hand in ("R", "L"):
            return hand
    return None


def resolve_hand(swing: dict, hand: str | None = None, P: np.ndarray | None = None) -> str:
    """Explicit hand, else physics' swing_hand (recorded hand, else the faster wrist).

    One source of truth with physics, so the coach and physics never pick different arms.
    """
    if hand in ("R", "L"):
        return hand
    return physics_swing_hand(swing, P)


def stroke_side(swing: dict, hand: str | None = None) -> tuple[str, float]:
    """("forehand" | "backhand", wrist side offset). Defaults to forehand if unmeasurable."""
    P = to_array(swing)
    hand = resolve_hand(swing, hand, P)
    c = contact_frame(swing, P, hand)
    offset = wrist_side_offset(P, hand, c, up_vector(P))
    stroke = "backhand" if np.isfinite(offset) and offset < 0 else "forehand"
    return stroke, offset


def stance_open_deg(swing: dict, hand: str | None = None) -> float:
    """Feet line vs hitting direction at contact, folded to 0..90 degrees. NaN if unmeasurable.

    Hitting direction = racket tip velocity at contact if the racket is tracked,
    else the hitting wrist's velocity, both flattened onto the floor.
    """
    P = to_array(swing)
    hand = resolve_hand(swing, hand, P)
    c = contact_frame(swing, P, hand)
    up = up_vector(P)
    tip = P[:, RACKET_TIP]
    point = tip if np.isfinite(tip).all(axis=1).mean() > 0.8 else P[:, ARM[hand]["wr"]]
    if len(P) < 2:
        return float("nan")
    direction = _flat(np.gradient(point, axis=0)[c], up)
    feet = _flat(P[c, R_ANKLE] - P[c, L_ANKLE], up)
    nd, nf = np.linalg.norm(direction), np.linalg.norm(feet)
    if not (np.isfinite(nd) and np.isfinite(nf)) or nd < 1e-9 or nf < 1e-9:
        return float("nan")
    cos = abs(float(direction @ feet)) / (nd * nf)
    return float(np.degrees(np.arccos(np.clip(cos, 0.0, 1.0))))
