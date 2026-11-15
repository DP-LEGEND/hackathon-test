"""Racket face from the forearm roll, for the PREDICTED ball's aim. Owner: aryan.

The camera can't see the racket face. With a phone strapped to the forearm, the swing carries
its forearm roll through contact (swing["wrist"]["roll_change_abs_deg"], services/wrist):
that roll is measured. How much of it turns the racket face is NOT measured:

- face = FACE_PER_ROLL_DEG x (roll - the stroke's good median), 0 at or below the median,
  capped at FACE_CAP_DEG. FACE_PER_ROLL_DEG is an ASSUMPTION.
- A face turned by f degrees sends the ball f degrees cross-court (ASSUMED: the ball leaves
  along the face). Cross-court = towards the far side of the court from the drive spot: the
  left wall for a right-handed forehand, the right wall for a right-handed backhand.
- The aim starts from the player's STATED intent, a straight drive (0 deg, parallel to the
  side walls), as in the demo: a square face sends the ball straight.

So with sensor data, both PREDICTED balls are aimed this way (compare.py): yours from your
roll, the ghost's from its roll. Every fix except firm_wrist leaves the roll alone, so the
ghost keeps your face. The firm_wrist fix lowers the roll by its amount (the coach's amount
is roll - good median), which squares the face. Without usable sensor data nothing here is
used and the aim stays compare.py's wrist-direction estimate.

The good medians come from the first real session (14 Nov 2026 shadow swings, coach/faults.py
uses them as the rolled_wrist targets). Mock recordings (wrist.synth, roll ~16 deg good vs
~62 deg rolled) use the mock session's good median instead, and say MOCK.

The roll is used only when the coach's rolled_wrist rule can judge it (aim_roll): mock data
(the mock rule has no timing gate), or a real entry whose roll window sits on the gyro peak
(contact_source "gyro peak"), the timing those medians and the real lines were tuned on. A
real entry timed any other way (impact spike, double tap) keeps the camera's aim, with the
reason (AIM_NOT_GYRO_PEAK).
"""

from __future__ import annotations

import math
from typing import Any, Optional

from physics.ball import COURT_WIDTH_M

# ASSUMPTION (not measured): degrees the racket face turns per degree of forearm roll above the
# stroke's good median. Nothing measures the face yet; this only sizes the demo's PREDICTED aim.
FACE_PER_ROLL_DEG = 0.3
FACE_CAP_DEG = 15.0  # the face never turns more than this, however far the forearm rolls
# Good medians of the forearm roll through contact, degrees: real shadow session (n=15 good
# backhands, 10 good forehands; the forehand's 136.75 to 0.1) and the mock session.
GOOD_ROLL_DEG = {"forehand": 136.8, "backhand": 99.3}
MOCK_GOOD_ROLL_DEG = 16.5
INTENT = "straight drive"
INTENT_AZIMUTH_DEG = 0.0  # a straight drive: parallel to the side walls
ASSUMED_LABEL = "ASSUMED"
MOCK_LABEL = "MOCK (sensor)"  # mock data is labelled mock on screen
# The timing the real medians (and coach/faults.py's real lines) were tuned on.
GYRO_PEAK = "gyro peak"
AIM_NOT_GYRO_PEAK = ("Wrist roll not used for the aim: the face model's good medians were tuned on gyro-peak-timed "
                     "practice swings, and this swing's roll is timed from {source}, so the aim is the camera's.")


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def sensor_roll(swing: dict) -> Optional[dict[str, Any]]:
    """{"roll": deg, "mock": bool} from a usable swing["wrist"] entry, else None."""
    wrist = swing.get("wrist")
    if not isinstance(wrist, dict) or not wrist.get("usable") or not _finite(wrist.get("roll_change_abs_deg")):
        return None
    return {"roll": float(wrist["roll_change_abs_deg"]), "mock": bool(wrist.get("mock"))}


def aim_roll(swing: dict) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """(roll, None) when the face model may use the swing's wrist roll, i.e. when the coach's
    rolled_wrist rule can judge it: mock data, or a real entry timed at the gyro peak.
    (None, why) for a usable real entry timed any other way. (None, None) without usable sensor
    data, exactly as before."""
    roll = sensor_roll(swing)
    if roll is None or roll["mock"]:
        return roll, None
    source = swing["wrist"].get("contact_source")
    if source == GYRO_PEAK:
        return roll, None
    return None, AIM_NOT_GYRO_PEAK.format(source=f"the {source}" if source else "an unknown contact")


def good_roll(stroke: str, mock: bool) -> float:
    """The roll at which the face is square: the stroke's good median (the mock's for mock data)."""
    return MOCK_GOOD_ROLL_DEG if mock else GOOD_ROLL_DEG[stroke]


def face_deg(roll: float, good: float) -> float:
    """Racket face turn, degrees (>= 0): FACE_PER_ROLL_DEG per degree above `good`, capped."""
    return round(min(FACE_CAP_DEG, FACE_PER_ROLL_DEG * max(0.0, roll - good)), 1)


def cross_court_sign(anchor_x: float) -> float:
    """+1 if cross-court is towards the right wall (+azimuth), -1 if towards the left wall."""
    return 1.0 if anchor_x < COURT_WIDTH_M / 2 else -1.0


def cross_court_wall(anchor_x: float) -> str:
    return "right" if cross_court_sign(anchor_x) > 0 else "left"


def face_aim(roll: float, good: float, anchor_x: float, mock: bool) -> dict[str, Any]:
    """The azimuth entry for one side (compare.py's assumptions.launch.<side>.azimuth format)."""
    face = face_deg(roll, good)
    value = round(INTENT_AZIMUTH_DEG + cross_court_sign(anchor_x) * face, 1)
    source = "MOCK forearm roll" if mock else "forearm roll (wrist sensor)"
    if face > 0:
        why = (f"{source} {roll:.1f} deg, {roll - good:.1f} above the good median {good:g}, turns the "
               f"racket face {face:g} deg towards the {cross_court_wall(anchor_x)} wall (cross-court)")
    else:
        why = f"{source} {roll:.1f} deg, at or below the good median {good:g}: the racket face is square"
    return {
        "value": value, "unit": "deg", "estimate": False,
        "label": MOCK_LABEL if mock else ASSUMED_LABEL,
        "method": (f"your stated intent, a {INTENT} (0 deg), turned by the racket face; face assumed "
                   f"{FACE_PER_ROLL_DEG:g} deg per degree of roll above the good median (not measured), "
                   f"capped at {FACE_CAP_DEG:g}: {why}"),
        "clamped": FACE_PER_ROLL_DEG * max(0.0, roll - good) > FACE_CAP_DEG,
        "rawValue": value, "faceDeg": face, "rollDeg": round(roll, 1),
    }


def face_note(mock: bool) -> str:
    """The caveat line the page prints under the prediction (assumptions.note)."""
    roll = "MOCK forearm roll" if mock else "forearm roll from the wrist sensor"
    return (f" Aim: your stated {INTENT}, turned cross-court by the racket face, which is assumed to turn "
            f"{FACE_PER_ROLL_DEG:g}° per degree of {roll} above the good median (capped at {FACE_CAP_DEG:g}°); "
            "the camera can't see the face.")
