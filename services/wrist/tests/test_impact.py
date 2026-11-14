"""Impact quality: clean vs mishit, relative to the session (MOCK data from wrist.synth)."""

from __future__ import annotations

import numpy as np
import pytest

from wrist.impact import G, MISHIT_Z, clip_levels, impact_shape, judge
from wrist.load import Recording


def _rec(acc: np.ndarray, rate: float = 100.0) -> Recording:
    n = len(acc)
    return Recording(t=np.arange(n) / rate, acc=acc, gyro=np.zeros((n, 3)), quat=np.tile([0.0, 0, 0, 1], (n, 1)),
                     rate_hz=rate, orientation="quaternion", mock=True, source="test")


def test_the_mishit_is_flagged_by_its_longer_spike(fused) -> None:
    for sid, m in fused.metrics["swings"].items():
        im = m["impact"]
        assert im["label"] == "ESTIMATE" and im["estimate"] is True and im["baseline_n"] == 9
        assert fused.series["swings"][sid]["impact"]["quality"] == im["quality"]
        if fused.truth["swings"][sid]["impact"] == "mishit":
            assert im["quality"] == "mishit" and im["z_width"] > MISHIT_Z and im["score"] < 50
            assert any("wide" in r for r in im["reasons"])
        else:
            assert im["quality"] == "clean" and im["score"] > 50 and im["reasons"] == []


def test_a_session_of_clean_hits_is_all_clean(session) -> None:
    assert {m["impact"]["quality"] for m in session.metrics["swings"].values()} == {"clean"}


def test_width_of_a_known_spike() -> None:
    hp = np.zeros(200)
    hp[100:104] = 10.0  # 4 samples at full height: half-height crossings half a sample outside
    shape = impact_shape(_rec(np.zeros((200, 3))), hp, 1.0, np.full(3, np.inf))
    assert shape == {"peak_g": round(10 / G, 2), "width_ms": 40.0, "clipped": False}


def test_a_ringing_spike_is_measured_through_its_zero_crossings() -> None:
    hp = np.zeros(200)
    hp[[100, 102, 104]] = [10.0, 8.0, 6.0]
    shape = impact_shape(_rec(np.zeros((200, 3))), hp, 1.01, np.full(3, np.inf))
    assert shape["width_ms"] == pytest.approx(40 + 5 + 10 / 6, abs=0.1)


def test_a_saturated_accelerometer_is_reported() -> None:
    acc = np.random.default_rng(0).normal(0, 0.1, (200, 3))
    acc[100:104, 0] = 156.9  # a flat top at 16 g
    clip = clip_levels(_rec(acc))
    assert clip[0] == pytest.approx(156.9) and np.isinf(clip[1:]).all()
    hp = np.abs(acc[:, 0])
    assert impact_shape(_rec(acc), hp, 1.0, clip)["clipped"] is True
    shapes = {f"s{k}": {"peak_g": 10.0 + k / 10, "width_ms": 12.0, "clipped": False} for k in range(5)}
    shapes["hit"] = {"peak_g": 16.0, "width_ms": 12.0, "clipped": True}
    assert any("limit" in r for r in judge(shapes, 100.0)["hit"]["reasons"])


def test_judging_needs_enough_other_impacts() -> None:
    shapes = {f"s{k}": {"peak_g": 10.0, "width_ms": 12.0, "clipped": False} for k in range(4)}
    out = judge(shapes, 100.0)
    assert all(v["quality"] is None and v["score"] is None and "needs 4" in v["reasons"][0] for v in out.values())


def test_an_impact_far_weaker_than_usual_is_a_mishit_too() -> None:
    shapes = {f"s{k}": {"peak_g": 10.0 + 0.3 * np.sin(k), "width_ms": 12.0, "clipped": False} for k in range(6)}
    shapes["shank"] = {"peak_g": 3.0, "width_ms": 12.0, "clipped": False}
    out = judge(shapes, 100.0)
    assert out["shank"]["quality"] == "mishit" and "far below" in out["shank"]["reasons"][0]
    assert out["shank"]["score"] == 0 and out["s1"]["quality"] == "clean"
