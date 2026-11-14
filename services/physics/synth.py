"""Turn a folder of good swings into labelled synthetic swings (Adaption fine-tune data). Owner: aryan.

Usage (from services/):
    python -m physics.synth ../data/raw/good_swings --out ../data/raw/synthetic --fps-real 120

Reads every *.json in the folder, one Swing each (lib/ghost/types.ts shape). For each:
- keeps the original, labelled "none"
- makes --per-swing edited copies with one fault each, cycling through FAULTS with random sizes

Writes into --out (keep it under data/raw/, which git ignores):
- swings/<name>.json   each edited swing (marked synthetic: true)
- synthetic.csv        one row per swing: fault, requested and re-measured size, metrics
- adaption.jsonl       one line per swing:
                       {"input": "<re-measured metrics>", "output": "<fault +size unit>", "cue": ""}
                       `cue` (the coaching sentence) is left empty; the coach service fills it later.

Labels use the RE-MEASURED change, not the requested one: code measures, nothing is assumed.
All output is SIMULATED data and must be labelled that way anywhere it's shown.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

from physics.ghost import EDITS, inject_fault
from physics.metrics import RELEASE_WINDOW_MS, describe, measure

# Fault sizes to sample (uniform), in each edit's own unit and sign.
FAULTS = {
    "elbow_bend": (6.0, 30.0),       # deg: elbow more bent at contact
    "shoulder_turn": (-35.0, -6.0),  # deg: less shoulder turn in the backswing
    "wrist_early": (15.0, 80.0),     # ms: wrist uncocks earlier
}
METRIC_KEYS = ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_release_ms")
CSV_COLUMNS = ["name", "source", "fault", "requested_size", "measured_size", "unit", "hand",
               "contact_frame", "fps_real", *METRIC_KEYS, "swing_json"]


def measured_change(fault: str, before: dict, after: dict) -> float:
    """The fault's size as the code measures it, in the edit's sign convention."""
    if fault == "elbow_bend":
        return before["elbow_at_contact_deg"] - after["elbow_at_contact_deg"]
    if fault == "shoulder_turn":
        return after["shoulder_turn_deg"] - before["shoulder_turn_deg"]
    if fault == "wrist_early":
        return after["wrist_release_ms"] - before["wrist_release_ms"]
    raise ValueError(f"unknown fault {fault!r}")


def agrees(fault: str, requested: float, got: float, fps_real: float) -> bool:
    """Did re-measuring find the fault at (about) the size we injected?

    If not, the metric is too noisy on this swing to label it, so we drop the example
    rather than train on a wrong label.
    """
    tol = 0.5 if EDITS[fault]["unit"] == "deg" else 1.5 * 1000 / fps_real
    return abs(got - requested) <= max(tol, 0.25 * abs(requested))


def sample_size(fault: str, base: dict, rng: np.random.Generator) -> float | None:
    """Random size for `fault` that this swing can take, or None if there's no room."""
    lo, hi = FAULTS[fault]
    if fault == "shoulder_turn":
        lo = max(lo, -0.6 * base["shoulder_turn_deg"])  # keep at least 40% of the turn
    if fault == "wrist_early":
        hi = min(hi, RELEASE_WINDOW_MS[0] - 10 - base["wrist_release_ms"])  # stay measurable
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return None
    return round(float(rng.uniform(lo, hi)), 1)


def label(fault: str, size: float) -> str:
    if fault == "none":
        return "none"
    return f"{fault} {size:+.0f} {EDITS[fault]['unit']}"


def _rounded(swing: dict, nd: int = 5) -> dict:
    """Round point coordinates to `nd` decimals (10 micrometres) to keep files small."""
    out = dict(swing, frames=[])
    for f in swing["frames"]:
        g = dict(f, joints=[[round(x, nd) for x in j] for j in f["joints"]])
        for key in ("racketTip", "racketThroat"):
            if g.get(key) is not None:
                g[key] = [round(x, nd) for x in g[key]]
        out["frames"].append(g)
    return out


def generate(folder: str | Path, out: str | Path, per_swing: int = 30, seed: int = 0,
             fps_real: float | None = None, hand: str | None = None) -> dict:
    """Write the synthetic set. Returns a summary {"sources", "rows", "skipped", "csv", "jsonl"}."""
    files = sorted(Path(folder).glob("*.json"))
    if not files:
        raise ValueError(f"no .json swings found in {folder}")
    out = Path(out)
    (out / "swings").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    rows, lines, skipped, sources = [], [], [], 0

    def add(name, source, fault, requested, got, m, path):
        rows.append({
            "name": name, "source": source, "fault": fault, "requested_size": requested,
            "measured_size": round(got, 2), "unit": EDITS[fault]["unit"] if fault != "none" else "",
            "hand": m["hand"], "contact_frame": m["contact_frame"], "fps_real": m["fps_real"],
            **{k: round(m[k], 2) for k in METRIC_KEYS}, "swing_json": str(path),
        })
        lines.append({"input": describe(m), "output": label(fault, got), "cue": ""})

    for path in files:
        swing = json.loads(path.read_text())
        swing.setdefault("id", path.stem)
        try:
            base = measure(swing, fps_real, hand)
        except (ValueError, KeyError) as e:
            skipped.append(f"{path.name}: {e}")
            continue
        if not all(math.isfinite(base[k]) for k in METRIC_KEYS):
            skipped.append(f"{path.name}: some metrics couldn't be measured ({base})")
            continue
        sources += 1
        add(f"{path.stem}__none", path.name, "none", 0.0, 0.0, base, path)
        for k in range(per_swing):
            fault = list(FAULTS)[k % len(FAULTS)]
            size = sample_size(fault, base, rng)
            name = f"{path.stem}__{fault}_{k:03d}"
            if size is None:
                skipped.append(f"{name}: no room for this fault on this swing")
                continue
            try:
                edited = inject_fault(swing, fault, size, fps_real, base["hand"])
                after = measure(edited, fps_real, base["hand"])
            except ValueError as e:
                skipped.append(f"{name}: {e}")
                continue
            if not all(math.isfinite(after[m]) for m in METRIC_KEYS):
                skipped.append(f"{name}: metrics couldn't be re-measured")
                continue
            got = measured_change(fault, base, after)
            if not agrees(fault, size, got, base["fps_real"]):
                unit = EDITS[fault]["unit"]
                skipped.append(f"{name}: injected {size:+.1f} {unit} but re-measured {got:+.1f} {unit}; "
                               f"{fault} can't be measured reliably on this swing")
                continue
            target = out / "swings" / f"{name}.json"
            target.write_text(json.dumps(_rounded(edited)))
            add(name, path.name, fault, size, got, after, target)

    csv_path, jsonl_path = out / "synthetic.csv", out / "adaption.jsonl"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    with jsonl_path.open("w") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")
    return {"sources": sources, "rows": len(rows), "skipped": skipped,
            "csv": str(csv_path), "jsonl": str(jsonl_path)}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Make labelled synthetic swings from good swings (SIMULATED data).")
    p.add_argument("folder", help="folder of good swing .json files, one swing per file")
    p.add_argument("--out", required=True, help="output folder, e.g. ../data/raw/synthetic")
    p.add_argument("--per-swing", type=int, default=30, help="edited copies per good swing (default 30)")
    p.add_argument("--seed", type=int, default=0, help="random seed, for repeatable output")
    p.add_argument("--fps-real", type=float, default=None,
                   help="real capture rate, e.g. 120 for 4x slow-mo rendered at 30 fps (default: swing fps)")
    p.add_argument("--hand", choices=["R", "L"], default=None, help="hitting hand (default: detect)")
    a = p.parse_args(argv)
    try:
        s = generate(a.folder, a.out, a.per_swing, a.seed, a.fps_real, a.hand)
    except ValueError as e:
        sys.exit(f"error: {e}")
    print(f"{s['rows']} labelled swings from {s['sources']} good swings -> {s['csv']} and {s['jsonl']}")
    if s["skipped"]:
        print(f"skipped {len(s['skipped'])}:")
        for msg in s["skipped"][:20]:
            print("  " + msg)


if __name__ == "__main__":
    main()
