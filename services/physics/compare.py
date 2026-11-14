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
and launch rule apply to both swings, so only the fix changes the ball.

Where the ball model's inputs come from (physics/ball.py):
- Contact: the swing's contactFrame. It is the hit sound when the pipeline's contactMethod is
  "audio-transient", else the pipeline's wrist-speed estimate; `contactMethod` says which.
- Stroke (forehand or backhand) picks the anchor and the default elevation: given, else the
  pipeline's label, else measured from the skeleton (ESTIMATE), else forehand labelled ASSUMED.
  A label the pipeline's classifier or the coach guessed is checked against the skeleton first.
- Launch point: each swing's racket head at contact, height above the lowest foot MEASURED.
  Yours sits over the ASSUMED anchor, the drive spot for the stroke (DRIVE_SPOT_RIGHT_HANDED,
  mirrored for a left-hander). The ghost's is wherever its racket head ends up with your
  placement. The racket head itself is an ESTIMATE until racket tracking exists
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
- Azimuth (aim across the court) is an ESTIMATE: the floor-plane direction of the hitting
  wrist's velocity at contact, in court axes, clamped to +-AZIMUTH_LIMIT_DEG. Only within
  AZIMUTH_TRUST_DEG of straight, as on a drive; further off (a backhand's wrist moves
  sideways) the aim is ASSUMED straight.
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

from physics.ball import COURT_WIDTH_M, DEFAULT_CONTACT, predict_ball_path
from physics.ghost import EDITS, FIXES, apply_fix
from physics.metrics import contact_frame, measure, real_fps
from physics.skeleton import (
    ARM, L_HIP, R_HIP, RACKET_HEAD_M, court_axes, court_shift, from_array, mid, racket_head, speed, swing_hand,
    to_array,
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
              elevation_deg: float, racket: dict) -> tuple[dict, dict]:
    """One swing: metrics, the swing on the court, its PREDICTED ball (from `racket`), and its launch.

    `shift` is the player's court_shift, so you and the ghost stand in exactly the same place.
    Metrics are measured on the swing as given; they don't depend on where it stands.
    """
    m = measure(swing, fps_real, hand)
    metrics = {k: _num(m[k]) for k in METRICS}
    Pc = court_axes(to_array(swing)) + shift
    point = [round(float(c), 3) for c in racket_head(Pc, hand)[contact]]
    if not 0 < point[1] < 3:
        raise ValueError(f"the racket head at contact is {point[1]:.2f} m above the floor; "
                         "the ball model needs 0 to 3 m")
    azimuth = estimate_azimuth(Pc, hand, contact)
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


def compare(swing: dict, fix_name: str, amount: float, fps_real: float | None = None,
            hand: str | None = None, elevation_deg: float | None = None, *,
            side: str | None = None) -> dict:
    """The swing as played next to its ghost (one fix applied), in court coordinates. Never mutates `swing`.

    fix_name: one of physics.ghost.FIXES, e.g. compare(swing, "straighten_elbow", 12).
    fps_real: real capture rate (120 for a 4x slow-mo clip stored at 30 fps). Default: swing["fps"].
    hand: "R" or "L". Default: the hand the pipeline recorded, else whichever wrist moves fastest.
    elevation_deg: the ASSUMED launch angle for this swing's two PREDICTED ball paths.
        Default: DEFAULT_ELEVATION_DEG for the stroke (12 forehand, 3 backhand).
    side: "forehand" or "backhand", e.g. the stroke the coach was told. Default: the pipeline's
        label, else measured from the skeleton, else forehand labelled ASSUMED (swing_stroke).
    swing: a pipeline swing (hip-centred, facing +z), not a compare() output.
    """
    if fix_name not in FIXES:
        uses = [fix for fix, (edit, _) in FIXES.items() if edit == fix_name]
        tip = f" ({fix_name!r} is an edit; the fixes that use it are {', '.join(map(repr, uses))})" if uses else ""
        raise ValueError(f"unknown fix {fix_name!r}{tip}; known fixes: {', '.join(FIXES)}")
    if hand not in (None, "R", "L"):
        raise ValueError(f"hand must be 'R' or 'L', got {hand!r}")
    if not swing.get("frames"):
        raise ValueError("swing has no frames")
    if _in_court_frame(swing):
        raise ValueError("this swing is already in court coordinates (a compare() output); pass the pipeline swing")
    P = to_array(swing)
    hand = hand or swing_hand(swing, P)
    contact, contact_method = ball_contact(swing, P, hand)
    stroke, stroke_source = swing_stroke(swing, P, hand, contact, side)
    anchor = drive_spot(hand, stroke)
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
    ghost_swing = apply_fix(played, fix_name, amount, fps_real, hand)
    ghost_swing.pop("wrist", None)  # your forearm phone's data isn't the ghost's: nothing may coach it

    you_racket, ghost_racket, racket_note = racket_speeds(
        swing, estimate_racket_speed(played, fps_real, hand), estimate_racket_speed(ghost_swing, fps_real, hand))
    you, you_launch = _on_court(played, fps_real, hand, contact, shift, elevation, you_racket)
    ghost, ghost_launch = _on_court(ghost_swing, fps_real, hand, contact, shift, elevation, ghost_racket)
    # The ghost inherits your frames' flags, so the same metrics are left out on both sides.
    _drop_guessed(you, guessed)
    _drop_guessed(ghost, guessed)
    delta = _delta(you, ghost)
    edit, _ = FIXES[fix_name]
    return {
        "fix": {"id": fix_name, "amount": float(amount), "unit": EDITS[edit]["unit"]},
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
            "stroke": {"value": stroke, "source": stroke_source, "label": STROKE_LABELS[stroke_source]},
            "anchor": {
                "x": anchor[0], "z": anchor[1], "assumed": True, "label": "ASSUMED",
                "method": f"{stroke} drive spot for a {'right' if hand == 'R' else 'left'}-hander. Your racket "
                          "head at contact sits here; the ghost is moved by exactly the same amount, so the "
                          "bodies overlap.",
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
            "note": "Ball paths are PREDICTED. The launch angle and the spot on court are assumed; racket "
                    "speed (from the forearm phone when the swing has usable wrist data, else the video), "
                    "racket head and aim are estimated from the wrist and forearm until racket tracking "
                    "exists.",
        },
    }


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
    parser.add_argument("--no-swings", action="store_true",
                        help="leave out the two swings' frames so the numbers are easy to read")
    args = parser.parse_args(argv)

    try:
        swing = json.loads(args.swing.read_text())
        swing.setdefault("id", args.swing.stem)
        result = compare(swing, args.fix, args.amount, args.fps_real, args.hand, args.elevation, side=args.side)
        if args.no_swings:
            for side in ("you", "ghost"):
                del result[side]["swing"]
        text = json.dumps(result, indent=2, allow_nan=False)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        sys.exit(f"compare: {e}")
    print(text)


if __name__ == "__main__":
    main()
