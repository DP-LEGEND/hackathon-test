"""Reliability count: how many single-swing clips run end to end through the upload path.

Sends every clip in a folder, one at a time, to the local service's POST /process (the endpoint
/upload uses). Prints one row per clip, then one summary line:

  N of M uploads ran end to end with a coach call and ghost

"ran ok?" is yes when the service answered 201 with a coach result and a compare result, and both
balls (yours and the ghost's) are PREDICTED paths. A refused upload shows the service's own error
text in the error column.

The summary counts an upload only when all of these hold:
  - it ran ok;
  - the coach named a fault (its call, the top fault);
  - the ghost makes the coach's ghost_fix: the compare's fix id equals coach.ghost_fix, the amount
    is above 0, and compare.noCorrection is false.
When the top fault can't be animated, the coach's ghost shows its worst fault that can be
(ghost_fault, whose fix is ghost_fix). The coach call column then reads
"<top fault> (ghost shows <ghost_fault>)", and the row counts only if the compare made that fix.
A clean swing runs ok, but the coach finds no fault and the ghost doesn't change, so it isn't
counted. Its error column says "not counted: ..." and why. The line above the summary gives the
plain ran-ok count.

Read-only. Clips are only opened for reading, and the script writes no files. It snapshots this
repo's public/swings before the first upload and again after every clip, and stops with exit 1 if
anything there changed.

The service saves each upload under its GHOST_SWINGS_DIR (default data/processed, git-ignored), and
/ghost lists what it saved. To keep the count out of the demo's swing list, run a second service with
a temp folder. Start it from services/:

  GHOST_SWINGS_DIR="$(mktemp -d)" python -m uvicorn pipeline.server:app --port 8014

then, from the repo root in a second terminal:

  python3 scripts/reliability_count.py data/raw/reliability --service http://localhost:8014

Windows (PowerShell): py scripts\\reliability_count.py data\\raw\\reliability --service http://localhost:8014

Which files count as clips:
  - .mov, .mp4, .m4v or .avi (any case), directly inside the folder, in name order;
  - hidden files and everything else are skipped and listed;
  - a clip over the service's 250 MB limit is not sent, and counts as not end to end.
--slowdown, --hand and --stroke go with every clip. Without them the service detects each one, as
/upload's Auto does.

Exit 0 when the count finished, whatever N is. Exit 1 when the service isn't answering, stops
answering mid-run, or public/swings changed. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PUBLIC_SWINGS = REPO / "public" / "swings"
VIDEO_SUFFIXES = (".mov", ".mp4", ".m4v", ".avi")  # what POST /process accepts
MAX_UPLOAD_BYTES = 250 * 1024 * 1024  # services/pipeline/server.py MAX_UPLOAD_BYTES
CHUNK_BYTES = 1024 * 1024
TIMEOUT_S = 900.0     # one clip: the service answers only when pose, coach and ghost are done
BUSY_WAIT_S = 600.0   # how long to keep retrying while the service is busy with another clip (429)
BUSY_RETRY_S = 15.0
HEALTH_TIMEOUT_S = 5.0
SUMMARY = "{n} of {m} uploads ran end to end with a coach call and ghost"
HEADERS = ("#", "clip", "ran ok?", "stroke detected", "coach call", "ghost_fix",
           "front wall you→ghost (PREDICTED)", "time", "error")


@dataclass
class Row:
    clip: str
    ran: bool = False  # 201, coach and compare results, both balls PREDICTED
    ok: bool = False   # ran, the coach named a fault, and the ghost makes the coach's ghost_fix: counted
    stroke: str = "-"
    call: str = "-"
    ghost_fix: str = "-"
    wall: str = "-"
    seconds: float | None = None
    error: str = ""


class ServiceDown(Exception):
    """The service stopped answering, so the rest of the count would say nothing about the clips."""


def list_clips(folder: Path) -> tuple[list[Path], list[str]]:
    """The clips directly inside folder in name order, and the names of everything else skipped."""
    clips, skipped = [], []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in VIDEO_SUFFIXES:
            clips.append(path)
        else:
            skipped.append(path.name)
    return clips, skipped


def snapshot(folder: Path) -> dict[str, tuple[int, int]]:
    """Every file under folder with its size and modification time, to tell whether anything changed."""
    if not folder.is_dir():
        return {}
    files = {}
    for path in folder.rglob("*"):
        if path.is_file():
            stat = path.stat()
            files[path.relative_to(folder).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return files


def changes(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> list[str]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return ([f"added {k}" for k in added] + [f"removed {k}" for k in removed]
            + [f"changed {k}" for k in changed])


def multipart(clip: Path, fields: dict[str, str]) -> tuple[str, int, Callable[[], Iterator[bytes]]]:
    """A streamed multipart body: the form fields, then the clip read in 1 MB chunks (never all at once)."""
    boundary = f"ghost-reliability-{uuid.uuid4().hex}"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", clip.name)  # the service only reads the suffix
    head = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
                    for key, value in fields.items())
    head += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
             "Content-Type: application/octet-stream\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()

    def body() -> Iterator[bytes]:
        yield head
        with clip.open("rb") as stream:
            while chunk := stream.read(CHUNK_BYTES):
                yield chunk
        yield tail

    return f"multipart/form-data; boundary={boundary}", len(head) + clip.stat().st_size + len(tail), body


def _json(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return raw.decode("utf-8", "replace").strip()[:300]


def post_clip(service: str, clip: Path, fields: dict[str, str], timeout: float) -> tuple[int, object]:
    """POST one clip to /process. Returns (HTTP status, parsed body); connection errors are raised."""
    content_type, length, body = multipart(clip, fields)
    request = urllib.request.Request(f"{service}/process", data=body(), method="POST", headers={
        "Content-Type": content_type, "Content-Length": str(length), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _json(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _json(exc.read())


def healthy(service: str) -> str | None:
    """None when GET /health answers {"ok": true}, else what went wrong."""
    try:
        with urllib.request.urlopen(f"{service}/health", timeout=HEALTH_TIMEOUT_S) as response:
            body = _json(response.read())
    except urllib.error.HTTPError as exc:
        return f"/health answered HTTP {exc.code}"
    except (urllib.error.URLError, OSError) as exc:
        return f"no answer ({getattr(exc, 'reason', exc)})"
    return None if isinstance(body, dict) and body.get("ok") is True else f"/health answered {body!r}"


def _get(data: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _metres(value: object) -> str:
    number = _number(value)
    return "none" if number is None else f"{number:.2f}"


def judge(row: Row, status: int, body: object) -> Row:
    """Fill the row from the service's answer and decide whether the upload ran end to end."""
    if status != 201:
        detail = _get(body, "detail") if isinstance(body, dict) else body
        row.error = f"HTTP {status}: {detail if isinstance(detail, str) else json.dumps(detail)[:300]}"
        return row
    coach, comparison = _get(body, "coach"), _get(body, "compare")
    if not isinstance(coach, dict) or not isinstance(comparison, dict):
        row.error = "the service answered 201 without a coach or compare result"
        return row
    broken, uncounted, notes = [], [], []

    stroke = coach.get("stroke") or _get(comparison, "assumptions", "stroke", "value")
    source = _get(comparison, "you", "swing", "metadata", "strokeSource") or coach.get("stroke_source")
    row.stroke = f"{stroke} ({source})" if stroke and source else str(stroke or "none")

    # The call is the coach's top fault. The ghost animates ghost_fault (the worst fault it can show,
    # services/coach/agent.py), whose fix is ghost_fix: the one the compare must have made to count.
    top_id, ghost_id = _get(coach, "fault", "id"), _get(coach, "ghost_fault", "id")
    if top_id:
        row.call = str(top_id) + (f" (ghost shows {ghost_id})" if ghost_id and ghost_id != top_id else "")
    else:
        row.call = "no fault"
        uncounted.append("the coach named no fault")

    fix_id, amount = _get(comparison, "fix", "id"), _number(_get(comparison, "fix", "amount"))
    coach_fix = coach.get("ghost_fix")
    if comparison.get("noCorrection") is True or not fix_id or amount is None or amount <= 0:
        row.ghost_fix = "none (unchanged ghost)"
        note = coach.get("ghost_note")
        uncounted.append("the ghost makes no fix" + (f": {note}" if isinstance(note, str) and note else ""))
    else:
        row.ghost_fix = f"{fix_id} {amount:g} {_get(comparison, 'fix', 'unit') or ''}".rstrip()
        if fix_id != coach_fix:
            uncounted.append(f"the ghost makes {fix_id}, but the coach's ghost_fix is {coach_fix or 'none'}")

    balls = {side: _get(comparison, side, "ball") for side in ("you", "ghost")}
    for side, ball in balls.items():
        if not (isinstance(ball, dict) and ball.get("predicted") is True and ball.get("label") == "PREDICTED"):
            broken.append(f"no PREDICTED ball for {side}")
    row.wall = f"{_metres(_get(balls['you'], 'frontWallHeightM'))} → {_metres(_get(balls['ghost'], 'frontWallHeightM'))} m"

    written, rejected = _number(body.get("written")), body.get("rejected")
    if written is not None and written > 1:
        notes.append(f"note: {written:g} swings found; this row is the first")
    if isinstance(rejected, list) and rejected:
        notes.append(f"note: {len(rejected)} candidate swing(s) rejected")
    row.ran = not broken
    row.ok = row.ran and not uncounted
    if row.ran and uncounted:
        broken = [f"not counted: {'; '.join(uncounted)}"]
    else:
        broken += uncounted
    row.error = "; ".join(broken + notes)
    return row


def run_clip(service: str, clip: Path, fields: dict[str, str], timeout: float, busy_wait: float,
             say: Callable[[str], None]) -> Row:
    row = Row(clip.name)
    size = clip.stat().st_size
    if size == 0:
        row.error = "empty file; not sent"
        return row
    if size > MAX_UPLOAD_BYTES:
        row.error = f"{size / 1048576:.0f} MB is over the service's 250 MB upload limit; not sent"
        return row
    start, deadline = time.monotonic(), time.monotonic() + busy_wait
    try:
        while True:
            status, body = post_clip(service, clip, fields, timeout)
            if status != 429 or time.monotonic() >= deadline:
                break
            say(f"  the service is busy with another clip (429); retrying in {BUSY_RETRY_S:g} s")
            time.sleep(BUSY_RETRY_S)
    except TimeoutError:
        row.error = f"no answer within {timeout:g} s"
    except (urllib.error.URLError, OSError) as exc:
        down = healthy(service)
        if down:
            row.error = f"the service stopped answering during this clip ({down})"
            row.seconds = time.monotonic() - start
            raise ServiceDown(row.error) from None
        row.error = f"upload failed: {getattr(exc, 'reason', exc)}"
    else:
        judge(row, status, body)
    row.seconds = time.monotonic() - start
    return row


def table(rows: list[Row]) -> list[str]:
    cells = [[str(i), r.clip, "yes" if r.ran else "no", r.stroke, r.call, r.ghost_fix, r.wall,
              "-" if r.seconds is None else f"{r.seconds:.0f} s", r.error or "-"]
             for i, r in enumerate(rows, 1)]
    widths = [max(len(line[c]) for line in [list(HEADERS), *cells]) for c in range(len(HEADERS) - 1)]

    def line(values: list[str]) -> str:
        return "  ".join(v.ljust(w) for v, w in zip(values, widths)) + "  " + values[-1]

    return [line(list(HEADERS)), line(["-" * w for w in widths] + ["-" * len(HEADERS[-1])])] + [line(c) for c in cells]


def summary(rows: list[Row]) -> str:
    return SUMMARY.format(n=sum(r.ok for r in rows), m=len(rows))


def ran_line(rows: list[Row]) -> str:
    return (f"Ran ok (201, coach and compare results, both balls PREDICTED): {sum(r.ran for r in rows)} of "
            f"{len(rows)}; the coach named a fault the ghost fixes: {sum(r.ok for r in rows)} of {len(rows)}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count how many single-swing clips run end to end "
                                     "through the service's POST /process (read-only on the clips).")
    parser.add_argument("folder", type=Path, help="folder of single-swing clips (copy them out of Downloads first)")
    parser.add_argument("--service", default="http://localhost:8000", help="the Python service (default %(default)s)")
    parser.add_argument("--slowdown", type=float, help="send this slowdown with every clip (default: detected)")
    parser.add_argument("--hand", choices=("R", "L", "auto"), help="send this hand with every clip")
    parser.add_argument("--stroke", choices=("forehand", "backhand", "auto"), help="send this stroke with every clip")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S, help="seconds to wait for one clip (default %(default)g)")
    parser.add_argument("--busy-wait", type=float, default=BUSY_WAIT_S,
                        help="seconds to keep retrying while the service is busy, 429 (default %(default)g)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    def say(text: str) -> None:
        print(text, file=sys.stderr, flush=True)

    if not args.folder.is_dir():
        parser.error(f"{args.folder} is not a folder")
    service = args.service.rstrip("/")
    fields = {key: str(value) for key, value in
              (("slowdown", args.slowdown), ("hand", args.hand), ("stroke", args.stroke)) if value is not None}
    clips, skipped = list_clips(args.folder)
    if not clips:
        parser.error(f"no .mov, .mp4, .m4v or .avi clips directly inside {args.folder}")
    down = healthy(service)
    if down:
        print(f"FAIL  the service at {service} isn't answering: {down}. Start it first (see the top of this script).")
        return 1

    print(f"Service {service}; {len(clips)} clip(s) from {args.folder}"
          + (f"; sent with {fields}" if fields else "; slowdown, hand and stroke detected by the service"))
    if skipped:
        print(f"Skipped (not a clip): {', '.join(skipped)}")
    before, rows, stop = snapshot(PUBLIC_SWINGS), [], None
    try:
        for i, clip in enumerate(clips, 1):
            say(f"[{i}/{len(clips)}] {clip.name} ({clip.stat().st_size / 1048576:.1f} MB) ...")
            try:
                rows.append(run_clip(service, clip, fields, args.timeout, args.busy_wait, say))
            except ServiceDown as exc:
                rows.append(Row(clip.name, error=str(exc)))
                stop = f"INCOMPLETE: the service stopped answering; {len(clips) - i} clip(s) not sent"
                break
            say(f"  {'counted' if rows[-1].ok else 'ran, not counted' if rows[-1].ran else 'failed'} "
                f"in {rows[-1].seconds or 0:.0f} s")
            changed = changes(before, snapshot(PUBLIC_SWINGS))
            if changed:
                stop = (f"FAIL  public/swings changed after {clip.name} ({', '.join(changed[:5])}): the service "
                        "is saving uploads there. Restart it with GHOST_SWINGS_DIR set to a temp folder.")
                break
    except KeyboardInterrupt:
        stop = f"INCOMPLETE: stopped by Ctrl-C; {len(clips) - len(rows)} clip(s) not sent"

    print()
    print("\n".join(table(rows)))
    print()
    print(ran_line(rows))
    print(summary(rows))
    if stop:
        print(stop)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
