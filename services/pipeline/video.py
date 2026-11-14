"""Probe encoded cadence and QuickTime edit rates without guessing capture FPS.

r_frame_rate is retained as evidence, never treated as a capture-rate tag.
Native edit-rate movies are decoded without their presentation edit list so pose
runs on the source cadence. A burned-in render needs explicit capture metadata
or a manual slowdown; missing information is disclosed in the result.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
import os
from pathlib import Path
import struct
import subprocess


class VideoError(ValueError):
    pass


def tool(name: str) -> str:
    return os.environ.get(f'GHOST_{name.upper()}', name)


def run_tool(arguments: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except FileNotFoundError as exc:
        raise RuntimeError('Install ffmpeg/ffprobe or configure GHOST_FFMPEG/GHOST_FFPROBE') from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoError('Video decoding timed out; use a shorter clip') from exc
    if result.returncode:
        raise VideoError('Video cannot be read or decoded; upload a valid local video')
    return result.stdout.decode('utf-8', errors='replace')


def rate(value) -> float | None:
    try:
        result = float(Fraction(str(value)))
        return result if 0 < result <= 1000 else None
    except (ValueError, ZeroDivisionError):
        return None


def _boxes(stream, start: int, end: int):
    cursor = start
    count = 0
    while cursor + 8 <= end:
        stream.seek(cursor)
        size, kind = struct.unpack('>I4s', stream.read(8))
        header = 8
        if size == 1:
            extra = stream.read(8)
            if len(extra) != 8:
                raise VideoError('Truncated QuickTime atom')
            size = struct.unpack('>Q', extra)[0]
            header = 16
        elif size == 0:
            size = end - cursor
        if size < header or cursor + size > end:
            raise VideoError('Invalid QuickTime atom size')
        yield kind, cursor + header, cursor + size
        cursor += size
        count += 1
        if count > 10000:
            raise VideoError('Too many QuickTime atoms')


def quicktime_edits(path: Path) -> list[dict]:
    """Video elst v0/v1 entries: movie seconds, source media seconds, relative rate.

    Walk only bounded headers, never load the mdat/video payload into memory.
    Empty edits are presentation padding; they carry no captured frames.
    """
    with path.open('rb') as stream:
        top = list(_boxes(stream, 0, path.stat().st_size)) if path.suffix.lower() in ('.mov', '.mp4', '.m4v') else []
        movie = next((entry for entry in top if entry[0] == b'moov'), None)
        if movie is None:
            return []
        children = list(_boxes(stream, movie[1], movie[2]))
        header = next((entry for entry in children if entry[0] == b'mvhd'), None)
        if header is None:
            return []
        stream.seek(header[1]); data = stream.read(min(40, header[2] - header[1]))
        if len(data) < 24:
            raise VideoError('Truncated QuickTime movie header')
        scale = struct.unpack_from('>I', data, 20 if data[0] == 1 else 12)[0]
        if not scale:
            raise VideoError('Invalid movie timescale')
        for kind, start, end in children:
            if kind != b'trak':
                continue
            track = list(_boxes(stream, start, end))
            media = next((entry for entry in track if entry[0] == b'mdia'), None)
            edits = next((entry for entry in track if entry[0] == b'edts'), None)
            if not media:
                continue
            media_boxes = list(_boxes(stream, media[1], media[2]))
            handler = next((entry for entry in media_boxes if entry[0] == b'hdlr'), None)
            mdhd = next((entry for entry in media_boxes if entry[0] == b'mdhd'), None)
            if not handler or not mdhd:
                continue
            stream.seek(handler[1] + 8)
            if stream.read(4) != b'vide':
                continue
            if not edits:
                return []
            stream.seek(mdhd[1]); data = stream.read(min(40, mdhd[2] - mdhd[1]))
            if len(data) < 24:
                raise VideoError('Truncated media header')
            media_scale = struct.unpack_from('>I', data, 20 if data[0] == 1 else 12)[0]
            if not media_scale:
                raise VideoError('Invalid media timescale')
            elst = next((entry for entry in _boxes(stream, edits[1], edits[2]) if entry[0] == b'elst'), None)
            if elst is None:
                continue
            stream.seek(elst[1]); data = stream.read(8)
            if len(data) != 8 or data[0] not in (0, 1):
                raise VideoError('Unsupported QuickTime edit version')
            count = struct.unpack_from('>I', data, 4)[0]
            width = 20 if data[0] == 1 else 12
            if count > 128 or elst[1] + 8 + count * width > elst[2]:
                raise VideoError('Invalid QuickTime edit list')
            out, position = [], 0.0
            for _ in range(count):
                values = struct.unpack('>Qqi' if width == 20 else '>Iii', stream.read(width))
                duration, media_time, fixed_rate = values
                speed = fixed_rate / 65536
                seconds = duration / scale
                if media_time != -1:
                    if speed <= 0 or speed > 16:
                        raise VideoError('Freeze/reverse QuickTime edits are unsupported')
                    out.append({'playbackStart': position, 'playbackEnd': position + seconds,
                                'mediaStart': media_time / media_scale, 'rate': speed})
                position += seconds
            return out
    return []


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    base_fps: float
    duration: float
    capture_fps: float
    slowdown: float
    source: str
    edits: list[dict]
    warning: str | None = None
    ignore_edits: bool = False
    playback_fps: float | None = None


def probe_video(path: Path, slowdown: float | None = None) -> VideoInfo:
    payload = json.loads(run_tool([tool('ffprobe'), '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                  '-format_whitelist', 'mov,avi', '-show_streams',
                                  '-show_format', '-of', 'json', str(path.resolve())]))
    video = next((s for s in payload.get('streams', []) if s.get('codec_type') == 'video'), None)
    if video is None:
        raise VideoError('Upload has no video stream')
    fps = rate(video.get('avg_frame_rate')) or rate(video.get('r_frame_rate'))
    base = rate(video.get('r_frame_rate')) or fps
    duration = float(video.get('duration') or payload.get('format', {}).get('duration', 0))
    if fps is None or not 0 < duration <= 300:
        raise VideoError('Video must have a valid frame rate and be at most 5 playback minutes')
    if int(video.get('width', 0)) * int(video.get('height', 0)) > 3840 * 2160:
        raise VideoError('Upload resolution must be at most 4K')
    edits = quicktime_edits(path)
    nonunit = any(abs(entry['rate'] - 1) > 1e-6 for entry in edits)
    native_fps = fps
    native_duration = duration
    if nonunit:
        native_payload = json.loads(run_tool([tool('ffprobe'), '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-format_whitelist', 'mov,avi', '-ignore_editlist', '1',
            '-select_streams', 'v:0', '-show_entries', 'stream=avg_frame_rate,r_frame_rate,duration',
            '-of', 'json', str(path.resolve())]))
        if not native_payload.get('streams'):
            raise VideoError('Cannot read native media cadence')
        native = native_payload['streams'][0]
        native_fps = rate(native.get('avg_frame_rate')) or rate(native.get('r_frame_rate'))
        native_duration = float(native.get('duration') or duration)
        if native_fps is None:
            raise VideoError('Cannot determine native media cadence')
    if slowdown is not None:
        if not 0 < slowdown <= 16:
            raise VideoError('slowdown must be positive and at most 16')
        return VideoInfo(native_fps, base, native_duration, native_fps * slowdown, slowdown,
                         'manual', [], ignore_edits=nonunit, playback_fps=fps)
    tags = {**payload.get('format', {}).get('tags', {}), **video.get('tags', {})}
    # Numeric capture-rate extensions are read only when actually present. The
    # Apple full-frame-rate-playback-intent tag is a hint, not a capture cadence.
    capture = None
    for key, value in tags.items():
        normalized = key.lower().replace('-', '').replace('_', '').replace('.', '')
        if normalized in ('comapplequicktimecapturefps', 'comapplequicktimecaptureframerate',
                          'comapplequicktimevideoframerate'):
            capture = rate(value)
            if capture:
                break
    if nonunit:
        factor = 1 / min(entry['rate'] for entry in edits)
        return VideoInfo(native_fps, base, duration, capture or native_fps, factor,
                         'quicktime-edit-list', edits, ignore_edits=True, playback_fps=fps)
    if capture and capture >= fps:
        return VideoInfo(fps, base, duration, capture, capture / fps, 'capture-rate-tag', [])
    return VideoInfo(fps, base, duration, fps, 1.0, 'encoded-cadence', [],
        'No capture time mapping; using encoded real-time cadence. Override slowdown for a burned-in slow render.')


def timing_at(info: VideoInfo, real_seconds: float) -> tuple[float, float]:
    """Return (source playback seconds, local slowdown) on the normalized clock."""
    factor = info.capture_fps / info.fps
    if info.source != 'quicktime-edit-list':
        return real_seconds * factor, factor
    elapsed = 0.0
    for edit in info.edits:
        duration = (edit['playbackEnd'] - edit['playbackStart']) * edit['rate'] / factor
        if real_seconds <= elapsed + duration:
            local = real_seconds - elapsed
            return edit['playbackStart'] + local * factor / edit['rate'], factor / edit['rate']
        elapsed += duration
    return info.edits[-1]['playbackEnd'], factor / info.edits[-1]['rate']


def normalize_video(source: Path, destination: Path, info: VideoInfo) -> None:
    """Decode source media to CFR real seconds, applying trims but undoing slow edits."""
    native = info.source == 'quicktime-edit-list'
    factor = info.capture_fps / info.fps
    duration = (sum((e['playbackEnd'] - e['playbackStart']) * e['rate'] for e in info.edits)
                if native else info.duration) / factor
    if duration > 30:
        raise VideoError('Live clip must be at most 30 real seconds')
    if not 0 < info.capture_fps <= 480:
        raise VideoError('Unsupported capture frame rate')
    fps = min(info.capture_fps, 120)
    arguments = [tool('ffmpeg'), '-v', 'error', '-nostdin', '-y']
    if info.ignore_edits:
        arguments += ['-ignore_editlist', '1']
    arguments += ['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'mov,avi', '-i', str(source.resolve())]
    scale = 'scale=trunc(iw*min(1\\,1280/iw)/2)*2:trunc(ih*min(1\\,1280/iw)/2)*2'
    if native:
        filters = []
        for i, edit in enumerate(info.edits):
            start = edit['mediaStart']
            end = start + (edit['playbackEnd'] - edit['playbackStart']) * edit['rate']
            filters.append(f'[0:v:0]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{factor}[v{i}]')
        inputs = ''.join(f'[v{i}]' for i in range(len(info.edits)))
        filters.append(f'{inputs}concat=n={len(info.edits)}:v=1:a=0,{scale}[out]')
        arguments += ['-filter_complex', ';'.join(filters), '-map', '[out]']
    else:
        arguments += ['-map', '0:v:0', '-vf', f'setpts=(PTS-STARTPTS)/{factor},{scale}']
    arguments += ['-an', '-r', str(fps), '-t', '30', '-c:v', 'mjpeg', '-q:v', '3', str(destination)]
    run_tool(arguments, timeout=120)
