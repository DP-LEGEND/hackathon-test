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
- split: one row per synthetic swing, input = stroke + the code-measured numbers,
  output = the injected fault's NAME only (no size: the model never sees the original swing,
  so it can't know the size, and only code may state numbers). Train and test are split by
  SOURCE swing, so edits of one swing never sit on both sides. The rare "none" rows are
  repeated in the train file only; the test file is never oversampled.

Everything written here is SIMULATED data (faults injected by code into real swings) and
must be labelled that way wherever it is shown. Keep the output under data/raw/ (git-ignored).
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
    """The text a model sees: stroke plus the code-measured numbers (physics.metrics.describe)."""
    return f"{stroke}, {describe(metrics)}"


def build_rows(synthetic_dir: str | Path, swings_dir: str | Path) -> list[dict]:
    """One row per line of synthetic.csv, with stroke from the source swing file."""
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


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def write_split(synthetic_dir: str | Path, swings_dir: str | Path, out: str | Path,
                test_share: float = 0.25, seed: int = 0) -> dict:
    """Write train/test files and split.json into `out`. Returns the manifest."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = build_rows(synthetic_dir, swings_dir)
    train, test, manifest = split_by_source(rows, test_share, seed)
    tuned_train = oversample_none(train, seed)
    _write_jsonl(out / "train_rows.jsonl", train)
    _write_jsonl(out / "test_rows.jsonl", test)
    _write_jsonl(out / "adaption_train.jsonl", [{"input": r["input"], "output": r["output"]} for r in tuned_train])
    _write_jsonl(out / "adaption_test.jsonl", [{"input": r["input"], "output": r["output"]} for r in test])
    manifest.update({
        "data": SIMULATED_NOTE,
        "labels": list(LABELS),
        "counts": {
            "train": dict(Counter(r["output"] for r in train)),
            "train_oversampled": dict(Counter(r["output"] for r in tuned_train)),
            "test": dict(Counter(r["output"] for r in test)),
        },
        "files": ["train_rows.jsonl", "test_rows.jsonl", "adaption_train.jsonl", "adaption_test.jsonl"],
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
            print(f"  {SIMULATED_NOTE}")
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
