"""Per-swing wrist numbers against the synthetic truth (MOCK data from wrist.synth)."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation, Slerp

from wrist.metrics import (
    SERIES_MS, WINDOW_MS, axis_vector, body_rotations, gyro_convention, swing_metrics, twist_deg, wrist_metrics,
)


@pytest.mark.parametrize("name", ["session", "session_inverse"])
def test_numbers_match_the_truth_for_either_quaternion_convention(name: str, request) -> None:
    s = request.getfixturevalue(name)
    assert s.metrics["sensor"]["quaternion"]["convention"] == s.truth["quat_convention"]
    assert s.metrics["sensor"]["quaternion"]["ok"]
    for swing, truth in s.truth["swings"].items():
        m = s.metrics["swings"][swing]
        assert m["usable"] and m["skip_reason"] is None and m["mock"] is True
        assert m["roll_change_deg"] == pytest.approx(truth["roll_change_deg"], abs=1.5)
        assert m["roll_change_abs_deg"] == abs(m["roll_change_deg"])
        assert m["roll_change_gyro_deg"] == pytest.approx(truth["roll_change_deg"], abs=1.5)
        assert m["peak_roll_rate_dps"] == pytest.approx(truth["peak_roll_rate_dps"], rel=0.03)
        assert m["peak_angular_speed_dps"] == pytest.approx(truth["peak_angular_speed_dps"], rel=0.03)
        assert m["window_ms"] == list(WINDOW_MS)


def test_rolled_swings_roll_more_than_normal_ones(session) -> None:
    rolls = {lab: [session.metrics["swings"][sid]["roll_change_abs_deg"]
                   for sid, t in session.truth["swings"].items() if t["label"] == lab]
             for lab in ("none", "rolled_wrist")}
    assert min(rolls["rolled_wrist"]) > max(rolls["none"])


def test_series_is_small_and_ends_the_window_on_the_quoted_number(session) -> None:
    assert set(session.series["swings"]) == set(session.truth["swings"])
    assert session.series["mock"] is True
    for swing, ser in session.series["swings"].items():
        t, roll = ser["t_ms"], ser["roll_deg"]
        assert len(t) == len(roll) == (SERIES_MS[1] - SERIES_MS[0]) // 10 + 1
        assert t[0] == SERIES_MS[0] and t[-1] == SERIES_MS[1] and 0 in t
        assert roll[t.index(WINDOW_MS[0])] == pytest.approx(0.0, abs=0.05)
        assert roll[t.index(WINDOW_MS[1])] == pytest.approx(ser["roll_change_deg"], abs=0.11)
        assert ser["roll_change_deg"] == session.metrics["swings"][swing]["roll_change_deg"]
    assert len(json.dumps(session.series, separators=(",", ":"))) < 20_000


def test_outputs_are_valid_json(session) -> None:
    json.dumps(session.metrics, allow_nan=False)
    json.dumps(session.series, allow_nan=False)


def test_twist_ignores_the_swing_about_other_axes() -> None:
    y = axis_vector("y")
    for swing_deg in (0, 45, 120):
        rel = Rotation.from_euler("z", swing_deg, degrees=True) * Rotation.from_euler("y", 30, degrees=True)
        assert twist_deg(rel, y)[0] == pytest.approx(30.0)
    assert twist_deg(Rotation.from_euler("y", -50, degrees=True), y)[0] == pytest.approx(-50.0)
    assert twist_deg(Rotation.from_euler("y", 30, degrees=True), axis_vector("-y"))[0] == pytest.approx(-30.0)


def test_axis_vector() -> None:
    assert axis_vector("Y").tolist() == [0, 1, 0] and axis_vector("-x").tolist() == [-1, 0, 0]
    with pytest.raises(ValueError):
        axis_vector("w")


def test_wrong_forearm_axis_is_flagged(session) -> None:
    metrics, _ = wrist_metrics(session.rec, session.sync, axis="x")
    assert metrics["sensor"]["axis_hint"] == {"chosen": "x", "dominant_accel_axis": "y", "agrees": False}
    assert any("--axis" in w for w in metrics["warnings"])
    assert session.metrics["sensor"]["axis_hint"]["agrees"] is True


def test_orientation_that_disagrees_with_the_gyro_makes_swings_unusable(session) -> None:
    rec = copy.copy(session.rec)
    rng = np.random.default_rng(3)
    rec.quat = Rotation.random(rec.t.size, random_state=rng).as_quat()  # nonsense attitude
    assert gyro_convention(rec)["ok"] is False
    metrics, series = wrist_metrics(rec, session.sync)
    assert all(not m["usable"] and "gyro" in m["skip_reason"] for m in metrics["swings"].values())
    assert all(s["usable"] is False for s in series["swings"].values())


def test_misaligned_and_unpaired_swings_are_skipped_with_a_reason(session) -> None:
    sync = copy.deepcopy(session.sync)
    first = sync["alignment"]["pairs"][0]
    first["ok"], first["error_ms"] = False, 250.0
    sync["alignment"]["unpaired_swings"] = ["lost-swing"]
    metrics, series = wrist_metrics(session.rec, sync)
    assert metrics["swings"][first["swing"]]["usable"] is False
    assert "250 ms" in metrics["swings"][first["swing"]]["skip_reason"]
    assert "roll_change_deg" not in metrics["swings"][first["swing"]], "no numbers for an untrusted impact"
    assert first["swing"] not in series["swings"]
    assert metrics["swings"]["lost-swing"] == {
        "usable": False, "mock": True, "align_error_ms": None, "skip_reason": "no impact paired with this swing"}


def test_window_off_the_recording_gives_none(session) -> None:
    rec = session.rec
    slerp = Slerp(rec.t, body_rotations(rec, "body_to_world"))
    assert swing_metrics(rec, slerp, float(rec.t[0]) + 0.05, axis_vector("y")) is None
    assert swing_metrics(rec, slerp, float(rec.t[-1]) - 0.05, axis_vector("y")) is None
