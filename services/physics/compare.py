"""The player's swing next to the ghost: metrics, PREDICTED ball paths and what changed. Owner: aryan.

compare(swing, fix_name, amount) returns one JSON-able dict, all in COURT coordinates
("coordinateSystem": "court", the frame of physics/ball.py: metres, x 0-6.40 across from
the left wall, y up from the floor, z 0-9.75 back from the front wall):
    you    measured metrics, the swing on the court, and its PREDICTED ball path
    ghost  the same for the swing with one fix applied (physics/ghost.py)
    delta  metric and outcome changes, e.g. elbow 137.7 -> 149.7 deg, ball tin -> in

Your swing goes on the court with skeleton.to_court: turned to face the front wall, lowest
foot on the floor, and slid so YOUR racket head at contact sits over the ANCHOR, the drive
spot for the stroke. The ghost gets exactly the same turn and slide, so the two bodies
overlap and only the fixed part differs. Each PREDICTED ball starts at its own swing's racket
head at contact, so the ball leaves the racket you see: yours on the anchor, the ghost's
wherever the fix moved its racket (about 10 cm away for the elbow fixes). The same placement
and launch rule apply to both swings, so only the fix changes the ball: the ghost's aim is
yours turned by however much the fix turns its racket line at contact (ghost_azimuth).

Where the ball model's inputs come from (physics/ball.py):
- Contact: the swing's contactFrame. It is the hit sound when the pipeline's contactMethod is
  "audio-transient", else the pipeline's wrist-speed estimate; `contactMethod` says which.
- Stroke (forehand or backhand) picks the anchor and the default elevation: given, else the
  pipeline's label, else measured from the skeleton (ESTIMATE), else forehand labelled ASSUMED.
  A label the pipeline's classifier or the coach guessed is checked against the skeleton first.
- Launch point: each swing's racket head at contact, height above the lowest foot MEASURED.
  Yours sits over the anchor: where you hit from, MEASURED from the video when the camera sees
  the court lines (physics/court_spot.py, passed as `spot`), else the ASSUMED drive spot for the
  stroke (DRIVE_SPOT_RIGHT_HANDED, mirrored for a left-hander). The ghost's is wherever its
  racket head ends up with your placement. The racket head itself is an ESTIMATE until racket tracking exists
  (skeleton.racket_head: wrist + 0.45 m along the forearm).
- Racket speed is an ESTIMATE until racket tracking exists, from one of two sources:
  - Wrist sensor, when the swing carries a usable swing["wrist"] entry with a racket speed
    (services/wrist: camera wrist velocity + the forearm phone's gyro x RACKET_LEVER_M).
    Labelled "ESTIMATE (sensor)", or "MOCK (sensor)" for synthetic recordings. The ghost has
    no sensor, so its speed is yours scaled by the fix's change in the video estimate
    (ghost / you): only the fix changes it, never the switch of method.
  - Video otherwise ("ESTIMATE (video)"). The forearm and racket are treated as one
    straight lever turning about the elbow, so the racket's sweet spot moves
    (forearm + racket) / forearm times faster than the wrist:
        racket speed = wrist speed x (forearm + RACKET_LEVER_M) / forearm
    It ignores the wrist snap, so the hold_wrist_cock fix doesn't change it.
  RACKET_LEVER_M = RACKET_HEAD_M (0.45 m, the launch point) + GRIP_OFFSET_M, for both.
  assumptions.racketSpeed says which source was used, and why.
- Azimuth (aim across the court). Yours is an ESTIMATE: the floor-plane direction of the
  hitting wrist's velocity at contact, in court axes, clamped to +-AZIMUTH_LIMIT_DEG. Only
  within AZIMUTH_TRUST_DEG of straight, as on a drive; further off (a backhand's wrist moves
  sideways) the aim is ASSUMED straight. The ghost's is yours plus the fix's change in the
  racket line's floor heading at contact (elbow -> racket head, ghost minus you), with your
  label: the racket face turns with the trunk and forearm that carry it. A fix that leaves the
  trunk and forearm at contact where they were leaves the aim where it was.
- Every ghost aims a straight drive (TARGET_INTENT): parallel to the side walls, so down the right
  wall from the forehand spot and down the left from the backhand spot (mirrored for a
  left-hander). On top of its fix, the ghost holds the smallest shoulder turn at contact that puts
  its aim on that line (contact_turn_for_intent); your swing and ball are never changed. Pass
  intent=None for the fix alone.
- fix.explain says in plain words how the fix gets from body to ball, quoting only the numbers
  above with their labels. `validation` (when a validate_ball result is passed as `tracked`) puts
  your PREDICTED ball next to the real ball tracked in the clip.
- With usable wrist-sensor data the coach can judge (wrist_face.aim_roll: mock data, or a real
  roll timed at the gyro peak), both aims come from the racket face instead (wrist_face.py):
  your stated straight drive, turned cross-court by FACE_PER_ROLL_DEG (an ASSUMPTION) per
  degree of forearm roll above the stroke's good median, capped at FACE_CAP_DEG. The ghost's
  face comes from its roll, which only the firm_wrist fix changes (it lowers the roll by its
  amount; no joint moves), so at the coach's amount the ghost's face is square and its ball
  goes straight. The camera's aims (yours from the wrist, the ghost's from the racket line)
  stay as cameraAim, a cross-check, and no shoulder turn is held for the TARGET (assumptions.aim
  says why). firm_wrist without such data raises GuessedFixError. A real roll timed from the
  impact or a double tap keeps everything above (the camera's aims, the TARGET hold), and both
  azimuths' method and assumptions.face (applied false) say why.
- Elevation (launch angle) is ASSUMED: DEFAULT_ELEVATION_DEG for the stroke (12 forehand,
  3 backhand) unless you pass one for the swing. A swing's path at contact is too noisy to
  give the launch angle, and the face angle needs racket tracking.

Try it (from inside services/):

    python -m physics.compare ../public/swings/swing_fh_over_rotation.json turn_shoulders_less 15 --no-swings
    python -m physics.compare ../data/samples/swing_sample.json turn_shoulders_more 15 --no-swings

--no-swings leaves out the two skeletons so the numbers are readable. Clips from
pipeline/run.py store the 30 fps playback rate, so add the real capture rate, e.g.
--fps-real 120 for 4x slow motion, or every speed comes out 4x too slow.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from physics.ball import COURT_LENGTH_M, COURT_WIDTH_M, DEFAULT_CONTACT, predict_ball_path
from physics.ghost import EDITS, FIXES, apply_fix
from physics.wrist_face import (
    FACE_CAP_DEG, FACE_PER_ROLL_DEG, INTENT, INTENT_AZIMUTH_DEG, aim_roll, cross_court_wall, face_aim, face_note,
    good_roll,
)
from physics.metrics import contact_frame, measure, real_fps, shoulder_coil, shoulder_yaw
from physics.skeleton import (
    ARM, L_HIP, R_HIP, RACKET_HEAD_M, court_axes, court_shift, from_array, mid, racket_head, speed, swing_hand,
    to_array, up_vector,
)

# ---- Racket speed estimate ----
GRIP_OFFSET_M = 0.10           # estimate: the extra lever from the grip, beyond RACKET_HEAD_M
# Wrist to the sweet spot of a 686 mm (WSF maximum) racket: 0.55 m. services/wrist uses it too.
RACKET_LEVER_M = round(RACKET_HEAD_M + GRIP_OFFSET_M, 3)
VIDEO_LABEL = "ESTIMATE (video)"
SENSOR_LABEL = "ESTIMATE (sensor)"
SENSOR_MOCK_LABEL = "MOCK (sensor)"   # synthetic wrist recording: mock data is labelled mock
SPEED_WINDOW_MS = 25.0         # median wrist speed over this window around contact (skips one-frame spikes)
RACKET_SPEED_RANGE_MS = (1.0, 80.0)  # what ball.py accepts; anything outside is clamped and flagged

# ---- Shot direction ----
# ASSUMED launch angle by stroke; pass elevation_deg to set it for one swing. Calibrated on
# video: the IMG_2115 forehand (public/swings/swing_fh_over_rotation.json) hits the front wall
# near 1.8 m with 12 deg; the low IMG_2116 backhand (swing_2116_bh_stereo.json) hits it at
# 0.5-0.8 m, which 3 deg gives.
DEFAULT_ELEVATION_DEG = {"forehand": 12.0, "backhand": 3.0}
# ASSUMED drive spots (the anchor) for a right-hander, court (x, z) metres; mirrored across the
# court for a left-hander. Forehand: ball.py's DEFAULT_CONTACT, 1 m off the right wall.
# Backhand: 2 m off the left wall, where the IMG_2116 video shows the ball reaching the front
# wall (1.5-2.5 m from the left wall).
DRIVE_SPOT_RIGHT_HANDED = {
    "forehand": (DEFAULT_CONTACT[0], DEFAULT_CONTACT[2]),
    "backhand": (2.0, DEFAULT_CONTACT[2]),
}
# To measure the stroke, the racket head must be at least this far to one side of the hips at contact.
SIDE_DEAD_ZONE_M = 0.10
# Aim (azimuth): the wrist's direction at contact is trusted only within AZIMUTH_TRUST_DEG of
# straight, as on a drive. Further off it is moving sideways (a backhand: 53 deg on IMG_2116),
# so the aim is ASSUMED straight instead. A trusted aim is clamped to +-AZIMUTH_LIMIT_DEG.
AZIMUTH_TRUST_DEG = 25.0
AZIMUTH_LIMIT_DEG = 20.0
# Below this floor-projected forearm length (m) at contact the racket line is too close to
# vertical to give a heading, so a fix's turn of it counts as unmeasured (racket_line_heading).
RACKET_LINE_MIN_FLOOR_M = 0.05
# A shot intent the player stated -> the aim it means across the court, degrees (0 = parallel to
# the side walls). With one, the shoulder fixes (AIM_FIXES, the only fixes that turn the trunk)
# hold the smallest turn at contact that puts the ghost's aim on it (contact_turn_for_intent).
INTENT_AIMS = {"straight drive": 0.0}
AIM_FIXES = ("turn_shoulders_less", "turn_shoulders_more")
# Every ghost aims this shot unless the caller says otherwise: 0 deg is parallel to the side walls,
# so from the forehand spot it runs down the right wall and from the backhand spot down the left
# (the spots are mirrored for a left-hander). Labelled TARGET; an intent passed in is STATED.
TARGET_INTENT = "straight drive"
# The largest turn a fix other than the shoulder fixes may hold at contact to aim the ghost, deg
# (a shoulder fix is capped at its own size). The aim itself is clamped to this too.
AIM_HOLD_LIMIT_DEG = AZIMUTH_LIMIT_DEG
# Straight drive: struck later than a cross-court, with the ball further back beside the body
# (coaching knowledge, not measured). ASSUMPTION: the straight-drive ghost meets the ball this much
# further back along the shot line (away from the front wall) than your racket head at contact.
# Its racket speed and its body are unchanged; only where the ball leaves the racket moves.
LATER_CONTACT_BACK_M = 0.2
_TARGET = object()  # compare()'s default intent: TARGET_INTENT, labelled TARGET
# assumptions.aim.why when usable wrist-sensor data aims both balls by the racket face (wrist_face.py).
FACE_AIMS_WHY = ("the wrist sensor's forearm roll aims both balls by the racket face (ASSUMED face model), "
                 "so no shoulder turn is held at contact")

SIDES = ("forehand", "backhand")

# Metrics we compare, in display order: measure() key -> (unit, words for the summary).
METRICS = {
    "elbow_at_contact_deg": ("deg", "elbow at contact"),
    "shoulder_turn_deg": ("deg", "shoulder turn"),
    "wrist_at_contact_deg": ("deg", "wrist angle at contact"),
    "wrist_release_ms": ("ms", "wrist release before contact"),
    "stance_open_deg": ("deg", "stance open to the shot"),
}


def _num(x, nd: int = 1) -> float | None:
    """Round for JSON; NaN and infinity become None (JSON has no NaN)."""
    if x is None or not math.isfinite(x):
        return None
    return round(float(x), nd)


def estimate_racket_speed(swing: dict, fps_real: float | None = None, hand: str | None = None) -> dict:
    """ESTIMATED racket (sweet spot) speed at contact from the hitting wrist's speed.

    racket speed = median wrist speed around contact x (forearm + RACKET_LEVER_M) / forearm.
    `value` is rounded to 0.1 m/s and clamped to what ball.py accepts (`clamped` says when).
    """
    P = to_array(swing)
    if len(P) < 2:
        raise ValueError("need at least two frames to measure a speed")
    fps = real_fps(swing, fps_real)
    hand = hand or swing_hand(swing, P)
    c = contact_frame(swing, P, hand)
    j = ARM[hand]
    half = max(1, round(SPEED_WINDOW_MS / 2 * fps / 1000))
    near = np.linalg.norm(np.gradient(P[:, j["wr"]], axis=0), axis=1)[max(0, c - half): c + half + 1] * fps
    forearms = np.linalg.norm(P[:, j["wr"]] - P[:, j["el"]], axis=1)
    if not (np.isfinite(near).any() and np.isfinite(forearms).any()):
        raise ValueError("can't estimate racket speed: the hitting elbow and wrist aren't visible around contact")
    wrist, forearm = float(np.nanmedian(near)), float(np.nanmedian(forearms))
    if forearm <= 0:
        raise ValueError("can't estimate racket speed: the hitting forearm has zero length")
    raw = wrist * (forearm + RACKET_LEVER_M) / forearm
    lo, hi = RACKET_SPEED_RANGE_MS
    return {
        "value": round(min(max(raw, lo), hi), 1),
        "unit": "m/s",
        "estimate": True,
        "label": VIDEO_LABEL,
        "source": "video",
        "method": "wrist speed x (forearm + racket) / forearm",
        "wristSpeedMs": round(wrist, 2),
        "forearmM": round(forearm, 3),
        "racketLeverM": RACKET_LEVER_M,
        "clamped": not lo <= raw <= hi,
        "rawValue": round(raw, 1),
    }


def sensor_racket_speed(swing: dict) -> tuple[dict | None, str]:
    """Your racket speed from the forearm phone, or (None, why not).

    Reads swing["wrist"] (python -m wrist.run writes it; docs/interfaces.md): used only when
    it's usable and its racket_speed_sensor has a value. The label comes from the entry's
    own mock flag, so a synthetic recording always says MOCK.
    """
    wrist = swing.get("wrist")
    if not isinstance(wrist, dict):
        return None, "no wrist sensor data for this swing"
    if not wrist.get("usable"):
        return None, f"wrist sensor data unusable: {wrist.get('skip_reason') or 'marked unusable'}"
    rs = wrist.get("racket_speed_sensor")
    value = rs.get("value") if isinstance(rs, dict) else None
    if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0):
        why = rs.get("reason") if isinstance(rs, dict) else None
        return None, "the wrist sensor gave no racket speed" + (f": {why}" if why else "")
    raw = rs.get("rawValue")
    raw = float(raw) if isinstance(raw, (int, float)) and math.isfinite(raw) and raw > 0 else float(value)
    mock = bool(wrist.get("mock") or rs.get("mock"))
    return {**rs, "rawValue": raw, "estimate": True, "label": SENSOR_MOCK_LABEL if mock else SENSOR_LABEL,
            "source": "wrist sensor", "mock": mock, "contactSource": wrist.get("contact_source")}, ""


def _clamped_speed(raw: float) -> dict:
    lo, hi = RACKET_SPEED_RANGE_MS
    return {"value": round(min(max(raw, lo), hi), 1), "clamped": not lo <= raw <= hi, "rawValue": round(raw, 1)}


def racket_speeds(swing: dict, you_video: dict, ghost_video: dict) -> tuple[dict, dict, dict]:
    """(your racket speed, the ghost's, assumptions.racketSpeed): the sensor's when usable, else video.

    The ghost never borrows your measured number: it gets yours x (ghost / you) video
    estimates, so the change between you and the ghost is the fix's alone.
    """
    sensor, why = sensor_racket_speed(swing)
    if sensor is not None and not you_video["rawValue"] > 0:
        sensor, why = None, "the video estimate is zero, so the fix's change can't scale the sensor speed"
    if sensor is None:
        return you_video, ghost_video, {"source": "video", "label": VIDEO_LABEL, "why": why}
    scale = ghost_video["rawValue"] / you_video["rawValue"]
    you = {**sensor, **_clamped_speed(sensor["rawValue"])}
    ghost = {
        "unit": "m/s", "estimate": True, "label": sensor["label"], "source": "wrist sensor, scaled by the fix",
        "mock": sensor["mock"], **_clamped_speed(sensor["rawValue"] * scale),
        "method": "your sensor racket speed x (ghost / you) video estimates, so only the fix changes it",
        "scale": round(scale, 3), "videoYouMs": you_video["value"], "videoGhostMs": ghost_video["value"],
    }
    note = {"source": "wrist sensor", "label": sensor["label"],
            "why": "your speed from the forearm phone (camera wrist velocity + gyro x lever, "
                   f"{RACKET_LEVER_M:g} m); the ghost's is yours scaled by the fix's change in the video estimate",
            "videoEstimateMs": you_video["value"]}
    return you, ghost, note


def ball_contact(swing: dict, P: np.ndarray, hand: str) -> tuple[int, str]:
    """(frame, how it was found): when the racket meets the ball.

    The swing's contactFrame, with the pipeline's contactMethod: "audio-transient" when the hit
    sound timed it, else an estimate (the pipeline stores the frame where the hitting wrist moves
    fastest). Without a usable contactFrame, that wrist-speed peak is measured here.
    """
    cf = swing.get("contactFrame")
    meta = swing.get("metadata") if isinstance(swing.get("metadata"), dict) else {}
    if isinstance(cf, (int, np.integer)) and not isinstance(cf, bool) and 0 <= cf < len(P):
        return int(cf), meta.get("contactMethod") or "provided-contact-estimate"
    v = speed(P[:, ARM[hand]["wr"]] - mid(P, L_HIP, R_HIP), 1.0)
    if not np.isfinite(v).any():
        raise ValueError("can't find the contact: no contactFrame and the hitting wrist isn't visible")
    return int(np.nanargmax(v)), "wrist-speed-peak-estimate"


# metadata.strokeSource values that mean a machine guessed the stroke label: the pipeline's
# classifier ("auto") or, for an ambiguous stroke, the coach (pipeline/live.py "coach-inferred").
AUTO_STROKE_SOURCES = ("auto", "coach-inferred")
AUTO_LABEL_OVERRIDDEN = "measured (auto label overridden)"
# strokeSource values a caller writes back after decide_stroke() measured the stroke from the
# skeleton (pipeline/live.py does, before coaching). compare() carries them through as ESTIMATE.
MEASURED_STROKE_SOURCES = ("measured", AUTO_LABEL_OVERRIDDEN)
STROKE_LABELS = {"given": "RECORDED", "recorded": "RECORDED", "measured": "ESTIMATE",
                 AUTO_LABEL_OVERRIDDEN: "ESTIMATE", "assumed": "ASSUMED"}


def _measured_stroke(P: np.ndarray, hand: str, contact: int) -> str | None:
    """The stroke from the skeleton, or None when it's too close to call.

    The hitting-hand side of the body at contact is a forehand: which side of the hips the
    racket head is on, across the court, at least SIDE_DEAD_ZONE_M out.
    """
    try:
        Pc = court_axes(P)
    except ValueError:  # can't tell up from down, so can't tell left from right either
        return None
    across = racket_head(Pc, hand)[contact, 0] - mid(Pc, L_HIP, R_HIP)[contact, 0]  # + = player's right
    if not np.isfinite(across) or abs(across) < SIDE_DEAD_ZONE_M:
        return None
    return "forehand" if (across > 0) == (hand == "R") else "backhand"


def swing_stroke(swing: dict, P: np.ndarray, hand: str, contact: int, side: str | None = None) -> tuple[str, str]:
    """("forehand" | "backhand", where it came from). It picks the anchor and the default elevation.

    "given": `side`, e.g. the stroke the coach was told. "recorded": the pipeline's label
    (swing["stroke"] or swing["side"]). A machine-guessed label (metadata.strokeSource in
    AUTO_STROKE_SOURCES: the pipeline's classifier or the coach) is checked against the skeleton
    first, and the skeleton wins when they disagree: AUTO_LABEL_OVERRIDDEN. "measured": no label,
    so the skeleton (_measured_stroke). "assumed": nothing works, so it is a forehand, labelled
    ASSUMED. Never a silent default. A stroke a caller already measured and wrote back
    (strokeSource in MEASURED_STROKE_SOURCES, e.g. pipeline/live.py before coaching) is kept.

    Why the skeleton can beat a guessed label: the coach's and the pipeline's classifiers measure
    along the shoulder line, which turns side-on at contact, and both call the labelled IMG_2116
    backhand a forehand. Manual labels, side= and files without strokeSource are trusted as is.
    """
    if side is not None:
        if side not in SIDES:
            raise ValueError(f"side must be 'forehand' or 'backhand', got {side!r}")
        return side, "given"
    label = next((swing[key] for key in ("stroke", "side") if swing.get(key) in SIDES), None)
    meta = swing.get("metadata")
    source = meta.get("strokeSource") if isinstance(meta, dict) else None
    if label is not None and source in MEASURED_STROKE_SOURCES:
        return label, source  # already measured from this skeleton (decide_stroke) before coaching
    auto = source in AUTO_STROKE_SOURCES
    if label is not None and not auto:
        return label, "recorded"
    measured = _measured_stroke(P, hand, contact)
    if label is not None:
        return (measured, AUTO_LABEL_OVERRIDDEN) if measured not in (None, label) else (label, "recorded")
    return (measured, "measured") if measured is not None else ("forehand", "assumed")


def decide_stroke(swing: dict, hand: str | None = None) -> tuple[str, str]:
    """swing_stroke() for a whole swing dict: the stroke compare() will use, and its source.

    For callers that must agree with compare() before it runs. pipeline/live.py coaches with
    this stroke, so the advice, the ghost fix and the ball path all use one stroke.
    """
    P = to_array(swing)
    hand = hand or swing_hand(swing, P)
    contact, _ = ball_contact(swing, P, hand)
    return swing_stroke(swing, P, hand, contact)


def drive_spot(hand: str, side: str) -> tuple[float, float]:
    """ASSUMED anchor (x, z): where the racket meets the ball on the court floor.

    DRIVE_SPOT_RIGHT_HANDED for the stroke, mirrored across the court for a left-hander:
    right-handed forehand (5.4, 7.0), backhand (2.0, 7.0); left-handed (1.0, 7.0) and (4.4, 7.0).
    """
    x, z = DRIVE_SPOT_RIGHT_HANDED[side]
    return (x if hand == "R" else round(COURT_WIDTH_M - x, 3), z)


def estimate_azimuth(Pc: np.ndarray, hand: str, contact: int) -> dict:
    """Aim of the shot, degrees: 0 = straight at the front wall, + = towards the right wall.

    `rawValue` is the floor-plane direction of the hitting wrist's velocity at contact, in court
    axes (Pc). Within AZIMUTH_TRUST_DEG of straight it is the ESTIMATE, clamped to
    +-AZIMUTH_LIMIT_DEG (`clamped` says when). Further off, or if it can't be measured, the wrist
    is moving sideways rather than along the shot, so the aim is ASSUMED straight (0).
    """
    v = np.gradient(Pc[:, ARM[hand]["wr"]], axis=0)[contact] if len(Pc) >= 2 else np.full(3, np.nan)
    raw = None
    if np.isfinite(v).all() and math.hypot(v[0], v[2]) > 1e-12:
        raw = math.degrees(math.atan2(v[0], -v[2]))  # towards the front wall is -z
    lim = AZIMUTH_LIMIT_DEG
    if raw is not None and abs(raw) <= AZIMUTH_TRUST_DEG:
        return {
            "value": round(min(max(raw, -lim), lim), 1), "unit": "deg",
            "estimate": True, "label": "ESTIMATE",
            "method": "floor-plane direction of the hitting wrist's velocity at contact, court axes",
            "clamped": not -lim <= raw <= lim, "rawValue": round(raw, 1),
        }
    why = ("the hitting wrist's direction at contact can't be measured" if raw is None else
           f"the hitting wrist moves {abs(raw):.0f} deg off straight at contact (more than "
           f"{AZIMUTH_TRUST_DEG:g}), sideways rather than along the shot")
    return {
        "value": 0.0, "unit": "deg",
        "estimate": False, "label": "ASSUMED",
        "method": f"assumed straight: {why}",
        "clamped": False, "rawValue": None if raw is None else round(raw, 1),
    }


def racket_line_heading(Pc: np.ndarray, hand: str, contact: int) -> float | None:
    """Floor-plane heading of the racket line at contact, degrees: 0 = at the front wall, + = towards the right wall.

    The racket line runs from the hitting elbow along the forearm to the racket head
    (skeleton.racket_head: the racket continues the forearm until racket tracking exists), in
    court axes (Pc). A turn of the trunk about the vertical turns it by exactly that angle; an
    elbow fix turns the forearm. None when it can't be measured: a joint is missing, or the
    forearm is within RACKET_LINE_MIN_FLOOR_M of vertical on the floor, where pose noise would
    swing the heading arbitrarily.
    """
    j = ARM[hand]
    d = Pc[contact, j["wr"]] - Pc[contact, j["el"]]
    if not np.isfinite(d).all() or math.hypot(d[0], d[2]) < RACKET_LINE_MIN_FLOOR_M:
        return None
    return math.degrees(math.atan2(d[0], -d[2]))  # towards the front wall is -z


def ghost_azimuth(you_aim: dict, Pc_you: np.ndarray, Pc_ghost: np.ndarray, hand: str, contact: int) -> dict:
    """The ghost's aim: yours (estimate_azimuth), turned by the fix's turn of the racket line at contact.

    The ball leaves square to the racket face, and the face turns with the trunk and forearm
    that carry it. So the ghost's aim is your aim (measured from your wrist; it matches the
    video) plus racket_line_heading(ghost) - racket_line_heading(you), clamped to
    +-AZIMUTH_LIMIT_DEG, with your aim's label. A trunk less open at contact sends the ball
    more down the line; a more open one sends it more across the court.

    The turn_shoulders edits shrink or grow the backswing and fade to zero at contact (unless a
    stated intent holds a turn there: contact_turn_for_intent), close_stance turns only the
    legs, and hold_wrist_cock bends the hand (the racket line ignores the wrist, as the racket
    speed estimate does): all leave the aim as yours. The elbow fixes turn the forearm, so they
    turn the aim. This replaces the ghost's own wrist direction, which picked up where the edit
    blends back into your swing at contact. If the racket line can't be measured on either
    swing (racket_line_heading is None), the fix's turn is unmeasured and the ghost keeps your aim.
    """
    you_line, ghost_line = racket_line_heading(Pc_you, hand, contact), racket_line_heading(Pc_ghost, hand, contact)
    if you_line is None or ghost_line is None:
        # No reliable racket line (missing joint or a near-vertical forearm): the fix's turn is
        # unmeasured, so the ghost keeps your aim rather than a guessed one.
        return {
            **{k: you_aim[k] for k in ("value", "unit", "estimate", "label", "clamped", "rawValue") if k in you_aim},
            "method": f"your aim ({you_aim['value']:g} deg, {you_aim['label']}): the racket line at contact "
                      "can't be measured (forearm missing or too close to vertical), so the fix's turn of "
                      "it is unmeasured",
            "youDeg": you_aim["value"], "racketLineTurnDeg": None,
        }
    turn = (ghost_line - you_line + 180.0) % 360.0 - 180.0
    raw = you_aim["value"] + turn
    shown = round(turn, 1) + 0.0  # + 0.0 so a rounding speck never reads "-0.0"
    lim = AZIMUTH_LIMIT_DEG
    return {
        "value": round(min(max(raw, -lim), lim), 1) + 0.0, "unit": "deg",
        "estimate": you_aim["estimate"], "label": you_aim["label"],
        "method": f"your aim ({you_aim['value']:g} deg, {you_aim['label']}) turned by the fix's change in the "
                  f"racket line (elbow -> racket head) at contact, {shown:+.1f} deg",
        "clamped": not -lim <= raw <= lim, "rawValue": round(raw, 1),
        "youDeg": you_aim["value"], "racketLineTurnDeg": shown,
    }


def contact_turn_for_intent(P: np.ndarray, Pc: np.ndarray, hand: str, contact: int, you_aim: dict,
                            intent: str, fix_name: str, amount: float, *, fix_turn_deg: float | None = 0.0,
                            stated: bool = True, arm_guessed: str | None = None) -> tuple[dict, float]:
    """(assumptions.aim, contact_turn_deg for apply_fix): the smallest shoulder turn held at contact
    that puts the ghost's aim on the intended line (INTENT_AIMS).

    The ghost's aim is yours plus the racket line's turn at contact (ghost_azimuth), and turning
    the trunk about the vertical turns the racket line by exactly that angle. So the turn needed
    is the intent's aim minus the aim the fix alone gives (yours + fix_turn_deg, the fix's own
    turn of the racket line: 0 for the shoulder and stance fixes, which leave contact alone): no
    search, and nothing about the result is set by hand (the ghost's aim is still measured from
    its pose). Capped at the fix's size for a shoulder fix (AIM_FIXES), else AIM_HOLD_LIMIT_DEG.
    For a zero amount, an aim that is only ASSUMED (no measured aim to turn), a guessed hitting arm
    (arm_guessed), a racket line that can't be measured (fix_turn_deg None too) or shoulders that
    don't turn, nothing is held
    (contact_turn_deg 0) and `why` says so.

    stated: the player said this is the shot they meant (label STATED); False when it is the
    target every ghost aims (TARGET_INTENT, label TARGET).

    arm_guessed: why the hitting elbow or wrist at contact is guessed (guessed_arm_at_contact),
        else None. The racket line runs through them, so a guessed arm holds nothing.

    contactTurnDeg is in the shoulders' sense (- = turned less far through at contact, i.e. less
    open), as apply_fix takes it; headingTurnDeg is the same turn on the court (+ = towards the
    right wall). Which matches which follows the way the shoulders turn from the top of the
    backswing to contact (the coil's sign, as ghost.py measures it).
    """
    target = INTENT_AIMS[intent]
    aim = {"intent": intent, "label": "STATED" if stated else "TARGET", "targetDeg": target, "applied": False}
    coil = 0.0
    why = None
    if float(amount) == 0.0:
        why = "the fix's amount is 0"
    elif not you_aim.get("estimate"):
        why = "your aim is assumed, not measured, so there is no measured aim to turn onto the line"
    elif arm_guessed:
        why = f"the hitting arm at contact is guessed ({arm_guessed}), so its racket line can't be aimed"
    elif racket_line_heading(Pc, hand, contact) is None or fix_turn_deg is None:
        why = "the racket line at contact can't be measured, so a turn of it can't be aimed"
    else:
        _, coil = shoulder_coil(shoulder_yaw(P, up_vector(P)), contact)
        if abs(coil) < 1.0:
            why = "the shoulders don't turn before contact, so there is no turn to hold"
    if why:
        return {**aim, "why": why}, 0.0
    s = float(np.sign(coil))
    fix_turn = float(fix_turn_deg or 0.0)
    need = target - (you_aim["value"] + fix_turn)  # heading turn that puts the fix's aim on the target
    shoulder_fix = fix_name in AIM_FIXES
    cap = abs(float(amount)) if shoulder_fix else AIM_HOLD_LIMIT_DEG
    contact_turn = float(np.clip(s * need, -cap, cap))  # heading turn = s x contact turn (ghost.py)
    heading_turn = s * contact_turn
    start = f"your aim ({you_aim['value']:g} deg)" if fix_turn == 0 else \
        f"the aim the fix alone gives ({you_aim['value'] + fix_turn:.1f} deg: yours {fix_turn:+.1f})"
    cap_by = "the fix's size" if shoulder_fix else "the hold limit"
    return {
        **aim, "applied": True,
        "contactTurnDeg": round(contact_turn, 1) + 0.0, "headingTurnDeg": round(heading_turn, 1) + 0.0,
        "capDeg": cap, "capBy": cap_by, "capped": abs(need) > cap,
        "method": f"smallest shoulder turn held at contact that turns the racket line from {start} to the "
                  f"{intent} line ({target:g} deg), capped at {cap_by} ({cap:g} deg); the ghost's aim is then "
                  "measured from its pose",
    }, contact_turn


def _intent_note(aim: dict) -> str:
    """The sentence /ghost shows under the PREDICTED ball (assumptions.note) for an applied intent."""
    turn = aim["contactTurnDeg"]
    why = "the player's stated intent" if aim["label"] == "STATED" else "every ghost's target"
    if turn == 0:
        return f" Aiming: {aim['intent']} ({why}). The drive already goes straight, so nothing is held at contact."
    text = (f" Aiming: {aim['intent']} ({why}). Smallest change that sends your drive "
            f"straight: {'−' if turn < 0 else '+'}{abs(turn):g}° of shoulder turn at contact.")
    if aim["capped"]:
        whose = "the fix's " if aim["capBy"] == "the fix's size" else ""
        text += f" Capped at {whose}{aim['capDeg']:g}°, so the ghost's aim stops short of straight."
    return text


def _court_swing(swing: dict, Pc: np.ndarray) -> dict:
    """Copy of `swing` with its points in court coordinates, labelled as such."""
    out = from_array(swing, Pc)
    out["coordinateSystem"] = "court"
    meta = out.get("metadata")
    if isinstance(meta, dict) and "coordinateSystem" in meta:
        meta["coordinateSystem"] = "court"  # the pipeline's "hip-centred-y-up-metres" no longer holds
    return out


def _in_court_frame(swing: dict) -> bool:
    meta = swing.get("metadata")
    in_meta = isinstance(meta, dict) and meta.get("coordinateSystem") == "court"
    return swing.get("coordinateSystem") == "court" or in_meta


def _on_court(swing: dict, fps_real, hand: str, contact: int, shift: np.ndarray,
              elevation_deg: float, racket: dict, azimuth: dict | None = None,
              aim: dict | None = None, back_m: float = 0.0) -> tuple[dict, dict]:
    """One swing: metrics, the swing on the court, its PREDICTED ball (from `racket`), and its launch.

    `shift` is the player's court_shift, so you and the ghost stand in exactly the same place.
    `azimuth` is the aim to use (the ghost's, from ghost_azimuth); None measures it from this
    swing's wrist (estimate_azimuth), as for yours.
    Metrics are measured on the swing as given; they don't depend on where it stands.
    `aim`: the wrist-sensor aim (wrist_face.face_aim) to use instead of the wrist's direction,
    which is then kept only as `cameraAim`, a cross-check. None (no sensor data) = as before.
    `back_m`: the ball leaves this much further back from the front wall (+z) than the racket head
    at contact (the straight-drive ghost's later contact, LATER_CONTACT_BACK_M). 0 = at the head.
    """
    m = measure(swing, fps_real, hand)
    metrics = {k: _num(m[k]) for k in METRICS}
    Pc = court_axes(to_array(swing)) + shift
    point = [round(float(c), 3) for c in racket_head(Pc, hand)[contact] + np.array([0.0, 0.0, back_m])]
    if not 0 < point[1] < 3:
        raise ValueError(f"the racket head at contact is {point[1]:.2f} m above the floor; "
                         "the ball model needs 0 to 3 m")
    if azimuth is None:
        azimuth = estimate_azimuth(Pc, hand, contact)
    if aim is not None:
        azimuth = {**aim, "cameraAim": {"value": azimuth["value"], "label": azimuth["label"]}}
    ball = predict_ball_path(racket["value"], elevation_deg, azimuth["value"], tuple(point))
    side = {"swing": _court_swing(swing, Pc), "metrics": metrics, "racketSpeed": racket, "ball": ball}
    return side, {"point": point, "azimuth": azimuth}


def guessed_metrics(swing: dict, hand: str, contact: int, fps: float) -> dict[str, str]:
    """{compare metric: why} for every METRICS entry that reads a joint the pipeline guessed.

    Same rule as the coach (coach.measure_extra): a joint listed in metadata.approximatedJoints,
    marked true in frames[i].filled on a frame the metric reads, or below 0.5 visibility at
    contact. stance_open_deg here is the hitting-direction angle, so it is guessed whenever
    the hitting wrist around contact is (the coach may judge stance from the feet instead,
    but that is a different number). Files without flags give {} (absence means unknown).
    """
    from coach.measure_extra import _guessed_why, _per_joint, guessed_measurements

    out = {k: why for k, why in guessed_measurements(swing, hand, contact, fps).items() if k in METRICS}
    frames = swing.get("frames") or []
    if frames and "wrist_at_contact_deg" in METRICS:
        c = int(np.clip(contact, 0, len(frames) - 1))
        listed = set((swing.get("metadata") or {}).get("approximatedJoints") or [])
        vis = _per_joint(frames[c], "visibility")
        a = ARM[hand]
        why = next((w for j in (a["el"], a["wr"], a["index"])
                    if (w := _guessed_why(j, listed, frames, range(c, c + 1), vis))), None)
        if why:
            out["wrist_at_contact_deg"] = why
        # Racket speed (and so the PREDICTED ball speed) reads the hitting wrist's speed over
        # the frames around contact and the elbow->wrist forearm: if either is guessed there,
        # the numbers are still shown but flagged as not measured.
        span = range(max(0, c - 2), min(len(frames), c + 3))
        why = next((w for j in (a["wr"], a["el"]) if (w := _guessed_why(j, listed, frames, span, vis))), None)
        if why:
            reason = f"racket speed reads the hitting wrist and elbow around contact; {why}"
            out["racket_speed"] = reason
            out["ball_speed"] = reason
    return out



def guessed_arm_at_contact(swing: dict, hand: str, contact: int) -> str | None:
    """Why the hitting elbow or wrist is guessed at the contact frame, else None.

    guessed_metrics' rule (coach.measure_extra): listed in metadata.approximatedJoints, marked
    true in frames[contact].filled, or below 0.5 visibility at contact. The racket line that an
    aiming hold turns runs from the elbow through the wrist, so neither may be guessed.
    """
    from coach.measure_extra import _guessed_why, _per_joint

    frames = swing.get("frames") or []
    if not frames:
        return None
    c = int(np.clip(contact, 0, len(frames) - 1))
    listed = set((swing.get("metadata") or {}).get("approximatedJoints") or [])
    vis = _per_joint(frames[c], "visibility")
    a = ARM[hand]
    return next((w for j in (a["el"], a["wr"]) if (w := _guessed_why(j, listed, frames, range(c, c + 1), vis))), None)

# Fix -> the measurement it edits, and the joint that measurement needs around contact.
FIX_TARGETS = {
    "straighten_elbow": ("elbow_at_contact_deg", "elbow"),
    "bend_elbow": ("elbow_at_contact_deg", "elbow"),
    "hold_wrist_cock": ("wrist_release_ms", "wrist"),
    "close_stance": ("stance_open_deg", "wrist"),  # stance is measured against the wrist's direction
    "turn_shoulders_more": ("shoulder_turn_deg", "shoulder"),
    "turn_shoulders_less": ("shoulder_turn_deg", "shoulder"),
}


class GuessedFixError(ValueError):
    """The fix edits a measurement the camera couldn't make on this swing."""


def _drop_guessed(side: dict, guessed: dict[str, str]) -> None:
    for k in guessed:
        side["metrics"].pop(k, None)


def _change(a, b, nd: int = 1) -> dict:
    return {"you": a, "ghost": b, "change": None if a is None or b is None else round(b - a, nd)}


def _landing_depth(ball: dict) -> float | None:
    return None if ball["landing"] is None else round(ball["landing"][1], 2)


def _fmt(x, unit: str = "") -> str:
    return "n/a" if x is None else f"{x:g}{unit}"


def _delta(you: dict, ghost: dict) -> dict:
    metrics = {}
    for k, (unit, _) in METRICS.items():
        if k in you["metrics"] and k in ghost["metrics"]:
            metrics[k] = {**_change(you["metrics"][k], ghost["metrics"][k]), "unit": unit}
    yb, gb = you["ball"], ghost["ball"]
    ball = {
        "predicted": True,
        "label": "PREDICTED",
        "outcome": {"you": yb["outcome"], "ghost": gb["outcome"], "changed": yb["outcome"] != gb["outcome"]},
        "speedKmh": _change(yb["speedKmh"], gb["speedKmh"]),
        "frontWallHeightM": _change(_num(yb["frontWallHeightM"], 2), _num(gb["frontWallHeightM"], 2), 2),
        "landingDepthM": _change(_landing_depth(yb), _landing_depth(gb), 2),
        "landsBehindShortLine": {"you": yb["landsBehindShortLine"], "ghost": gb["landsBehindShortLine"]},
    }
    summary = []
    for k, (unit, words) in METRICS.items():
        d = metrics.get(k)
        if d and d["change"]:
            summary.append(f"{words} {_fmt(d['you'])} -> {_fmt(d['ghost'])} {unit} ({d['change']:+g})")
    depth = ball["landingDepthM"]
    summary.append(
        f"PREDICTED ball {ball['outcome']['you']} -> {ball['outcome']['ghost']}, "
        f"{_fmt(ball['speedKmh']['you'])} -> {_fmt(ball['speedKmh']['ghost'])} km/h, "
        f"lands {_fmt(depth['you'], ' m')} -> {_fmt(depth['ghost'], ' m')} from the front wall"
    )
    return {"metrics": metrics, "ball": ball, "summary": summary}


# fix.explain: what the ghost changes, in words. {a} is the fix's amount.
FIX_WORDS = {
    "straighten_elbow": "straightens its elbow {a:g}° at contact",
    "bend_elbow": "bends its elbow {a:g}° more at contact",
    "turn_shoulders_more": "turns its shoulders {a:g}° more in the backswing",
    "turn_shoulders_less": "turns its shoulders {a:g}° less in the backswing",
    "hold_wrist_cock": "holds its wrist cock {a:g} ms longer",
    "close_stance": "closes its stance {a:g}°",
}
OUTCOME_WORDS = {"tin": "hits the tin", "out": "goes out", "down": "never reaches the front wall"}


def _line_turn(Pc_you: np.ndarray, Pc_ghost: np.ndarray, hand: str, contact: int) -> float | None:
    """The fix's turn of the racket line at contact, degrees (ghost minus you); None if unmeasured."""
    a, b = racket_line_heading(Pc_you, hand, contact), racket_line_heading(Pc_ghost, hand, contact)
    return None if a is None or b is None else (b - a + 180.0) % 360.0 - 180.0


def _near_wall(x: float) -> str:
    return "right" if x > COURT_WIDTH_M / 2 else "left"


def _aim_words(az: float, x: float) -> str:
    """'straight', '13.5° across court' or '4° towards the right wall', from a launch at x."""
    if abs(az) < 0.5:
        return "straight"
    towards = "right" if az > 0 else "left"
    return f"{abs(az):g}° towards the {towards} wall" if towards == _near_wall(x) else f"{abs(az):g}° across court"


def _path_words(az: float, x: float) -> str:
    if abs(az) < 0.5:
        return "straight down the middle" if abs(x - COURT_WIDTH_M / 2) < 1.0 else f"straight down the {_near_wall(x)} wall"
    towards = "right" if az > 0 else "left"
    return f"towards the {towards} wall" if towards == _near_wall(x) else "cross-court"


def _ball_words(ball: dict) -> str:
    if ball["outcome"] in OUTCOME_WORDS and ball["outcome"] != "out":
        return OUTCOME_WORDS[ball["outcome"]]
    parts = [] if ball["frontWallHeightM"] is None else [f"front wall {ball['frontWallHeightM']:.2f} m high"]
    if ball["outcome"] == "out":
        parts.append("out")
    elif ball["landing"] is not None:
        parts.append(f"lands {ball['landing'][1]:.2f} m from the front wall")
    return ", ".join(parts)


def explain_fix(fix_name: str, amount: float, stroke: str, you: dict, ghost: dict, you_launch: dict,
                ghost_launch: dict, aim: dict | None, elevation: float, spot_measured: bool,
                racket_note: dict) -> str:
    """fix.explain: the chain from body to ball for this fix, in plain words.

    Quotes only numbers compare() measured or solved, each with its label: the fix's measurement
    (measured), the aims (ESTIMATE or ASSUMED), the held turn (solved), the PREDICTED balls, and
    the ASSUMED launch angle and spot. The coach's own wording is never touched.
    """
    you_az, ghost_az = you_launch["azimuth"], ghost_launch["azimuth"]
    x_you, x_ghost = you_launch["point"][0], ghost_launch["point"][0]
    if fix_name in FIX_TARGETS:
        metric = FIX_TARGETS[fix_name][0]
        unit, words = METRICS[metric]
        u = "°" if unit == "deg" else f" {unit}"
        mine, theirs = you["metrics"].get(metric), ghost["metrics"].get(metric)
        body = f"Your {words} was {mine:g}{u} (measured)" if mine is not None else f"Your {words} couldn't be measured"
    else:  # firm_wrist without a roll the coach can judge: compare allows only amount 0 here
        metric, u, mine, theirs = None, "", None, None
        body = "Your forearm roll wasn't measured (no wrist-sensor roll the coach can judge)"
    if you_az["label"] == "ASSUMED":
        line = "your aim is ASSUMED straight (the wrist moves sideways at contact)"
    else:
        line = f"your racket line pointed {_aim_words(you_az['value'], x_you)} at contact ({you_az['label']}, from the wrist)"
    text = (f"{body}, and {line}, so your PREDICTED ball goes {_path_words(you_az['value'], x_you)}: "
            f"{_ball_words(you['ball'])}.")
    if amount == 0:
        text += " The ghost is your swing unchanged."
    else:
        change = FIX_WORDS[fix_name].format(a=abs(amount))
        turn = aim.get("contactTurnDeg", 0.0) if aim and aim.get("applied") else 0.0
        if mine is not None and theirs is not None:
            # The stance is measured against the shot line, which the held turn moves as well.
            relative = " against the straight shot line" if metric == "stance_open_deg" and turn else ""
            change += f" ({mine:g}{u} → {theirs:g}{u}{relative})"
        hold = f" and holds {abs(turn):g}° {'less' if turn < 0 else 'more'} shoulder turn at contact" if turn else ""
        points = ("its aim stays ASSUMED straight" if ghost_az["label"] == "ASSUMED" else
                  f"which points its racket line {_aim_words(ghost_az['value'], x_ghost)}")
        text += (f" The ghost {change}{hold}, {points}, so its PREDICTED ball goes "
                 f"{_path_words(ghost_az['value'], x_ghost)}: {_ball_words(ghost['ball'])}.")
    text += (f" Ball speed {you['ball']['speedKmh']:g} → {ghost['ball']['speedKmh']:g} km/h, {racket_note['label']}."
             f" ASSUMED: the {elevation:g}° launch angle{'' if spot_measured else ' and the spot on court'}.")
    if spot_measured:
        text += " The spot on court is MEASURED from the video."
    return text


def _face_words(face_deg: float, cross: str) -> str:
    return "square" if face_deg == 0 else f"{face_deg:g}° open, {cross} (cross-court)"


def explain_face_fix(fix_name: str, amount: float, stroke: str, you: dict, ghost: dict, you_launch: dict,
                     ghost_launch: dict, face: dict, elevation: float, spot_measured: bool,
                     racket_note: dict) -> str:
    """fix.explain when the racket face aims both balls (assumptions.face applied): the chain from
    the forearm roll to the ball. Same rules as explain_fix: only numbers compare() measured or
    computed, each with its label; the face model is ASSUMED, the balls PREDICTED, mock data MOCK."""
    src = "MOCK sensor data" if face["mock"] else "measured by the wrist sensor"
    you_az, ghost_az = you_launch["azimuth"], ghost_launch["azimuth"]
    x_you, x_ghost = you_launch["point"][0], ghost_launch["point"][0]
    roll, g_roll = face["you"]["rollDeg"], face["ghost"]["rollDeg"]
    text = (f"Your forearm rolled {roll:g}° through contact ({src}). ASSUMED: the racket face turns "
            f"{face['facePerRollDeg']:g}° per degree of roll above the {stroke}'s good median "
            f"({face['goodRollDeg']:g}°), so your face was {_face_words(face['you']['faceDeg'], face['crossCourt'])} "
            f"and your PREDICTED ball goes {_path_words(you_az['value'], x_you)}: {_ball_words(you['ball'])}.")
    if amount == 0:
        text += " The ghost is your swing unchanged."
    else:
        if fix_name == "firm_wrist":
            change = f"rolls its forearm {abs(amount):g}° less through contact ({roll:g}° → {g_roll:g}°)"
        else:
            metric = FIX_TARGETS[fix_name][0]
            unit, _ = METRICS[metric]
            u = "°" if unit == "deg" else f" {unit}"
            mine, theirs = you["metrics"].get(metric), ghost["metrics"].get(metric)
            change = FIX_WORDS[fix_name].format(a=abs(amount))
            if mine is not None and theirs is not None:
                change += f" ({mine:g}{u} → {theirs:g}{u})"
            change += " and keeps your forearm roll"
        text += (f" The ghost {change}, so its face is {_face_words(face['ghost']['faceDeg'], face['crossCourt'])}"
                 f" and its PREDICTED ball goes {_path_words(ghost_az['value'], x_ghost)}: {_ball_words(ghost['ball'])}.")
    text += (f" Ball speed {you['ball']['speedKmh']:g} → {ghost['ball']['speedKmh']:g} km/h, {racket_note['label']}."
             f" ASSUMED: the {elevation:g}° launch angle{'' if spot_measured else ' and the spot on court'}.")
    if spot_measured:
        text += " The spot on court is MEASURED from the video."
    return text


def _validation(swing: dict, you_ball: dict, you_az: dict, tracked: dict) -> dict | None:
    """`validation`: your PREDICTED ball next to the real one tracked in the clip (validate_ball).

    predicted/tracked are front-wall heights (m); error_m and error_deg are tracked minus
    predicted. None when your PREDICTED ball never reaches the front wall (nothing to compare).
    """
    if not isinstance(tracked, dict) or tracked.get("method") not in ("tracked", "hand-labelled"):
        raise ValueError("tracked must be a physics.validate_ball result with method 'tracked' or 'hand-labelled'")
    if swing.get("id") and tracked.get("swing") and tracked["swing"] != swing["id"]:
        raise ValueError(f"the validation is for swing {tracked['swing']!r}, not {swing['id']!r}")
    real = tracked.get("tracked") or {}
    h, az = (real.get("frontWall") or {}).get("heightM"), real.get("azimuthDeg")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (h, az)):
        raise ValueError("the validation result has no tracked front-wall height and direction")
    pred = you_ball["frontWallHeightM"]
    if pred is None:
        return None
    return {
        "label": "PREDICTED vs tracked",
        "what": "your ball: front-wall height (m) and direction (deg, + = towards the right wall)",
        "predicted": round(pred, 2), "tracked": round(h, 2), "error_m": round(h - pred, 2),
        "predictedAzimuthDeg": you_az["value"], "trackedAzimuthDeg": round(az, 1),
        "error_deg": round(az - you_az["value"], 1),
        "errorSign": "tracked minus predicted",
        "method": tracked["method"],
        "clip": tracked.get("clip"),
    }


def compare(swing: dict, fix_name: str, amount: float, fps_real: float | None = None,
            hand: str | None = None, elevation_deg: float | None = None, *,
            side: str | None = None, intent: str | None | object = _TARGET, spot: dict | None = None,
            tracked: dict | None = None) -> dict:
    """The swing as played next to its ghost (one fix applied), in court coordinates. Never mutates `swing`.

    fix_name: one of physics.ghost.FIXES, e.g. compare(swing, "straighten_elbow", 12).
    amount: the fix's size, 0 or more (0 = your swing unchanged); the fix's name gives the direction.
    fps_real: real capture rate (120 for a 4x slow-mo clip stored at 30 fps). Default: swing["fps"].
    hand: "R" or "L". Default: the hand the pipeline recorded, else whichever wrist moves fastest.
    elevation_deg: the ASSUMED launch angle for this swing's two PREDICTED ball paths.
        Default: DEFAULT_ELEVATION_DEG for the stroke (12 forehand, 3 backhand).
    side: "forehand" or "backhand", e.g. the stroke the coach was told. Default: the pipeline's
        label, else measured from the skeleton, else forehand labelled ASSUMED (swing_stroke).
    intent: the shot the ghost aims, one of INTENT_AIMS ("straight drive"). On top of its fix the
        ghost holds the smallest shoulder turn at contact that sends its PREDICTED ball on that
        line (contact_turn_for_intent; assumptions.aim and the note say so). Default: every ghost
        aims TARGET_INTENT (label TARGET); passed in, it is the player's STATED intent; None
        holds nothing (the fix alone).
    spot: where the player hit from, MEASURED from the video (physics.court_spot.measure_spot:
        {"x", "z", "label": "MEASURED", "method", ...}); your racket head at contact sits over it
        instead of the ASSUMED drive spot. Default: the ASSUMED drive spot (a live upload has no
        court lines to measure from).
    tracked: a physics.validate_ball result for this swing (the real ball tracked in its clip);
        adds `validation`: your PREDICTED front-wall height and direction next to the tracked
        ones, errors tracked minus predicted. Default: no validation.
    swing: a pipeline swing (hip-centred, facing +z), not a compare() output.
    """
    if fix_name not in FIXES:
        uses = [fix for fix, (edit, _) in FIXES.items() if edit == fix_name]
        tip = f" ({fix_name!r} is an edit; the fixes that use it are {', '.join(map(repr, uses))})" if uses else ""
        raise ValueError(f"unknown fix {fix_name!r}{tip}; known fixes: {', '.join(FIXES)}")
    if float(amount) < 0:
        # The fix's name says which way it goes (straighten, turn less...): a negative amount would
        # reverse it while fix.explain and the legend still name it.
        raise ValueError("amount must be 0 or more")
    if hand not in (None, "R", "L"):
        raise ValueError(f"hand must be 'R' or 'L', got {hand!r}")
    stated = intent is not _TARGET
    intent = TARGET_INTENT if intent is _TARGET else intent
    if intent is not None and intent not in INTENT_AIMS:
        raise ValueError(f"intent must be one of {', '.join(map(repr, INTENT_AIMS))}, got {intent!r}")
    if not swing.get("frames"):
        raise ValueError("swing has no frames")
    if _in_court_frame(swing):
        raise ValueError("this swing is already in court coordinates (a compare() output); pass the pipeline swing")
    P = to_array(swing)
    hand = hand or swing_hand(swing, P)
    contact, contact_method = ball_contact(swing, P, hand)
    stroke, stroke_source = swing_stroke(swing, P, hand, contact, side)
    spot = _measured_spot(spot)
    anchor = (spot["x"], spot["z"]) if spot else drive_spot(hand, stroke)
    given_elevation = elevation_deg is not None
    elevation = float(elevation_deg) if given_elevation else DEFAULT_ELEVATION_DEG[stroke]
    shift = court_shift(P, hand, contact, anchor)  # from YOUR racket head; the ghost reuses it
    played = {**swing, "contactFrame": contact}
    # Never show a number read from a guessed joint, and never edit one: refuse a fix whose
    # target measurement is guessed, and leave guessed metrics out (listed in notMeasured).
    guessed = guessed_metrics(played, hand, contact, real_fps(swing, fps_real))
    target = FIX_TARGETS.get(fix_name)
    if target and target[0] in guessed and float(amount) != 0.0:  # amount 0 = "unchanged", always allowed
        side_name = "right" if hand == "R" else "left"
        raise GuessedFixError(f"Not available on this swing: the camera couldn't see the {side_name} {target[1]} "
                              "around contact (guessed joints), so a ghost of this fix would edit a guess.")
    edit, sign = FIXES[fix_name]
    roll, aim_skip = aim_roll(swing)
    if edit == "wrist_roll" and roll is None and float(amount) != 0.0:
        raise GuessedFixError("Not available on this swing: a firm-wrist ghost needs the forearm roll from a "
                              + (f"wrist sensor timed as the coach judges it. {aim_skip}" if aim_skip else
                                 "wrist sensor, and this swing has no usable wrist-sensor data."))
    Pc = court_axes(P)
    you_aim = estimate_azimuth(Pc + shift, hand, contact)  # as _on_court measures it
    ghost_swing = apply_fix(played, fix_name, amount, fps_real, hand)  # the fix alone
    aim, contact_turn = None, 0.0
    if intent is not None and roll is not None:
        # The racket face aims both balls (below), so no shoulder turn is held for the line.
        aim = {"intent": intent, "label": "STATED" if stated else "TARGET", "targetDeg": INTENT_AIMS[intent],
               "applied": False, "why": FACE_AIMS_WHY}
    elif intent is not None:
        aim, contact_turn = contact_turn_for_intent(
            P, Pc, hand, contact, you_aim, intent, fix_name, amount, stated=stated,
            arm_guessed=guessed_arm_at_contact(played, hand, contact),
            fix_turn_deg=_line_turn(Pc, court_axes(to_array(ghost_swing)), hand, contact))
    if contact_turn:
        ghost_swing = apply_fix(played, fix_name, amount, fps_real, hand, contact_turn_deg=contact_turn)
    ghost_swing.pop("wrist", None)  # your forearm phone's data isn't the ghost's: nothing may coach it

    # Wrist sensor: both balls are aimed by the racket face from the forearm roll (wrist_face.py).
    # Only the wrist_roll edit (firm_wrist) changes the ghost's roll. No sensor data: as before.
    you_face = ghost_face = face = None
    if roll is not None:
        good = good_roll(stroke, roll["mock"])
        ghost_roll = max(0.0, roll["roll"] + sign * float(amount)) if edit == "wrist_roll" else roll["roll"]
        you_face = face_aim(roll["roll"], good, anchor[0], roll["mock"])
        ghost_face = face_aim(ghost_roll, good, anchor[0], roll["mock"])
        face = {
            "applied": True, "label": you_face["label"], "assumed": True, "mock": roll["mock"],
            "facePerRollDeg": FACE_PER_ROLL_DEG, "capDeg": FACE_CAP_DEG, "goodRollDeg": good,
            "intent": {"value": INTENT, "azimuthDeg": INTENT_AZIMUTH_DEG, "label": "STATED"},
            "crossCourt": f"towards the {cross_court_wall(anchor[0])} wall",
            "you": {"rollDeg": you_face["rollDeg"], "faceDeg": you_face["faceDeg"]},
            "ghost": {"rollDeg": ghost_face["rollDeg"], "faceDeg": ghost_face["faceDeg"]},
            "method": (f"ASSUMPTION (not measured): the racket face turns {FACE_PER_ROLL_DEG:g} deg per degree of "
                       f"forearm roll above the {stroke}'s good median ({good:g} deg), capped at {FACE_CAP_DEG:g}, "
                       f"and the ball leaves along the face, from your stated {INTENT}. The roll is "
                       + ("MOCK sensor data." if roll["mock"] else "measured by the wrist sensor.")),
        }

    you_racket, ghost_racket, racket_note = racket_speeds(
        swing, estimate_racket_speed(played, fps_real, hand), estimate_racket_speed(ghost_swing, fps_real, hand))
    you, you_launch = _on_court(played, fps_real, hand, contact, shift, elevation, you_racket, you_aim, you_face)
    ghost_cam = ghost_azimuth(you_aim, Pc, court_axes(to_array(ghost_swing)), hand, contact)
    # A straight-drive ghost that aims (the hold applies) also meets the ball later, further back.
    late = (aim is not None and aim["applied"] and aim["intent"] == TARGET_INTENT and float(amount) != 0.0)
    ghost, ghost_launch = _on_court(ghost_swing, fps_real, hand, contact, shift, elevation, ghost_racket,
                                    ghost_cam, ghost_face, back_m=LATER_CONTACT_BACK_M if late else 0.0)
    if aim_skip:  # a real roll the coach can't judge: the camera's aim, saying why
        for launch in (you_launch, ghost_launch):
            az = launch["azimuth"]
            launch["azimuth"] = {**az, "method": f"{az['method']}. {aim_skip}", "wristRollUsed": False}
        face = {"applied": False, "reason": aim_skip, "contactSource": swing["wrist"].get("contact_source")}
    # The ghost inherits your frames' flags, so the same metrics are left out on both sides.
    _drop_guessed(you, guessed)
    _drop_guessed(ghost, guessed)
    delta = _delta(you, ghost)
    where = ("The launch angle is assumed; the spot on court is measured from the video (court lines "
             "and the hitting-side foot)" if spot else "The launch angle and the spot on court are assumed")
    note = (f"Ball paths are PREDICTED. {where}; racket "
            "speed (from the forearm phone when the swing has usable wrist data, else the video), "
            "racket head and aim are estimated from the wrist and forearm until racket tracking exists.")
    if roll is not None:
        note += face_note(roll["mock"])
    fix = {"id": fix_name, "amount": float(amount), "unit": EDITS[edit]["unit"]}
    if aim is not None and aim["applied"]:
        note += _intent_note(aim)
        fix["aiming"] = aim["intent"]  # for the ghost legend: "turn shoulders less · aiming: straight drive"
    if face is not None and face["applied"]:
        fix["explain"] = explain_face_fix(fix_name, float(amount), stroke, you, ghost, you_launch, ghost_launch,
                                          face, elevation, spot is not None, racket_note)
    else:
        fix["explain"] = explain_fix(fix_name, float(amount), stroke, you, ghost, you_launch, ghost_launch,
                                     aim, elevation, spot is not None, racket_note)
    later = {"applied": late, "backM": LATER_CONTACT_BACK_M if late else 0.0, "label": "ASSUMPTION",
             "method": ("ASSUMPTION (coaching knowledge, not measured): a straight drive is struck later than a "
                        "cross-court, with the ball further back beside the body, so the straight-drive ghost's "
                        f"ball leaves {LATER_CONTACT_BACK_M:g} m further back along the shot line than its racket "
                        "head at contact. Its racket speed and body are unchanged.")}
    if late:
        line = (f"Contact later, ball further back beside the body: the ghost meets the ball "
                f"{LATER_CONTACT_BACK_M:g} m further back along the shot line (ASSUMPTION).")
        fix["explain"] = f"{fix['explain']} {line}" if fix.get("explain") else line
        note += (f" ASSUMPTION: the straight-drive ghost meets the ball later, {LATER_CONTACT_BACK_M:g} m "
                 "further back beside the body.")
    validation = None if tracked is None else _validation(swing, you["ball"], you_launch["azimuth"], tracked)
    out = {
        "fix": fix,
        "hand": hand,
        "contactFrame": contact,
        "contactMethod": contact_method,
        "fpsReal": real_fps(swing, fps_real),
        "coordinateSystem": "court",
        "you": you,
        "ghost": ghost,
        "delta": delta,
        "notMeasured": guessed,
        "assumptions": {
            "laterContact": later,
            "stroke": {"value": stroke, "source": stroke_source, "label": STROKE_LABELS[stroke_source]},
            "anchor": {
                "x": anchor[0], "z": anchor[1], "assumed": True, "label": "ASSUMED",
                "method": f"{stroke} drive spot for a {'right' if hand == 'R' else 'left'}-hander. Your racket "
                          "head at contact sits here; the ghost is moved by exactly the same amount, so the "
                          "bodies overlap.",
            } if not spot else {
                "x": anchor[0], "z": anchor[1], "assumed": False, "label": spot["label"],
                "method": f"{spot['method']}. Your racket head at contact sits here; the ghost is moved by "
                          "exactly the same amount, so the bodies overlap.",
            },
            "launch": {
                "racketHead": f"ESTIMATE: hitting wrist + {RACKET_HEAD_M:g} m along elbow -> wrist, "
                              "at its measured height (no racket tracking yet)",
                "elevation": {
                    "value": elevation, "unit": "deg", "assumed": True, "label": "ASSUMED",
                    "method": "given for this swing" if given_elevation else f"default for a {stroke}",
                },
                "you": you_launch,
                "ghost": ghost_launch,
            },
            "racketSpeed": racket_note,
            "launchElevationDeg": elevation,
            "contactSpot": you_launch["point"],  # kept for app/ghost/compare.ts: your launch point
            **({} if aim is None else {"aim": aim}),
            "note": note,
        },
        **({} if validation is None else {"validation": validation}),
    }
    if face is not None:
        out["assumptions"]["face"] = face
    return out


def _measured_spot(spot: dict | None) -> dict | None:
    """A MEASURED spot from physics.court_spot, checked; None keeps the ASSUMED drive spot."""
    if spot is None:
        return None
    if not isinstance(spot, dict) or spot.get("label") != "MEASURED":
        raise ValueError("spot must be a physics.court_spot result labelled MEASURED")
    x, z = spot.get("x"), spot.get("z")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (x, z)):
        raise ValueError(f"spot needs finite x and z, got {x!r}, {z!r}")
    if not (0.0 <= x <= COURT_WIDTH_M and 0.0 < z <= COURT_LENGTH_M):
        raise ValueError(f"spot ({x}, {z}) m is off the court")
    return {"x": float(x), "z": float(z), "label": "MEASURED", "method": str(spot.get("method") or "measured")}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compare a swing with its ghost: metrics, PREDICTED ball paths and what changed.")
    parser.add_argument("swing", type=Path, help="swing JSON (lib/ghost/types.ts Swing)")
    parser.add_argument("fix", help=f"one of: {', '.join(FIXES)}")
    parser.add_argument("amount", type=float, help="fix size, in the fix's unit (deg or ms)")
    parser.add_argument("--fps-real", type=float, default=None,
                        help="real capture rate, e.g. 120 for 4x slow-mo stored at 30 fps (default: the swing's fps)")
    parser.add_argument("--hand", choices=["R", "L"], default=None, help="hitting hand (default: detected)")
    fh, bh = DEFAULT_ELEVATION_DEG["forehand"], DEFAULT_ELEVATION_DEG["backhand"]
    parser.add_argument("--elevation", type=float, default=None,
                        help=f"assumed launch angle for this swing, degrees up "
                             f"(default: {fh:g} forehand, {bh:g} backhand)")
    parser.add_argument("--side", choices=SIDES, default=None,
                        help="stroke (default: the pipeline's label, else measured, else forehand labelled ASSUMED)")
    parser.add_argument("--intent", choices=list(INTENT_AIMS), default=None,
                        help="the shot the player says they meant (labelled STATED); default: every ghost "
                             f"aims a {TARGET_INTENT} (labelled TARGET)")
    parser.add_argument("--no-aim", action="store_true", help="the fix alone: hold nothing at contact")
    parser.add_argument("--spot-file", type=Path, default=None,
                        help="where the player hit from, MEASURED (physics.court_spot output JSON)")
    parser.add_argument("--validation-file", type=Path, default=None,
                        help="this swing's physics.validate_ball result: adds `validation` (PREDICTED vs tracked)")
    parser.add_argument("--no-swings", action="store_true",
                        help="leave out the two swings' frames so the numbers are easy to read")
    args = parser.parse_args(argv)

    try:
        swing = json.loads(args.swing.read_text())
        swing.setdefault("id", args.swing.stem)
        spot = json.loads(args.spot_file.read_text()) if args.spot_file else None
        tracked = json.loads(args.validation_file.read_text()) if args.validation_file else None
        intent = None if args.no_aim else (args.intent or _TARGET)
        result = compare(swing, args.fix, args.amount, args.fps_real, args.hand, args.elevation, side=args.side,
                         intent=intent, spot=spot, tracked=tracked)
        if args.no_swings:
            for side in ("you", "ghost"):
                del result[side]["swing"]
        text = json.dumps(result, indent=2, allow_nan=False)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        sys.exit(f"compare: {e}")
    print(text)


if __name__ == "__main__":
    main()
