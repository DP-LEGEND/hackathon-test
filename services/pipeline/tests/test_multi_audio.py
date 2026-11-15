"""Real-time sync and contact markers for the additive multi-upload endpoint."""
from pathlib import Path
import wave

import numpy as np
import pytest

from pipeline import multi_audio
from pipeline.segment import audio_hits
from pipeline.video import VideoInfo


def info(slowdown=1, duration=4, edits=None):
    return VideoInfo(30, 30, duration, 30 * slowdown, slowdown, 'manual', edits or [])


def decoded_audio(monkeypatch, peaks_a, peaks_b, energy_a=None, energy_b=None):
    calls = []

    def extract(clip, video_info, wav):
        calls.append(clip.name)
        if clip.name == 'a.mov':
            return np.asarray(peaks_a, dtype=float), np.asarray(energy_a or [1] * len(peaks_a), dtype=float)
        return np.asarray(peaks_b, dtype=float), np.asarray(energy_b or [1] * len(peaks_b), dtype=float)

    monkeypatch.setattr(multi_audio, '_extract_hits', extract)
    return calls


def test_one_hit_per_camera_syncs_with_correct_offset_sign(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [1.25], [1.75])
    offset, markers, sync = multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)
    assert offset == .5  # B time = A time + .5
    assert sync['method'] == 'audio-hit-peaks' and sync['matchedAudioHits'] == 1
    assert sync['offsetBRealSeconds'] == .5
    assert markers.is_file()
    np.testing.assert_allclose(audio_hits(str(markers), rise_db=25), [1.25], atol=.0051)


def test_shared_nonuniform_hit_pattern_handles_cropped_leading_event(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [.3, .8, 1.6, 2.9], [.6, 1.4, 2.7])
    offset, _, sync = multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)
    assert offset == pytest.approx(-.2)
    assert sync['matchedAudioHits'] == 3
    assert sync['audioResidualMs'] == pytest.approx(0)


def test_ambiguous_repeated_hits_do_not_silently_pick_an_offset(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [.5, 1.5], [.5, 1.5, 2.5])
    with pytest.raises(ValueError, match='ambiguous'):
        multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)


def test_dominant_ball_hit_beats_unpaired_transient_noise(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [.5, 1.5], [.25, 1.75, 3], [1, 10], [1, 10, 1])
    offset, _, sync = multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)
    assert offset == .25 and sync['matchedAudioHits'] == 1


@pytest.mark.parametrize('peaks_a,peaks_b', [([], []), ([1], []), ([], [1])])
def test_missing_peaks_require_manual_offset(tmp_path, monkeypatch, peaks_a, peaks_b):
    decoded_audio(monkeypatch, peaks_a, peaks_b)
    with pytest.raises(ValueError, match='provide offset_b_s'):
        multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)


def test_explicit_offset_bypasses_b_audio_and_maps_b_slowdown(tmp_path, monkeypatch):
    calls = decoded_audio(monkeypatch, [.6], [])
    offset, markers, sync = multi_audio.prepare_audio(
        Path('a.mov'), Path('b.mov'), info(4, 12), info(2, 8), tmp_path, offset_b_s=-1.5)
    assert calls == ['a.mov']
    assert offset == -.75
    assert sync['offsetBPlaybackSeconds'] == -1.5
    assert sync['method'] == 'provided-offset' and markers is not None


def test_explicit_offset_still_works_without_any_audio(tmp_path, monkeypatch):
    calls = []

    def missing_audio(clip, *_):
        calls.append(clip.name)
        raise ValueError('No audio stream')

    monkeypatch.setattr(multi_audio, '_extract_hits', missing_audio)
    offset, markers, sync = multi_audio.prepare_audio(
        Path('a.mov'), Path('b.mov'), info(), info(), tmp_path, offset_b_s=.7)
    assert calls == ['a.mov'] and offset == .7 and markers is None
    assert sync['warnings'] and 'wrist-speed' in sync['warnings'][0]


def test_explicit_offset_piecewise_mapping_and_negative_extrapolation():
    movie = info(duration=10, edits=[
        {'playbackStart': 0, 'playbackEnd': 1, 'mediaStart': 0, 'rate': 1},
        {'playbackStart': 1, 'playbackEnd': 9, 'mediaStart': 1, 'rate': .25},
        {'playbackStart': 9, 'playbackEnd': 10, 'mediaStart': 3, 'rate': 1},
    ])
    assert multi_audio.playback_offset_to_real(movie, -2) == -2
    assert multi_audio.playback_offset_to_real(movie, 5) == 2
    assert multi_audio.playback_offset_to_real(movie, 11) == 5


def test_explicit_offset_rejects_nonfinite_and_unmapped_edit_gap():
    movie = info(edits=[
        {'playbackStart': 0, 'playbackEnd': 1, 'mediaStart': 0, 'rate': 1},
        {'playbackStart': 2, 'playbackEnd': 3, 'mediaStart': 1, 'rate': 1},
    ])
    with pytest.raises(ValueError, match='gap'):
        multi_audio.playback_offset_to_real(movie, 1.5)
    for offset in (float('nan'), float('inf')):
        with pytest.raises(ValueError, match='finite'):
            multi_audio.playback_offset_to_real(movie, offset)


def test_real_contact_markers_survive_the_existing_detector(tmp_path):
    hits = np.array([.615, 1.2, 2.505])
    path = multi_audio._write_markers(tmp_path / 'markers.wav', hits, 3)
    with wave.open(str(path), 'rb') as stream:
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        assert stream.getframerate() == 16_000 and stream.getnframes() <= 3 * 16_000 + 1
    np.testing.assert_allclose(audio_hits(str(path), rise_db=25), hits, atol=.0051)


def test_decoded_original_hits_map_to_normalized_seconds_and_cleanup(tmp_path, monkeypatch):
    commands = []

    def ffmpeg(arguments, **kwargs):
        commands.append(arguments)
        assert kwargs['timeout'] == 30
        destination = Path(arguments[-1])
        hits = np.array([2.4, 4.8]) if destination.name == 'audio-a.wav' else np.array([1.7, 2.3])
        multi_audio._write_markers(destination, hits, 6)
        return ''

    monkeypatch.setattr(multi_audio, 'run_tool', ffmpeg)
    offset, markers, sync = multi_audio.prepare_audio(
        Path('a.mov'), Path('b.mov'), info(4, 6), info(1, 6), tmp_path)
    assert offset == pytest.approx(1.1, abs=.006)
    assert len(commands) == 2 and all('file,pipe' in args and 'mov,avi' in args for args in commands)
    assert not (tmp_path / 'audio-a.wav').exists() and not (tmp_path / 'audio-b.wav').exists()
    np.testing.assert_allclose(audio_hits(str(markers), rise_db=25), [.6, 1.2], atol=.0051)
    assert sync['matchedAudioHits'] == 2


def test_automatic_missing_audio_is_a_controlled_sync_error(tmp_path, monkeypatch):
    def missing(*_):
        raise RuntimeError('ffmpeg unavailable')

    monkeypatch.setattr(multi_audio, '_extract_hits', missing)
    with pytest.raises(ValueError, match='Camera A has no usable'):
        multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)


def test_clip_duration_is_bounded_before_audio_decode(tmp_path, monkeypatch):
    def forbidden(*_):
        pytest.fail('oversized duration reached audio extraction')

    monkeypatch.setattr(multi_audio, '_extract_hits', forbidden)
    with pytest.raises(ValueError, match='30 real seconds'):
        multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(duration=31), info(), tmp_path)
