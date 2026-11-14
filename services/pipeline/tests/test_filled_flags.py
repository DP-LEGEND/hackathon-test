"""Synthetic provenance, run-scoped labels, and repo-root startup regressions."""
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pipeline.pose import to_swing
from pipeline.process import Options, swings_from_raw
from pipeline.server import app
from pipeline.tests.test_stereo_cli import stereo_pair

ROOT = Path(__file__).resolve().parents[3]
check_swing = runpy.run_path(str(ROOT / 'scripts/check_swing.py'))['check']


def synthetic_raw(n=8):
    return {'world': np.ones((n, 33, 3)), 't': np.arange(n) / 30, 'fps': 30}


def masks(swing):
    return np.array([frame['filled'] for frame in swing['frames']])


def test_serializer_flags_smoothing_fills_and_slices_upstream_flags():
    raw = synthetic_raw()
    raw['world'][3, 5] = np.nan
    raw['filled'] = np.zeros((8, 33), dtype=bool)
    raw['filled'][5, 7] = True
    swing = to_swing(raw, f0=2, f1=7, contact_frame=2)
    expected = np.zeros((5, 33), dtype=bool)
    expected[1, 5] = expected[3, 7] = True
    np.testing.assert_array_equal(masks(swing), expected)
    assert not check_swing(swing)[0]
    json.dumps(swing, allow_nan=False)


@pytest.mark.parametrize('filled', [np.zeros((8, 32), dtype=bool), np.zeros((8, 33), dtype=int)])
def test_serializer_rejects_invalid_provenance(filled):
    raw = synthetic_raw()
    raw['filled'] = filled
    with pytest.raises(ValueError, match='filled must be a boolean array'):
        to_swing(raw)


def test_checker_accepts_legacy_frames_and_rejects_malformed_optional_flags():
    swing = to_swing(synthetic_raw(), contact_frame=3)
    for frame in swing['frames']:
        frame.pop('filled')
    assert not check_swing(swing)[0]
    for invalid in (None, [False] * 32, [0] * 33, [False] * 32 + ['true']):
        swing['frames'][0]['filled'] = invalid
        assert any('filled' in error for error in check_swing(swing)[0])


def test_mono_gap_and_parent_copies_are_flagged_per_frame(stereo_pair):
    a, b, *_ = stereo_pair
    b['vis'][:] = 0
    a['world'][60:65, 13] = np.nan
    a['img'][60:65, 13] = np.nan
    a['world'][55:100, 5] = np.nan  # long optional gap is copied, not interpolated
    swings, report = swings_from_raw(a, b)
    assert report['written'] == 2
    for swing in swings:
        flags = masks(swing)
        start = swing['metadata']['sourceStartFrame']
        source_frames = np.arange(len(flags)) + start
        np.testing.assert_array_equal(flags[:, 13], (source_frames >= 60) & (source_frames < 65))
        np.testing.assert_array_equal(flags[:, 5], (source_frames >= 55) & (source_frames < 100))
        assert not flags[:, 12].any()
        assert swing['source'] == 'mono'
        assert not check_swing(swing)[0]


def test_stereo_gap_fill_and_observations_are_distinguished(stereo_pair):
    a, b, *_ = stereo_pair
    b['vis'][60:65, 13] = 0
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == 2
    for swing in swings:
        assert swing['source'] == 'stereo'
        flags = masks(swing)
        frames = np.arange(len(flags)) + swing['metadata']['sourceStartFrame']
        np.testing.assert_array_equal(flags[:, 13], (frames >= 60) & (frames < 65))
        assert not flags[:, 12].any()


def test_stereo_camera_b_time_interpolation_is_flagged(stereo_pair):
    a, b, *_ = stereo_pair
    for key in ('t', 'img', 'vis', 'world'):
        b[key] = b[key][::2]
    b['fps'] /= 2
    swings, report = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert report['written'] == 2
    for swing in swings:
        assert swing['source'] == 'stereo'
        frames = np.arange(len(swing['frames'])) + swing['metadata']['sourceStartFrame']
        np.testing.assert_array_equal(masks(swing)[:, 12], frames % 2 == 1)


def test_failed_stereo_normalisation_uses_mono_provenance(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, b, *_ = stereo_pair
    b['vis'][60:65, 13] = 0
    original = process.normalise
    calls = []
    def normalise(points, torso):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError('synthetic stereo failure')
        return original(points, torso)
    monkeypatch.setattr(process, 'normalise', normalise)
    swings, _ = swings_from_raw(a, b, Options(focal_a=900, focal_b=900))
    assert swings[0]['source'] == 'mono'
    assert not masks(swings[0])[:, 13].any()


@pytest.fixture
def labelled_api(tmp_path, monkeypatch):
    for run in ('run-a', 'run-b'):
        directory = tmp_path / run
        directory.mkdir()
        swing = to_swing(synthetic_raw(), swing_id='same', contact_frame=3)
        (directory / 'same.json').write_text(json.dumps(swing))
        (directory / 'manifest.json').write_text(json.dumps({'files': ['same.json']}))
    labels = tmp_path / 'labels.csv'
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    monkeypatch.setenv('GHOST_LABELS_CSV', str(labels))
    return TestClient(app), labels


def test_same_swing_id_matches_only_its_run(labelled_api):
    client, labels = labelled_api
    labels.write_text('pipeline_run,swing,intended_fault\nrun-a,same,none\nrun-b,same,early_wrist\n')
    rows = client.get('/swings').json()['swings']
    assert {row['id']: row['label'] for row in rows} == {'same@run-a': 'good', 'same@run-b': 'early_wrist'}


def test_missing_run_label_never_falls_back_to_another_run_or_bare_id(labelled_api):
    client, labels = labelled_api
    labels.write_text('pipeline_run,swing,intended_fault\nrun-a,same,none\n,same,open_stance\n')
    rows = client.get('/swings').json()['swings']
    assert {row['id']: row['label'] for row in rows} == {'same@run-a': 'good', 'same@run-b': None}


def test_conflicting_suffix_and_run_column_are_rejected(labelled_api):
    client, labels = labelled_api
    labels.write_text('pipeline_run,swing,intended_fault\nrun-b,same@run-a,none\n')
    assert client.get('/swings').status_code == 503


def test_health_is_independent_of_catalogue(labelled_api, monkeypatch):
    client, _ = labelled_api
    monkeypatch.setenv('GHOST_SWINGS_DIR', 'does-not-exist')
    assert client.get('/health').json() == {'ok': True}


def test_documented_repo_root_start_command(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {**os.environ, 'GHOST_SWINGS_DIR': str(tmp_path / 'empty')}
    command = [sys.executable, '-m', 'uvicorn', 'pipeline.server:app', '--app-dir',
               'services', '--host', '127.0.0.1', '--port', str(port)]
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None, 'API exited during startup'
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=.5) as response:
                    assert json.load(response) == {'ok': True}
                break
            except urllib.error.URLError:
                time.sleep(.05)
        else:
            pytest.fail('API did not become healthy from the documented root command')
    finally:
        process.terminate()
        process.wait(timeout=5)
