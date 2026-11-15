"""Rebuild the demo's saved compare files (public/swings) from compare(). Owner: aryan.

For each fix with a file in public/swings/catalogue.json, compare() runs with:
- the same swing, fix, amount, real frame rate and stroke as the saved file;
- the player's STATED intent when any saved file of the swing has one, else every ghost's TARGET
  straight drive;
- the MEASURED spot when physics/validation/spots/<swing>.json exists (else the ASSUMED drive spot);
- `validation` when physics/validation/results/<swing>.json exists (the tracked real ball).

Without --write it changes nothing and prints, per file, the numbers that would change. From services/:
    python -m physics.demo_files            # what would change
    python -m physics.demo_files --write    # rewrite the files (only after the team says go)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from physics.compare import _TARGET, compare
from physics.validate_ball import RESULTS_DIR, SPOTS_DIR

REPO = Path(__file__).resolve().parents[2]
SWINGS_DIR = REPO / "public" / "swings"


def _wall(ball: dict) -> float | None:
    return ball["frontWallHeightM"] if ball["frontWallHeightM"] is None else round(ball["frontWallHeightM"], 2)


def _land(ball: dict) -> float | None:
    return None if ball["landing"] is None else round(ball["landing"][1], 2)


def summary(cmp: dict) -> dict:
    """The numbers the demo shows or the smoke test quotes, from one compare file."""
    out = {}
    for side in ("you", "ghost"):
        ball, launch = cmp[side]["ball"], cmp["assumptions"]["launch"][side]
        out[side] = {"speedKmh": ball["speedKmh"], "frontWallM": _wall(ball), "landsM": _land(ball),
                     "outcome": ball["outcome"], "aimDeg": launch["azimuth"]["value"],
                     "startXM": round(launch["point"][0], 2), "startZM": round(launch["point"][2], 2)}
    aim = cmp["assumptions"].get("aim") or {}
    out["aim"] = {k: aim.get(k) for k in ("intent", "label", "applied", "contactTurnDeg")} if aim else None
    out["anchor"] = cmp["assumptions"]["anchor"]["label"]
    out["explain"] = "explain" in cmp["fix"]
    out["validation"] = cmp.get("validation")
    return out


def stated_intent(entry: dict) -> str | None:
    """The intent the player stated for this swing: any of its saved files labelled STATED."""
    for info in entry["fixes"].values():
        if info.get("file"):
            aim = json.loads((SWINGS_DIR / info["file"]).read_text())["assumptions"].get("aim") or {}
            if aim.get("label") == "STATED":
                return aim["intent"]
    return None


def rebuild(entry: dict, fix: str, info: dict) -> tuple[dict, dict]:
    """(saved compare file, rebuilt compare file) for one catalogue fix."""
    saved = json.loads((SWINGS_DIR / info["file"]).read_text())
    swing = json.loads((SWINGS_DIR / entry["swing"]).read_text())
    swing.setdefault("id", entry["id"])
    spot_path, result_path = SPOTS_DIR / f"{entry['id']}.json", RESULTS_DIR / f"{entry['id']}.json"
    stated = stated_intent(entry)
    new = compare(swing, fix, info["amount"], saved["fpsReal"], saved["hand"], side=entry["stroke"],
                  intent=stated or _TARGET,
                  spot=json.loads(spot_path.read_text()) if spot_path.exists() else None,
                  tracked=json.loads(result_path.read_text()) if result_path.exists() else None)
    return saved, new


def changes(old: dict, new: dict, prefix: str = "") -> list[str]:
    lines = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if isinstance(a, dict) and isinstance(b, dict):
            lines += changes(a, b, f"{prefix}{k}.")
        elif a != b:
            lines.append(f"{prefix}{k}: {a} -> {b}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild public/swings compare files from compare().")
    ap.add_argument("--write", action="store_true", help="rewrite the files (default: only print the changes)")
    args = ap.parse_args(argv)
    catalogue = json.loads((SWINGS_DIR / "catalogue.json").read_text())
    for entry in catalogue["swings"]:
        for fix, info in entry["fixes"].items():
            if not info.get("file"):
                continue
            try:
                saved, new = rebuild(entry, fix, info)
            except (OSError, ValueError, KeyError) as exc:
                print(f"{info['file']}: {exc}", file=sys.stderr)
                return 1
            print(f"== {info['file']}")
            for line in changes(summary(saved), summary(new)) or ["(no change)"]:
                print("  " + line)
            if args.write:
                (SWINGS_DIR / info["file"]).write_text(json.dumps(new, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
