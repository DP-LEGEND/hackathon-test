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

from physics.metrics import contact_frame, shoulder_coil, shoulder_yaw
from physics.skeleton import (
    ARM, L_ANKLE, L_KNEE, L_SH, R_ANKLE, R_KNEE, R_SH, RACKET_TIP, hitting_hand, to_array, up_vector,
)

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


def stroke_side(swing: dict, hand: str | None = None) -> tuple[str, float]:
    """("forehand" | "backhand", wrist side offset). Defaults to forehand if unmeasurable."""
    P = to_array(swing)
    hand = hand or hitting_hand(P)
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
    hand = hand or hitting_hand(P)
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
