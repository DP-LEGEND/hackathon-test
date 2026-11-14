import numpy as np
import pytest
from pipeline.pose import smooth, to_swing, extract_raw
from pipeline.features import _yaw
from pipeline.stereo import sample_b_at_a, normalise


def test_short_smoothing_preserves_frame_count():
    assert smooth(np.ones((2, 33, 3)), 15).shape == (2, 33, 3)
    assert smooth(np.empty((0, 3))).shape == (0, 3)


def test_swing_contract_and_missing_pose():
    raw = {'t': np.arange(3) / 30, 'fps': 30, 'world': np.ones((3, 33, 3))}
    swing = to_swing(raw, contact_frame=1)
    assert swing['id'] and swing['contactFrame'] == 1
    assert len(swing['frames']) == 3
    raw['world'][:] = np.nan
    with pytest.raises(ValueError, match='missing joints'):
        to_swing(raw)


def test_invalid_video():
    with pytest.raises(ValueError, match='Cannot read video'):
        extract_raw('/missing/clip.mov')


def test_cropped_stereo_alignment_includes_last_frame():
    b = {'t': np.array([10., 11., 12.]), 'img': np.arange(3.)[:, None, None] * np.ones((3, 33, 3)), 'vis': np.ones((3, 33))}
    img, vis = sample_b_at_a({'t': np.array([10., 10.5, 12., 13.])}, b, 1, 0)
    np.testing.assert_allclose(img[:3, 0, 0], [0, .5, 2])
    assert vis[-1].sum() == 0


def test_yaw_recovers_after_missing_pose():
    a = np.zeros((4, 3)); b = np.ones((4, 3)); b[1] = np.nan
    assert np.isfinite(_yaw(a, b)[2:]).all()


def test_normalise_centres_each_frame():
    x = np.zeros((3, 33, 3)); x[:, 11:13, 1] = .5; x[:, 27:29, 1] = -1
    x += np.arange(3.)[:, None, None]
    y = normalise(x)
    np.testing.assert_allclose((y[:, 23] + y[:, 24]) / 2, 0, atol=1e-12)
