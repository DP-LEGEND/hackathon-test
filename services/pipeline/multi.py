"""Optional stereo and wrist inputs, with the existing live result contract.

The original live worker is deliberately unchanged. Intermediate manifests live
two levels below the catalogue root; only the final coached result is published.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import math
from pathlib import Path
import tempfile
import uuid

from coach.agent import coach_swing
from physics.compare import decide_stroke
from pipeline.live import LiveOptions, live_comparison, process_live_clip
from pipeline.multi_audio import prepare_audio
from pipeline.multi_wrist import attach_sensor
from pipeline.pose import DEFAULT_MODEL
from pipeline.process import Options, process_clips
from pipeline.video import VideoInfo, normalize_video, probe_video, timing_at


@dataclass(frozen=True)
class MultiOptions:
    slowdown_a: float = 1.0
    slowdown_b: float = 1.0
    # B playback seconds at A's start, as in pipeline.process.Options.offset_b.
    offset_b_s: float | None = None
    model_path: str = DEFAULT_MODEL

    def validate(self) -> None:
        for slowdown in (self.slowdown_a, self.slowdown_b):
            LiveOptions(slowdown=slowdown).validate()
        if self.offset_b_s is not None and not math.isfinite(self.offset_b_s):
            raise ValueError('offset_b_s must be finite')


def _read_swings(directory: Path, report: dict) -> list[dict]:
    files = report.get('files') or []
    if not files:
        raise ValueError('No fully tracked swing found; keep the whole body in frame and film one clear swing')
    return [json.loads((directory / name).read_text(encoding='utf-8')) for name in files]


def _stereo(video_a: Path, video_b: Path, work: Path, options: MultiOptions) -> tuple[list[dict], dict, VideoInfo]:
    info_a = probe_video(video_a, options.slowdown_a)
    info_b = probe_video(video_b, options.slowdown_b)
    normalized_a, normalized_b = work / 'a.avi', work / 'b.avi'
    # This also enforces the live path's duration, cadence and resolution limits.
    normalize_video(video_a, normalized_a, info_a)
    normalize_video(video_b, normalized_b, info_b)
    offset, hits, sync = prepare_audio(video_a, video_b, info_a, info_b, work, options.offset_b_s)
    directory = work / 'stereo'
    report = process_clips(str(normalized_a), str(normalized_b), str(directory), Options(
        slowdown_a=1, slowdown_b=1, offset_b=offset, model_path=options.model_path,
        hits_wav=str(hits) if hits is not None else None))
    report['sync'] = {**report.get('sync', {}), **sync}
    swings = _read_swings(directory, report)
    for swing in swings:
        metadata = swing['metadata']
        contact = metadata['realStartSeconds'] + swing['frames'][swing['contactFrame']]['t']
        playback, factor = timing_at(info_a, contact)
        metadata.update({
            'sourceContactSeconds': contact,
            'sourceContactPlaybackSeconds': playback,
            'sourceStartPlaybackSeconds': timing_at(info_a, metadata['realStartSeconds'])[0],
            'sourceTimeBase': 'normalized-real-time', 'timeMapping': info_a.edits,
            'slowdown': factor, 'slowdownSource': 'manual', 'timingBasis': info_a.source,
            'timingWarning': info_a.warning, 'captureFps': info_a.capture_fps,
            'avgFrameRate': info_a.playback_fps or info_a.fps, 'rFrameRate': info_a.base_fps,
        })
    return swings, report, info_a


def _coach_and_compare(swing: dict) -> tuple[dict, dict]:
    """Use the live path's stroke decision and ghost policy on the attached swing."""
    metadata = swing['metadata']
    stroke = metadata.get('stroke')
    if stroke not in ('forehand', 'backhand'):
        stroke = None
        swing.pop('stroke', None)
        metadata.pop('stroke', None)
        metadata['strokeSource'] = 'coach-inferred'
    else:
        swing['stroke'] = stroke
    decided, source = decide_stroke(swing, metadata['hand'])
    if source.startswith('measured'):
        stroke = swing['stroke'] = metadata['stroke'] = decided
        metadata['strokeSource'] = source
    coached = coach_swing(swing, stroke=stroke, fps_real=swing['fpsReal'])
    metadata['stroke'] = stroke or coached['stroke']
    swing['stroke'] = metadata['stroke']
    return coached, live_comparison(swing, coached, metadata['hand'])


def process_multi_clips(
    video_a: Path,
    output: Path,
    options: MultiOptions = MultiOptions(),
    *,
    video_b: Path | None = None,
    sensor_csv: Path | None = None,
    warnings: list[str] | None = None,
) -> dict:
    """Return /process's result fields, plus non-fatal optional-input warnings."""
    options.validate()
    if not video_a.is_file():
        raise ValueError('The primary video is missing')
    if not Path(options.model_path).is_file():
        raise RuntimeError('Pose model unavailable; configure GHOST_POSE_MODEL before the demo')
    if output.exists():
        raise ValueError('Live processing requires a fresh output directory')
    notices = list(warnings or [])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.multi-', dir=output.parent) as temporary:
        work = Path(temporary)
        swings, report, info_a = None, None, None
        if video_b is not None:
            try:
                swings, report, info_a = _stereo(video_a, video_b, work, options)
                notices.extend(report.get('sync', {}).get('warnings', []))
            except Exception:
                # An optional camera, including its decoder/calibration/audio,
                # cannot prevent the primary clip from using the live path.
                notices.append('Stereo processing or audio sync failed; using video_a with estimated (1 camera) depth.')
        if swings is None:
            directory = work / 'mono'
            report = process_live_clip(video_a, directory, LiveOptions(
                slowdown=options.slowdown_a, model_path=options.model_path))
            swings = _read_swings(directory, report)

        session = uuid.uuid4().hex[:12]
        for index, swing in enumerate(swings, 1):
            # Stereo's content-hash IDs must not collide with an earlier upload.
            swing['id'] = f'{session}-swing-{index:04d}'
            metadata = swing['metadata']
            stereo = metadata.get('reconstruction', swing.get('source')) == 'stereo'
            metadata['depth'] = 'triangulated (2 cameras)' if stereo else 'estimated (1 camera)'
            metadata['reconstruction'] = swing['source'] = 'stereo' if stereo else 'mono'
            if video_b is not None and not stereo and not any('using video_a' in note for note in notices):
                notices.append(f'Swing {index}: stereo reconstruction failed; using video_a with estimated (1 camera) depth.')

        if sensor_csv is not None:
            try:
                info_a = info_a or probe_video(video_a, options.slowdown_a)
                attached, sensor_warnings = attach_sensor(copy.deepcopy(swings), video_a, sensor_csv,
                    slowdown=options.slowdown_a, work=work, info=info_a)
                # Validate the optional result before discarding the video-only
                # version. Sensor failures must never make an otherwise usable upload fail.
                for swing in attached:
                    _coach_and_compare(swing)
                    json.dumps(swing, allow_nan=False)
                swings = attached
                notices.extend(sensor_warnings)
            except Exception:
                notices.append('Wrist data could not be synced or measured; ignored the sensor data.')

        prepared = []
        published = work / 'published'
        published.mkdir()
        for swing in swings:
            coached, comparison = _coach_and_compare(swing)
            name = swing['id']
            for suffix, payload in (('', swing), ('.coach', coached), ('.compare', comparison)):
                (published / f'{name}{suffix}.json').write_text(
                    json.dumps(payload, allow_nan=False), encoding='utf-8')
            prepared.append({'id': name, 'coach': coached, 'compare': comparison})

        # Remove live response-only keys before publishing the same manifest contract.
        report = {key: value for key, value in report.items()
                  if key not in ('swingId', 'swingIds', 'coach', 'compare', 'webPath')}
        report.update(session=session, files=[f"{row['id']}.json" for row in prepared],
                      written=len(prepared), status='partial' if report.get('rejected') else 'complete',
                      warnings=list(dict.fromkeys(notices)))
        (published / 'manifest.json').write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
        # The directory becomes catalogue-visible only after every file is ready.
        published.rename(output)
    return {**report, 'swingId': prepared[0]['id'], 'swingIds': [row['id'] for row in prepared],
            'coach': prepared[0]['coach'], 'compare': prepared[0]['compare'], 'webPath': '/ghost'}
