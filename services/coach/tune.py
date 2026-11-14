"""Tune fault thresholds against labelled swings. Owners: aryan and Dev.

Reads data/labels/labels.csv (which block each swing was filmed in: the INTENDED fault)
and a folder of pipeline swing JSONs, measures every labelled swing with the coach, and
for each fault compares the good block ("none") with that fault's block. For every
candidate measurement it reports the threshold that best separates them (balanced
accuracy = average of "fault swings flagged" and "good swings not flagged"), and how
the CURRENT rule does. If nothing separates well, it says to disable the fault.

It never edits THRESHOLDS: read the report, then change faults.py by hand.

Run (from inside services/, swings anywhere under the folder, e.g. pipeline output):

    python -m coach.tune ../data/labels/labels.csv ../data/raw
    python -m coach.tune ../data/labels/labels.csv ../data/raw --json > tune.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Callable, Optional

from coach.faults import THRESHOLDS, measure_swing, severity

# labels.csv intended_fault -> fault id (None = the good block).
LABEL_TO_FAULT: dict[str, Optional[str]] = {
    "none": None,
    "early_wrist": "early_wrist_snap",
    "over_rotation": "over_rotation",
    "straight_arm": "straight_arm",
    "open_stance": "stance_too_open",
    "rolled_wrist": "rolling_wrist",
}

# Measurements worth trying for each fault (the current rule's is always included).
CANDIDATES: dict[str, list[str]] = {
    "early_wrist_snap": ["wrist_uncock_deg", "wrist_uncock_ms", "wrist_angle_change_pre_deg", "wrist_release_ms"],
    "over_rotation": ["hip_turn_range_deg", "shoulder_turn_deg"],
    "straight_arm": ["elbow_min_before_deg", "elbow_at_contact_deg"],
    "stance_too_open": ["stance_width_ratio", "stance_open_deg"],
    "rolling_wrist": ["forearm_roll_deg"],
}

MIN_SWINGS = 5  # per side; fewer and we can't tell
MIN_SEPARATION = 0.75  # balanced accuracy needed to keep a fault
DECIMALS = 3  # thresholds and medians are reported (and scored) at this precision


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def best_threshold(good: list[float], fault: list[float]) -> Optional[dict[str, Any]]:
    """Threshold that best separates fault values from good ones, or None if either is empty.

    Direction comes from the data: the fault block's median vs the good block's ("fires
    above" when faults read higher, "fires below" when lower). Candidate cuts are the
    midpoints between neighbouring values, ROUNDED FIRST to DECIMALS (duplicates dropped)
    and scored as rounded, so the hit rates reported are those of the threshold applied.

    Ties: when several cuts score the same, prefer one that forms a correctly directed
    rule (rule_problem() is None); among those, the lowest cut. So a usable rule is never
    dropped just because an unusable cut with the same score came first.
    """
    good = [v for v in good if _finite(v)]
    fault = [v for v in fault if _finite(v)]
    if not good or not fault:
        return None
    above = statistics.median(fault) >= statistics.median(good)
    medians = {"good_median": round(statistics.median(good), DECIMALS),
               "fault_median": round(statistics.median(fault), DECIMALS),
               "n_good": len(good), "n_fault": len(fault)}
    values = sorted(set(good + fault))
    mids = [(a + b) / 2 for a, b in zip(values, values[1:])] or [values[0]]
    cuts = sorted({round(m, DECIMALS) for m in mids})
    best: Optional[dict[str, Any]] = None
    best_key: tuple[float, bool] = (-1.0, False)
    for cut in cuts:
        flags: Callable[[float], bool] = (lambda v: v > cut) if above else (lambda v: v < cut)
        tpr = sum(map(flags, fault)) / len(fault)
        fpr = sum(map(flags, good)) / len(good)
        score = (tpr + (1 - fpr)) / 2
        candidate = {"threshold": cut, "fires": "above" if above else "below",
                     "fault_flagged": round(tpr, 3), "good_flagged": round(fpr, 3),
                     "balanced_accuracy": round(score, 3), **medians}
        # Higher score wins; on an equal score a usable rule beats an unusable one.
        key = (round(score, 9), rule_problem(candidate) is None)
        if best is None or key > best_key:
            best, best_key = candidate, key
    assert best is not None
    return best


def rule_problem(best: dict[str, Any]) -> Optional[str]:
    """Why best's threshold can't become a faults.py rule as-is, or None if it can.

    The rule is {threshold, severe_at: fault median, target: good median}, and
    severity() reads its direction from severe_at vs threshold. So the fault median
    must be strictly on the firing side and the good median strictly on the other side;
    otherwise the rule fires backwards (flagging good swings) or has zero span (raises).
    """
    t, f, g = best["threshold"], best["fault_median"], best["good_median"]
    ok = (g < t < f) if best["fires"] == "above" else (f < t < g)
    if ok:
        return None
    return (f"fault median {f} and good median {g} aren't on opposite sides of threshold {t} "
            f"(fires {best['fires']}), so the rule would read backwards or have no span")


def current_rule_score(rule: dict[str, Any], good: list[float], fault: list[float]) -> dict[str, Any]:
    """How the rule as it stands treats the good and fault blocks."""
    def flagged(vals: list[float]) -> Optional[float]:
        vals = [v for v in vals if _finite(v)]
        return round(sum(severity(v, rule) > 0 for v in vals) / len(vals), 3) if vals else None
    return {"threshold": rule["threshold"], "fault_flagged": flagged(fault), "good_flagged": flagged(good)}


def load_labels(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return [r for r in csv.DictReader(fh)
                if r.get("side") in THRESHOLDS and r.get("intended_fault") in LABEL_TO_FAULT]


def load_swings(folder: Path) -> dict[str, dict]:
    """Every swing under `folder`, by id. Files may hold one swing, a list, or {"swings": [...]}."""
    out: dict[str, dict] = {}
    for path in sorted(folder.rglob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        items = data if isinstance(data, list) else data.get("swings", [data]) if isinstance(data, dict) else []
        for s in items:
            if isinstance(s, dict) and "frames" in s and "id" in s:
                out[str(s["id"])] = s
    return out


def measure_labelled(labels: list[dict[str, str]], swings: dict[str, dict],
                     measure: Callable[..., dict] = measure_swing) -> dict[str, Any]:
    """{stroke: {block: [metrics, ...]}} plus which labels had no swing or failed to measure."""
    by_block: dict[str, dict[str, list[dict]]] = {s: {} for s in THRESHOLDS}
    missing, failed = [], []
    for row in labels:
        swing = swings.get(row["swing"])
        if swing is None:
            missing.append(row["swing"])
            continue
        try:
            m = measure(swing, row["side"])
        except Exception as exc:  # one bad swing must not stop the report
            failed.append(f"{row['swing']}: {exc}")
            continue
        by_block[row["side"]].setdefault(row["intended_fault"], []).append(m)
    return {"metrics": by_block, "missing": missing, "failed": failed}


def tune(labels: list[dict[str, str]], swings: dict[str, dict],
         measure: Callable[..., dict] = measure_swing) -> dict[str, Any]:
    """The full report: per stroke and fault, every candidate and a recommendation."""
    measured = measure_labelled(labels, swings, measure)
    report: dict[str, Any] = {"labelled": len(labels), "missing": len(measured["missing"]),
                              "failed": measured["failed"], "faults": {}}
    for stroke, blocks in measured["metrics"].items():
        good_rows = blocks.get("none", [])
        for label, fault_id in LABEL_TO_FAULT.items():
            if fault_id is None or label not in blocks:
                continue
            rule = THRESHOLDS[stroke][fault_id]
            fault_rows = blocks[label]
            options = []
            for name in dict.fromkeys([rule["measurement"], *CANDIDATES.get(fault_id, [])]):
                good = [r.get(name) for r in good_rows]
                fault = [r.get(name) for r in fault_rows]
                best = best_threshold(good, fault)
                entry: dict[str, Any] = {"measurement": name, "best": best,
                                         "rule_problem": rule_problem(best) if best else None}
                if name == rule["measurement"]:
                    entry["current"] = current_rule_score(rule, good, fault)
                options.append(entry)
            enough = [o for o in options if o["best"]
                      and o["best"]["n_good"] >= MIN_SWINGS and o["best"]["n_fault"] >= MIN_SWINGS]
            # Only a threshold that becomes a correctly-directed rule may be recommended.
            usable = [o for o in enough if o["rule_problem"] is None]
            top = max(usable, key=lambda o: o["best"]["balanced_accuracy"], default=None)
            if not enough:
                verdict = {"action": "disable", "why": f"fewer than {MIN_SWINGS} measured good or fault swings"}
            elif top is None:
                verdict = {"action": "disable", "why": "no measurement gives a rule in the right direction: "
                                                        + enough[0]["rule_problem"]}
            elif top["best"]["balanced_accuracy"] < MIN_SEPARATION:
                verdict = {"action": "disable",
                           "why": f"best separation {top['best']['balanced_accuracy']:.2f} < {MIN_SEPARATION} "
                                  f"({top['measurement']})"}
            else:
                b = top["best"]
                verdict = {"action": "set", "rule": {
                    "measurement": top["measurement"], "threshold": b["threshold"],
                    "severe_at": b["fault_median"], "target": b["good_median"]}}
            report["faults"][f"{stroke}/{fault_id}"] = {
                "label": label, "n_good": len(good_rows), "n_fault": len(fault_rows),
                "options": options, "verdict": verdict}
    return report


def _print(report: dict[str, Any]) -> None:
    print(f"{report['labelled']} labelled swings; {report['missing']} not found in the folder; "
          f"{len(report['failed'])} failed to measure.")
    for key, item in report["faults"].items():
        print(f"\n{key}  (good {item['n_good']} vs {item['label']} {item['n_fault']})")
        for o in item["options"]:
            b = o["best"]
            if b is None:
                print(f"  {o['measurement']:<28} not measured")
                continue
            line = (f"  {o['measurement']:<28} good~{b['good_median']:<8} fault~{b['fault_median']:<8} "
                    f"best: fires {b['fires']} {b['threshold']} -> flags {b['fault_flagged']:.0%} of faults, "
                    f"{b['good_flagged']:.0%} of good (score {b['balanced_accuracy']:.2f})")
            if o.get("rule_problem"):
                line += f"\n  {'':<28} not usable as a rule: {o['rule_problem']}"
            if "current" in o and o["current"]["good_flagged"] is not None:
                c = o["current"]
                line += (f"\n  {'':<28} current {c['threshold']}: flags {c['fault_flagged']:.0%} of faults, "
                         f"{c['good_flagged']:.0%} of good")
            print(line)
        v = item["verdict"]
        print(f"  => {v['action'].upper()}: " + (v["why"] if v["action"] == "disable" else json.dumps(v["rule"])))


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune fault thresholds against labelled swings.")
    parser.add_argument("labels", type=Path, help="labels CSV, e.g. ../data/labels/labels.csv")
    parser.add_argument("swings", type=Path, help="folder with the pipeline's swing JSON files")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()
    report = tune(load_labels(args.labels), load_swings(args.swings))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print(report)


if __name__ == "__main__":
    main()
