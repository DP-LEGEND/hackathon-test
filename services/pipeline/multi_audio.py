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
from pipeline.segment import audio_hits
from pipeline.video import VideoInfo, run_tool, tool


SAMPLE_RATE = 16_000
MATCH_TOLERANCE_S = .035
MAX_HITS = 128


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


def _extract_hits(clip: Path, info: VideoInfo, wav: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return normalized real hit times and local transient energy for ranking."""
    run_tool([tool('ffmpeg'), '-v', 'error', '-nostdin', '-y',
              '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,avi',
              '-i', str(clip.resolve()), '-map', '0:a:0', '-vn', '-ac', '1',
              '-ar', str(SAMPLE_RATE), '-c:a', 'pcm_s16le', '-t', '300', str(wav)], timeout=30)
    peaks = audio_hits(str(wav), rise_db=25)
    if len(peaks) > MAX_HITS:
        raise ValueError('Too many audio transients for a reliable two-camera sync')
    with wave.open(str(wav), 'rb') as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, SAMPLE_RATE):
            raise ValueError('Invalid decoded audio for two-camera sync')
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(float)
    times, strength = [], []
    duration = _duration(info)
    for peak in peaks:
        mapped = playback_hits_to_real(info, np.asarray([peak], dtype=float))
        if len(mapped) != 1 or not 0 <= mapped[0] < duration:
            continue
        # audio_hits supplies the band-pass/prominence gate. Energy only ranks
        # accepted transients; it cannot introduce an undetected loud sound.
        lo = max(0, int((peak - .01) * SAMPLE_RATE))
        hi = min(len(samples), int((peak + .025) * SAMPLE_RATE))
        if hi > lo:
            times.append(float(mapped[0]))
            strength.append(float(np.mean(samples[lo:hi] ** 2)))
    return np.asarray(times), np.asarray(strength)


def _dominant(strength: np.ndarray) -> int | None:
    if not len(strength):
        return None
    order = np.argsort(strength)
    if len(order) == 1 or strength[order[-1]] >= 4 * max(strength[order[-2]], 1):
        return int(order[-1])
    return None


def _match_hits(a: np.ndarray, b: np.ndarray, energy_a: np.ndarray,
                energy_b: np.ndarray) -> tuple[float, int, float]:
    """Prefer a unique shared transient pattern; isolated dominant peaks also work.

Regular/repeated patterns with equally good distinct alignments are rejected.
This avoids silently assuming zero or matching the first noise in each clip.
"""
    if not len(a) or not len(b):
        raise ValueError('No ball-hit audio peak found in both clips; provide offset_b_s')
    if len(a) == len(b) == 1:
        return float(b[0] - a[0]), 1, 0.0
    candidates = []
    for offset in np.unique(np.round((b[:, None] - a).ravel(), 4)):
        distance = abs(a[:, None] + offset - b)
        pairs = sorted((float(distance[i, j]), i, j)
                       for i, j in zip(*np.nonzero(distance <= MATCH_TOLERANCE_S)))
        used_a, used_b, differences = set(), set(), []
        for _, i, j in pairs:
            if i not in used_a and j not in used_b:
                used_a.add(i)
                used_b.add(j)
                differences.append(float(b[j] - a[i]))
        if not differences:
            continue
        refined = float(np.median(differences))
        residual = float(np.max(abs(np.asarray(differences) - refined)))
        candidates.append((len(differences), residual, refined))
    candidates.sort(key=lambda row: (-row[0], row[1], abs(row[2])))
    best = candidates[0]
    competitors = [row for row in candidates[1:] if abs(row[2] - best[2]) > 2 * MATCH_TOLERANCE_S]
    if (best[0] >= 2 and best[0] >= math.ceil(.6 * min(len(a), len(b)))
            and (not competitors or competitors[0][0] < best[0])):
        return best[2], best[0], best[1]
    strongest_a, strongest_b = _dominant(energy_a), _dominant(energy_b)
    if strongest_a is not None and strongest_b is not None:
        return float(b[strongest_b] - a[strongest_a]), 1, 0.0
    raise ValueError('Ball-hit audio sync is ambiguous; provide offset_b_s')


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
    duration_a, _ = _duration(info_a), _duration(info_b)
    work.mkdir(parents=True, exist_ok=True)
    wav_a, wav_b = work / 'audio-a.wav', work / 'audio-b.wav'
    warnings = []
    try:
        try:
            hits_a, energy_a = _extract_hits(clip_a, info_a, wav_a)
        except (ValueError, RuntimeError, OSError, wave.Error) as exc:
            if offset_b_s is None:
                raise ValueError('Camera A has no usable ball-hit audio; provide offset_b_s') from exc
            hits_a, energy_a = np.array([]), np.array([])
        if offset_b_s is not None:
            offset = playback_offset_to_real(info_b, offset_b_s)
            metadata = {'method': 'provided-offset', 'offsetBPlaybackSeconds': float(offset_b_s),
                        'matchedAudioHits': 0, 'audioResidualMs': None}
        else:
            try:
                hits_b, energy_b = _extract_hits(clip_b, info_b, wav_b)
            except (ValueError, RuntimeError, OSError, wave.Error) as exc:
                raise ValueError('Camera B has no usable ball-hit audio; provide offset_b_s') from exc
            offset, count, residual = _match_hits(hits_a, hits_b, energy_a, energy_b)
            metadata = {'method': 'audio-hit-peaks', 'matchedAudioHits': count,
                        'audioResidualMs': residual * 1000, 'audioHitsB': len(hits_b)}
        markers = _write_markers(work / 'audio-hit-markers-a.wav', hits_a, duration_a)
        if markers is None:
            warnings.append('Camera A audio is unavailable; contact timing uses the existing wrist-speed estimate.')
        metadata.update(offsetBRealSeconds=offset, audioHitsA=len(hits_a),
                        contactAudio='detected-transient timing markers' if markers else None,
                        warnings=warnings)
        return offset, markers, metadata
    finally:
        for path in (wav_a, wav_b):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # The caller also owns and removes the temporary directory.
