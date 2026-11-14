"""Fault library for the squash forehand and backhand. Owners: aryan and Dev.

Code measures, Claude explains: every fault is a fixed rule on a number the code
measured (physics.metrics, pipeline.features, or measure_extra). Nothing here guesses.

To tune: change THRESHOLDS only. Each rule has
- measurement: which measured number the rule reads (see MEASUREMENTS)
- threshold:   the fault fires once the measurement is past this value
- severe_at:   severity reaches 1.0 here (rises linearly from 0 at threshold)
- target:      where the ghost aims; fix_amount = how far past target on the faulty
               side (0 if already on the good side, which makes it not ghost_ready)
- source:      "labelled clips" (from real data) or "guess" (coaching rule of thumb)
- amount_from: optional {measurement, target} when the ghost edit needs a different
               unit than the detection measurement (e.g. degrees detected, ms edited)
The direction (too high or too low) follows from severe_at vs threshold.

Rules from labelled clips use: target = the good swings' value, severe_at = the
faulty swings' value, threshold = halfway between.

Fix names match physics/ghost.py apply_fix. A fault is ghost_ready only if its fix
exists in physics.ghost.FIXES today, the amount is in that edit's unit, and the
swing allows the edit. aryan is adding close_stance, bend_elbow, turn_shoulders_less;
they become ready automatically once FIXES has them. firm_wrist isn't planned yet.

rolled_wrist is the one fault the camera can't see: it reads forearm roll from a phone
strapped to the forearm (services/wrist, coach/wrist_sensor.py) and is skipped (listed
in not_measured) for swings without usable sensor data.
"""

from __future__ import annotations

import math
from typing import Any, Literal, Optional, TypedDict

import numpy as np

from physics.ghost import EDITS, FIXES
from physics.metrics import measure, real_fps
from physics.skeleton import L_SH, R_SH, to_array
from pipeline.features import swing_features

from coach.measure_extra import (
    STROKES, guessed_measurements, recorded_hand, stance_ankles_guessed, stance_joints_filled,
    stance_open_front_wall_deg, stroke_side, wrist_index_filled,
    wrist_uncock,
)
from coach.wrist_sensor import sensor_metrics

Stroke = Literal["forehand", "backhand"]
Confidence = Literal["high", "medium", "low"]

LABELLED = "labelled clips"
GUESS = "guess"
# Thresholds picked by python -m wrist.tune from labelled wrist-sensor swings.
WRIST_SENSOR = "wrist-sensor swings"
WRIST_MOCK = "mock wrist-sensor swings"  # synthetic data: replace with real swings

# ---- Tune here ---------------------------------------------------------------------
THRESHOLDS: dict[str, dict[str, dict[str, Any]]] = {
    "forehand": {
        # Labelled clips: wrist angle change before contact, good 30 deg -> early snap 61 deg.
        # Read on the directional uncock (only the wrist OPENING by contact counts; a
        # held or growing cock gives ~0). On a real release it matches the unsigned
        # change the labels were measured on (143.3 vs 142.8 deg on the sample; the
        # smoothing differs slightly), so the labelled thresholds still apply.
        "early_wrist_snap": {"measurement": "wrist_uncock_deg", "threshold": 45.5,
                             "severe_at": 61.0, "target": 30.0, "source": LABELLED,
                             "amount_from": {"measurement": "wrist_uncock_ms", "target": 10.0}},
        # Labelled clips: hip turn range, good 65 deg -> over-rotated 110 deg.
        # The ghost's turn_shoulders_less only rotates the upper body, so its amount comes
        # from the shoulders' own excess over 85 deg, never from the hip number.
        "over_rotation": {"measurement": "hip_turn_range_deg", "threshold": 87.5,
                          "severe_at": 110.0, "target": 65.0, "source": LABELLED,
                          "amount_from": {"measurement": "shoulder_turn_deg", "target": 85.0}},
        "under_rotation": {"measurement": "shoulder_turn_deg", "threshold": 60.0,
                           "severe_at": 30.0, "target": 80.0, "source": GUESS},
        "straight_arm": {"measurement": "elbow_at_contact_deg", "threshold": 160.0,
                         "severe_at": 175.0, "target": 140.0, "source": GUESS},
        # Labelled clips: feet spacing roughly halves with an open stance. Width is in
        # shoulder widths; the normal 1.7 comes from the one real clip (sample backhand).
        # The close_stance ghost edits the stance ANGLE (physics), not feet spacing, so its
        # amount is the angle's excess over 25 deg; the angle falls as the stance closes.
        "stance_too_open": {"measurement": "stance_width_ratio", "threshold": 1.275,
                            "severe_at": 0.85, "target": 1.7, "source": LABELLED,
                            "amount_from": {"measurement": "stance_open_deg", "target": 25.0,
                                            "fix_lowers": True}},
        # Wrist sensor only (coach/wrist_sensor.py): forearm roll -150..+100 ms around
        # contact; skipped when the swing has no sensor data. From MOCK 5 normal (16.5 deg)
        # vs 5 rolled (62.1 deg) swings via python -m wrist.tune: retune on real swings.
        "rolled_wrist": {"measurement": "forearm_roll_deg", "threshold": 39.3,
                         "severe_at": 62.1, "target": 16.5, "source": WRIST_MOCK},
    },
    "backhand": {
        # Fastest wrist OPENING before contact; a fast cocking move never counts.
        "early_wrist_snap": {"measurement": "wrist_uncock_ms", "threshold": 40.0,
                             "severe_at": 100.0, "target": 10.0, "source": GUESS},
        "over_rotation": {"measurement": "shoulder_turn_deg", "threshold": 115.0,
                          "severe_at": 140.0, "target": 100.0, "source": GUESS},
        "under_rotation": {"measurement": "shoulder_turn_deg", "threshold": 70.0,
                           "severe_at": 40.0, "target": 90.0, "source": GUESS},
        # Labelled clips: smallest elbow angle before contact, good 77 deg -> straight arm 109 deg.
        "straight_arm": {"measurement": "elbow_min_before_deg", "threshold": 93.0,
                         "severe_at": 109.0, "target": 77.0, "source": LABELLED},
        "stance_too_open": {"measurement": "stance_open_deg", "threshold": 40.0,
                            "severe_at": 70.0, "target": 15.0, "source": GUESS},
        # Wrist sensor only; the same MOCK rule as the forehand until real backhands.
        "rolled_wrist": {"measurement": "forearm_roll_deg", "threshold": 39.3,
                         "severe_at": 62.1, "target": 16.5, "source": WRIST_MOCK},
    },
}
# ------------------------------------------------------------------------------------

# Every number a rule may read: its unit, how far we trust it, and how a label says it.
MEASUREMENTS: dict[str, dict[str, Any]] = {
    "wrist_release_ms": {"unit": "ms", "confidence": "low",  # MediaPipe hands are noisy
                         "phrase": "wrist releases {v:.0f} ms before contact"},
    "wrist_angle_change_pre_deg": {"unit": "deg", "confidence": "low",
                                   "phrase": "wrist angle changes {v:.0f} deg before contact"},
    "wrist_uncock_deg": {"unit": "deg", "confidence": "low",
                         "phrase": "wrist uncocks {v:.0f} deg before contact"},
    "wrist_uncock_ms": {"unit": "ms", "confidence": "low",
                        "phrase": "wrist releases {v:.0f} ms before contact"},
    "shoulder_turn_deg": {"unit": "deg", "confidence": "medium",
                          "phrase": "shoulders turn {v:.0f} deg"},
    "hip_turn_range_deg": {"unit": "deg", "confidence": "medium",
                           "phrase": "hips turn {v:.0f} deg"},
    "elbow_at_contact_deg": {"unit": "deg", "confidence": "medium",
                             "phrase": "elbow at {v:.0f} deg at contact"},
    "elbow_min_before_deg": {"unit": "deg", "confidence": "medium",
                             "phrase": "elbow never bends past {v:.0f} deg before contact"},
    "stance_open_deg": {"unit": "deg", "confidence": "low",  # contact frame is approximate
                        "phrase": "stance {v:.0f} deg open to the shot"},
    "stance_width_ratio": {"unit": "shoulder widths", "confidence": "medium",
                           "phrase": "feet {v:.1f} shoulder widths apart"},
    # Wrist sensor (forearm phone), None without one. Low until real swings confirm the
    # strap axis and the threshold. "sensor": labels get "(MOCK sensor data)" if synthetic.
    "forearm_roll_deg": {"unit": "deg", "confidence": "low", "sensor": True,
                         "phrase": "forearm rolls {v:.0f} deg through contact (wrist sensor)"},
    "forearm_roll_rate_dps": {"unit": "deg/s", "confidence": "low", "sensor": True,
                              "phrase": "forearm rolls at up to {v:.0f} deg/s through contact (wrist sensor)"},
}

# The library. `priority` breaks severity ties: stance first, then preparation,
# rotation, wrist (the coaching order in agent.py).
FAULTS: dict[str, dict[str, Any]] = {
    "stance_too_open": {"title": "Stance too open", "fix": "close_stance", "priority": 0,
                        "cue": "Your open stance lets your hips fly open early. Close it so you can hold the turn.",
                        "tip": "A compact, closed stance is more deceptive: your opponent can't read the direction early."},
    "straight_arm": {"title": "Straight arm, no elbow lead", "fix": "bend_elbow", "priority": 1,
                     "cue": "Lead with a bent elbow, then extend through the ball."},
    "under_rotation": {"title": "Under-rotation", "fix": "turn_shoulders_more", "priority": 2,
                       "cue": "Turn your shoulders further before you swing."},
    "over_rotation": {"title": "Over-rotation", "fix": "turn_shoulders_less", "priority": 3,
                      "cue": "Turn a little less and stay balanced through the ball."},
    "early_wrist_snap": {"title": "Early wrist snap", "fix": "hold_wrist_cock", "priority": 4,
                         "cue": "Keep your wrist cocked until the racket meets the ball."},
    "rolled_wrist": {"title": "Rolled wrist", "fix": "firm_wrist", "priority": 5,
                     "cue": "Keep your wrist firm and the racket face steady through the ball."},
}

# Smallest shoulder turn the shoulder edits in physics/ghost.py can work from.
MIN_SHOULDER_TURN_FOR_EDIT = 1.0

# Added to a sensor fault's label when its numbers came from a synthetic recording.
MOCK_SENSOR_NOTE = " (MOCK sensor data)"


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
    source: str
    fix: str
    fix_amount: Optional[float]
    fix_unit: str
    ghost_ready: bool
    cue: str
    tip: Optional[str]  # an optional second coaching point, e.g. why the fix matters


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def severity(value: float, rule: dict[str, Any]) -> float:
    """0 at or inside the threshold, rising linearly to 1 at severe_at (capped)."""
    thr, severe = rule["threshold"], rule["severe_at"]
    span = severe - thr
    if span == 0:
        raise ValueError("severe_at must differ from threshold")
    return max(0.0, min(1.0, (value - thr) / span))


def fix_amount(fix: str, value: float, rule: dict[str, Any], metrics: dict[str, Any]) -> tuple[Optional[float], str]:
    """(amount, unit) the ghost should move, capped at what apply_fix allows. None if unmeasured.

    Directional: the ghost only moves from the faulty side towards the target. If the
    amount's measurement is already on the good side (e.g. a wrist release that is
    already late, or shoulders that aren't over-turned), the amount is 0, which makes
    the fault not ghost_ready.
    """
    src = rule.get("amount_from") or {"measurement": rule["measurement"], "target": rule["target"]}
    measured = value if src["measurement"] == rule["measurement"] else metrics.get(src["measurement"])
    unit = MEASUREMENTS[src["measurement"]]["unit"]
    if not _finite(measured):
        return None, unit
    # A "too high" fault (severe_at above threshold) is fixed by lowering, and vice versa.
    # amount_from can say otherwise ("fix_lowers") when its measurement runs the other way.
    lowers = src.get("fix_lowers", rule["severe_at"] > rule["threshold"])
    amount = max(0.0, (measured - src["target"]) if lowers else (src["target"] - measured))
    if fix in FIXES:
        amount = min(amount, EDITS[FIXES[fix][0]]["max_abs"])
    return round(amount, 2 if unit == "shoulder widths" else 1), unit


def ghost_ready(fix: str, amount: Optional[float], unit: str, metrics: dict[str, Any]) -> bool:
    """True only if apply_fix(swing, fix, amount) would run on this swing."""
    if fix not in FIXES or amount is None or amount <= 0:
        return False
    edit = FIXES[fix][0]
    if EDITS[edit]["unit"] != unit:
        return False  # e.g. a ratio can't drive a degree edit
    if fix == "close_stance" and metrics.get("stance_direction") == "front_wall_axis":
        return False  # the edit changes the hitting-direction angle, which was guessed here
    if edit == "shoulder_turn":
        turn = metrics.get("shoulder_turn_deg")
        if not _finite(turn) or turn < MIN_SHOULDER_TURN_FOR_EDIT:
            return False  # ghost.py refuses: the shoulders don't turn
        if FIXES[fix][1] < 0 and amount >= turn:
            return False  # can't take away more turn than there is
    return True


def _shoulder_width_m(P: np.ndarray, contact: int) -> float:
    """Median shoulder width up to contact, metres. Divides feet spacing so it's size-independent."""
    widths = np.linalg.norm(P[: contact + 1, R_SH] - P[: contact + 1, L_SH], axis=1)
    return float(np.nanmedian(widths)) if np.isfinite(widths).any() else float("nan")


def measure_swing(swing: dict, stroke: Optional[Stroke] = None, fps_real: Optional[float] = None) -> dict[str, Any]:
    """All numbers the fault rules use, plus which stroke and where it came from."""
    # physics measure() picks the hand with physics.skeleton.swing_hand: the recorded hand
    # (metadata.hand, else swing["hand"]), guessing from wrist speed only without one.
    m = measure(swing, fps_real)
    m["hand_source"] = "recorded" if recorded_hand(swing) else "detected"
    given = stroke or swing.get("stroke")
    if given is not None and given not in STROKES:
        raise ValueError(f"stroke must be one of {STROKES}, got {given!r}")
    detected, side_offset = stroke_side(swing, m["hand"])
    m["stroke"] = given or detected
    m["stroke_source"] = "given" if given else "detected"  # detected = low confidence
    m["wrist_side_offset"] = side_offset
    # stance_open_deg comes from physics measure() (the same angle the close_stance
    # ghost edits), so the ghost's stance amount matches what the edit changes.

    P = to_array(swing)
    feats = swing_features(P[:, :33], m["contact_frame"], real_fps(swing, fps_real), m["hand"])
    m["wrist_angle_change_pre_deg"] = feats["wrist_angle_change_pre"]
    m["hip_turn_range_deg"] = feats["hip_turn_range"]
    m["elbow_min_before_deg"] = feats["elbow_min_before"]
    m["wrist_uncock_deg"], m["wrist_uncock_ms"] = wrist_uncock(
        swing, m["hand"], m["contact_frame"], m["fps_real"])
    shoulder_width = _shoulder_width_m(P, m["contact_frame"])
    m["stance_width_ratio"] = (
        feats["stance_width_m"] / shoulder_width
        if _finite(shoulder_width) and shoulder_width > 1e-6 else float("nan")
    )
    # Forearm roll: the camera can't see it, only a forearm phone (swing["wrist"]). Without
    # a usable one these are None and rolled_wrist is skipped.
    m.update(sensor_metrics(swing.get("wrist")))

    # Stance comes from the ankles. If either is a filled-in placeholder, both stance
    # numbers are unmeasured: no stance fault beats a false one.
    filled = stance_joints_filled(swing, m["contact_frame"])
    m["stance_skipped"] = (
        "; ".join(f"joint {j} {why}" for j, why in sorted(filled.items())) if filled else None
    )
    if filled:
        m["stance_open_deg"] = None
        m["stance_width_ratio"] = None

    # Every wrist number needs the hitting-side index finger. A filled-in index sits on
    # the wrist and gives a fake 90 deg angle, so none of them is a measurement.
    m["wrist_skipped"] = wrist_index_filled(swing, m["hand"], m["contact_frame"])
    if m["wrist_skipped"]:
        for key in ("wrist_angle_change_pre_deg", "wrist_release_ms", "wrist_uncock_deg", "wrist_uncock_ms"):
            m[key] = None

    # Never call a fault from a guessed joint: a number that reads a joint the pipeline
    # approximated, marked filled on a frame it uses (#39 flags), or saw at visibility
    # below 0.5 at contact is unmeasured, so its fault is skipped (see unmeasured_faults).
    m["guessed_joints"] = guessed_measurements(swing, m["hand"], m["contact_frame"], m["fps_real"])
    m["stance_direction"] = "hitting_direction" if _finite(m.get("stance_open_deg")) else None
    # Stance is a feet measurement. When only the shot direction (the hitting wrist around
    # contact) is guessed and the ankles were seen, judge the feet against the front-wall
    # axis instead of dropping the stance check. Only where stance_open_deg is the rule's
    # own measurement (backhand): on the forehand it only sizes the close_stance ghost,
    # which edits the hitting-direction angle, so there it stays unmeasured.
    stance_rule = THRESHOLDS.get(m["stroke"], {}).get("stance_too_open", {})
    if ("stance_open_deg" in m["guessed_joints"] and not m["stance_skipped"]
            and stance_rule.get("measurement") == "stance_open_deg"
            and stance_ankles_guessed(swing, m["contact_frame"]) is None):
        front = stance_open_front_wall_deg(swing, m["contact_frame"])
        if _finite(front):
            m["guessed_joints"].pop("stance_open_deg")
            m["stance_open_deg"] = front
            m["stance_direction"] = "front_wall_axis"
            m["stance_note"] = FRONT_WALL_STANCE_NOTE
    for key in m["guessed_joints"]:
        m[key] = None
    return m


FRONT_WALL_STANCE_NOTE = ("Stance measured from the feet against the camera's forward direction "
                          "(assumes the phone filmed from behind); not used as a fault.")


def detect_faults(swing: dict, stroke: Optional[Stroke] = None, fps_real: Optional[float] = None,
                  metrics: Optional[dict[str, Any]] = None) -> list[Fault]:
    """Every fault that fires on this swing, worst first (severity, then coaching priority).

    Pass `metrics` (from measure_swing) to skip re-measuring.
    """
    m = metrics if metrics is not None else measure_swing(swing, stroke, fps_real)
    found: list[Fault] = []
    for fault_id, rule in THRESHOLDS[m["stroke"]].items():
        if rule.get("disabled"):
            continue  # switched off: its measurement can't tell good from faulty swings
        if (rule["measurement"] == "stance_open_deg"
                and m.get("stance_direction") == "front_wall_axis"):
            continue  # feet vs the camera's forward axis: reported, never a fault
        spec = FAULTS[fault_id]
        meas = MEASUREMENTS[rule["measurement"]]
        value = m.get(rule["measurement"])
        if not _finite(value):
            continue  # not measured: never guess
        sev = severity(value, rule)
        if sev <= 0:
            continue
        amount, amount_unit = fix_amount(spec["fix"], value, rule, m)
        found.append(Fault(
            id=fault_id,
            label=f"{spec['title']}: {meas['phrase'].format(v=value)}"
                  + (MOCK_SENSOR_NOTE if meas.get("sensor") and m.get("wrist_sensor") == "mock sensor" else ""),
            stroke=m["stroke"],
            measurement=rule["measurement"],
            value=round(float(value), 2 if meas["unit"] == "shoulder widths" else 1),
            unit=meas["unit"],
            threshold=rule["threshold"],
            severity=round(sev, 2),
            confidence=meas["confidence"],
            source=rule["source"],
            fix=spec["fix"],
            fix_amount=amount,
            fix_unit=amount_unit,
            ghost_ready=ghost_ready(spec["fix"], amount, amount_unit, m),
            cue=spec["cue"],
            tip=spec.get("tip"),
        ))
    found.sort(key=lambda f: (-f["severity"], FAULTS[f["id"]]["priority"]))
    return found


def unmeasured_faults(metrics: dict[str, Any]) -> list[str]:
    """Fault ids we couldn't check on this stroke because their measurement is missing."""
    rules = THRESHOLDS[metrics["stroke"]]
    return [fid for fid, rule in rules.items()
            if not rule.get("disabled") and not _finite(metrics.get(rule["measurement"]))]


def disabled_faults(stroke: Stroke) -> dict[str, str]:
    """Fault ids switched off for this stroke, with why (set "disabled": "<reason>" in THRESHOLDS)."""
    return {fid: rule["disabled"] for fid, rule in THRESHOLDS[stroke].items() if rule.get("disabled")}
