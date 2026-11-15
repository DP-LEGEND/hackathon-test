"""Integrated-gyro orientation, the fallback when the phone's own is missing or bad."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation, Slerp

from wrist.load import Recording
from wrist.metrics import body_rotations, choose_orientation, gyro_convention
from wrist.orient import integrate_gyro, orientation_bias, still_bias
from wrist.tests.conftest import Session


def _rec(gyro: np.ndarray, rate: float = 100.0, quat: np.ndarray | None = None) -> Recording:
    n = len(gyro)
    return Recording(t=np.arange(n) / rate, acc=np.zeros((n, 3)), gyro=gyro, quat=quat, rate_hz=rate,
                     orientation="none" if quat is None else "quaternion", mock=True, source="test")


def test_bias_is_the_still_gyro_around_the_taps() -> None:
    rng = np.random.default_rng(0)
    bias = np.radians([0.5, -1.0, 1.5])
    gyro = bias + rng.normal(0, 0.01, (1000, 3))
    gyro[300:302] += 5.0                      # the taps jolt the phone...
    gyro[345:347] += 5.0
    gyro[600:] += np.radians([0, 0, 300.0])   # ...and later the arm swings
    est, info = still_bias(_rec(gyro), [3.0, 3.45])
    assert np.degrees(est) == pytest.approx(np.degrees(bias), abs=0.1)
    assert info["bias_from"] == "around the sync taps" and info["warning"] is None
    assert info["drift_if_uncorrected_deg_per_min"] == pytest.approx(np.degrees(np.linalg.norm(est)) * 60, abs=0.1)
    assert info["bias_dps"] == pytest.approx(np.degrees(est).tolist(), abs=1e-3)


def test_without_taps_the_start_is_used_and_without_stillness_nothing_is_removed() -> None:
    gyro = np.tile(np.radians([0.0, 0.0, 1.0]), (1000, 1))
    est, info = still_bias(_rec(gyro), None)
    assert np.degrees(est[2]) == pytest.approx(1.0) and "no sync taps" in info["bias_from"]
    moving = np.tile(np.radians([0.0, 0.0, 90.0]), (1000, 1))
    est, info = still_bias(_rec(moving), [3.0, 3.45])
    assert not est.any() and "isn't removed" in info["warning"]


def test_integration_matches_exact_rotations() -> None:
    t = np.arange(0, 2, 0.01)
    w = np.column_stack([np.zeros_like(t), np.zeros_like(t), np.full_like(t, np.radians(90))])
    R = integrate_gyro(_rec(w), np.zeros(3))
    assert np.degrees(R[-1].magnitude()) == pytest.approx(90 * t[-1], abs=1e-6)
    # Two axes at once, the body-frame rate of R(t) = Rz(a t) Ry(b t): exact for any step size.
    a, b = np.radians(400), np.radians(150)
    body = Rotation.from_rotvec(np.outer(t, [0, b, 0])).inv().apply(np.outer(np.ones_like(t), [0, 0, a])) + [0, b, 0]
    R = integrate_gyro(_rec(body), np.zeros(3))
    truth = Rotation.from_rotvec(np.outer(t, [0, 0, a])) * Rotation.from_rotvec(np.outer(t, [0, b, 0]))
    assert np.degrees((truth.inv() * R).magnitude()).max() < 0.5


def test_integrated_gyro_tracks_the_phone_orientation_over_a_swing(session) -> None:
    rec = session.rec
    phone = Slerp(rec.t, body_rotations(rec, gyro_convention(rec)["convention"]))
    gyro = Slerp(rec.t, integrate_gyro(rec, np.zeros(3)))
    for tr in session.truth["swings"].values():
        c = tr["impact_s"]
        p, g = phone([c - 0.15, c + 0.1]), gyro([c - 0.15, c + 0.1])
        assert np.degrees(((p[0].inv() * p[1]).inv() * (g[0].inv() * g[1])).magnitude()) < 1.0


def test_choose_orientation_prefers_the_phone(session) -> None:
    _, used, bias = choose_orientation(session.rec, session.sync["taps_s"])
    assert used["source"] == "phone" and used["convention"] == "body_to_world"
    assert used["gyro_bias"]["bias_from"].startswith("the phone's own orientation")
    assert np.degrees(np.abs(bias)).max() < 0.1, "the mock gyro has no offset against its orientation"


def test_the_phone_path_takes_a_constant_gyro_offset_off_the_roll(session, tmp_path) -> None:
    """Codex P2 on #74: the roll is the gyro integral on every path, so a gyro offset must come off
    even when the phone's own orientation is kept. A still window would read slow movement as
    bias; the phone's orientation can't."""
    offset = Session(tmp_path / "offset", gyro_bias_dps=[0.0, 5.0, 0.0])   # 5 deg/s about the forearm
    assert gyro_convention(offset.rec)["ok"], "the phone path is still chosen"
    used = offset.metrics["sensor"]["orientation_used"]
    assert used["source"] == "phone"
    assert used["gyro_bias"]["bias_dps"] == pytest.approx([0.0, 5.0, 0.0], abs=0.1)
    for sid, m in offset.metrics["swings"].items():   # uncorrected, 5 deg/s x 0.25 s = 1.25 deg on every swing
        assert m["roll_change_deg"] == pytest.approx(session.metrics["swings"][sid]["roll_change_deg"], abs=0.15)


def test_orientation_bias_ignores_slow_movement() -> None:
    """Slow, steady turning (under still_bias's 20 deg/s) isn't bias: the orientation turns with it."""
    rate, n = 100.0, 1000
    gyro = np.zeros((n, 3))
    gyro[:, 1] = np.radians(10.0)                                    # turning at 10 deg/s, no offset
    rots = Rotation.from_rotvec(np.outer(np.arange(n) / rate, gyro[0]))
    rec = _rec(gyro, rate, quat=rots.as_quat())
    bias, info = orientation_bias(rec, rots)
    assert np.degrees(np.abs(bias)).max() < 1e-6 and info["warning"] is None
    still, _ = still_bias(rec, None)
    assert np.degrees(still[1]) == pytest.approx(10.0, abs=0.01), "the still window would call it bias"
