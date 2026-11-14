"""The player's swing next to the ghost: metrics, PREDICTED ball paths and what changed. Owner: aryan.

compare(swing, fix_name, amount) returns one JSON-able dict:
    you    measured metrics + PREDICTED ball path for the swing as played
    ghost  the same for the swing with one fix applied (physics/ghost.py), plus the ghost swing
    delta  metric and outcome changes, e.g. elbow 137.7 -> 149.7 deg, ball tin -> in

Where the ball model's inputs come from (physics/ball.py):
- Racket speed is an ESTIMATE until racket tracking exists. The forearm and racket are
  treated as one straight lever turning about the elbow, so the racket's sweet spot
  moves (forearm + racket) / forearm times faster than the wrist:
      racket speed = wrist speed x (forearm + RACKET_LEVER_M) / forearm
  It ignores the wrist snap, so the hold_wrist_cock fix doesn't change it.
- The launch angle and contact spot are ASSUMED (a straight drive from ball.py's default
  spot, mirrored for a left-hander). A swing's path at contact is too noisy to give the
  launch angle, and the face angle needs racket tracking.

Try it (from inside services/):

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
from physics.skeleton import ARM, swing_hand, to_array

# ---- Racket speed estimate ----
RACKET_LEVER_M = 0.55          # estimate: wrist to the sweet spot of a 686 mm (WSF maximum) racket
SPEED_WINDOW_MS = 25.0         # median wrist speed over this window around contact (skips one-frame spikes)
RACKET_SPEED_RANGE_MS = (1.0, 80.0)  # what ball.py accepts; anything outside is clamped and flagged

# ---- Assumed shot (not measured) ----
DEFAULT_ELEVATION_DEG = 5.0    # a typical drive: ball.py's straight drive at 35 m/s and 5 deg lands a good length
DEFAULT_AZIMUTH_DEG = 0.0      # straight down the wall

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


def _contact_spot(hand: str) -> tuple[float, float, float]:
    x, y, z = DEFAULT_CONTACT
    return (x, y, z) if hand == "R" else (COURT_WIDTH_M - x, y, z)


def _side(swing: dict, fps_real, hand: str, elevation_deg: float, azimuth_deg: float) -> dict:
    """Metrics, racket speed estimate and PREDICTED ball path for one swing."""
    m = measure(swing, fps_real, hand)
    metrics = {k: _num(m[k]) for k in METRICS}
    racket = estimate_racket_speed(swing, fps_real, hand)
    ball = predict_ball_path(racket["value"], elevation_deg, azimuth_deg, _contact_spot(hand))
    return {"swing": swing, "metrics": metrics, "racketSpeed": racket, "ball": ball}


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
            hand: str | None = None, elevation_deg: float = DEFAULT_ELEVATION_DEG,
            azimuth_deg: float = DEFAULT_AZIMUTH_DEG) -> dict:
    """The swing as played next to its ghost (one fix applied). Never mutates `swing`.

    fix_name: one of physics.ghost.FIXES, e.g. compare(swing, "straighten_elbow", 12).
    fps_real: real capture rate (120 for a 4x slow-mo clip stored at 30 fps). Default: swing["fps"].
    hand: "R" or "L". Default: the hand the pipeline recorded, else whichever wrist moves fastest.
    elevation_deg, azimuth_deg: the ASSUMED launch direction for both PREDICTED ball paths.
    """
    if fix_name not in FIXES:
        uses = [fix for fix, (edit, _) in FIXES.items() if edit == fix_name]
        tip = f" ({fix_name!r} is an edit; the fixes that use it are {', '.join(map(repr, uses))})" if uses else ""
        raise ValueError(f"unknown fix {fix_name!r}{tip}; known fixes: {', '.join(FIXES)}")
    if hand not in (None, "R", "L"):
        raise ValueError(f"hand must be 'R' or 'L', got {hand!r}")
    if not swing.get("frames"):
        raise ValueError("swing has no frames")
    P = to_array(swing)
    hand = hand or swing_hand(swing, P)
    played = {**swing, "contactFrame": contact_frame(swing, P, hand)}
    ghost_swing = apply_fix(played, fix_name, amount, fps_real, hand)

    you = _side(played, fps_real, hand, elevation_deg, azimuth_deg)
    ghost = _side(ghost_swing, fps_real, hand, elevation_deg, azimuth_deg)
    edit, _ = FIXES[fix_name]
    return {
        "fix": {"id": fix_name, "amount": float(amount), "unit": EDITS[edit]["unit"]},
        "hand": hand,
        "contactFrame": played["contactFrame"],
        "fpsReal": real_fps(swing, fps_real),
        "you": you,
        "ghost": ghost,
        "delta": _delta(you, ghost),
        "assumptions": {
            "launchElevationDeg": elevation_deg,
            "launchAzimuthDeg": azimuth_deg,
            "contactSpot": list(_contact_spot(hand)),
            "note": "Shot direction and contact spot are assumed, not measured, and racket speed is "
                    "estimated from the wrist, until racket tracking exists.",
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
                        help=f"assumed launch angle, degrees up (default {DEFAULT_ELEVATION_DEG:g})")
    parser.add_argument("--azimuth", type=float, default=DEFAULT_AZIMUTH_DEG,
                        help="assumed launch direction, degrees towards the right wall (default 0)")
    parser.add_argument("--no-swings", action="store_true",
                        help="leave out the two swings' frames so the numbers are easy to read")
    args = parser.parse_args(argv)

    try:
        swing = json.loads(args.swing.read_text())
        swing.setdefault("id", args.swing.stem)
        result = compare(swing, args.fix, args.amount, args.fps_real, args.hand, args.elevation, args.azimuth)
        if args.no_swings:
            for side in ("you", "ghost"):
                del result[side]["swing"]
        text = json.dumps(result, indent=2, allow_nan=False)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        sys.exit(f"compare: {e}")
    print(text)


if __name__ == "__main__":
    main()
