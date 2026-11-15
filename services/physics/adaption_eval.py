"""Fault-naming eval on held-out SIMULATED swings: code rule vs Claude, raw and baseline-relative.
Owner: aryan.

    # from services/, after physics.adaption_prep split
    python -m physics.adaption_eval --data ../data/raw/adaption --claude-sample 200
    # once Adaption reports the LoRA checkpoint's win rate, add it to the report:
    python -m physics.adaption_eval --data ../data/raw/adaption --adaption-win-rate "61% vs base model (n=200)"

Every answerer sees the same held-out test rows (source swings never used in training) and
names one label: none, elbow_bend, shoulder_turn or wrist_early. Nobody states a number;
the numbers in the input were measured by code. Two input formats, one table each:

- raw: the numbers of that one swing;
- relative: each number's change from the player's clean-swing average for the stroke.

Answerers:
- (a) Code rule: a per-fault threshold on how far each number sits from the clean training
  swings of the same stroke, fitted on the training rows only.
- (b) Claude (claude-opus-5-5, effort low): the same training knowledge as text (clean-swing
  numbers and a few labelled training rows), on a stratified sample of 200 or fewer test rows.
  Answers are cached in claude_cache.json next to the data, so a re-run is free.

Adaption AutoScientist returns a LoRA checkpoint scored as a win rate against its base model;
the report keeps a slot for that number, filled in by hand (--adaption-win-rate). Writes
eval_report.md and eval_results.json next to the data. All results are on SIMULATED data and
must be labelled that way wherever they're shown. The Claude key is loaded from .env.local
(repo root, or --env-dir) into the process only, never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Literal, Optional

import numpy as np
from pydantic import BaseModel

from physics.adaption_prep import LABELS, STROKES

CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_EFFORT = "low"
PROMPT_VERSION = "fault-label-v1"
MAX_CLAUDE_SAMPLE = 200
# List prices per million tokens for the cost note (Claude Opus 5.5, Nov 2026).
PRICE_IN, PRICE_OUT = 4.00, 20.00
REPO_ROOT = Path(__file__).resolve().parents[2]
MODES = {
    "raw": {"train": "train_rows.jsonl", "test": "test_rows.jsonl",
            "title": "Raw numbers of one swing"},
    "relative": {"train": "train_rows_relative.jsonl", "test": "test_rows_relative.jsonl",
                 "title": "Change from the player's clean-swing average (baseline-relative)"},
}

# Which metric each fault moves, and which way (+1: the number goes up).
DIRECTIONS = {
    "elbow_bend": ("elbow_at_contact_deg", -1.0),   # elbow more bent: smaller angle
    "shoulder_turn": ("shoulder_turn_deg", -1.0),   # less turn: smaller angle
    "wrist_early": ("wrist_release_ms", +1.0),      # earlier release: more ms before contact
}
SD_FLOOR = {"elbow_at_contact_deg": 1.0, "shoulder_turn_deg": 1.0, "wrist_release_ms": 1.0}
GRID = np.round(np.arange(0.0, 8.01, 0.1), 2)


class FaultCall(BaseModel):
    """Claude's answer: exactly one label, no numbers."""
    fault: Literal["none", "elbow_bend", "shoulder_turn", "wrist_early"]


assert FaultCall.model_json_schema()["properties"]["fault"]["enum"] == list(LABELS)


# ---------- data ----------

def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def stratified_sample(rows: list[dict], n: int, seed: int = 0) -> list[dict]:
    """All "none" rows, then the rest spread evenly over the fault labels. Keeps test order."""
    if n >= len(rows):
        return list(rows)
    rng = np.random.default_rng(seed)
    by_label = {lab: [i for i, r in enumerate(rows) if r["output"] == lab] for lab in LABELS}
    picked = list(by_label["none"][:n])
    faults = [lab for lab in LABELS[1:] if by_label[lab]]
    left = n - len(picked)
    for j, lab in enumerate(faults):
        want = left // len(faults) + (1 if j < left % len(faults) else 0)
        idx = by_label[lab]
        picked += [idx[i] for i in rng.choice(len(idx), size=min(want, len(idx)), replace=False)]
    return [rows[i] for i in sorted(picked)]


# ---------- (a) code rule ----------

@dataclass
class ThresholdRule:
    """Per stroke: clean-swing mean and spread of each number. Per fault: a z threshold."""
    reference: dict = field(default_factory=dict)   # {stroke: {metric: (mean, sd)}}
    thresholds: dict = field(default_factory=dict)  # {fault: z}

    def scores(self, row: dict) -> dict:
        ref = self.reference[row["stroke"]]
        out = {}
        for fault, (metric, sign) in DIRECTIONS.items():
            mean, sd = ref[metric]
            out[fault] = sign * (row[metric] - mean) / sd
        return out

    def predict(self, row: dict) -> str:
        z = self.scores(row)
        over = {f: v for f, v in z.items() if v > self.thresholds[f]}
        return max(over, key=over.get) if over else "none"


def fit_rule(train: list[dict], rounds: int = 3) -> ThresholdRule:
    """Reference from the clean (none) training swings; thresholds by balanced accuracy on train."""
    rule = ThresholdRule()
    for stroke in STROKES:
        clean = [r for r in train if r["stroke"] == stroke and r["output"] == "none"]
        if len(clean) < 2:
            raise ValueError(f"need at least 2 clean {stroke} training swings, got {len(clean)}")
        rule.reference[stroke] = {
            m: (float(np.mean([r[m] for r in clean])), max(SD_FLOOR[m], float(np.std([r[m] for r in clean], ddof=1))))
            for m, _ in DIRECTIONS.values()
        }
    z = [rule.scores(r) for r in train]
    truth = [r["output"] for r in train]

    def balanced(th: dict) -> float:
        preds = []
        for s in z:
            over = {f: v for f, v in s.items() if v > th[f]}
            preds.append(max(over, key=over.get) if over else "none")
        return score(truth, preds)["balanced_accuracy"]

    # One shared threshold first (moving one at a time can get stuck), then refine each fault.
    best = -1.0
    for t in GRID:
        s = balanced({f: float(t) for f in DIRECTIONS})
        if s > best + 1e-12:
            best, rule.thresholds = s, {f: float(t) for f in DIRECTIONS}
    for _ in range(rounds):
        for f in DIRECTIONS:
            for t in GRID:
                trial = dict(rule.thresholds, **{f: float(t)})
                s = balanced(trial)
                if s > best + 1e-12:
                    best, rule.thresholds = s, trial
    return rule


def own_copy_accuracy(rows: list[dict]) -> tuple[int, int]:
    """Diagnostic only, not an answerer and not possible in real use: name each row from how far it
    moved from the UNCHANGED COPY of the same source swing (its none row)."""
    base = {r["source"]: r for r in rows if r["output"] == "none"}
    hits = total = 0
    for r in rows:
        b = base.get(r["source"])
        if b is None:
            continue
        moved = {f: sign * (r[m] - b[m]) for f, (m, sign) in DIRECTIONS.items()}
        best = max(moved, key=moved.get)
        hits += (best if moved[best] > 1.0 else "none") == r["output"]
        total += 1
    return hits, total


def spread_note(rule: ThresholdRule, train: list[dict], test: list[dict]) -> str:
    """Why these inputs are hard to label: injected sizes vs the spread between clean swings."""
    parts = []
    for f, (m, _) in DIRECTIONS.items():
        sizes = [abs(r["measured_size"]) for r in train if r["output"] == f]
        sds = "/".join(f"{rule.reference[s][m][1]:.0f}" for s in STROKES)
        unit = "ms" if m.endswith("_ms") else "deg"
        parts.append(f"{f} median {np.median(sizes):.0f} {unit} vs sd {sds} {unit}")
    hits, total = own_copy_accuracy(test)
    return ("Injected fault sizes vs the spread of the clean training swings in this format (forehand/backhand sd): "
            + "; ".join(parts) + f". Diagnostic only (not possible in real use): comparing each test row with the "
            f"unchanged copy of the same swing names {hits}/{total} correctly.")


# ---------- scoring ----------

def score(truth: list[str], pred: list[str]) -> dict:
    """Accuracy, per-label recall, and false alarms on none (a clean swing called a fault)."""
    assert len(truth) == len(pred)
    recall = {}
    for lab in LABELS:
        idx = [i for i, t in enumerate(truth) if t == lab]
        hit = sum(pred[i] == lab for i in idx)
        recall[lab] = {"hit": hit, "total": len(idx), "rate": hit / len(idx) if idx else None}
    rates = [v["rate"] for v in recall.values() if v["rate"] is not None]
    nones = [i for i, t in enumerate(truth) if t == "none"]
    correct = sum(t == p for t, p in zip(truth, pred))
    return {
        "rows": len(truth),
        "correct": correct,
        "accuracy": correct / len(truth) if truth else None,
        "balanced_accuracy": sum(rates) / len(rates) if rates else 0.0,
        "recall": recall,
        "false_alarms_on_none": {"count": sum(pred[i] != "none" for i in nones), "total": len(nones)},
        "not_a_label": sum(p not in LABELS for p in pred),
    }


# ---------- (b) Claude ----------

def claude_system_prompt(rule: ThresholdRule, train: list[dict], mode: str = "raw", seed: int = 0,
                         per_label: int = 3) -> str:
    """Same training knowledge the rule has, as text: clean-swing numbers and labelled examples."""
    relative = mode == "relative"
    seen = ("how much each number changed, measured by code against the player's clean-swing average for "
            "that stroke (their baseline)" if relative else "only the numbers the code measured")
    lines = [
        "You label squash swings for a fault-detection test. The data is SIMULATED: code took real "
        "swings that a coach labelled clean and either left them unchanged or injected exactly one "
        f"fault, then re-measured them. You see {seen}. Name which fault was injected. "
        "Never state or estimate a number.",
        "",
        "Labels:",
        "- none: the swing was left unchanged.",
        "- elbow_bend: elbow more bent at contact (a smaller elbow angle) than the player's normal swing.",
        "- shoulder_turn: less shoulder turn in the backswing (a smaller shoulder turn).",
        "- wrist_early: the wrist releases earlier (more milliseconds before contact).",
        "",
        ("Clean training swings vary around their baseline by (mean, standard deviation; computed by code):"
         if relative else "Clean training swings measured (mean, standard deviation; computed by code):"),
    ]
    if relative:
        names = {"elbow_at_contact_deg": "elbow change", "shoulder_turn_deg": "shoulder turn change",
                 "wrist_release_ms": "wrist release change (ms; + means earlier)"}
        fmt = "{:+.0f}"
    else:
        names = {"elbow_at_contact_deg": "elbow at contact", "shoulder_turn_deg": "shoulder turn",
                 "wrist_release_ms": "wrist release (ms before contact; negative means after)"}
        fmt = "{:.0f}"
    for stroke in STROKES:
        ref = rule.reference[stroke]
        parts = [f"{names[m]} {fmt.format(ref[m][0])} (sd {ref[m][1]:.0f})" for m, _ in DIRECTIONS.values()]
        lines.append(f"- {stroke}: " + "; ".join(parts))
    lines += ["", "Labelled training examples:"]
    rng = np.random.default_rng(seed)
    for lab in LABELS:
        pool = [r for r in train if r["output"] == lab]
        for i in rng.choice(len(pool), size=min(per_label, len(pool)), replace=False):
            lines.append(f"{pool[i]['input']} -> {lab}")
    lines += ["", "Answer with the single most likely label."]
    return "\n".join(lines)


class ClaudeUnavailable(RuntimeError):
    pass


class ClaudeAnswerer:
    """Asks Claude for one label per row; caches every real answer on disk."""

    def __init__(self, system: str, cache_path: Path, client=None, workers: int = 4):
        self.system = system
        self.cache_path = Path(cache_path)
        self.cache = json.loads(self.cache_path.read_text()) if self.cache_path.is_file() else {}
        self.client = client
        self.workers = workers
        self.lock = threading.Lock()
        self.new_calls = 0
        self.errors: list[str] = []

    def key(self, text: str) -> str:
        blob = json.dumps({"model": CLAUDE_MODEL, "effort": CLAUDE_EFFORT, "prompt": PROMPT_VERSION,
                           "system": self.system, "input": text}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _save(self) -> None:
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        os.replace(tmp, self.cache_path)

    def _client(self):
        if self.client is None:
            import anthropic
            key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if not key:
                raise ClaudeUnavailable("ANTHROPIC_API_KEY is not set")
            self.client = anthropic.Anthropic(api_key=key)
        return self.client

    def _ask(self, text: str) -> dict:
        import anthropic
        t0 = time.perf_counter()
        try:
            response = self._client().beta.messages.parse(
                model=CLAUDE_MODEL,
                max_tokens=2000,
                system=self.system,
                messages=[{"role": "user", "content": f"Swing: {text}"}],
                output_format=FaultCall,
                output_config={"effort": CLAUDE_EFFORT},
                # If the main model declines, the API retries on a fallback model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise ClaudeUnavailable("Claude rejected the API key") from exc
        latency = time.perf_counter() - t0
        if response.stop_reason == "refusal":
            fault = "refused"
        elif response.parsed_output is None:
            fault = "no_answer"
        else:
            fault = response.parsed_output.fault
        usage = getattr(response, "usage", None)
        return {"fault": fault, "latency_s": round(latency, 3), "served_by": getattr(response, "model", None),
                "stop_reason": response.stop_reason,
                "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                "asked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def answer_all(self, rows: list[dict]) -> list[Optional[dict]]:
        """One cached-or-fresh answer per row (None where the call failed; failures aren't cached)."""
        results: list[Optional[dict]] = [None] * len(rows)
        todo: dict[str, list[int]] = {}  # identical inputs are asked once
        for i, r in enumerate(rows):
            k = self.key(r["input"])
            hit = self.cache.get(k)
            if hit is not None:
                results[i] = dict(hit, cached=True)
            else:
                todo.setdefault(k, []).append(i)
        if not todo:
            return results
        self._client()  # fail fast on a missing key
        import anthropic
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._ask, rows[idx[0]]["input"]): (k, idx) for k, idx in todo.items()}
            for done, fut in enumerate(as_completed(futures), 1):
                k, idx = futures[fut]
                try:
                    ans = fut.result()
                except ClaudeUnavailable:
                    for f in futures:
                        f.cancel()
                    raise
                except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                    self.errors.append(f"{rows[idx[0]]['name']}: {type(exc).__name__}")
                    continue
                with self.lock:
                    self.cache[k] = ans
                    self.new_calls += 1
                    self._save()
                for i in idx:
                    results[i] = dict(ans, cached=False)
                if done % 25 == 0:
                    print(f"  Claude: {done}/{len(todo)} new answers", file=sys.stderr)
        return results


# ---------- one format ----------

def run_mode(data: Path, mode: str, claude_sample: int = MAX_CLAUDE_SAMPLE, use_claude: bool = True,
             seed: int = 0, workers: int = 4, client=None) -> dict:
    """Score the code rule and Claude on one input format. Returns columns and notes."""
    if not 0 < claude_sample <= MAX_CLAUDE_SAMPLE:
        raise ValueError(f"--claude-sample must be 1..{MAX_CLAUDE_SAMPLE}")
    files = MODES[mode]
    train, test = load_rows(data / files["train"]), load_rows(data / files["test"])
    if {r["source"] for r in train} & {r["source"] for r in test}:
        raise ValueError("a source swing is in both train and test; re-run adaption_prep split")
    rule = fit_rule(train)
    sample = stratified_sample(test, claude_sample, seed)
    columns, notes = [], []

    preds, lat = [], []
    for r in test:
        t0 = time.perf_counter()
        preds.append(rule.predict(r))
        lat.append(time.perf_counter() - t0)
    by_name = dict(zip((r["name"] for r in test), zip(preds, lat)))
    columns.append({"name": "(a) Code rule, fitted on train", "score": score([r["output"] for r in test], preds),
                    "latencies": lat, "predictions": preds, "rows": [r["name"] for r in test]})
    columns.append({"name": f"(a) Code rule, same {len(sample)} rows as Claude",
                    "score": score([r["output"] for r in sample], [by_name[r["name"]][0] for r in sample]),
                    "latencies": [by_name[r["name"]][1] for r in sample],
                    "predictions": [by_name[r["name"]][0] for r in sample], "rows": [r["name"] for r in sample]})
    notes.append("Code rule thresholds (z from clean training swings): "
                 + ", ".join(f"{f} > {t:.1f}" for f, t in rule.thresholds.items()))
    majority = Counter(r["output"] for r in train).most_common(1)[0][0]
    notes.append(f"For scale: always answering the most common training label ({majority}) scores "
                 f"{_pct(sum(r['output'] == majority for r in test) / len(test))} on all test rows.")
    notes.append(spread_note(rule, train, test))

    claude_name = f"(b) Claude {CLAUDE_MODEL} (effort {CLAUDE_EFFORT})"
    if not use_claude:
        columns.append({"name": claude_name, "skipped": "turned off with --no-claude"})
    else:
        answerer = ClaudeAnswerer(claude_system_prompt(rule, train, mode, seed), data / "claude_cache.json",
                                  client=client, workers=workers)
        try:
            answers = answerer.answer_all(sample)
        except ClaudeUnavailable as exc:
            columns.append({"name": claude_name, "skipped": str(exc)})
        else:
            # A failed call stays in Claude's score as a wrong answer, so Claude and the rule's
            # "same rows" column always share one denominator.
            preds_c = [a["fault"] if a is not None else "error" for a in answers]
            got = [a for a in answers if a is not None]
            columns.append({"name": claude_name, "score": score([r["output"] for r in sample], preds_c),
                            "latencies": [a["latency_s"] for a in got], "predictions": preds_c,
                            "rows": [r["name"] for r in sample]})
            tin = sum(a["input_tokens"] for a in got)
            tout = sum(a["output_tokens"] for a in got)
            notes.append(f"Claude: {answerer.new_calls} new calls, {sum(a['cached'] for a in got)} rows from cache; "
                         f"served by {dict(Counter(a['served_by'] for a in got))}; {tin:,} input + {tout:,} "
                         f"output tokens (about ${(tin * PRICE_IN + tout * PRICE_OUT) / 1e6:.2f} at list price).")
            odd = Counter(a["fault"] for a in got if a["fault"] not in LABELS)
            if odd:
                notes.append(f"Claude gave no label for {dict(odd)} rows (counted wrong).")
            failed = len(answers) - len(got)
            if failed:
                notes.append(f"{failed} Claude call{'s' if failed != 1 else ''} failed and "
                             f"{'are' if failed != 1 else 'is'} scored as wrong"
                             + (": " + "; ".join(answerer.errors[:5]) + (" …" if len(answerer.errors) > 5 else "")
                                if answerer.errors else "") + ".")

    meta = {"mode": mode, "title": files["title"], "example_input": test[0]["input"],
            "test_rows": len(test), "test_sources": len({r["source"] for r in test}),
            "train_rows": len(train), "train_sources": len({r["source"] for r in train}),
            "claude_sample": len(sample), "notes": notes}
    return {"meta": meta, "columns": columns}


# ---------- report ----------

def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _cell(rec: dict) -> str:
    return "n/a" if not rec["total"] else f"{rec['hit']}/{rec['total']} ({100 * rec['hit'] / rec['total']:.0f}%)"


def _latency(seconds: list[float]) -> str:
    if not seconds:
        return "n/a"
    m = median(seconds)
    return f"{m * 1000:.3f} ms" if m < 0.1 else f"{m:.2f} s"


def table_markdown(columns: list[dict]) -> list[str]:
    out = ["| Answerer (SIMULATED test rows) | Rows | Accuracy | none | elbow_bend | shoulder_turn | wrist_early "
           "| False alarms on none | Median latency |",
           "|---|---|---|---|---|---|---|---|---|"]
    for c in columns:
        if c.get("skipped"):
            out.append(f"| {c['name']} | - | skipped: {c['skipped']} | | | | | | |")
            continue
        s = c["score"]
        fa = s["false_alarms_on_none"]
        out.append(f"| {c['name']} | {s['rows']} | {_pct(s['accuracy'])} | "
                   + " | ".join(_cell(s["recall"][lab]) for lab in LABELS)
                   + f" | {fa['count']} of {fa['total']} | {_latency(c['latencies'])} |")
    return out


def report_markdown(sections: list[dict], split: dict, win_rate: Optional[str]) -> str:
    first = sections[0]["meta"]
    out = [
        "# Fault-naming eval (SIMULATED data)",
        "",
        f"SIMULATED: {first['test_rows']} held-out test rows from {first['test_sources']} source swings that no "
        f"answerer trained on ({first['train_rows']} training rows from {first['train_sources']} other swings). "
        "Each row is a real, labelled-clean swing left unchanged (none) or with one fault injected by code and "
        "re-measured. These are not real faults. Both tables use the same test swings.",
    ]
    for n, sec in enumerate(sections, 1):
        m = sec["meta"]
        out += ["", f"## {n}. {m['title']} (SIMULATED)", "", f"Example input: `{m['example_input']}`"]
        if m["mode"] == "relative":
            out += ["", "Baseline: " + split.get("baseline", "the player's clean-swing average") + "."]
        out += [""] + table_markdown(sec["columns"]) + [""] + [f"- {note}" for note in m["notes"]]
    auto = split.get("autoscientist", {})
    out += [
        "", f"## {len(sections) + 1}. Adaption AutoScientist (SIMULATED training data)", "",
        f"- Training file: `{Path(auto.get('file', 'autoscientist_train.jsonl')).name}`, {auto.get('rows', '?')} rows, "
        f"labels {auto.get('labels', {})}; {auto.get('format', '')}.",
        "- Adaption returns a LoRA checkpoint and scores it as a win rate against its base model. That is not "
        "accuracy on the test rows above, so it isn't comparable with the tables.",
        f"- Win rate vs base model: {win_rate if win_rate else '**not run yet — fill in by hand** (re-run with --adaption-win-rate)'}",
        "",
        "Recall cells: rows of that label named correctly. False alarms on none: unchanged swings called a fault. "
        "Latency: wall time per answer on this Mac (Claude: one API call, measured when first asked; cached re-runs "
        "report the original time).",
    ]
    return "\n".join(out) + "\n"


def evaluate(data: Path, claude_sample: int = MAX_CLAUDE_SAMPLE, use_claude: bool = True, seed: int = 0,
             workers: int = 4, client=None, win_rate: Optional[str] = None) -> dict:
    """Both formats, one report. Writes eval_report.md and eval_results.json into `data`."""
    data = Path(data)
    sections = [run_mode(data, mode, claude_sample, use_claude, seed, workers, client) for mode in MODES]
    split = json.loads((data / "split.json").read_text()) if (data / "split.json").is_file() else {}
    md = report_markdown(sections, split, win_rate)
    (data / "eval_report.md").write_text(md)
    results = {
        "data": split.get("data", "SIMULATED"), "prompt_version": PROMPT_VERSION, "seed": seed,
        "sections": {s["meta"]["mode"]: {"meta": s["meta"], "columns": [
            {k: v for k, v in c.items() if k != "latencies"}
            | ({"median_latency_s": median(c["latencies"])} if c.get("latencies") else {})
            for c in s["columns"]]} for s in sections},
        "adaption": {"autoscientist": split.get("autoscientist"), "win_rate_vs_base": win_rate},
    }
    (data / "eval_results.json").write_text(json.dumps(results, indent=1) + "\n")
    return {"markdown": md, "results": results}


def load_env(env_dir: Optional[str]) -> None:
    """Load .env.local then .env from the repo root and --env-dir, never overriding or printing."""
    from dotenv import load_dotenv
    for base in [REPO_ROOT] + ([Path(env_dir).expanduser()] if env_dir else []):
        for name in (".env.local", ".env"):
            if (base / name).is_file():
                load_dotenv(base / name, override=False)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Fault-naming eval on SIMULATED held-out swings (raw and relative).")
    p.add_argument("--data", default="../data/raw/adaption", help="adaption_prep split --out folder")
    p.add_argument("--claude-sample", type=int, default=MAX_CLAUDE_SAMPLE, help="test rows for Claude (max 200)")
    p.add_argument("--no-claude", action="store_true", help="run the code rule only")
    p.add_argument("--adaption-win-rate", default=None,
                   help='Adaption\'s LoRA win rate vs base model, as text, e.g. "61%% vs base (n=200)"')
    p.add_argument("--env-dir", default=None, help="extra folder whose .env.local holds the Claude key")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=4, help="parallel Claude calls")
    a = p.parse_args(argv)
    load_env(a.env_dir)
    try:
        out = evaluate(Path(a.data), a.claude_sample, not a.no_claude, a.seed, a.workers, win_rate=a.adaption_win_rate)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(str(e))
    print(out["markdown"])


if __name__ == "__main__":
    main()
