"""Multi-input HTTP/publish contracts with synthetic pose extraction, real physics."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.server import app
from pipeline.tests.test_stereo_cli import stereo_pair
from pipeline.video import VideoInfo


@pytest.fixture
def multi_run(tmp_path, monkeypatch, stereo_pair):
    import pipeline.live as live
    import pipeline.multi as multi
    import pipeline.process as process

    a, b, *_ = stereo_pair
    root = tmp_path / 'results'
    model = tmp_path / 'model.task'
    model.write_bytes(b'pose extraction is injected')
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(root))
    monkeypatch.setenv('GHOST_POSE_MODEL', str(model))
    info = VideoInfo(120, 120, 2, 120, 1, 'manual', [])
    for module in (live, multi):
        monkeypatch.setattr(module, 'probe_video', lambda *args: info)
        monkeypatch.setattr(module, 'normalize_video', lambda source, dest, info: dest.write_bytes(b'normalized'))
    monkeypatch.setattr(live, 'extract_raw', lambda *args, **kwargs: copy.deepcopy(a))
    monkeypatch.setattr(live, 'run_tool', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('silent')))
    monkeypatch.setattr(process, 'extract_pair', lambda *args, **kwargs: (copy.deepcopy(a), copy.deepcopy(b)))
    sync_calls = []

    def audio(clip_a, clip_b, info_a, info_b, work, offset):
        sync_calls.append(offset)
        return 0., None, {'method': 'manual' if offset is not None else 'audio-peak'}

    monkeypatch.setattr(multi, 'prepare_audio', audio)
    return TestClient(app), root, sync_calls


def uploads(second=False, csv=None):
    files = {'video_a': ('front.mov', b'primary bytes', 'video/quicktime')}
    if second:
        files['video_b'] = ('side.MP4', b'secondary bytes', 'video/mp4')
    if csv is not None:
        files['sensor_csv'] = ('sensor.csv', csv, 'text/csv')
    return files


def published(client, root, response):
    assert response.status_code == 201, response.text
    result = response.json()
    assert {'detected', 'written', 'rejected', 'sync', 'calibration', 'session', 'files', 'status',
            'swingId', 'swingIds', 'coach', 'compare', 'webPath'} <= result.keys()
    assert result['webPath'] == '/ghost'
    assert result['swingId'] == result['swingIds'][0]
    assert result['written'] == len(result['swingIds']) > 0
    directory, = list(root.glob('*/manifest.json'))
    manifest = json.loads(directory.read_text())
    assert manifest['files'] == result['files']
    assert manifest['warnings'] == result['warnings']
    saved = [json.loads((directory.parent / name).read_text()) for name in manifest['files']]
    for swing in saved:
        identifier = swing['id']
        assert client.get(f'/swings/{identifier}').status_code == 200
        assert client.post(f'/coach/{identifier}').status_code == 200
        assert (directory.parent / f'{identifier}.coach.json').is_file()
        assert (directory.parent / f'{identifier}.compare.json').is_file()
        assert len(swing['frames'][0]['joints']) == 33
    assert json.loads((directory.parent / f"{result['swingId']}.coach.json").read_text()) == result['coach']
    assert json.loads((directory.parent / f"{result['swingId']}.compare.json").read_text()) == result['compare']
    assert {path.suffix for path in directory.parent.iterdir()} == {'.json'}
    return result, saved


def test_one_video_publishes_live_coach_ghost_and_compare(multi_run):
    client, root, calls = multi_run
    result, saved = published(client, root, client.post('/process/multi', files=uploads()))
    assert not calls and result['warnings'] == []
    assert all(swing['metadata']['depth'] == 'estimated (1 camera)' for swing in saved)
    assert all(swing['source'] == swing['metadata']['reconstruction'] == 'mono' for swing in saved)


def test_two_videos_publish_triangulated_depth(multi_run):
    client, root, calls = multi_run
    result, saved = published(client, root, client.post('/process/multi', files=uploads(True)))
    assert calls == [None]
    assert result['sync']['method'] == 'audio-peak'
    assert result['warnings'] == []
    assert all(swing['metadata']['depth'] == 'triangulated (2 cameras)' for swing in saved)
    assert all(swing['source'] == swing['metadata']['reconstruction'] == 'stereo' for swing in saved)
    assert all(swing['metadata']['sourceTimeBase'] == 'normalized-real-time' for swing in saved)


@pytest.mark.parametrize('second', [False, True])
def test_auto_slowdown_uses_airdrop_metadata(multi_run, monkeypatch, second):
    import pipeline.live as live
    import pipeline.multi as multi
    import pipeline.video as video
    from pipeline.tests.test_live_clip import probe_payload

    client, root, _ = multi_run
    payload = probe_payload('30/1', '30/1', {'com.apple.quicktime.full-frame-rate-playback-intent': '1'})
    monkeypatch.setattr(video, 'run_tool', lambda *args, **kwargs: json.dumps(payload))
    monkeypatch.setattr(video, 'quicktime_edits', lambda *args: [])
    calls = []

    def probe(path, slowdown):
        calls.append(slowdown)
        return video.probe_video(path, slowdown)

    monkeypatch.setattr(live, 'probe_video', probe)
    monkeypatch.setattr(multi, 'probe_video', probe)
    # The page leaves both fields out for Auto, exactly as it does for /process.
    result, saved = published(client, root, client.post('/process/multi', files=uploads(second)))
    assert calls == ([None, None] if second else [None])
    assert result['warnings'] == []
    assert all(swing['metadata']['slowdown'] == 4 for swing in saved)
    assert all(swing['metadata']['slowdownSource'] == 'playback-intent' for swing in saved)


@pytest.mark.parametrize('values,expected', [
    ({'slowdown_a': '4'}, [4, 4]),
    ({'slowdown_a': '4', 'slowdown_b': '2'}, [4, 2]),
    ({'slowdown_b': '2'}, [None, 2]),
])
def test_second_camera_inherits_only_an_explicit_primary_override(multi_run, monkeypatch, values, expected):
    import pipeline.multi as multi
    client, root, _ = multi_run
    original_probe = multi.probe_video
    calls = []

    def probe(path, slowdown):
        calls.append(slowdown)
        return original_probe(path, slowdown)

    monkeypatch.setattr(multi, 'probe_video', probe)
    published(client, root, client.post('/process/multi', files=uploads(True), data=values))
    assert calls == expected


@pytest.mark.parametrize('manual', [False, True])
def test_auto_preserves_live_speed_retry_without_overriding_manual_one(multi_run, monkeypatch, manual):
    import pipeline.live as live
    client, root, _ = multi_run
    raw = live.extract_raw('injected')
    slowed = {**raw, 't': raw['t'] * 4, 'fps': raw['fps'] / 4}
    monkeypatch.setattr(live, 'extract_raw', lambda *args, **kwargs: copy.deepcopy(slowed))
    monkeypatch.setattr(live, 'probe_video', lambda *args: VideoInfo(30, 30, 8, 30, 1, 'encoded-cadence', []))
    detect = live.swings_from_raw
    calls = []

    def swings(raw, b, options):
        calls.append(options.slowdown_a)
        return detect(raw, b, options)

    monkeypatch.setattr(live, 'swings_from_raw', swings)
    response = client.post('/process/multi', files=uploads(), data={'slowdown_a': '1'} if manual else {})
    if manual:
        assert response.status_code == 422
        assert calls == [1]
        assert not list(root.glob('*/manifest.json'))
    else:
        _, saved = published(client, root, response)
        assert calls == [1, 2, 4, 8]
        assert all(swing['metadata']['slowdown'] == 4 for swing in saved)
        assert all(swing['metadata']['slowdownSource'] == 'speed-retry' for swing in saved)


def test_two_videos_and_csv_attach_before_coaching(multi_run, monkeypatch):
    import pipeline.multi as multi
    client, root, _ = multi_run
    original_coach = multi.coach_swing
    coached = []

    def attach(swings, clip, csv, **kwargs):
        assert csv.read_bytes() == b'CSV fixture'
        assert clip.read_bytes() == b'primary bytes'
        assert kwargs['slowdown'] is None and kwargs['info'].capture_fps == 120
        for swing in swings:
            swing['wrist'] = {'usable': True, 'mock': True, 'roll_change_abs_deg': 10.,
                             'peak_roll_rate_abs_dps': 15., 'peak_angular_speed_dps': 350.,
                             'contact_source': 'gyro peak'}
        return swings, []

    def coach(swing, **kwargs):
        assert swing['wrist']['usable']
        coached.append(swing['id'])
        return original_coach(swing, **kwargs)

    monkeypatch.setattr(multi, 'attach_sensor', attach)
    monkeypatch.setattr(multi, 'coach_swing', coach)
    result, saved = published(client, root, client.post('/process/multi', files=uploads(True, b'CSV fixture')))
    assert result['warnings'] == [] and set(coached) == set(result['swingIds'])
    assert all(swing['wrist']['usable'] for swing in saved)
    assert all(swing['metadata']['depth'] == 'triangulated (2 cameras)' for swing in saved)
    assert result['compare']['assumptions']['launch']['you']['azimuth']['label'] == 'MOCK (sensor)'


@pytest.mark.parametrize('filename,contents', [
    ('sensor.csv', b'not,a,sensor\n1,2,3'),
    ('sensor.zip', b'not an archive'),
    ('sensor.bin', b'PK\x03\x04truncated archive'),
    ('sensor.bin', b'unreadable sensor file'),
])
def test_bad_sensor_is_ignored_and_upload_still_publishes(multi_run, filename, contents):
    client, root, _ = multi_run
    files = uploads(True)
    files['sensor_csv'] = (filename, contents, 'application/octet-stream')
    result, saved = published(client, root, client.post('/process/multi', files=files))
    assert result['warnings']
    assert any('sensor' in warning.lower() or 'csv' in warning.lower() for warning in result['warnings'])
    assert all('wrist' not in swing for swing in saved)


@pytest.mark.parametrize('filename', ['sensor.csv', 'sensor.ZIP', 'sensor.bin'])
def test_real_sensor_sync_measurement_and_publish_are_chained(multi_run, tmp_path, monkeypatch, filename):
    """Generated recording; actual CSV/ZIP loader, tap sync, wrist/coach/physics."""
    import pipeline.multi as multi
    import pipeline.multi_wrist as wrist
    from pipeline.tests.test_multi_wrist import flat_csv, info
    from wrist.fuse import read_swings
    from wrist.load import load_recording
    from wrist.synth import make_session

    client, root, _ = multi_run
    truth = make_session(tmp_path / 'sensor-session', labels=('none', 'rolled_wrist'),
                         camera=True, video_jitter_s=0, shadow=(1,), zip_export=True)
    recording = load_recording(truth['export'])
    swings = list(read_swings(truth['swings_dir']).values())
    for swing in swings:
        swing['metadata']['reconstruction'] = 'stereo'
    monkeypatch.setattr(multi, '_stereo', lambda *args: (copy.deepcopy(swings),
        {'detected': len(swings), 'written': len(swings), 'rejected': [], 'sync': {}, 'calibration': {}}, info()))
    monkeypatch.setattr(wrist, '_video_taps', lambda *args: [t - truth['video_offset_s'] for t in truth['taps_s']])
    sensor = (flat_csv(tmp_path / 'sensor.csv', recording) if filename.endswith('.csv')
              else Path(truth['export']))
    files = uploads(True)
    files['sensor_csv'] = (filename, sensor.read_bytes(), 'application/octet-stream')
    result, saved = published(client, root, client.post('/process/multi', files=files))
    assert not any('ignored' in warning.lower() for warning in result['warnings'])
    for swing in saved:
        assert swing['wrist']['usable'] and swing['wrist']['contact_source'] == 'gyro peak'
        assert swing['metadata']['wristSync']['method'] == 'audio double tap matched to sensor taps'
    assert result['compare']['assumptions']['launch']['you']['azimuth']['label'] == 'MOCK (sensor)'


def test_failed_optional_attachment_cannot_partially_mutate_video_swings(multi_run, monkeypatch):
    import pipeline.multi as multi
    client, root, _ = multi_run

    def broken(swings, *args, **kwargs):
        swings[0]['frames'] = []
        raise ValueError('cannot sync')

    monkeypatch.setattr(multi, 'attach_sensor', broken)
    result, saved = published(client, root, client.post('/process/multi', files=uploads(csv=b'CSV fixture')))
    assert all(swing['frames'] and 'wrist' not in swing for swing in saved)
    assert any('ignored' in warning for warning in result['warnings'])


@pytest.mark.parametrize('failure', ['audio', 'empty', 'calibration'])
def test_stereo_failure_keeps_video_a_available(multi_run, monkeypatch, failure):
    import pipeline.multi as multi
    import pipeline.process as process
    client, root, _ = multi_run
    if failure == 'audio':
        monkeypatch.setattr(multi, 'prepare_audio', lambda *args: (_ for _ in ()).throw(ValueError('No peak')))
    elif failure == 'empty':
        monkeypatch.setattr(multi, 'process_clips', lambda *args: {'files': [], 'written': 0})
    else:
        pair = process.extract_pair

        def no_overlap(*args, **kwargs):
            a, b = pair(*args, **kwargs)
            b['vis'][:] = 0
            return a, b

        monkeypatch.setattr(process, 'extract_pair', no_overlap)
    result, saved = published(client, root, client.post('/process/multi', files=uploads(True)))
    assert any('using video_a' in warning for warning in result['warnings'])
    assert all(swing['metadata']['depth'] == 'estimated (1 camera)' for swing in saved)


def test_explicit_offset_is_forwarded_and_not_double_scaled(multi_run, monkeypatch):
    import pipeline.multi as multi
    import pipeline.process as pipeline
    client, root, calls = multi_run
    original = multi.process_clips
    pair = pipeline.extract_pair
    seen = []

    def shifted(*args, **kwargs):
        a, b = pair(*args, **kwargs)
        b['t'] += .125
        return a, b

    def audio(a, b, info_a, info_b, work, offset):
        calls.append(offset)
        return .125, None, {'method': 'provided-offset'}

    def process(a, b, destination, options):
        seen.append(options)
        return original(a, b, destination, options)

    monkeypatch.setattr(multi, 'process_clips', process)
    monkeypatch.setattr(multi, 'prepare_audio', audio)
    monkeypatch.setattr(pipeline, 'extract_pair', shifted)
    published(client, root, client.post('/process/multi', files=uploads(True),
              data={'slowdown_a': '4', 'slowdown_b': '2', 'offset_b_s': '0.25'}))
    assert calls == [.25]
    assert seen[0].slowdown_a == seen[0].slowdown_b == 1
    assert seen[0].offset_b == .125


def test_repeated_uploads_have_distinct_resolvable_ids(multi_run):
    client, _, _ = multi_run
    first = client.post('/process/multi', files=uploads(True)).json()
    second = client.post('/process/multi', files=uploads(True)).json()
    assert set(first['swingIds']).isdisjoint(second['swingIds'])
    for identifier in first['swingIds'] + second['swingIds']:
        assert client.get(f'/swings/{identifier}').status_code == 200


def test_coaching_failure_publishes_nothing(multi_run, monkeypatch):
    import pipeline.multi as multi
    client, root, _ = multi_run
    monkeypatch.setattr(multi, 'coach_swing', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('not measurable')))
    response = client.post('/process/multi', files=uploads(True))
    assert response.status_code == 422
    assert not list(root.glob('*/manifest.json'))
    assert client.get('/swings').json() == {'swings': []}


@pytest.mark.parametrize('values', [{'slowdown_a': '0'}, {'slowdown_b': '17'},
                                    {'slowdown_a': 'nan'}, {'offset_b_s': 'inf'}])
def test_invalid_controls_are_rejected(multi_run, values):
    client, _, _ = multi_run
    assert client.post('/process/multi', files=uploads(), data=values).status_code == 422


def test_required_video_and_shared_admission_limits(multi_run, monkeypatch):
    import pipeline.server as server
    client, _, _ = multi_run
    assert client.post('/process/multi', files={'video_b': ('b.mov', b'bytes')}).status_code == 422
    assert client.post('/process/multi', files={'video_a': ('a.mov', b'')}).status_code == 422
    assert client.post('/process/multi', files={'video_a': ('a.txt', b'bytes')}).status_code == 422
    assert server.PROCESS_SEMAPHORE.acquire(blocking=False)
    try:
        assert client.post('/process/multi', files=uploads()).status_code == 429
    finally:
        server.PROCESS_SEMAPHORE.release()
    response = client.post('/process/multi', files=uploads(), headers={'Content-Length': str(server.MAX_UPLOAD_BYTES + 1)})
    assert response.status_code == 413
    monkeypatch.setattr(server, 'MAX_UPLOAD_BYTES', 20)
    response = client.post('/process/multi', files=uploads(True), headers={'Content-Length': '0'})
    assert response.status_code == 413  # aggregate actual bytes, even with a dishonest header


@pytest.mark.parametrize('optional', ['video_b', 'sensor_csv'])
def test_invalid_optional_file_is_only_a_warning(multi_run, optional):
    client, root, _ = multi_run
    files = uploads()
    files[optional] = ('unexpected.txt', b'unsupported')
    result, _ = published(client, root, client.post('/process/multi', files=files))
    assert result['warnings']
