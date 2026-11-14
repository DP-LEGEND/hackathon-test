"""Swing tempo from the gyro (MOCK data from wrist.synth, plus hand-made speed profiles)."""

from __future__ import annotations

import numpy as np
import pytest

from wrist.load import Recording
from wrist.tempo import SERIES_MS, SERIES_STEP_MS, tempo


def _rec_from_speed(speed_dps: np.ndarray, rate: float = 100.0) -> Recording:
    n = len(speed_dps)
    gyro = np.zeros((n, 3))
    gyro[:, 2] = np.radians(speed_dps)
    return Recording(t=np.arange(n) / rate, acc=np.zeros((n, 3)), gyro=gyro, quat=np.tile([0.0, 0, 0, 1], (n, 1)),
                     rate_hz=rate, orientation="quaternion", mock=True, source="test")


def _crossings_ms(speed: np.ndarray, t: np.ndarray, rest: float) -> tuple[np.ndarray, np.ndarray]:
    above = speed > rest
    return t[1:][~above[:-1] & above[1:]] * 1000, t[1:][above[:-1] & ~above[1:]] * 1000


def test_tempo_matches_the_noise_free_swing(session) -> None:
    motion = session.truth["motion"]
    for sid, m in session.metrics["swings"].items():
        tp = m["tempo"]
        assert tp["label"] == "ESTIMATE" and tp["reasons"] == [] and tp["contact_ms"] == 0
        rel = np.arange(-1.5, 1.0, 0.0005)
        speed = np.degrees(np.linalg.norm(motion.gyro(m["impact_s"] + rel), axis=1))
        ups, downs = _crossings_ms(speed, rel, tp["rest_dps"])
        assert tp["backswing_start_ms"] == pytest.approx(ups[ups < 0][0], abs=25)
        assert tp["forward_start_ms"] == pytest.approx(ups[ups < 0][-1], abs=25), "end of the pause at the top"
        assert tp["follow_through_end_ms"] == pytest.approx(downs[downs > 0][0], abs=25)
        assert tp["backswing_ms"] == tp["forward_start_ms"] - tp["backswing_start_ms"]
        assert tp["forward_swing_ms"] == -tp["forward_start_ms"] and tp["follow_through_ms"] == tp["follow_through_end_ms"]
        assert tp["tempo_ratio"] == pytest.approx(tp["backswing_ms"] / tp["forward_swing_ms"], abs=0.01)
        assert tp["tempo_ratio"] > 1
        assert tp["backswing_to_contact_ms"] == -tp["backswing_start_ms"] > 0


def test_a_looped_swing_turns_around_at_the_dip() -> None:
    t = np.arange(0, 6, 0.01)
    speed = 400 * np.exp(-((t - 2.65) / 0.15) ** 2) + 1500 * np.exp(-((t - 3.0) / 0.1) ** 2)
    tp = tempo(_rec_from_speed(speed), 3.0)
    rest = tp["rest_dps"]
    assert rest == 75
    dip = 2.6 + 0.01 * np.argmin(speed[(t >= 2.6) & (t < 2.95)])
    assert speed.min() < rest < speed[(t > 2.6) & (t < 2.95)].min(), "one continuous movement"
    assert tp["backswing_start_ms"] == pytest.approx((2.65 - 0.15 * np.sqrt(np.log(400 / 75)) - 3) * 1000, abs=15)
    assert tp["forward_start_ms"] == pytest.approx((dip - 3) * 1000, abs=20)
    assert tp["follow_through_end_ms"] == pytest.approx(100 * np.sqrt(np.log(1500 / 75)), abs=15)


def test_no_turn_around_leaves_the_top_unknown() -> None:
    t = np.arange(0, 6, 0.01)
    speed = 1500 * np.exp(-((t - 3.0) / 0.1) ** 2)  # the forearm only moves forward
    tp = tempo(_rec_from_speed(speed), 3.0)
    assert tp["backswing_start_ms"] is not None and tp["forward_start_ms"] is None and tp["backswing_ms"] is None
    assert tp["backswing_to_contact_ms"] == -tp["backswing_start_ms"], "needs only the backswing start"
    assert "turn-around" in tp["reasons"][0]


def test_an_arm_that_never_settles_gives_no_backswing_start() -> None:
    t = np.arange(0, 6, 0.01)
    speed = 300 + 1500 * np.exp(-((t - 3.0) / 0.1) ** 2)  # fidgeting at 300 deg/s throughout
    tp = tempo(_rec_from_speed(speed), 3.0)
    assert tp["backswing_start_ms"] is None and tp["follow_through_end_ms"] is None
    assert tp["backswing_to_contact_ms"] is None
    assert any("never settled" in r for r in tp["reasons"]) and any("still moving" in r for r in tp["reasons"])


def test_angular_speed_series_for_the_graph(session) -> None:
    grid = session.series["angular_speed_t_ms"]
    assert grid[0] == SERIES_MS[0] and grid[-1] == SERIES_MS[1] and grid[1] - grid[0] == SERIES_STEP_MS
    for sid, ser in session.series["swings"].items():
        speed = ser["angular_speed_dps"]
        assert len(speed) == len(grid) and all(isinstance(v, int) for v in speed)
        assert abs(grid[int(np.argmax(speed))]) <= 40, "fastest at contact"
        assert ser["tempo"]["label"] == "ESTIMATE"
        assert ser["tempo"]["backswing_start_ms"] == session.metrics["swings"][sid]["tempo"]["backswing_start_ms"]
