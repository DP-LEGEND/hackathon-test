"""Real-time sync and contact markers for the additive multi-upload endpoint."""
from pathlib import Path
import wave

import numpy as np
import pytest

from pipeline import multi_audio
from pipeline.segment import audio_hits
from pipeline.video import VideoInfo
from pipeline.video import timing_at


def info(slowdown=1, duration=20, edits=None):
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


def test_sequence_syncs_with_correct_offset_sign(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [1.25, 4.25, 8.25], [1.75, 4.75, 8.75])
    offset, markers, sync = multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)
    assert offset == .5  # B time = A time + .5
    assert sync['method'] == 'audio-swing-sequence' and sync['matchedAudioHits'] == 3
    assert sync['offsetBRealSeconds'] == .5
    assert markers.is_file()
    np.testing.assert_allclose(audio_hits(str(markers), rise_db=25), [1.25, 4.25, 8.25], atol=.0051)


def test_shared_nonuniform_hit_pattern_handles_cropped_leading_event(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [1, 4, 8, 13], [3.8, 7.8, 12.8])
    offset, _, sync = multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)
    assert offset == pytest.approx(-.2)
    assert sync['matchedAudioHits'] == 3
    assert sync['audioResidualMs'] == pytest.approx(0)


def test_ambiguous_repeated_hits_do_not_silently_pick_an_offset(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [1, 4, 7], [1, 4, 7, 10])
    with pytest.raises(multi_audio.SyncError, match='ambiguous') as failed:
        multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)
    assert failed.value.debug['audioSwingTimesA'] == [1, 4, 7]
    assert failed.value.debug['audioSwingTimesB'] == [1, 4, 7, 10]
    assert failed.value.debug['offsetBRealSeconds'] is None


def test_single_loud_peak_cannot_override_missing_sequence(tmp_path, monkeypatch):
    decoded_audio(monkeypatch, [1.5], [1.75], [10], [10])
    with pytest.raises(multi_audio.SyncError, match='at least 3'):
        multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), info(), info(), tmp_path)


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
        hits = np.array([4., 16., 32.]) if destination.name == 'audio-a.wav' else np.array([2.1, 5.1, 9.1])
        multi_audio._write_markers(destination, hits, 40)
        return ''

    monkeypatch.setattr(multi_audio, 'run_tool', ffmpeg)
    offset, markers, sync = multi_audio.prepare_audio(
        Path('a.mov'), Path('b.mov'), info(4, 40), info(1, 12), tmp_path)
    assert offset == pytest.approx(1.1, abs=.006)
    assert len(commands) == 2 and all('file,pipe' in args and 'mov,avi' in args for args in commands)
    assert not (tmp_path / 'audio-a.wav').exists() and not (tmp_path / 'audio-b.wav').exists()
    np.testing.assert_allclose(audio_hits(str(markers), rise_db=25), [1, 4, 8], atol=.0051)
    assert sync['matchedAudioHits'] == 3


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


def noisy_session_audio(path, movie, swing_times):
    """Generated audio, with feeds/pickups around every stronger swing."""
    rate = 16_000
    samples = np.random.default_rng(41).normal(0, 2, int(movie.duration * rate) + rate)
    burst = np.sin(2 * np.pi * 4000 * np.arange(80) / rate) * np.hanning(80)
    for number, when in enumerate(swing_times):
        for delta, amplitude in [(-.9, 1200), (-.25, 3500), (0, 18000 + number * 1000), (.5, 1800)]:
            playback, _ = timing_at(movie, when + delta)
            start = int(round(playback * rate))
            samples[start:start + len(burst)] += amplitude * burst
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(np.clip(samples, -32768, 32767).astype('<i2').tobytes())


def test_real_decoder_output_rejects_feeds_and_matches_swings_across_different_speed_switches(tmp_path, monkeypatch):
    a = info(duration=50, edits=[
        {'playbackStart': 0, 'playbackEnd': 5, 'mediaStart': 0, 'rate': 1},
        {'playbackStart': 5, 'playbackEnd': 45, 'mediaStart': 5, 'rate': .25},
        {'playbackStart': 45, 'playbackEnd': 50, 'mediaStart': 15, 'rate': 1},
    ])
    b = info(duration=46, edits=[
        {'playbackStart': 0, 'playbackEnd': 9, 'mediaStart': 0, 'rate': 1},
        {'playbackStart': 9, 'playbackEnd': 41, 'mediaStart': 9, 'rate': .25},
        {'playbackStart': 41, 'playbackEnd': 46, 'mediaStart': 17, 'rate': 1},
    ])
    swings = np.array([3., 7., 12., 18.])

    def ffmpeg(arguments, **kwargs):
        path = Path(arguments[-1])
        movie, hits = (a, swings) if path.name == 'audio-a.wav' else (b, swings + .6)
        noisy_session_audio(path, movie, hits)
        return ''

    monkeypatch.setattr(multi_audio, 'run_tool', ffmpeg)
    offset, markers, sync = multi_audio.prepare_audio(Path('a.mov'), Path('b.mov'), a, b, tmp_path)
    assert offset == pytest.approx(.6, abs=.006)
    assert sync['matchedAudioHits'] == 4
    assert sync['audioSwingTimesA'] == pytest.approx(swings, abs=.006)
    assert sync['audioSwingTimesB'] == pytest.approx(swings + .6, abs=.006)
    assert sync['audioSwingPlaybackTimesA'] == pytest.approx([3, 13, 33, 48], abs=.006)
    assert sync['audioSwingSlowdownsA'] == [1, 4, 4, 1]
    assert sync['audioSwingSlowdownsB'] == [1, 1, 4, 1]
    assert sync['sequencePairs'] == [[0, 0], [1, 1], [2, 2], [3, 3]]
    assert audio_hits(str(markers), rise_db=25) == pytest.approx(swings, abs=.006)


def test_playback_peak_helper_is_provisional_before_real_clock_selection(tmp_path, monkeypatch):
    times = np.array([1., 2., 4., 7.])
    amplitudes = np.array([1., 10., 11., 12.])
    monkeypatch.setattr(multi_audio, '_decode_candidates', lambda *args: (times, amplitudes))
    playback, _ = multi_audio.extract_playback_peaks(Path('a.mov'), tmp_path / 'audio.wav')
    assert playback == pytest.approx([2, 4, 7])
