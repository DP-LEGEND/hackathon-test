"""Optional stereo and wrist inputs, with the existing live result contract.

The original live worker is deliberately unchanged. Intermediate manifests live
two levels below the catalogue root; only the final coached result is published.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
from pipeline import multi_audio, process as pipeline_process
from pipeline.multi_wrist import attach_sensor
from pipeline.multi_timing import (probe_multi_video as probe_video,
                                  normalize_multi_video as normalize_video,
                                  infer_local_timing, timing_debug, local_timing_at as timing_at)
from pipeline.pose import DEFAULT_MODEL
from pipeline.process import Options, process_clips
from pipeline.video import VideoInfo


@dataclass(frozen=True)
class MultiOptions:
    slowdown_a: float | None = None
    slowdown_b: float | None = None
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


class MultiProcessingError(ValueError):
    """A multi-only failure with safe diagnostics for the HTTP response."""
    def __init__(self, message: str, debug: dict, status_code: int = 422):
        super().__init__(message)
        self.debug, self.status_code = debug, status_code


class _StereoFailure(ValueError):
    def __init__(self, message: str, debug: dict, info_a=None, normalized_a=None):
        super().__init__(message)
        self.debug, self.info_a, self.normalized_a = debug, info_a, normalized_a


def _stereo_reason(debug: dict, stage: str, exc: Exception) -> str:
    geometry = debug['stereo']
    reason = geometry.get('reason')
    error = geometry.get('reprojectionErrorPx')
    if reason and 'reprojection' in reason:
        return (f"calibration error {error:.2f} px exceeds {geometry['tolerancePx']:g} px"
                if error is not None else 'calibration error is non-finite')
    if reason and 'too few' in reason:
        count = geometry.get('positiveDepthJointSamples', geometry.get('sharedJointSamples', 0))
        return f'too few tracked joints ({count} usable samples; at least 12 required)'
    if reason:
        return reason
    if stage == 'sync':
        detail = str(exc) if isinstance(exc, ValueError) else 'audio could not be read'
        return detail if detail.startswith('offset not found') else f'offset not found: {detail}'
    if stage == 'reconstruction':
        return 'too few tracked joints or no accepted swing after reconstruction'
    return 'video timing or pose extraction unavailable'


def _audio_debug(sync: dict) -> dict:
    return {key: value for key, value in sync.items()
            if key.startswith('audio') or key in ('method', 'sequencePairs', 'offsetBRealSeconds', 'offsetBPlaybackSeconds')}


def _stereo(video_a: Path, video_b: Path, work: Path, options: MultiOptions) -> tuple[list[dict], dict, VideoInfo]:
    debug = {'stereo': {'status': 'not-attempted', 'reason': None, 'reprojectionErrorPx': None},
             'sync': {}, 'videoA': {}, 'videoB': {}}
    info_a, info_b, normalized_a, stage = None, None, None, 'timing'
    try:
        info_a = probe_video(video_a, options.slowdown_a)
        info_b = probe_video(video_b, options.slowdown_b)
        normalized_a, normalized_b = work / 'a.avi', work / 'b.avi'
        normalize_video(video_a, normalized_a, info_a)
        normalize_video(video_b, normalized_b, info_b)
        cache = work / 'pose-cache'
        needs_local = [info.source not in ('manual', 'capture-rate-tag', 'quicktime-edit-list')
                       for info in (info_a, info_b)]
        if any(needs_local):
            raw_a, raw_b = pipeline_process.extract_pair(str(normalized_a), str(normalized_b), options.model_path,
                cache, pipeline_process.extract_raw, no_cache=False)
            infos = [info_a, info_b]
            for index, (source, normalized, raw, name) in enumerate(zip(
                    (video_a, video_b), (normalized_a, normalized_b), (raw_a, raw_b), ('videoA', 'videoB'))):
                if not needs_local[index]:
                    continue
                try:
                    peaks, _ = multi_audio.extract_playback_peaks(source, work / f'{name}-local.wav')
                    corrected, evidence = infer_local_timing(raw, infos[index], peaks)
                    debug[name]['localTiming'] = evidence
                    if corrected != infos[index]:
                        replacement = normalized.with_name(normalized.stem + '-corrected.avi')
                        normalize_video(source, replacement, corrected)
                        replacement.replace(normalized)
                        infos[index] = corrected
                except (ValueError, RuntimeError, OSError):
                    debug[name]['localTiming'] = {'status': 'unavailable',
                        'reason': 'No usable audio/motion evidence for local timing; retained metadata timing.'}
            info_a, info_b = infos
        stage = 'sync'
        offset, hits, sync = prepare_audio(video_a, video_b, info_a, info_b, work, options.offset_b_s)
        debug['sync'] = _audio_debug(sync)
        for name, info, suffix in (('videoA', info_a, 'A'), ('videoB', info_b, 'B')):
            times = sync.get(f'audioSwingTimes{suffix}', [])
            debug[name].update(chosenSwingTimesSeconds=times, timing=timing_debug(info, times), timingSource=info.source)
        stage = 'reconstruction'
        directory = work / 'stereo'
        report = process_clips(str(normalized_a), str(normalized_b), str(directory), Options(
            slowdown_a=1, slowdown_b=1, offset_b=offset, model_path=options.model_path,
            cache_dir=str(cache), calibration_debug=debug['stereo'],
            hits_wav=str(hits) if hits is not None else None))
        report['sync'] = {**report.get('sync', {}), **sync}
        report['debug'] = debug
        swings = _read_swings(directory, report)
        if debug['stereo'].get('status') == 'calibrated':
            debug['stereo']['status'] = 'triangulated' if any(s['source'] == 'stereo' for s in swings) else 'mono-fallback'
            if debug['stereo']['status'] == 'mono-fallback':
                debug['stereo']['reason'] = 'too few tracked joints after reconstruction quality gates'
    except Exception as exc:
        if getattr(exc, 'debug', None):
            debug['sync'].update(_audio_debug(exc.debug))
        for name, info, suffix in (('videoA', info_a, 'A'), ('videoB', info_b, 'B')):
            times = debug['sync'].get(f'audioSwingTimes{suffix}', [])
            debug[name]['chosenSwingTimesSeconds'] = times
            if info:
                debug[name].update(timing=timing_debug(info, times), timingSource=info.source)
        reason = _stereo_reason(debug, stage, exc)
        debug['stereo'].update(status='failed', reason=reason)
        raise _StereoFailure(reason, debug, info_a, normalized_a) from exc
    for swing in swings:
        metadata = swing['metadata']
        contact = metadata['realStartSeconds'] + swing['frames'][swing['contactFrame']]['t']
        playback, factor = timing_at(info_a, contact)
        metadata.update({
            'sourceContactSeconds': contact,
            'sourceContactPlaybackSeconds': playback,
            'sourceStartPlaybackSeconds': timing_at(info_a, metadata['realStartSeconds'])[0],
            'sourceTimeBase': 'normalized-real-time', 'timeMapping': info_a.edits,
            'slowdown': factor, 'slowdownSource': ('manual' if options.slowdown_a is not None else
                info_a.source if info_a.source in ('playback-intent', 'local-speed-inference') else 'auto'), 'timingBasis': info_a.source,
            'timingWarning': info_a.warning,
            'captureFps': info_a.fps * factor if info_a.source == 'local-speed-inference' else info_a.capture_fps,
            'avgFrameRate': info_a.playback_fps or info_a.fps, 'rFrameRate': info_a.base_fps,
        })
    return swings, report, info_a


def _prepare_primary(video: Path, work: Path, options: MultiOptions, debug: dict):
    """Local timing also applies when only video A (plus an optional sensor) exists."""
    info = probe_video(video, options.slowdown_a)
    if info.source in ('manual', 'capture-rate-tag', 'quicktime-edit-list'):
        return video, options.slowdown_a, info
    try:
        peaks, _ = multi_audio.extract_playback_peaks(video, work / 'primary-local.wav')
        if len(peaks) < 3:
            return video, options.slowdown_a, info
        initial = work / 'primary-initial.avi'
        normalize_video(video, initial, info)
        raw = pipeline_process.extract_raw(str(initial), model_path=options.model_path)
        corrected, evidence = infer_local_timing(raw, info, peaks)
        debug['videoA']['localTiming'] = evidence
        if corrected != info:
            normalized = work / 'primary-corrected.avi'
            normalize_video(video, normalized, corrected)
            return normalized, 1, corrected
    except (ValueError, RuntimeError, OSError):
        debug['videoA']['localTiming'] = {'status': 'unavailable',
            'reason': 'No usable audio/motion evidence for local timing; retained metadata timing.'}
    return video, options.slowdown_a, info


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
    debug = {'videoA': {}, 'videoB': {} if video_b else None, 'sync': {},
             'stereo': {'status': 'not-requested', 'reason': None, 'reprojectionErrorPx': None},
             'sensor': {'status': 'not-requested'}}
    for warning in warnings or []:
        if 'sensor' in warning.lower() and 'ignored' in warning.lower():
            debug['sensor'].update(status='ignored', reason=warning)
    try:
        return _process_multi_clips(video_a, output, options, video_b=video_b,
                                   sensor_csv=sensor_csv, warnings=warnings, debug=debug)
    except MultiProcessingError:
        raise
    except ValueError as exc:
        raise MultiProcessingError(str(exc), debug) from exc
    except (RuntimeError, OSError) as exc:
        raise MultiProcessingError('Multi-upload processing is unavailable', debug, 503) from exc


def _process_multi_clips(video_a, output, options, *, video_b, sensor_csv, warnings, debug) -> dict:
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
        fallback_video, fallback_slowdown = video_a, options.slowdown_a
        if video_b is not None:
            try:
                swings, report, info_a = _stereo(video_a, video_b, work, options)
                debug.update(report.get('debug', {}))
                notices.extend(report.get('sync', {}).get('warnings', []))
            except Exception as exc:
                # An optional camera, including its decoder/calibration/audio,
                # cannot prevent the primary clip from using the live path.
                if isinstance(exc, _StereoFailure):
                    debug.update(exc.debug)
                    info_a = exc.info_a
                    if info_a and info_a.source == 'local-speed-inference' and exc.normalized_a:
                        fallback_video, fallback_slowdown = exc.normalized_a, 1
                    reason = str(exc)
                else:
                    reason = 'video timing or pose extraction unavailable'
                    debug['stereo'].update(status='failed', reason=reason)
                notices.append(f'Stereo fallback: {reason}; using video_a with estimated (1 camera) depth.')
        if swings is None:
            if fallback_video == video_a and 'localTiming' not in debug['videoA']:
                fallback_video, fallback_slowdown, info_a = _prepare_primary(video_a, work, options, debug)
            directory = work / 'mono'
            report = process_live_clip(fallback_video, directory, LiveOptions(
                slowdown=fallback_slowdown, model_path=options.model_path))
            swings = _read_swings(directory, report)
            if swings[0]['metadata'].get('slowdownSource') == 'speed-retry':
                factor = swings[0]['metadata']['slowdown']
                info_a = replace(info_a or probe_video(video_a, options.slowdown_a),
                                 capture_fps=swings[0]['metadata']['captureFps'],
                                 slowdown=factor, source='speed-retry')
                # Sync evidence from before the retry belongs to another clock.
                debug['sync']['preRetryAudioSwingTimesA'] = debug['sync'].pop('audioSwingTimesA', [])
            if fallback_video != video_a:
                for swing in swings:
                    metadata = swing['metadata']
                    contact = metadata['sourceContactSeconds']
                    playback, factor = timing_at(info_a, contact)
                    metadata.update(slowdown=factor, slowdownSource=info_a.source,
                                    sourceContactPlaybackSeconds=playback, timingBasis=info_a.source,
                                    sourceStartPlaybackSeconds=timing_at(info_a, metadata['realStartSeconds'])[0],
                                    captureFps=info_a.fps * factor, avgFrameRate=info_a.playback_fps or info_a.fps,
                                    rFrameRate=info_a.base_fps, timeMapping=info_a.edits, timingWarning=info_a.warning)

        # Record/select only the dominant audio contacts on this opt-in path.
        # A silent clip still gets the existing mono pose estimate, explicitly
        # distinguished from selected audio swing times in debug.
        selected = debug['sync'].get('audioSwingTimesA')
        if selected is None:
            try:
                info_a = info_a or probe_video(video_a, options.slowdown_a)
                metadata = swings[0]['metadata']
                if metadata.get('slowdownSource') == 'speed-retry':
                    info_a = replace(info_a, capture_fps=info_a.fps * metadata['slowdown'],
                                     slowdown=metadata['slowdown'], source='speed-retry')
                times, _ = multi_audio._extract_hits(video_a, info_a, work / 'primary-audio.wav')
                selected = times.tolist()
                debug['sync']['audioSwingTimesA'] = selected
            except (ValueError, RuntimeError, OSError):
                debug['videoA']['audioStatus'] = 'unavailable; contacts use pose estimates'
        if selected:
            before_filter = len(swings)
            keep = set()
            for hit in selected:
                index = min(range(len(swings)), key=lambda i: abs(swings[i]['metadata']['sourceContactSeconds'] - hit))
                if abs(swings[index]['metadata']['sourceContactSeconds'] - hit) <= .6:
                    keep.add(index)
            swings = [swing for index, swing in enumerate(swings) if index in keep]
            debug['videoA']['discardedNonSwingWindows'] = before_filter - len(swings)
            if not swings:
                raise ValueError('No fully tracked swing matches the dominant audio swing sequence')
        debug['videoA']['chosenSwingTimesSeconds'] = selected or []
        if info_a:
            debug['videoA'].update(timing=timing_debug(info_a, selected or []), timingSource=info_a.source)
        debug['videoA']['acceptedContactTimesSeconds'] = [s['metadata']['sourceContactSeconds'] for s in swings]
        for name in ('videoA', 'videoB'):
            local = (debug.get(name) or {}).get('localTiming', {})
            if local.get('warnings'):
                notices.extend(f'{name}: {warning}' for warning in local['warnings'])

        session = uuid.uuid4().hex[:12]
        for index, swing in enumerate(swings, 1):
            # Stereo's content-hash IDs must not collide with an earlier upload.
            swing['id'] = f'{session}-swing-{index:04d}'
            metadata = swing['metadata']
            stereo = metadata.get('reconstruction', swing.get('source')) == 'stereo'
            metadata['depth'] = 'triangulated (2 cameras)' if stereo else 'estimated (1 camera)'
            metadata['reconstruction'] = swing['source'] = 'stereo' if stereo else 'mono'
            debug['stereo'].setdefault('windows', []).append({
                'swingId': swing['id'], 'source': metadata['reconstruction'],
                'reason': metadata.get('fallbackReason') if not stereo and video_b else None})
            if video_b is not None and not stereo and not any('using video_a' in note for note in notices):
                reason = debug['stereo'].get('reason') or metadata.get('fallbackReason') or 'too few tracked joints'
                error = debug['stereo'].get('reprojectionErrorPx')
                if error is not None:
                    reason += f' (reprojection error {error:.2f} px)'
                notices.append(f'Swing {index}: {reason}; using video_a with estimated (1 camera) depth.')

        if sensor_csv is not None:
            try:
                debug['sensor']['status'] = 'matching'
                info_a = info_a or probe_video(video_a, options.slowdown_a)
                attached, sensor_warnings = attach_sensor(copy.deepcopy(swings), video_a, sensor_csv,
                    slowdown=options.slowdown_a, work=work, info=info_a,
                    video_swing_times=selected or None, debug=debug['sensor'])
                # Validate the optional result before discarding the video-only
                # version. Sensor failures must never make an otherwise usable upload fail.
                for swing in attached:
                    _coach_and_compare(swing)
                    json.dumps(swing, allow_nan=False)
                swings = attached
                if debug['sensor'].get('status') == 'matching':
                    debug['sensor']['status'] = 'attached' if any('wrist' in s for s in swings) else 'ignored'
                notices.extend(sensor_warnings)
            except Exception:
                debug['sensor'].update(status='ignored', reason='Wrist data could not be synced or measured')
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
                      warnings=list(dict.fromkeys(notices)), debug=debug)
        (published / 'manifest.json').write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
        # The directory becomes catalogue-visible only after every file is ready.
        published.rename(output)
    return {**report, 'swingId': prepared[0]['id'], 'swingIds': [row['id'] for row in prepared],
            'coach': prepared[0]['coach'], 'compare': prepared[0]['compare'], 'webPath': '/ghost'}
