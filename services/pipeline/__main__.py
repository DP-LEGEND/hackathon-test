"""From services/: python -m pipeline <clip_a> <clip_b> <out_dir>."""
from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path
import uuid

import cv2

from pipeline.process import Options, process_clips
from pipeline.live import LiveOptions, process_live_clip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Synced fixed-camera clips to individual 3D Swing JSON files")
    ap.add_argument("clip_a", help="iPhone clip")
    ap.add_argument("clip_b", nargs="?", help="optional second clip, or output folder in single-camera mode")
    ap.add_argument("out_dir", nargs="?", help="new output directory (stereo mode)")
    ap.add_argument("--out-dir", dest="live_output", help="new output directory (single-camera mode)")
    ap.add_argument("--slowdown", type=float, help="manual primary-clip slowdown, wins over metadata")
    ap.add_argument("--stroke", choices=["forehand", "backhand"], help="manual stroke, wins over automatic classification")
    ap.add_argument("--slowdown-a", type=float, default=None, help="A playback slowdown factor (4 for a 4x slow render)")
    ap.add_argument("--slowdown-b", type=float, default=1)
    ap.add_argument("--offset-b", type=float, default=0, help="B clip seconds at A time zero")
    ap.add_argument("--hand", choices=["auto", "R", "L"], default="auto")
    ap.add_argument("--side", choices=["auto", "forehand", "backhand"], default="auto")
    ap.add_argument("--torso-m", type=float, default=.5, help="shoulder-mid to hip-mid length for metric scale")
    ap.add_argument("--focal-a", type=float, help="camera A focal length in source pixels")
    ap.add_argument("--focal-b", type=float, help="camera B focal length in source pixels")
    ap.add_argument("--min-speed", type=float, default=Options.min_speed, help="minimum wrist speed in torso lengths / real second (default: 8)")
    ap.add_argument("--max-gap-s", type=float, default=Options.max_gap_s, help="maximum bounded pose gap in real seconds (default: 0.25)")
    ap.add_argument("--model-path", default=Options.model_path)
    ap.add_argument("--no-cache", action="store_true", help="re-extract both poses and refresh raw_cache.npz")
    ap.add_argument("--cache-dir", help="reuse raw_cache.npz across fresh output directories (default: out_dir)")
    for camera in ("a", "b"):
        ap.add_argument(f"--{camera}-realtime-before", type=float, default=0,
                        help="QuickTime seconds before which playback is real speed")
        ap.add_argument(f"--{camera}-realtime-after", type=float,
                        help="QuickTime seconds after which playback is real speed")
    ap.add_argument("--hits-wav", help="optional camera A playback-time 16 kHz mono PCM16 WAV; unmatched swings use speed peaks")
    ap.add_argument("--tap-filter", action="store_true", help="speed >=7 torso/s and spacing >=2.5 real s; sound is optional")
    args = vars(ap.parse_args(argv))
    clip_a, clip_b, out_dir = (args.pop(key) for key in ("clip_a", "clip_b", "out_dir"))
    live_output = args.pop("live_output")
    slowdown = args.pop("slowdown")
    stroke = args.pop("stroke")
    try:
        if out_dir is None:
            output = Path(live_output or clip_b or os.environ.get('GHOST_SWINGS_DIR', str(
                Path(__file__).resolve().parents[2] / 'data' / 'processed')))
            if not live_output and clip_b is None:
                output = output / f'live-{uuid.uuid4().hex}'
            out_dir = str(output)
            report = process_live_clip(Path(clip_a), output, LiveOptions(
                slowdown=slowdown if slowdown is not None else args['slowdown_a'],
                hand=None if args['hand'] == 'auto' else args['hand'],
                stroke=stroke or (None if args['side'] == 'auto' else args['side']),
                model_path=args['model_path'], min_speed=args['min_speed']))
        else:
            if args["slowdown_a"] is None:
                args["slowdown_a"] = 1
            if slowdown is not None:
                args['slowdown_a'] = slowdown
            if stroke is not None:
                args['side'] = stroke
            report = process_clips(clip_a, clip_b, out_dir, Options(**args))
    except (ValueError, OSError, RuntimeError, ImportError, cv2.error) as exc:
        print(f"pipeline: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {report['written']}/{report['detected']} swings to {out_dir}")
    if "swingId" in report:
        print(f"Swing id: {report['swingId']}")
    if report["written"] == 0:
        print("No usable swings; see failed manifest.json", file=sys.stderr)
        return 1
    if report["rejected"]:
        print("Some swings failed pose quality checks; see manifest.json", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
