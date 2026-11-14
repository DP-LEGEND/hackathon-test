"""Launch angle from a side-camera clip, and the keep/change call for the ASSUMED elevations. Owner: aryan.

For the 08:00 check in docs/elevation-check.md. physics/compare.py's DEFAULT_ELEVATION_DEG
(12 deg forehand, 3 deg backhand) were each fitted to one clip; this measures new hits.

The side camera must point straight across the court, square to the shot, with the ball near
the middle of the frame. The angle is then a ratio of pixel distances, so no scale is needed.
Two points on a horizontal court line (--level) correct a phone that wasn't level.

From inside services/:

    python -m physics.measure_launch click CLIP [FRAME] --stroke forehand --hit 1 --csv HITS.csv
    python -m physics.measure_launch angle X1 Y1 X2 Y2 [--level LX1 LY1 LX2 LY2]
    python -m physics.measure_launch summary HITS.csv

HITS.csv columns: stroke, hit, launch_deg, predicted_wall_m, actual_wall_m. The two wall
columns are optional; they feed rule 13. The rules are in decide().
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

from physics.compare import DEFAULT_ELEVATION_DEG, SIDES

# Decision rules 11-14 (docs/elevation-check.md).
KEEP_WITHIN_DEG = 2.0    # 11/12: about 0.25 m on the front wall, roughly twice one hit's measuring error
WALL_TOLERANCE_M = 0.25  # 13: median predicted minus actual front-wall height
MAX_SPREAD_DEG = 5.0     # 14: a hit further than this from the median: one value can't represent them
MIN_HITS = 3             # fewer usable hits: keep, there isn't enough to change anything
GAP_FRAMES = 4           # second ball click: about 0.6 m of flight at 240 fps (use 2 at 120 fps)
CSV_COLUMNS = ("stroke", "hit", "launch_deg", "predicted_wall_m", "actual_wall_m")


def launch_angle_deg(p1, p2, level=None) -> float:
    """Degrees above horizontal of the ball moving from image point p1 to p2 (pixels, y down).

    The ball may travel left or right in the frame. `level` is two points on a horizontal court
    line; the angle is then measured from that line, which corrects a tilted phone.
    """
    mx, my = p2[0] - p1[0], p1[1] - p2[1]  # up is positive
    if mx == 0 and my == 0:
        raise ValueError("the two ball points are the same")
    roll = 0.0
    if level is not None:
        (ax, ay), (bx, by) = sorted(level)  # left point first
        if ax == bx:
            raise ValueError("the level points must be two different points on a horizontal court line")
        roll = math.atan2(ay - by, bx - ax)
    c, s = math.cos(roll), math.sin(roll)
    along, up = mx * c + my * s, -mx * s + my * c  # turned back by the phone's tilt
    return math.degrees(math.atan2(up, abs(along)))


def decide(angles, default: float, wall_errors=()) -> dict:
    """The keep/change call for one stroke, from its hits' launch angles in degrees.

    wall_errors: predicted minus actual front-wall height per hit, metres (rule 13, optional).
    """
    out = {"hits": len(angles), "default": default, "decision": "keep", "newDefault": None, "note": None}
    if len(angles) < MIN_HITS:
        return {**out, "rule": None, "why": f"only {len(angles)} usable hits, need {MIN_HITS}"}
    med = statistics.median(angles)
    spread = max(abs(a - med) for a in angles)
    out.update(median=med, spread=spread, low=min(angles), high=max(angles))
    if spread > MAX_SPREAD_DEG:
        return {**out, "rule": 14, "why": f"hits spread ±{spread:.1f}°, more than ±{MAX_SPREAD_DEG:g}°: "
                                          "one value can't represent them"}
    off = med - default
    if abs(off) >= KEEP_WITHIN_DEG:
        return {**out, "decision": "change", "newDefault": math.floor(med + 0.5), "rule": 12,
                "why": f"median is {off:+.1f}° from the default"}
    out.update(rule=11, why=f"median is within {KEEP_WITHIN_DEG:g}° of the default ({off:+.1f}°)")
    if wall_errors:
        wall = statistics.median(wall_errors)
        if abs(wall) > WALL_TOLERANCE_M:
            out["note"] = (f"rule 13: predicted front-wall height is off by {wall:+.2f} m although the angle "
                           "matches. The error is speed or launch height, not elevation: log it for after the freeze.")
    return out


def summarise(rows: list[dict]) -> dict[str, dict]:
    """decide() for each stroke, from read_hits() rows."""
    angles = {s: [r["launch_deg"] for r in rows if r["stroke"] == s] for s in SIDES}
    walls = {s: [r["predicted_wall_m"] - r["actual_wall_m"] for r in rows if r["stroke"] == s
                 and r["predicted_wall_m"] is not None and r["actual_wall_m"] is not None] for s in SIDES}
    return {s: decide(angles[s], DEFAULT_ELEVATION_DEG[s], walls[s]) for s in SIDES}


def format_summary(results: dict[str, dict]) -> str:
    lines = []
    for stroke, d in results.items():
        if d["rule"] is None:
            lines.append(f"{stroke}: KEEP {d['default']:g}° ({d['why']})")
            continue
        call = f"CHANGE to {d['newDefault']}°" if d["decision"] == "change" else f"KEEP {d['default']:g}°"
        lines.append(f"{stroke}: {d['hits']} hits, median {d['median']:.1f}° ({d['low']:.1f} to {d['high']:.1f}, "
                     f"spread ±{d['spread']:.1f}°), default {d['default']:g}° -> {call} "
                     f"(rule {d['rule']}: {d['why']})")
        if d["note"]:
            lines.append(f"  {d['note']}")
    if any(d["decision"] == "change" for d in results.values()):
        new = {s: float(d["newDefault"] if d["decision"] == "change" else d["default"]) for s, d in results.items()}
        lines.append(f"New line for services/physics/compare.py: DEFAULT_ELEVATION_DEG = {json.dumps(new)}")
    return "\n".join(lines)


def _number(text, where: str, required: bool = False):
    if text is None or not str(text).strip():
        if required:
            raise ValueError(f"{where} is missing")
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{where} must be a number, got {text!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"{where} must be a finite number, got {text!r}")
    return value


def read_hits(path: Path) -> list[dict]:
    """Rows of a hits CSV (CSV_COLUMNS). Blank lines are skipped; anything else unreadable is an error."""
    rows = []
    with open(path, newline="") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            stroke = (row.get("stroke") or "").strip().lower()
            if stroke not in SIDES:
                raise ValueError(f"{path} line {line}: stroke must be forehand or backhand, got {row.get('stroke')!r}")
            rows.append({
                "stroke": stroke,
                "launch_deg": _number(row.get("launch_deg"), f"{path} line {line} launch_deg", required=True),
                "predicted_wall_m": _number(row.get("predicted_wall_m"), f"{path} line {line} predicted_wall_m"),
                "actual_wall_m": _number(row.get("actual_wall_m"), f"{path} line {line} actual_wall_m"),
            })
    return rows


def append_hit(path: Path, stroke: str, hit, angle: float) -> None:
    """Add one measured hit to the CSV, writing the header first if the file is new."""
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(CSV_COLUMNS)
        writer.writerow([stroke, "" if hit is None else hit, f"{angle:.1f}", "", ""])


class _Frames:
    """A clip's frames, read forward once (no seeking), keeping the last `keep` for stepping back."""

    def __init__(self, clip: Path, keep: int = 90):
        import cv2
        self._cv2, self.clip, self.keep = cv2, clip, keep
        self._open()

    def _open(self) -> None:
        self.cap = self._cv2.VideoCapture(str(self.clip))
        if not self.cap.isOpened():
            raise ValueError(f"can't read {self.clip}: check the path, or film with Formats > Most Compatible")
        self.next, self.kept = 0, {}

    def count(self) -> int:
        return int(self.cap.get(self._cv2.CAP_PROP_FRAME_COUNT) or 0)

    def get(self, k: int):
        """Frame k (a BGR image), or None past the end."""
        if k in self.kept:
            return self.kept[k]
        if k < self.next:  # stepped back further than what is kept: read again from the start
            self.cap.release()
            self._open()
        while self.next <= k:
            ok, image = self.cap.read()
            if not ok:
                return None
            self.kept[self.next] = image
            self.next += 1
            if len(self.kept) > self.keep:
                del self.kept[min(self.kept)]
        return self.kept[k]


def click_points(clip: Path, frame: int | None, gap: int = GAP_FRAMES, level: bool = False):
    """Show the clip from `frame` (default: the middle); the user clicks. Needs a screen.

    Returns (level points or None, (frame, x, y) of the first ball click, (frame, x, y) of the second).
    """
    import cv2
    frames = _Frames(clip)
    state = {"i": frame if frame is not None else frames.count() // 2}
    if frames.get(state["i"]) is None:
        raise ValueError(f"frame {state['i']} is past the end of {clip}")
    prompts = (["click a point on a horizontal court line", "click a second point on that line"] if level else [])
    prompts += ["click the ball, first frame clear of the strings", "click the ball again"]
    clicks = []

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((state["i"], float(x), float(y)))

    window = "measure_launch"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)  # keep the aspect: angles stay true
    cv2.setMouseCallback(window, on_mouse)
    try:
        while len(clicks) < len(prompts):
            before = len(clicks)
            cv2.setWindowTitle(window, f"frame {state['i']}: {prompts[before]}  (a/d 1 frame, A/D 10, q quit)")
            cv2.imshow(window, frames.get(state["i"]))
            key = cv2.waitKey(30) & 0xFF
            if key in (27, ord("q")):
                raise SystemExit("measure_launch: cancelled")
            step = {ord("a"): -1, ord("d"): 1, ord("A"): -10, ord("D"): 10}.get(key, 0)
            if len(clicks) > before and len(clicks) == len(prompts) - 1:
                step = gap  # first ball click done: jump ahead to where the second one goes
            target = max(0, state["i"] + step)
            if frames.get(target) is not None:
                state["i"] = target
    finally:
        cv2.destroyWindow(window)
        cv2.waitKey(1)
    return ([(x, y) for _, x, y in clicks[:2]] if level else None), clicks[-2], clicks[-1]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Launch angle from a side-camera clip, and the keep/change call for the ASSUMED elevations.")
    modes = parser.add_subparsers(dest="mode", required=True)
    click = modes.add_parser("click", help="open the clip and click the ball twice (needs a screen)")
    click.add_argument("clip", type=Path)
    click.add_argument("frame", type=int, nargs="?", help="frame to open at, near the hit (default: the middle)")
    click.add_argument("--gap", type=int, default=GAP_FRAMES,
                       help=f"frames between the two ball clicks (default {GAP_FRAMES}; use 2 at 120 fps)")
    click.add_argument("--level", action="store_true", help="first click two points on a horizontal court line")
    angle = modes.add_parser("angle", help="launch angle from two ball positions in pixels")
    angle.add_argument("coords", type=float, nargs=4, metavar=("X1", "Y1", "X2", "Y2"))
    angle.add_argument("--level", type=float, nargs=4, metavar=("LX1", "LY1", "LX2", "LY2"),
                       help="two points on a horizontal court line, to correct a tilted phone")
    for mode in (click, angle):
        mode.add_argument("--stroke", choices=SIDES, help="needed with --csv")
        mode.add_argument("--hit", help="hit number, for the CSV")
        mode.add_argument("--csv", type=Path, help="add this hit to a hits CSV")
    summary = modes.add_parser("summary", help="median, spread and keep/change per stroke from a hits CSV")
    summary.add_argument("hits", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.mode == "summary":
            print(format_summary(summarise(read_hits(args.hits))))
            return
        if args.csv and not args.stroke:
            raise ValueError("--csv needs --stroke forehand or --stroke backhand")
        if args.mode == "angle":
            x1, y1, x2, y2 = args.coords
            level = None if args.level is None else (tuple(args.level[:2]), tuple(args.level[2:]))
            result = launch_angle_deg((x1, y1), (x2, y2), level)
            print(f"launch angle {result:.1f}°")
        else:
            level, (f1, x1, y1), (f2, x2, y2) = click_points(args.clip, args.frame, args.gap, args.level)
            result = launch_angle_deg((x1, y1), (x2, y2), level)
            print(f"launch angle {result:.1f}° (ball clicked at frames {f1} and {f2})")
        if args.csv:
            append_hit(args.csv, args.stroke, args.hit, result)
            print(f"added to {args.csv}")
    except (OSError, ValueError) as e:
        sys.exit(f"measure_launch: {e}")


if __name__ == "__main__":
    main()
