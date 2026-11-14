"""Tests for the fault library and coach_swing. Offline: no Claude, no network.

Expected results are worked out from THRESHOLDS, so retuning thresholds doesn't break
these tests; only a broken rule does.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from coach.agent import NO_FAULT_CUE, coach_swing
from coach.faults import (
    FAULTS, MEASUREMENTS, THRESHOLDS, detect_faults, measure_swing, severity, unmeasured_faults,
)
from physics.ghost import EDITS, FIXES, apply_fix
from physics.metrics import measure
from physics.tests.swing_factory import make_swing

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "swing_sample.json"
STROKES = ("forehand", "backhand")


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text())


def neutral_metrics(stroke: str) -> dict:
    """Metrics where every measurement sits on its target, so no fault fires."""
    rules = THRESHOLDS[stroke]
    m: dict = {"stroke": stroke}
    for fid, spec in FAULTS.items():
        m.setdefault(spec["measurement"], rules[fid]["target"])
    return m


def fires(value: float, rule: dict) -> bool:
    return severity(value, rule) > 0


# ---- The library itself -------------------------------------------------------------

def test_library_covers_the_six_faults_for_both_strokes() -> None:
    expected = {"early_wrist_snap", "over_rotation", "under_rotation", "straight_arm",
                "stance_too_open", "rolling_wrist"}
    assert set(FAULTS) == expected
    for stroke in STROKES:
        assert set(THRESHOLDS[stroke]) == expected
        for rule in THRESHOLDS[stroke].values():
            assert rule["severe_at"] != rule["threshold"]
            assert severity(rule["target"], rule) == 0, "target must be inside the threshold"


@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_each_fault_has_measurement_fix_and_one_line_cue(fault_id: str) -> None:
    spec = FAULTS[fault_id]
    assert spec["measurement"] in MEASUREMENTS
    assert spec["fix"]
    cue = spec["cue"].strip()
    assert cue.endswith(".") and cue.count(".") == 1, "one sentence"
    assert not any(ch.isdigit() for ch in cue), "cues quote no numbers"


def test_ready_fixes_really_run_in_apply_fix() -> None:
    swing = make_swing()
    ready = {spec["fix"] for spec in FAULTS.values() if spec["fix"] in FIXES}
    assert ready == {"turn_shoulders_more", "hold_wrist_cock"}
    for fix in ready:
        edit = FIXES[fix][0]
        ghost = apply_fix(swing, fix, EDITS[edit]["max_abs"] / 4)
        assert ghost["synthetic"] is True


# ---- Severity and ranking -----------------------------------------------------------

def test_severity_is_zero_at_threshold_and_linear_to_one() -> None:
    rule = {"threshold": 40.0, "severe_at": 100.0, "target": 10.0}
    assert severity(40.0, rule) == 0
    assert severity(70.0, rule) == pytest.approx(0.5)
    assert severity(100.0, rule) == 1
    assert severity(500.0, rule) == 1
    low_rule = {"threshold": 60.0, "severe_at": 30.0, "target": 80.0}  # "too low" fault
    assert severity(45.0, low_rule) == pytest.approx(0.5)
    assert severity(90.0, low_rule) == 0


@pytest.mark.parametrize("stroke", STROKES)
def test_neutral_swing_has_no_faults(stroke: str) -> None:
    assert detect_faults({}, metrics=neutral_metrics(stroke)) == []


@pytest.mark.parametrize("stroke", STROKES)
@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_each_fault_fires_alone_past_its_threshold(stroke: str, fault_id: str) -> None:
    rule = THRESHOLDS[stroke][fault_id]
    m = neutral_metrics(stroke)
    m[FAULTS[fault_id]["measurement"]] = rule["threshold"]
    assert detect_faults({}, metrics=m) == [], "exactly at the threshold is not a fault"

    m[FAULTS[fault_id]["measurement"]] = rule["severe_at"]
    faults = detect_faults({}, metrics=m)
    assert [f["id"] for f in faults] == [fault_id]
    f = faults[0]
    assert f["severity"] == 1.0
    assert f["fix"] == FAULTS[fault_id]["fix"]
    assert f["ghost_ready"] == (f["fix"] in FIXES)
    assert f["fix_amount"] == pytest.approx(min(
        abs(rule["severe_at"] - rule["target"]),
        EDITS[FIXES[f["fix"]][0]]["max_abs"] if f["ghost_ready"] else math.inf,
    ), abs=0.1)


def test_worst_fault_first_and_priority_breaks_ties() -> None:
    m = neutral_metrics("forehand")
    rules = THRESHOLDS["forehand"]
    m["wrist_release_ms"] = rules["early_wrist_snap"]["severe_at"]  # severity 1, priority 4
    m["elbow_at_contact_deg"] = rules["straight_arm"]["severe_at"]  # severity 1, priority 1
    assert [f["id"] for f in detect_faults({}, metrics=m)] == ["straight_arm", "early_wrist_snap"]

    half = (rules["straight_arm"]["threshold"] + rules["straight_arm"]["severe_at"]) / 2
    m["elbow_at_contact_deg"] = half  # now severity 0.5
    assert [f["id"] for f in detect_faults({}, metrics=m)] == ["early_wrist_snap", "straight_arm"]


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_unmeasured_values_never_fire(missing) -> None:
    m = neutral_metrics("forehand")
    m["wrist_release_ms"] = missing
    assert detect_faults({}, metrics=m) == []
    assert "early_wrist_snap" in unmeasured_faults(m)


# ---- The real sample swing ----------------------------------------------------------

def test_sample_uses_physics_measurements_exactly(sample: dict) -> None:
    m = measure_swing(sample, "backhand")
    physics = measure(sample)
    for key in ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_release_ms", "contact_frame"):
        assert m[key] == physics[key]
    assert m["forearm_roll_deg"] is None
    assert 0 <= m["stance_open_deg"] <= 90


@pytest.mark.parametrize("stroke", STROKES)
def test_sample_faults_match_thresholds(sample: dict, stroke: str) -> None:
    m = measure_swing(sample, stroke)
    got = {f["id"] for f in detect_faults(sample, metrics=m)}
    expected = {
        fid for fid, spec in FAULTS.items()
        if isinstance(m[spec["measurement"]], float) and math.isfinite(m[spec["measurement"]])
        and fires(m[spec["measurement"]], THRESHOLDS[stroke][fid])
    }
    assert got == expected


def test_coach_swing_on_sample(sample: dict) -> None:
    result = coach_swing(sample, stroke="backhand")
    json.dumps(result, allow_nan=False)  # valid JSON for the API, no NaN

    assert result["stroke"] == "backhand" and result["stroke_source"] == "given"
    assert result["not_measured"] == ["rolling_wrist"]
    top = result["fault"]
    assert top is not None, "this sample has faults at the current thresholds"
    assert result["fix"] == top["fix"] and result["cue"] == top["cue"]
    assert result["fix_amount"] == top["fix_amount"] and result["ghost_ready"] == top["ghost_ready"]
    # The label quotes the measured number (rounded), never anything else.
    assert f"{top['value']:.0f}" in top["label"]
    all_ids = [top["id"]] + result["other_faults"]
    assert len(all_ids) == len(set(all_ids))


def test_coach_swing_with_no_faults(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    monkeypatch.setattr("coach.agent.detect_faults", lambda swing, metrics: [])
    result = coach_swing(sample, stroke="forehand")
    assert result["fault"] is None and result["fix"] is None
    assert result["cue"] == NO_FAULT_CUE and result["ghost_ready"] is False


# ---- Stroke --------------------------------------------------------------------------

def test_stroke_comes_from_argument_then_swing_then_detection(sample: dict) -> None:
    assert measure_swing(sample, "backhand")["stroke_source"] == "given"
    assert measure_swing({**sample, "stroke": "backhand"})["stroke"] == "backhand"
    detected = measure_swing(sample)
    assert detected["stroke_source"] == "detected" and detected["stroke"] in STROKES


def test_mock_forehand_is_detected_as_forehand() -> None:
    m = measure_swing(make_swing())
    assert m["stroke"] == "forehand" and m["wrist_side_offset"] > 0


def test_bad_stroke_is_rejected(sample: dict) -> None:
    with pytest.raises(ValueError, match="stroke"):
        measure_swing(sample, "lob")  # type: ignore[arg-type]
