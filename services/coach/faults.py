"""Fault library for the squash forehand and backhand. Owners: aryan and Dev.

Code measures, Claude explains: every fault is a fixed rule on a number the code
measured. Nothing here guesses.

To tune: change THRESHOLDS only. Each entry has
- threshold: the fault fires once the measurement is past this value
- severe_at: severity reaches 1.0 here (severity rises linearly from 0 at threshold)
- target:    where the ghost aims; fix_amount = |measured - target|
The direction (too high or too low) follows from severe_at vs threshold.

STARTING GUESSES from coaching rules of thumb, not fitted to data yet. Tune them with
the labelled clips in data/labels/ before trusting severities.

Fix names: a fault's `fix` is the name the ghost uses in physics/ghost.py apply_fix.
Some fixes aren't built there yet; `ghost_ready` says which. Missing ones, for the
physics owner: turn_shoulders_less, bend_elbow, close_stance, firm_wrist.
"""

from __future__ import annotations

import math
from typing import Any, Literal, Optional, TypedDict

from physics.ghost import EDITS, FIXES
from physics.metrics import measure

from coach.measure_extra import STROKES, stance_open_deg, stroke_side

Stroke = Literal["forehand", "backhand"]
Confidence = Literal["high", "medium", "low"]

# ---- Tune here ---------------------------------------------------------------------
THRESHOLDS: dict[str, dict[str, dict[str, float]]] = {
    "forehand": {
        "early_wrist_snap": {"threshold": 40.0, "severe_at": 100.0, "target": 10.0},  # ms before contact
        "over_rotation": {"threshold": 100.0, "severe_at": 130.0, "target": 85.0},  # deg
        "under_rotation": {"threshold": 60.0, "severe_at": 30.0, "target": 80.0},  # deg
        "straight_arm": {"threshold": 160.0, "severe_at": 175.0, "target": 140.0},  # elbow deg
        "stance_too_open": {"threshold": 50.0, "severe_at": 80.0, "target": 25.0},  # deg
        "rolling_wrist": {"threshold": 30.0, "severe_at": 60.0, "target": 0.0},  # deg, not measured yet
    },
    "backhand": {
        "early_wrist_snap": {"threshold": 40.0, "severe_at": 100.0, "target": 10.0},
        "over_rotation": {"threshold": 115.0, "severe_at": 140.0, "target": 100.0},
        "under_rotation": {"threshold": 70.0, "severe_at": 40.0, "target": 90.0},
        "straight_arm": {"threshold": 168.0, "severe_at": 178.0, "target": 150.0},
        "stance_too_open": {"threshold": 40.0, "severe_at": 70.0, "target": 15.0},
        "rolling_wrist": {"threshold": 30.0, "severe_at": 60.0, "target": 0.0},
    },
}
# ------------------------------------------------------------------------------------

# What each measurement is and how far we trust it.
MEASUREMENTS: dict[str, dict[str, Any]] = {
    "wrist_release_ms": {"unit": "ms", "confidence": "low"},  # MediaPipe hands are noisy (metrics.py)
    "shoulder_turn_deg": {"unit": "deg", "confidence": "medium"},
    "elbow_at_contact_deg": {"unit": "deg", "confidence": "medium"},
    "stance_open_deg": {"unit": "deg", "confidence": "low"},  # contact frame is approximate
    "forearm_roll_deg": {"unit": "deg", "confidence": "low"},  # not measured yet: always None
}

# The library. `priority` breaks severity ties: stance first, then preparation,
# rotation, wrist (the coaching order in agent.py).
FAULTS: dict[str, dict[str, Any]] = {
    "stance_too_open": {
        "measurement": "stance_open_deg",
        "label": "Stance {value:.0f} deg open to the shot",
        "fix": "close_stance",
        "cue": "Step across so you stand side-on to the front wall.",
        "priority": 0,
    },
    "straight_arm": {
        "measurement": "elbow_at_contact_deg",
        "label": "Elbow {value:.0f} deg at contact, no elbow lead",
        "fix": "bend_elbow",
        "cue": "Lead with a bent elbow, then extend through the ball.",
        "priority": 1,
    },
    "under_rotation": {
        "measurement": "shoulder_turn_deg",
        "label": "Shoulders turn only {value:.0f} deg",
        "fix": "turn_shoulders_more",
        "cue": "Turn your shoulders further before you swing.",
        "priority": 2,
    },
    "over_rotation": {
        "measurement": "shoulder_turn_deg",
        "label": "Shoulders turn {value:.0f} deg, past the ball",
        "fix": "turn_shoulders_less",
        "cue": "Turn a little less and stay balanced through the ball.",
        "priority": 3,
    },
    "early_wrist_snap": {
        "measurement": "wrist_release_ms",
        "label": "Wrist releases {value:.0f} ms before contact",
        "fix": "hold_wrist_cock",
        "cue": "Keep your wrist cocked until the racket meets the ball.",
        "priority": 4,
    },
    "rolling_wrist": {
        "measurement": "forearm_roll_deg",
        "label": "Forearm rolls {value:.0f} deg through contact",
        "fix": "firm_wrist",
        "cue": "Keep your wrist firm and the racket face steady.",
        "priority": 5,
    },
}


class Fault(TypedDict):
    id: str
    label: str
    stroke: Stroke
    measurement: str
    value: float
    unit: str
    threshold: float
    severity: float
    confidence: Confidence
    fix: str
    fix_amount: float
    ghost_ready: bool
    cue: str


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def severity(value: float, rule: dict[str, float]) -> float:
    """0 at or inside the threshold, rising linearly to 1 at severe_at (capped)."""
    thr, severe = rule["threshold"], rule["severe_at"]
    span = severe - thr
    if span == 0:
        raise ValueError("severe_at must differ from threshold")
    return max(0.0, min(1.0, (value - thr) / span))


def fix_amount(fix: str, value: float, rule: dict[str, float]) -> float:
    """How far the ghost should move this measurement, capped at what apply_fix allows."""
    amount = abs(value - rule["target"])
    if fix in FIXES:
        amount = min(amount, EDITS[FIXES[fix][0]]["max_abs"])
    return round(amount, 1)


def measure_swing(swing: dict, stroke: Optional[Stroke] = None, fps_real: Optional[float] = None) -> dict[str, Any]:
    """All numbers the fault rules use, plus which stroke and where it came from."""
    m = measure(swing, fps_real)
    given = stroke or swing.get("stroke")
    if given is not None and given not in STROKES:
        raise ValueError(f"stroke must be one of {STROKES}, got {given!r}")
    detected, side_offset = stroke_side(swing, m["hand"])
    m["stroke"] = given or detected
    m["stroke_source"] = "given" if given else "detected"  # detected = low confidence
    m["wrist_side_offset"] = side_offset
    m["stance_open_deg"] = stance_open_deg(swing, m["hand"])
    m["forearm_roll_deg"] = None  # not measured yet
    return m


def detect_faults(swing: dict, stroke: Optional[Stroke] = None, fps_real: Optional[float] = None,
                  metrics: Optional[dict[str, Any]] = None) -> list[Fault]:
    """Every fault that fires on this swing, worst first (severity, then coaching priority).

    Pass `metrics` (from measure_swing) to skip re-measuring.
    """
    m = metrics if metrics is not None else measure_swing(swing, stroke, fps_real)
    rules = THRESHOLDS[m["stroke"]]
    found: list[Fault] = []
    for fault_id, spec in FAULTS.items():
        value = m.get(spec["measurement"])
        if not _finite(value):
            continue  # not measured: never guess
        rule = rules[fault_id]
        sev = severity(value, rule)
        if sev <= 0:
            continue
        meas = MEASUREMENTS[spec["measurement"]]
        found.append(Fault(
            id=fault_id,
            label=spec["label"].format(value=value),
            stroke=m["stroke"],
            measurement=spec["measurement"],
            value=round(float(value), 1),
            unit=meas["unit"],
            threshold=rule["threshold"],
            severity=round(sev, 2),
            confidence=meas["confidence"],
            fix=spec["fix"],
            fix_amount=fix_amount(spec["fix"], value, rule),
            ghost_ready=spec["fix"] in FIXES,
            cue=spec["cue"],
        ))
    found.sort(key=lambda f: (-f["severity"], FAULTS[f["id"]]["priority"]))
    return found


def unmeasured_faults(metrics: dict[str, Any]) -> list[str]:
    """Fault ids we couldn't check because their measurement is missing."""
    return [fid for fid, spec in FAULTS.items() if not _finite(metrics.get(spec["measurement"]))]
