"""Pick the rolled_wrist threshold from labelled normal vs rolled swings. Owner: Henoch.

Input: wrist_metrics.json (wrist.run) and a labels CSV with `swing` and `intended_fault`
("none" = normal, "rolled_wrist" = rolled; data/labels/labels.csv works, use --run).
Only usable swings count (metrics.py marks the rest).

For each candidate number (roll change, peak roll rate) it reports, honestly:
- medians and ranges of both groups, and the MARGIN between them (smallest rolled minus
  largest normal: > 0 means every swing is on its own side, < 0 means they overlap);
- the threshold, by the fault library's rule for labelled data: halfway between the
  normal median (target) and the rolled median (severe_at);
- how that threshold sorts these same swings (in-sample, optimistic) and LEAVE-ONE-OUT
  accuracy: each swing judged by a threshold made from the other swings only, the
  better guess at how a new swing will fare;
- Cohen's d (difference of means in pooled standard deviations).

Verdict: "set" a rule only with >= 5 usable swings in each group, leave-one-out >= 0.8
and rolled swings rolling MORE than normal ones; otherwise say why not. It never edits
coach/faults.py: copy the rule there by hand.

Run (from inside services/):

    python -m wrist.tune wrist_metrics.json ../data/labels/labels.csv --run <pipeline_run>
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any, Optional

from wrist.sync import strip_run

NORMAL, ROLLED = "none", "rolled_wrist"
# wrist metrics key -> the coach measurement it becomes (coach/faults.py MEASUREMENTS)
CANDIDATES = {"roll_change_abs_deg": "forearm_roll_deg", "peak_roll_rate_abs_dps": "forearm_roll_rate_dps"}
UNITS = {"roll_change_abs_deg": "deg", "peak_roll_rate_abs_dps": "deg/s"}
MIN_SWINGS = 5
MIN_LOO = 0.8


def _threshold(normal: list[float], rolled: list[float]) -> tuple[float, bool]:
    """(halfway between the medians, fires above?)."""
    n, r = statistics.median(normal), statistics.median(rolled)
    return (n + r) / 2, r > n


def _flags(v: float, thr: float, above: bool) -> bool:
    return v > thr if above else v < thr


def separation(normal: list[float], rolled: list[float]) -> Optional[dict[str, Any]]:
    """How well one number splits normal from rolled swings. None if a group is empty."""
    if not normal or not rolled:
        return None
    thr, above = _threshold(normal, rolled)
    rolled_flagged = sum(_flags(v, thr, above) for v in rolled) / len(rolled)
    normal_flagged = sum(_flags(v, thr, above) for v in normal) / len(normal)
    margin = (min(rolled) - max(normal)) if above else (min(normal) - max(rolled))

    correct = total = 0
    every = [(v, False) for v in normal] + [(v, True) for v in rolled]
    for i, (v, is_rolled) in enumerate(every):
        rest_n = [x for j, (x, r) in enumerate(every) if j != i and not r]
        rest_r = [x for j, (x, r) in enumerate(every) if j != i and r]
        if not rest_n or not rest_r:
            continue
        t, a = _threshold(rest_n, rest_r)
        correct += _flags(v, t, a) == is_rolled
        total += 1

    d = None
    if len(normal) > 1 and len(rolled) > 1:
        pooled = (((len(normal) - 1) * statistics.variance(normal) + (len(rolled) - 1) * statistics.variance(rolled))
                  / (len(normal) + len(rolled) - 2)) ** 0.5
        d = round((statistics.mean(rolled) - statistics.mean(normal)) / pooled, 2) if pooled > 0 else None
    return {
        "n_normal": len(normal), "n_rolled": len(rolled),
        "normal_median": round(statistics.median(normal), 1), "rolled_median": round(statistics.median(rolled), 1),
        "normal_range": [round(min(normal), 1), round(max(normal), 1)],
        "rolled_range": [round(min(rolled), 1), round(max(rolled), 1)],
        "threshold": round(thr, 1), "fires": "above" if above else "below",
        "margin": round(margin, 1),
        "in_sample": {"rolled_flagged": round(rolled_flagged, 2), "normal_flagged": round(normal_flagged, 2),
                      "balanced_accuracy": round((rolled_flagged + 1 - normal_flagged) / 2, 2)},
        "leave_one_out_accuracy": round(correct / total, 2) if total else None,
        "cohens_d": d,
    }


def tune(metrics: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    """The report: per candidate separation, and one verdict for rolled_wrist."""
    groups: dict[str, list[dict]] = {NORMAL: [], ROLLED: []}
    skipped = []
    for swing, label in labels.items():
        if label not in groups:
            continue
        entry = metrics.get("swings", {}).get(swing)
        if entry is None or not entry.get("usable"):
            skipped.append({"swing": swing, "label": label,
                            "why": entry.get("skip_reason") if entry else "no wrist entry for this swing"})
            continue
        groups[label].append({"swing": swing, **entry})

    options = {}
    for key in CANDIDATES:
        normal = [e[key] for e in groups[NORMAL] if isinstance(e.get(key), (int, float))]
        rolled = [e[key] for e in groups[ROLLED] if isinstance(e.get(key), (int, float))]
        options[key] = separation(normal, rolled)

    n_n, n_r = len(groups[NORMAL]), len(groups[ROLLED])
    mock = bool(metrics.get("mock"))
    report: dict[str, Any] = {
        "mock": mock, "n_normal": n_n, "n_rolled": n_r, "skipped": skipped, "options": options,
        "values": {lab: {e["swing"]: {k: e.get(k) for k in CANDIDATES} for e in rows} for lab, rows in groups.items()},
    }
    report["verdict"] = _verdict(options, n_n, n_r, mock)
    return report


def _verdict(options: dict[str, Optional[dict]], n_n: int, n_r: int, mock: bool) -> dict[str, Any]:
    if n_n < MIN_SWINGS or n_r < MIN_SWINGS:
        return {"action": "no_rule", "why": f"need >= {MIN_SWINGS} usable swings in each group, "
                                            f"have {n_n} normal and {n_r} rolled"}
    scored = [(k, o) for k, o in options.items() if o and o["leave_one_out_accuracy"] is not None]
    if not scored:
        return {"action": "no_rule", "why": "nothing measured"}
    # Best leave-one-out; ties keep the first candidate (roll change, the primary number).
    key, best = max(scored, key=lambda ko: ko[1]["leave_one_out_accuracy"])
    if best["fires"] != "above":
        return {"action": "check", "why": f"rolled swings show LESS {key} than normal ones; check the forearm "
                                          "axis (--axis) and the labels before trusting this"}
    if best["leave_one_out_accuracy"] < MIN_LOO:
        return {"action": "no_rule", "why": f"best leave-one-out accuracy {best['leave_one_out_accuracy']:.0%} "
                                            f"< {MIN_LOO:.0%} ({key}): normal and rolled swings don't separate"}
    # source = coach/faults.py WRIST_MOCK / WRIST_SENSOR, so the rule pastes in as-is.
    rule = {"measurement": CANDIDATES[key], "threshold": best["threshold"],
            "severe_at": best["rolled_median"], "target": best["normal_median"],
            "source": "mock wrist-sensor swings" if mock else "wrist-sensor swings"}
    honest = (f"{n_n} vs {n_r} swings, one player, one session. Leave-one-out "
              f"{best['leave_one_out_accuracy']:.0%}; ")
    honest += (f"every swing on its own side with {best['margin']} {UNITS[key]} to spare. "
               if best["margin"] > 0 else
               f"the groups OVERLAP by {-best['margin']} {UNITS[key]}, so some swings will be misjudged. ")
    honest += "With this few swings the threshold is provisional: expect misses on new swings and other players."
    if mock:
        honest = "MOCK data: says nothing about real swings. " + honest
    return {"action": "set", "measurement": key, "rule": rule, "honest": honest}


def read_labels(path: str | Path, run: Optional[str] = None) -> dict[str, str]:
    """{swing: intended_fault} from a labels CSV, optionally only one pipeline_run."""
    with Path(path).open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    return {strip_run(r["swing"], run): r["intended_fault"] for r in rows
            if r.get("swing") and r.get("intended_fault") and (not run or r.get("pipeline_run", run) == run)}


def _print(report: dict[str, Any]) -> None:
    print(("MOCK DATA. " if report["mock"] else "") +
          f"{report['n_normal']} normal vs {report['n_rolled']} rolled usable swings; "
          f"{len(report['skipped'])} labelled swings skipped.")
    for s in report["skipped"]:
        print(f"  skipped {s['swing']} ({s['label']}): {s['why']}")
    for key, o in report["options"].items():
        if o is None:
            print(f"\n{key}: not measured in both groups")
            continue
        loo = "n/a" if o["leave_one_out_accuracy"] is None else f"{o['leave_one_out_accuracy']:.0%}"
        print(f"\n{key} ({UNITS[key]})\n"
              f"  normal median {o['normal_median']} range {o['normal_range']}\n"
              f"  rolled median {o['rolled_median']} range {o['rolled_range']}\n"
              f"  threshold {o['threshold']} (fires {o['fires']}), margin {o['margin']} "
              f"({'clean split' if o['margin'] > 0 else 'OVERLAP'})\n"
              f"  in-sample: flags {o['in_sample']['rolled_flagged']:.0%} of rolled, "
              f"{o['in_sample']['normal_flagged']:.0%} of normal\n"
              f"  leave-one-out accuracy {loo}, Cohen's d {o['cohens_d']}")
    v = report["verdict"]
    print(f"\n=> {v['action'].upper()}: " + (json.dumps(v["rule"]) + f"\n   {v['honest']}"
                                            if v["action"] == "set" else v["why"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Choose the rolled_wrist threshold from labelled swings.")
    parser.add_argument("metrics", type=Path, help="wrist_metrics.json from python -m wrist.run")
    parser.add_argument("labels", type=Path, help="CSV with swing and intended_fault (none / rolled_wrist)")
    parser.add_argument("--run", help="only labels whose pipeline_run is this (and drop '@<run>' from ids)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()
    report = tune(json.loads(args.metrics.read_text()), read_labels(args.labels, args.run))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print(report)


if __name__ == "__main__":
    main()
