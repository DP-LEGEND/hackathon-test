"""The wrist.run command end to end on a MOCK export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wrist.run import main
from wrist.synth import make_session


def test_run_writes_metrics_and_series(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    truth = make_session(tmp_path / "s", zip_export=True)
    out, series_out = tmp_path / "wrist_metrics.json", tmp_path / "wrist_series.json"
    assert main([truth["export"], "--contacts", truth["contacts"], "--video-tap", str(truth["video_tap_s"]),
                 "--out", str(out), "--series-out", str(series_out)]) == 0

    metrics = json.loads(out.read_text())
    series = json.loads(series_out.read_text())
    assert metrics["mock"] is True and series["mock"] is True
    assert set(metrics["swings"]) == set(truth["swings"]) == set(series["swings"])
    assert all(s["usable"] for s in metrics["swings"].values())
    assert series_out.stat().st_size < 20_000

    printed = capsys.readouterr().out
    assert printed.startswith("MOCK DATA.")
    assert "10/10 pairs within 100 ms" in printed and "10/10 swings usable" in printed


def test_run_with_camera_swings_writes_estimates_and_filled_swings(tmp_path: Path,
                                                                    capsys: pytest.CaptureFixture[str]) -> None:
    truth = make_session(tmp_path / "s", camera=True, mishit=(3,))
    out, series_out, filled = tmp_path / "m.json", tmp_path / "s.json", tmp_path / "filled"
    # A folder of swing JSONs as --contacts doubles as --swings.
    assert main([truth["export"], "--contacts", truth["swings_dir"], "--video-tap", str(truth["video_tap_s"]),
                 "--out", str(out), "--series-out", str(series_out), "--filled-out", str(filled)]) == 0

    metrics = json.loads(out.read_text())
    assert metrics["estimates"]["camera_swings"] == 10 and metrics["estimates"]["lever_m"] == 0.55
    assert all(s["racket_speed_sensor"]["value"] for s in metrics["swings"].values())
    assert sorted(p.stem for p in filled.glob("*.json")) == sorted(truth["swings"])  # --filled-out still works
    swing = json.loads((filled / "synth-01.json").read_text())
    assert swing["metadata"]["wristSensorFill"]["label"] == "ESTIMATE"
    assert swing["wrist"] == metrics["swings"]["synth-01"], "ready for the coach and compare()"

    printed = capsys.readouterr().out
    assert printed.count("ESTIMATES: racket") == 10 and "MOCK (sensor)" in printed and "filled wrist" in printed
    assert printed.count("ring-down") == 10 and "mishit" not in printed and "backswing to contact" in printed
    assert "10 camera swings read" in printed and "Wrote 10 swings with swing['wrist']" in printed


def test_run_with_a_shadow_swing_and_no_orientation_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    truth = make_session(tmp_path / "s", camera=True, shadow=(4,))
    (Path(truth["export"]) / "Orientation.csv").unlink()
    out, swings_out = tmp_path / "m.json", tmp_path / "swings"
    assert main([truth["export"], "--contacts", truth["swings_dir"], "--video-tap", str(truth["video_tap_s"]),
                 "--out", str(out), "--series-out", str(tmp_path / "s.json"), "--swings-out", str(swings_out)]) == 0
    m = json.loads(out.read_text())["swings"]["synth-05"]
    assert m["contact_source"] == "double tap" and m["impact"] is None and m["impact_s"] is None and m["usable"]
    assert json.loads((swings_out / "synth-05.json").read_text())["wrist"]["contact_source"] == "double tap"
    printed = capsys.readouterr().out
    assert "Orientation: integrated gyro" in printed and "1 swing(s) with no impact" in printed
    assert "synth-05: roll" in printed and "no impact: contact from the double tap" in printed
    assert "no impact (shadow swing)" in printed and "10/10 swings usable" in printed


def test_run_when_every_swing_is_a_shadow_swing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """No impacts at all: sync from the double tap only, impact fields null, no crash."""
    truth = make_session(tmp_path / "s", labels=("none",) * 3, shadow=(0, 1, 2))
    out = tmp_path / "m.json"
    assert main([truth["export"], "--contacts", truth["contacts"], "--video-tap", str(truth["video_tap_s"]),
                 "--out", str(out), "--series-out", str(tmp_path / "s.json")]) == 0
    metrics = json.loads(out.read_text())
    assert metrics["sync"]["alignment"]["n_impacts"] == 0 and len(metrics["sync"]["alignment"]["tap_only"]) == 3
    for sid, m in metrics["swings"].items():
        assert m["usable"] and m["contact_source"] == "double tap" and m["impact"] is None
        assert m["roll_change_deg"] == pytest.approx(truth["swings"][sid]["roll_change_deg"], abs=2.0)
    printed = capsys.readouterr().out
    assert "0 impacts vs 3 video contacts" in printed and "3/3 swings usable" in printed


def test_synth_cli_writes_json_truth_and_camera_swings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from wrist.synth import main as synth_main

    synth_main([str(tmp_path), "--camera", "--mishit", "2"])
    truth = json.loads((tmp_path / "truth.json").read_text())
    assert "motion" not in truth and truth["swings"]["synth-03"]["impact"] == "mishit"
    assert len(list((tmp_path / "swings").glob("*.json"))) == 10
    assert "--swings" in capsys.readouterr().out
