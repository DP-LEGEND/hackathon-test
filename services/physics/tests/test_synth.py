"""Synthetic data generator tests (mock swings only)."""

import csv
import json

import pytest

from physics.synth import CSV_COLUMNS, generate, main
from physics.tests.swing_factory import make_swing


@pytest.fixture()
def good_folder(tmp_path):
    d = tmp_path / "good"
    d.mkdir()
    (d / "fh_a.json").write_text(json.dumps(make_swing()))
    (d / "fh_b.json").write_text(json.dumps(make_swing(fps=120.0)))
    return d


def test_generate_writes_csv_jsonl_and_swings(good_folder, tmp_path):
    s = generate(good_folder, tmp_path / "out", per_swing=6, seed=1)
    assert s["sources"] == 2 and s["rows"] == 14 and s["skipped"] == []

    rows = list(csv.DictReader(open(s["csv"])))
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert sum(r["fault"] == "none" for r in rows) == 2
    for r in rows:
        if r["fault"] == "none":
            continue
        tol = 1e-3 if r["unit"] == "deg" else 1000 / 120  # wrist timing: within one frame
        assert float(r["measured_size"]) == pytest.approx(float(r["requested_size"]), abs=tol)
        swing = json.loads(open(r["swing_json"]).read())
        assert swing["synthetic"] is True and swing["edits"][0]["id"] == r["fault"]

    lines = [json.loads(x) for x in open(s["jsonl"])]
    assert len(lines) == 14
    for line in lines:
        assert set(line) == {"input", "output", "cue"}
        assert line["cue"] == ""
        assert "elbow at contact" in line["input"] and "shoulder turn" in line["input"]
    outputs = {line["output"].split()[0] for line in lines}
    assert outputs == {"none", "elbow_bend", "shoulder_turn", "wrist_early"}


def test_same_seed_gives_same_output(good_folder, tmp_path):
    a = generate(good_folder, tmp_path / "a", per_swing=3, seed=7)
    b = generate(good_folder, tmp_path / "b", per_swing=3, seed=7)
    assert open(a["jsonl"]).read() == open(b["jsonl"]).read()


def test_empty_folder_is_a_clear_error(tmp_path, capsys):
    with pytest.raises(SystemExit, match="no .json swings"):
        main([str(tmp_path), "--out", str(tmp_path / "out")])
