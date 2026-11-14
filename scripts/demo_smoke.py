"""Pre-demo check: is everything the /ghost demo needs running and right? Takes under 30 s.

Start the Python service and the web app first, then run this from the repo root. It needs
only the standard library, so any Python 3 works and there is nothing to install:

  python scripts/demo_smoke.py
  python scripts/demo_smoke.py --service http://localhost:8000 --web http://localhost:3000

Windows: py scripts\\demo_smoke.py

It prints one PASS (green) or FAIL (red) line per check and exits 1 if any check fails:

  1. health    The service's GET /health and the web app's /api proxy (/api/health) both answer ok.
  2. hero      The saved forehand hero (catalogue.json's defaultSwing in public/swings): the coach
               says over_rotation; the compare file for the coach's fix is in court coordinates,
               with the PREDICTED front wall at 1.92 m (within 0.05) at the ASSUMED 12 deg.
  3. backhand  The saved backhand: front wall at 0.78 m (within 0.05) at 3 deg, from anchor x = 2.0.
  Both read the fix /ghost starts on: the coach's ghost_fix (else its first fault's fix). If that
  fix has no usable compare file, the check fails rather than trying another fix. If the coach names
  none, the first fix in catalogue order with a file is checked, and the PASS line says so.
  4. pages     /ghost and /upload answer 200.
  5. process   POST /process with no file answers exactly 422 (anything else fails, with the status).

A FAIL line says what was wrong, for example "connection refused" when a server isn't running.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BUDGET_S = 30.0       # the whole run
TIMEOUT_S = 5.0       # one request
PAGE_TIMEOUT_S = 15.0  # a page: the Next dev server compiles it on the first request
WALL_TOLERANCE_M = 0.05


class CheckFailed(Exception):
    pass


class Smoke:
    def __init__(self, service: str, web: str):
        self.service, self.web = service.rstrip("/"), web.rstrip("/")
        self.started = time.monotonic()
        self.saved_files: dict[str, dict] = {}

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def request(self, url: str, method: str = "GET", cap: float = TIMEOUT_S) -> tuple[int, bytes]:
        """(status, body). A 4xx or 5xx is an answer too; only no answer raises."""
        timeout = min(cap, BUDGET_S - self.elapsed())
        if timeout <= 0:
            raise CheckFailed(f"out of time ({BUDGET_S:g} s budget used up)")
        data = b"" if method == "POST" else None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            raise CheckFailed(f"{url}: {e.reason}") from None
        except TimeoutError:
            raise CheckFailed(f"{url}: no answer within {timeout:.0f} s") from None

    def json(self, url: str) -> dict:
        status, body = self.request(url)
        if status != 200:
            raise CheckFailed(f"{url} answered {status}: {body[:120].decode(errors='replace')}")
        try:
            return json.loads(body)
        except ValueError:
            raise CheckFailed(f"{url} didn't answer JSON") from None

    def saved(self, name: str) -> dict:
        """A saved demo file from public/swings, as the web app serves it."""
        if name not in self.saved_files:
            self.saved_files[name] = self.json(f"{self.web}/swings/{name}")
        return self.saved_files[name]


def _coach_fix(coach: dict) -> str | None:
    """The fix the coach names, the way /ghost reads it: ghost_fix, else the first fault's fix
    (app/ghost/sources.ts coachPickFix). None when the coach names no fix ("Nothing to fix")."""
    if isinstance(coach.get("ghost_fix"), str) and coach["ghost_fix"]:
        return coach["ghost_fix"]
    for fault in coach.get("faults") or []:
        if isinstance(fault, dict) and isinstance(fault.get("fix"), str) and fault["fix"]:
            return fault["fix"]
    return None


def _compare_for(smoke: Smoke, entry: dict, coach: dict) -> tuple[str, dict, str]:
    """(fix, compare file, why this fix). When the coach names a fix, its compare file must exist: a
    missing or unavailable one fails here, and no other fix is checked instead. When the coach names
    none, /ghost opens on the first fix in catalogue order that has a file, so that is checked.
    Every compare file of a swing has the same "you" ball, which is what the checks read."""
    fixes = entry.get("fixes") or {}
    named = _coach_fix(coach)
    if named is not None:
        option = fixes.get(named)
        if option is None:
            raise CheckFailed(f"{entry.get('id')}: the coach names {named!r}, which catalogue.json doesn't list")
        if option.get("error") or not option.get("file"):
            why = option.get("error") or "catalogue.json has no compare file for it"
            raise CheckFailed(f"{entry.get('id')}: the coach names {named!r}, but it has no usable compare file: {why}")
        try:
            return named, smoke.saved(option["file"]), f"the coach's fix {named}"
        except CheckFailed as e:
            raise CheckFailed(f"{entry.get('id')}: the coach names {named!r}, but its compare file "
                              f"is unavailable: {e}") from None
    for fix in smoke.saved("catalogue.json").get("fixes") or list(fixes):
        option = fixes.get(fix) or {}
        if not option.get("error") and option.get("file"):
            return fix, smoke.saved(option["file"]), (
                f"the coach names no fix, so /ghost opens on the first fix in catalogue order: {fix}")
    raise CheckFailed(f"{entry.get('id')}: no fix has a compare file in catalogue.json")


def _court_problems(compare: dict, wall: float, elevation: float, anchor_x: float | None = None) -> list[str]:
    problems = []
    if compare.get("coordinateSystem") != "court":
        problems.append(f"coordinateSystem is {compare.get('coordinateSystem')!r}, want 'court'")
    got = compare["you"]["ball"].get("frontWallHeightM")
    if got is None or abs(got - wall) > WALL_TOLERANCE_M:
        problems.append(f"front wall {got} m, want {wall} ± {WALL_TOLERANCE_M}")
    angle = compare["assumptions"]["launch"]["elevation"]["value"]
    if angle != elevation:
        problems.append(f"elevation {angle}°, want {elevation:g}°")
    if anchor_x is not None and compare["assumptions"]["anchor"]["x"] != anchor_x:
        problems.append(f"anchor x {compare['assumptions']['anchor']['x']}, want {anchor_x}")
    return problems


def check_health(smoke: Smoke) -> str:
    problems = []
    for name, url in (("service /health", f"{smoke.service}/health"), ("web /api/health", f"{smoke.web}/api/health")):
        try:
            if smoke.json(url).get("ok") is not True:
                problems.append(f"{name} didn't say ok")
        except CheckFailed as e:
            problems.append(str(e))
    if problems:
        raise CheckFailed("; ".join(problems))
    return "service /health and web /api/health answer ok"


def check_hero(smoke: Smoke) -> str:
    catalogue = smoke.saved("catalogue.json")
    hero = catalogue.get("defaultSwing")
    entry = next((e for e in catalogue.get("swings", []) if e.get("id") == hero), None)
    if entry is None:
        raise CheckFailed(f"catalogue.json's defaultSwing {hero!r} isn't in its swings")
    coach = smoke.saved(entry["coach"])
    fix, compare, why = _compare_for(smoke, entry, coach)
    problems = _court_problems(compare, wall=1.92, elevation=12.0)
    fault = (coach.get("fault") or {}).get("id")
    if fault != "over_rotation":
        problems.insert(0, f"coach fault {fault!r}, want 'over_rotation'")
    if problems:
        raise CheckFailed(f"{hero}: " + "; ".join(problems))
    return (f"{hero}: over_rotation, court coordinates, front wall "
            f"{compare['you']['ball']['frontWallHeightM']} m at 12°; {why}")


def check_backhand(smoke: Smoke) -> str:
    for entry in smoke.saved("catalogue.json").get("swings", []):
        coach = smoke.saved(entry["coach"])
        if coach.get("stroke") == "backhand":
            break
    else:
        raise CheckFailed("no saved backhand in catalogue.json (no coach file says stroke 'backhand')")
    fix, compare, why = _compare_for(smoke, entry, coach)
    problems = _court_problems(compare, wall=0.78, elevation=3.0, anchor_x=2.0)
    if problems:
        raise CheckFailed(f"{entry['id']}: " + "; ".join(problems))
    return (f"{entry['id']}: front wall {compare['you']['ball']['frontWallHeightM']} m at 3° "
            f"from x = 2.0; {why}")


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
    """An upload with no file is FastAPI's missing-field validation error, exactly 422. A 404 or 405
    (a removed or renamed route) or a 500 fails, so the check can't pass on the wrong endpoint."""
    status, body = smoke.request(f"{smoke.service}/process", method="POST")
    if status != 422:
        detail = body[:100].decode(errors="replace")
        raise CheckFailed(f"POST /process with no file answered {status}, want exactly 422: {detail}")
    return "POST /process with no file answered 422 (the missing file is rejected)"


CHECKS = [("health", check_health), ("hero", check_hero), ("backhand", check_backhand),
          ("pages", check_pages), ("process", check_process)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pre-demo check of the Ghost service and web app (under 30 s).")
    parser.add_argument("--service", default="http://localhost:8000", help="Python service (default %(default)s)")
    parser.add_argument("--web", default="http://localhost:3000", help="Next web app (default %(default)s)")
    args = parser.parse_args(argv)
    colour = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    if colour and os.name == "nt":
        os.system("")  # turns on colour codes in the Windows console
    paint = (lambda text, code: f"\033[{code}m{text}\033[0m") if colour else (lambda text, code: text)

    smoke = Smoke(args.service, args.web)
    print(f"Checking service {smoke.service} and web app {smoke.web}")
    failed = 0
    for number, (name, check) in enumerate(CHECKS, 1):
        try:
            ok, detail = True, check(smoke)
        except CheckFailed as e:
            ok, detail = False, str(e)
        except (KeyError, TypeError, AttributeError) as e:  # a saved file without the expected fields
            ok, detail = False, f"unexpected data: {type(e).__name__} {e}"
        failed += not ok
        print(f"{paint('PASS', 32) if ok else paint('FAIL', 31)}  {number}. {name:<9} {detail}")
    summary = f"{len(CHECKS) - failed}/{len(CHECKS)} checks passed in {smoke.elapsed():.1f} s"
    print(paint(summary, 32 if not failed else 31))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
