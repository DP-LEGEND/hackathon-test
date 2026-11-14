"""Command line: run pose on a whole clip (or a window) and save raw arrays.

Usage (from services/):
  python -m pipeline.extract <clip> <out.npz> [--start S] [--end S] [--model heavy|full]
"""

import argparse
from pathlib import Path

import numpy as np

from pipeline.pose import extract_raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("out")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--model", default="heavy", choices=["heavy", "full", "lite"])
    a = ap.parse_args()
    model = str(Path.home() / "ghost-models" / f"pose_landmarker_{a.model}.task")
    raw = extract_raw(a.clip, a.start, a.end, model_path=model)
    np.savez_compressed(a.out, **{k: np.asarray(v) for k, v in raw.items()})
    det = (~np.isnan(raw["world"][:, 0, 0])).mean()
    print(f"{a.clip}: {len(raw['t'])} frames, detected {det:.1%}")


if __name__ == "__main__":
    main()
