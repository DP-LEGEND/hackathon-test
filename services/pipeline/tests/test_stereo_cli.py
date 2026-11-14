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
    for contact in (.6, 1.5):
        world[:, 16, 0] += .6 * (1 + np.tanh((times - contact) / .035)) / 2
    for i, ti in enumerate(times):
        rotation = cv2.Rodrigues(np.array([0., .15 * np.sin(4 * ti), 0.]))[0]
        world[i] = (world[i] - [0, 0, 4]) @ rotation.T + [0, .02 * np.sin(5 * ti), 4]
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
        assert swing['side'] == 'forehand'
        assert swing['frames'][0]['t'] == 0
        assert 0 <= swing['contactFrame'] < len(swing['frames'])
        assert swing['metadata']['contactMethod'] == 'wrist-speed-peak-estimate'
        joints = np.array([f['joints'] for f in swing['frames']])
        assert joints.shape[1:] == (33, 3) and np.isfinite(joints).all()
        np.testing.assert_allclose((joints[:, 23] + joints[:, 24]) / 2, 0, atol=1e-6)
        np.testing.assert_allclose(np.diff([f['t'] for f in swing['frames']]), 1 / 120)
        json.dumps(swing, allow_nan=False)


def test_missing_joint_rejects_instead_of_inventing_pose(stereo_pair):
    a, b, *_ = stereo_pair
    a['img'][40:100, 5] = np.nan; a['vis'][40:100, 5] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['detected'] == 2
    assert report['written'] == 1 and len(report['rejected']) == 1
    assert 'missing joints' in report['rejected'][0]['reason']
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
        raw['img'][:, [15, 16]] = raw['img'][:, [16, 15]]
    swings, report = swings_from_raw(a, b, Options(hand='L', side='backhand', focal_a=900, focal_b=900))
    assert report['written'] == 2
    assert all(s['metadata']['hand'] == 'L' and s['side'] == 'backhand' for s in swings)


def test_cli_partial_output_is_explicit(tmp_path, monkeypatch, stereo_pair, capsys):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    a['img'][40:100, 5] = np.nan; a['vis'][40:100, 5] = 0
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
