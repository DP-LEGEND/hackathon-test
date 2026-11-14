"""Synthetic stereo fixtures; these are not real-player validation."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.__main__ import main
from pipeline.process import Options, classify_side, process_clips, swings_from_raw
from pipeline.stereo import _K, calibrate, triangulate


@pytest.fixture
def stereo_pair():
    n, fps = 240, 120
    times = np.arange(n) / fps
    rng = np.random.default_rng(17)
    world = np.broadcast_to(rng.uniform(-.25, .25, (33, 3)), (n, 33, 3)).copy()
    world[:, :, 2] += 4
    for j, point in {11: [-.2, -.5, 4], 12: [.2, -.5, 4], 23: [-.14, 0, 4],
                     24: [.14, 0, 4], 27: [-.15, .9, 4], 28: [.15, .9, 4],
                     14: [.3, -.3, 4.1], 16: [.35, -.1, 4]}.items():
        world[:, j] = point
    for i, ti in enumerate(times):
        rotation = cv2.Rodrigues(np.array([0., .15 * np.sin(4 * ti), 0.]))[0]
        world[i] = (world[i] - [0, 0, 4]) @ rotation.T + [0, .02 * np.sin(5 * ti), 4]
    # An articulated arm: the old independent wrist translation stretched the
    # forearm and was not suitable for metric speed or bone-length assertions.
    angle = np.full(n, -1.2)
    step = lambda at, width: (1 + np.tanh((times - at) / width)) / 2
    for contact in (.6, 1.5):
        angle += -.4 * step(contact - .24, .07) + 2.8 * step(contact, .025)
        if contact == .6:
            angle -= 2.4 * step(contact + .38, .20)
    world[:, 14] = world[:, 12] + .3 * np.c_[np.sin(angle + .3), np.cos(angle + .3), np.zeros(n)]
    world[:, 16] = world[:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(n)]
    world[:, :, 2] += (.6 * np.sin(3 * times))[:, None]  # avoid near-planar calibration degeneracy
    k = _K(900, (1280, 720))
    r = cv2.Rodrigues(np.array([0., .18, 0.]))[0]
    trans = np.array([-.8, .02, .05])

    def raw(xyz):
        image = xyz @ k.T
        image = np.concatenate([image[:, :, :2] / image[:, :, 2:], np.zeros((n, 33, 1))], axis=2)
        return {'img': image, 'vis': np.ones((n, 33)), 't': times.copy(),
                'fps': fps, 'size': (1280, 720), 'world': xyz.copy()}
    return raw(world), raw(world @ r.T + trans), world, r, trans


def test_triangulation_matches_known_geometry(stereo_pair):
    a, b, expected, r, trans = stereo_pair
    cal = {'Ka': _K(900, a['size']), 'Kb': _K(900, b['size']), 'R': r,
           't': trans[:, None], 'scale': 1, 'offset': 0}
    actual = triangulate(a, b, cal, 0, len(a['t']))
    np.testing.assert_allclose(actual, expected, atol=1e-9)


def test_stereo_pipeline_real_time_and_contract(stereo_pair):
    a, b, _, _, _ = stereo_pair
    a['t'] *= 4; a['fps'] /= 4
    swings, report = swings_from_raw(a, b, Options(slowdown_a=4, focal_a=900, focal_b=900))
    assert report['detected'] == report['written'] == 2
    assert report['calibration']['reprojectionErrorPx'] < .01
    for swing in swings:
        assert swing['fps'] == 120
        assert swing['fpsReal'] == 120 and swing['source'] == 'stereo'
        assert swing['side'] == 'forehand'
        assert swing['frames'][0]['t'] == 0
        assert 0 <= swing['contactFrame'] < len(swing['frames'])
        assert swing['metadata']['contactMethod'] == 'wrist-speed-peak-estimate'
        joints = np.array([f['joints'] for f in swing['frames']])
        assert joints.shape[1:] == (33, 3) and np.isfinite(joints).all()
        np.testing.assert_allclose((joints[:, 23] + joints[:, 24]) / 2, 0, atol=1e-6)
        np.testing.assert_allclose(np.diff([f['t'] for f in swing['frames']]), 1 / 120)
        json.dumps(swing, allow_nan=False)


def test_both_views_missing_key_joint_rejects_instead_of_inventing_pose(stereo_pair):
    a, b, *_ = stereo_pair
    a['img'][40:100, 13] = np.nan; a['vis'][40:100, 13] = 0
    b['vis'][40:100, 13] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['detected'] == 2
    assert report['written'] == 1 and len(report['rejected']) == 1
    assert 'missing key joints' in report['rejected'][0]['reason']
    assert len(swings) == 1


def test_no_overlap_has_actionable_calibration_error(stereo_pair):
    a, b, *_ = stereo_pair
    with pytest.raises(ValueError, match='shared visible joints'):
        calibrate(a, b, 1, 100, f_a=900, f_b=900)


def test_side_handedness_and_ambiguity():
    world = np.zeros((4, 33, 3)); world[:, 11, 0] = -.2; world[:, 12, 0] = .2
    world[:, 16, 0] = .4; world[:, 15, 0] = -.4
    assert classify_side(world, 3, 'R') == classify_side(world, 3, 'L') == 'forehand'
    world[:, 16, 0] = -.4
    assert classify_side(world, 3, 'R') == 'backhand'
    world[:, 16, 0] = 0
    assert classify_side(world, 3, 'R') == 'unknown'


def test_cli_writes_individual_json_and_preserves_output(tmp_path, monkeypatch, stereo_pair):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    clip_a = tmp_path / 'a.mov'; clip_b = tmp_path / 'b.mov'; model = tmp_path / 'pose.task'
    for path in (clip_a, clip_b, model):
        path.write_bytes(path.name.encode())  # placeholder inputs; extraction is injected below
    monkeypatch.setattr(process, 'extract_raw', lambda clip, **kw: a if Path(clip) == clip_a else b)
    out = tmp_path / 'out'
    arguments = [str(clip_a), str(clip_b), str(out), '--model-path', str(model),
                 '--focal-a', '900', '--focal-b', '900', '--side', 'backhand']
    assert main(arguments) == 0
    report = json.loads((out / 'manifest.json').read_text())
    assert len(report['files']) == 2 and report['status'] == 'complete'
    for name in report['files']:
        swing = json.loads((out / name).read_text())
        assert swing['side'] == 'backhand' and swing['id'] in name
    saved = {f.name: f.read_bytes() for f in out.iterdir()}
    assert main(arguments) == 1
    assert saved == {f.name: f.read_bytes() for f in out.iterdir()}


def test_cli_errors_are_concise(tmp_path, capsys):
    assert main(['missing.mov', 'missing2.mov', str(tmp_path / 'out')]) == 1
    assert 'Clip does not exist' in capsys.readouterr().err
    assert main(['a', 'b', str(tmp_path), '--slowdown-a', 'nan']) == 1
    assert 'must be finite and positive' in capsys.readouterr().err


@pytest.mark.parametrize('field,value', [('slowdown_a', 0), ('slowdown_b', -1), ('focal_a', float('inf')), ('max_gap_s', -1)])
def test_invalid_options(field, value):
    with pytest.raises(ValueError):
        Options(**{field: value}).validate()


def test_left_hand_controls_segmentation(stereo_pair):
    a, b, *_ = stereo_pair
    # Use the same known stereo trajectory as the left wrist instead.
    for raw in (a, b):
        for key in ('img', 'world', 'vis'):
            raw[key][:, [11, 13, 15, 12, 14, 16]] = raw[key][:, [12, 14, 16, 11, 13, 15]]
    swings, report = swings_from_raw(a, b, Options(hand='L', side='backhand', focal_a=900, focal_b=900))
    assert report['written'] == 2
    assert all(s['metadata']['hand'] == 'L' and s['side'] == 'backhand' for s in swings)


def test_cli_partial_output_is_explicit(tmp_path, monkeypatch, stereo_pair, capsys):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    a['img'][40:100, 13] = np.nan; a['vis'][40:100, 13] = 0
    b['vis'][40:100, 13] = 0
    paths = [tmp_path / name for name in ('a.mov', 'b.mov', 'pose.task')]
    for path in paths:
        path.write_bytes(path.name.encode())
    monkeypatch.setattr(process, 'extract_raw', lambda clip, **kw: a if Path(clip) == paths[0] else b)
    out = tmp_path / 'partial'
    assert main([str(paths[0]), str(paths[1]), str(out), '--model-path', str(paths[2]),
                 '--focal-a', '900', '--focal-b', '900']) == 2
    assert 'failed pose quality' in capsys.readouterr().err
    report = json.loads((out / 'manifest.json').read_text())
    assert report['status'] == 'partial' and report['written'] == 1


def test_missing_ipad_view_uses_mono_without_mislabeling_coordinates(stereo_pair):
    a, b, *_ = stereo_pair
    # A deliberately distinct monocular trajectory makes mislabelling stereo
    # coordinates as mono detectable, not just the source flag.
    a['world'][:, 16] = a['world'][:, 14] + 1.1 * (a['world'][:, 16] - a['world'][:, 14])
    options = Options(focal_a=900, focal_b=900)
    stereo, _ = swings_from_raw(a, b, options)
    absent = {**b, 'vis': np.zeros_like(b['vis'])}
    mono, _ = swings_from_raw(a, absent, options)
    b['vis'][:] = 0
    actual, report = swings_from_raw(a, b, options)
    assert report['detected'] == report['written'] == 2 and report['rejected'] == []
    assert all(s['source'] == 'stereo' for s in stereo)
    assert [s['source'] for s in actual] == ['mono', 'mono']
    assert not np.allclose([f['joints'][16] for f in actual[0]['frames']],
                           [f['joints'][16] for f in stereo[0]['frames']])
    for result, expected in zip(actual, mono):
        np.testing.assert_allclose([f['joints'] for f in result['frames']],
                                   [f['joints'] for f in expected['frames']], atol=1e-5)
        assert result['contactFrame'] == expected['contactFrame']
        assert result['fpsReal'] == result['fps'] == 120
        json.dumps(result, allow_nan=False)


def test_only_required_iphone_joints_are_enough_without_ipad(stereo_pair):
    from pipeline.process import CORE_JOINTS
    a, b, *_ = stereo_pair
    optional = [j for j in range(33) if j not in CORE_JOINTS]
    a['world'][:, optional] = np.nan
    a['img'][:, optional] = np.nan
    a['vis'][:, optional] = 0
    b['vis'][:] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == report['detected'] == 2
    assert report['calibration']['error']
    for swing in swings:
        assert swing['source'] == swing['metadata']['reconstruction'] == 'mono'
        assert set(swing['metadata']['approximatedJoints']) == set(optional)
        joints = np.array([f['joints'] for f in swing['frames']])
        assert joints.shape[1:] == (33, 3) and np.isfinite(joints).all()
        np.testing.assert_allclose(joints[:, 25], joints[:, 23])
        np.testing.assert_allclose((joints[:, 23] + joints[:, 24]) / 2, 0, atol=1e-6)


@pytest.mark.parametrize('joint', [11, 12, 13, 14, 15, 16, 23, 24])
def test_each_missing_key_joint_in_both_views_rejects(stereo_pair, monkeypatch, joint):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    # Keep segmentation fixed so a missing detection joint cannot hide the gate.
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kw: [
        {'start': 30, 'end': 110, 'peak': 70, 'speed': 10}])
    a['vis'][30:111, joint] = 0
    b['vis'][30:111, joint] = 0
    a['world'][30:111, joint] = np.nan
    a['img'][30:111, joint] = np.nan
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert swings == [] and report['written'] == 0 and len(report['rejected']) == 1
    assert 'missing key joints' in report['rejected'][0]['reason']


def test_no_usable_swings_is_failed_and_reruns_use_cached_pose(tmp_path, monkeypatch, stereo_pair, capsys):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    a['world'][:, 13] = np.nan  # segmentation sees both peaks, but core gate fails
    a['img'][:, 13] = np.nan
    paths = [tmp_path / name for name in ('a.mov', 'b.mov', 'pose.task')]
    for path in paths:
        path.write_bytes(path.name.encode())
    calls = []
    def extract(clip, **kw):
        calls.append(clip)
        return a if Path(clip) == paths[0] else b
    monkeypatch.setattr(process, 'extract_raw', extract)
    out = tmp_path / 'failed'
    args = [str(paths[0]), str(paths[1]), str(out), '--model-path', str(paths[2]),
            '--focal-a', '900', '--focal-b', '900']
    assert main(args) == 1
    assert 'No usable swings' in capsys.readouterr().err
    report = json.loads((out / 'manifest.json').read_text())
    assert report['status'] == 'failed' and report['written'] == 0 and report['files'] == []
    assert (out / 'raw_cache.npz').is_file() and len(calls) == 2
    assert main(args) == 1  # cached arrays, not a second expensive extraction
    assert len(calls) == 2
    assert main(args + ['--no-cache']) == 1
    assert len(calls) == 4


def test_fresh_output_reuses_cache_without_touching_successful_output(tmp_path, monkeypatch, stereo_pair):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    paths = [tmp_path / name for name in ('a.mov', 'b.mov', 'pose.task')]
    for path in paths:
        path.write_bytes(path.name.encode())
    calls = []
    def extract(clip, **kw):
        calls.append(clip)
        return a if Path(clip) == paths[0] else b
    monkeypatch.setattr(process, 'extract_raw', extract)
    out = tmp_path / 'run-01'
    options = Options(model_path=str(paths[2]), focal_a=900, focal_b=900)
    process_clips(str(paths[0]), str(paths[1]), str(out), options)
    saved = {p.name: p.read_bytes() for p in out.iterdir()}
    fresh = tmp_path / 'run-02'
    args = [str(paths[0]), str(paths[1]), str(fresh), '--cache-dir', str(out),
            '--model-path', str(paths[2]), '--focal-a', '900', '--focal-b', '900']
    assert main(args) == 0 and len(calls) == 2
    assert saved == {p.name: p.read_bytes() for p in out.iterdir()}
    assert len(list(fresh.glob('*-swing-*.json'))) == 2


def test_bounded_iphone_gap_can_be_repaired_but_missing_optional_joint_does_not_reject(stereo_pair):
    a, b, *_ = stereo_pair
    a['world'][60:65, 13] = np.nan  # short bounded coordinate gap, not low visibility
    a['img'][60:65, 13] = np.nan
    a['vis'][:, 5] = 0
    b['vis'][:, 5] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == report['detected'] == 2
    assert all(s['source'] == 'stereo' for s in swings)
    assert all(5 in s['metadata']['approximatedJoints'] for s in swings)


def test_degenerate_optional_ankles_do_not_reject_mono_swing(stereo_pair):
    a, b, *_ = stereo_pair
    shoulders = (a['world'][:, 11] + a['world'][:, 12]) / 2
    a['world'][:, 27] = shoulders
    a['world'][:, 28] = shoulders
    b['vis'][:] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == 2 and all(s['source'] == 'mono' for s in swings)


@pytest.mark.parametrize('error', [ValueError('no shared joints'), cv2.error('calibration failed')])
def test_calibration_errors_fall_back_to_mono(stereo_pair, monkeypatch, error):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(process, 'calibrate', fail)
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == 2 and report['calibration']['error'] == str(error)
    assert all(s['source'] == 'mono' and s['metadata']['fallbackReason'] == str(error) for s in swings)


def test_failed_stereo_normalisation_recovers_using_complete_mono_swing(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    options = Options(focal_a=900, focal_b=900)
    mono, _ = swings_from_raw(a, {**b, 'vis': np.zeros_like(b['vis'])}, options)
    original = process.normalise
    calls = []
    def fail_first(world, torso_m):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError('degenerate stereo pose')
        return original(world, torso_m)
    monkeypatch.setattr(process, 'normalise', fail_first)
    swings, report = swings_from_raw(a, b, options)
    assert report['written'] == 2 and [s['source'] for s in swings] == ['mono', 'stereo']
    assert 'degenerate stereo pose' in swings[0]['metadata']['fallbackReason']
    np.testing.assert_allclose([f['joints'] for f in swings[0]['frames']],
                               [f['joints'] for f in mono[0]['frames']])


@pytest.mark.parametrize('visibility', [.5, .75, 1.])
def test_mono_joints_above_minimum_visibility_report_confidence(stereo_pair, visibility):
    from pipeline.process import CORE_JOINTS
    a, b, *_ = stereo_pair
    a['vis'][:, CORE_JOINTS] = visibility
    b['vis'][:] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['detected'] == report['written'] == 2 and report['rejected'] == []
    for swing in swings:
        assert swing['source'] == 'mono'
        assert swing['metadata']['coreVisibility'] == pytest.approx(visibility)
        assert swing['metadata']['lowConfidence'] == (visibility < .3)


def test_permanently_hidden_joint_without_learned_bone_cannot_be_recovered(stereo_pair):
    a, b, *_ = stereo_pair
    a['vis'][:, 13] = .2  # no jointly observed frames to learn this bone's length
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == 0 and swings == []


@pytest.mark.parametrize('visibility', [0., .1, .499, float('nan')])
def test_missing_or_below_minimum_visibility_rejects_mono(stereo_pair, visibility):
    a, b, *_ = stereo_pair
    a['vis'][:] = visibility
    b['vis'][:] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['detected'] == report['written'] == 0 and swings == []


@pytest.mark.parametrize('slowdown', [1, 4])
@pytest.mark.parametrize('missing_frames,written', [(6, 2), (7, 1), (10, 1)])
def test_six_frame_gap_limit_uses_real_fps(stereo_pair, slowdown, missing_frames, written):
    a, b, *_ = stereo_pair
    a['t'] *= slowdown
    a['fps'] /= slowdown
    a['world'][68:68 + missing_frames, 13] = np.nan
    a['img'][68:68 + missing_frames, 13] = np.nan
    b['vis'][:] = 0
    options = Options(slowdown_a=slowdown, focal_a=900, focal_b=900)
    swings, report = swings_from_raw(a, b, options)
    assert options.max_gap_s == .25 and options.min_speed == 8
    assert report['detected'] == 2 and len(swings) == report['written'] == written
    if missing_frames == 6:
        _, strict = swings_from_raw(a, b, Options(slowdown_a=slowdown, max_gap_s=.02,
                                                 focal_a=900, focal_b=900))
        assert strict['written'] == 1
