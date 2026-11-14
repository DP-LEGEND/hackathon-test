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
- Launch point: each swing's racket head at contact, height above the lowest foot MEASURED.
  Yours sits over the ASSUMED anchor: ball.py's forehand drive spot for a right-hander,
  mirrored across the court for a backhand or a left hand. The ghost's is wherever its racket
  head ends up with your placement. The racket head itself is an ESTIMATE until racket
  tracking exists (skeleton.racket_head: wrist + 0.45 m along the forearm).
- Racket speed is an ESTIMATE until racket tracking exists. The forearm and racket are
  treated as one straight lever turning about the elbow, so the racket's sweet spot
  moves (forearm + racket) / forearm times faster than the wrist:
      racket speed = wrist speed x (forearm + RACKET_LEVER_M) / forearm
  It ignores the wrist snap, so the hold_wrist_cock fix doesn't change it.
- Azimuth (aim across the court) is an ESTIMATE: the floor-plane direction of the hitting
  wrist's velocity at contact, in court axes, clamped to +-AZIMUTH_LIMIT_DEG. Only within
  AZIMUTH_TRUST_DEG of straight, as on a drive; further off (a backhand's wrist moves
  sideways) the aim is ASSUMED straight.
- Elevation (launch angle) is ASSUMED: DEFAULT_ELEVATION_DEG unless you pass one for the
  swing. A swing's path at contact is too noisy to give the launch angle, and the face angle
  needs racket tracking.

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
RACKET_LEVER_M = 0.55          # estimate: wrist to the sweet spot of a 686 mm (WSF maximum) racket
SPEED_WINDOW_MS = 25.0         # median wrist speed over this window around contact (skips one-frame spikes)
RACKET_SPEED_RANGE_MS = (1.0, 80.0)  # what ball.py accepts; anything outside is clamped and flagged

# ---- Shot direction ----
# ASSUMED launch angle. Calibrated on IMG_2115 (public/swings/swing_fh_over_rotation.json):
# its PREDICTED ball hits the front wall near the 1.8 m seen in the video. One angle can't
# fit every swing (the low IMG_2116 backhand needs about 0-3 deg), so pass elevation_deg per swing.
DEFAULT_ELEVATION_DEG = 12.0
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
        "label": "ESTIMATE",
        "method": "wrist speed x (forearm + racket) / forearm",
        "wristSpeedMs": round(wrist, 2),
        "forearmM": round(forearm, 3),
        "racketLeverM": RACKET_LEVER_M,
        "clamped": not lo <= raw <= hi,
        "rawValue": round(raw, 1),
    }


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


def anchor_side(swing: dict, P: np.ndarray, hand: str, contact: int, side: str | None = None) -> tuple[str, str]:
    """("forehand" | "backhand", where that came from), to choose the anchor.

    `side` when given; else the side the pipeline recorded (swing["stroke"] or swing["side"]);
    else measured: the hitting-hand side of the body at contact is a forehand. That is which
    side of the hips the racket head is on, across the court. (pipeline/process.py
    classify_side measures along the shoulder line instead, which turns side-on at contact:
    it calls the labelled 2116 backhand a forehand.)
    """
    if side is not None:
        if side not in SIDES:
            raise ValueError(f"side must be 'forehand' or 'backhand', got {side!r}")
        return side, "given"
    for key in ("stroke", "side"):
        if swing.get(key) in SIDES:
            return swing[key], "recorded"
    Pc = court_axes(P)
    across = racket_head(Pc, hand)[contact, 0] - mid(Pc, L_HIP, R_HIP)[contact, 0]  # + = player's right
    if not np.isfinite(across):
        return "forehand", "default"
    on_right = across > 0
    return ("forehand" if on_right == (hand == "R") else "backhand"), "measured"


def drive_spot(hand: str, side: str) -> tuple[float, float]:
    """ASSUMED anchor (x, z): where the racket meets the ball on the court floor.

    ball.py's forehand drive spot for a right-hander (1 m off the right wall, behind the short
    line), mirrored across the court for a backhand or a left hand. A left-hander's backhand
    is mirrored twice, so it is back on the right.
    """
    x, _, z = DEFAULT_CONTACT
    mirrored = (hand == "L") != (side == "backhand")
    return (round(COURT_WIDTH_M - x, 3) if mirrored else x, z)


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
              elevation_deg: float) -> tuple[dict, dict]:
    """One swing: metrics, racket speed, the swing on the court, its PREDICTED ball, and its launch.

    `shift` is the player's court_shift, so you and the ghost stand in exactly the same place.
    Metrics and speed are measured on the swing as given; they don't depend on where it stands.
    """
    m = measure(swing, fps_real, hand)
    metrics = {k: _num(m[k]) for k in METRICS}
    racket = estimate_racket_speed(swing, fps_real, hand)
    Pc = court_axes(to_array(swing)) + shift
    point = [round(float(c), 3) for c in racket_head(Pc, hand)[contact]]
    if not 0 < point[1] < 3:
        raise ValueError(f"the racket head at contact is {point[1]:.2f} m above the floor; "
                         "the ball model needs 0 to 3 m")
    azimuth = estimate_azimuth(Pc, hand, contact)
    ball = predict_ball_path(racket["value"], elevation_deg, azimuth["value"], tuple(point))
    side = {"swing": _court_swing(swing, Pc), "metrics": metrics, "racketSpeed": racket, "ball": ball}
    return side, {"point": point, "azimuth": azimuth}


def _change(a, b, nd: int = 1) -> dict:
    return {"you": a, "ghost": b, "change": None if a is None or b is None else round(b - a, nd)}


def _landing_depth(ball: dict) -> float | None:
    return None if ball["landing"] is None else round(ball["landing"][1], 2)


def _fmt(x, unit: str = "") -> str:
    return "n/a" if x is None else f"{x:g}{unit}"


def _delta(you: dict, ghost: dict) -> dict:
    metrics = {}
    for k, (unit, _) in METRICS.items():
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
        d = metrics[k]
        if d["change"]:
            summary.append(f"{words} {_fmt(d['you'])} -> {_fmt(d['ghost'])} {unit} ({d['change']:+g})")
    depth = ball["landingDepthM"]
    summary.append(
        f"PREDICTED ball {ball['outcome']['you']} -> {ball['outcome']['ghost']}, "
        f"{_fmt(ball['speedKmh']['you'])} -> {_fmt(ball['speedKmh']['ghost'])} km/h, "
        f"lands {_fmt(depth['you'], ' m')} -> {_fmt(depth['ghost'], ' m')} from the front wall"
    )
    return {"metrics": metrics, "ball": ball, "summary": summary}


def compare(swing: dict, fix_name: str, amount: float, fps_real: float | None = None,
            hand: str | None = None, elevation_deg: float = DEFAULT_ELEVATION_DEG, *,
            side: str | None = None) -> dict:
    """The swing as played next to its ghost (one fix applied), in court coordinates. Never mutates `swing`.

    fix_name: one of physics.ghost.FIXES, e.g. compare(swing, "straighten_elbow", 12).
    fps_real: real capture rate (120 for a 4x slow-mo clip stored at 30 fps). Default: swing["fps"].
    hand: "R" or "L". Default: the hand the pipeline recorded, else whichever wrist moves fastest.
    elevation_deg: the ASSUMED launch angle for this swing's two PREDICTED ball paths. One angle
        can't fit every swing: IMG_2115's forehand needs about 12, the low IMG_2116 backhand 0-3.
    side: "forehand" or "backhand", for the anchor, e.g. the coach's stroke. Default: the side
        the pipeline recorded, else measured from which side of the body the contact is on.
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
    side, side_source = anchor_side(swing, P, hand, contact, side)
    anchor = drive_spot(hand, side)
    shift = court_shift(P, hand, contact, anchor)  # from YOUR racket head; the ghost reuses it
    played = {**swing, "contactFrame": contact}
    ghost_swing = apply_fix(played, fix_name, amount, fps_real, hand)

    you, you_launch = _on_court(played, fps_real, hand, contact, shift, elevation_deg)
    ghost, ghost_launch = _on_court(ghost_swing, fps_real, hand, contact, shift, elevation_deg)
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
        "delta": _delta(you, ghost),
        "assumptions": {
            "anchor": {
                "x": anchor[0], "z": anchor[1], "side": side, "sideSource": side_source,
                "assumed": True, "label": "ASSUMED",
                "method": "drive spot for the stroke: ball.py's forehand spot for a right-hander, mirrored "
                          "across the court for a backhand or a left hand. Your racket head at contact "
                          "sits here; the ghost is moved by exactly the same amount, so the bodies overlap.",
            },
            "launch": {
                "racketHead": f"ESTIMATE: hitting wrist + {RACKET_HEAD_M:g} m along elbow -> wrist, "
                              "at its measured height (no racket tracking yet)",
                "elevation": {"value": float(elevation_deg), "unit": "deg", "assumed": True, "label": "ASSUMED"},
                "you": you_launch,
                "ghost": ghost_launch,
            },
            "launchElevationDeg": float(elevation_deg),
            "contactSpot": you_launch["point"],  # kept for app/ghost/compare.ts: your launch point
            "note": "Ball paths are PREDICTED. The launch angle and the spot on court are assumed; racket "
                    "speed, racket head and aim are estimated from the wrist and forearm until racket "
                    "tracking exists.",
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
    parser.add_argument("--elevation", type=float, default=DEFAULT_ELEVATION_DEG,
                        help=f"assumed launch angle for this swing, degrees up (default {DEFAULT_ELEVATION_DEG:g})")
    parser.add_argument("--side", choices=SIDES, default=None,
                        help="stroke, for the spot on court (default: recorded by the pipeline, else measured)")
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
