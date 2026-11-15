"""Adaption data prep tests (mock swings and a made-up labels.csv only)."""

import csv
import json

import pytest

from physics.adaption_prep import LABELS, build_rows, oversample_none, select_clean, write_split
from physics.synth import generate
from physics.tests.swing_factory import make_swing

LABEL_COLUMNS = ["clip", "swing", "side", "intended_fault", "severity", "quality_1_to_5",
                 "outcome", "held_out", "comment"]


def write_labels(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        for swing, side, fault in rows:
            w.writerow({"clip": "IMG_TEST", "swing": swing, "side": side, "intended_fault": fault})


@pytest.fixture()
def real_folder(tmp_path):
    d = tmp_path / "real"
    d.mkdir()
    sides = {"fh_clean_a": "forehand", "fh_clean_b": "forehand", "bh_clean_a": "backhand",
             "bh_clean_b": "backhand", "fh_faulty": "forehand", "bh_twice": "backhand",
             "fh_unlabelled": "forehand"}
    for name, side in sides.items():
        (d / f"{name}.json").write_text(json.dumps(dict(make_swing(fps=120.0), side=side)))
    labels = tmp_path / "labels.csv"
    write_labels(labels, [
        ("fh_clean_a", "forehand", "none"), ("fh_clean_b", "forehand", "none"),
        ("bh_clean_a", "backhand", "none"), ("bh_clean_b", "backhand", "none"),
        ("fh_faulty", "forehand", "straight_arm"),
        ("bh_twice", "backhand", "none"), ("bh_twice", "backhand", "rolled_wrist"),  # two runs disagree
    ])
    return d, labels


@pytest.fixture()
def synthetic(real_folder, tmp_path):
    src, labels = real_folder
    clean = tmp_path / "clean"
    select_clean(src, labels, clean)
    out = tmp_path / "synthetic"
    generate(clean, out, per_swing=6, seed=1)
    return clean, out


def test_select_copies_only_swings_labelled_clean_everywhere(real_folder, tmp_path):
    src, labels = real_folder
    before = {p.name: p.read_bytes() for p in src.iterdir()}
    r = select_clean(src, labels, tmp_path / "clean")
    assert sorted(r["selected"]) == ["bh_clean_a.json", "bh_clean_b.json", "fh_clean_a.json", "fh_clean_b.json"]
    assert len(r["skipped"]) == 3  # acted fault, disagreeing labels, no label
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before  # source untouched
    assert sorted(p.name for p in (tmp_path / "clean").iterdir()) == sorted(r["selected"])


def test_select_refuses_to_write_into_the_source(real_folder):
    src, labels = real_folder
    with pytest.raises(ValueError, match="different folder"):
        select_clean(src, labels, src)


def test_side_mismatch_is_skipped(tmp_path):
    d = tmp_path / "real"
    d.mkdir()
    (d / "x.json").write_text(json.dumps(dict(make_swing(fps=120.0), side="backhand")))
    labels = tmp_path / "labels.csv"
    write_labels(labels, [("x", "forehand", "none")])
    r = select_clean(d, labels, tmp_path / "clean")
    assert r["selected"] == [] and "side" in r["skipped"][0]


def test_rows_have_stroke_in_input_and_fault_name_only(synthetic):
    clean, out = synthetic
    rows = build_rows(out, clean)
    assert len(rows) == 28  # 4 clean swings x (1 unchanged + 6 edits)
    for r in rows:
        assert r["output"] in LABELS and not any(ch.isdigit() for ch in r["output"])
        assert r["input"].startswith(r["stroke"] + ", ") and "elbow at contact" in r["input"]
    assert {r["stroke"] for r in rows} == {"forehand", "backhand"}
    assert {r["output"] for r in rows} == set(LABELS)


def test_split_is_by_source_and_only_train_is_oversampled(synthetic, tmp_path):
    clean, out = synthetic
    m = write_split(out, clean, tmp_path / "split", test_share=0.5, seed=0)
    d = tmp_path / "split"
    load = lambda name: [json.loads(x) for x in open(d / name)]  # noqa: E731
    train, test = load("train_rows.jsonl"), load("test_rows.jsonl")
    assert not {r["source"] for r in train} & {r["source"] for r in test}
    assert {r["stroke"] for r in test} == {"forehand", "backhand"}
    tuned = load("adaption_train.jsonl")
    assert all(set(x) == {"input", "output"} for x in tuned)
    assert sum(x["output"] == "none" for x in tuned) > sum(r["output"] == "none" for r in train)
    assert load("adaption_test.jsonl") == [{"input": r["input"], "output": r["output"]} for r in test]
    assert "SIMULATED" in m["data"]
    assert m["counts"]["test"]["none"] == sum(r["output"] == "none" for r in test)


def test_same_seed_gives_same_split(synthetic, tmp_path):
    clean, out = synthetic
    write_split(out, clean, tmp_path / "a", seed=3)
    write_split(out, clean, tmp_path / "b", seed=3)
    for name in ("train_rows.jsonl", "test_rows.jsonl", "adaption_train.jsonl"):
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()


def test_oversample_none_reaches_the_average_fault_count():
    rows = [{"output": "none"}] * 2 + [{"output": "elbow_bend"}] * 10 + [{"output": "wrist_early"}] * 6
    out = oversample_none(rows, seed=0)
    assert sum(r["output"] == "none" for r in out) == 8
    assert sum(r["output"] == "elbow_bend" for r in out) == 10
