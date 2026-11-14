"""Review regressions: timing trims, inference recovery and upload admission."""
import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pipeline.live import LiveOptions, peak_wrist_speed, process_live_clip
from pipeline.process import Options, process_clips, swings_from_raw
from pipeline.server import app
from pipeline.video import VideoInfo, probe_video, timing_at
from pipeline.tests.test_live_clip import metadata_file, probe_payload
from pipeline.tests.test_stereo_cli import stereo_pair


@pytest.fixture
def live_run(tmp_path, monkeypatch, stereo_pair):
    import pipeline.live as live
    a, _, *_ = stereo_pair
    clip, model = tmp_path / 'clip.avi', tmp_path / 'model.task'
    clip.write_bytes(b'synthetic decode input')
    model.write_bytes(b'injected model')
    monkeypatch.setattr(live, 'probe_video', lambda *args: VideoInfo(120, 120, 2, 120, 1, 'encoded-cadence', []))
    monkeypatch.setattr(live, 'normalize_video', lambda source, dest, info: dest.write_bytes(b'decoded'))
    monkeypatch.setattr(live, 'extract_raw', lambda *args, **kwargs: a)
    monkeypatch.setattr(live, 'run_tool', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('silent')))
    return clip, tmp_path / 'out', str(model), a


def test_manual_slowdown_retains_trim_and_playback_mapping(tmp_path, monkeypatch):
    import pipeline.video as video
    clip = tmp_path / 'trimmed.mov'
    clip.write_bytes(b'probe injected below')
    edit = {'playbackStart': 0., 'playbackEnd': 1., 'mediaStart': 1., 'rate': 1.}
    monkeypatch.setattr(video, 'quicktime_edits', lambda path: [edit])
    def probe(arguments, **kwargs):
        if '-ignore_editlist' in arguments:
            return json.dumps({'streams': [{'avg_frame_rate': '30/1', 'duration': '3'}]})
        return json.dumps(probe_payload('30/1', '30/1'))
    monkeypatch.setattr(video, 'run_tool', probe)
    info = probe_video(clip, slowdown=4)
    assert info.edits == [edit] and info.ignore_edits
    assert info.source == 'manual' and info.capture_fps == 120
    assert timing_at(info, .125) == (.5, 4)
    calls = []
    monkeypatch.setattr(video, 'run_tool', lambda arguments, **kwargs: calls.append(arguments))
    video.normalize_video(clip, tmp_path / 'out.avi', info)
    filters = calls[0][calls[0].index('-filter_complex') + 1]
    assert 'trim=start=1.0:end=2.0' in filters and 'setpts=(PTS-STARTPTS)/4.0' in filters


def test_ambiguous_stroke_does_not_discard_other_swings(live_run, monkeypatch):
    import pipeline.live as live
    clip, output, model, raw = live_run
    swings, report = swings_from_raw(raw, options=Options(hand='R', side='forehand'))
    swings[0]['side'] = swings[0]['metadata']['stroke'] = 'unknown'
    monkeypatch.setattr(live, 'swings_from_raw', lambda *args: (swings, report))
    # The skeleton can't tell either, so the coach infers (else physics decides before coaching).
    monkeypatch.setattr(live, 'decide_stroke', lambda swing, hand: ('forehand', 'assumed'))
    original = live.coach_swing
    called = []
    def coach(swing, stroke, **kwargs):
        called.append(stroke)
        if stroke is None:
            assert 'stroke' not in swing and 'stroke' not in swing['metadata']
        return original(swing, stroke=stroke, **kwargs)
    monkeypatch.setattr(live, 'coach_swing', coach)
    result = process_live_clip(clip, output, LiveOptions(hand='R', model_path=model))
    assert result['written'] == 2 and called == [None, 'forehand']
    manifest = json.loads((output / 'manifest.json').read_text())
    saved = [json.loads((output / name).read_text()) for name in manifest['files']]
    assert saved[0]['metadata']['strokeSource'] == 'coach-inferred'
    assert saved[0]['stroke'] == saved[0]['metadata']['stroke'] in ('forehand', 'backhand')
    assert saved[1]['metadata']['stroke'] == 'forehand'


@pytest.mark.parametrize('label, decided_by', [('unknown', 'measured'),
                                               ('forehand', 'measured (auto label overridden)')])
def test_live_coaches_the_stroke_the_skeleton_decides(live_run, monkeypatch, label, decided_by):
    # IMG_2116 is a backhand that the coach, left to guess, calls a forehand. The stroke is decided
    # from the skeleton before coaching, so the advice, ghost fix and ball path are all backhand.
    import pipeline.live as live
    from pathlib import Path
    from coach.agent import coach_swing
    from coach.faults import THRESHOLDS
    clip, output, model, raw = live_run
    swings, report = swings_from_raw(raw, options=Options(hand='R', side='forehand'))
    sample = json.loads((Path(__file__).resolve().parents[3] / 'data/samples/swing_sample.json').read_text())
    swing = {**swings[0], 'frames': sample['frames'], 'contactFrame': sample['contactFrame'],
             'fps': sample['fps'], 'fpsReal': sample['fps'], 'side': label}
    guess = coach_swing({k: v for k, v in swing.items() if k != 'stroke'}, fps_real=120.0)
    assert (guess['stroke'], guess['stroke_source']) == ('forehand', 'detected')  # the coach's own guess
    monkeypatch.setattr(live, 'swings_from_raw', lambda *args: ([swing], report))
    result = process_live_clip(clip, output, LiveOptions(hand='R', model_path=model))
    coached = result['coach']
    assert (coached['stroke'], coached['stroke_source']) == ('backhand', 'given')
    fault = coached['fault']
    assert fault['stroke'] == 'backhand' and fault['threshold'] == THRESHOLDS['backhand'][fault['id']]['threshold']
    assert set(coached['other_faults']) <= set(THRESHOLDS['backhand'])
    saved = json.loads((output / f"{result['swingId']}.json").read_text())
    assert saved['stroke'] == saved['metadata']['stroke'] == 'backhand'
    assert saved['metadata']['strokeSource'] == decided_by
    stroke = result['compare']['assumptions']['stroke']
    assert stroke == {'value': 'backhand', 'source': decided_by, 'label': 'ESTIMATE'}
    assert result['compare']['assumptions']['anchor']['x'] == 2.0


def test_process_clips_forwards_live_min_speed(tmp_path, monkeypatch):
    import pipeline.live as live
    captured = []
    monkeypatch.setattr(live, 'process_live_clip', lambda clip, output, options: captured.append(options))
    process_clips('one.mov', None, str(tmp_path / 'out'), Options(min_speed=19.5))
    assert captured[0].min_speed == 19.5


@pytest.mark.parametrize('intent', ['0', '1'])
def test_playback_intent_defaults_to_four_and_manual_wins(tmp_path, monkeypatch, intent):
    clip = metadata_file(tmp_path, monkeypatch, probe_payload('30/1', '30/1', {
        'com.apple.quicktime.full-frame-rate-playback-intent': intent}))
    automatic = probe_video(clip)
    assert automatic.slowdown == 4 and automatic.source == 'playback-intent'
    assert automatic.capture_fps == 120
    manual = probe_video(clip, slowdown=1)
    assert manual.slowdown == 1 and manual.source == 'manual'


def test_playback_intent_provenance_is_saved(live_run, monkeypatch):
    import pipeline.live as live
    clip, output, model, _ = live_run
    monkeypatch.setattr(live, 'probe_video', lambda *args: VideoInfo(30, 30, 8, 120, 4, 'playback-intent', []))
    result = process_live_clip(clip, output, LiveOptions(model_path=model))
    saved = json.loads((output / f"{result['swingId']}.json").read_text())
    assert saved['metadata']['slowdownSource'] == 'playback-intent'


def retry_fixture(live_run, monkeypatch, base_speed=5):
    import pipeline.live as live
    clip, output, model, raw = live_run
    template = swings_from_raw(raw, options=Options(hand='R', side='forehand'))[0][0]
    calls = []
    def detections(raw, b, options):
        factor = options.slowdown_a
        calls.append(factor)
        report = {'detected': 0, 'written': 0, 'rejected': []}
        if factor == 1:
            return [], report
        swing = copy.deepcopy(template)
        swing['fps'] = swing['fpsReal'] = 30 * factor
        for index, frame in enumerate(swing['frames']):
            frame['t'] = index / (30 * factor)
            frame['joints'][16] = [index * base_speed / 30, .2, 0]
        swing['metadata']['sourceContactSeconds'] = swing['contactFrame'] / 30
        swing['metadata']['realStartSeconds'] = 0
        report.update(detected=1, written=1)
        return [swing], report
    monkeypatch.setattr(live, 'probe_video', lambda *args: VideoInfo(30, 30, 4, 30, 1, 'encoded-cadence', []))
    monkeypatch.setattr(live, 'swings_from_raw', detections)
    monkeypatch.setattr(live, 'coach_swing', lambda *args, **kwargs: {
        'stroke': 'forehand', 'ghost_ready': False, 'fix': None, 'fix_amount': None})
    monkeypatch.setattr(live, 'compare', lambda *args, **kwargs: {'you': {}, 'ghost': {}})
    return clip, output, model, calls


def test_slowdown_retries_choose_measured_plausible_wrist_speed(live_run, monkeypatch):
    clip, output, model, calls = retry_fixture(live_run, monkeypatch)
    result = process_live_clip(clip, output, LiveOptions(model_path=model))
    assert calls == [1, 2, 4, 8]
    swing = json.loads((output / f"{result['swingId']}.json").read_text())
    assert swing['metadata']['slowdown'] == 4
    assert swing['metadata']['slowdownSource'] == 'speed-retry'
    assert swing['metadata']['retryPeakWristSpeedMs'] == pytest.approx(20)
    assert peak_wrist_speed(swing) == pytest.approx(20)


@pytest.mark.parametrize('with_audio', [False, True])
def test_retry_saves_same_contact_times_as_normalized_clip(live_run, monkeypatch, with_audio):
    import pipeline.live as live
    clip, output, model, raw = live_run
    raw = copy.deepcopy(raw)
    raw['world'][:, 16, 0] *= 1.5
    slowed = {**raw, 't': raw['t'] * 4, 'fps': raw['fps'] / 4}
    if with_audio:
        monkeypatch.setattr(live, 'run_tool', lambda *args, **kwargs: '')
        monkeypatch.setattr(live, 'audio_hits', lambda *args, **kwargs: np.array([.63, 1.53]) * 4)

    def saved_swings(destination, info, pose, options):
        monkeypatch.setattr(live, 'probe_video', lambda *args: info)
        monkeypatch.setattr(live, 'extract_raw', lambda *args, **kwargs: copy.deepcopy(pose))
        result = process_live_clip(clip, destination, options)
        return [json.loads((destination / name).read_text()) for name in result['files']]

    retried = saved_swings(output, VideoInfo(30, 30, 8, 30, 1, 'encoded-cadence', []), slowed,
                          LiveOptions(hand='R', stroke='forehand', model_path=model))
    normalized = saved_swings(output.with_name('manual'), VideoInfo(30, 30, 8, 120, 4, 'manual', []), raw,
                             LiveOptions(slowdown=4, hand='R', stroke='forehand', model_path=model))
    assert len(retried) == len(normalized) == 2
    for actual, expected in zip(retried, normalized):
        metadata = actual['metadata']
        assert metadata['slowdown'] == 4 and metadata['slowdownSource'] == 'speed-retry'
        assert metadata['contactMethod'] == ('audio-transient' if with_audio else 'wrist-speed-peak-estimate')
        real_contact = metadata['realStartSeconds'] + actual['frames'][actual['contactFrame']]['t']
        assert metadata['sourceContactSeconds'] == pytest.approx(real_contact)
        for field in ('sourceContactSeconds', 'sourceContactPlaybackSeconds'):
            assert metadata[field] == pytest.approx(expected['metadata'][field])
        assert metadata['sourceContactPlaybackSeconds'] == pytest.approx(real_contact * 4)


def test_no_plausible_retry_publishes_nothing(live_run, monkeypatch):
    clip, output, model, calls = retry_fixture(live_run, monkeypatch, base_speed=20)
    with pytest.raises(ValueError, match='No fully tracked'):
        process_live_clip(clip, output, LiveOptions(model_path=model))
    assert calls == [1, 2, 4, 8] and not output.exists()


def test_manual_slowdown_is_never_retried(live_run, monkeypatch):
    clip, output, model, calls = retry_fixture(live_run, monkeypatch)
    with pytest.raises(ValueError, match='No fully tracked'):
        process_live_clip(clip, output, LiveOptions(slowdown=1, model_path=model))
    assert calls == [1]


def test_coach_uses_animated_fallback_without_replacing_top_fault(tmp_path, monkeypatch):
    import pipeline.server as server
    monkeypatch.setattr(server, 'measurement_swing', lambda identifier: {
        'contactFrame': 3, 'metadata': {'hand': 'R'}, 'side': 'forehand'})
    verdict = {'fault': {'id': 'unsupported'}, 'fix': 'firm_wrist', 'fix_amount': 20,
               'cue': 'Keep your wrist steady.', 'ghost_ready': False,
               'ghost_fix': 'bend_elbow', 'ghost_fix_amount': 12}
    monkeypatch.setattr(server, 'coach_swing', lambda *args, **kwargs: verdict)
    client = TestClient(app)
    result = client.post('/coach/synthetic').json()
    assert result['fault'] == verdict['fault'] and result['cue'] == verdict['cue']
    assert result['fix'] == 'bend_elbow' and result['amount'] == 12 and result['ghost_ready']
    verdict['ghost_fix'] = 'not-supported'
    result = client.post('/coach/synthetic').json()
    assert result['fix'] is None and result['amount'] is None and not result['ghost_ready']


def admission_request(headers):
    sent = []
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'method': 'POST', 'path': '/process',
             'root_path': '', 'scheme': 'http', 'query_string': b'', 'http_version': '1.1',
             'headers': headers, 'server': ('localhost', 8000), 'client': ('127.0.0.1', 1)}
    async def never_read():
        pytest.fail('Rejected upload must not read or parse its body')
    async def send(message):
        sent.append(message)
    asyncio.run(app(scope, never_read, send))
    return sent


def test_oversized_content_length_rejected_before_form_parsing():
    import pipeline.server as server
    sent = admission_request([(b'content-length', str(server.MAX_UPLOAD_BYTES + 1).encode()),
                              (b'content-type', b'multipart/form-data; boundary=test')])
    assert sent[0]['status'] == 413
    assert server.PROCESS_SEMAPHORE.acquire(blocking=False)
    server.PROCESS_SEMAPHORE.release()


async def streamed_upload(chunks):
    sent = []
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'method': 'POST', 'path': '/process',
             'root_path': '', 'scheme': 'http', 'query_string': b'', 'http_version': '1.1',
             'headers': [(b'content-type', b'multipart/form-data; boundary=test')],
             'server': ('localhost', 8000), 'client': ('127.0.0.1', 1)}
    async def receive():
        chunk = await anext(chunks, None)
        return {'type': 'http.request', 'body': chunk or b'', 'more_body': chunk is not None}
    async def send(message):
        sent.append(message)
    await app(scope, receive, send)
    return sent


def test_busy_upload_is_size_checked_before_job_admission(tmp_path, monkeypatch):
    import pipeline.server as server
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    monkeypatch.setattr(server, 'MAX_UPLOAD_BYTES', 4)
    assert server.PROCESS_SEMAPHORE.acquire(blocking=False)
    try:
        async def chunks():
            yield (b'--test\r\nContent-Disposition: form-data; name="file"; filename="a.mov"\r\n'
                   b'Content-Type: video/quicktime\r\n\r\ntoo-large\r\n--test--\r\n')
        assert asyncio.run(streamed_upload(chunks()))[0]['status'] == 413
    finally:
        server.PROCESS_SEMAPHORE.release()


def test_slow_upload_does_not_reserve_processing_slot(tmp_path, monkeypatch):
    import pipeline.server as server
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    processed = []
    def process(upload, *args):
        processed.append(upload.read_bytes())
        return {'swingId': 'ready'}
    monkeypatch.setattr(server, 'process_live_clip', process)

    async def exercise():
        paused, resume = asyncio.Event(), asyncio.Event()
        async def slow_body():
            yield (b'--test\r\nContent-Disposition: form-data; name="file"; filename="slow.mov"\r\n'
                   b'Content-Type: video/quicktime\r\n\r\nsl')
            paused.set()
            await resume.wait()
            yield b'ow\r\n--test--\r\n'
        async def fast_body():
            yield (b'--test\r\nContent-Disposition: form-data; name="file"; filename="fast.mov"\r\n'
                   b'Content-Type: video/quicktime\r\n\r\nfast\r\n--test--\r\n')
        slow = asyncio.create_task(streamed_upload(slow_body()))
        try:
            await asyncio.wait_for(paused.wait(), timeout=5)
            fast = await asyncio.wait_for(streamed_upload(fast_body()), timeout=5)
            assert fast[0]['status'] == 201
            assert processed == [b'fast'] and not slow.done()
        finally:
            resume.set()
            completed = await asyncio.wait_for(slow, timeout=5)
        assert completed[0]['status'] == 201
        assert processed == [b'fast', b'slow']
    asyncio.run(exercise())


@pytest.mark.parametrize('failure,status', [(ValueError, 422), (RuntimeError, 503), (OSError, 503)])
def test_processing_failure_releases_slot(tmp_path, monkeypatch, failure, status):
    import pipeline.server as server
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    def fail(*args):
        raise failure('processing failed')
    monkeypatch.setattr(server, 'process_live_clip', fail)
    with TestClient(app) as client:
        assert client.post('/process', files={'file': ('a.mov', b'clip')}).status_code == status
        monkeypatch.setattr(server, 'process_live_clip', lambda *args: {'swingId': 'ready'})
        assert client.post('/process', files={'file': ('b.mov', b'clip')}).status_code == 201


def test_concurrent_job_is_rejected_and_slot_is_released(tmp_path, monkeypatch):
    import pipeline.server as server
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    entered, finish = threading.Event(), threading.Event()
    def process(*args):
        entered.set()
        assert finish.wait(timeout=5)
        return {'swingId': 'ready'}
    monkeypatch.setattr(server, 'process_live_clip', process)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(client.post, '/process', files={'file': ('a.mov', b'clip')})
        try:
            assert entered.wait(timeout=5)
            assert client.post('/process', files={'file': ('b.mov', b'clip')}).status_code == 429
            assert client.get('/health').status_code == 200
        finally:
            finish.set()
        assert first.result(timeout=5).status_code == 201
        assert client.post('/process', files={'file': ('c.mov', b'clip')}).status_code == 201
        assert client.post('/process', files={'file': ('empty.mov', b'')}).status_code == 422
        assert client.post('/process', files={'file': ('d.mov', b'clip')}).status_code == 201
