"""Check POST /process/multi (a second camera angle and a wrist sensor file) on a running service.

Usage, from the repo root, with the Python service running:

  python scripts/multi_upload_check.py VIDEO_A VIDEO_B SENSOR --slowdown-a 4 --slowdown-b 1
  python scripts/multi_upload_check.py VIDEO_A VIDEO_B SENSOR --service http://localhost:8000 \
      --slowdown-a 4 --slowdown-b 1 --offset-b -0.25

Windows: py scripts\\multi_upload_check.py VIDEO_A VIDEO_B SENSOR --slowdown-a 4 --slowdown-b 1

Pass --slowdown-a and --slowdown-b until Dev's fix to Auto slowdown lands. With Auto,
/process/multi took AirDropped iPhone slow-motion clips as real time (slowdown 1) and answered
422 (found testing #111), so case 1 would fail for the wrong reason. For the 2116 pair: the iPhone
clip is 4x slow motion and the iPad clip real time, so --slowdown-a 4 --slowdown-b 1.

Needs Python 3 and `requests` only. requests isn't in services/requirements.txt: if it's
missing, `pip install requests` (the script says so and stops).

  VIDEO_A  camera A: IMG_2116.MOV, the iPhone slow-motion angle of the saved two-camera sample
           sample_2116_backhand_stereo (services/physics/validation/swings.json).
  VIDEO_B  camera B: IMG_5342, the iPad angle of the same session (data/labels/labels.csv,
           "iPad IMG_5342" on every IMG_2116 row).
  SENSOR   a Sensor Logger export: a .csv, or the CSV zip that services/wrist/README.md records
           into data/raw/wrist/. The docs record no sensor file for the IMG_2116 session, so a
           file from another session may not sync with these clips; then case 3 fails on
           "wrist data", which says the file didn't match, not that the route is broken.

The clips and the sensor file are only read and uploaded: never copied, never committed
(data/raw/ is git-ignored). The service's 250 MB limit covers the whole request, so all the files
one case sends must be 250 MB or less together: cut one swing from both angles over the same
seconds first. The script checks every case's total before uploading anything. Each case that
succeeds saves swings, so
start the service with a throwaway GHOST_SWINGS_DIR, not the demo's.

Four cases, one POST /process/multi each, run one after another (the service takes one at a time):

  1  VIDEO_A only                   depth "estimated (1 camera)",     no wrist data
  2  VIDEO_A + VIDEO_B              depth "triangulated (2 cameras)", no wrist data
  3  VIDEO_A + VIDEO_B + SENSOR     depth "triangulated (2 cameras)", wrist data
  4  VIDEO_A + VIDEO_B + broken CSV depth "triangulated (2 cameras)", no wrist data, a warning

Checks in every case:
  - HTTP 200. 201 passes too: POST /process answers 201 Created.
  - The same top-level keys as a /process response (PROCESS_KEYS, from services/pipeline/live.py).
    A missing key fails; extra keys (such as "warnings") are listed, not failed.
  - The depth label, from the saved swing (GET /swings/{swingId}): swing "source" and
    metadata "reconstruction"/"depth" are "mono"/"estimated" for one camera and "stereo" for two.
    A two-camera upload can fall back to one camera; the line then shows metadata.fallbackReason.
  - Usable wrist data only in case 3: the saved swing's "wrist" with "usable": true. A swing the
    sensor couldn't be matched to carries {"usable": false, "skip_reason": ...}
    (docs/interfaces.md); that counts as no wrist data, and the line shows its skip_reason.
  - Case 4: the answer is a success with a non-empty "warnings", not an error status.

It prints PASS or FAIL per case, then exits 0 if all four pass and 1 if any fails. Before
uploading anything it POSTs an empty form to the route. If the service has no /process/multi yet
(404 or 405), it prints "route not found", uploads nothing and exits 2. It exits 3 if the service
isn't running, and 4 if a file is missing or a case's files are over 250 MB together.

The form field names are the ones /upload sends in PR #107 (FIELD_* below). Change them here if
Dev's route names them differently.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("This check needs the requests package: pip install requests")

# Top-level keys of a POST /process answer (services/pipeline/live.py, process_live_clip):
# the pipeline report (process.py swings_from_raw), the run's session/files/status, and live.py's own.
PROCESS_KEYS = frozenset({
    "detected", "written", "rejected", "sync", "calibration",
    "session", "files", "status",
    "swingId", "swingIds", "coach", "compare", "webPath",
})

# Form fields, as /upload sends them to /process/multi in PR #107.
FIELD_VIDEO_A, FIELD_VIDEO_B, FIELD_SENSOR = "video_a", "video_b", "sensor_csv"
FIELD_SLOWDOWN_A, FIELD_SLOWDOWN_B, FIELD_OFFSET_B = "slowdown_a", "slowdown_b", "offset_b_s"

# The service's upload limit (services/pipeline/server.py). On /process/multi it covers the whole
# request, so it applies to all the files one case sends, together.
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
ONE_CAMERA, TWO_CAMERAS = "estimated (1 camera)", "triangulated (2 cameras)"
VIDEO_TYPES = {".mov": "video/quicktime", ".mp4": "video/mp4", ".m4v": "video/x-m4v", ".avi": "video/x-msvideo"}
SENSOR_TYPES = {".csv": "text/csv", ".zip": "application/zip"}

# Case 4's file: shaped like a CSV, but not a Sensor Logger export (wrong columns, no numbers).
BROKEN_CSV = "this is not a sensor logger export\nnot,a,number\n???,,\n"

EXIT_ROUTE_NOT_FOUND, EXIT_NO_SERVICE, EXIT_BAD_FILES = 2, 3, 4


def main() -> int:
    args = parse_args()
    base = args.service.rstrip("/")
    print(f"POST {base}/process/multi")

    try:
        requests.get(f"{base}/health", timeout=5)
        # An empty form uploads nothing: a missing route answers 404 (405 if only another method
        # exists), and the real route rejects it (422) before doing any work.
        probe = requests.post(f"{base}/process/multi", data={}, timeout=30)
    except requests.RequestException:
        print(f"Service not reachable at {base}. Start it from services/:\n"
              "  python -m uvicorn pipeline.server:app --port 8000")
        return EXIT_NO_SERVICE
    if probe.status_code in (404, 405):
        print(f"route not found: this service has no POST /process/multi yet "
              f"(HTTP {probe.status_code} {detail(probe)}). Nothing was uploaded.")
        for number, name, *_ in CASES:
            print(f"  case {number}  {name:<34} NOT RUN")
        return EXIT_ROUTE_NOT_FOUND

    problems = check_files(args)
    if problems:
        print("\n".join(problems))
        return EXIT_BAD_FILES

    with tempfile.TemporaryDirectory(prefix="multi-upload-check-") as temporary:
        broken = Path(temporary) / "broken_sensor.csv"
        broken.write_text(BROKEN_CSV, encoding="utf-8")
        files = {"a": args.video_a, "b": args.video_b, "sensor": args.sensor, "broken": broken}
        passed = 0
        for number, name, parts, depth, wrist, warning in CASES:
            failures, note = run_case(base, args, [files[p] for p in parts], depth, wrist, warning)
            passed += not failures
            print(f"  case {number}  {name:<34} {'FAIL' if failures else 'PASS'}  {note}")
            for failure in failures:
                print(f"      - {failure}")
    print(f"{passed} of {len(CASES)} cases passed")
    return 0 if passed == len(CASES) else 1


# number, name, files (camera A, camera B, sensor file), expected depth, wrist data?, warning?
CASES = [
    (1, "one video", ("a",), ONE_CAMERA, False, False),
    (2, "two videos", ("a", "b"), TWO_CAMERAS, False, False),
    (3, "two videos + wrist sensor", ("a", "b", "sensor"), TWO_CAMERAS, True, False),
    (4, "two videos + broken sensor CSV", ("a", "b", "broken"), TWO_CAMERAS, False, True),
]


def run_case(base: str, args: argparse.Namespace, paths: list[Path], want_depth: str,
             want_wrist: bool, want_warning: bool) -> tuple[list[str], str]:
    fields = {}
    if args.slowdown_a is not None:
        fields[FIELD_SLOWDOWN_A] = str(args.slowdown_a)
    if len(paths) > 1:
        if args.slowdown_b is not None:
            fields[FIELD_SLOWDOWN_B] = str(args.slowdown_b)
        if args.offset_b is not None:
            fields[FIELD_OFFSET_B] = str(args.offset_b)

    started = time.monotonic()
    handles = []
    try:
        uploads = {}
        for field, path in zip((FIELD_VIDEO_A, FIELD_VIDEO_B, FIELD_SENSOR), paths):
            types = SENSOR_TYPES if field == FIELD_SENSOR else VIDEO_TYPES
            handle = path.open("rb")
            handles.append(handle)
            uploads[field] = (path.name, handle, types.get(path.suffix.lower(), "application/octet-stream"))
        response = requests.post(f"{base}/process/multi", data=fields, files=uploads, timeout=args.timeout)
    except requests.Timeout:
        return [f"no answer within {args.timeout:g} s (raise --timeout for long clips)"], ""
    except requests.RequestException as exc:
        return [f"request failed: {exc.__class__.__name__}"], ""
    finally:
        for handle in handles:
            handle.close()
    took = f"{time.monotonic() - started:.1f} s"
    status = f"(HTTP {response.status_code}, {took})"

    if response.status_code in (404, 405):
        return ["route not found"], status
    if response.status_code not in (200, 201):
        what = "an error, not a warning" if want_warning else "not a success"
        return [f"HTTP {response.status_code}, {what}: {detail(response)}"], status
    try:
        body = response.json()
    except ValueError:
        return ["the body isn't JSON"], status
    if not isinstance(body, dict):
        return ["the body isn't a JSON object"], status

    failures = []
    keys = set(body)
    if missing := sorted(PROCESS_KEYS - keys):
        failures.append(f"missing /process keys: {', '.join(missing)}")
    extra = sorted(keys - PROCESS_KEYS)

    swing = saved_swing(base, body.get("swingId"))
    if isinstance(swing, str):
        failures.append(swing)
        swing = {}
    depth, fallback = depth_label(body, swing)
    if depth != want_depth:
        failures.append(f"depth: expected {want_depth}, got {depth}"
                        + (f" (fallbackReason: {fallback})" if fallback else ""))

    has_wrist = isinstance(swing.get("wrist"), dict) and swing["wrist"].get("usable") is True
    # A wrist block that isn't usable: why the sensor wasn't matched to this swing.
    skipped = None
    if isinstance(swing.get("wrist"), dict) and not has_wrist:
        skipped = swing["wrist"].get("skip_reason") or "no skip_reason given"
    if has_wrist != want_wrist:
        if want_wrist:
            failures.append("wrist data: expected usable wrist data in the saved swing, but "
                            + (f"its wrist block isn't usable ({skipped})" if skipped
                               else "the swing has no wrist block"))
        else:
            failures.append("wrist data: the saved swing has usable wrist data, expected none")

    warnings = body.get("warnings")
    warnings = [warnings] if isinstance(warnings, str) else list(warnings or [])
    if want_warning and not warnings:
        failures.append("expected a warning about the broken CSV; the answer has no \"warnings\"")

    wrist_note = "yes" if has_wrist else f"no (not usable: {skipped})" if skipped else "no"
    note = f"{status} depth: {depth}; wrist data: {wrist_note}"
    if warnings:
        note += f"; warnings: {' | '.join(str(w) for w in warnings)}"
    if extra:
        note += f"; extra keys: {', '.join(extra)}"
    return failures, note


def saved_swing(base: str, swing_id: object) -> dict | str:
    """The saved swing the answer points to, or a failure message."""
    if not isinstance(swing_id, str) or not swing_id:
        return "no swingId in the answer, so the saved swing can't be read"
    try:
        response = requests.get(f"{base}/swings/{swing_id}", timeout=30)
    except requests.RequestException as exc:
        return f"GET /swings/{swing_id} failed: {exc.__class__.__name__}"
    if response.status_code != 200:
        return f"GET /swings/{swing_id}: HTTP {response.status_code} {detail(response)}"
    try:
        swing = response.json()
    except ValueError:
        return f"GET /swings/{swing_id}: the body isn't JSON"
    return swing if isinstance(swing, dict) else f"GET /swings/{swing_id}: not a JSON object"


def depth_label(body: dict, swing: dict) -> tuple[str, str | None]:
    """One camera or two, from the answer's own label if it has one, else the saved swing."""
    metadata = swing.get("metadata") if isinstance(swing.get("metadata"), dict) else {}
    fallback = metadata.get("fallbackReason")
    for value in (body.get("depth"), body.get("depthLabel")):
        if value in (ONE_CAMERA, TWO_CAMERAS):
            return value, fallback
    seen = {str(v).lower() for v in (swing.get("source"), metadata.get("reconstruction"),
                                     metadata.get("depth")) if v}
    if seen & {"stereo", "triangulated"}:
        return TWO_CAMERAS, fallback
    if seen & {"mono", "estimated"}:
        return ONE_CAMERA, fallback
    return f"unknown (source/reconstruction/depth: {sorted(seen) or 'none'})", fallback


def check_files(args: argparse.Namespace) -> list[str]:
    """Every file exists with a known type, and each case's files fit the limit together."""
    problems, sizes = [], {"broken": len(BROKEN_CSV.encode("utf-8"))}
    for key, label, path, types in (("a", "VIDEO_A", args.video_a, VIDEO_TYPES),
                                    ("b", "VIDEO_B", args.video_b, VIDEO_TYPES),
                                    ("sensor", "SENSOR", args.sensor, SENSOR_TYPES)):
        if not path.is_file():
            problems.append(f"{label}: no such file: {path}")
            continue
        if path.suffix.lower() not in types:
            problems.append(f"{label}: {path.name} should be {', '.join(sorted(types))}")
        sizes[key] = path.stat().st_size
    if problems:
        return problems
    for number, name, parts, *_ in CASES:
        total = sum(sizes[p] for p in parts)
        if total > MAX_UPLOAD_BYTES:
            problems.append(f"case {number} ({name}): its files are {total / 2**20:.0f} MB together, over the "
                            "250 MB limit for one request. Cut one swing from both angles over the same seconds.")
    return problems


def detail(response: requests.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    except ValueError:
        pass
    return response.text[:200].strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check POST /process/multi on a running service.")
    parser.add_argument("video_a", type=Path, help="camera A clip, e.g. IMG_2116.MOV (iPhone)")
    parser.add_argument("video_b", type=Path, help="camera B clip, e.g. IMG_5342 (iPad)")
    parser.add_argument("sensor", type=Path, help="a Sensor Logger export (.csv or CSV .zip)")
    parser.add_argument("--service", default=os.environ.get("GHOST_SERVICE", "http://localhost:8000"))
    parser.add_argument("--slowdown-a", type=float,
                        help="camera A's slowdown, e.g. 4 for the iPhone clip (default: the service's Auto; "
                             "pass it until Auto is fixed)")
    parser.add_argument("--slowdown-b", type=float,
                        help="camera B's slowdown, e.g. 1 for the iPad clip (default: the service's Auto; "
                             "pass it until Auto is fixed)")
    parser.add_argument("--offset-b", type=float, help="camera B's offset in seconds (default: none sent)")
    parser.add_argument("--timeout", type=float, default=900, help="seconds to wait per case (default 900)")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
