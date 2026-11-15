"""scripts/make_mock_wrist_sample.py: a MOCK wrist swing becomes a /ghost sample with a firm-wrist ghost.

Runs on a tmp copy of the catalogue, never on public/swings. The swing is swing_factory mock data
with a hand-made mock wrist entry.
"""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from physics.tests.swing_factory import make_swing

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("make_mock_wrist_sample", REPO / "scripts" / "make_mock_wrist_sample.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_session(root: Path, roll: float = 60.8, mock: bool = True) -> Path:
    (root / "filled").mkdir(parents=True)
    swing = {**make_swing(), "id": "synth-07", "fpsReal": 240.0, "synthetic": True,
             "metadata": {"hand": "R", "mock": mock},
             "wrist": {"usable": True, "mock": mock, "roll_change_deg": roll, "roll_change_abs_deg": roll,
                       "peak_roll_rate_abs_dps": 8 * roll, "peak_angular_speed_dps": 1300, "skip_reason": None}}
    (root / "filled" / "synth-07.json").write_text(json.dumps(swing))
    series = {"mock": mock, "window_ms": [-150, 100], "swings": {
        "synth-07": {"usable": True, "t_ms": [-150, 0, 100], "roll_deg": [0.0, roll / 2, roll], "roll_change_deg": roll},
        "synth-01": {"usable": True, "t_ms": [-150, 100], "roll_deg": [0.0, 16.5], "roll_change_deg": 16.5}}}
    (root / "wrist_series.json").write_text(json.dumps(series))
    return root


@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    out = tmp_path / "swings"
    out.mkdir()
    shutil.copy(REPO / "public" / "swings" / "catalogue.json", out / "catalogue.json")
    return out


def test_a_rolled_mock_swing_becomes_a_sample_whose_ghost_goes_straight(script, tmp_path, out_dir) -> None:
    before = json.loads((out_dir / "catalogue.json").read_text())
    assert script.main([str(mock_session(tmp_path / "mock")), "--out-dir", str(out_dir)]) == 0
    after = json.loads((out_dir / "catalogue.json").read_text())
    entry = after["swings"][-1]
    assert entry["id"] == "mock_wrist_synth_07" and "MOCK" in entry["label"] and entry["madeBy"] == script.MADE_BY
    # firm_wrist is offered (top-level list and unit); everything else in the catalogue is as it was
    assert after["fixes"] == before["fixes"] + ["firm_wrist"] and after["units"]["firm_wrist"] == "deg"
    assert after["swings"][:-1] == before["swings"] and after["defaultSwing"] == before["defaultSwing"]
    assert after["demoAmounts"] == before["demoAmounts"]
    coach = json.loads((out_dir / entry["coach"]).read_text())
    assert coach["fault"]["id"] == "rolled_wrist" and coach["cue"] == "Keep your wrist firm through contact."
    assert coach["ghost_fix"] == "firm_wrist" and coach["ghost_note"] is None
    fix = entry["fixes"]["firm_wrist"]
    assert fix["flagged"] is True and fix["amount"] == pytest.approx(60.8 - 16.5, abs=0.05)
    result = json.loads((out_dir / fix["file"]).read_text())
    launch = result["assumptions"]["launch"]
    assert launch["ghost"]["azimuth"]["value"] == 0.0 and abs(launch["you"]["azimuth"]["value"]) > 10
    assert launch["you"]["azimuth"]["label"] == "MOCK (sensor)" and result["delta"]["ball"]["label"] == "PREDICTED"
    series = json.loads((out_dir / entry["wristSeries"]).read_text())
    assert list(series["swings"]) == ["mock_wrist_synth_07"] and series["mock"] is True


def test_it_refuses_real_data_and_an_existing_sample(script, tmp_path, out_dir, capsys) -> None:
    real = mock_session(tmp_path / "real", mock=False)
    assert script.main([str(real), "--out-dir", str(out_dir)]) == 2
    assert "isn't mock data" in capsys.readouterr().err
    mock = mock_session(tmp_path / "mock")
    assert script.main([str(mock), "--out-dir", str(out_dir)]) == 0
    assert script.main([str(mock), "--out-dir", str(out_dir)]) == 2
    assert "pass --replace" in capsys.readouterr().err
    assert script.main([str(mock), "--out-dir", str(out_dir), "--replace"]) == 0
    ids = [s["id"] for s in json.loads((out_dir / "catalogue.json").read_text())["swings"]]
    assert ids.count("mock_wrist_synth_07") == 1


def test_it_never_replaces_a_sample_it_did_not_make(script, tmp_path, out_dir, capsys) -> None:
    hero = json.loads((out_dir / "catalogue.json").read_text())["defaultSwing"]
    mock = mock_session(tmp_path / "mock")
    assert script.main([str(mock), "--out-dir", str(out_dir), "--id", hero, "--replace"]) == 2
    assert "not made by this script" in capsys.readouterr().err
