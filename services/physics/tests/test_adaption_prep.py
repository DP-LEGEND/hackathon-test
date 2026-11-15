"""Adaption data prep tests (mock swings and a made-up labels.csv only)."""

import csv
import json
import re
from pathlib import Path

import pytest

from physics.adaption_prep import (LABELS, autoscientist_rows, build_rows, clean_swing_ids, make_relative,
                                   oversample_none, relative_input, select_clean, write_split)
from physics.synth import METRIC_KEYS, generate
from physics.tests.swing_factory import make_swing

LABEL_COLUMNS = ["clip", "swing", "side", "intended_fault", "severity", "quality_1_to_5",
                 "outcome", "held_out", "comment", "pipeline_run"]
RUN = "run-01"  # mock pipeline run: the swing folder's name and labels.csv's pipeline_run
CLEAN = [f"fhsess-swing-000{i}" for i in range(1, 5)] + [f"bhsess-swing-000{i}" for i in range(1, 5)]
RELATIVE_FORMAT = re.compile(r"^(forehand|backhand); elbow [+-]\d+ deg vs your baseline; "
                             r"shoulder turn [+-]\d+ deg; wrist release [+-]\d+ ms$")


def write_labels(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        for row in rows:
            swing, side, fault, run = row if len(row) == 4 else (*row, RUN)
            w.writerow({"clip": "IMG_TEST", "swing": swing, "side": side, "intended_fault": fault, "pipeline_run": run})


@pytest.fixture()
def real_folder(tmp_path):
    d = tmp_path / RUN
    d.mkdir()
    sides = {name: ("forehand" if name.startswith("fh") else "backhand") for name in CLEAN}
    sides.update({"fhsess-swing-0009": "forehand", "bhsess-swing-0009": "backhand", "fhsess-swing-0010": "forehand"})
    for name, side in sides.items():
        (d / f"{name}.json").write_text(json.dumps(dict(make_swing(fps=120.0), side=side)))
    labels = tmp_path / "labels.csv"
    write_labels(labels, [(name, sides[name], "none") for name in CLEAN] + [
        ("fhsess-swing-0009", "forehand", "straight_arm"),                                          # acted fault
        ("bhsess-swing-0009", "backhand", "none"), ("bhsess-swing-0009", "backhand", "rolled_wrist"),  # runs disagree
    ])  # fhsess-swing-0010 has no label at all
    return d, labels


@pytest.fixture()
def synthetic(real_folder, tmp_path):
    src, labels = real_folder
    clean = tmp_path / "clean"
    select_clean(src, labels, clean)
    out = tmp_path / "synthetic"
    generate(clean, out, per_swing=6, seed=1)
    return clean, out


def load(path):
    return [json.loads(x) for x in open(path)]


def test_select_copies_only_swings_labelled_clean_everywhere(real_folder, tmp_path):
    src, labels = real_folder
    before = {p.name: p.read_bytes() for p in src.iterdir()}
    r = select_clean(src, labels, tmp_path / "clean")
    assert sorted(r["selected"]) == sorted(f"{n}.json" for n in CLEAN)
    assert len(r["skipped"]) == 3  # acted fault, disagreeing labels, no label
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before  # source untouched
    assert sorted(p.name for p in (tmp_path / "clean").iterdir()) == sorted(r["selected"])


def test_select_refuses_to_write_into_the_source(real_folder):
    src, labels = real_folder
    with pytest.raises(ValueError, match="different folder"):
        select_clean(src, labels, src)


def test_select_refuses_a_non_empty_out_folder(real_folder, tmp_path):
    src, labels = real_folder
    out = tmp_path / "clean"
    out.mkdir()
    select_clean(src, labels, out / "fresh")  # a new folder is fine
    (out / "old-swing.json").write_text("{}")  # left over from an earlier run
    with pytest.raises(ValueError, match="--out must be empty or new; stale swings"):
        select_clean(src, labels, out)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert len(select_clean(src, labels, empty)["selected"]) == len(CLEAN)  # an existing empty folder is fine


def test_side_mismatch_is_skipped(tmp_path):
    d = tmp_path / RUN
    d.mkdir()
    (d / "x.json").write_text(json.dumps(dict(make_swing(fps=120.0), side="backhand")))
    labels = tmp_path / "labels.csv"
    write_labels(labels, [("x", "forehand", "none")])
    r = select_clean(d, labels, tmp_path / "clean")
    assert r["selected"] == [] and "side" in r["skipped"][0]


PAIR = "7178110a0b06-swing-0024"  # real labels.csv pair: none in fh-04, early_wrist in fh-05


def test_same_swing_id_is_only_taken_from_the_run_where_it_is_clean(tmp_path):
    runs = {}
    for run, fps in (("fh-04", 120.0), ("fh-05", 240.0)):  # different fps so the copies can be told apart
        d = tmp_path / run
        d.mkdir()
        (d / f"{PAIR}.json").write_text(json.dumps(dict(make_swing(fps=fps), side="forehand")))
        runs[run] = d
    labels = tmp_path / "labels.csv"
    write_labels(labels, [(PAIR, "forehand", "none", "fh-04"), (f"{PAIR}@fh-05", "forehand", "early_wrist", "fh-05")])
    r = select_clean([runs["fh-04"], runs["fh-05"]], labels, tmp_path / "clean")
    assert r["selected"] == [f"{PAIR}.json"] and r["runs"] == {f"{PAIR}.json": "fh-04"}
    assert (tmp_path / "clean" / f"{PAIR}.json").read_bytes() == (runs["fh-04"] / f"{PAIR}.json").read_bytes()
    assert any("(fh-05): not labelled clean in fh-05" in x for x in r["skipped"])


def test_repo_labels_key_the_pair_by_run():
    labels = Path(__file__).resolve().parents[3] / "data/labels/labels.csv"
    if not labels.is_file():
        pytest.skip("data/labels/labels.csv not in this checkout")
    clean = clean_swing_ids(labels)
    assert clean[("fh-04", PAIR)] == "forehand"
    assert ("fh-05", PAIR) not in clean


def test_a_swing_with_no_run_stops_with_its_name(tmp_path):
    d = tmp_path / "real_swings"  # flat folder: not a run, and the file has no run field
    d.mkdir()
    (d / f"{PAIR}.json").write_text(json.dumps(dict(make_swing(fps=120.0), side="forehand")))
    labels = tmp_path / "labels.csv"
    write_labels(labels, [(PAIR, "forehand", "none", "fh-04")])
    with pytest.raises(ValueError, match=f"{PAIR}.json: can't tell which pipeline run"):
        select_clean(d, labels, tmp_path / "clean")
    assert not (tmp_path / "clean").exists()  # nothing copied


def test_a_run_field_in_the_swing_beats_its_folder(tmp_path):
    d = tmp_path / "anywhere"
    d.mkdir()
    (d / f"{PAIR}.json").write_text(json.dumps(dict(make_swing(fps=120.0), side="forehand", pipeline_run="fh-04")))
    labels = tmp_path / "labels.csv"
    write_labels(labels, [(PAIR, "forehand", "none", "fh-04"), (f"{PAIR}@fh-05", "forehand", "early_wrist", "fh-05")])
    assert select_clean(d, labels, tmp_path / "clean")["runs"] == {f"{PAIR}.json": "fh-04"}


def test_a_label_without_a_run_is_ignored(real_folder, tmp_path):
    src, labels = real_folder
    rows = list(csv.DictReader(open(labels)))
    rows.insert(0, {"clip": "IMG_OLD", "swing": "fhsess-swing-0009", "side": "forehand", "intended_fault": "none",
                    "pipeline_run": ""})  # unscoped: no pipeline_run, no "@run" suffix
    rows.insert(0, {"clip": "IMG_OLD", "swing": "fhsess-swing-0001", "side": "forehand", "intended_fault": "elbow_bend",
                    "pipeline_run": ""})  # would make a clean swing faulty if it weren't ignored
    with open(labels, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    r = select_clean(src, labels, tmp_path / "clean")
    assert sorted(r["selected"]) == sorted(f"{n}.json" for n in CLEAN)  # same clean swings as without them
    assert ("", "fhsess-swing-0009") not in clean_swing_ids(labels)


def test_a_suffix_that_disagrees_with_pipeline_run_is_refused(tmp_path):
    labels = tmp_path / "labels.csv"
    write_labels(labels, [(f"{PAIR}@fh-05", "forehand", "none", "fh-04")])
    with pytest.raises(ValueError, match="says run 'fh-05' but pipeline_run is 'fh-04'"):
        clean_swing_ids(labels)


def test_rows_have_stroke_in_input_and_fault_name_only(synthetic):
    clean, out = synthetic
    rows = build_rows(out, clean)
    assert len(rows) == 56  # 8 clean swings x (1 unchanged + 6 edits)
    for r in rows:
        assert r["output"] in LABELS and not any(ch.isdigit() for ch in r["output"])
        assert r["input"].startswith(r["stroke"] + ", ") and "elbow at contact" in r["input"]
    assert {r["stroke"] for r in rows} == {"forehand", "backhand"}
    assert {r["output"] for r in rows} == set(LABELS)


def test_relative_input_format():
    deltas = {"elbow_at_contact_deg": 21.4, "shoulder_turn_deg": -4.2, "wrist_release_ms": -0.3}
    assert relative_input("backhand", deltas) == \
        "backhand; elbow +21 deg vs your baseline; shoulder turn -4 deg; wrist release +0 ms"


def _row(source, fault, elbow, stroke="forehand"):
    m = {"elbow_at_contact_deg": elbow, "shoulder_turn_deg": 60.0, "wrist_release_ms": 20.0}
    return {"name": f"{source}__{fault}", "source": f"{source}.json", "stroke": stroke, "output": fault,
            "fault": fault, "measured_size": 0.0, "input": "raw", **m}


def test_baseline_is_the_players_other_clean_training_swings():
    train = [_row("s1-swing-0001", "none", 100), _row("s1-swing-0002", "none", 110),
             _row("s1-swing-0003", "none", 120), _row("s1-swing-0001", "elbow_bend", 80),
             _row("s2-swing-0001", "none", 300), _row("s2-swing-0002", "none", 310)]  # another player
    test = [_row("s1-swing-0009", "none", 200), _row("s1-swing-0009", "elbow_bend", 180)]
    tr, te, summary = make_relative(train, test)
    assert summary == {"s1 forehand": 3, "s2 forehand": 2}
    assert tr[0]["elbow_at_contact_deg"] == pytest.approx(100 - 115)  # own swing left out: mean(110, 120)
    assert tr[3]["elbow_at_contact_deg"] == pytest.approx(80 - 115)
    assert tr[4]["elbow_at_contact_deg"] == pytest.approx(300 - 310)  # only its own player's swings
    assert te[0]["elbow_at_contact_deg"] == pytest.approx(200 - 110)  # test swings never feed a baseline
    assert te[1]["baseline_swings"] == 3 and te[1]["raw_elbow_at_contact_deg"] == 180
    assert te[1]["input"] == "forehand; elbow +70 deg vs your baseline; shoulder turn +0 deg; wrist release +0 ms"


def test_baseline_needs_another_clean_swing():
    with pytest.raises(ValueError, match="no other clean training swing"):
        make_relative([_row("s1-swing-0001", "none", 100), _row("s1-swing-0001", "elbow_bend", 80)], [])


def test_split_is_by_source_and_autoscientist_holds_train_rows_only(synthetic, tmp_path):
    clean, out = synthetic
    m = write_split(out, clean, tmp_path / "split", test_share=0.25, seed=0)
    d = tmp_path / "split"
    train, test = load(d / "train_rows.jsonl"), load(d / "test_rows.jsonl")
    train_rel, test_rel = load(d / "train_rows_relative.jsonl"), load(d / "test_rows_relative.jsonl")
    assert not {r["source"] for r in train} & {r["source"] for r in test}
    assert {r["stroke"] for r in test} == {"forehand", "backhand"}
    assert [r["name"] for r in train_rel] == [r["name"] for r in train]
    assert [r["name"] for r in test_rel] == [r["name"] for r in test]
    assert all(RELATIVE_FORMAT.match(r["input"]) for r in train_rel + test_rel)
    clean_train = {s: sum(r["output"] == "none" and r["stroke"] == s for r in train) for s in ("forehand", "backhand")}
    assert all(r["baseline_swings"] == clean_train[r["stroke"]] - 1 for r in train_rel)  # own swing left out
    assert all(r["baseline_swings"] == clean_train[r["stroke"]] for r in test_rel)
    auto = load(d / "autoscientist_train.jsonl")
    assert auto == autoscientist_rows(oversample_none(train_rel, 0))  # built from training rows only
    assert all(set(x) == {"prompt", "completion"} and x["completion"] in LABELS for x in auto)
    assert all("SIMULATED" in x["prompt"] and x["prompt"].endswith("\nFault:") for x in auto)
    assert sum(x["completion"] == "none" for x in auto) > sum(r["output"] == "none" for r in train)
    assert m["autoscientist"]["rows"] == len(auto) and "SIMULATED" in m["data"]
    assert sum(m["autoscientist"]["labels"].values()) == len(auto)


def test_same_seed_gives_same_split(synthetic, tmp_path):
    clean, out = synthetic
    write_split(out, clean, tmp_path / "a", seed=3)
    write_split(out, clean, tmp_path / "b", seed=3)
    for name in ("train_rows.jsonl", "test_rows_relative.jsonl", "autoscientist_train.jsonl"):
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()


def test_oversample_none_reaches_the_average_fault_count():
    rows = [{"output": "none"}] * 2 + [{"output": "elbow_bend"}] * 10 + [{"output": "wrist_early"}] * 6
    out = oversample_none(rows, seed=0)
    assert sum(r["output"] == "none" for r in out) == 8
    assert sum(r["output"] == "elbow_bend" for r in out) == 10


def test_metric_keys_are_the_three_the_inputs_describe():
    assert METRIC_KEYS == ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_release_ms")
