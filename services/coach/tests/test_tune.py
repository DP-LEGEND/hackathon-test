"""Tests for the threshold tuning report. Offline; uses the real labels.csv and sample swing."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from coach.tune import MIN_SWINGS, best_threshold, current_rule_score, load_labels, load_swings, tune

ROOT = Path(__file__).resolve().parents[3]
LABELS = ROOT / "data" / "labels" / "labels.csv"
SAMPLE = ROOT / "data" / "samples" / "swing_sample.json"


def test_separable_values_get_a_clean_threshold() -> None:
    b = best_threshold([1, 2, 3, 4, 5], [8, 9, 10, 11, 12])
    assert b["fires"] == "above" and 5 < b["threshold"] < 8
    assert b["balanced_accuracy"] == 1.0 and b["fault_flagged"] == 1.0 and b["good_flagged"] == 0.0
    assert (b["good_median"], b["fault_median"], b["n_good"], b["n_fault"]) == (3, 10, 5, 5)


def test_faults_that_read_lower_fire_below() -> None:
    b = best_threshold([1.6, 1.7, 1.8, 1.9], [0.8, 0.9, 1.0])  # e.g. feet spacing halves
    assert b["fires"] == "below" and 1.0 < b["threshold"] < 1.6 and b["balanced_accuracy"] == 1.0


def test_overlapping_values_score_low_and_missing_values_are_ignored() -> None:
    b = best_threshold([1, 5, 9, 3, 7, float("nan")], [2, 6, 8, 4, None])  # type: ignore[list-item]
    assert b["balanced_accuracy"] < 0.75 and b["n_good"] == 5 and b["n_fault"] == 4
    assert best_threshold([], [1.0]) is None and best_threshold([1.0], [None]) is None  # type: ignore[list-item]


def test_current_rule_score_reports_both_blocks() -> None:
    rule = {"threshold": 40.0, "severe_at": 100.0, "target": 10.0}
    s = current_rule_score(rule, good=[108, 110, 20, 30], fault=[120, 130])
    assert s == {"threshold": 40.0, "fault_flagged": 1.0, "good_flagged": 0.5}  # flags half the good swings


def test_real_labels_load_without_unlabelled_rows() -> None:
    rows = load_labels(LABELS)
    assert rows and all(r["intended_fault"] != "unlabelled" for r in rows)
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        counts[(r["side"], r["intended_fault"])] = counts.get((r["side"], r["intended_fault"]), 0) + 1
    assert counts[("forehand", "none")] == 23 and counts[("forehand", "early_wrist")] == 3
    assert counts[("backhand", "rolled_wrist")] == 25


def test_swings_load_from_single_list_and_wrapped_files(tmp_path: Path) -> None:
    one = {"id": "a", "frames": []}
    (tmp_path / "one.json").write_text(json.dumps(one))
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "many.json").write_text(json.dumps([{"id": "b", "frames": []}, {"id": "c", "frames": []}]))
    (tmp_path / "wrapped.json").write_text(json.dumps({"swings": [{"id": "d", "frames": []}], "report": {}}))
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "other.json").write_text(json.dumps({"not": "a swing"}))
    assert sorted(load_swings(tmp_path)) == ["a", "b", "c", "d"]


def _labels(side: str, block: str, n: int, start: int = 0) -> list[dict[str, str]]:
    return [{"side": side, "intended_fault": block, "swing": f"{block}-{i}"} for i in range(start, start + n)]


def test_report_sets_separable_faults_and_disables_the_rest() -> None:
    labels = (_labels("forehand", "none", 8) + _labels("forehand", "open_stance", 8)
              + _labels("forehand", "early_wrist", 3) + _labels("forehand", "over_rotation", 8))
    swings = {row["swing"]: {"id": row["swing"]} for row in labels}

    def fake_measure(swing: dict, stroke: str) -> dict:
        block, i = swing["id"].rsplit("-", 1)
        i = int(i)
        open_ = block == "open_stance"
        return {
            "stance_width_ratio": (0.9 if open_ else 1.7) + i * 0.01,  # separates cleanly
            "stance_open_deg": 30 + (i * 7) % 40,  # same spread in both blocks
            "hip_turn_range_deg": 60 + (i * 9) % 50,  # over-rotation can't be told apart
            "shoulder_turn_deg": 60 + (i * 9) % 50,
            "wrist_uncock_deg": 70.0 if block == "early_wrist" else 20.0,
        }

    report = tune(labels, swings, measure=fake_measure)
    assert report["missing"] == 0 and report["failed"] == []

    stance = report["faults"]["forehand/stance_too_open"]
    assert stance["verdict"]["action"] == "set"
    rule = stance["verdict"]["rule"]
    assert rule["measurement"] == "stance_width_ratio" and 0.97 < rule["threshold"] < 1.7
    assert rule["target"] > rule["threshold"] > rule["severe_at"]  # fires below, like the code
    current = next(o for o in stance["options"] if "current" in o)["current"]
    assert current["good_flagged"] == 0.0

    wrist = report["faults"]["forehand/early_wrist_snap"]
    assert wrist["verdict"] == {"action": "disable", "why": f"fewer than {MIN_SWINGS} measured good or fault swings"}

    over = report["faults"]["forehand/over_rotation"]
    assert over["verdict"]["action"] == "disable" and "separation" in over["verdict"]["why"]


def test_report_counts_missing_and_failed_swings() -> None:
    labels = _labels("forehand", "none", 2) + _labels("forehand", "open_stance", 2)
    swings = {"none-0": {"id": "none-0"}, "open_stance-0": {"id": "open_stance-0"}}

    def boom(swing: dict, stroke: str) -> dict:
        raise ValueError("swing has no frames")

    report = tune(labels, swings, measure=boom)
    assert report["missing"] == 2 and len(report["failed"]) == 2
    assert "swing has no frames" in report["failed"][0]


@pytest.mark.parametrize("block", ["open_stance"])
def test_real_measurement_on_identical_swings_cannot_separate(block: str) -> None:
    sample = json.loads(SAMPLE.read_text())
    labels = _labels("backhand", "none", MIN_SWINGS) + _labels("backhand", block, MIN_SWINGS)
    swings = {row["swing"]: {**copy.deepcopy(sample), "id": row["swing"]} for row in labels}
    report = tune(labels, swings)  # the real measure_swing
    assert report["failed"] == []
    assert report["faults"]["backhand/stance_too_open"]["verdict"]["action"] == "disable"
