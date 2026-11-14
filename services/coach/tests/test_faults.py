"""Tests for the fault library and coach_swing. Offline: no Claude, no network.

Expected results are worked out from THRESHOLDS, so retuning thresholds doesn't break
these tests; only a broken rule does.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from coach.agent import GHOST_SHOWS_NEXT, GHOST_SHOWS_NONE, NO_FAULT_CUE, coach_swing
from coach.faults import (
    FAULTS, GUESS, LABELLED, MEASUREMENTS, THRESHOLDS, detect_faults, measure_swing, severity,
    unmeasured_faults,
)
from physics.ghost import EDITS, FIXES, apply_fix
from physics.metrics import measure
from physics.tests.swing_factory import make_swing

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "swing_sample.json"
STROKES = ("forehand", "backhand")
SIX = {"early_wrist_snap", "over_rotation", "under_rotation", "straight_arm", "stance_too_open", "rolling_wrist"}


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text())


def neutral_metrics(stroke: str) -> dict:
    """Metrics where every measurement sits on its target, so no fault fires."""
    m: dict = {"stroke": stroke}
    for rule in THRESHOLDS[stroke].values():
        m.setdefault(rule["measurement"], rule["target"])
        if "amount_from" in rule:
            m.setdefault(rule["amount_from"]["measurement"], rule["amount_from"]["target"])
    m.setdefault("shoulder_turn_deg", 80.0)
    return m


def fires(value: float, rule: dict) -> bool:
    return severity(value, rule) > 0


def expected_amount(fault_id: str, stroke: str, m: dict) -> float:
    rule = THRESHOLDS[stroke][fault_id]
    src = rule.get("amount_from") or rule
    gap = m[src["measurement"]] - src["target"]
    lowers = src.get("fix_lowers", rule["severe_at"] > rule["threshold"])
    amount = max(0.0, gap if lowers else -gap)  # faulty side only
    fix = FAULTS[fault_id]["fix"]
    return min(amount, EDITS[FIXES[fix][0]]["max_abs"]) if fix in FIXES else amount


# ---- The library itself -------------------------------------------------------------

@pytest.mark.parametrize("stroke", STROKES)
def test_library_covers_the_six_faults(stroke: str) -> None:
    assert set(FAULTS) == SIX
    assert set(THRESHOLDS[stroke]) == SIX
    for rule in THRESHOLDS[stroke].values():
        assert rule["measurement"] in MEASUREMENTS
        assert rule["source"] in (LABELLED, GUESS)
        assert rule["severe_at"] != rule["threshold"]
        assert severity(rule["target"], rule) == 0, "target must be inside the threshold"
        if "amount_from" in rule:
            assert rule["amount_from"]["measurement"] in MEASUREMENTS


def test_labelled_rules_put_threshold_halfway_from_good_to_fault() -> None:
    labelled = [(s, f, r) for s in STROKES for f, r in THRESHOLDS[s].items() if r["source"] == LABELLED]
    assert {(s, f) for s, f, _ in labelled} == {
        ("forehand", "early_wrist_snap"), ("forehand", "over_rotation"),
        ("forehand", "stance_too_open"), ("backhand", "straight_arm"),
    }
    for _, _, rule in labelled:
        assert rule["threshold"] == pytest.approx((rule["target"] + rule["severe_at"]) / 2)


def test_labelled_values_from_real_data() -> None:
    fh, bh = THRESHOLDS["forehand"], THRESHOLDS["backhand"]
    assert (fh["early_wrist_snap"]["target"], fh["early_wrist_snap"]["severe_at"]) == (30.0, 61.0)
    assert (fh["over_rotation"]["target"], fh["over_rotation"]["severe_at"]) == (65.0, 110.0)
    assert fh["stance_too_open"]["severe_at"] == pytest.approx(fh["stance_too_open"]["target"] / 2)
    assert (bh["straight_arm"]["target"], bh["straight_arm"]["severe_at"]) == (77.0, 109.0)


@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_each_fault_has_fix_and_short_cue(fault_id: str) -> None:
    spec = FAULTS[fault_id]
    assert spec["fix"] and spec["title"]
    for text, max_sentences in ((spec["cue"], 2), (spec.get("tip"), 1)):
        if text is None:
            continue
        text = text.strip()
        assert text.endswith(".") and 1 <= text.count(".") <= max_sentences
        assert not any(ch.isdigit() for ch in text), "cues and tips quote no numbers"


def test_stance_cue_and_tip_wording() -> None:
    spec = FAULTS["stance_too_open"]
    assert spec["cue"] == "Your open stance lets your hips fly open early. Close it so you can hold the turn."
    assert spec["tip"] == "A compact, closed stance is more deceptive: your opponent can't read the direction early."


def test_fix_names_match_physics_and_aryans_planned_fixes() -> None:
    names = {spec["fix"] for spec in FAULTS.values()}
    available = {"straighten_elbow", "turn_shoulders_more", "hold_wrist_cock"}
    planned = {"close_stance", "bend_elbow", "turn_shoulders_less"}
    assert available <= set(FIXES)
    assert names - {"firm_wrist"} <= available | planned


def test_ready_fixes_really_run_in_apply_fix() -> None:
    swing = make_swing()
    for fix in {spec["fix"] for spec in FAULTS.values()} & set(FIXES):
        ghost = apply_fix(swing, fix, EDITS[FIXES[fix][0]]["max_abs"] / 4)
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
    m[rule["measurement"]] = rule["threshold"]
    assert detect_faults({}, metrics=m) == [], "exactly at the threshold is not a fault"

    m[rule["measurement"]] = rule["severe_at"]
    faults = detect_faults({}, metrics=m)
    assert [f["id"] for f in faults] == [fault_id]
    f = faults[0]
    assert f["severity"] == 1.0
    assert f["fix"] == FAULTS[fault_id]["fix"]
    assert f["source"] == rule["source"]
    assert f["fix_amount"] == pytest.approx(expected_amount(fault_id, stroke, m), abs=0.01)
    if f["ghost_ready"]:
        assert f["fix"] in FIXES and EDITS[FIXES[f["fix"]][0]]["unit"] == f["fix_unit"]


def test_worst_fault_first_and_priority_breaks_ties() -> None:
    m = neutral_metrics("backhand")
    rules = THRESHOLDS["backhand"]
    m["wrist_uncock_ms"] = rules["early_wrist_snap"]["severe_at"]  # severity 1, priority 4
    m["elbow_min_before_deg"] = rules["straight_arm"]["severe_at"]  # severity 1, priority 1
    assert [f["id"] for f in detect_faults({}, metrics=m)] == ["straight_arm", "early_wrist_snap"]

    sa = rules["straight_arm"]
    m["elbow_min_before_deg"] = (sa["threshold"] + sa["severe_at"]) / 2  # now severity 0.5
    assert [f["id"] for f in detect_faults({}, metrics=m)] == ["early_wrist_snap", "straight_arm"]


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_unmeasured_values_never_fire(missing) -> None:
    m = neutral_metrics("forehand")
    m["wrist_uncock_deg"] = missing
    assert detect_faults({}, metrics=m) == []
    assert "early_wrist_snap" in unmeasured_faults(m)


# ---- Ghost readiness ----------------------------------------------------------------

def _fault(m: dict, fault_id: str) -> dict:
    return next(f for f in detect_faults({}, metrics=m) if f["id"] == fault_id)


def test_wrist_ghost_amount_is_in_ms_even_when_detected_in_degrees() -> None:
    m = neutral_metrics("forehand")
    m["wrist_uncock_deg"] = 61.0
    m["wrist_uncock_ms"] = 56.0
    f = _fault(m, "early_wrist_snap")
    assert f["unit"] == "deg" and f["fix_unit"] == "ms"
    assert f["fix_amount"] == pytest.approx(46.0) and f["ghost_ready"] is True


def test_no_shoulder_ghost_when_shoulders_barely_turn() -> None:
    # Codex P1 on #22: ghost.py refuses shoulder edits below 1 deg of turn.
    m = neutral_metrics("forehand")
    m["shoulder_turn_deg"] = 0.5
    f = _fault(m, "under_rotation")
    assert f["fix"] == "turn_shoulders_more" and f["ghost_ready"] is False


def test_planned_fixes_become_ready_when_physics_adds_them(monkeypatch: pytest.MonkeyPatch) -> None:
    m = neutral_metrics("forehand")
    m["hip_turn_range_deg"] = 110.0
    m["shoulder_turn_deg"] = 100.0  # shoulders over-turned too
    monkeypatch.delitem(FIXES, "turn_shoulders_less", raising=False)
    assert _fault(m, "over_rotation")["ghost_ready"] is False

    monkeypatch.setitem(FIXES, "turn_shoulders_less", ("shoulder_turn", -1.0))
    assert _fault(m, "over_rotation")["ghost_ready"] is True


def test_over_rotation_ghost_amount_comes_from_shoulders_not_hips(monkeypatch: pytest.MonkeyPatch) -> None:
    # Codex P1 on #28: turn_shoulders_less only rotates the upper body, so the hip
    # excess (110 - 65 = 45 deg) must never become a shoulder reduction.
    monkeypatch.setitem(FIXES, "turn_shoulders_less", ("shoulder_turn", -1.0))
    m = neutral_metrics("forehand")
    m["hip_turn_range_deg"] = 110.0

    m["shoulder_turn_deg"] = 100.0
    f = _fault(m, "over_rotation")
    assert f["fix"] == "turn_shoulders_less" and f["fix_unit"] == "deg"
    assert f["fix_amount"] == pytest.approx(15.0) and f["ghost_ready"] is True  # 100 - 85

    m["shoulder_turn_deg"] = 80.0  # hips over-rotate, shoulders don't
    f = _fault(m, "over_rotation")
    assert f["severity"] == 1.0, "the hip fault is still reported for the caption"
    assert f["fix_amount"] == 0.0 and f["ghost_ready"] is False  # no shoulder reduction

    m["shoulder_turn_deg"] = None
    f = _fault(m, "over_rotation")
    assert f["fix_amount"] is None and f["ghost_ready"] is False


def test_late_wrist_release_gets_no_hold_wrist_cock(monkeypatch: pytest.MonkeyPatch) -> None:
    # Codex P2 on #28: hold_wrist_cock always delays the release, so a release that's
    # already at or after the 10 ms target must not be pushed later.
    m = neutral_metrics("forehand")
    m["wrist_uncock_deg"] = 61.0  # the angle rule fires
    for release_ms in (10.0, 0.0, -20.0):
        m["wrist_uncock_ms"] = release_ms
        f = _fault(m, "early_wrist_snap")
        assert f["fix_amount"] == 0.0 and f["ghost_ready"] is False
    m["wrist_uncock_ms"] = 56.0
    assert _fault(m, "early_wrist_snap")["fix_amount"] == pytest.approx(46.0)


@pytest.mark.parametrize("stroke", STROKES)
@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_ghost_never_moves_past_the_target(stroke: str, fault_id: str) -> None:
    """Directional amounts: on the good side of the target the ghost does nothing."""
    rule = THRESHOLDS[stroke][fault_id]
    src = rule.get("amount_from") or rule
    m = neutral_metrics(stroke)
    m[rule["measurement"]] = rule["severe_at"]  # the fault fires
    if "amount_from" in rule:
        lowers = src.get("fix_lowers", rule["severe_at"] > rule["threshold"])
        good_side = -1.0 if lowers else 1.0
        m[src["measurement"]] = src["target"] + good_side * 5.0
        f = _fault(m, fault_id)
        assert f["fix_amount"] == 0.0 and f["ghost_ready"] is False
    else:
        f = _fault(m, fault_id)
        assert f["fix_amount"] > 0  # severe_at is on the faulty side of the target


def test_fix_with_wrong_unit_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(FIXES, "close_stance", ("elbow_bend", -1.0))  # deg edit
    m = neutral_metrics("forehand")
    m["stance_width_ratio"] = 0.85  # measured in shoulder widths
    assert _fault(m, "stance_too_open")["ghost_ready"] is False


# ---- The real sample swing ----------------------------------------------------------

def test_sample_uses_physics_and_pipeline_measurements(sample: dict) -> None:
    m = measure_swing(sample, "backhand")
    physics = measure(sample)
    for key in ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_release_ms", "contact_frame"):
        assert m[key] == physics[key]
    for key in ("wrist_angle_change_pre_deg", "hip_turn_range_deg", "elbow_min_before_deg", "stance_width_ratio"):
        assert math.isfinite(m[key])
    assert m["forearm_roll_deg"] is None
    assert 0 <= m["stance_open_deg"] <= 90


@pytest.mark.parametrize("stroke", STROKES)
def test_sample_faults_match_thresholds(sample: dict, stroke: str) -> None:
    m = measure_swing(sample, stroke)
    got = {f["id"] for f in detect_faults(sample, metrics=m)}
    expected = set()
    for fid, rule in THRESHOLDS[stroke].items():
        v = m[rule["measurement"]]
        if isinstance(v, float) and math.isfinite(v) and fires(v, rule):
            expected.add(fid)
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
    assert top["label"].startswith(FAULTS[top["id"]]["title"])
    all_ids = [top["id"]] + result["other_faults"]
    assert len(all_ids) == len(set(all_ids))


def test_sample_backhand_ghost_fault_is_animatable(sample: dict) -> None:
    result = coach_swing(sample, stroke="backhand")
    ghost = result["ghost_fault"]
    assert ghost is not None and ghost["ghost_ready"] is True
    assert result["ghost_fix"] == ghost["fix"] and result["ghost_fix"] in FIXES
    assert result["ghost_fix_amount"] == ghost["fix_amount"]
    # It really animates: physics accepts this fix and amount on this swing.
    assert apply_fix(sample, result["ghost_fix"], result["ghost_fix_amount"])["synthetic"] is True
    if result["fault"]["ghost_ready"]:
        assert result["ghost_fault"] == result["fault"] and result["ghost_note"] is None
    else:
        assert result["ghost_note"] == GHOST_SHOWS_NEXT


def test_no_ghost_fault_when_nothing_is_animatable(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    monkeypatch.setattr("coach.faults.FIXES", {})  # no fix is built, whatever physics has today
    m = neutral_metrics("backhand")
    m["stance_open_deg"] = THRESHOLDS["backhand"]["stance_too_open"]["severe_at"]
    faults = detect_faults({}, metrics=m)
    assert faults and not any(f["ghost_ready"] for f in faults)
    monkeypatch.setattr("coach.agent.detect_faults", lambda swing, metrics: faults)
    result = coach_swing(sample, stroke="backhand")
    assert result["fault"]["id"] == "stance_too_open"
    assert result["ghost_fault"] is None and result["ghost_fix"] is None
    assert result["ghost_fix_amount"] is None and result["ghost_note"] == GHOST_SHOWS_NONE


def test_coach_swing_with_no_faults(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    monkeypatch.setattr("coach.agent.detect_faults", lambda swing, metrics: [])
    result = coach_swing(sample, stroke="forehand")
    assert result["fault"] is None and result["fix"] is None
    assert result["cue"] == NO_FAULT_CUE and result["ghost_ready"] is False
    assert result["ghost_fault"] is None and result["ghost_note"] is None


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


# ---- Filled-in ankles never produce stance faults -----------------------------------

STANCE_FAULT = "stance_too_open"
L_ANKLE, R_ANKLE, L_KNEE, R_KNEE = 27, 28, 25, 26


def _with(sample: dict, **changes) -> dict:
    import copy

    s = copy.deepcopy(sample)
    for key, value in changes.items():
        s[key] = value
    return s


def _stance_result(swing: dict, stroke: str = "backhand") -> tuple[dict, dict]:
    m = measure_swing(swing, stroke)
    return m, coach_swing(swing, stroke=stroke)


def test_real_ankles_are_measured(sample: dict) -> None:
    m, result = _stance_result(sample)
    assert m["stance_skipped"] is None
    assert math.isfinite(m["stance_open_deg"]) and math.isfinite(m["stance_width_ratio"])
    assert result["fault"]["id"] == STANCE_FAULT  # the sample's real top fault


@pytest.mark.parametrize("stroke", STROKES)
@pytest.mark.parametrize("ankle", [L_ANKLE, R_ANKLE])
def test_ankle_listed_as_approximated_skips_stance(sample: dict, stroke: str, ankle: int) -> None:
    swing = _with(sample, metadata={"approximatedJoints": [19, ankle, 31]})
    m, result = _stance_result(swing, stroke)
    assert m["stance_open_deg"] is None and m["stance_width_ratio"] is None
    assert f"joint {ankle} approximated" in m["stance_skipped"]
    ids = [f["id"] for f in detect_faults(swing, metrics=m)]
    assert STANCE_FAULT not in ids
    assert result["fault"] is None or result["fault"]["id"] != STANCE_FAULT
    assert STANCE_FAULT not in result["other_faults"]
    assert STANCE_FAULT in result["not_measured"]
    json.dumps(result, allow_nan=False)


def test_ankle_copied_from_knee_at_contact_skips_stance_without_metadata(sample: dict) -> None:
    swing = _with(sample)
    c = swing["contactFrame"]
    swing["frames"][c]["joints"][R_ANKLE] = list(swing["frames"][c]["joints"][R_KNEE])
    m, result = _stance_result(swing)
    assert m["stance_skipped"] == "joint 28 copied from knee at contact"
    assert STANCE_FAULT not in [result["fault"]["id"]] + result["other_faults"]


def test_ankle_missing_at_contact_skips_stance(sample: dict) -> None:
    swing = _with(sample)
    swing["frames"][swing["contactFrame"]]["joints"][L_ANKLE] = [0.0, 0.0, 0.0]  # pipeline's "lost"
    m, _ = _stance_result(swing)
    assert m["stance_skipped"] == "joint 27 missing at contact"
    assert m["stance_open_deg"] is None and m["stance_width_ratio"] is None


def test_copy_away_from_contact_or_other_filled_joints_keep_stance(sample: dict) -> None:
    swing = _with(sample, metadata={"approximatedJoints": [19, 20, 31, 32]})  # hands and toes only
    swing["frames"][0]["joints"][R_ANKLE] = list(swing["frames"][0]["joints"][R_KNEE])  # not contact
    m, result = _stance_result(swing)
    assert m["stance_skipped"] is None
    assert result["fault"]["id"] == STANCE_FAULT


def test_other_faults_still_fire_when_stance_is_skipped(sample: dict) -> None:
    clean = {f["id"] for f in detect_faults(sample, "backhand")}
    swing = _with(sample, metadata={"approximatedJoints": [L_ANKLE, R_ANKLE]})
    skipped = {f["id"] for f in detect_faults(swing, "backhand")}
    assert skipped == clean - {STANCE_FAULT}


# ---- A filled-in index finger never produces a wrist fault --------------------------

WRIST_FAULT = "early_wrist_snap"
R_WRIST, L_INDEX, R_INDEX = 16, 19, 20  # the sample is right-handed


def test_real_index_is_measured(sample: dict) -> None:
    m = measure_swing(sample, "forehand")
    assert m["wrist_skipped"] is None and math.isfinite(m["wrist_angle_change_pre_deg"])
    assert WRIST_FAULT in {f["id"] for f in detect_faults(sample, metrics=m)}  # real fault on the sample


def test_index_listed_as_approximated_skips_wrist_angle(sample: dict) -> None:
    swing = _with(sample, metadata={"approximatedJoints": [R_INDEX]})
    m = measure_swing(swing, "forehand")
    assert m["wrist_angle_change_pre_deg"] is None
    assert m["wrist_skipped"] == "joint 20 approximated"
    result = coach_swing(swing, stroke="forehand")
    assert WRIST_FAULT not in [result["fault"]["id"]] + result["other_faults"]
    assert WRIST_FAULT in result["not_measured"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("frame_offset", [-30, 0])  # before contact, and at contact
def test_index_copied_onto_wrist_up_to_contact_skips_wrist_angle(sample: dict, frame_offset: int) -> None:
    swing = _with(sample)
    f = swing["contactFrame"] + frame_offset
    swing["frames"][f]["joints"][R_INDEX] = list(swing["frames"][f]["joints"][R_WRIST])
    m = measure_swing(swing, "forehand")
    assert m["wrist_skipped"] == f"joint 20 copied from wrist at frame {f}"
    assert m["wrist_angle_change_pre_deg"] is None
    assert WRIST_FAULT not in {x["id"] for x in detect_faults(swing, metrics=m)}


def test_copy_after_contact_or_off_side_index_keeps_wrist_angle(sample: dict) -> None:
    swing = _with(sample, metadata={"approximatedJoints": [L_INDEX, 27]})  # non-hitting index, an ankle
    after = swing["contactFrame"] + 5
    swing["frames"][after]["joints"][R_INDEX] = list(swing["frames"][after]["joints"][R_WRIST])
    m = measure_swing(swing, "forehand")
    assert m["wrist_skipped"] is None and math.isfinite(m["wrist_angle_change_pre_deg"])
    assert m["stance_skipped"] is not None  # the ankle is still handled separately


def test_left_hander_checks_the_left_index(sample: dict) -> None:
    from coach.measure_extra import wrist_index_filled

    c = sample["contactFrame"]
    assert wrist_index_filled({**sample, "metadata": {"approximatedJoints": [L_INDEX]}}, "L", c) == "joint 19 approximated"
    assert wrist_index_filled({**sample, "metadata": {"approximatedJoints": [R_INDEX]}}, "L", c) is None


def test_other_faults_still_fire_when_wrist_is_skipped(sample: dict) -> None:
    clean = {f["id"] for f in detect_faults(sample, "forehand")}
    swing = _with(sample, metadata={"approximatedJoints": [R_INDEX]})
    skipped = {f["id"] for f in detect_faults(swing, "forehand")}
    assert skipped == clean - {WRIST_FAULT}


def test_filled_index_also_drops_release_timing(sample: dict) -> None:
    swing = _with(sample, metadata={"approximatedJoints": [R_INDEX]})
    m = measure_swing(swing, "backhand")
    for key in ("wrist_angle_change_pre_deg", "wrist_release_ms", "wrist_uncock_deg", "wrist_uncock_ms"):
        assert m[key] is None, key
    assert WRIST_FAULT not in {f["id"] for f in detect_faults(swing, metrics=m)}  # backhand rule too
    json.dumps(coach_swing(swing, stroke="backhand"), allow_nan=False)


# ---- Early wrist snap needs the wrist to RELEASE (open) before contact ---------------

def _wrist_curve(kind: str, n: int, c: int, fps: float) -> "np.ndarray":
    """Inside wrist angle per frame (180 = in line, smaller = cocked)."""
    import numpy as np

    f = np.arange(n, dtype=float)
    cocked = np.interp(f, [0, c - 60, c - 40], [170, 170, 110])  # cock to 110 deg during prep
    if kind == "held":  # cock, then hold through contact and after
        return cocked
    if kind == "increasing":  # keeps cocking right up to contact, and after
        return np.interp(f, [0, c, n - 1], [170, 110, 100])
    if kind == "early_release":  # opens fully ~100 ms before contact
        start, end = c - round(0.125 * fps), c - round(0.075 * fps)
        return np.where(f < start, cocked, np.interp(f, [start, end], [110, 170]))
    if kind == "after_contact":  # holds the cock until contact, opens just after
        return np.where(f <= c, cocked, np.interp(f, [c, c + round(0.03 * fps)], [110, 170]))
    raise ValueError(kind)


@pytest.mark.parametrize("kind, fires", [
    ("held", False), ("increasing", False), ("after_contact", False), ("early_release", True),
])
@pytest.mark.parametrize("stroke", STROKES)
def test_early_wrist_snap_only_for_a_release_before_contact(
    monkeypatch: pytest.MonkeyPatch, kind: str, fires: bool, stroke: str,
) -> None:
    import numpy as np

    swing = make_swing()  # 240 fps mock forehand; only the wrist curve is replaced
    m0 = measure(swing)
    c, n, fps = m0["contact_frame"], len(swing["frames"]), m0["fps_real"]
    curve = _wrist_curve(kind, n, c, fps)
    monkeypatch.setattr("coach.measure_extra.wrist_angle", lambda P, hand: curve.copy())

    m = measure_swing(swing, stroke)
    got = WRIST_FAULT in {f["id"] for f in detect_faults(swing, metrics=m)}
    assert got is fires, (kind, m["wrist_uncock_deg"], m["wrist_uncock_ms"])
    if kind in ("held", "increasing"):
        # The old unsigned range (max - min = 60 deg) would have called this an early snap.
        assert np.nanmax(curve[: c + 1]) - np.nanmin(curve[: c + 1]) >= 60
        assert m["wrist_uncock_deg"] < 1 and m["wrist_uncock_ms"] is None
    if kind == "early_release":
        assert m["wrist_uncock_deg"] > 55 and 60 < m["wrist_uncock_ms"] < 140
    if kind == "after_contact":
        assert m["wrist_uncock_ms"] is None or m["wrist_uncock_ms"] <= 0


def test_directional_release_matches_physics_on_a_clean_swing(sample: dict) -> None:
    m = measure_swing(sample, "backhand")
    assert m["wrist_uncock_ms"] == pytest.approx(m["wrist_release_ms"])  # 56.1 ms: a real opening


# ---- Hitting hand comes from metadata.hand when the pipeline recorded it ------------

@pytest.mark.parametrize("hand", ["R", "L"])
def test_metadata_hand_is_used_instead_of_guessing(sample: dict, hand: str) -> None:
    m = measure_swing(_with(sample, metadata={"hand": hand}), "backhand")
    assert m["hand"] == hand and m["hand_source"] == "recorded"


def test_top_level_hand_counts_as_recorded_like_physics(sample: dict) -> None:
    # physics.skeleton.swing_hand (PR #36) also trusts swing["hand"]; the coach agrees.
    m = measure_swing(_with(sample, hand="L"), "backhand")
    assert m["hand"] == "L" and m["hand_source"] == "recorded"
    both = _with(sample, hand="R", metadata={"hand": "L"})  # metadata wins, as in physics
    assert measure_swing(both, "backhand")["hand"] == "L"


@pytest.mark.parametrize("swing_extra", [
    {}, {"hand": "L"}, {"metadata": {"hand": "L"}}, {"metadata": {"hand": "X"}, "hand": "L"},
    {"metadata": {"hand": "R"}, "hand": "L"},
])
def test_coach_and_physics_always_pick_the_same_hand(sample: dict, swing_extra: dict) -> None:
    from coach.measure_extra import recorded_hand, resolve_hand
    from physics.skeleton import swing_hand

    swing = _with(sample, **swing_extra)
    assert resolve_hand(swing) == swing_hand(swing) == measure_swing(swing, "backhand")["hand"]
    assert recorded_hand(swing) in (None, swing_hand(swing))


@pytest.mark.parametrize("metadata", [None, {}, {"hand": "X"}, {"hand": None}])
def test_hand_is_guessed_only_without_valid_metadata(sample: dict, metadata) -> None:
    swing = dict(sample) if metadata is None else _with(sample, metadata=metadata)
    m = measure_swing(swing, "backhand")
    assert m["hand"] == "R" and m["hand_source"] == "detected"  # the sample's faster wrist


def test_stroke_side_and_stance_use_the_recorded_hand(sample: dict) -> None:
    from coach.measure_extra import resolve_hand, stance_open_deg, stroke_side

    lefty = _with(sample, metadata={"hand": "L"})
    assert resolve_hand(lefty) == "L" and resolve_hand(lefty, "R") == "R"  # explicit still wins
    assert stroke_side(lefty) == stroke_side(sample, "L")
    assert stance_open_deg(lefty) == stance_open_deg(sample, "L")


# ---- Forehand stance ghost and pairing with turn_shoulders_less --------------------

def test_forehand_stance_ghost_amount_is_in_stance_degrees() -> None:
    m = neutral_metrics("forehand")
    m["stance_width_ratio"] = 0.85  # fault measured on feet spacing...
    m["stance_open_deg"] = 70.0  # ...ghost amount from the angle close_stance edits
    f = _fault(m, "stance_too_open")
    assert f["fix"] == "close_stance" and f["fix_unit"] == "deg"
    assert f["fix_amount"] == pytest.approx(45.0)  # 70 - 25
    assert f["ghost_ready"] is ("close_stance" in FIXES)
    assert f["tip"] == FAULTS["stance_too_open"]["tip"]

    m["stance_open_deg"] = 20.0  # already closed by angle: nothing to animate
    f = _fault(m, "stance_too_open")
    assert f["fix_amount"] == 0.0 and f["ghost_ready"] is False


def _coach_on(monkeypatch: pytest.MonkeyPatch, sample: dict, m: dict) -> dict:
    m.setdefault("stroke_source", "given")
    monkeypatch.setattr("coach.agent.measure_swing", lambda swing, stroke, fps_real: m)
    return coach_swing(sample, stroke=m["stroke"])


def test_close_stance_pairs_with_turn_shoulders_less(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    monkeypatch.setitem(FIXES, "close_stance", ("stance_open", -1.0))
    monkeypatch.setitem(FIXES, "turn_shoulders_less", ("shoulder_turn", -1.0))
    m = neutral_metrics("forehand")
    m.update(stance_width_ratio=0.85, stance_open_deg=70.0,  # open stance
             hip_turn_range_deg=110.0, shoulder_turn_deg=100.0)  # over-rotation
    result = _coach_on(monkeypatch, sample, m)
    assert result["fault"]["id"] == "stance_too_open" and result["ghost_fix"] == "close_stance"
    assert result["ghost_fixes"] == [{"fix": "close_stance", "amount": 45.0},
                                     {"fix": "turn_shoulders_less", "amount": 15.0}]
    assert result["ghost_edits"] == {"stance_open": -45.0, "shoulder_turn": -15.0}
    assert result["tip"] == FAULTS["stance_too_open"]["tip"]
    json.dumps(result, allow_nan=False)


def test_no_pair_when_partner_cannot_be_animated(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    monkeypatch.setitem(FIXES, "close_stance", ("stance_open", -1.0))
    m = neutral_metrics("forehand")
    m.update(stance_width_ratio=0.85, stance_open_deg=70.0,
             hip_turn_range_deg=110.0, shoulder_turn_deg=80.0)  # hips over-rotate, shoulders don't
    result = _coach_on(monkeypatch, sample, m)
    assert "over_rotation" in result["other_faults"]
    assert result["ghost_fixes"] == [{"fix": "close_stance", "amount": 45.0}]
    assert result["ghost_edits"] == {"stance_open": -45.0}


def test_paired_edits_run_in_physics_on_the_real_sample(sample: dict) -> None:
    from physics.ghost import edit_swing

    ghost = edit_swing(sample, {"stance_open": -45.0, "shoulder_turn": -15.0})
    assert ghost["synthetic"] is True
    assert [e["id"] for e in ghost["edits"]] == ["stance_open", "shoulder_turn"]
    assert measure(ghost)["stance_open_deg"] < measure(sample)["stance_open_deg"]


def test_single_ghost_has_one_fix_and_matching_edits(sample: dict) -> None:
    result = coach_swing(sample, stroke="backhand")
    assert len(result["ghost_fixes"]) == 1
    assert result["ghost_fixes"][0] == {"fix": result["ghost_fix"], "amount": result["ghost_fix_amount"]}
    edit, sign = FIXES[result["ghost_fix"]]
    assert result["ghost_edits"] == {edit: sign * result["ghost_fix_amount"]}


# ---- A rule can be switched off when it can't separate good from faulty swings -----

def test_disabled_rule_never_fires(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    from coach.faults import disabled_faults

    rule = THRESHOLDS["forehand"]["early_wrist_snap"]
    monkeypatch.setitem(rule, "disabled", "good and early-wrist blocks overlap")
    m = neutral_metrics("forehand")
    m[rule["measurement"]] = rule["severe_at"]
    assert detect_faults({}, metrics=m) == []
    assert "early_wrist_snap" not in unmeasured_faults(m)
    assert disabled_faults("forehand") == {"early_wrist_snap": "good and early-wrist blocks overlap"}
    assert coach_swing(sample, stroke="forehand")["disabled_faults"] == disabled_faults("forehand")
    assert disabled_faults("backhand") == {}
