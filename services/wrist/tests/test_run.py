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
