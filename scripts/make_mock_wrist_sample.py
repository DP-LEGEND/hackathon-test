"""Turn one MOCK wrist-sensor swing (wrist.synth output) into a saved /ghost sample, so the
firm-wrist ghost can be shown before real recordings exist. Owner: aryan.

Run from the repo root with the services Python environment active, after wrist.run has made
the mock session's filled swings and series (docs/demo-runbook.md, beat 4):

  python scripts/make_mock_wrist_sample.py <mock-session-folder> --swing synth-07

<mock-session-folder> holds filled/<swing>.json (the swing with its forearm entry, "wrist")
and wrist_series.json, as wrist.run writes them with --filled-out and --series-out.

What it does (nothing is written until every file has passed /ghost's parsers):
 1. Reads the swing and refuses anything that isn't mock: real recordings follow the morning
    wrist-sensor steps in docs/demo-runbook.md (pre-flight step 6 and Tab 3).
 2. Coach (coach.agent.coach_swing plus every fault) on the swing WITH its wrist entry: the
    coach judges rolled_wrist by the mock rule; when it fires it is the call and firm_wrist the ghost.
 3. physics.compare.compare for every fix. With the forearm roll, both PREDICTED balls are aimed
    by the racket face (physics/wrist_face.py, an ASSUMED face model): the rolled swing's goes
    cross-court, the firm-wrist ghost's straight.
 4. Writes swing_<id>.json, coach_<id>.json, compare_<id>_<fix>.json and wrist_<id>.json to
    --out-dir (public/swings) and APPENDS one entry to catalogue.json. It adds firm_wrist to
    the top-level fix list and units if missing (the page only offers listed fixes; other
    samples don't have it, and demoAmounts is untouched, so nothing else changes). Every other
    entry and defaultSwing stay exactly as they were. Only a sample this script made can be
    replaced, and only with --replace, and no file it would write may already exist or belong
    to a catalogue entry it didn't make (sample ids and file names are separate: the hero's
    swing file is swing_fh_over_rotation.json).

On a rolled swing the coach's call is the wrist ("Keep your wrist firm through contact."): a
wrist-sensor fault leads, pose faults follow. The body is wrist.synth's placeholder (only the
arm moves), so those pose faults mean nothing. Everything says MOCK. These files are for a
local demo: don't commit them.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services"))

from coach.agent import coach_swing  # noqa: E402
from coach.faults import detect_faults, measure_swing  # noqa: E402
from physics.compare import compare  # noqa: E402
from physics.ghost import EDITS, FIXES  # noqa: E402

ID_RE = re.compile(r"[A-Za-z0-9_-]+")
MADE_BY = "scripts/make_mock_wrist_sample.py"
# Fix size when the coach didn't flag the fault: the catalogue's demoAmounts, else these
# (the saved-sample script's values in app/ghost/README.md). firm_wrist has none: it only
# runs at the coach's amount.
DEMO_AMOUNT = {"straighten_elbow": 12.0, "bend_elbow": 12.0, "turn_shoulders_more": 15.0,
               "turn_shoulders_less": 15.0, "hold_wrist_cock": 40.0, "close_stance": 15.0}
WRIST_FIX = "firm_wrist"


class SampleError(Exception):
    """A step that can't be trusted: stop before writing anything."""


def load_demo_smoke():
    spec = importlib.util.spec_from_file_location("demo_smoke", REPO / "scripts" / "demo_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strict_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def round_swing(swing: dict) -> None:
    for f in swing["frames"]:
        f["joints"] = [[round(c, 4) for c in p] for p in f["joints"]]


def check_wrist_series(value: dict, swing_id: str) -> None:
    """app/ghost/wrist.ts parseWristSeries, and the panel must show (usable entry)."""
    entry = (value.get("swings") or {}).get(swing_id)
    if not isinstance(entry, dict) or entry.get("usable") is not True:
        raise SampleError(f"wrist series has no usable entry for {swing_id}: the panel would be hidden")
    t, deg = entry.get("t_ms"), entry.get("roll_deg")
    ok = (isinstance(t, list) and isinstance(deg, list) and len(t) >= 2 and len(t) == len(deg)
          and all(isinstance(v, (int, float)) and math.isfinite(v) for v in t + deg)
          and all(b > a for a, b in zip(t, t[1:])))
    if not ok:
        raise SampleError("wrist series: t_ms / roll_deg don't match what the panel reads")


def build(mock_dir: Path, swing_name: str, sample_id: str, catalogue: dict) -> tuple[dict, dict[str, Any], dict]:
    """(catalogue entry, {file name: data}, new catalogue). Reads only; writes nothing."""
    swing_path = mock_dir / "filled" / f"{swing_name}.json"
    series_path = mock_dir / "wrist_series.json"
    for p in (swing_path, series_path):
        if not p.is_file():
            raise SampleError(f"missing {p.name} under the mock folder: run wrist.run with --filled-out "
                              "and --series-out first (docs/demo-runbook.md, beat 4)")
    swing = json.loads(swing_path.read_text(encoding="utf-8"))
    wrist = swing.get("wrist")
    meta = swing.get("metadata") or {}
    if not isinstance(wrist, dict) or not wrist.get("usable"):
        raise SampleError(f"{swing_name} has no usable wrist entry")
    if wrist.get("mock") is not True or meta.get("mock") is not True:
        raise SampleError(f"{swing_name} isn't mock data: for a real recording, follow the morning wrist-sensor "
                          "sample steps in docs/demo-runbook.md (pre-flight step 6 and Tab 3)")
    series_all = json.loads(series_path.read_text(encoding="utf-8"))
    if series_all.get("mock") is not True:
        raise SampleError("wrist_series.json isn't mock data")
    series_entry = (series_all.get("swings") or {}).get(swing_name)
    if not isinstance(series_entry, dict):
        raise SampleError(f"wrist_series.json has no entry for {swing_name}")

    hand = meta.get("hand") or "R"
    fps_real = swing.get("fpsReal")
    swing = {**swing, "id": sample_id}
    coach = coach_swing(swing, None, fps_real)
    coach["faults"] = detect_faults(swing, metrics=measure_swing(swing, None, fps_real))
    stroke = coach["stroke"]
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
            result = compare(swing, fix, amount, fps_real=fps_real, hand=hand)
        except ValueError as e:
            row["error"] = str(e)
        else:
            round_swing(result["you"]["swing"])
            round_swing(result["ghost"]["swing"])
            row["file"] = f"compare_{sample_id}_{fix}.json"
            compares[row["file"]] = result
        fixes[fix] = row

    round_swing(swing)
    rolled = "rolled wrist" if WRIST_FIX in flagged else "wrist not flagged"
    entry = {
        "id": sample_id,
        "label": f"{stroke.capitalize()} · MOCK wrist sensor ({swing_name}, {rolled}) · synthetic body, only the arm moves",
        "stroke": stroke, "swing": f"swing_{sample_id}.json", "coach": f"coach_{sample_id}.json",
        "fixes": fixes, "wristSeries": f"wrist_{sample_id}.json", "madeBy": MADE_BY,
    }
    series = {**series_all, "swings": {sample_id: series_entry}}
    files = {entry["swing"]: swing, entry["coach"]: coach, entry["wristSeries"]: series, **compares}

    swings_list = [s for s in catalogue["swings"] if s.get("id") != sample_id] + [entry]
    top_fixes = list(catalogue["fixes"]) + ([WRIST_FIX] if WRIST_FIX not in catalogue["fixes"] else [])
    units = {**catalogue.get("units", {}), WRIST_FIX: EDITS[FIXES[WRIST_FIX][0]]["unit"]}
    new_catalogue = {**catalogue, "fixes": top_fixes, "units": units, "swings": swings_list}
    return entry, files, new_catalogue


def check(entry: dict, files: dict[str, Any], catalogue: dict, new_catalogue: dict) -> dict[str, str]:
    """Serialise and check every file with /ghost's parsers; return {name: text}."""
    smoke = load_demo_smoke()
    text = {name: strict_json(data) for name, data in files.items()}
    text["catalogue.json"] = strict_json(new_catalogue)
    # The repo is public: no local path may end up in a sample.
    for name, body in text.items():
        for private in (str(Path.home()), "/private/", tempfile.gettempdir()):
            if private in body:
                raise SampleError(f"internal: {name} would contain a local path ({private!r})")
    try:
        smoke.parse_catalogue(json.loads(text["catalogue.json"]))
        smoke.parse_swing(json.loads(text[entry["swing"]]))
        smoke.parse_coach(json.loads(text[entry["coach"]]))
        for name in files:
            if name.startswith("compare_"):
                smoke.parse_compare(json.loads(text[name]))
    except smoke.DataError as e:
        raise SampleError(f"a file /ghost would refuse: {e}") from e
    check_wrist_series(json.loads(text[entry["wristSeries"]]), entry["id"])
    others = [s for s in new_catalogue["swings"] if s["id"] != entry["id"]]
    if (new_catalogue.get("defaultSwing") != catalogue.get("defaultSwing")
            or others != [s for s in catalogue["swings"] if s["id"] != entry["id"]]
            or new_catalogue.get("demoAmounts") != catalogue.get("demoAmounts")
            or new_catalogue["fixes"][:len(catalogue["fixes"])] != catalogue["fixes"]):
        raise SampleError("internal: the other samples would change")
    return text


def entry_files(entry: dict) -> set[str]:
    """Every file a catalogue entry names: its swing, coach, wrist series and compare files."""
    names = {entry.get(k) for k in ("swing", "coach", "wristSeries")}
    names |= {f.get("file") for f in (entry.get("fixes") or {}).values() if isinstance(f, dict)}
    return {n for n in names if isinstance(n, str)}


def refuse_taken_files(files: dict[str, Any], catalogue: dict, out_dir: Path, replacing: dict | None) -> None:
    """Refuse a file name another catalogue entry names, or one already on disk (unless it is the
    sample this script made and is replacing): the ID check alone misses e.g. --id fh_over_rotation,
    whose swing_fh_over_rotation.json is the hero's swing file."""
    owners = {name: s.get("id") for s in catalogue["swings"] if s.get("madeBy") != MADE_BY for name in entry_files(s)}
    mine = entry_files(replacing) if replacing is not None and replacing.get("madeBy") == MADE_BY else set()
    for name in sorted(files):
        if name in owners:
            raise SampleError(f"{name} belongs to catalogue entry {owners[name]!r}, not made by this script: "
                              "pick another --id")
        if (out_dir / name).exists() and name not in mine:
            raise SampleError(f"{name} already exists in the output folder: pick another --id")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mock_dir", type=Path, help="the mock session folder (filled/ and wrist_series.json)")
    ap.add_argument("--swing", default="synth-07", help="mock swing id (default synth-07, a rolled wrist)")
    ap.add_argument("--id", default=None, help="sample id (letters, digits, _ and -); default mock_wrist_<swing>")
    ap.add_argument("--out-dir", type=Path, default=REPO / "public" / "swings")
    ap.add_argument("--replace", action="store_true", help="replace a sample this script made with the same id")
    args = ap.parse_args(argv)

    sample_id = args.id or f"mock_wrist_{args.swing}".replace("-", "_")
    try:
        if not ID_RE.fullmatch(sample_id):
            raise SampleError(f"sample id {sample_id!r}: use letters, digits, _ and -")
        catalogue_path = args.out_dir / "catalogue.json"
        if not catalogue_path.is_file():
            raise SampleError(f"{args.out_dir} has no catalogue.json")
        catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
        old = next((s for s in catalogue["swings"] if s.get("id") == sample_id), None)
        if old is not None and (old.get("madeBy") != MADE_BY or not args.replace
                                or sample_id == catalogue.get("defaultSwing")):
            raise SampleError(f"catalogue already has {sample_id!r}"
                              + ("" if old.get("madeBy") == MADE_BY else ", not made by this script")
                              + ": pick another --id" + (", or pass --replace" if old.get("madeBy") == MADE_BY else ""))
        entry, files, new_catalogue = build(args.mock_dir, args.swing, sample_id, catalogue)
        refuse_taken_files(files, catalogue, args.out_dir, old if old is not None and args.replace else None)
        text = check(entry, files, catalogue, new_catalogue)
    except SampleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    cat_text = text.pop("catalogue.json")
    for name, body in text.items():
        (args.out_dir / name).write_text(body, encoding="utf-8")
    tmp = catalogue_path.with_suffix(".json.tmp")
    tmp.write_text(cat_text, encoding="utf-8")
    tmp.replace(catalogue_path)

    coach = files[entry["coach"]]
    print(f"coach: call {(coach.get('fault') or {}).get('id')}, ghost {coach.get('ghost_fix')} "
          f"{coach.get('ghost_fix_amount')}; all faults {[f['id'] for f in coach['faults']]}")
    wrist_file = entry["fixes"].get(WRIST_FIX, {}).get("file")
    if wrist_file:
        launch = files[wrist_file]["assumptions"]["launch"]
        print(f"firm_wrist: your aim {launch['you']['azimuth']['value']:+g} deg, ghost "
              f"{launch['ghost']['azimuth']['value']:+g} deg ({launch['you']['azimuth']['label']})")
    print(f"wrote {len(text)} files to {args.out_dir} and {'replaced' if old else 'appended'} catalogue entry "
          f"{sample_id!r} (other samples, defaultSwing and demoAmounts unchanged). Don't commit them.")
    print(f"open: /ghost?swing={sample_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
