"""Impact: peak g and ring-down, reported but not judged (MOCK data from wrist.synth)."""

from __future__ import annotations

import numpy as np
import pytest

from wrist.impact import G, RING_LIMIT_MS, clip_levels, impact_shape, noise_floor
from wrist.load import Recording

JUDGEMENTS = {"quality", "score", "z_peak", "z_width", "reasons", "baseline_n"}


def _rec(acc: np.ndarray, rate: float = 100.0) -> Recording:
    n = len(acc)
    return Recording(t=np.arange(n) / rate, acc=acc, gyro=np.zeros((n, 3)), quat=np.tile([0.0, 0, 0, 1], (n, 1)),
                     rate_hz=rate, orientation="quaternion", mock=True, source="test")


def test_impacts_are_reported_never_judged(fused) -> None:
    for sid, m in fused.metrics["swings"].items():
        im = m["impact"]
        assert im["label"] == "ESTIMATE" and im["estimate"] is True and im["judged"] is False
        assert not JUDGEMENTS & set(im), "no clean/mishit verdict, score or z-scores"
        assert im["resolution_ms"] == 10.0 and im["peak_g"] > 5
        assert fused.series["swings"][sid]["impact"]["ring_down_ms"] == im["ring_down_ms"]
        assert not JUDGEMENTS & set(fused.series["swings"][sid]["impact"])


def test_the_mishit_rings_down_far_longer(fused) -> None:
    rings = {sid: m["impact"]["ring_down_ms"] for sid, m in fused.metrics["swings"].items()}
    mishits = [sid for sid in rings if fused.truth["swings"][sid]["impact"] == "mishit"]
    assert len(mishits) == 1
    clean = [v for sid, v in rings.items() if sid not in mishits]
    assert rings[mishits[0]] > 2 * max(clean), "an off-centre hit keeps the arm shaking"
    assert max(clean) < 45, "a clean knock dies in a few samples"


def test_width_and_ring_down_of_a_known_spike() -> None:
    hp = np.zeros(200)
    hp[100:104] = 10.0  # 4 samples at full height: half-height crossings half a sample outside
    shape = impact_shape(_rec(np.zeros((200, 3))), hp, 1.0, np.full(3, np.inf))
    # Ring-down: last sample >= 1.0 (10% of 10) is 103; it crosses 0.9 of the way to the next sample.
    assert shape == {"peak_g": round(10 / G, 2), "width_ms": 40.0, "ring_down_ms": 39.0, "ring_down_capped": False,
                     "threshold_g": round(1.0 / G, 2), "clipped": False}


def test_a_ringing_spike_is_measured_through_its_zero_crossings() -> None:
    hp = np.zeros(200)
    hp[[100, 102, 104]] = [10.0, 8.0, 6.0]
    shape = impact_shape(_rec(np.zeros((200, 3))), hp, 1.01, np.full(3, np.inf))
    assert shape["width_ms"] == pytest.approx(40 + 5 + 10 / 6, abs=0.1)
    assert shape["ring_down_ms"] == pytest.approx(40 + 10 * 5 / 6, abs=0.1)


def test_ring_down_stops_at_the_noise_floor_and_ignores_a_later_blip() -> None:
    hp = np.full(400, 0.3)
    hp[100] = 4.0     # 10% of this (0.4) would be inside the noise, so the floor sets the threshold
    hp[115] = 1.5     # a lone blip 150 ms later, after a quiet stretch: not ringing
    shape = impact_shape(_rec(np.zeros((400, 3))), hp, 1.0, np.full(3, np.inf), floor=1.0)
    assert shape["threshold_g"] == round(1.0 / G, 2)
    assert shape["ring_down_ms"] == pytest.approx(10 * (4.0 - 1.0) / (4.0 - 0.3), abs=0.1)

    rng = np.random.default_rng(0)
    noisy = np.abs(rng.normal(0, 0.5, 400))
    assert 1.0 < noise_floor(noisy) < 1.5, "median + 3 robust SDs of the noise"

    ringing = np.zeros(400)
    ringing[100:] = 10.0 * np.exp(-np.arange(300) / 300)  # still at a third of its height 300 ms later
    capped = impact_shape(_rec(np.zeros((400, 3))), ringing, 1.0, np.full(3, np.inf))
    assert capped["ring_down_capped"] is True and capped["ring_down_ms"] == RING_LIMIT_MS


def test_a_saturated_accelerometer_is_reported() -> None:
    acc = np.random.default_rng(0).normal(0, 0.1, (200, 3))
    acc[100:104, 0] = 156.9  # a flat top at 16 g
    clip = clip_levels(_rec(acc))
    assert clip[0] == pytest.approx(156.9) and np.isinf(clip[1:]).all()
    hp = np.abs(acc[:, 0])
    assert impact_shape(_rec(acc), hp, 1.0, clip)["clipped"] is True
