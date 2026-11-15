"""Local timing for multi uploads only; the original live clock is unchanged.

Native edit-rate metadata wins. A flattened clip has no recoverable capture clock
in its frame PTS; its per-swing wrist-speed estimates are explicitly heuristic.
Transitions between inferred rates are midpoint estimates, never measured edits.
"""
from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path

import numpy as np

from pipeline.video import VideoInfo, normalize_video, probe_video, run_tool, tool

INFERRED_SOURCE = 'local-speed-inference'


def probe_multi_video(path: Path, slowdown: float | None = None) -> VideoInfo:
    """Keep native per-edit clocks ahead of the global AirDrop hint."""
    return probe_video(path, slowdown)


def local_timing_at(info: VideoInfo, seconds: float) -> tuple[float, float]:
    """Map a normalized swing to its local playback clock, using half-open edits."""
    factor = info.capture_fps / info.fps
    if not info.edits:
        return seconds * factor, factor
    elapsed = 0.0
    for index, edit in enumerate(info.edits):
        duration = (edit['playbackEnd'] - edit['playbackStart']) * edit['rate'] / factor
        if seconds < elapsed + duration or index == len(info.edits) - 1:
            return edit['playbackStart'] + (seconds - elapsed) * factor / edit['rate'], factor / edit['rate']
        elapsed += duration
    raise ValueError('No local timing segment')


def timing_debug(info: VideoInfo, real_times) -> list[dict]:
    rows = []
    for value in real_times:
        seconds = float(value)
        if not math.isfinite(seconds):
            raise ValueError('Swing times must be finite')
        playback, factor = local_timing_at(info, seconds)
        rows.append({'realSeconds': seconds, 'playbackSeconds': float(playback),
                     'slowdown': float(factor), 'source': info.source,
                     'inferred': info.source in ('playback-intent', INFERRED_SOURCE)})
    return rows


def _wrist_speed(raw: dict, playback: np.ndarray, center: float) -> float | None:
    """Measured metres per playback second, around the selected loud swing."""
    world = np.asarray(raw['world'], dtype=float)
    visibility = np.asarray(raw['vis'], dtype=float)
    if len(playback) < 5 or world.shape != (len(playback), 33, 3):
        return None
    hips = (world[:, 23] + world[:, 24]) / 2
    values = []
    for elbow, wrist in ((13, 15), (14, 16)):
        points = world[:, wrist] - hips
        dt = np.diff(playback)
        observed = (visibility[:, [elbow, wrist, 23, 24]] >= .5).all(axis=1)
        valid = observed[1:] & observed[:-1] & (dt > 0) & np.isfinite(dt)
        valid &= np.isfinite(points[1:]).all(axis=1) & np.isfinite(points[:-1]).all(axis=1)
        near = np.abs((playback[1:] + playback[:-1]) / 2 - center) <= 1.2
        use = valid & near
        if use.sum() >= 5:
            speed = np.linalg.norm(np.diff(points, axis=0)[use], axis=1) / dt[use]
            # A percentile removes a single landmark jump without replacing the
            # measured world scale with torso-size or image-speed estimates.
            values.append(float(np.percentile(speed, 95)))
    return max(values) if values else None


def infer_local_timing(raw: dict, info: VideoInfo, swing_playback_times) -> tuple[VideoInfo, dict]:
    """Estimate each loud swing's 1/2/4/8 factor from local wrist motion.

    ``raw`` is extracted on ``info``'s initially normalized clock. Audio event
    times are source playback seconds. Native non-unit edit metadata and manual
    overrides are never replaced. If no plausible evidence exists, retain the
    initial clock and report that limitation rather than claiming a measurement.
    """
    centers = np.asarray(swing_playback_times, dtype=float)
    if centers.ndim != 1 or not np.isfinite(centers).all() or np.any(np.diff(centers) <= 0):
        raise ValueError('Chosen audio swing times must be finite and increasing')
    debug = {'method': 'native-clock', 'source': info.source, 'swings': [],
             'transitionTimesMeasured': info.source == 'quicktime-edit-list', 'warnings': []}
    if info.source == 'manual' or any(abs(edit['rate'] - 1) > 1e-6 for edit in info.edits):
        debug['reason'] = 'Manual timing or native local edit rates take precedence.'
        return info, debug
    if len(info.edits) > 1:
        debug['reason'] = 'Multiple trimmed media sections prevent a unique inferred playback clock.'
        debug['warnings'].append(debug['reason'])
        return info, debug
    if not len(centers):
        debug['reason'] = 'No chosen audio swings for local speed inference.'
        return info, debug
    playback = np.asarray([local_timing_at(info, float(t))[0] for t in raw['t']])
    initial = info.capture_fps / info.fps
    factors = []
    measured = 0
    for center in centers:
        speed = _wrist_speed(raw, playback, float(center))
        candidates = [(abs(speed * factor - 23.5), factor) for factor in (1., 2., 4., 8.)
                      if speed is not None and 12 <= speed * factor <= 35]
        factor = min(candidates)[1] if candidates else initial
        measured += bool(candidates)
        factors.append(factor)
        debug['swings'].append({'playbackSeconds': float(center), 'slowdown': float(factor),
                                'wristSpeedPerPlaybackSecond': speed,
                                'estimatedWristSpeedMs': speed * factor if speed is not None else None,
                                'inferred': bool(candidates),
                                'reason': '12–35 m/s wrist-speed heuristic nearest 23.5 m/s' if candidates
                                else 'No plausible wrist-speed candidate; retained initial timing.'})
    debug.update(method='local-wrist-speed', transitionTimesMeasured=False)
    if not measured or all(abs(factor - initial) < 1e-6 for factor in factors):
        debug['reason'] = 'Local estimates retain the initial clock.'
        return info, debug
    start = info.edits[0]['playbackStart'] if info.edits else 0.
    end = info.edits[-1]['playbackEnd'] if info.edits else info.duration
    if centers[0] < start or centers[-1] >= end:
        raise ValueError('Chosen swing is outside the source playback interval')
    boundaries = [start, *((centers[1:] + centers[:-1]) / 2).tolist(), end]
    media_start = info.edits[0]['mediaStart'] if info.edits else 0.
    edits = [{'playbackStart': float(lo), 'playbackEnd': float(hi),
              'mediaStart': media_start + float(lo) - start, 'rate': 1 / float(factor),
              'inferred': True}
             for lo, hi, factor in zip(boundaries[:-1], boundaries[1:], factors)]
    warning = ('Local slowdowns are inferred from wrist speed; speed-change boundaries are estimated '
               'midpoints between swings. Verify against the original capture/edit metadata.')
    debug.update(source=INFERRED_SOURCE, transitionPlaybackSeconds=boundaries[1:-1])
    debug['warnings'].append(warning)
    return replace(info, capture_fps=info.fps, slowdown=max(factors), source=INFERRED_SOURCE,
                   edits=edits, warning=warning), debug


def normalize_multi_video(source: Path, destination: Path, info: VideoInfo) -> None:
    """Decode inferred local rates without treating them as native QuickTime edits."""
    if info.source != INFERRED_SOURCE:
        normalize_video(source, destination, info)
        return
    duration = sum((edit['playbackEnd'] - edit['playbackStart']) * edit['rate'] for edit in info.edits)
    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ValueError('Multi-upload clips must be at most 30 real seconds')
    factors = [1 / edit['rate'] for edit in info.edits]
    fps = min(120., info.fps * max(factors))
    if not 0 < fps <= 480:
        raise ValueError('Unsupported local capture frame rate')
    arguments = [tool('ffmpeg'), '-v', 'error', '-nostdin', '-y']
    if info.ignore_edits:
        arguments += ['-ignore_editlist', '1']
    arguments += ['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,avi', '-i', str(source.resolve())]
    filters = []
    for index, edit in enumerate(info.edits):
        start = edit['mediaStart']
        end = start + edit['playbackEnd'] - edit['playbackStart']
        filters.append(f"[0:v:0]trim=start={start}:end={end},setpts=(PTS-STARTPTS)*{edit['rate']}[v{index}]")
    inputs = ''.join(f'[v{i}]' for i in range(len(info.edits)))
    scale = 'scale=trunc(iw*min(1\\,1280/iw)/2)*2:trunc(ih*min(1\\,1280/iw)/2)*2'
    filters.append(f'{inputs}concat=n={len(info.edits)}:v=1:a=0,{scale}[out]')
    arguments += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-an', '-r', str(fps),
                  '-t', str(duration), '-c:v', 'mjpeg', '-q:v', '3', str(destination)]
    run_tool(arguments, timeout=120)
