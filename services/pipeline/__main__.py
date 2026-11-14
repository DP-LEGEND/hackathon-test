"""From services/: python -m pipeline <clip_a> <clip_b> <out_dir>."""
from __future__ import annotations

import argparse
import sys

import cv2

from pipeline.process import Options, process_clips


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Synced fixed-camera clips to individual 3D Swing JSON files")
    ap.add_argument("clip_a", help="iPhone clip")
    ap.add_argument("clip_b", help="iPad clip")
    ap.add_argument("out_dir", help="new or empty output directory")
    ap.add_argument("--slowdown-a", type=float, default=1, help="A playback slowdown factor (4 for a 4x slow render)")
    ap.add_argument("--slowdown-b", type=float, default=1)
    ap.add_argument("--offset-b", type=float, default=0, help="B clip seconds at A time zero")
    ap.add_argument("--hand", choices=["R", "L"], default="R")
    ap.add_argument("--side", choices=["auto", "forehand", "backhand"], default="auto")
    ap.add_argument("--torso-m", type=float, default=.5, help="shoulder-mid to hip-mid length for metric scale")
    ap.add_argument("--focal-a", type=float, help="camera A focal length in source pixels")
    ap.add_argument("--focal-b", type=float, help="camera B focal length in source pixels")
    ap.add_argument("--min-speed", type=float, default=6, help="minimum wrist speed in torso lengths / real second")
    ap.add_argument("--max-gap-s", type=float, default=.1, help="maximum interpolated pose gap in real seconds")
    ap.add_argument("--model-path", default=Options.model_path)
    ap.add_argument("--no-cache", action="store_true", help="re-extract both poses and refresh raw_cache.npz")
    ap.add_argument("--cache-dir", help="reuse raw_cache.npz across fresh output directories (default: out_dir)")
    args = vars(ap.parse_args(argv))
    clip_a, clip_b, out_dir = (args.pop(key) for key in ("clip_a", "clip_b", "out_dir"))
    try:
        report = process_clips(clip_a, clip_b, out_dir, Options(**args))
    except (ValueError, OSError, RuntimeError, ImportError, cv2.error) as exc:
        print(f"pipeline: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {report['written']}/{report['detected']} swings to {out_dir}")
    if report["written"] == 0:
        print("No usable swings; see failed manifest.json", file=sys.stderr)
        return 1
    if report["rejected"]:
        print("Some swings failed pose quality checks; see manifest.json", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
