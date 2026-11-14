"""The coach: one swing in, the one fix that matters out. Owners: aryan and Dev.

Rule: code measures, Claude explains and decides. coach_swing is fully deterministic:
physics measures the swing, the fault library (faults.py) ranks what's wrong, and
the top fault's fix and cue come back. cue.py can then have Claude word it, quoting
only these numbers.

Try it (from inside services/):

    python -m coach.agent ../data/samples/swing_sample.json --stroke backhand
    python -m coach.agent swing.json --wrist wrist_metrics.json   # with the forearm sensor
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any, Optional

from physics.ghost import FIXES

from coach.faults import Fault, Stroke, detect_faults, disabled_faults, measure_swing, unmeasured_faults

NO_FAULT_CUE = "Nothing to fix on this swing. Hit the next one the same way."
GHOST_SHOWS_NEXT = "The ghost shows the next fix, because the top one isn't animated yet."
GHOST_SHOWS_NONE = "The ghost can't animate this fix yet."

# Fixes the ghost shows together when both faults fire: an open stance lets the hips
# fly open, so closing the stance pairs with turning the shoulders less.
GHOST_PAIRS: set[frozenset[str]] = {frozenset({"close_stance", "turn_shoulders_less"})}


def ghost_fixes(primary: Optional[Fault], faults: list[Fault]) -> list[Fault]:
    """The primary ghost fault, plus any ghost-ready fault paired with it in GHOST_PAIRS."""
    if primary is None:
        return []
    partners = [f for f in faults if f is not primary and f["ghost_ready"]
                and frozenset({primary["fix"], f["fix"]}) in GHOST_PAIRS]
    return [primary] + partners[:1]


def ghost_edits(chosen: list[Fault]) -> dict[str, float]:
    """physics.ghost.edit_swing edits for these fixes, e.g. {"stance_open": -55, "shoulder_turn": -12}."""
    edits: dict[str, float] = {}
    for f in chosen:
        edit, sign = FIXES[f["fix"]]
        edits[edit] = sign * float(f["fix_amount"])
    return edits


def _json_safe(metrics: dict[str, Any]) -> dict[str, Any]:
    """Round floats and turn NaN into None so the result is valid JSON."""
    out: dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, float):
            out[k] = round(v, 1) if math.isfinite(v) else None
        else:
            out[k] = v
    return out


def coach_swing(swing: dict, stroke: Optional[Stroke] = None, fps_real: Optional[float] = None) -> dict[str, Any]:
    """Return the top fault, its fix and its cue for one swing.

    stroke: "forehand" or "backhand". If omitted we use swing["stroke"], else detect it
    (low confidence; see measure_extra.py). fps_real: real capture rate if slow-mo.

    Result keys: stroke, stroke_source, metrics, fault (Fault or None), fix, fix_amount,
    ghost_ready, cue, other_faults (ids, worst first), not_measured (fault ids), and
    for the ghost: ghost_fault (worst fault the ghost can animate, or None),
    ghost_fix, ghost_fix_amount, ghost_note (None when the ghost shows the top fix),
    ghost_fixes ([{fix, amount}], the primary first plus any paired fix) and
    ghost_edits (the same as physics.ghost.edit_swing edits). Also tip (a second
    coaching point, or None) and disabled_faults ({id: why} switched off for this stroke).

    `fault` stays the overall worst one for the caption; the ghost animates `ghost_fault`.
    ghost_fixes / ghost_edits describe the pair the ghost SHOULD show, but the live path
    (/compare route, web page, physics compare()) applies only ghost_fix today, so the
    avatar describes ghost_fix alone. Use ghost_edits once /compare accepts several edits.
    """
    metrics = measure_swing(swing, stroke, fps_real)
    faults: list[Fault] = detect_faults(swing, metrics=metrics)
    top = faults[0] if faults else None
    ghost = next((f for f in faults if f["ghost_ready"]), None)
    if top is None or top["ghost_ready"]:
        note = None
    else:
        note = GHOST_SHOWS_NEXT if ghost else GHOST_SHOWS_NONE
    shown = ghost_fixes(ghost, faults)
    return {
        "stroke": metrics["stroke"],
        "stroke_source": metrics["stroke_source"],
        "metrics": _json_safe(metrics),
        "fault": top,
        "fix": top["fix"] if top else None,
        "fix_amount": top["fix_amount"] if top else None,
        "ghost_ready": top["ghost_ready"] if top else False,
        "cue": top["cue"] if top else NO_FAULT_CUE,
        "tip": top["tip"] if top else None,
        "other_faults": [f["id"] for f in faults[1:]],
        "not_measured": unmeasured_faults(metrics),
        "notes": [n for n in (metrics.get("stance_note"),) if n],
        "disabled_faults": disabled_faults(metrics["stroke"]),
        "ghost_fault": ghost,
        "ghost_fix": ghost["fix"] if ghost else None,
        "ghost_fix_amount": ghost["fix_amount"] if ghost else None,
        "ghost_note": note,
        "ghost_fixes": [{"fix": f["fix"], "amount": f["fix_amount"]} for f in shown],
        "ghost_edits": ghost_edits(shown),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Coach one swing JSON file.")
    parser.add_argument("swing", help="path to a Swing JSON file")
    parser.add_argument("--stroke", choices=["forehand", "backhand"], help="override stroke detection")
    parser.add_argument("--fps-real", type=float, help="real capture fps for slow-mo clips")
    parser.add_argument("--wrist", help="wrist_metrics.json from python -m wrist.run (adds the rolled_wrist check)")
    args = parser.parse_args()
    with open(args.swing) as fh:
        swing = json.load(fh)
    if args.wrist:
        from coach.wrist_sensor import attach_wrist  # CLI-only
        with open(args.wrist) as fh:
            swing = attach_wrist(swing, json.load(fh))
    print(json.dumps(coach_swing(swing, args.stroke, args.fps_real), indent=2))


if __name__ == "__main__":
    main()
