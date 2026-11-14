"""A live clip to saved swings, deterministic coaching and PREDICTED ghost paths."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
import uuid
import wave

import numpy as np

from coach.agent import coach_swing
from physics.compare import compare
from pipeline.pose import DEFAULT_MODEL, extract_raw
from pipeline.process import Options, swings_from_raw
from pipeline.video import normalize_video, probe_video, timing_at, tool, run_tool, VideoInfo
from pipeline.segment import audio_hits


@dataclass(frozen=True)
class LiveOptions:
    slowdown: float | None = None
    hand: str | None = None
    stroke: str | None = None
    model_path: str = DEFAULT_MODEL
    min_speed: float = 8.0

    def validate(self) -> None:
        if self.slowdown is not None and (not np.isfinite(self.slowdown) or not 0 < self.slowdown <= 16):
            raise ValueError('slowdown must be finite, positive and at most 16')
        if self.hand not in (None, 'R', 'L'):
            raise ValueError('hand must be R or L')
        if self.stroke not in (None, 'forehand', 'backhand'):
            raise ValueError('stroke must be forehand or backhand')
        if not np.isfinite(self.min_speed) or self.min_speed <= 0:
            raise ValueError('min_speed must be positive')


def process_live_clip(clip: Path, output: Path, options: LiveOptions = LiveOptions()) -> dict:
    options.validate()
    if not clip.is_file():
        raise ValueError(f"Clip does not exist: {clip}")
    if not Path(options.model_path).is_file():
        raise RuntimeError('Pose model unavailable; configure GHOST_POSE_MODEL before the demo')
    if output.exists():
        raise ValueError('Live processing requires a fresh output directory')
    info = probe_video(clip, options.slowdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    # No manifest is published until all pipeline/coach/physics results are ready.
    with tempfile.TemporaryDirectory(prefix='.live-', dir=output.parent) as staging:
        stage = Path(staging)
        normalized = stage / 'normalized.avi'
        normalize_video(clip, normalized, info)
        raw = extract_raw(str(normalized), model_path=options.model_path)
        # Sound helps contact timing when present; it never gates a swing.
        wav = stage / 'hits.wav'
        try:
            run_tool([tool('ffmpeg'), '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe',
                      '-format_whitelist', 'mov,avi', '-i', str(clip.resolve()),
                      '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-t', '300', str(wav)], timeout=30)
            raw['audio_hits'] = playback_hits_to_real(info, audio_hits(str(wav), rise_db=25))
        except (ValueError, OSError, wave.Error):
            raw['audio_hits'] = np.array([], dtype=float)
        finally:
            wav.unlink(missing_ok=True)
        swings, report = swings_from_raw(raw, None, Options(
            hand=options.hand or 'auto', side=options.stroke or 'auto', min_speed=options.min_speed))
        if not swings:
            raise ValueError('No fully tracked swing found; keep the whole body in frame and film one clear swing')
        session = uuid.uuid4().hex[:12]
        files, prepared = [], []
        for index, swing in enumerate(swings, 1):
            swing['id'] = f'{session}-swing-{index:04d}'
            metadata = swing['metadata']
            seconds = metadata['sourceContactSeconds']
            playback_seconds, factor = timing_at(info, seconds)
            metadata.update({
                'slowdown': options.slowdown if options.slowdown is not None else factor,
                'slowdownSource': 'manual' if options.slowdown is not None else 'auto',
                'timingBasis': info.source, 'timingWarning': info.warning,
                'captureFps': info.capture_fps, 'avgFrameRate': info.playback_fps or info.fps, 'rFrameRate': info.base_fps,
                'sourceContactPlaybackSeconds': playback_seconds,
                'sourceStartPlaybackSeconds': timing_at(info, metadata['realStartSeconds'])[0],
                'sourceTimeBase': 'normalized-real-time',
                'timeMapping': info.edits,
                'handSource': 'manual' if options.hand is not None else 'auto',
                'strokeSource': 'manual' if options.stroke is not None else 'auto',
                'stroke': options.stroke or swing['side'], 'depth': 'estimated',
                'reconstruction': 'mono',
            })
            swing['stroke'] = metadata['stroke']
            coached = coach_swing(swing, stroke=swing['stroke'], fps_real=swing['fpsReal'])
            ready = bool(coached['ghost_ready'] and coached['fix'])
            # No-fault swings get an unchanged comparison, explicitly marked as such.
            fix = coached['fix'] if ready else 'straighten_elbow'
            amount = coached['fix_amount'] if ready else 0.0
            comparison = compare(swing, fix, amount, fps_real=swing['fpsReal'], hand=metadata['hand'])
            comparison['noCorrection'] = not ready
            name = f"{swing['id']}.json"
            files.append(name)
            (stage / name).write_text(json.dumps(swing, allow_nan=False), encoding='utf-8')
            (stage / f"{swing['id']}.coach.json").write_text(json.dumps(coached, allow_nan=False), encoding='utf-8')
            (stage / f"{swing['id']}.compare.json").write_text(json.dumps(comparison, allow_nan=False), encoding='utf-8')
            prepared.append({'id': swing['id'], 'coach': coached, 'compare': comparison})
        report.update(session=session, files=files, status='partial' if report['rejected'] else 'complete')
        # Decoded temporary frames are not retained with the result.
        normalized.unlink()
        # Move only completed JSON files, then publish the manifest atomically.
        # The catalogue ignores a directory until that final manifest exists.
        output.mkdir()
        for path in stage.iterdir():
            path.replace(output / path.name)
        manifest = output / '.manifest.tmp'
        manifest.write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
        manifest.replace(output / 'manifest.json')
    return {**report, 'swingId': prepared[0]['id'], 'swingIds': [row['id'] for row in prepared],
            'coach': prepared[0]['coach'], 'compare': prepared[0]['compare'], 'webPath': '/ghost'}


def playback_hits_to_real(info: VideoInfo, hits: np.ndarray) -> np.ndarray:
    factor = info.capture_fps / info.fps
    if info.source != 'quicktime-edit-list':
        return hits / factor
    out, elapsed = [], 0.0
    for edit in info.edits:
        selected = hits[(hits >= edit['playbackStart']) & (hits < edit['playbackEnd'])]
        out.extend(elapsed + (selected - edit['playbackStart']) * edit['rate'] / factor)
        elapsed += (edit['playbackEnd'] - edit['playbackStart']) * edit['rate'] / factor
    return np.asarray(out, dtype=float)
