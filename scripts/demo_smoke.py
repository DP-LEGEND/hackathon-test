"""Pre-demo check: is everything the /ghost demo needs running and right? Takes under 30 s.

Start the Python service and the web app first, then run this from the repo root. It needs
only the standard library, so any Python 3 works and there is nothing to install:

  python scripts/demo_smoke.py
  python scripts/demo_smoke.py --service http://localhost:8000 --web http://localhost:3000

Windows: py scripts\\demo_smoke.py

It prints one PASS (green) or FAIL (red) line per check and exits 1 if any check fails:

  1. health    The service's GET /health and the web app's /api proxy (/api/health) both answer ok.
  2. hero      The saved forehand hero (catalogue.json's defaultSwing in public/swings): the coach
               says over_rotation; the compare file for the coach's fix is in court coordinates at
               the ASSUMED 12 deg, and shows exactly the PREDICTED numbers the runbook and pitch
               quote: ball speed 133.2 -> 119.1 km/h, front wall 1.92 -> 1.88 m.
  3. backhand  The saved backhand: the coach's fault is null (nothing to fix), and its ball shows
               exactly 130.4 km/h and front wall 0.78 m, at 3 deg from anchor x = 2.0.
  4. pages     /ghost and /upload answer 200.
  5. process   An upload with no file answers exactly 422, both from the service (POST /process)
               and through the web app's proxy (POST /api/process), which is what /upload uses.

Checks 2 and 3 fail whenever /ghost would fail to load the same data. Every saved file they read
goes through a Python copy of the parser the browser uses for it, in app/ghost/compare.ts
(parseCatalogue, parseCoach, parseCompare with parseBall) and app/ghost/swing.ts (parseSwing,
used by loadSwingFor). JSON with NaN or Infinity is refused, as the browser's response.json() does.
A compare file must also be for the fix it was opened for, as loadCompareFor requires.

They read the fix /ghost starts on, among the fixes catalogue.json's fixes list offers: the coach's
ghost_fix, which must be usable (else the check fails rather than trying another fix); without one,
the first of the coach's faults with a usable fix; without that, the first usable fix in catalogue
order. "Usable" is the page's rule: no error string at all. The PASS line names which.

To test a broken copy of the saved files without the web app serving it, point --swings-dir at a
folder holding them (catalogue.json and the files it names); the other checks still use the servers:

  python scripts/demo_smoke.py --swings-dir /tmp/swings-copy

A FAIL line says what was wrong and in which file and field, for example
"catalogue.json: units must be an object" or "connection refused" when a server isn't running.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BUDGET_S = 30.0       # the whole run
TIMEOUT_S = 5.0       # one request
PAGE_TIMEOUT_S = 15.0  # a page: the Next dev server compiles it on the first request

# The PREDICTED numbers docs/demo-runbook.md and docs/pitch.md quote, as (you, ghost). /ghost prints
# them exactly as the files hold them (formatValue in app/ghost/compare.ts), so they must match
# exactly: a changed saved file changes what's on screen. None isn't checked (beat 2 stops at the
# coach's call, so the backhand's ghost numbers are never said).
HERO_SPEED_KMH = (133.2, 119.1)
HERO_WALL_M = (1.92, 1.88)
BACKHAND_SPEED_KMH = (130.4, None)
BACKHAND_WALL_M = (0.78, None)

# Same limits as the browser (app/ghost/swing.ts JOINT_COUNT, compare.ts OUTCOMES and fileName).
JOINT_COUNT = 33
OUTCOMES = ("in", "tin", "out", "down")
FILE_NAME = re.compile(r"[A-Za-z0-9_.-]+\.json")

# An upload with no clip: a multipart form, as /upload sends, with only a form field in it.
BOUNDARY = "demo-smoke-boundary"
UPLOAD_WITHOUT_FILE = (f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="stroke"\r\n\r\nauto\r\n'
                       f"--{BOUNDARY}--\r\n").encode()


class CheckFailed(Exception):
    pass


class DataError(Exception):
    """A value the browser's parser would reject. The message names the field, as the browser's does."""


# ---- The browser's parsers (app/ghost/compare.ts, app/ghost/swing.ts), check for check ----

def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _record(value, where: str) -> dict:
    if not isinstance(value, dict):
        raise DataError(f"{where} must be an object")
    return value


def _text(value, where: str) -> str:
    if not isinstance(value, str) or value == "":
        raise DataError(f"{where} must be a non-empty string")
    return value


def _num(value, where: str):
    if not _finite(value):
        raise DataError(f"{where} must be a finite number")
    return value


def _num_or_null(value, where: str):
    return None if value is None else _num(value, where)


def _vec3(value, where: str) -> None:
    if not (isinstance(value, list) and len(value) == 3 and all(_finite(v) for v in value)):
        raise DataError(f"{where} must be [x, y, z]")


def _outcome(value, where: str) -> None:
    if value not in OUTCOMES:
        raise DataError(f"{where} must be one of {', '.join(OUTCOMES)}")


def _change(value, where: str) -> None:
    row = _record(value, where)
    for key in ("you", "ghost", "change"):
        _num_or_null(row.get(key), f"{where}.{key}")


def _file_name(value, where: str) -> str:
    name = _text(value, where)
    if not FILE_NAME.fullmatch(name):
        raise DataError(f"{where} must be a .json file name")
    return name


def parse_catalogue(value) -> dict:
    """compare.ts parseCatalogue."""
    c = _record(value, "file")
    if not isinstance(c.get("fixes"), list) or not isinstance(c.get("swings"), list):
        raise DataError("fixes and swings must be lists")
    for i, fix in enumerate(c["fixes"]):
        _text(fix, f"fixes[{i}]")
    for key, unit in _record(c.get("units"), "units").items():
        _text(unit, f"units.{key}")
    for key, amount in _record(c.get("demoAmounts"), "demoAmounts").items():
        _num(amount, f"demoAmounts.{key}")
    for i, raw in enumerate(c["swings"]):
        where = f"swings[{i}]"
        entry = _record(raw, where)
        for fix_id, raw_fix in _record(entry.get("fixes"), f"{where}.fixes").items():
            fix = _record(raw_fix, f"{where}.fixes.{fix_id}")
            _num(fix.get("amount"), f"{where}.fixes.{fix_id}.amount")
            if "file" in fix:  # the browser parses any "file" that is present, null included
                _file_name(fix["file"], f"{where}.fixes.{fix_id}.file")
        _text(entry.get("id"), f"{where}.id")
        _text(entry.get("label"), f"{where}.label")
        _file_name(entry.get("swing"), f"{where}.swing")
        _file_name(entry.get("coach"), f"{where}.coach")
        if entry.get("wristSeries") is not None:
            _file_name(entry["wristSeries"], f"{where}.wristSeries")
    return c


def _parse_fault(value, where: str) -> None:
    f = _record(value, where)
    for key in ("id", "label", "fix"):
        _text(f.get(key), f"{where}.{key}")
    for key in ("value", "threshold", "severity", "fix_amount"):
        _num_or_null(f.get(key), f"{where}.{key}")


def parse_coach(value) -> dict:
    """compare.ts parseCoach (with parseFault)."""
    c = _record(value, "file")
    for key in ("fault", "ghost_fault"):
        if c.get(key) is not None:
            _parse_fault(c[key], key)
    if isinstance(c.get("faults"), list):
        for i, fault in enumerate(c["faults"]):
            _parse_fault(fault, f"faults[{i}]")
    _text(c.get("cue"), "cue")
    _num_or_null(c.get("ghost_fix_amount"), "ghost_fix_amount")
    return c


def parse_swing(value) -> dict:
    """swing.ts parseSwing, which loadSwing (and so loadSwingFor) runs first."""
    if not isinstance(value, dict):
        raise DataError("expected a JSON object")
    _text(value.get("id"), "id")
    if not _finite(value.get("fps")) or value["fps"] <= 0:
        raise DataError("fps must be a positive number")
    frames = value.get("frames")
    if not isinstance(frames, list) or len(frames) < 2:
        raise DataError("frames must hold at least two frames")
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise DataError(f"frame {i} is not an object")
        if not _finite(frame.get("t")):
            raise DataError(f"frame {i}: t must be a number of seconds")
        joints = frame.get("joints")
        if not isinstance(joints, list) or len(joints) != JOINT_COUNT:
            raise DataError(f"frame {i}: expected {JOINT_COUNT} joints")
        for j, joint in enumerate(joints):
            if not (isinstance(joint, list) and len(joint) == 3 and all(_finite(v) for v in joint)):
                raise DataError(f"frame {i}, joint {j}: expected [x, y, z] as finite numbers")
    for i in range(1, len(frames)):
        if frames[i]["t"] <= frames[i - 1]["t"]:
            raise DataError(f"frame {i}: t must increase")
    return value


def parse_ball(value, where: str) -> None:
    """compare.ts parseBall: no real ball, so a path not marked PREDICTED is refused."""
    b = _record(value, where)
    if b.get("predicted") is not True or b.get("label") != "PREDICTED":
        raise DataError(f'{where} is not marked PREDICTED (needs predicted: true and label: "PREDICTED")')
    points = b.get("points")
    if not isinstance(points, list) or len(points) < 2:
        raise DataError(f"{where}.points must hold at least two points")
    landing = b.get("landing")
    landing_ok = isinstance(landing, list) and len(landing) == 2 and all(_finite(v) for v in landing)
    if landing is not None and not landing_ok:
        raise DataError(f"{where}.landing must be [x, z] or null")
    for i, point in enumerate(points):
        _vec3(point, f"{where}.points[{i}]")
    _num(b.get("speedKmh"), f"{where}.speedKmh")
    _outcome(b.get("outcome"), f"{where}.outcome")
    for i, event in enumerate(b["events"] if isinstance(b.get("events"), list) else []):
        _vec3(_record(event, f"{where}.events[{i}]").get("point"), f"{where}.events[{i}].point")
    _num_or_null(b.get("frontWallHeightM"), f"{where}.frontWallHeightM")


def _parse_side(value, where: str) -> None:
    """compare.ts parseSide: the embedded swing goes through loadSwing, then the ball and racket speed."""
    side = _record(value, where)
    speed = _record(side.get("racketSpeed"), f"{where}.racketSpeed")
    try:
        parse_swing(side.get("swing"))
    except DataError as e:
        raise DataError(f"{where}.swing: {e}") from None
    parse_ball(side.get("ball"), f"{where}.ball")
    _num(speed.get("value"), f"{where}.racketSpeed.value")
    _text(speed.get("unit"), f"{where}.racketSpeed.unit")


def parse_compare(value) -> dict:
    """compare.ts parseCompare, which loadCompareFor runs on every compare file."""
    c = _record(value, "file")
    fix = _record(c.get("fix"), "fix")
    if c.get("hand") not in ("R", "L"):
        raise DataError("hand must be R or L")
    _parse_side(c.get("you"), "you")
    _parse_side(c.get("ghost"), "ghost")
    delta = _record(c.get("delta"), "delta")
    for key, row in _record(delta.get("metrics"), "delta.metrics").items():
        _change(row, f"delta.metrics.{key}")
    ball = _record(delta.get("ball"), "delta.ball")
    outcomes = _record(ball.get("outcome"), "delta.ball.outcome")
    assumptions = _record(c.get("assumptions"), "assumptions")
    _text(fix.get("id"), "fix.id")
    _num(fix.get("amount"), "fix.amount")
    _text(fix.get("unit"), "fix.unit")
    _outcome(outcomes.get("you"), "delta.ball.outcome.you")
    _outcome(outcomes.get("ghost"), "delta.ball.outcome.ghost")
    for key in ("speedKmh", "frontWallHeightM", "landingDepthM"):
        _change(ball.get(key), f"delta.ball.{key}")
    _vec3(assumptions.get("contactSpot"), "assumptions.contactSpot")
    return c


def _snippet(body: bytes) -> str:
    """The start of a response body for a FAIL line; a web page is named, not dumped."""
    text = body[:200].decode(errors="replace").strip()
    if text[:15].lower().startswith(("<!doctype", "<html")):
        return "an HTML page"
    return text[:100]


def _refuse_constant(name: str):
    raise ValueError(f"{name} is not valid JSON")


def parse_json(raw: bytes, where: str):
    """json.loads that refuses NaN and Infinity, like the browser's response.json()."""
    try:
        return json.loads(raw, parse_constant=_refuse_constant)
    except ValueError as e:
        raise CheckFailed(f"{where} isn't valid JSON for the browser (NaN or Infinity aren't allowed): {e}") from None


# ---- Talking to the servers ----

class Smoke:
    def __init__(self, service: str, web: str, swings_dir: Path | None = None):
        self.service, self.web = service.rstrip("/"), web.rstrip("/")
        self.swings_dir = swings_dir
        self.started = time.monotonic()
        self.raw_files: dict[str, object] = {}

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def request(self, url: str, method: str = "GET", cap: float = TIMEOUT_S, body: bytes | None = None,
                headers: dict | None = None) -> tuple[int, bytes]:
        """(status, body). A 4xx or 5xx is an answer too; only no answer raises."""
        timeout = min(cap, BUDGET_S - self.elapsed())
        if timeout <= 0:
            raise CheckFailed(f"out of time ({BUDGET_S:g} s budget used up)")
        data = body if body is not None else (b"" if method == "POST" else None)
        request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            raise CheckFailed(f"{url}: {e.reason}") from None
        except TimeoutError:
            raise CheckFailed(f"{url}: no answer within {timeout:.0f} s") from None

    def json(self, url: str):
        status, body = self.request(url)
        if status != 200:
            raise CheckFailed(f"{url} answered {status}: {_snippet(body)}")
        return parse_json(body, url)

    def saved(self, name: str, parse=None):
        """A saved demo file, as the web app serves it from public/swings (or from --swings-dir).

        With `parse`, the file must also pass that browser parser; a DataError names the file."""
        if name not in self.raw_files:
            if self.swings_dir is None:
                self.raw_files[name] = self.json(f"{self.web}/swings/{name}")
            else:
                path = self.swings_dir / name
                try:
                    raw = path.read_bytes()
                except OSError as e:
                    raise CheckFailed(f"{name}: can't read {path}: {e.strerror}") from None
                self.raw_files[name] = parse_json(raw, name)
        value = self.raw_files[name]
        if parse is not None:
            try:
                parse(value)
            except DataError as e:
                raise CheckFailed(f"{name}: {e}") from None
        return value


# ---- Checks ----

def _offered_fixes(catalogue: dict, entry: dict) -> dict:
    """The fixes /ghost offers for this swing, in order (buildEntries in app/ghost/sources.ts): the
    ids in catalogue.json's top-level fixes list that the swing has. Others are never shown."""
    fixes = entry.get("fixes") or {}
    return {fix: fixes[fix] for fix in catalogue["fixes"] if fix in fixes}


def _unavailable(option: dict) -> str | None:
    """The page's FixOption.unavailable: the catalogue's error whenever it is a string, even an empty
    one, else None. Only None counts as usable (coachPickFix and activeFix test unavailable === null)."""
    error = option.get("error")
    return error if isinstance(error, str) else None


def _coach_faults(coach: dict) -> list:
    """The coach's faults as parseCoach gives them to the page: the faults list, or, for older coach
    files without one, fault then ghost_fault (each fault id once)."""
    if isinstance(coach.get("faults"), list):
        return coach["faults"]
    faults: list = []
    for fault in (coach.get("fault"), coach.get("ghost_fault")):
        if isinstance(fault, dict) and all(f.get("id") != fault.get("id") for f in faults):
            faults.append(fault)
    return faults


def _compare_for(smoke: Smoke, entry: dict, coach: dict) -> tuple[str, dict, str]:
    """(fix, compare file, why this fix) for the fix /ghost starts on, in the page's order
    (coachPickFix in app/ghost/sources.ts, then activeFix in app/ghost/ghost-demo.tsx), among the
    fixes the page offers (_offered_fixes) that it counts as usable (_unavailable is None):

    1. The coach's ghost_fix. The coach promised this ghost, so it must be offered and usable.
       If it isn't, the check fails; the page would quietly open another fix instead.
    2. Else the first of the coach's faults (_coach_faults) whose fix is usable. Like the page, skip
       fault fixes it can't show (e.g. firm_wrist), so this doesn't fail while the demo works.
    3. Else the first usable offered fix ("Nothing to fix"). The PASS line says so.

    The chosen fix needs a compare file (without one the page would ask the live API instead), which
    must pass parseCompare and be for that fix (loadCompareFor). Every compare file of a swing has
    the same "you" ball, which is what the checks read."""
    swing = entry.get("id")
    offered = _offered_fixes(smoke.saved("catalogue.json"), entry)
    usable = {fix: option for fix, option in offered.items() if _unavailable(option) is None}

    def load(fix: str, why: str) -> tuple[str, dict, str]:
        name = usable[fix].get("file")
        if name is None:
            raise CheckFailed(f"{swing}: {why}, but catalogue.json gives it no compare file "
                              "(the page would ask the live API for it instead)")
        try:
            result = smoke.saved(name, parse_compare)
        except CheckFailed as e:
            raise CheckFailed(f"{swing}: {why}, but its compare file won't load: {e}") from None
        if result["fix"]["id"] != fix:
            raise CheckFailed(f"{swing}: {why}, but {name} is for {result['fix']['id']!r}; "
                              "/ghost refuses a compare file made for another fix")
        return fix, result, why

    ghost = coach.get("ghost_fix")
    if isinstance(ghost, str) and ghost:
        if ghost not in offered:
            where = ("isn't in catalogue.json's top-level fixes list" if ghost in (entry.get("fixes") or {})
                     else "isn't one of this swing's fixes in catalogue.json")
            raise CheckFailed(f"{swing}: the coach's ghost fix {ghost!r} {where}, so /ghost can't open it")
        if ghost not in usable:
            reason = _unavailable(offered[ghost]) or "its error is an empty string"
            raise CheckFailed(f"{swing}: the coach's ghost fix {ghost!r} is marked unavailable: {reason}")
        return load(ghost, f"the coach's ghost fix {ghost}")
    for fault in _coach_faults(coach):
        fix = fault.get("fix") if isinstance(fault, dict) else None
        if isinstance(fix, str) and fix in usable:
            return load(fix, f"no ghost fix, so the fix for the coach's {fault.get('id')} fault: {fix}")
    for fix in usable:
        return load(fix, f"the coach names no fix, so /ghost opens on the first usable fix: {fix}")
    raise CheckFailed(f"{swing}: /ghost has no usable fix to open (catalogue.json offers none without an error)")


def _swing_file(smoke: Smoke, entry: dict) -> dict:
    """The entry's own swing file, as loadSwingFor loads it. Its contactFrame must be a frame index:
    without one /ghost still plays, but times the replay from a guessed (fastest-wrist) contact."""
    name = entry["swing"]
    swing = smoke.saved(name, parse_swing)
    contact, frames = swing.get("contactFrame"), len(swing["frames"])
    if not (isinstance(contact, int) and not isinstance(contact, bool) and 0 <= contact < frames):
        raise CheckFailed(f"{name}: contactFrame must be a frame number from 0 to {frames - 1}, got {contact!r} "
                          "(/ghost would guess contact from the fastest wrist)")
    return swing


def _shown_problems(compare: dict, speed: tuple, wall: tuple) -> list[str]:
    """The quoted (you, ghost) numbers against what /ghost prints: the court legend's ball speeds
    (you.ball and ghost.ball speedKmh, scene-legend.tsx) and the "What the fix changes" panel's
    ball speed and front wall height (delta.ball, delta-panel.tsx)."""
    problems = []
    for side, want in zip(("you", "ghost"), speed):
        got = compare[side]["ball"].get("speedKmh")
        if want is not None and got != want:
            problems.append(f"{side}.ball.speedKmh is {got}, want exactly {want}")
    for key, pair in (("speedKmh", speed), ("frontWallHeightM", wall)):
        for side, want in zip(("you", "ghost"), pair):
            got = compare["delta"]["ball"][key].get(side)
            if want is not None and got != want:
                problems.append(f"delta.ball.{key}.{side} is {got}, want exactly {want}")
    return problems


def _court_problems(compare: dict, elevation: float, anchor_x: float | None = None) -> list[str]:
    problems = []
    if compare.get("coordinateSystem") != "court":
        problems.append(f"coordinateSystem is {compare.get('coordinateSystem')!r}, want 'court'")
    angle = compare["assumptions"]["launch"]["elevation"]["value"]
    if angle != elevation:
        problems.append(f"assumptions.launch.elevation is {angle}°, want {elevation:g}°")
    if anchor_x is not None and compare["assumptions"]["anchor"]["x"] != anchor_x:
        problems.append(f"assumptions.anchor.x is {compare['assumptions']['anchor']['x']}, want {anchor_x}")
    return problems


def check_health(smoke: Smoke) -> str:
    problems = []
    for name, url in (("service /health", f"{smoke.service}/health"), ("web /api/health", f"{smoke.web}/api/health")):
        try:
            answer = smoke.json(url)
            if not isinstance(answer, dict) or answer.get("ok") is not True:
                problems.append(f"{name} didn't say ok")
        except CheckFailed as e:
            problems.append(str(e))
    if problems:
        raise CheckFailed("; ".join(problems))
    return "service /health and web /api/health answer ok"


def check_hero(smoke: Smoke) -> str:
    catalogue = smoke.saved("catalogue.json", parse_catalogue)
    hero = catalogue.get("defaultSwing")
    entry = next((e for e in catalogue["swings"] if e.get("id") == hero), None)
    if entry is None:
        raise CheckFailed(f"catalogue.json: defaultSwing {hero!r} isn't one of its swings")
    coach = smoke.saved(entry["coach"], parse_coach)
    _swing_file(smoke, entry)
    _, compare, why = _compare_for(smoke, entry, coach)
    problems = _court_problems(compare, elevation=12.0) + _shown_problems(compare, HERO_SPEED_KMH, HERO_WALL_M)
    fault = (coach.get("fault") or {}).get("id")
    if fault != "over_rotation":
        problems.insert(0, f"{entry['coach']}: fault.id is {fault!r}, want 'over_rotation'")
    if problems:
        raise CheckFailed(f"{hero}: " + "; ".join(problems))
    return (f"{hero}: over_rotation, court coordinates at 12°, ball speed {HERO_SPEED_KMH[0]} → {HERO_SPEED_KMH[1]} "
            f"km/h, front wall {HERO_WALL_M[0]} → {HERO_WALL_M[1]} m; {why}; "
            "its catalogue, coach, swing and compare files load as /ghost loads them")


def check_backhand(smoke: Smoke) -> str:
    catalogue = smoke.saved("catalogue.json", parse_catalogue)
    unreadable = []
    for entry in catalogue["swings"]:
        try:
            if smoke.saved(entry["coach"]).get("stroke") == "backhand":
                break
        except (CheckFailed, AttributeError) as e:  # reported by the check that reads that swing
            unreadable.append(f"{entry['coach']}: {e}")
    else:
        extra = f" (couldn't read: {'; '.join(unreadable)})" if unreadable else ""
        raise CheckFailed(f"no saved backhand: no coach file in catalogue.json says stroke 'backhand'{extra}")
    coach = smoke.saved(entry["coach"], parse_coach)
    _swing_file(smoke, entry)
    _, compare, why = _compare_for(smoke, entry, coach)
    problems = (_court_problems(compare, elevation=3.0, anchor_x=2.0)
                + _shown_problems(compare, BACKHAND_SPEED_KMH, BACKHAND_WALL_M))
    if coach.get("fault") is not None:
        fault = coach["fault"].get("id") if isinstance(coach["fault"], dict) else coach["fault"]
        problems.insert(0, f"{entry['coach']}: fault is {fault!r}, want null (beat 2 says nothing to fix)")
    if problems:
        raise CheckFailed(f"{entry['id']}: " + "; ".join(problems))
    return (f"{entry['id']}: fault null, ball speed {BACKHAND_SPEED_KMH[0]} km/h, front wall {BACKHAND_WALL_M[0]} m "
            f"at 3° from x = 2.0; {why}; its files load as /ghost loads them")


def check_pages(smoke: Smoke) -> str:
    problems = []
    for page in ("/ghost", "/upload"):
        try:
            status, _ = smoke.request(f"{smoke.web}{page}", cap=PAGE_TIMEOUT_S)
            if status != 200:
                problems.append(f"{page} answered {status}")
        except CheckFailed as e:
            problems.append(str(e))
    if problems:
        raise CheckFailed("; ".join(problems))
    return "/ghost and /upload answer 200"


def check_process(smoke: Smoke) -> str:
    """An upload with no file must be FastAPI's missing-field error, exactly 422, both from the service
    and through the web proxy that /upload posts to. A 404 or 405 (a removed or renamed route), a
    proxy 502 or a 500 fails, so the check can't pass on the wrong endpoint."""
    headers = {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}
    problems = []
    for name, url in (("service POST /process", f"{smoke.service}/process"),
                      ("web POST /api/process", f"{smoke.web}/api/process")):
        try:
            status, body = smoke.request(url, method="POST", body=UPLOAD_WITHOUT_FILE, headers=headers)
            if status != 422:
                problems.append(f"{name} answered {status}, want exactly 422: {_snippet(body)}")
        except CheckFailed as e:
            problems.append(str(e))
    if problems:
        raise CheckFailed("; ".join(problems))
    return "an upload with no file gets 422 from the service and through the web proxy"


CHECKS = [("health", check_health), ("hero", check_hero), ("backhand", check_backhand),
          ("pages", check_pages), ("process", check_process)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-demo check of the Ghost service and web app (under 30 s).")
    parser.add_argument("--service", default="http://localhost:8000", help="Python service (default %(default)s)")
    parser.add_argument("--web", default="http://localhost:3000", help="Next web app (default %(default)s)")
    parser.add_argument("--swings-dir", type=Path, default=None,
                        help="read the saved demo files from this folder instead of the web app (to test a copy)")
    args = parser.parse_args(argv)
    if args.swings_dir is not None and not args.swings_dir.is_dir():
        parser.error(f"--swings-dir {args.swings_dir} isn't a folder")
    colour = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    if colour and os.name == "nt":
        os.system("")  # turns on colour codes in the Windows console
    paint = (lambda text, code: f"\033[{code}m{text}\033[0m") if colour else (lambda text, code: text)

    smoke = Smoke(args.service, args.web, args.swings_dir)
    saved_from = f"saved files from {args.swings_dir}" if args.swings_dir else "saved files from the web app"
    print(f"Checking service {smoke.service} and web app {smoke.web} ({saved_from})")
    failed = 0
    for number, (name, check) in enumerate(CHECKS, 1):
        try:
            ok, detail = True, check(smoke)
        except CheckFailed as e:
            ok, detail = False, str(e)
        except (KeyError, TypeError, AttributeError) as e:  # a field the checks read beyond the parsers
            ok, detail = False, f"unexpected data: {type(e).__name__} {e}"
        failed += not ok
        print(f"{paint('PASS', 32) if ok else paint('FAIL', 31)}  {number}. {name:<9} {detail}")
    summary = f"{len(CHECKS) - failed}/{len(CHECKS)} checks passed in {smoke.elapsed():.1f} s"
    print(paint(summary, 32 if not failed else 31))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
