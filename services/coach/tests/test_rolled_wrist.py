"""rolled_wrist: the wrist-sensor fault. Offline: no Claude, no network.

Expected results come from THRESHOLDS, so retuning (python -m wrist.tune) doesn't break
these tests; only a broken rule does.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from coach.agent import coach_swing, main as agent_main
from coach.faults import (
    MOCK_ROLLED_WRIST, MOCK_SENSOR_NOTE, THRESHOLDS, WRIST_MOCK, detect_faults, measure_swing, severity,
)
from coach.wrist_sensor import NO_SENSOR, attach_wrist, sensor_metrics
from wrist.load import load_recording
from wrist.metrics import wrist_metrics
from wrist.sync import read_contacts, synchronise
from wrist.synth import make_session
from wrist.tune import tune

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "swing_sample.json"
RULE = THRESHOLDS["backhand"]["rolled_wrist"]


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text())


def wrist(roll: float, usable: bool = True, mock: bool = False, **extra) -> dict:
    """A wrist-sensor entry timed as the real lines were tuned (the gyro peak) unless extra says otherwise."""
    return {"usable": usable, "mock": mock, "roll_change_deg": -roll, "roll_change_abs_deg": roll,
            "peak_roll_rate_abs_dps": 8 * roll, "peak_angular_speed_dps": 1300, "skip_reason": None,
            "contact_source": "gyro peak", **extra}


def rolled(swing: dict, stroke: str = "backhand") -> dict | None:
    return next((f for f in detect_faults(swing, stroke) if f["id"] == "rolled_wrist"), None)


def test_without_a_sensor_rolled_wrist_is_skipped_not_guessed(sample: dict) -> None:
    m = measure_swing(sample, "backhand")
    assert m["forearm_roll_deg"] is None and m["wrist_sensor"] is None
    assert m["wrist_sensor_skipped"] == NO_SENSOR
    assert rolled(sample) is None
    assert "rolled_wrist" in coach_swing(sample, stroke="backhand")["not_measured"]


@pytest.mark.parametrize("stroke", ["forehand", "backhand"])
def test_a_big_roll_fires_with_the_measured_number(sample: dict, stroke: str) -> None:
    rule = THRESHOLDS[stroke]["rolled_wrist"]
    value = rule["severe_at"]
    f = rolled({**sample, "wrist": wrist(value)}, stroke)
    assert f is not None
    assert f["value"] == value and f["unit"] == "deg" and f["threshold"] == rule["threshold"]
    assert f["severity"] == pytest.approx(severity(value, rule)) == 1.0
    assert f["label"] == f"Rolled wrist: forearm rolls {value:.0f} deg through contact (wrist sensor)"
    assert f["fix"] == "firm_wrist" and f["ghost_ready"] is False, "no ghost edit for the wrist yet"
    assert f["source"] == rule["source"] and f["confidence"] == "low"
    assert f["fix_amount"] == pytest.approx(round(value - rule["target"], 1))


def test_a_normal_roll_does_not_fire_and_counts_as_measured(sample: dict) -> None:
    swing = {**sample, "wrist": wrist(RULE["target"])}
    assert rolled(swing) is None
    assert "rolled_wrist" not in coach_swing(swing, stroke="backhand")["not_measured"]


def test_mock_sensor_data_says_so_in_the_label(sample: dict) -> None:
    f = rolled({**sample, "wrist": wrist(RULE["severe_at"], mock=True)})
    assert f["label"].endswith(MOCK_SENSOR_NOTE)
    assert measure_swing({**sample, "wrist": wrist(30, mock=True)}, "backhand")["wrist_sensor"] == "mock sensor"
    assert MOCK_SENSOR_NOTE not in rolled({**sample, "wrist": wrist(RULE["severe_at"])})["label"]


@pytest.mark.parametrize("entry, why", [
    (wrist(80, usable=False, skip_reason="alignment error 300 ms > 100 ms"), "alignment error 300 ms > 100 ms"),
    ({"usable": True, "roll_change_abs_deg": float("nan"), "peak_roll_rate_abs_dps": 1,
      "peak_angular_speed_dps": 1}, "no roll_change_abs_deg"),
    ({"usable": True}, "no roll_change_abs_deg, peak_roll_rate_abs_dps, peak_angular_speed_dps"),
    ("not a dict", NO_SENSOR),
])
def test_untrusted_wrist_data_is_skipped_with_why(sample: dict, entry, why: str) -> None:
    m = measure_swing({**sample, "wrist": entry}, "backhand")
    assert m["forearm_roll_deg"] is None and why in m["wrist_sensor_skipped"]
    assert rolled({**sample, "wrist": entry}) is None


def test_sensor_metrics_maps_the_wrist_file_keys() -> None:
    out = sensor_metrics(wrist(50.0))
    assert out == {"forearm_roll_deg": 50.0, "forearm_roll_rate_dps": 400.0, "forearm_speed_dps": 1300.0,
                   "wrist_sensor": "sensor", "wrist_sensor_skipped": None, "wrist_contact_source": "gyro peak"}


def test_attach_wrist_by_swing_id_without_mutating(sample: dict) -> None:
    metrics = {"swings": {sample["id"]: wrist(70)}}
    attached = attach_wrist(sample, metrics)
    assert attached["wrist"]["roll_change_abs_deg"] == 70 and "wrist" not in sample
    missing = attach_wrist({**sample, "id": "other"}, metrics)
    assert missing["wrist"]["usable"] is False and "'other'" in missing["wrist"]["skip_reason"]


def test_coach_result_stays_valid_json_with_wrist_data(sample: dict) -> None:
    result = coach_swing({**sample, "wrist": wrist(RULE["severe_at"])}, stroke="backhand")
    json.dumps(result, allow_nan=False)
    ids = [result["fault"]["id"], *result["other_faults"]]
    assert "rolled_wrist" in ids
    assert result["metrics"]["forearm_roll_deg"] == RULE["severe_at"]


def test_agent_cli_attaches_the_wrist_file(sample: dict, tmp_path: Path, monkeypatch, capsys) -> None:
    wrist_file = tmp_path / "wrist_metrics.json"
    wrist_file.write_text(json.dumps({"mock": False, "swings": {sample["id"]: wrist(RULE["severe_at"])}}))
    monkeypatch.setattr(sys, "argv", ["coach.agent", str(SAMPLE), "--stroke", "backhand", "--wrist", str(wrist_file)])
    agent_main()
    result = json.loads(capsys.readouterr().out)
    assert result["metrics"]["wrist_sensor"] == "sensor"
    assert "rolled_wrist" in [result["fault"]["id"], *result["other_faults"]]


def test_end_to_end_from_a_mock_sensor_export(sample: dict, tmp_path: Path) -> None:
    """Synthetic export -> wrist metrics -> coach: rolled swings fire, normal ones don't.

    The synthetic forearm rolls far less than a real one (rolled ~62 deg vs real 128-165), so the
    coach judges mock data by MOCK_ROLLED_WRIST (what wrist.tune picks on this mock session), not
    the real-tuned lines, and the fix amount runs down to the mock good median.
    """
    truth = make_session(tmp_path)
    rec = load_recording(truth["export"])
    sync = synchronise(rec, read_contacts(truth["contacts"]), video_tap_s=truth["video_tap_s"])
    metrics, _ = wrist_metrics(rec, sync)
    mock_rule = tune(metrics, {sid: t["label"] for sid, t in truth["swings"].items()})["verdict"]["rule"]
    assert mock_rule == MOCK_ROLLED_WRIST and mock_rule["source"] == WRIST_MOCK
    for swing_id, t in truth["swings"].items():
        swing = attach_wrist({**sample, "id": swing_id}, metrics)
        f = rolled(swing)
        if t["label"] == "rolled_wrist":
            assert f is not None and f["label"].endswith(MOCK_SENSOR_NOTE), swing_id
            assert f["source"] == WRIST_MOCK and f["threshold"] == MOCK_ROLLED_WRIST["threshold"]
            assert f["fix_amount"] == pytest.approx(round(f["value"] - MOCK_ROLLED_WRIST["target"], 1))
        else:
            assert f is None, swing_id


@pytest.mark.parametrize("stroke", ["backhand", "forehand"])
def test_a_real_swing_at_the_mock_rolled_roll_does_not_fire(sample: dict, stroke: str) -> None:
    """Codex P2 on #74: 62 deg is a rolled MOCK swing but a normal real one (real good rolls are
    95-145 deg): real data keeps the per-stroke lines, mock data gets MOCK_ROLLED_WRIST."""
    assert rolled({**sample, "wrist": wrist(62.0)}, stroke) is None   # real, gyro-peak timed
    f = rolled({**sample, "wrist": wrist(62.0, mock=True)}, stroke)
    assert f is not None and f["threshold"] == MOCK_ROLLED_WRIST["threshold"] and f["source"] == WRIST_MOCK
    # the mock rule has no timing gate: a mock entry timed by its impact spike is still judged
    f = rolled({**sample, "wrist": wrist(62.0, mock=True, contact_source="impact spike")}, stroke)
    assert f is not None and f["label"].endswith(MOCK_SENSOR_NOTE)
