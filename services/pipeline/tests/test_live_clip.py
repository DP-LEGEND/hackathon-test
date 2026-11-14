"""Live auto-detection contracts and a generated short-video integration test."""
import json
import os
from pathlib import Path
import struct

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from pipeline.live import LiveOptions, process_live_clip, playback_hits_to_real
from pipeline.process import Options, classify_side, swings_from_raw
from pipeline.server import app
from pipeline.video import VideoInfo, probe_video, quicktime_edits, timing_at
from pipeline.tests.test_stereo_cli import stereo_pair


def probe_payload(fps='60/1', base='60/1', tags=None):
    return {'streams': [{'codec_type': 'video', 'avg_frame_rate': fps, 'r_frame_rate': base,
                         'width': 640, 'height': 480, 'duration': '2', 'tags': tags or {}}]}


def metadata_file(tmp_path, monkeypatch, payload):
    import pipeline.video as video
    clip = tmp_path / 'clip.avi'
    clip.write_bytes(b'probe fixture')
    monkeypatch.setattr(video, 'run_tool', lambda *args, **kwargs: json.dumps(payload))
    return clip


def test_auto_normal_60fps_is_not_slow_motion(tmp_path, monkeypatch):
    clip = metadata_file(tmp_path, monkeypatch, probe_payload())
    info = probe_video(clip)
    assert info.slowdown == 1 and info.capture_fps == 60


def test_vfr_base_rate_is_not_a_capture_rate(tmp_path, monkeypatch):
    clip = metadata_file(tmp_path, monkeypatch, probe_payload('60/1', '120/1'))
    assert probe_video(clip).slowdown == 1


def test_auto_capture_rate_tag_and_manual_override(tmp_path, monkeypatch):
    clip = metadata_file(tmp_path, monkeypatch, probe_payload('30/1', '30/1',
        {'com.apple.quicktime.capture.fps': '240'}))
    automatic = probe_video(clip)
    assert automatic.slowdown == 8 and automatic.capture_fps == 240
    manual = probe_video(clip, slowdown=2)
    assert manual.source == 'manual' and manual.slowdown == 2 and manual.capture_fps == 60


def atom(name, payload):
    return struct.pack('>I4s', len(payload) + 8, name) + payload


def movie_with_edits(version=0):
    header = b'\0' * 12 + struct.pack('>II', 1000, 10000) + b'\0' * 4
    edits = b'\x01\0\0\0' if version else b'\0' * 4
    edits += struct.pack('>I', 3)
    fmt = '>Qqi' if version else '>Iii'
    for duration, start, rate in ((1000, 0, 65536), (8000, 1000, 16384), (1000, 3000, 65536)):
        edits += struct.pack(fmt, duration, start, rate)
    media = atom(b'mdia', atom(b'hdlr', b'\0' * 8 + b'vide') + atom(b'mdhd', header))
    track = atom(b'trak', media + atom(b'edts', atom(b'elst', edits)))
    return atom(b'moov', atom(b'mvhd', header) + track)


@pytest.mark.parametrize('version', [0, 1])
def test_auto_quicktime_piecewise_edit_mapping(tmp_path, monkeypatch, version):
    import pipeline.video as video
    clip = tmp_path / 'clip.mov'
    clip.write_bytes(movie_with_edits(version))
    def probe(arguments, **kwargs):
        if '-ignore_editlist' in arguments:
            return json.dumps({'streams': [{'avg_frame_rate': '120/1', 'duration': '4'}]})
        return json.dumps(probe_payload('30/1', '120/1'))
    monkeypatch.setattr(video, 'run_tool', probe)
    assert [edit['rate'] for edit in quicktime_edits(clip)] == [1, .25, 1]
    info = probe_video(clip)
    assert info.capture_fps == 120 and info.source == 'quicktime-edit-list'
    assert timing_at(info, .5) == (.5, 1)
    assert timing_at(info, 2) == (5, 4)
    assert timing_at(info, 3.5) == (9.5, 1)
    np.testing.assert_allclose(playback_hits_to_real(info, np.array([.5, 5, 9.5])), [.5, 2, 3.5])


def test_single_camera_auto_hand_and_estimated_depth(stereo_pair):
    a, _, *_ = stereo_pair
    for key in ('img', 'world', 'vis'):
        a[key][:, [11, 13, 15, 12, 14, 16]] = a[key][:, [12, 14, 16, 11, 13, 15]]
    swings, report = swings_from_raw(a)
    assert report['written'] == 2
    assert all(swing['metadata']['hand'] == 'L' and swing['metadata']['handSource'] == 'auto'
               and swing['metadata']['depth'] == 'estimated' for swing in swings)
    for swing in swings:
        json.dumps(swing, allow_nan=False)
        assert len(swing['frames'][0]['joints']) == 33


@pytest.mark.parametrize('hand', ['L', 'R'])
@pytest.mark.parametrize('stroke', ['forehand', 'backhand'])
def test_auto_stroke_is_relative_to_the_body_not_camera_axes(hand, stroke):
    world = np.zeros((5, 33, 3))
    world[:, 11] = [-.2, .5, 0]
    world[:, 12] = [.2, .5, 0]
    world[:, 23] = [-.1, 0, 0]
    world[:, 24] = [.1, 0, 0]
    sign = (1 if hand == 'R' else -1) * (1 if stroke == 'forehand' else -1)
    world[:, 16 if hand == 'R' else 15] = [.4 * sign, .2, 0]
    rotation = cv2.Rodrigues(np.array([.3, 1.1, -.2]))[0]
    assert classify_side(world @ rotation.T, 2, hand) == stroke


def test_manual_hand_stroke_and_sound_free_contact(stereo_pair):
    a, _, *_ = stereo_pair
    swings, _ = swings_from_raw(a, options=Options(hand='R', side='backhand', tap_filter=True))
    assert swings
    for swing in swings:
        meta = swing['metadata']
        assert meta['hand'] == 'R' and meta['handSource'] == 'manual'
        assert meta['stroke'] == 'backhand' and meta['strokeSource'] == 'manual'
        assert meta['contactMethod'] == 'wrist-speed-peak-estimate'
        assert swing['contactFrame'] >= 0


def test_process_upload_overrides_and_error_states(tmp_path, monkeypatch):
    import pipeline.server as server
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path / 'out'))
    calls = []
    def process(clip, output, options):
        assert clip.read_bytes() == b'video bytes'
        calls.append(options)
        return {'swingId': 'new-swing', 'coach': {}, 'compare': {}}
    monkeypatch.setattr(server, 'process_live_clip', process)
    client = TestClient(app)
    response = client.post('/process', files={'file': ('clip.mov', b'video bytes', 'video/quicktime')},
                           data={'slowdown': '4', 'hand': 'L', 'stroke': 'backhand'})
    assert response.status_code == 201 and response.json()['swingId'] == 'new-swing'
    assert calls[0].slowdown == 4 and calls[0].hand == 'L' and calls[0].stroke == 'backhand'
    assert client.post('/process', files={'file': ('clip.mov', b'')}).status_code == 422
    for override in ({'slowdown': 'nan'}, {'slowdown': '0'}, {'hand': 'X'}, {'stroke': 'lob'}):
        assert client.post('/process', files={'file': ('clip.mov', b'bytes')}, data=override).status_code == 422
    monkeypatch.setattr(server, 'process_live_clip', lambda *args: (_ for _ in ()).throw(RuntimeError('setup')))
    assert client.post('/process', files={'file': ('clip.mov', b'bytes')}).status_code == 503


def test_real_model_rejects_rotating_photo_as_non_swing(tmp_path, monkeypatch):
    """Optional real decoder + MediaPipe integration on a generated image-motion clip.

    GHOST_LIVE_TEST_IMAGE is the official MediaPipe pose.jpg fixture. The clip is
    synthetic global rotation, not a validated squash swing. Nothing is mocked.
    """
    image_path = os.environ.get('GHOST_LIVE_TEST_IMAGE')
    model_path = os.environ.get('GHOST_POSE_MODEL')
    if not image_path or not model_path:
        pytest.skip('Set GHOST_LIVE_TEST_IMAGE and GHOST_POSE_MODEL for real-model video integration')
    image = cv2.imread(image_path)
    assert image is not None
    image = cv2.resize(image, (640, 426))
    clip = tmp_path / 'short.avi'
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*'MJPG'), 60, (640, 426))
    assert writer.isOpened()
    for i in range(150):
        seconds = i / 60
        angle = 40 * np.tanh((seconds - 1.2) / .045)
        matrix = cv2.getRotationMatrix2D((320, 213), angle, .8)
        writer.write(cv2.warpAffine(image, matrix, (640, 426)))
    writer.release()
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path / 'processed'))
    response = TestClient(app).post('/process', files={'file': ('short.avi', clip.read_bytes(), 'video/x-msvideo')})
    assert response.status_code == 422, response.text
    assert 'No fully tracked swing' in response.json()['detail']
    assert TestClient(app).get('/swings').json() == {'swings': []}
    assert not list((tmp_path / 'processed').glob('*/manifest.json'))

def test_end_to_end_short_clip_with_real_model(tmp_path, monkeypatch):
    """Optional real decoder + MediaPipe end-to-end success on a real swing.

    GHOST_LIVE_TEST_CLIP is a short real-time clip of one real squash swing
    (kept outside the repo; e.g. a 4 s real-time cut of a forehand). Nothing is
    mocked: decode, pose, swing gate, coach and ghost all run.
    """
    clip_path = os.environ.get('GHOST_LIVE_TEST_CLIP')
    model_path = os.environ.get('GHOST_POSE_MODEL')
    if not clip_path or not model_path:
        pytest.skip('Set GHOST_LIVE_TEST_CLIP and GHOST_POSE_MODEL for real-model swing integration')
    clip = Path(clip_path)
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path / 'processed'))
    client = TestClient(app)
    response = client.post('/process', files={'file': (clip.name, clip.read_bytes(), 'video/mp4')})
    assert response.status_code == 201, response.text
    result = response.json()
    swing_id = result['swingId']
    swing = client.get(f'/swings/{swing_id}').json()
    assert swing['metadata']['slowdown'] == 1 and swing['metadata']['slowdownSource'] == 'auto'
    assert swing['metadata']['depth'] == 'estimated'
    assert swing['metadata']['backswingVerified']
    assert swing['metadata']['hand'] in ('L', 'R') and swing['metadata']['stroke'] in ('forehand', 'backhand')
    assert result['coach']['metrics']['hand'] == swing['metadata']['hand']
    assert result['compare']['you']['ball']['label'] == 'PREDICTED'
    assert result['compare']['ghost']['ball']['label'] == 'PREDICTED'
    assert any(row['id'] == swing_id for row in client.get('/swings').json()['swings'])
    json.dumps(result, allow_nan=False)


def test_manual_values_are_saved_through_coach_and_ghost(tmp_path, monkeypatch, stereo_pair):
    import pipeline.live as live
    a, _, *_ = stereo_pair
    clip = tmp_path / 'clip.avi'
    clip.write_bytes(b'synthetic decoder fixture')
    model = tmp_path / 'pose.task'
    model.write_bytes(b'injected model')
    monkeypatch.setattr(live, 'probe_video', lambda *args: VideoInfo(60, 60, 4, 120, 2, 'manual', []))
    monkeypatch.setattr(live, 'normalize_video', lambda source, dest, info: dest.write_bytes(b'normalized'))
    monkeypatch.setattr(live, 'extract_raw', lambda *args, **kwargs: a)
    monkeypatch.setattr(live, 'run_tool', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('no audio')))
    output = tmp_path / 'output'
    result = process_live_clip(clip, output, LiveOptions(slowdown=2, hand='R', stroke='backhand', model_path=str(model)))
    swing = json.loads((output / f"{result['swingId']}.json").read_text())
    meta = swing['metadata']
    assert (meta['slowdown'], meta['hand'], meta['stroke']) == (2, 'R', 'backhand')
    assert (meta['slowdownSource'], meta['handSource'], meta['strokeSource']) == ('manual',) * 3
    assert result['coach']['metrics']['hand'] == result['compare']['hand'] == 'R'
    assert (output / 'manifest.json').is_file()
    assert not list(output.glob('*.avi'))

def test_cli_one_clip_defaults_and_manual_precedence(tmp_path, monkeypatch):
    import pipeline.__main__ as cli
    calls = []
    monkeypatch.setenv('GHOST_SWINGS_DIR', str(tmp_path))
    def process(clip, output, options):
        calls.append((clip, output, options))
        return {'written': 1, 'detected': 1, 'rejected': [], 'swingId': 'ready'}
    monkeypatch.setattr(cli, 'process_live_clip', process)
    assert cli.main(['new.mov']) == 0
    assert calls[-1][1].parent == tmp_path
    assert (calls[-1][2].slowdown, calls[-1][2].hand, calls[-1][2].stroke) == (None, None, None)
    assert cli.main(['new.mov', '--out-dir', str(tmp_path / 'manual'), '--slowdown-a', '4',
                     '--slowdown', '1', '--hand', 'L', '--side', 'backhand', '--stroke', 'forehand']) == 0
    assert (calls[-1][2].slowdown, calls[-1][2].hand, calls[-1][2].stroke) == (1, 'L', 'forehand')


def test_auto_hand_is_resolved_per_window_not_per_session(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, _, *_ = stereo_pair
    # Move the whole articulated second swing to the left arm, not just its
    # image wrist: final admission now verifies physical 3D swing evidence.
    for key in ('img', 'world', 'vis'):
        a[key][120:, [11, 13, 15, 12, 14, 16]] = a[key][120:, [12, 14, 16, 11, 13, 15]]
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 24, 'end': 114, 'peak': 72, 'speed': 10},
        {'start': 132, 'end': 222, 'peak': 180, 'speed': 11}])
    swings, report = swings_from_raw(a)
    assert report['written'] == 2
    assert [s['metadata']['hand'] for s in swings] == ['R', 'L']


def test_audio_contact_outside_peak_window_is_retained(stereo_pair, monkeypatch):
    import pipeline.process as process
    a, _, *_ = stereo_pair
    a['audio_hits'] = np.array([1.05])
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 18, 'end': 114, 'peak': 72, 'speed': 10, 'hit': 1.05}])
    swings, _ = swings_from_raw(a, options=Options(hand='R'))
    assert swings[0]['metadata']['contactMethod'] == 'audio-transient'
    assert a['t'][swings[0]['metadata']['sourceContactFrame']] == pytest.approx(1.05)


@pytest.mark.parametrize('manual', [None, 4])
def test_real_decoder_undoes_piecewise_quicktime_edits(tmp_path, manual):
    """Generate a MOV, replace its edit list, and exercise actual ffprobe/ffmpeg."""
    import io
    from pipeline.video import _boxes, normalize_video, run_tool, tool
    if not os.environ.get('GHOST_FFMPEG') or not os.environ.get('GHOST_FFPROBE'):
        pytest.skip('Set GHOST_FFMPEG/GHOST_FFPROBE for real edit-list decoder integration')
    source = tmp_path / 'source.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 60, (64, 64))
    for index in range(120):
        writer.write(np.full((64, 64, 3), index * 2, dtype=np.uint8))
    writer.release()
    movie = tmp_path / 'source.mov'
    run_tool([tool('ffmpeg'), '-v', 'error', '-y', '-i', str(source), '-c:v', 'mpeg4', str(movie)])
    data = movie.read_bytes()
    def children(payload):
        stream = io.BytesIO(payload)
        return [(kind, payload[start:end]) for kind, start, end in _boxes(stream, 0, len(payload))]
    top = children(data)
    assert [kind for kind, _ in top].index(b'mdat') < [kind for kind, _ in top].index(b'moov')
    moov = next(payload for kind, payload in top if kind == b'moov')
    mvhd = next(payload for kind, payload in children(moov) if kind == b'mvhd')
    movie_scale = struct.unpack_from('>I', mvhd, 12)[0]
    trak = next(payload for kind, payload in children(moov) if kind == b'trak')
    mdia = next(payload for kind, payload in children(trak) if kind == b'mdia')
    mdhd = next(payload for kind, payload in children(mdia) if kind == b'mdhd')
    media_scale = struct.unpack_from('>I', mdhd, 12)[0]
    selected_edits = ((.5, 0, 1), (4, .5, .25), (.5, 1.5, 1)) if manual is None else ((1, .5, 1),)
    movie_duration = sum(edit[0] for edit in selected_edits)
    def transform(kind, payload):
        if kind in (b'moov', b'trak', b'edts'):
            payload = b''.join(transform(k, p) for k, p in children(payload))
        elif kind in (b'mvhd', b'tkhd'):
            mutable = bytearray(payload)
            struct.pack_into('>I', mutable, 16 if kind == b'mvhd' else 20, round(movie_duration * movie_scale))
            payload = bytes(mutable)
        elif kind == b'elst':
            payload = b'\0' * 4 + struct.pack('>I', len(selected_edits))
            for duration, start, speed in selected_edits:
                payload += struct.pack('>Iii', round(duration * movie_scale), round(start * media_scale), round(speed * 65536))
        return atom(kind, payload)
    movie.write_bytes(b''.join(transform(kind, payload) for kind, payload in top))
    info = probe_video(movie, slowdown=manual)
    assert info.slowdown == 4
    if manual is None:
        assert info.source == 'quicktime-edit-list'
        assert timing_at(info, 1) == (2.5, 4)
    else:
        assert info.source == 'manual' and info.ignore_edits and len(info.edits) == 1
        assert timing_at(info, .125) == (.5, 4)
    normalized = tmp_path / 'real.avi'
    normalize_video(movie, normalized, info)
    capture = cv2.VideoCapture(str(normalized))
    try:
        assert capture.get(cv2.CAP_PROP_FPS) == pytest.approx(60 if manual is None else 120)
        assert capture.get(cv2.CAP_PROP_FRAME_COUNT) == pytest.approx(120 if manual is None else 30, abs=2)
        if manual is not None:
            means = []
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                means.append(float(frame.mean()))
            # Input brightness encodes source frame index. Only the .5-1.5 s
            # source interval (roughly 60-180) may survive the manual slowdown.
            assert min(means) >= 50 and max(means) <= 190
    finally:
        capture.release()
