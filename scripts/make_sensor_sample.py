"""Turn one hit (iPhone slow-motion clip + Sensor Logger export) into a saved /ghost sample with
the Wrist sensor panel. Owner: aryan.

Run from the repo root with the services Python environment active:

  python scripts/make_sensor_sample.py <clip.MOV> <sensor.zip> --tap 12.40 --window 81.0 88.0 --stroke backhand

  --tap        Playback second (as QuickTime shows it) of the frame where the hand first lands on
               the strapped phone, for the first tap at the start of the recording.
  --window     Playback seconds around ONE hit, START END (at most 30 real seconds; 6-8 playback
               seconds is plenty: about one second before contact to one after, at 4x).
  --stroke     forehand or backhand (the pipeline's guess is not trusted for a saved sample).

What it does, in order (nothing is written until every step has passed):
 1. Clock. The clip's playback seconds become real seconds: real = playback / slowdown. The
    slow-motion exports from this iPhone run at 4x (each 30 fps frame is 1/120 s), measured on
    the 14 Nov tap session, so --slowdown defaults to 4 for a file of 60 fps or less. A file
    encoded faster than 60 fps needs --slowdown given.
 2. Tap sync (the shadow-session method). The first run of two or more taps on the sensor is
    found, and the first tap is timed from its ONSET (the first sample of the knock, when the
    hand meets the phone, the frame the video shows) rather than its peak, which is often the
    phone's rebound 10-20 ms later. offset = sensor tap - video tap (real seconds).
 3. Pose + physics. The window is cut from the clip (frame-accurate re-encode, sound kept for
    the pipeline's audio contact) and run through the live pipeline (pipeline.live), the same
    path as an upload: MediaPipe pose, swing detection, contact, stroke and hand.
    CHECK THE TAP: the tool saves data/raw/tapcheck_<id>.jpg (git-ignored), the frame where
    each sensor tap should land if --tap is right. The hand must be on the phone in every one.
    Nothing in the data can catch a misread tap: a tap one swing-interval off pairs the hit with
    the neighbouring swing's impact just as neatly.
 4. Wrist. The hit's impact spike (the nearest within 300 ms of the pipeline's contact, through
    the tap clock) is the contact. The pipeline's contact must agree with it within
    --tolerance-ms (100), else it stops. When the pipeline timed contact from the wrist's speed
    peak (no ball sound found), which on the 14 Nov front camera came 135-205 ms after the
    forearm's fastest turn on backhands, --contact-from-impact moves the swing's contactFrame
    to the impact's frame instead (metadata.contactMethod, pipelineContactFrame and
    contactShiftMs say so). Only use it once the tap check is right: with a wrong tap it would
    move contact to the wrong frame. A sound-timed contact is never moved.
    wrist.metrics.wrist_report gives the roll, the turn rate and the camera alignment;
    wrist.fuse.attach_wrist_entries puts the entry on the swing as swing["wrist"]
    (docs/interfaces.md). --shadow (no ball) ignores spikes and times contact from the tap
    alone, and says so ("contact_source": "double tap").
 5. Coach and ghosts. coach.agent.coach_swing plus every fault (coach.faults.detect_faults) on
    the swing WITH its wrist entry, so the coach judges rolled_wrist; physics.compare.compare
    for every fix, as the saved-sample script in app/ghost/README.md does.
 6. Files. swing_<id>.json, coach_<id>.json, compare_<id>_<fix>.json and wrist_<id>.json (the
    wrist_series.json format app/ghost/wrist.ts reads) go in --out-dir (public/swings), and one
    entry naming them, with "wristSeries", is APPENDED to catalogue.json. Every other entry,
    defaultSwing and the top-level fix lists stay exactly as they were, so the demo's hero and
    backhand (scripts/demo_smoke.py) are untouched. Only a sample this script made can be
    replaced, and only with --replace.

Every file is checked with the same parsers demo_smoke.py uses for /ghost before anything is
written. Then open /ghost?swing=<id>: the Wrist sensor panel is on the coach's call step.

Mock data is labelled: a synthetic export (wrist/synth.py) says MOCK in the panel. Ball paths
stay PREDICTED; on a shadow swing (no ball) the court numbers mean nothing, and the label says
"shadow swing".
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services"))

import numpy as np  # noqa: E402

from coach.agent import coach_swing  # noqa: E402
from coach.faults import detect_faults, measure_swing  # noqa: E402
from physics.compare import compare  # noqa: E402
from physics.ghost import FIXES  # noqa: E402
from pipeline.live import LiveOptions, process_live_clip  # noqa: E402
from wrist.fuse import LEVER_M, attach_wrist_entries  # noqa: E402
from wrist.impact import G  # noqa: E402
from wrist.load import Recording, load_recording  # noqa: E402
from wrist.metrics import wrist_report  # noqa: E402
from wrist.sync import (  # noqa: E402
    IMPACT_GUARD_S, MIN_SWING_DPS, SPIKE_K, TAP_GAP_S, TOLERANCE_MS, align, find_impacts, find_spikes,
    spike_signal,
)
import wrist.metrics as _wm  # noqa: E402

# Roll = the gyro integrated about the forearm axis, on every path. main's wrist_report still
# quotes the orientation's twist when the phone's own orientation is used; on the first real
# recording (14 Nov, 50 swings) that twist scattered over +-180 deg (SD 86-156 deg per block)
# while the gyro integral's SD was 5-10 deg. Commit af0b423 (feat/wrist-shadow, not merged yet)
# makes the gyro integral the default; until then this script asks for it. Same signature, so
# this is a no-op once that commit is in main.
_swing_metrics, _roll_series = _wm.swing_metrics, _wm.roll_series
GYRO_ROLL = "gyro integrated about the forearm axis"


def _gyro_swing_metrics(rec, slerp, impact_s, axis, roll_from="gyro", gyro_bias=None):
    m = _swing_metrics(rec, slerp, impact_s, axis, "gyro", gyro_bias)
    if m is not None:
        m["roll_method"] = GYRO_ROLL
    return m


def _gyro_roll_series(rec, slerp, impact_s, axis, roll_from="gyro", gyro_bias=None):
    return _roll_series(rec, slerp, impact_s, axis, "gyro", gyro_bias)


_wm.swing_metrics, _wm.roll_series = _gyro_swing_metrics, _gyro_roll_series

# Tap detection (the same constants as the shadow-session code, services/wrist/shadow.py on
# feat/wrist-shadow): a tap knocks at least MIN_TAP_G with the arm still; spikes closer than
# TAP_MERGE_S are one tap; a tap starts at the first sample above TAP_ONSET_G, at most
# TAP_ONSET_S before its peak.
MIN_TAP_G = 0.5
TAP_MERGE_S = 0.1
TAP_ONSET_G = 0.3
TAP_ONSET_S = 0.05
DEFAULT_SLOWDOWN = 4.0  # these iPhone slow-motion exports: 30 fps frames of 1/120 s (14 Nov taps)
MAX_WINDOW_REAL_S = 30.0  # the live pipeline's limit
IMPACT_SEARCH_S = 0.30  # the hit's impact is the nearest spike this close to the pipeline's contact
SENSOR_CONTACT = "wrist-sensor impact spike (tap-synced)"
ID_RE = re.compile(r"[A-Za-z0-9_-]+")
MADE_BY = "scripts/make_sensor_sample.py"
# Fix size when the coach didn't flag the fault: the catalogue's demoAmounts, else these
# (the saved-sample script's values in app/ghost/README.md).
DEMO_AMOUNT = {"straighten_elbow": 12.0, "bend_elbow": 12.0, "turn_shoulders_more": 15.0,
               "turn_shoulders_less": 15.0, "hold_wrist_cock": 40.0, "close_stance": 15.0}


class SampleError(Exception):
    """A step that can't be trusted: stop before writing anything."""


# ---- 1. clock and 2. tap sync ----

def video_fps(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")[0]
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def tap_onset(rec: Recording, peak_t: float, hp: np.ndarray) -> float:
    i = int(np.argmin(np.abs(rec.t - peak_t)))
    first = i
    while first > 0 and rec.t[i] - rec.t[first - 1] <= TAP_ONSET_S + 1e-9 and hp[first - 1] >= TAP_ONSET_G * G:
        first -= 1
    return float(rec.t[first])


def first_tap_event(rec: Recording, spikes: list) -> list[float] | None:
    """Onset times of the first run of two or more taps, or None."""
    hp = spike_signal(rec)
    taps = []
    for s in spikes:
        if s.gyro_dps >= MIN_SWING_DPS or s.height < MIN_TAP_G * G:
            continue
        if taps and s.t - taps[-1].t < TAP_MERGE_S:
            if s.height > taps[-1].height:
                taps[-1] = s
            continue
        taps.append(s)
    run: list = []
    for s in taps:
        if run and s.t - run[-1].t > TAP_GAP_S[1]:
            if len(run) >= 2:
                break
            run = []
        run.append(s)
    if len(run) < 2:
        return None
    return [round(tap_onset(rec, s.t, hp), 3) for s in run]


def tap_check_image(clip: Path, tap_play: float, taps: list[float], slowdown: float, out: Path) -> list[float]:
    """The frame at each sensor tap's predicted playback time, 3 per row: a misread --tap shows."""
    import cv2

    times = [tap_play + (t - taps[0]) * slowdown for t in taps]
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS)
    tiles = []
    for k, play_s in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(play_s * fps)))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        tile = cv2.resize(frame, (640, int(round(h * 640 / w))), interpolation=cv2.INTER_AREA)
        cv2.putText(tile, f"sensor tap {k + 1}: video {play_s:.3f} s", (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (61, 138, 255), 2, cv2.LINE_AA)
        tiles.append(tile)
    cap.release()
    if not tiles:
        raise SampleError("couldn't read the tap frames from the clip: check --tap")
    while len(tiles) % 3:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack(rows))
    return times


# ---- 3. pose + physics ----

def cut_window(clip: Path, start: float, end: float, out: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{start:.4f}", "-i", str(clip),
                    "-t", f"{end - start:.4f}", "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
                   check=True)


def run_pipeline(window: Path, work: Path, slowdown: float, hand: str, stroke: str) -> list[dict]:
    try:
        report = process_live_clip(window, work / "run", LiveOptions(slowdown=slowdown, hand=hand, stroke=stroke))
    except ValueError as e:
        raise SampleError(f"the pipeline found no usable swing in the window: {e}. Widen --window around "
                          "the hit (about 1 s before contact to 1 s after, in real time) or pick another hit.") from e
    swings = [json.loads((work / "run" / f"{sid}.json").read_text()) for sid in report["swingIds"]]
    rejected = report.get("rejected") or []
    print(f"pipeline: {len(swings)} swing(s) kept, {len(rejected)} rejected"
          + "".join(f"\n  rejected: {r.get('reason')}" for r in rejected))
    return swings


# ---- 6. checks: the browser's parsers ----

def load_demo_smoke():
    spec = importlib.util.spec_from_file_location("demo_smoke", REPO / "scripts" / "demo_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_wrist_series(value: dict, swing_id: str) -> dict:
    """app/ghost/wrist.ts parseWristSeries, and the panel must show (usable entry)."""
    entry = (value.get("swings") or {}).get(swing_id)
    if not isinstance(entry, dict) or entry.get("usable") is not True:
        raise SampleError(f"wrist series has no usable entry for {swing_id}: the panel would be hidden")
    t, deg = entry.get("t_ms"), entry.get("roll_deg")
    ok = (isinstance(t, list) and isinstance(deg, list) and len(t) >= 2 and len(t) == len(deg)
          and all(isinstance(v, (int, float)) and math.isfinite(v) for v in t + deg)
          and all(b > a for a, b in zip(t, t[1:])))
    if not ok or not (isinstance(entry.get("roll_change_deg"), (int, float)) and math.isfinite(entry["roll_change_deg"])):
        raise SampleError("wrist series: t_ms / roll_deg / roll_change_deg don't match what the panel reads")
    grid, speeds = value.get("angular_speed_t_ms"), entry.get("angular_speed_dps")
    if grid is not None and speeds is not None and len(grid) != len(speeds):
        raise SampleError("wrist series: angular_speed_dps must match angular_speed_t_ms")
    return entry


def strict_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def round_swing(swing: dict) -> None:
    for f in swing["frames"]:
        f["joints"] = [[round(c, 4) for c in p] for p in f["joints"]]


# ---- main ----

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", type=Path, help="the slow-motion clip (copy it out of Downloads first)")
    ap.add_argument("sensor", type=Path, help="Sensor Logger export (.zip or folder)")
    ap.add_argument("--tap", type=float, required=True,
                    help="playback s of the frame where the hand first lands on the phone (first tap)")
    ap.add_argument("--window", type=float, nargs=2, required=True, metavar=("START", "END"),
                    help="playback s around one hit")
    ap.add_argument("--stroke", choices=["forehand", "backhand"], required=True)
    ap.add_argument("--shadow", action="store_true", help="a swing with no ball: contact from the tap, spikes ignored")
    ap.add_argument("--contact-from-impact", action="store_true",
                    help="move a wrist-speed contact to the sensor's impact (only after the tap check is right)")
    ap.add_argument("--hand", choices=["R", "L"], default="R")
    ap.add_argument("--slowdown", type=float, default=None,
                    help=f"real s per playback s is 1/slowdown (default {DEFAULT_SLOWDOWN:g} for a <=60 fps file)")
    ap.add_argument("--sensor-tap", type=float, default=None, help="sensor s of the first tap's onset (default: found)")
    ap.add_argument("--id", default=None, help="sample id (letters, digits, _ and -); default from the clip and window")
    ap.add_argument("--label", default=None, help="the swing picker's label")
    ap.add_argument("--out-dir", type=Path, default=REPO / "public" / "swings")
    ap.add_argument("--replace", action="store_true", help="replace a sample this script made with the same id")
    ap.add_argument("--axis", default="y", help="phone axis along the forearm (default y)")
    ap.add_argument("--tolerance-ms", type=float, default=TOLERANCE_MS)
    ap.add_argument("--keep-work", action="store_true", help="keep the temporary pipeline folder")
    ap.add_argument("--check-image", type=Path, default=None,
                    help="where to save the tap check (default data/raw/tapcheck_<id>.jpg, git-ignored)")
    args = ap.parse_args(argv)

    try:
        return make_sample(args)
    except SampleError as e:
        print(f"\nSTOPPED, nothing written: {e}", file=sys.stderr)
        return 1


def make_sample(args: argparse.Namespace) -> int:
    clip, sensor, out_dir = args.clip.resolve(), args.sensor.resolve(), args.out_dir.resolve()
    for p in (clip, sensor):
        if not p.exists():
            raise SampleError(f"{p} doesn't exist")
    if not (out_dir / "catalogue.json").is_file():
        raise SampleError(f"{out_dir} has no catalogue.json")
    start, end = args.window
    if not 0 <= start < end:
        raise SampleError("--window must be START END with 0 <= START < END")

    # 1. clock
    fps = video_fps(clip)
    if args.slowdown is None:
        if fps > 60:
            raise SampleError(f"the clip is encoded at {fps:g} fps, so its playback timing isn't the 4x export's: "
                              "give --slowdown (real seconds = playback seconds / slowdown)")
        slowdown = DEFAULT_SLOWDOWN
    else:
        slowdown = args.slowdown
    if not 0 < slowdown <= 16:
        raise SampleError("--slowdown must be in (0, 16]")
    if (end - start) / slowdown > MAX_WINDOW_REAL_S:
        raise SampleError(f"the window is {(end - start) / slowdown:.1f} real s; the pipeline takes at most "
                          f"{MAX_WINDOW_REAL_S:g}. Keep it to one hit.")
    print(f"clock: {clip.name} at {fps:g} fps, slowdown {slowdown:g} ({'given' if args.slowdown else 'default'}): "
          f"real s = playback s / {slowdown:g}")

    # 2. tap sync
    rec = load_recording(sensor)
    spikes = find_spikes(rec, SPIKE_K)
    taps = first_tap_event(rec, spikes)
    if args.sensor_tap is not None:
        sensor_tap = args.sensor_tap
        taps = taps or [sensor_tap]
    elif taps is None:
        raise SampleError("no run of two or more taps found in the sensor recording: pass --sensor-tap")
    else:
        sensor_tap = taps[0]
    video_tap_real = args.tap / slowdown
    offset = sensor_tap - video_tap_real
    print(f"sensor: {rec.source}, {rec.rate_hz:.0f} Hz, {rec.t[0]:.1f}-{rec.t[-1]:.1f} s{' (MOCK)' if rec.mock else ''}")
    print(f"tap sync: sensor first tap onset {sensor_tap:.3f} s ({len(taps)} taps), video tap {args.tap:.3f} playback s "
          f"= {video_tap_real:.3f} real s -> offset {offset:+.3f} s (sensor = real video + offset)")

    sample_id = args.id or re.sub(r"[^A-Za-z0-9_-]", "_", f"sensor_{clip.stem}_{start:.0f}s")
    if not ID_RE.fullmatch(sample_id):
        raise SampleError("--id may only use letters, digits, _ and -")
    check_path = (args.check_image or REPO / "data" / "raw" / f"tapcheck_{sample_id}.jpg").resolve()
    tap_times = tap_check_image(clip, args.tap, taps, slowdown, check_path)
    print(f"TAP CHECK: the hand should land on the phone at video {', '.join(f'{t:.3f}' for t in tap_times)} s "
          f"-> look at {check_path}")

    catalogue_path = out_dir / "catalogue.json"
    catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
    existing = next((i for i, s in enumerate(catalogue["swings"]) if s.get("id") == sample_id), None)
    if existing is not None:
        old = catalogue["swings"][existing]
        if old.get("madeBy") != MADE_BY or sample_id == catalogue.get("defaultSwing"):
            raise SampleError(f"{sample_id!r} is an existing sample this script didn't make: pick another --id")
        if not args.replace:
            raise SampleError(f"{sample_id!r} already exists: pass --replace to overwrite it, or pick another --id")

    work = Path(tempfile.mkdtemp(prefix="sensor-sample-"))
    try:
        # 3. pose + physics
        window = work / "window.mp4"
        cut_window(clip, start, end, window)
        swings = run_pipeline(window, work, slowdown, args.hand, args.stroke)

        # 4. wrist: pair the hit's impact with the pipeline's contact through the tap clock
        events = [(s, start / slowdown + s["metadata"]["sourceContactSeconds"]) for s in swings]
        impacts, rejected = find_impacts(spikes, max(taps) + IMPACT_GUARD_S)
        impact_t = np.array([s.t for s in impacts])

        def impact_gap(contact_real: float) -> float:
            return float(np.min(np.abs(impact_t - (contact_real + offset)))) if impact_t.size else math.inf

        swing, contact_real = min(events, key=lambda e: (impact_gap(e[1]), abs(e[1] - (start + end) / 2 / slowdown)))
        swing["id"] = sample_id
        md = swing["metadata"]
        md["sourceClip"] = clip.name
        md["sourceWindowPlaybackSeconds"] = [start, end]
        md["wristSync"] = {"method": "first tap's onset matched to the video frame where the hand lands",
                           "slowdown": slowdown, "videoTapPlaybackSeconds": args.tap,
                           "sensorTapSeconds": round(sensor_tap, 3), "offsetSeconds": round(offset, 4)}
        if args.shadow:
            impact_t = np.array([])
        else:
            predicted = contact_real + offset
            near = impact_t[np.abs(impact_t - predicted) <= IMPACT_SEARCH_S]
            if near.size == 0:
                raise SampleError(f"no impact spike within {IMPACT_SEARCH_S * 1000:.0f} ms of the hit's video contact: "
                                  "check --tap and --slowdown, or pass --shadow for a swing with no ball")
            hit = float(near[np.argmin(np.abs(near - predicted))])
            gap_ms = (hit - predicted) * 1000
            md["pipelineContactMinusImpactMs"] = round(-gap_ms, 1)
            print(f"impact: sensor {hit:.3f} s; the pipeline's contact ({md.get('contactMethod')}) is "
                  f"{-gap_ms:+.0f} ms from it")
            if abs(gap_ms) > args.tolerance_ms:
                if md.get("contactMethod") == "audio-transient":
                    raise SampleError(f"the ball's sound and the sensor's impact are {gap_ms:+.0f} ms apart (more than "
                                      f"{args.tolerance_ms:.0f}): the sync is wrong. Check --tap (the frame the hand "
                                      "lands), --slowdown, and that the clip and export are from the same session")
                if not args.contact_from_impact:
                    raise SampleError(f"the pipeline timed contact from the wrist's speed peak (no ball sound found) and "
                                      f"it is {-gap_ms:+.0f} ms from the sensor's impact (more than "
                                      f"{args.tolerance_ms:.0f}). Open {check_path}: if the hand is on the phone in "
                                      "every frame, rerun with --contact-from-impact; if not, fix --tap")
                t = np.array([f["t"] for f in swing["frames"]])
                rel = hit - offset - start / slowdown - md["realStartSeconds"]
                new_cf = int(np.argmin(np.abs(t - rel)))
                if not (0 < new_cf < len(t) - 1) or abs(t[new_cf] - rel) > 1.5 / swing["fpsReal"]:
                    raise SampleError("the impact falls outside the pipeline's swing frames: widen --window")
                md.update({"pipelineContactFrame": swing["contactFrame"], "pipelineContactMethod": md.get("contactMethod"),
                           "contactShiftMs": round((t[new_cf] - t[swing["contactFrame"]]) * 1000, 1),
                           "contactMethod": SENSOR_CONTACT})
                swing["contactFrame"] = new_cf
                md["sourceContactFrame"] = md.get("sourceStartFrame", 0) + new_cf
                md["sourceContactSeconds"] = md["realStartSeconds"] + float(t[new_cf])
                md["sourceContactPlaybackSeconds"] = md["sourceContactSeconds"] * slowdown
                contact_real = start / slowdown + md["sourceContactSeconds"]
                print(f"contact moved to the impact: frame {md['pipelineContactFrame']} -> {new_cf} "
                      f"({md['contactShiftMs']:+.0f} ms)")
        speed = np.degrees(np.linalg.norm(rec.gyro, axis=1))

        def swinging(t_s: float) -> bool:
            near = np.abs(rec.t - t_s) <= args.tolerance_ms / 1000
            return bool(rec.t[0] <= t_s <= rec.t[-1] and near.any() and speed[near].max() >= MIN_SWING_DPS)

        alignment = align(list(impact_t), [(sample_id, contact_real)], sensor_tap, video_tap_real, 1.0,
                          args.tolerance_ms, swinging)
        pair = next((p for p in alignment["pairs"] if p["swing"] == sample_id), None)
        warnings = []
        if pair is not None:
            if not pair["ok"]:
                raise SampleError(f"the nearest impact is {pair['error_ms']:+.0f} ms from where the video puts contact "
                                  f"(more than {args.tolerance_ms:.0f} ms): check --tap (the frame the hand lands), "
                                  "--slowdown, and that this clip and export are from the same session")
            print(f"contact: video {(contact_real * slowdown):.3f} playback s ({swing['metadata'].get('contactMethod')}); "
                  f"sensor impact {pair['impact_s']:.3f} s, alignment error {pair['error_ms']:+.1f} ms")
        elif alignment["tap_only"]:
            warnings.append("no impact near this swing (shadow swing?): contact timed from the tap alone, so its "
                            "window carries the sync and video-contact error")
            print(f"contact: video {(contact_real * slowdown):.3f} playback s, NO impact: timed from the tap alone")
        else:
            raise SampleError("no impact paired with this swing, and the forearm wasn't swinging at the tap-predicted "
                              "contact: check --tap, --slowdown and --window")
        sync = {"taps_s": taps, "video_tap_s": video_tap_real, "spike_threshold_k": SPIKE_K,
                "impacts": {p["swing"]: p["impact_s"] for p in alignment["pairs"] if p["ok"]},
                "tap_only": {t["swing"]: t["contact_s"] for t in alignment["tap_only"]},
                "rejected_spikes": rejected, "alignment": alignment, "warnings": warnings,
                "tap_method": "first tap's onset, matched to the video frame where the hand lands"}
        metrics, series, filled = wrist_report(rec, sync, args.axis, {sample_id: swing}, LEVER_M)
        entry = metrics["swings"].get(sample_id) or {}
        if not entry.get("usable"):
            raise SampleError(f"the wrist entry isn't usable: {entry.get('skip_reason')}")
        swing = attach_wrist_entries({sample_id: swing}, metrics, filled)[sample_id]
        fill = entry.get("occlusion_fill") or {}
        print(f"wrist: roll {entry['roll_change_deg']:+.1f} deg over {entry['window_ms']} ms, peak turn "
              f"{entry['peak_angular_speed_dps']:.0f} deg/s, contact from {entry['contact_source']}; camera agreement "
              f"{(fill.get('agreement_deg') or {}).get('median')} deg; fill applied {fill.get('applied')}")
        for w in metrics.get("warnings", []):
            print(f"  warning: {w}")

        # 5. coach and ghosts, on the swing with its wrist entry
        stroke, fps_real = args.stroke, swing.get("fpsReal")
        swing["stroke"] = swing["metadata"]["stroke"] = stroke
        coach = coach_swing(swing, stroke, fps_real)
        coach["faults"] = detect_faults(swing, metrics=measure_swing(swing, stroke, fps_real))
        flagged = {f["fix"]: f for f in coach["faults"]}
        demo = {**DEMO_AMOUNT, **(catalogue.get("demoAmounts") or {})}
        fixes: dict[str, dict] = {}
        compares: dict[str, dict] = {}
        for fix in FIXES:
            amount = flagged[fix]["fix_amount"] if fix in flagged else demo.get(fix)
            if amount is None:
                continue
            row: dict[str, Any] = {"amount": amount, "flagged": fix in flagged}
            try:
                result = compare(swing, fix, amount, fps_real=fps_real, hand=args.hand)
            except ValueError as e:
                row["error"] = str(e)
            else:
                round_swing(result["you"]["swing"])
                round_swing(result["ghost"]["swing"])
                row["file"] = f"compare_{sample_id}_{fix}.json"
                compares[row["file"]] = result
            fixes[fix] = row
        print(f"coach: fault {(coach.get('fault') or {}).get('id') if isinstance(coach.get('fault'), dict) else coach.get('fault')}; "
              f"all faults {[f['id'] for f in coach['faults']]}; ghosts {len(compares)}/{len(fixes)}")

        # 6. files: checked with the browser's parsers before anything is written
        round_swing(swing)
        shadow = pair is None
        label = args.label or (f"{stroke.capitalize()} · wrist sensor · "
                               f"{'shadow swing (no ball), contact from the tap' if shadow else 'real hit'} · "
                               f"iPhone {fps * slowdown:g} fps ({clip.stem} {int(contact_real * slowdown // 60):02d}:"
                               f"{contact_real * slowdown % 60:04.1f})" + (" · MOCK sensor" if rec.mock else ""))
        new_entry = {"id": sample_id, "label": label, "stroke": stroke, "swing": f"swing_{sample_id}.json",
                     "coach": f"coach_{sample_id}.json", "fixes": fixes, "wristSeries": f"wrist_{sample_id}.json",
                     "madeBy": MADE_BY}
        files = {new_entry["swing"]: swing, new_entry["coach"]: coach, new_entry["wristSeries"]: series, **compares}
        swings_list = list(catalogue["swings"])
        if existing is None:
            swings_list.append(new_entry)
        else:
            swings_list[existing] = new_entry
        new_catalogue = {**catalogue, "swings": swings_list}

        smoke = load_demo_smoke()
        text = {name: strict_json(data) for name, data in files.items()}
        cat_text = strict_json(new_catalogue)
        # The repo is public: no local path (home folder, temp folders) may end up in a sample.
        for name, body in {**text, "catalogue.json": cat_text}.items():
            for private in (str(Path.home()), str(work), "/private/", tempfile.gettempdir()):
                if private in body:
                    raise SampleError(f"internal: {name} would contain a local path ({private!r})")
        try:
            smoke.parse_catalogue(json.loads(cat_text))
            smoke.parse_swing(json.loads(text[new_entry["swing"]]))
            smoke.parse_coach(json.loads(text[new_entry["coach"]]))
            for name in compares:
                smoke.parse_compare(json.loads(text[name]))
        except smoke.DataError as e:
            raise SampleError(f"a file /ghost would refuse: {e}") from e
        check_wrist_series(json.loads(text[new_entry["wristSeries"]]), sample_id)
        if new_catalogue.get("defaultSwing") != catalogue.get("defaultSwing") or \
                [s for s in swings_list if s["id"] != sample_id] != [s for s in catalogue["swings"] if s["id"] != sample_id]:
            raise SampleError("internal: the other samples would change")

        for name, body in text.items():
            (out_dir / name).write_text(body, encoding="utf-8")
        tmp = catalogue_path.with_suffix(".json.tmp")
        tmp.write_text(cat_text, encoding="utf-8")
        tmp.replace(catalogue_path)
    finally:
        if args.keep_work:
            print(f"work folder kept: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    print(f"\nwrote {len(text)} files to {out_dir} and {'replaced' if existing is not None else 'appended'} "
          f"catalogue entry {sample_id!r} (other samples and defaultSwing unchanged)")
    print(f"open: http://localhost:3000/ghost?swing={sample_id}  (Wrist sensor panel on the coach's call step)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
