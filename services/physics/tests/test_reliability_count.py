"""scripts/reliability_count.py against a stub service. The service answers here are MOCK data."""

from __future__ import annotations

import importlib.util
import json
import re
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "reliability_count.py"


@pytest.fixture(scope="module")
def rc():
    spec = importlib.util.spec_from_file_location("reliability_count", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclass looks the module up while it loads
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


@pytest.fixture(autouse=True)
def guarded(rc, tmp_path, monkeypatch):
    """Watch a temp public/swings, never the repo's, and don't wait between busy retries."""
    folder = tmp_path / "public-swings"
    folder.mkdir()
    (folder / "catalogue.json").write_text("{}")
    monkeypatch.setattr(rc, "PUBLIC_SWINGS", folder)
    monkeypatch.setattr(rc, "BUSY_RETRY_S", 0.0)
    return folder


SAME = object()


def answer(fault="over_rotation", fix=("turn_shoulders_less", 52.6), walls=(1.45, 1.44), *,
           ghost_fault=SAME, ghost_fix=SAME, written=1, rejected=(), predicted=True, note=None):
    """A MOCK 201 body shaped like services/pipeline/live.py process_live_clip's.

    By default the top fault is the one the ghost animates (ghost_fault) and the compare made its fix
    (ghost_fix); with no fix, there is no fault the ghost can show.
    """
    if ghost_fault is SAME:
        ghost_fault = fault if fix else None
    if ghost_fix is SAME:
        ghost_fix = fix[0] if fix else None
    def ball(height):
        return {"predicted": predicted, "label": "PREDICTED" if predicted else "MEASURED", "frontWallHeightM": height}
    return {
        "status": "complete", "written": written, "rejected": list(rejected), "swingId": "mock-swing-0001",
        "coach": {"stroke": "forehand", "stroke_source": "given", "fault": {"id": fault} if fault else None,
                  "ghost_fault": {"id": ghost_fault} if ghost_fault else None, "ghost_fix": ghost_fix,
                  "ghost_note": note},
        "compare": {"fix": {"id": fix[0] if fix else "straighten_elbow", "amount": fix[1] if fix else 0.0, "unit": "deg"},
                    "noCorrection": fix is None,
                    "you": {"ball": ball(walls[0]), "swing": {"metadata": {"strokeSource": "measured"}}},
                    "ghost": {"ball": ball(walls[1])}},
    }


class Stub(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health" and not self.server.dead:
            self._send(200, {"ok": True})
        else:
            self._send(500, {"detail": "down"})

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        boundary = re.search(r"boundary=(\S+)", self.headers["Content-Type"]).group(1).encode()
        parts = [p for p in body.split(b"--" + boundary) if p.strip(b"-\r\n")]
        fields, upload, name = {}, None, None
        for part in parts:
            header, content = part.split(b"\r\n\r\n", 1)
            content = content[:-2]  # the CRLF before the next boundary
            found = re.search(rb'filename="([^"]+)"', header)
            if found:
                name, upload = found.group(1).decode(), content
            else:
                fields[re.search(rb'name="([^"]+)"', header).group(1).decode()] = content.decode()
        self.server.received.append({"path": self.path, "name": name, "fields": fields, "upload": upload})
        status, payload = self.server.script[name].pop(0)
        if status is None:  # drop the connection without answering, as a crashed service does
            self.server.dead = True
            self.close_connection = True
            return
        if callable(payload):
            payload = payload()
        self._send(status, payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def service():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    server.received, server.script, server.dead = [], {}, False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server
    server.shutdown()
    server.server_close()


def clips(folder: Path, names: dict[str, bytes]) -> Path:
    folder.mkdir(exist_ok=True)
    for name, data in names.items():
        (folder / name).write_bytes(data)
    return folder


def state(folder: Path) -> dict[str, tuple[bytes, int]]:
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}


def test_counts_only_uploads_where_the_coach_names_a_fault_the_ghost_fixes(rc, service, tmp_path, capsys):
    folder = clips(tmp_path / "clips", {"a.mov": b"A" * 3000, "b.MP4": b"B" * 10, "c.mov": b"C",
                                        "notes.txt": b"x", ".hidden.mov": b"x"})
    service.script = {"a.mov": [(201, answer())], "b.MP4": [(201, answer(fault=None, fix=None, walls=(1.2, 1.2)))],
                      "c.mov": [(422, {"detail": "No swing found in the clip"})]}
    before = state(folder)

    assert rc.main([str(folder), "--service", service.url]) == 0
    out = capsys.readouterr().out.splitlines()

    assert out[-1] == "1 of 3 uploads ran end to end with a coach call and ghost"
    assert out[-2] == ("Ran ok (201, coach and compare results, both balls PREDICTED): 2 of 3; "
                       "the coach named a fault the ghost fixes: 1 of 3.")
    assert "Skipped (not a clip): .hidden.mov, notes.txt" in out
    rows = {line.split()[1]: line for line in out if re.match(r"\d+ ", line)}
    assert rows["a.mov"].split()[2] == "yes" and "forehand (measured)" in rows["a.mov"]
    assert "over_rotation" in rows["a.mov"] and "turn_shoulders_less 52.6 deg" in rows["a.mov"]
    assert "1.45 → 1.44 m" in rows["a.mov"] and rows["a.mov"].rstrip().endswith("-")
    assert rows["b.MP4"].split()[2] == "yes" and "no fault" in rows["b.MP4"]
    assert rows["b.MP4"].rstrip().endswith("not counted: the coach named no fault; the ghost makes no fix")
    assert rows["c.mov"].split()[2] == "no" and rows["c.mov"].rstrip().endswith("HTTP 422: No swing found in the clip")
    # One at a time, in name order, every byte sent, nothing else sent, and the clips untouched.
    assert [r["name"] for r in service.received] == ["a.mov", "b.MP4", "c.mov"]
    assert {r["path"] for r in service.received} == {"/process"}
    assert service.received[0]["upload"] == b"A" * 3000 and service.received[0]["fields"] == {}
    assert state(folder) == before


def test_the_form_fields_go_with_every_clip(rc, service, tmp_path, capsys):
    folder = clips(tmp_path / "clips", {"one clip.mov": b"1", "two.m4v": b"2"})
    service.script = {"one_clip.mov": [(201, answer())], "two.m4v": [(201, answer())]}
    assert rc.main([str(folder), "--service", service.url + "/", "--slowdown", "4", "--hand", "R",
                    "--stroke", "backhand"]) == 0
    assert [r["fields"] for r in service.received] == [{"slowdown": "4.0", "hand": "R", "stroke": "backhand"}] * 2
    assert capsys.readouterr().out.splitlines()[-1] == "2 of 2 uploads ran end to end with a coach call and ghost"


def test_a_busy_service_is_retried(rc, service, tmp_path, capsys):
    folder = clips(tmp_path / "clips", {"a.mov": b"A"})
    service.script = {"a.mov": [(429, {"detail": "A clip is already processing"}), (201, answer())]}
    assert rc.main([str(folder), "--service", service.url]) == 0
    assert len(service.received) == 2
    assert capsys.readouterr().out.splitlines()[-1] == "1 of 1 uploads ran end to end with a coach call and ghost"


def test_still_busy_after_the_wait_is_reported(rc, service, tmp_path, capsys):
    folder = clips(tmp_path / "clips", {"a.mov": b"A"})
    service.script = {"a.mov": [(429, {"detail": "A clip is already processing"})]}
    assert rc.main([str(folder), "--service", service.url, "--busy-wait", "0"]) == 0
    out = capsys.readouterr().out
    assert "HTTP 429: A clip is already processing" in out and out.endswith("0 of 1 uploads ran end to end with a coach call and ghost\n")


def test_empty_and_oversize_clips_are_not_sent_but_are_counted(rc, service, tmp_path, capsys):
    folder = clips(tmp_path / "clips", {"empty.mov": b""})
    big = folder / "big.mov"
    with big.open("wb") as stream:
        stream.truncate(rc.MAX_UPLOAD_BYTES + 1)  # sparse: takes no disk space
    assert rc.main([str(folder), "--service", service.url]) == 0
    out = capsys.readouterr().out
    assert service.received == []
    assert "over the service's 250 MB upload limit; not sent" in out and "empty file; not sent" in out
    assert out.endswith("0 of 2 uploads ran end to end with a coach call and ghost\n")


def test_it_stops_when_public_swings_changes(rc, service, tmp_path, guarded, capsys):
    folder = clips(tmp_path / "clips", {"a.mov": b"A", "b.mov": b"B"})

    def save_into_public_swings():
        (guarded / "live-123" / "manifest.json").parent.mkdir()
        (guarded / "live-123" / "manifest.json").write_text("{}")
        return answer()

    service.script = {"a.mov": [(201, save_into_public_swings)], "b.mov": [(201, answer())]}
    assert rc.main([str(folder), "--service", service.url]) == 1
    out = capsys.readouterr().out
    assert [r["name"] for r in service.received] == ["a.mov"]
    assert "FAIL  public/swings changed after a.mov (added live-123/manifest.json)" in out
    assert "1 of 1 uploads ran end to end with a coach call and ghost" in out


def test_a_service_that_isnt_running_fails_before_anything_is_sent(rc, tmp_path, capsys):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # closed again before the run: nothing listens there
    folder = clips(tmp_path / "clips", {"a.mov": b"A"})
    assert rc.main([str(folder), "--service", f"http://127.0.0.1:{port}"]) == 1
    out = capsys.readouterr().out
    assert out.startswith(f"FAIL  the service at http://127.0.0.1:{port} isn't answering")
    assert "uploads ran end to end" not in out


def test_a_service_that_dies_mid_run_stops_the_count(rc, service, tmp_path, capsys):
    folder = clips(tmp_path / "clips", {"a.mov": b"A", "b.mov": b"B", "c.mov": b"C"})
    service.script = {"a.mov": [(201, answer())], "b.mov": [(None, None)], "c.mov": [(201, answer())]}
    assert rc.main([str(folder), "--service", service.url]) == 1
    out = capsys.readouterr().out.splitlines()
    assert [r["name"] for r in service.received] == ["a.mov", "b.mov"]
    assert out[-1] == "INCOMPLETE: the service stopped answering; 1 clip(s) not sent"
    assert out[-2] == "1 of 2 uploads ran end to end with a coach call and ghost"
    assert any("the service stopped answering during this clip" in line for line in out)


@pytest.mark.parametrize("body,ran,ok,error", [
    (answer(predicted=False), False, False, "no PREDICTED ball for you; no PREDICTED ball for ghost"),
    (answer(fix=None, note="the fix would edit a guessed joint"), True, False,
     "not counted: the ghost makes no fix: the fix would edit a guessed joint"),
    (answer(written=2, rejected=[{"reason": "too short"}]), True, True,
     "note: 2 swings found; this row is the first; note: 1 candidate swing(s) rejected"),
    (answer(walls=(None, 1.3)), True, True, ""),
    ({"coach": None}, False, False, "the service answered 201 without a coach or compare result"),
])
def test_judge(rc, body, ran, ok, error):
    row = rc.judge(rc.Row("x.mov"), 201, body)
    assert (row.ran, row.ok, row.error) == (ran, ok, error)
    if body is not None and "compare" in body and body["compare"]["you"]["ball"]["frontWallHeightM"] is None:
        assert row.wall == "none → 1.30 m"  # the PREDICTED ball didn't reach the front wall


def test_an_unanimated_top_fault_counts_when_the_ghost_makes_the_ghost_faults_fix(rc):
    # The coach's top fault can't be animated; the ghost shows the next fault it can (agent.py).
    body = answer(fault="rolled_wrist", ghost_fault="over_rotation", ghost_fix="turn_shoulders_less",
                  fix=("turn_shoulders_less", 52.6), note="The ghost shows the next fault it can animate.")
    row = rc.judge(rc.Row("x.mov"), 201, body)
    assert (row.ran, row.ok, row.error) == (True, True, "")
    assert row.call == "rolled_wrist (ghost shows over_rotation)"
    assert row.ghost_fix == "turn_shoulders_less 52.6 deg"
    lines = rc.table([row])
    assert "rolled_wrist (ghost shows over_rotation)" in lines[2] and lines[2].split()[2] == "yes"


def test_a_compare_that_doesnt_make_the_coachs_ghost_fix_isnt_counted(rc):
    body = answer(fault="over_rotation", ghost_fix="turn_shoulders_less", fix=("straighten_elbow", 10))
    row = rc.judge(rc.Row("x.mov"), 201, body)
    assert (row.ran, row.ok) == (True, False)
    assert row.error == "not counted: the ghost makes straighten_elbow, but the coach's ghost_fix is turn_shoulders_less"
    assert row.call == "over_rotation" and row.ghost_fix == "straighten_elbow 10 deg"
    # The top fault's own fix doesn't count either when the ghost is meant to show another fault.
    body = answer(fault="rolled_wrist", ghost_fault="over_rotation", ghost_fix="turn_shoulders_less",
                  fix=("firm_wrist", 10))
    row = rc.judge(rc.Row("x.mov"), 201, body)
    assert not row.ok and row.call == "rolled_wrist (ghost shows over_rotation)"
    assert row.error == "not counted: the ghost makes firm_wrist, but the coach's ghost_fix is turn_shoulders_less"
    # And a fix the coach never asked for (no ghost_fault at all) is not counted.
    row = rc.judge(rc.Row("x.mov"), 201, answer(ghost_fault=None, ghost_fix=None))
    assert not row.ok and row.error.endswith("but the coach's ghost_fix is none")


def test_errors_without_any_clip(rc, tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit):
        rc.main([str(tmp_path / "empty")])
    with pytest.raises(SystemExit):
        rc.main([str(tmp_path / "missing")])


def test_the_upload_limit_matches_the_service(rc):
    server = (SCRIPT.parents[1] / "services" / "pipeline" / "server.py").read_text()
    assert "MAX_UPLOAD_BYTES = 250 * 1024 * 1024" in server and rc.MAX_UPLOAD_BYTES == 250 * 1024 * 1024
