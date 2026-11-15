"""Local multi-upload clocks: different edit switches and inferred flat renders."""
from dataclasses import replace
import json
import shutil

import cv2
import numpy as np
import pytest

from pipeline.live import playback_hits_to_real
from pipeline.multi_timing import (INFERRED_SOURCE, infer_local_timing, local_timing_at,
                                   normalize_multi_video, probe_multi_video, timing_debug)
from pipeline.video import VideoInfo, tool


def edited(switch, end=12):
    return VideoInfo(120, 120, switch + (end - switch) * 4, 120, 4,
                     'quicktime-edit-list', [
        {'playbackStart': 0., 'playbackEnd': switch, 'mediaStart': 0., 'rate': 1.},
        {'playbackStart': switch, 'playbackEnd': switch + (end - switch) * 4,
         'mediaStart': switch, 'rate': .25}], ignore_edits=True)


def test_independent_mid_clip_switches_keep_sequence_offset():
    a, b = edited(4), edited(8)
    swings_a = np.array([2., 6., 11.])
    swings_b = swings_a + .7
    debug_a = timing_debug(a, swings_a)
    debug_b = timing_debug(b, swings_b)
    assert [row['slowdown'] for row in debug_a] == [1, 4, 4]
    assert [row['slowdown'] for row in debug_b] == [1, 1, 4]
    playback_a = np.array([row['playbackSeconds'] for row in debug_a])
    playback_b = np.array([row['playbackSeconds'] for row in debug_b])
    real_a = playback_hits_to_real(a, playback_a)
    real_b = playback_hits_to_real(b, playback_b)
    assert real_b - real_a == pytest.approx([.7, .7, .7])
    assert not np.allclose(playback_b - playback_a, .7)
    assert local_timing_at(a, 4) == (4, 4), 'the new rate owns the exact switch boundary'


def test_native_local_edits_precede_global_airdrop_hint(tmp_path, monkeypatch):
    import pipeline.video as video
    clip = tmp_path / 'clip.mov'
    clip.write_bytes(b'probe fixture')
    expected = edited(4)
    monkeypatch.setattr(video, 'quicktime_edits', lambda path: expected.edits)

    def probe(arguments, **kwargs):
        if '-ignore_editlist' in arguments:
            return json.dumps({'streams': [{'avg_frame_rate': '120/1', 'duration': '12'}]})
        return json.dumps({'streams': [{'codec_type': 'video', 'avg_frame_rate': '30/1',
            'r_frame_rate': '120/1', 'width': 640, 'height': 480, 'duration': '36',
            'tags': {'com.apple.quicktime.full-frame-rate-playback-intent': '1'}}]})

    monkeypatch.setattr(video, 'run_tool', probe)
    info = probe_multi_video(clip)
    assert info.source == 'quicktime-edit-list'
    assert [row['slowdown'] for row in timing_debug(info, [2, 6, 11])] == [1, 4, 4]


def flat_motion():
    playback = np.arange(0, 18, 1 / 30)
    speed = np.zeros(len(playback))
    centers = [2., 9., 16.]
    for center, factor in zip(centers, [1, 4, 4]):
        speed[np.abs(playback - center) <= .45] = 23.5 / factor
    world = np.zeros((len(playback), 33, 3))
    world[:, 16, 0] = np.cumsum(speed) / 30
    raw = {'t': playback / 4, 'fps': 120., 'world': world,
           'vis': np.ones((len(playback), 33))}
    info = VideoInfo(30, 30, 18, 120, 4, 'playback-intent', [])
    return raw, info, centers


def test_local_wrist_speed_recovers_normal_then_four_times_slow():
    raw, initial, centers = flat_motion()
    inferred, debug = infer_local_timing(raw, initial, centers)
    assert inferred.source == INFERRED_SOURCE
    assert inferred.capture_fps == inferred.fps
    assert [row['slowdown'] for row in debug['swings']] == [1, 4, 4]
    assert debug['transitionTimesMeasured'] is False
    assert debug['transitionPlaybackSeconds'] == [5.5, 12.5]
    assert 'midpoints' in debug['warnings'][0]
    real = playback_hits_to_real(inferred, np.array(centers))
    assert real == pytest.approx([2, 6.375, 8.125])
    assert [row['slowdown'] for row in timing_debug(inferred, real)] == [1, 4, 4]
    assert [row['playbackSeconds'] for row in timing_debug(inferred, real)] == pytest.approx(centers)
    json.dumps(debug, allow_nan=False)


@pytest.mark.parametrize('manual', [False, True])
def test_reliable_timing_is_not_replaced_by_motion_heuristic(manual):
    raw, _, centers = flat_motion()
    info = replace(edited(4), source='manual') if manual else edited(4)
    inferred, debug = infer_local_timing(raw, info, centers)
    assert inferred is info
    assert debug['method'] == 'native-clock'


def test_untracked_motion_retains_initial_timing_and_explains_uncertainty():
    raw, info, centers = flat_motion()
    raw['vis'][:] = 0
    inferred, debug = infer_local_timing(raw, info, centers)
    assert inferred is info
    assert all(row['inferred'] is False for row in debug['swings'])
    assert all(row['wristSpeedPerPlaybackSecond'] is None for row in debug['swings'])


def test_inferred_normalization_uses_full_source_intervals(tmp_path, monkeypatch):
    import pipeline.multi_timing as timing
    raw, initial, centers = flat_motion()
    info, _ = infer_local_timing(raw, initial, centers)
    calls = []
    monkeypatch.setattr(timing, 'run_tool', lambda arguments, **kwargs: calls.append(arguments))
    normalize_multi_video(tmp_path / 'source.mov', tmp_path / 'normalized.avi', info)
    args = calls[0]
    filters = args[args.index('-filter_complex') + 1]
    assert 'trim=start=0.0:end=5.5,setpts=(PTS-STARTPTS)*1.0' in filters
    assert 'trim=start=5.5:end=12.5,setpts=(PTS-STARTPTS)*0.25' in filters
    assert 'trim=start=12.5:end=18.0,setpts=(PTS-STARTPTS)*0.25' in filters
    assert float(args[args.index('-t') + 1]) == pytest.approx(8.625)
    assert float(args[args.index('-r') + 1]) == 120


def test_native_normalization_keeps_existing_decoder(tmp_path, monkeypatch):
    import pipeline.multi_timing as timing
    calls = []
    monkeypatch.setattr(timing, 'normalize_video', lambda *args: calls.append(args))
    info = edited(4)
    normalize_multi_video(tmp_path / 'a.mov', tmp_path / 'a.avi', info)
    assert calls[0][2] is info


def test_real_decoder_preserves_all_intervals_at_inferred_local_rates(tmp_path):
    if shutil.which(tool('ffmpeg')) is None:
        pytest.skip('ffmpeg needed for generated local-rate normalization')
    raw, initial, centers = flat_motion()
    info, _ = infer_local_timing(raw, initial, centers)
    source, output = tmp_path / 'source.avi', tmp_path / 'real.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 30, (64, 64))
    assert writer.isOpened()
    for frame in range(18 * 30):
        seconds = frame / 30
        level = 80 if seconds < 5.5 else 150 if seconds < 12.5 else 220
        writer.write(np.full((64, 64, 3), level, dtype=np.uint8))
    writer.release()
    normalize_multi_video(source, output, info)
    capture = cv2.VideoCapture(str(output))
    try:
        assert capture.get(cv2.CAP_PROP_FPS) == 120
        assert capture.get(cv2.CAP_PROP_FRAME_COUNT) == pytest.approx(8.625 * 120, abs=4)
        for seconds, expected in [(1, 80), (5, 80), (6, 150), (8, 220)]:
            capture.set(cv2.CAP_PROP_POS_FRAMES, seconds * 120)
            ok, frame = capture.read()
            assert ok and float(frame.mean()) == pytest.approx(expected, abs=3)
    finally:
        capture.release()
