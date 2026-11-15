"""Adaption eval tests (made-up rows and a fake Claude client; no network, no keys)."""

import json
from types import SimpleNamespace

import pytest

from physics import adaption_eval as ev
from physics.adaption_prep import LABELS


def row(name, source, stroke, fault, elbow, shoulder, wrist):
    return {"name": name, "source": source, "stroke": stroke, "hand": "R", "fault": fault, "output": fault,
            "measured_size": 0.0, "elbow_at_contact_deg": elbow, "shoulder_turn_deg": shoulder,
            "wrist_release_ms": wrist,
            "input": f"{stroke}, right-handed swing; elbow at contact {elbow:.0f} deg; "
                     f"shoulder turn {shoulder:.0f} deg; wrist release {wrist:.0f} ms before contact"}


def toy_rows(prefix, n_sources=4):
    """Per source and stroke: one unchanged row and one clearly moved row per fault."""
    rows = []
    for s in range(n_sources):
        for stroke in ("forehand", "backhand"):
            src = f"{prefix}{stroke}{s}"
            e, sh, w = 120 + s, 60 + s, 40 + s
            rows += [row(f"{src}_none", src, stroke, "none", e, sh, w),
                     row(f"{src}_e", src, stroke, "elbow_bend", e - 25, sh, w),
                     row(f"{src}_s", src, stroke, "shoulder_turn", e, sh - 25, w),
                     row(f"{src}_w", src, stroke, "wrist_early", e, sh, w + 60)]
    return rows


class FakeClient:
    """Stands in for anthropic.Anthropic: says elbow_bend for elbow angles in the 90s, else none."""

    def __init__(self):
        self.calls = 0
        self.systems = set()
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    def parse(self, **kw):
        self.calls += 1
        self.systems.add(kw["system"])
        assert kw["model"] == "claude-opus-5-5" and kw["output_format"] is ev.FaultCall
        fault = "elbow_bend" if "elbow at contact 9" in kw["messages"][0]["content"] else "none"
        return SimpleNamespace(stop_reason="end_turn", parsed_output=ev.FaultCall(fault=fault),
                               model="claude-opus-5-5", usage=SimpleNamespace(input_tokens=100, output_tokens=10))


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for name, rows in (("train_rows.jsonl", toy_rows("tr")), ("test_rows.jsonl", toy_rows("te")),
                       ("train_rows_relative.jsonl", toy_rows("tr")), ("test_rows_relative.jsonl", toy_rows("te"))):
        (tmp_path / name).write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "split.json").write_text(json.dumps({
        "data": "SIMULATED: test", "baseline": "mean of the player's other clean training swings",
        "autoscientist": {"file": str(tmp_path / "autoscientist_train.jsonl"), "rows": 1373,
                          "labels": {"none": 343}, "format": "prompt/completion, train only"}}))
    return tmp_path


def test_rule_fitted_on_train_names_clear_faults():
    train, test = toy_rows("tr"), toy_rows("te")
    rule = ev.fit_rule(train)
    assert [rule.predict(r) for r in test] == [r["output"] for r in test]


def test_score_counts_recall_and_false_alarms_on_none():
    s = ev.score(["none", "none", "elbow_bend", "wrist_early"], ["none", "wrist_early", "elbow_bend", "refused"])
    assert s["correct"] == 2 and s["accuracy"] == 0.5
    assert s["recall"]["none"] == {"hit": 1, "total": 2, "rate": 0.5}
    assert s["false_alarms_on_none"] == {"count": 1, "total": 2}
    assert s["not_a_label"] == 1 and s["recall"]["shoulder_turn"]["rate"] is None


def test_sample_keeps_every_none_row_and_spreads_the_faults():
    rows = toy_rows("x", n_sources=10)  # 20 rows of each label
    s = ev.stratified_sample(rows, 50, seed=0)
    assert len(s) == 50 and sum(r["output"] == "none" for r in s) == 20
    assert sorted(sum(r["output"] == f for r in s) for f in LABELS[1:]) == [10, 10, 10]


def test_own_copy_diagnostic_uses_each_rows_own_source():
    rows = toy_rows("x")
    assert ev.own_copy_accuracy(rows) == (len(rows), len(rows))


def test_claude_prompt_carries_training_knowledge_only_as_text():
    train = toy_rows("tr")
    rule = ev.fit_rule(train)
    raw = ev.claude_system_prompt(rule, train, "raw")
    rel = ev.claude_system_prompt(rule, train, "relative")
    for system in (raw, rel):
        assert "SIMULATED" in system and "- forehand:" in system and "- backhand:" in system
        assert system.count(" -> ") == 3 * len(LABELS)
    assert "baseline" in rel and "+ means earlier" in rel and "+ means earlier" not in raw


def test_both_formats_run_and_claude_answers_are_cached(data_dir):
    first = FakeClient()
    out1 = ev.evaluate(data_dir, claude_sample=20, client=first, workers=2)
    assert first.calls == 40 and len(first.systems) == 2  # 20 rows per format, one prompt per format
    again = FakeClient()
    out = ev.evaluate(data_dir, claude_sample=20, client=again, workers=2)
    assert again.calls == 0
    for mode in ("raw", "relative"):
        claude = out["results"]["sections"][mode]["columns"][2]
        assert claude["name"].startswith("(b) Claude claude-opus-5-5") and claude["score"]["rows"] == 20
    md = out["markdown"]
    assert md == (data_dir / "eval_report.md").read_text()
    assert "20 new calls, 0 rows from cache" in out1["markdown"] and "0 new calls, 20 rows from cache" in md
    assert md.count("(SIMULATED)") >= 2 and "Raw numbers" in md and "baseline-relative" in md


def test_claude_is_skipped_cleanly_without_a_key(data_dir):
    out = ev.evaluate(data_dir, claude_sample=5)
    for mode in ("raw", "relative"):
        assert out["results"]["sections"][mode]["columns"][2]["skipped"] == "ANTHROPIC_API_KEY is not set"


def test_adaption_win_rate_slot_is_filled_by_hand(data_dir):
    out = ev.evaluate(data_dir, use_claude=False)
    assert "fill in by hand" in out["markdown"] and out["results"]["adaption"]["win_rate_vs_base"] is None
    out = ev.evaluate(data_dir, use_claude=False, win_rate="61% vs base model (n=200)")
    assert "Win rate vs base model: 61% vs base model (n=200)" in out["markdown"]
    assert out["results"]["adaption"]["win_rate_vs_base"] == "61% vs base model (n=200)"
    assert "autoscientist_train.jsonl`, 1373 rows" in out["markdown"]


def test_overlapping_sources_are_refused(data_dir):
    (data_dir / "test_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in toy_rows("tr")))
    with pytest.raises(ValueError, match="both train and test"):
        ev.evaluate(data_dir, use_claude=False)


def test_claude_sample_is_capped_at_200(data_dir):
    with pytest.raises(ValueError, match="1..200"):
        ev.evaluate(data_dir, claude_sample=201, use_claude=False)
