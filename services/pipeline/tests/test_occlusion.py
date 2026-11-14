"""Articulated synthetic motion: these are not labelled real-player clips."""
import copy
import json

import numpy as np
import pytest

from pipeline.kinematics import gap_limit
from pipeline.pose import smooth, to_swing
from pipeline.process import Options, swings_from_raw
from pipeline.stereo import _K, clean, sample_b_at_a, triangulate
from pipeline.tests.test_stereo_cli import stereo_pair


def calibration(a, b, rotation, translation):
    return {'Ka': _K(900, a['size']), 'Kb': _K(900, b['size']), 'R': rotation,
            't': translation[:, None], 'scale': 1, 'offset': 0}


@pytest.mark.parametrize('camera', [0, 1])
@pytest.mark.parametrize('start', [60, 68, 72])
def test_ten_hidden_frames_use_other_camera_with_stable_bones(stereo_pair, camera, start):
    a, b, truth, rotation, translation = stereo_pair
    hidden = (a, b)[camera]
    hidden['vis'][start:start + 10, 16] = .1
    hidden['img'][start:start + 10, 16, :2] += 700  # finite but confidently wrong pixels
    points, filled, visibility = triangulate(a, b, calibration(a, b, rotation, translation),
                                             0, len(truth), provenance=True)
    window = slice(start, start + 10)
    length = np.linalg.norm(points[window, 16] - points[window, 14], axis=1)
    assert np.max(abs(length / .32 - 1)) < .02
    assert np.max(np.linalg.norm(points[window, 16] - truth[window, 16], axis=1)) < .10
    assert filled[window, 16].all() and not filled[:start, 16].any()
    assert (visibility[window, 16] == 1).all()


def test_visibility_weights_reduce_confident_view_reprojection_error(stereo_pair):
    a, b, _, rotation, translation = stereo_pair
    b['img'][:, 16, 1] += 4
    cal = calibration(a, b, rotation, translation)
    equal = triangulate(a, b, cal, 0, len(a['t']))
    b['vis'][:, 16] = .5
    weighted = triangulate(a, b, cal, 0, len(a['t']))
    def residual(points):
        pixels = points[:, 16] @ cal['Ka'].T
        return np.linalg.norm(pixels[:, :2] / pixels[:, 2:] - a['img'][:, 16, :2], axis=1)
    assert np.median(residual(weighted)) < np.median(residual(equal)) * .8


@pytest.mark.parametrize('camera', [0, 1])
def test_hidden_root_hip_uses_confident_view_and_adjacent_anchor(stereo_pair, camera):
    a, b, truth, rotation, translation = stereo_pair
    (a, b)[camera]['vis'][68:78, 23] = .1
    (a, b)[camera]['img'][68:78, 23, :2] += 700
    points, filled, _ = triangulate(a, b, calibration(a, b, rotation, translation),
                                    0, len(truth), provenance=True)
    assert filled[68:78, 23].all()
    lengths = np.linalg.norm(points[68:78, 23] - points[68:78, 24], axis=1)
    assert np.max(abs(lengths / .28 - 1)) < .02
    assert np.max(np.linalg.norm(points[68:78, 23] - truth[68:78, 23], axis=1)) < .10
    swings, report = swings_from_raw(a, b, Options(hand='R', focal_a=900, focal_b=900))
    assert report['written'] == 2 and swings[0]['source'] == 'stereo'
    for raw in (a, b):
        raw['vis'][68:78, 23] = .1
    points = triangulate(a, b, calibration(a, b, rotation, translation), 0, len(truth))
    assert np.isnan(clean(points)[68:78, 23]).all()


@pytest.mark.parametrize('fps,limit', [(30, 3), (120, 6)])
def test_short_gaps_interpolate_angles_and_long_gaps_stay_hidden(stereo_pair, fps, limit):
    world = np.repeat(stereo_pair[2][:1], 40, axis=0)
    angle = np.linspace(-.8, .8, len(world))
    world[:, 16] = world[:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(len(world))]
    assert gap_limit(fps) == limit
    for count in (limit, limit + 1, 10):
        hidden = world.copy()
        hidden[15:15 + count, 16] = np.nan
        result = clean(hidden, max_gap=gap_limit(fps), win=5)
        if count > limit:
            assert np.isnan(result[15:15 + count, 16]).all()
        else:
            lengths = np.linalg.norm(result[:, 16] - result[:, 14], axis=1)
            assert np.max(abs(lengths / .32 - 1)) < .02
            assert np.max(np.linalg.norm(result[15:15 + count, 16] - world[15:15 + count, 16], axis=1)) < .10


def test_smoothing_does_not_mix_opposite_sides_of_hidden_gap():
    track = np.r_[np.zeros(10), np.full(10, np.nan), np.full(10, 100.)]
    result = smooth(track, win=25)
    np.testing.assert_array_equal(result[:10], 0)
    assert np.isnan(result[10:20]).all()
    np.testing.assert_array_equal(result[20:], 100)


def test_both_cameras_hidden_ten_frames_are_not_fabricated(stereo_pair):
    a, b, truth, rotation, translation = stereo_pair
    for raw in (a, b):
        raw['vis'][68:78, 16] = .1
    points = triangulate(a, b, calibration(a, b, rotation, translation), 0, len(truth))
    assert np.isnan(clean(points, max_gap=6)[68:78, 16]).all()
    swings, _ = swings_from_raw(a, b, Options(hand='R', focal_a=900, focal_b=900))
    assert len(swings) == 1
    assert swings[0]['metadata']['sourceContactSeconds'] > 1


def test_missing_camera_frames_cannot_bypass_hidden_gap_limit(stereo_pair):
    a, b, truth, rotation, translation = stereo_pair
    a['vis'][68:78, 16] = .1
    keep = np.r_[np.arange(68), np.arange(78, len(b['t']))]
    b = {**b, **{key: b[key][keep] for key in ('t', 'img', 'world', 'vis')}}
    image, visibility = sample_b_at_a(a, b, 1, 0)
    assert np.isnan(image[68:78]).all() and (visibility[68:78] == 0).all()
    assert np.isfinite(image[[67, 78]]).all() and (visibility[[67, 78]] == 1).all()
    points = triangulate(a, b, calibration(a, b, rotation, translation), 0, len(truth))
    assert np.isnan(clean(points)[68:78, 16]).all()
    swings, report = swings_from_raw(a, b, Options(hand='R', focal_a=900, focal_b=900))
    assert report['written'] == 1 and swings[0]['metadata']['sourceContactSeconds'] > 1


def test_resampling_adjacent_lower_fps_frames_preserves_evidence(stereo_pair):
    a, b, *_ = stereo_pair
    b = {**b, **{key: b[key][::4] for key in ('t', 'img', 'world', 'vis')}, 'fps': 30}
    image, visibility = sample_b_at_a(a, b, 1, 0)
    assert np.isfinite(image[:237]).all() and (visibility[:237] == 1).all()
    # A real-time section can have longer intervals than the encoded frame rate:
    # pass adjacency computed before mapping, including across its boundary.
    from pipeline.timing import Timeline
    clock = Timeline(4, realtime_after=1)
    b['frame_contiguous'] = np.diff(b['t']) <= 1.5 / b['fps']
    b['t'] = clock.real(b['t'])
    image, visibility = sample_b_at_a({**a, 't': clock.real(a['t'])}, b, 1, 0)
    assert np.isfinite(image[:237]).all() and (visibility[:237] == 1).all()


def test_pipeline_recovers_hidden_wrist_and_reports_filled_arm_frames(stereo_pair):
    a, b, *_ = stereo_pair
    a['vis'][68:78, 16] = .1
    a['img'][68:78, 16, :2] += 700
    a['world'][68:78, 16] = 1000  # not a permissible monocular fallback
    swings, report = swings_from_raw(a, b, Options(hand='R', focal_a=900, focal_b=900))
    assert report['written'] == 2
    swing = swings[0]
    assert swing['source'] == 'stereo'
    frames = swing['frames']
    flags = np.array([frame['filled'] for frame in frames])
    visibility = np.array([frame['visibility'] for frame in frames])
    assert flags[:, 16].sum() == 10
    assert flags.shape == visibility.shape == (len(frames), 33)
    assert swing['metadata']['hittingArmFilledPercent'] == pytest.approx(1000 / len(frames))
    assert swing['metadata']['peakWristSpeedMs'] > 12 and swing['metadata']['backswingVerified']
    assert frames[swing['contactFrame']]['t'] == pytest.approx(.6, abs=1 / swing['fpsReal'])
    json.dumps(swing, allow_nan=False)


@pytest.mark.parametrize('kind', ['walk', 'catch', 'slow_swing'])
def test_non_swings_never_publish_even_with_sound(stereo_pair, kind):
    a, b, world, rotation, translation = stereo_pair
    t = a['t']
    if kind == 'walk':
        angle = -.7 + .15 * np.sin(2 * np.pi * 1.5 * t)
    elif kind == 'catch':
        angle = -1.2 + 2.8 * (1 + np.tanh((t - .6) / .025)) / 2  # fast, no backswing
    else:
        # Retain the backswing but stretch all timestamps to drop below 12 m/s.
        a['t'] = b['t'] = t * 4
        a['fps'] = b['fps'] = a['fps'] / 4
        angle = None
    if angle is not None:
        world[:, 14] = world[:, 12] + .3 * np.c_[np.sin(angle + .3), np.cos(angle + .3), np.zeros(len(t))]
        world[:, 16] = world[:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(len(t))]
        world[:, :, 0] += (2 * t)[:, None]
        for raw, xyz in ((a, world), (b, world @ rotation.T + translation)):
            raw['world'] = xyz.copy()
            projection = xyz @ _K(900, raw['size']).T
            raw['img'][:, :, :2] = projection[:, :, :2] / projection[:, :, 2:]
    a['audio_hits'] = np.array([.6, 1.5])
    swings, report = swings_from_raw(a, b, Options(hand='R', min_speed=1, focal_a=900, focal_b=900))
    assert swings == [] and report['written'] == 0


def test_serializer_visibility_is_optional_input_but_validated(stereo_pair):
    raw = copy.deepcopy(stereo_pair[0])
    raw['vis'][10:13, 16] = .2
    raw['filled'] = np.zeros_like(raw['vis'], dtype=bool)
    raw['filled'][10:13, 16] = True
    swing = to_swing(raw, f0=10, f1=20, contact_frame=3, smooth_win=1)
    assert swing['frames'][0]['visibility'][16] == .2 and swing['frames'][0]['filled'][16]
    for invalid in (np.ones((240, 32)), np.full((240, 33), np.nan), np.full((240, 33), 2.)):
        raw['vis'] = invalid
        with pytest.raises(ValueError, match='confidence'):
            to_swing(raw)


def test_parent_gap_flags_interpolated_descendants_and_preserves_confidence(stereo_pair):
    raw = stereo_pair[0]
    raw['vis'][60:63, 13] = .1
    raw['world'][60:63, 13] = 500  # finite low-confidence predictions are hidden
    swing = to_swing(raw, contact_frame=72)
    for frame in swing['frames'][60:63]:
        assert frame['filled'][13] and frame['filled'][15]
        assert frame['visibility'][13] == .1 and frame['visibility'][15] == 1
    assert not swing['frames'][59]['filled'][15]


@pytest.mark.parametrize('stereo', [False, True])
def test_short_hidden_wrist_gap_at_contact_survives_detection(stereo_pair, stereo):
    a, b, *_ = stereo_pair
    for raw in (a, b):
        raw['vis'][69:75, 16] = .1
        raw['img'][69:75, 16, :2] = 2000
        raw['world'][69:75, 16] = 500
    a['audio_hits'] = np.array([.6])
    swings, report = swings_from_raw(a, b if stereo else None, Options(hand='R', focal_a=900, focal_b=900))
    assert report['written'] == 2
    swing = swings[0]
    assert swing['metadata']['sourceContactSeconds'] == pytest.approx(.6)
    frame = swing['frames'][swing['contactFrame']]
    assert frame['filled'][16] and frame['visibility'][16] == .1


def test_rejected_stronger_candidate_does_not_suppress_valid_swing(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, _, *_ = stereo_pair
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 0, 'end': 114, 'peak': 72, 'speed': 50},
        {'start': 28, 'end': 142, 'peak': 100, 'speed': 100},
    ])
    swings, report = swings_from_raw(a, options=Options(hand='R'))
    assert report['written'] == 1
    assert swings[0]['metadata']['sourceContactSeconds'] == pytest.approx(.6)
    assert len(report['rejected']) == 1 and 'Not a swing' in report['rejected'][0]['reason']
