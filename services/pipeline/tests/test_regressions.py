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


def test_exact_stereo_match_survives_missing_neighbours():
    b = {'t': np.arange(3.), 'img': np.ones((3, 33, 3)), 'vis': np.ones((3, 33))}
    b['img'][1] = np.nan; b['vis'][1] = 0
    img, vis = sample_b_at_a({'t': np.array([0., 2.])}, b, 1, 0)
    assert np.isfinite(img).all() and (vis == 1).all()


def test_x_factor_wraps_boundary():
    from pipeline.features import swing_features
    x = np.zeros((5, 33, 3))
    for j, angle in ((12, 179), (24, -179)):
        x[:, j, 0] = np.cos(np.radians(angle))
        x[:, j, 2] = np.sin(np.radians(angle))
    assert swing_features(x, 2, 30)['x_factor_max'] == pytest.approx(2)


def test_clean_only_fills_short_bounded_gaps():
    from pipeline.stereo import clean
    x = np.ones((20, 33, 3)); x[:3, 5] = np.nan; x[5:7, 5] = np.nan; x[10:17, 5] = np.nan
    y = clean(x, max_gap=2)
    assert np.isnan(y[:3, 5]).all()
    assert np.isfinite(y[5:7, 5]).all()
    assert np.isnan(y[10:17, 5]).all()


@pytest.mark.parametrize('start,end', [(100, None), (.001, .002)])
def test_empty_extraction_window(tmp_path, start, end):
    import cv2
    path = str(tmp_path / 'small.avi')
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 30, (32, 32))
    for _ in range(3):
        writer.write(np.zeros((32, 32, 3), np.uint8))
    writer.release()
    with pytest.raises(ValueError, match='contains no video frames'):
        extract_raw(path, start_s=start, end_s=end)
