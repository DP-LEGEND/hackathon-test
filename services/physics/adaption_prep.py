"""Clean fine-tune data for Adaption from the fault injector's output. Owner: aryan.

The first synth run trained on problems: most "good" source swings carried an acted fault,
stroke wasn't in the input, and the output asked for a fault size the input can't tell you.
This module fixes that in two steps around physics.synth:

    # from services/
    python -m physics.adaption_prep select --swings ~/hackathon-test-physics/data/raw/real_swings \
        --labels ../data/labels/labels.csv --out ../data/raw/adaption/clean_swings
    python -m physics.synth ../data/raw/adaption/clean_swings --out ../data/raw/adaption/synthetic \
        --fps-real 120 --per-swing 60
    python -m physics.adaption_prep split --synthetic ../data/raw/adaption/synthetic \
        --swings ../data/raw/adaption/clean_swings --out ../data/raw/adaption --seed 0

- select: copies only swings that every row of labels.csv marks intended_fault "none".
  The source folder is only read, never changed.
- split: one row per synthetic swing, output = the injected fault's NAME only (no size; only
  code may state numbers). Train and test are split by SOURCE swing, so edits of one swing never
  sit on both sides. Two input formats are written:
  - raw: stroke + the code-measured numbers of that one swing;
  - relative: stroke + each number's change from the player's clean-swing average for that
    stroke (their baseline). The baseline is the mean of the player's clean TRAINING swings,
    leaving out the row's own swing, so a test swing never feeds any baseline.
  The Adaption AutoScientist file (prompt/completion, relative format) holds training rows only,
  with the rare "none" rows repeated; the test split is never in it.

The player is the filming session (the swing id before "-swing-"): each session is one player
and one stroke. Everything written here is SIMULATED data (faults injected by code into real
swings) and must be labelled that way wherever it is shown. Keep the output under data/raw/.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from physics.metrics import describe
from physics.synth import METRIC_KEYS

LABELS = ("none", "elbow_bend", "shoulder_turn", "wrist_early")
STROKES = ("forehand", "backhand")
SIMULATED_NOTE = ("SIMULATED: one fault of known size injected by code (physics.ghost) into real, "
                  "labelled-clean swings, then re-measured. Not real faults.")
RELATIVE_NAMES = {"elbow_at_contact_deg": ("elbow", "deg"), "shoulder_turn_deg": ("shoulder turn", "deg"),
                  "wrist_release_ms": ("wrist release", "ms")}
AUTOSCIENTIST_INSTRUCTION = (
    "SIMULATED squash swing (one fault may have been injected by code). Changes were measured by code "
    "against this player's clean-swing average for the stroke; wrist release + means earlier. "
    "Name the one injected fault: none, elbow_bend, shoulder_turn or wrist_early.")
MIN_AUTOSCIENTIST_ROWS = 1000


def clean_swing_ids(labels_csv: str | Path) -> dict[str, str]:
    """{swing id: stroke} for swings that every labels.csv row marks intended_fault "none"."""
    seen: dict[str, set[tuple[str, str]]] = {}
    with open(labels_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            sid = row["swing"].strip()
            if sid:
                seen.setdefault(sid, set()).add((row["intended_fault"].strip(), row["side"].strip()))
    clean = {}
    for sid, labels in seen.items():
        faults = {f for f, _ in labels}
        sides = {s for _, s in labels}
        if faults == {"none"} and len(sides) == 1:
            clean[sid] = sides.pop()
    return clean


def select_clean(swings_dir: str | Path, labels_csv: str | Path, out: str | Path) -> dict:
    """Copy the labelled-clean swings from `swings_dir` into `out`. Returns a summary."""
    swings_dir, out = Path(swings_dir).resolve(), Path(out).resolve()
    if out == swings_dir:
        raise ValueError("--out must be a different folder from --swings (the source is never changed)")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("--out must be empty or new; stale swings from an earlier run would leak into synth")
    files = sorted(swings_dir.glob("*.json"))
    if not files:
        raise ValueError(f"no .json swings found in {swings_dir}")
    clean = clean_swing_ids(labels_csv)
    out.mkdir(parents=True, exist_ok=True)
    selected, skipped = [], []
    for path in files:
        if path.stem not in clean:
            skipped.append(f"{path.name}: not labelled clean (intended_fault isn't 'none' in every row)")
            continue
        side = json.loads(path.read_text()).get("side")
        if side != clean[path.stem]:
            skipped.append(f"{path.name}: swing says side {side!r} but labels.csv says {clean[path.stem]!r}")
            continue
        shutil.copy2(path, out / path.name)
        selected.append(path.name)
    return {"selected": selected, "skipped": skipped, "out": str(out)}


def model_input(stroke: str, metrics: dict) -> str:
    """Raw format: stroke plus the code-measured numbers of one swing (physics.metrics.describe)."""
    return f"{stroke}, {describe(metrics)}"


def relative_input(stroke: str, deltas: dict) -> str:
    """Relative format, e.g. "backhand; elbow -21 deg vs your baseline; shoulder turn -4 deg; wrist release +2 ms"."""
    parts = []
    for i, m in enumerate(METRIC_KEYS):
        name, unit = RELATIVE_NAMES[m]
        parts.append(f"{name} {round(deltas[m]):+d} {unit}" + (" vs your baseline" if i == 0 else ""))
    return f"{stroke}; " + "; ".join(parts)


def player_key(source: str, stroke: str) -> tuple[str, str]:
    """The player is the filming session (swing id before "-swing-"); one baseline per player and stroke."""
    stem = Path(source).stem
    return (stem.split("-swing-")[0] if "-swing-" in stem else "unknown", stroke)


def build_rows(synthetic_dir: str | Path, swings_dir: str | Path) -> list[dict]:
    """One raw-format row per line of synthetic.csv, with stroke from the source swing file."""
    swings_dir = Path(swings_dir)
    strokes: dict[str, str] = {}
    rows = []
    with open(Path(synthetic_dir) / "synthetic.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            source = r["source"]
            if source not in strokes:
                path = swings_dir / source
                if not path.is_file():
                    raise ValueError(f"source swing {source} isn't in {swings_dir}")
                side = json.loads(path.read_text()).get("side")
                if side not in STROKES:
                    raise ValueError(f"{source}: side must be forehand or backhand, got {side!r}")
                strokes[source] = side
            if r["fault"] not in LABELS:
                raise ValueError(f"{r['name']}: unknown fault {r['fault']!r}")
            m = {"hand": r["hand"], **{k: float(r[k]) for k in METRIC_KEYS}}
            rows.append({
                "name": r["name"], "source": source, "stroke": strokes[source], "hand": r["hand"],
                "fault": r["fault"], "measured_size": float(r["measured_size"]), "unit": r["unit"],
                **{k: m[k] for k in METRIC_KEYS},
                "input": model_input(strokes[source], m), "output": r["fault"],
            })
    if not rows:
        raise ValueError(f"no rows in {synthetic_dir}/synthetic.csv")
    return rows


def split_by_source(rows: list[dict], test_share: float = 0.25, seed: int = 0) -> tuple[list, list, dict]:
    """Split whole source swings into train/test, per stroke, so both strokes are in both sets."""
    rng = np.random.default_rng(seed)
    test_sources: set[str] = set()
    for stroke in STROKES:
        sources = sorted({r["source"] for r in rows if r["stroke"] == stroke})
        if len(sources) < 2:
            raise ValueError(f"need at least 2 {stroke} source swings to split, got {len(sources)}")
        k = min(len(sources) - 1, max(1, round(len(sources) * test_share)))
        test_sources.update(sources[i] for i in rng.permutation(len(sources))[:k])
    train = [r for r in rows if r["source"] not in test_sources]
    test = [r for r in rows if r["source"] in test_sources]
    manifest = {
        "seed": seed, "test_share": test_share,
        "train_sources": sorted({r["source"] for r in train}),
        "test_sources": sorted(test_sources),
    }
    return train, test, manifest


def make_relative(train: list[dict], test: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Relative-format copies of train and test rows.

    Baseline for a row = mean of its player's clean (none) TRAINING swings of the same stroke,
    leaving out the row's own source swing. Raw numbers are kept as raw_<metric>; the metric
    fields hold the changes, so the eval's rule and scoring work on them unchanged.
    """
    clean: dict[tuple[str, str], dict[str, dict]] = {}
    for r in train:
        if r["output"] == "none":
            clean.setdefault(player_key(r["source"], r["stroke"]), {})[r["source"]] = {m: r[m] for m in METRIC_KEYS}
    baselines: dict[str, tuple[dict, int]] = {}

    def baseline(r: dict) -> tuple[dict, int]:
        if r["source"] not in baselines:
            group = clean.get(player_key(r["source"], r["stroke"]), {})
            others = [v for s, v in group.items() if s != r["source"]]
            if not others:
                raise ValueError(f"{r['source']}: no other clean training swing of this player and stroke "
                                 "to build a baseline from")
            baselines[r["source"]] = ({m: float(np.mean([o[m] for o in others])) for m in METRIC_KEYS}, len(others))
        return baselines[r["source"]]

    def convert(r: dict) -> dict:
        base, n = baseline(r)
        deltas = {m: r[m] - base[m] for m in METRIC_KEYS}
        out = dict(r, **{f"raw_{m}": r[m] for m in METRIC_KEYS}, **deltas)
        out.update(baseline={m: round(base[m], 2) for m in METRIC_KEYS}, baseline_swings=n,
                   input=relative_input(r["stroke"], deltas))
        return out

    summary = {f"{k[0]} {k[1]}": len(v) for k, v in sorted(clean.items())}
    return [convert(r) for r in train], [convert(r) for r in test], summary


def oversample_none(train: list[dict], seed: int = 0) -> list[dict]:
    """Train rows with "none" repeated up to the average fault-class size, shuffled."""
    counts = Counter(r["output"] for r in train)
    fault_counts = [counts[f] for f in LABELS[1:] if counts[f]]
    nones = [r for r in train if r["output"] == "none"]
    if not nones or not fault_counts:
        return list(train)
    target = max(len(nones), round(sum(fault_counts) / len(fault_counts)))
    extra = [nones[i % len(nones)] for i in range(target - len(nones))]
    out = list(train) + extra
    order = np.random.default_rng(seed).permutation(len(out))
    return [out[i] for i in order]


def autoscientist_rows(rows: list[dict]) -> list[dict]:
    """Adaption AutoScientist raw mode: {"prompt", "completion"} per row."""
    return [{"prompt": f"{AUTOSCIENTIST_INSTRUCTION}\n{r['input']}\nFault:", "completion": r["output"]} for r in rows]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def write_split(synthetic_dir: str | Path, swings_dir: str | Path, out: str | Path,
                test_share: float = 0.25, seed: int = 0) -> dict:
    """Write raw and relative train/test rows, the AutoScientist file and split.json. Returns the manifest."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = build_rows(synthetic_dir, swings_dir)
    train, test, manifest = split_by_source(rows, test_share, seed)
    train_rel, test_rel, baseline_swings = make_relative(train, test)
    tuned = oversample_none(train_rel, seed)
    test_sources = set(manifest["test_sources"])
    if any(r["source"] in test_sources for r in tuned):
        raise AssertionError("a test swing reached the AutoScientist file")
    auto = autoscientist_rows(tuned)
    _write_jsonl(out / "train_rows.jsonl", train)
    _write_jsonl(out / "test_rows.jsonl", test)
    _write_jsonl(out / "train_rows_relative.jsonl", train_rel)
    _write_jsonl(out / "test_rows_relative.jsonl", test_rel)
    _write_jsonl(out / "autoscientist_train.jsonl", auto)
    manifest.update({
        "data": SIMULATED_NOTE,
        "labels": list(LABELS),
        "baseline": ("mean of the player's (filming session's) clean TRAINING swings of the same stroke, "
                     "leaving out the row's own swing; test swings never feed a baseline"),
        "baseline_clean_training_swings": baseline_swings,
        "counts": {
            "train": dict(Counter(r["output"] for r in train)),
            "test": dict(Counter(r["output"] for r in test)),
        },
        "autoscientist": {
            "file": str((out / "autoscientist_train.jsonl").resolve()),
            "rows": len(auto),
            "labels": dict(Counter(r["completion"] for r in auto)),
            "format": "prompt/completion, relative inputs, training swings only (none rows repeated), "
                      "test split never included",
        },
        "files": ["train_rows.jsonl", "test_rows.jsonl", "train_rows_relative.jsonl",
                  "test_rows_relative.jsonl", "autoscientist_train.jsonl"],
    })
    (out / "split.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Clean Adaption fine-tune data (SIMULATED).")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select", help="copy labelled-clean swings into a new folder")
    s.add_argument("--swings", required=True, help="folder of real swing .json files (read only)")
    s.add_argument("--labels", required=True, help="data/labels/labels.csv")
    s.add_argument("--out", required=True, help="new folder under data/raw/, e.g. ../data/raw/adaption/clean_swings")
    t = sub.add_parser("split", help="build train/test files from physics.synth output")
    t.add_argument("--synthetic", required=True, help="physics.synth --out folder (has synthetic.csv)")
    t.add_argument("--swings", required=True, help="the clean swing folder synth read from")
    t.add_argument("--out", required=True, help="output folder under data/raw/")
    t.add_argument("--test-share", type=float, default=0.25)
    t.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)
    try:
        if a.cmd == "select":
            r = select_clean(a.swings, a.labels, a.out)
            print(f"{len(r['selected'])} clean swings copied to {r['out']}; {len(r['skipped'])} skipped")
        else:
            m = write_split(a.synthetic, a.swings, a.out, a.test_share, a.seed)
            print(f"train sources {len(m['train_sources'])}, test sources {len(m['test_sources'])}")
            for k, v in m["counts"].items():
                print(f"  {k}: {v}")
            print(f"  baseline clean training swings per player and stroke: {m['baseline_clean_training_swings']}")
            auto = m["autoscientist"]
            print(f"AutoScientist train file: {auto['file']}")
            print(f"  rows: {auto['rows']}  labels: {auto['labels']}")
            if auto["rows"] < MIN_AUTOSCIENTIST_ROWS:
                print(f"  WARNING: fewer than {MIN_AUTOSCIENTIST_ROWS:,} rows; raise --per-swing in physics.synth")
            print(f"  {SIMULATED_NOTE}")
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
