import numpy as np

from pipeline.features import _angle, swing_features
from pipeline.pose import smooth


def test_angle_right_angle():
    a, b, c = np.array([[1.0, 0, 0]]), np.zeros((1, 3)), np.array([[0, 1.0, 0]])
    assert abs(_angle(a, b, c)[0] - 90) < 1e-6


def test_smoothing_leaves_gaps_for_articulated_repair():
    x = np.array([1.0, np.nan, 3.0, 3.0, 3.0])
    y = smooth(x, 3)
    np.testing.assert_allclose(y, x, equal_nan=True)


def test_swing_features_runs_on_synthetic_pose():
    rng = np.random.default_rng(0)
    world = rng.normal(0, 0.3, (96, 33, 3))
    f = swing_features(world, impact=54, fps_real=120)
    assert 0 <= f["elbow_at_impact"] <= 180
    assert f["shoulder_turn_range"] >= 0
