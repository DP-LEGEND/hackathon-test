"""Audio timing for the opt-in multi-upload path; existing live processing is untouched.

Both videos are normalized to real time before stereo extraction. The returned
WAV contains synthetic timing markers at *detected* camera-A audio transients,
not recorded/reconstructed sound. It only feeds process_clips' existing contact
detector and is never published or played to the user.
"""
from __future__ import annotations

import math
from pathlib import Path
import wave

import numpy as np

from pipeline.live import playback_hits_to_real
from pipeline.multi_sync import match_sequence, select_swing_peaks
from pipeline.segment import audio_hits
from pipeline.video import VideoInfo, run_tool, timing_at, tool


SAMPLE_RATE = 16_000
MAX_HITS = 128
MAX_CANDIDATE_HITS = 8192


class SyncError(ValueError):
    """A controlled multi-upload sync failure retaining its timing evidence."""
    def __init__(self, message: str, debug: dict):
        super().__init__(message)
        self.debug = debug


def _duration(info: VideoInfo) -> float:
    factor = info.capture_fps / info.fps
    duration = (sum((e['playbackEnd'] - e['playbackStart']) * e['rate'] for e in info.edits)
                if info.edits else info.duration) / factor
    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError('Multi-upload clips must be at most 30 real seconds')
    return duration


def playback_offset_to_real(info: VideoInfo, seconds: float) -> float:
    """B playback seconds at A's beginning -> B's normalized real-time clock.

An explicit offset may be negative or beyond B's end. Extrapolate using the
first/last local rate, matching the existing stereo Timeline convention. A gap
between edit segments has no video evidence and cannot define a sync point.
"""
    if not math.isfinite(seconds):
        raise ValueError('offset_b_s must be finite')
    factor = info.capture_fps / info.fps
    if not info.edits:
        return seconds / factor
    first, last = info.edits[0], info.edits[-1]
    if seconds < first['playbackStart']:
        return (seconds - first['playbackStart']) * first['rate'] / factor
    elapsed = 0.0
    for edit in info.edits:
        if seconds < edit['playbackStart']:
            raise ValueError('offset_b_s falls in a gap in camera B playback')
        if seconds <= edit['playbackEnd']:
            return elapsed + (seconds - edit['playbackStart']) * edit['rate'] / factor
        elapsed += (edit['playbackEnd'] - edit['playbackStart']) * edit['rate'] / factor
    return elapsed + (seconds - last['playbackEnd']) * last['rate'] / factor


def _decode_candidates(clip: Path, wav: Path) -> tuple[np.ndarray, np.ndarray]:
    """Decode transient candidates once, preserving RMS amplitude for selection."""
    run_tool([tool('ffmpeg'), '-v', 'error', '-nostdin', '-y',
              '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,avi',
              '-i', str(clip.resolve()), '-map', '0:a:0', '-vn', '-ac', '1',
              '-ar', str(SAMPLE_RATE), '-c:a', 'pcm_s16le', '-t', '300', str(wav)], timeout=30)
    peaks = audio_hits(str(wav), min_gap_s=.04, rise_db=25)
    if len(peaks) > MAX_CANDIDATE_HITS:
        raise ValueError('Too many audio candidates for a reliable two-camera sync')
    with wave.open(str(wav), 'rb') as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, SAMPLE_RATE):
            raise ValueError('Invalid decoded audio for two-camera sync')
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(float)
    times, strength = [], []
    for peak in peaks:
        # audio_hits supplies the band-pass/prominence gate. Energy only ranks
        # accepted transients; it cannot introduce an undetected loud sound.
        lo = max(0, int((peak - .01) * SAMPLE_RATE))
        hi = min(len(samples), int((peak + .025) * SAMPLE_RATE))
        if hi > lo:
            times.append(float(peak))
            strength.append(float(np.sqrt(np.mean(samples[lo:hi] ** 2))))
    return np.asarray(times), np.asarray(strength)


def extract_playback_peaks(clip: Path, wav: Path) -> tuple[np.ndarray, np.ndarray]:
    """Provisional playback peaks for local-rate estimation before normalization.

    Final sync re-decodes all candidates and applies dominance in real seconds;
    this provisional clock never decides which events survive the final filter.
    The caller owns the temporary WAV and its cleanup.
    """
    return select_swing_peaks(*_decode_candidates(clip, wav))


def _extract_hits(clip: Path, info: VideoInfo, wav: Path) -> tuple[np.ndarray, np.ndarray]:
    """Dominant swings on the real clock, including per-edit slowdown changes."""
    playback, strength = _decode_candidates(clip, wav)
    duration = _duration(info)
    times, amplitudes = [], []
    for peak, amplitude in zip(playback, strength):
        mapped = playback_hits_to_real(info, np.asarray([peak], dtype=float))
        if len(mapped) == 1 and 0 <= mapped[0] < duration:
            times.append(float(mapped[0]))
            amplitudes.append(float(amplitude))
    times, amplitudes = select_swing_peaks(times, amplitudes)
    if len(times) > MAX_HITS:
        raise ValueError('Too many dominant audio swings for a reliable two-camera sync')
    return times, amplitudes


def _write_markers(path: Path, hits: np.ndarray, duration: float) -> Path | None:
    if not len(hits):
        return None
    samples = np.zeros(int(math.ceil(duration * SAMPLE_RATE)) + 1, dtype='<i2')
    # A short 4 kHz burst lies inside audio_hits' 1.5–7 kHz band. Its envelope
    # peaks in the original detector's 5 ms timing bin (within one bin).
    n = np.arange(SAMPLE_RATE // 200)
    marker = np.rint(24_000 * np.sin(2 * np.pi * 4000 * n / SAMPLE_RATE) * np.hanning(len(n))).astype('<i2')
    for hit in hits:
        start = max(0, int(round(float(hit) * SAMPLE_RATE)))
        stop = min(len(samples), start + len(marker))
        if stop > start:
            samples[start:stop] = marker[:stop - start]
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(samples.tobytes())
    return path


def prepare_audio(clip_a: Path, clip_b: Path, info_a: VideoInfo, info_b: VideoInfo,
                  work: Path, offset_b_s: float | None = None) -> tuple[float, Path | None, dict]:
    """Find sync for normalized stereo and preserve A's detected audio contacts.

An explicit offset is B *playback* seconds at the beginning of A, the existing
process.Options convention. Missing audio never blocks an explicit offset.
Automatic sync failures raise ValueError so the caller can warn and use mono.
"""
    work.mkdir(parents=True, exist_ok=True)
    wav_a, wav_b = work / 'audio-a.wav', work / 'audio-b.wav'
    warnings = []
    metadata = {'method': 'provided-offset' if offset_b_s is not None else 'audio-swing-sequence',
                'audioSwingTimesA': [], 'audioSwingTimesB': [],
                'audioSwingPlaybackTimesA': [], 'audioSwingPlaybackTimesB': [],
                'audioSwingSlowdownsA': [], 'audioSwingSlowdownsB': [],
                'audioPeakStrengthsA': [], 'audioPeakStrengthsB': [],
                'matchedAudioHits': 0, 'audioResidualMs': None,
                'offsetBRealSeconds': None, 'sequencePairs': []}

    def record(source: str, hits: np.ndarray, strength: np.ndarray, info: VideoInfo) -> None:
        local = [timing_at(info, float(hit)) for hit in hits]
        metadata.update({f'audioSwingTimes{source}': hits.tolist(),
                         f'audioSwingPlaybackTimes{source}': [p for p, _ in local],
                         f'audioSwingSlowdowns{source}': [factor for _, factor in local],
                         f'audioPeakStrengths{source}': strength.tolist(),
                         f'audioHits{source}': len(hits)})

    try:
        duration_a, _ = _duration(info_a), _duration(info_b)
        try:
            hits_a, energy_a = _extract_hits(clip_a, info_a, wav_a)
        except (ValueError, RuntimeError, OSError, wave.Error) as exc:
            if offset_b_s is None:
                raise ValueError('offset not found: Camera A has no usable ball-hit audio; provide offset_b_s') from exc
            hits_a, energy_a = np.array([]), np.array([])
        record('A', hits_a, energy_a, info_a)
        if offset_b_s is not None:
            offset = playback_offset_to_real(info_b, offset_b_s)
            metadata['offsetBPlaybackSeconds'] = float(offset_b_s)
        else:
            try:
                hits_b, energy_b = _extract_hits(clip_b, info_b, wav_b)
            except (ValueError, RuntimeError, OSError, wave.Error) as exc:
                raise ValueError('offset not found: Camera B has no usable ball-hit audio; provide offset_b_s') from exc
            record('B', hits_b, energy_b, info_b)
            alignment = match_sequence(hits_a, hits_b)
            offset = alignment['offsetSeconds']
            metadata.update(matchedAudioHits=alignment['matchedCount'],
                            audioResidualMs=alignment['residualMs'], sequencePairs=alignment['pairs'])
        markers = _write_markers(work / 'audio-hit-markers-a.wav', hits_a, duration_a)
        if markers is None:
            warnings.append('Camera A audio is unavailable; contact timing uses the existing wrist-speed estimate.')
        metadata.update(offsetBRealSeconds=offset, audioHitsA=len(hits_a),
                        contactAudio='detected-transient timing markers' if markers else None,
                        warnings=warnings)
        return offset, markers, metadata
    except ValueError as exc:
        metadata.update(error=str(exc), warnings=warnings)
        raise SyncError(str(exc), metadata) from exc
    finally:
        for path in (wav_a, wav_b):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # The caller also owns and removes the temporary directory.
