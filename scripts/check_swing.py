"""Check that a JSON file matches the Swing contract in lib/ghost/types.ts.

Usage (from the repo root or anywhere):
  python scripts/check_swing.py data/samples/swing_sample.json [more.json ...]

Standard library only, so it runs before the services environment is set up.
Exit code 0 means every file passed.
"""

from __future__ import annotations

import json
import math
import sys

N_JOINTS = 33
L_HIP, R_HIP = 23, 24
# A few bones whose length should stay roughly constant through a swing.
BONES = {"upper arm R": (12, 14), "forearm R": (14, 16), "thigh R": (24, 26), "shin R": (26, 28)}


def _is_vec3(v) -> bool:
    return (
        isinstance(v, list)
        and len(v) == 3
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in v)
    )


def check(swing) -> tuple[list[str], list[str]]:
    """Return (errors, notes). No errors means the file matches the contract."""
    errors: list[str] = []
    notes: list[str] = []
    if not isinstance(swing, dict):
        return ["top level must be an object"], notes

    if not isinstance(swing.get("id"), str) or not swing.get("id"):
        errors.append('missing "id" (non-empty string)')
    fps = swing.get("fps")
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        errors.append('"fps" must be a positive number')
    frames = swing.get("frames")
    if not isinstance(frames, list) or len(frames) < 2:
        errors.append('"frames" must be a list of at least 2 frames')
        return errors, notes

    contact = swing.get("contactFrame")
    if not isinstance(contact, int) or isinstance(contact, bool):
        errors.append('missing "contactFrame" (integer frame index)')
    elif not 0 <= contact < len(frames):
        errors.append(f'"contactFrame" {contact} is outside 0..{len(frames) - 1}')

    last_t = -math.inf
    hip_off = 0.0
    for i, f in enumerate(frames):
        if not isinstance(f, dict):
            errors.append(f"frame {i}: must be an object")
            break
        t = f.get("t")
        if not isinstance(t, (int, float)) or not math.isfinite(t):
            errors.append(f'frame {i}: "t" must be a number (seconds)')
            break
        if t <= last_t:
            errors.append(f'frame {i}: "t" must increase (got {t} after {last_t})')
            break
        last_t = t
        joints = f.get("joints")
        if not isinstance(joints, list) or len(joints) != N_JOINTS:
            errors.append(f'frame {i}: "joints" must have {N_JOINTS} points')
            break
        bad = [j for j, p in enumerate(joints) if not _is_vec3(p)]
        if bad:
            errors.append(f"frame {i}: joints {bad[:5]} are not [x, y, z] finite numbers (no NaN, no null)")
            break
        for key in ("racketTip", "racketThroat"):
            if f.get(key) is not None and not _is_vec3(f[key]):
                errors.append(f'frame {i}: "{key}" must be [x, y, z] or null')
        mid = [(a + b) / 2 for a, b in zip(joints[L_HIP], joints[R_HIP])]
        hip_off = max(hip_off, math.hypot(*mid))

    if errors:
        return errors, notes

    if hip_off > 0.05:
        errors.append(f"skeleton is not hip-centred: hip midpoint is up to {hip_off:.2f} m from the origin")

    # Sanity notes, not failures.
    dur = frames[-1]["t"] - frames[0]["t"]
    notes.append(f"{len(frames)} frames over {dur:.2f} s at {fps} fps, contact at frame {contact}")
    head_up = sum(f["joints"][0][1] for f in frames) / len(frames)
    notes.append("y axis points " + ("up" if head_up > 0 else "DOWN (MediaPipe default; the web app expects y up)"))
    for name, (a, b) in BONES.items():
        lens = [math.dist(f["joints"][a], f["joints"][b]) for f in frames]
        mean = sum(lens) / len(lens)
        spread = (max(lens) - min(lens)) / mean if mean else float("inf")
        if spread > 0.3:
            notes.append(f"{name} length varies by {spread:.0%} (jittery pose?)")
    return errors, notes


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__)
        return 2
    failed = 0
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                swing = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"FAIL {path}: cannot read JSON ({exc})")
            failed += 1
            continue
        errors, notes = check(swing)
        print(("FAIL " if errors else "OK   ") + path)
        for e in errors:
            print(f"  x {e}")
        for n in notes:
            print(f"  - {n}")
        failed += bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
