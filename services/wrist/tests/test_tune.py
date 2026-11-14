"""Choosing the rolled_wrist threshold from labelled swings."""

from __future__ import annotations

from pathlib import Path

import pytest

from coach.faults import MEASUREMENTS, THRESHOLDS, WRIST_MOCK, WRIST_SENSOR, severity
from wrist.tune import read_labels, separation, tune
from wrist.tune import _verdict as verdict


def _metrics(normal: list[float], rolled: list[float], mock: bool = False) -> tuple[dict, dict]:
    swings, labels = {}, {}
    for lab, vals in (("none", normal), ("rolled_wrist", rolled)):
        for i, v in enumerate(vals):
            sid = f"{lab}-{i}"
            swings[sid] = {"usable": True, "roll_change_abs_deg": v, "peak_roll_rate_abs_dps": v * 8}
            labels[sid] = lab
    return {"mock": mock, "swings": swings}, labels


def test_clean_split_threshold_is_halfway_between_medians() -> None:
    sep = separation([10, 12, 15, 18, 20], [50, 55, 60, 62, 70])
    assert sep["threshold"] == pytest.approx((15 + 60) / 2)
    assert sep["fires"] == "above" and sep["margin"] == 30
    assert sep["in_sample"] == {"rolled_flagged": 1.0, "normal_flagged": 0.0, "balanced_accuracy": 1.0}
    assert sep["leave_one_out_accuracy"] == 1.0 and sep["cohens_d"] > 3


def test_overlap_is_reported_and_no_rule_is_set() -> None:
    metrics, labels = _metrics([10, 30, 45, 50, 20], [25, 40, 48, 35, 55])
    report = tune(metrics, labels)
    o = report["options"]["roll_change_abs_deg"]
    assert o["margin"] < 0 and o["leave_one_out_accuracy"] < 0.8
    assert report["verdict"]["action"] == "no_rule" and "don't separate" in report["verdict"]["why"]


def test_fewer_than_five_per_group_sets_no_rule() -> None:
    metrics, labels = _metrics([10, 12, 15, 18], [50, 55, 60, 62, 70])
    v = tune(metrics, labels)["verdict"]
    assert v["action"] == "no_rule" and "4 normal" in v["why"]


def test_rolled_rolling_less_is_flagged_not_set() -> None:
    metrics, labels = _metrics([50, 55, 60, 62, 70], [10, 12, 15, 18, 20])
    v = tune(metrics, labels)["verdict"]
    assert v["action"] == "check" and "--axis" in v["why"]


def test_set_rule_is_honest_and_pastes_into_faults() -> None:
    metrics, labels = _metrics([10, 12, 15, 18, 20], [50, 55, 60, 62, 70])
    v = tune(metrics, labels)["verdict"]
    assert v["action"] == "set"
    rule = v["rule"]
    assert rule["source"] == WRIST_SENSOR and rule["measurement"] in MEASUREMENTS
    assert severity(rule["target"], rule) == 0 and severity(rule["severe_at"], rule) == 1
    assert "5 vs 5" in v["honest"] and "provisional" in v["honest"] and "MOCK" not in v["honest"]
    mock_v = tune(*_metrics([10, 12, 15, 18, 20], [50, 55, 60, 62, 70], mock=True))["verdict"]
    assert mock_v["rule"]["source"] == WRIST_MOCK and mock_v["honest"].startswith("MOCK")


def test_unusable_and_unknown_swings_are_skipped_and_listed() -> None:
    metrics, labels = _metrics([10, 12, 15, 18, 20], [50, 55, 60, 62, 70])
    metrics["swings"]["none-0"] = {"usable": False, "skip_reason": "alignment error 300 ms > 100 ms"}
    labels["nowhere"] = "rolled_wrist"
    labels["other"] = "straight_arm"  # not part of this fault
    report = tune(metrics, labels)
    assert report["n_normal"] == 4 and report["n_rolled"] == 5
    assert {s["swing"] for s in report["skipped"]} == {"none-0", "nowhere"}


def test_ties_keep_roll_change_the_primary_number() -> None:
    sep = separation([10, 12, 15, 18, 20], [50, 55, 60, 62, 70])
    v = verdict({"roll_change_abs_deg": sep, "peak_roll_rate_abs_dps": sep}, 5, 5, False)
    assert v["measurement"] == "roll_change_abs_deg"


def test_committed_mock_rule_is_what_tune_picks_on_the_mock_session(session) -> None:
    """faults.py's rolled_wrist numbers come from this exact mock run (seed 0)."""
    labels = {sid: t["label"] for sid, t in session.truth["swings"].items()}
    v = tune(session.metrics, labels)["verdict"]
    assert v["action"] == "set"
    for stroke in THRESHOLDS:
        assert THRESHOLDS[stroke]["rolled_wrist"] == v["rule"]


def test_read_labels_filters_a_run(tmp_path: Path) -> None:
    p = tmp_path / "labels.csv"
    p.write_text("swing,intended_fault,pipeline_run\na@bh-05,none,bh-05\nb@bh-05,rolled_wrist,bh-05\nc,none,bh-04\n")
    assert read_labels(p, "bh-05") == {"a": "none", "b": "rolled_wrist"}
    assert read_labels(p) == {"a@bh-05": "none", "b@bh-05": "rolled_wrist", "c": "none"}
