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
    swings = load_swings(tmp_path)
    assert sorted(k for k in swings if "@" not in k) == ["a", "b", "c", "d"]  # unique ids keep a bare key
    assert swings["b"] is swings["b@sub"] and swings["a"] is swings[f"a@{tmp_path.name}"]


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
    assert wrist["verdict"] == {"action": "disable", "why": f"fewer than {MIN_SWINGS} measured fault swings"}

    over = report["faults"]["forehand/over_rotation"]
    assert over["verdict"]["action"] == "disable" and "separation" in over["verdict"]["why"]  # identical blocks: 0.5


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


# ---- Review fixes on #38: rounded threshold scored, rule direction preserved --------

from coach.faults import severity  # noqa: E402
from coach.tune import DECIMALS, rule_problem  # noqa: E402


def _rule(best: dict) -> dict:
    """The faults.py rule a "set" verdict would write for this best threshold."""
    return {"threshold": best["threshold"], "severe_at": best["fault_median"], "target": best["good_median"]}


def _applied_rates(rule: dict, good: list[float], fault: list[float]) -> tuple[float, float]:
    return (round(sum(severity(v, rule) > 0 for v in fault) / len(fault), 3),
            round(sum(severity(v, rule) > 0 for v in good) / len(good), 3))


def test_threshold_is_rounded_before_it_is_scored() -> None:
    # Codex P2: values 0.0001 apart used to report a perfect split at threshold 1.0.
    b = best_threshold([1.0001], [1.0002])
    assert b["threshold"] == round(b["threshold"], DECIMALS) == 1.0
    assert b["fault_flagged"] == 1.0 and b["good_flagged"] == 1.0  # what 1.0 really does
    assert b["balanced_accuracy"] == 0.5
    assert rule_problem(b) is not None  # threshold == severe_at == target: never recommended


@pytest.mark.parametrize("good, fault", [
    ([1.2101, 1.2102, 1.2049, 1.2, 1.19], [1.2106, 1.2107, 1.25, 1.3, 1.26]),  # near-ties at 3 decimals
    ([30.0, 31.5, 29.0, 35.0, 28.0], [61.0, 58.0, 63.5, 40.0, 70.0]),
    ([1.7, 1.6, 1.8, 1.65, 1.75], [0.9, 0.85, 1.1, 1.62, 0.95]),  # faults read lower
])
def test_reported_hit_rates_are_those_of_the_rule_that_gets_applied(good, fault) -> None:
    b = best_threshold(good, fault)
    assert rule_problem(b) is None
    assert _applied_rates(_rule(b), good, fault) == (b["fault_flagged"], b["good_flagged"])


def test_near_ties_report_the_rounded_cut_honestly() -> None:
    # Unrounded, the midpoint 1.2104 separates perfectly; at 3 decimals no cut does, and
    # the report must say so instead of claiming a perfect split.
    b = best_threshold([1.2101, 1.2102, 1.2049, 1.2, 1.19], [1.2106, 1.2107, 1.25, 1.3, 1.26])
    assert b["threshold"] == 1.208 and b["good_flagged"] == 0.4 and b["balanced_accuracy"] == 0.8


@pytest.mark.parametrize("good, fault", [
    ([1.21, 1.24, 1.26, 1.3, 1.33], [1.2104, 1.2499, 1.27, 1.4, 1.5]),  # best cut lands past the fault median
    ([5, 5, 5, 5], [0, 0, 10, 10]),
    ([1.0001], [1.0002]),
])
def test_backwards_or_zero_span_cuts_are_flagged(good, fault) -> None:
    assert rule_problem(best_threshold(good, fault)) is not None


def test_codex_borderline_case_is_never_recommended_backwards(monkeypatch: pytest.MonkeyPatch) -> None:
    # Codex P1: good [5,5,5,5] vs fault [0,0,10,10] picks "fires above 7.5" (score 0.75) but
    # the fault median is 5, so a {threshold 7.5, severe_at 5} rule would fire BELOW.
    b = best_threshold([5, 5, 5, 5], [0, 0, 10, 10])
    assert (b["fires"], b["threshold"], b["balanced_accuracy"], b["fault_median"]) == ("above", 7.5, 0.75, 5)
    assert "backwards" in rule_problem(b)

    monkeypatch.setattr("coach.tune.MIN_SWINGS", 4)
    labels = _labels("forehand", "none", 4) + _labels("forehand", "over_rotation", 4)
    values = {"none": [5, 5, 5, 5], "over_rotation": [0, 0, 10, 10]}

    def measure(swing: dict, stroke: str) -> dict:
        block, i = swing["id"].rsplit("-", 1)
        v = values[block][int(i)]
        return {"hip_turn_range_deg": v, "shoulder_turn_deg": v}

    report = tune(labels, {r["swing"]: {"id": r["swing"]} for r in labels}, measure=measure)
    verdict = report["faults"]["forehand/over_rotation"]["verdict"]
    assert verdict["action"] == "keep" and "right direction" in verdict["why"]  # separates (0.75), never "set" backwards


def test_direction_flips_when_the_fault_block_reads_lower() -> None:
    # The current over_rotation rule fires ABOVE (more hip turn = fault). If the labelled
    # fault block actually reads LOWER, the recommendation must fire below, not copy the
    # current direction, and applying it must flag faults and not good swings.
    labels = _labels("forehand", "none", 6) + _labels("forehand", "over_rotation", 6)
    good = [100.0, 104.0, 98.0, 110.0, 102.0, 106.0]
    fault = [70.0, 66.0, 75.0, 62.0, 80.0, 68.0]
    values = {"none": good, "over_rotation": fault}

    def measure(swing: dict, stroke: str) -> dict:
        block, i = swing["id"].rsplit("-", 1)
        return {"hip_turn_range_deg": values[block][int(i)], "shoulder_turn_deg": 80.0}

    report = tune(labels, {r["swing"]: {"id": r["swing"]} for r in labels}, measure=measure)
    item = report["faults"]["forehand/over_rotation"]
    hip = next(o for o in item["options"] if o["measurement"] == "hip_turn_range_deg")
    assert hip["best"]["fires"] == "below"
    assert hip["current"]["good_flagged"] > hip["current"]["fault_flagged"]  # today's rule is backwards here

    assert item["verdict"]["action"] == "set"
    rule = item["verdict"]["rule"]
    assert rule["measurement"] == "hip_turn_range_deg"
    assert rule["severe_at"] < rule["threshold"] < rule["target"]  # severity() reads "fires below"
    assert _applied_rates(rule, good, fault) == (1.0, 0.0)


def test_every_set_verdict_applies_with_its_reported_hit_rates() -> None:
    labels = (_labels("forehand", "none", 7) + _labels("forehand", "open_stance", 7)
              + _labels("forehand", "straight_arm", 7))
    data = {
        "none": {"stance_width_ratio": [1.70, 1.66, 1.74, 1.69, 1.81, 1.62, 1.72],
                 "elbow_at_contact_deg": [140, 145, 150, 138, 147, 152, 143]},
        "open_stance": {"stance_width_ratio": [0.91, 0.88, 1.20, 0.97, 1.65, 0.85, 1.02]},
        "straight_arm": {"elbow_at_contact_deg": [168, 171, 149, 174, 166, 177, 170]},
    }

    def measure(swing: dict, stroke: str) -> dict:
        block, i = swing["id"].rsplit("-", 1)
        return {k: v[int(i)] for k, v in data[block].items()}

    report = tune(labels, {r["swing"]: {"id": r["swing"]} for r in labels}, measure=measure)
    checked = 0
    for key, item in report["faults"].items():
        if item["verdict"]["action"] != "set":
            continue
        rule = item["verdict"]["rule"]
        block = item["label"]
        good = data["none"][rule["measurement"]]
        fault = data[block][rule["measurement"]]
        best = next(o["best"] for o in item["options"] if o["measurement"] == rule["measurement"])
        assert _applied_rates(rule, good, fault) == (best["fault_flagged"], best["good_flagged"]), key
        checked += 1
    assert checked == 2


# ---- Review fix on #38: tied scores prefer a cut that forms a usable rule -----------

def test_tied_cuts_prefer_the_one_that_forms_a_rule() -> None:
    # Codex P2: cuts 0.5 and 1.5 both score 0.75; 0.5 equals the good median (unusable),
    # 1.5 lies strictly between the medians and must be the one kept.
    good, fault = [0, 0, 0, 1, 1, 2], [1, 1, 2, 2, 2, 2]
    b = best_threshold(good, fault)
    assert (b["threshold"], b["balanced_accuracy"], b["fires"]) == (1.5, 0.75, "above")
    assert rule_problem(b) is None
    assert _applied_rates(_rule(b), good, fault) == (b["fault_flagged"], b["good_flagged"]) == (0.667, 0.167)


def test_tie_break_reaches_the_report_as_a_set_rule() -> None:
    good, fault = [0, 0, 0, 1, 1, 2], [1, 1, 2, 2, 2, 2]
    labels = _labels("backhand", "none", 6) + _labels("backhand", "straight_arm", 6)
    values = {"none": good, "straight_arm": fault}

    def measure(swing: dict, stroke: str) -> dict:
        block, i = swing["id"].rsplit("-", 1)
        return {"elbow_min_before_deg": values[block][int(i)]}

    report = tune(labels, {r["swing"]: {"id": r["swing"]} for r in labels}, measure=measure)
    verdict = report["faults"]["backhand/straight_arm"]["verdict"]
    assert verdict == {"action": "set", "rule": {"measurement": "elbow_min_before_deg", "threshold": 1.5,
                                                 "severe_at": 2.0, "target": 0.5}}


def test_a_higher_score_still_wins_over_a_usable_lower_one() -> None:
    # Score comes first: cut 2.5 scores 1.0 and is kept over usable cuts scoring 0.75.
    b = best_threshold([0, 0, 2, 2], [5, 5, 3, 3])
    assert (b["threshold"], b["balanced_accuracy"]) == (2.5, 1.0) and rule_problem(b) is None


def test_two_usable_tied_cuts_keep_the_lower_one() -> None:
    # Cuts 1.0 and 4.5 both score 0.875 and both lie strictly between the medians (0 and 7.5).
    good, fault = [0, 0, 0, 2], [2, 7, 8, 9]
    b = best_threshold(good, fault)
    assert (b["threshold"], b["balanced_accuracy"]) == (1.0, 0.875) and rule_problem(b) is None
    other = {**b, "threshold": 4.5}
    assert rule_problem(other) is None
    assert _applied_rates(_rule(other), good, fault)[0] < b["fault_flagged"] or \
        _applied_rates(_rule(other), good, fault)[1] < b["good_flagged"]  # a genuinely different cut, same score


# ---- Disable only below 0.7 balanced accuracy or with fewer than 5 fault swings -----

from coach.tune import MIN_SEPARATION, recommend  # noqa: E402


def _verdict(good: list[float], fault: list[float], with_good: bool = True) -> dict:
    """tune() verdict for backhand straight_arm with these elbow values per block."""
    labels = (_labels("backhand", "none", len(good)) if with_good else []) + \
        _labels("backhand", "straight_arm", len(fault))
    values = {"none": good, "straight_arm": fault}

    def measure(swing: dict, stroke: str) -> dict:
        block, i = swing["id"].rsplit("-", 1)
        return {"elbow_min_before_deg": values[block][int(i)]}

    report = tune(labels, {r["swing"]: {"id": r["swing"]} for r in labels}, measure=measure)
    return report["faults"]["backhand/straight_arm"]["verdict"]


def test_disable_rule_constants() -> None:
    assert (MIN_SEPARATION, MIN_SWINGS) == (0.7, 5)


def test_exactly_0_7_is_kept_as_a_rule_not_disabled() -> None:
    v = _verdict([0, 0, 2, 2, 3], [2, 2, 3, 3, 3])  # best cut 2.5 scores exactly 0.7
    assert v == {"action": "set", "rule": {"measurement": "elbow_min_before_deg", "threshold": 2.5,
                                           "severe_at": 3, "target": 2}}


def test_between_0_7_and_the_old_0_75_is_now_set() -> None:
    v = _verdict([0, 0, 2, 2, 2, 3], [2, 2, 3, 3, 3])  # 0.717: disabled before, a rule now
    assert v["action"] == "set" and v["rule"]["threshold"] == 2.5


def test_below_0_7_is_disabled() -> None:
    v = _verdict([0, 0, 3, 3, 3], [2, 2, 2, 3, 3])  # best 0.6
    assert v["action"] == "disable" and v["why"].startswith("best separation 0.60 < 0.7")


def test_fewer_than_5_fault_swings_is_disabled_even_if_perfectly_separable() -> None:
    v = _verdict([0, 1, 2, 3, 4, 5, 6, 7], [20, 21, 22, 23])
    assert v == {"action": "disable", "why": "fewer than 5 measured fault swings"}


def test_few_good_swings_no_longer_disable_a_separable_fault() -> None:
    v = _verdict([0, 1], [20, 21, 22, 23, 24])  # 2 good, 5 fault: the old rule needed 5 of each
    assert v["action"] == "set" and 1 < v["rule"]["threshold"] < 20


def test_fault_swings_without_any_good_ones_are_kept_not_disabled() -> None:
    v = _verdict([], [20, 21, 22, 23, 24], with_good=False)
    assert v == {"action": "keep", "why": "no good swings measured to compare against"}


def test_unmeasured_fault_swings_do_not_count() -> None:
    # 6 fault swings labelled, but only 4 have the measurement: fewer than 5 measured.
    v = _verdict([0, 1, 2, 3, 4], [20, 21, float("nan"), 23, None, 25])  # type: ignore[list-item]
    assert v == {"action": "disable", "why": "fewer than 5 measured fault swings"}


def test_recommend_only_disables_for_the_two_reasons() -> None:
    # Every "disable" says one of the two allowed reasons; anything else is set or keep.
    cases = [([0, 0, 2, 2, 3], [2, 2, 3, 3, 3]), ([0, 0, 3, 3, 3], [2, 2, 2, 3, 3]), ([5] * 5, [0, 0, 10, 10, 10]),
             ([0, 1, 2, 3, 4], [20, 21, 22]), ([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])]
    for good, fault in cases:
        v = _verdict(good, fault)
        assert v["action"] in ("set", "keep", "disable")
        if v["action"] == "disable":
            assert v["why"].startswith(("best separation", "fewer than 5 measured fault swings")), v
    assert recommend([])["action"] == "disable"  # no measurement at all: no fault swings


# ---- Review fix on #38: runs share swing ids, so swings are keyed "<id>@<run>" -------

from coach.tune import find_swing, measure_labelled  # noqa: E402

SHARED = "7178110a0b06-swing-0003"  # in both fh-04 and fh-05, as in the real labels


def _write(folder: Path, run: str, swing_id: str, marker: str) -> None:
    (folder / run).mkdir(parents=True, exist_ok=True)
    (folder / run / f"{swing_id}.json").write_text(json.dumps({"id": swing_id, "frames": [], "marker": marker}))


def _row(swing: str, run: str, block: str = "none") -> dict[str, str]:
    return {"swing": swing, "pipeline_run": run, "side": "forehand", "intended_fault": block}


def _measured(labels: list[dict[str, str]], swings: dict[str, dict]) -> tuple[list[str], list[str]]:
    seen: list[str] = []

    def record(swing: dict, stroke: str) -> dict:
        seen.append(swing["marker"])
        return {}

    return seen, measure_labelled(labels, swings, measure=record)["missing"]


def test_two_runs_with_the_same_swing_id_measure_two_different_swings(tmp_path: Path) -> None:
    _write(tmp_path, "fh-04", SHARED, "run 4")
    _write(tmp_path, "fh-05", SHARED, "run 5")
    _write(tmp_path, "fh-05", "7178110a0b06-swing-0099", "only in run 5")
    swings = load_swings(tmp_path)
    assert swings[f"{SHARED}@fh-04"]["marker"] == "run 4" and swings[f"{SHARED}@fh-05"]["marker"] == "run 5"
    assert SHARED not in swings  # shared id: no bare key, so one run can't overwrite the other
    assert swings["7178110a0b06-swing-0099"] is swings["7178110a0b06-swing-0099@fh-05"]  # unique: both keys

    # labels.csv style: fh-04 rows use the bare id, fh-05 rows carry the "@fh-05" suffix.
    labels = [_row(SHARED, "fh-04"), _row(f"{SHARED}@fh-05", "fh-05"), _row("7178110a0b06-swing-0099", "fh-05")]
    seen, missing = _measured(labels, swings)
    assert seen == ["run 4", "run 5", "only in run 5"] and missing == []


def test_a_bare_id_from_another_labelled_run_is_missing_not_measured(tmp_path: Path) -> None:
    _write(tmp_path, "fh-05", SHARED, "run 5")  # only fh-05 was given
    labels = [_row(SHARED, "fh-04"), _row(f"{SHARED}@fh-05", "fh-05")]
    seen, missing = _measured(labels, load_swings(tmp_path))
    assert seen == ["run 5"] and missing == [SHARED]  # the fh-04 label never measures fh-05's swing


def test_swings_in_one_flat_folder_still_match_bare_ids(tmp_path: Path) -> None:
    _write(tmp_path, "raw", "swing-a", "a")  # folder name isn't a labelled run
    swings = load_swings(tmp_path)
    assert find_swing(_row("swing-a", "fh-04"), swings, frozenset({"fh-04", "fh-05"}))["marker"] == "a"
    assert find_swing(_row("swing-a", ""), swings)["marker"] == "a"


def test_every_real_label_finds_its_own_runs_swing(tmp_path: Path) -> None:
    rows = load_labels(LABELS)
    assert any("@" in r["swing"] for r in rows)  # the suffixed fh-05/bh-05 ids are in there
    for r in rows:
        base, run = r["swing"].split("@")[0], r["pipeline_run"]
        assert "@" not in r["swing"] or r["swing"].endswith(f"@{run}"), r
        _write(tmp_path, run, base, f"{base}@{run}")
    seen, missing = _measured(rows, load_swings(tmp_path))
    assert missing == [] and seen == [f"{r['swing'].split('@')[0]}@{r['pipeline_run']}" for r in rows]
    assert len(set(seen)) == len(rows)  # no two labels share a swing
