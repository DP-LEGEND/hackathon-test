# /ghost

The demo flow has four steps: **pick a swing**, **the coach's call**, **the ghost** making the fix, then **on court** with both PREDICTED ball paths. Nothing in the browser measures or computes a metric: it only shows numbers that `services/` produced.

| File | Job |
|---|---|
| `ghost-demo.tsx` | The flow: steps, which swing and fix, loading |
| `sources.ts` | Swings from the swing API or the saved samples |
| `ghost-stage.tsx`, `skeleton-scene.ts` | The 3D view (three.js) and playback |
| `compare.ts`, `swing.ts` | Checks the JSON before anything is drawn |

## Where swings come from

1. **Live, from Dev's Python service** (`services/pipeline/server.py`), reached through the same-origin Next.js proxy (`app/api/[...path]/route.ts`), so the browser never calls another origin. The page uses `GET /api/swings` (with each swing's label), `GET /api/swings/{id}`, `POST /api/coach/{id}` for the coach's call and `POST /api/compare/{id}` for each ghost. A 502 from `/api` means the service isn't running, and the page falls back to the saved samples.
2. **Saved samples in `public/swings/`.** These always work, including offline and on the deployed site. The demo opens on `defaultSwing` in `catalogue.json`: the real forehand over-rotation swing.

The ghost starts on the coach's `ghost_fix` with `ghost_fix_amount`, and the caption shows `ghost_note` when the ghost shows a different fix from the top fault. Older coach files without those fields fall back to the worst fault physics can fix. Fixes the coach didn't flag use a small fixed demo size (`demoAmounts` in the catalogue). A fix physics can't apply to a swing shows its reason. When a fix leaves both PREDICTED paths identical, the court step draws one path and says so.

To try live swings, run this from the repo folder with the venv activated:

```
python -m uvicorn pipeline.server:app --app-dir services --port 8000
```

Swings come from `data/processed/` unless `GHOST_SWINGS_DIR` points somewhere else.

## Saved sample files

| File in `public/swings/` | Made by | What it holds |
|---|---|---|
| `catalogue.json` | the script below (backhand), #35 (forehand) | The samples, each fix's size and file or why it's unavailable, units, demo sizes, `defaultSwing` |
| `swing_2116_bh_stereo.json` | pipeline (two-camera stereo, 120 fps) | The input swing, the same as `data/samples/swing_sample.json` |
| `coach_2116_bh_stereo.json` | `coach.agent.coach_swing(swing, "backhand")` plus `faults` from `coach.faults.detect_faults` | Top fault and cue (the caption), and every fault, worst first |
| `compare_2116_<fix>.json` | `physics.compare.compare(swing, fix, amount)` | You and ghost swings, metrics, deltas, both PREDICTED ball paths |
| `swing_fh_over_rotation.json`, `coach_fh_over_rotation.json`, `compare_fh_over_rotation_<fix>.json` | #35, the same way | The forehand over-rotation demo swing (one-camera depth) |

There is one compare file for each fix in `physics.ghost.FIXES`. A fix the coach flagged uses the fault library's `fix_amount`. Other fixes use a small demo size and are labelled as such. Joint positions are rounded to 0.1 mm, the input's precision, after every metric has been computed.

## Regenerate the saved samples

The script below regenerates the backhand sample. It updates only that swing's entry in `catalogue.json` and keeps the other swings and `defaultSwing`. Save it as `make_swing_data.py` outside the repo, for example in Downloads. Then run it from inside `services/` with the venv activated.

Mac:

```
cd services
python - < ~/Downloads/make_swing_data.py
```

Windows PowerShell (PowerShell has no `<`, so pipe the file in):

```
cd services
Get-Content $HOME\Downloads\make_swing_data.py | python -
```

```python
import json
from pathlib import Path

from coach.agent import coach_swing
from coach.faults import detect_faults, measure_swing
from physics.compare import compare
from physics.ghost import EDITS, FIXES

OUT = Path("../public/swings")
SWING_FILE = "swing_2116_bh_stereo.json"
STROKE = "backhand"  # the clip is a labelled backhand; stroke detection is low confidence
# Fix size when the coach didn't flag the fault (and for live swings): compare.py's examples.
DEMO_AMOUNT = {
    "straighten_elbow": 12.0, "bend_elbow": 12.0,
    "turn_shoulders_more": 15.0, "turn_shoulders_less": 15.0,
    "hold_wrist_cock": 40.0, "close_stance": 15.0,
}


def round_swing(swing):
    for f in swing["frames"]:
        f["joints"] = [[round(c, 4) for c in p] for p in f["joints"]]
        for key in ("racketTip", "racketThroat"):
            if f.get(key) is not None:
                f[key] = [round(c, 4) for c in f[key]]


def write(name, data):
    (OUT / name).write_text(json.dumps(data, separators=(",", ":"), allow_nan=False), encoding="utf-8")


missing = set(FIXES) - set(DEMO_AMOUNT)
assert not missing, f"add a demo amount for {missing}"

swing = json.loads((OUT / SWING_FILE).read_text())
coach = coach_swing(swing, STROKE)
coach["faults"] = detect_faults(swing, metrics=measure_swing(swing, STROKE))
write("coach_2116_bh_stereo.json", coach)
flagged = {f["fix"]: f for f in coach["faults"]}

fixes = {}
for fix in FIXES:
    amount = flagged[fix]["fix_amount"] if fix in flagged else DEMO_AMOUNT[fix]
    entry = {"amount": amount, "flagged": fix in flagged}
    try:
        result = compare(swing, fix, amount)
    except ValueError as e:  # e.g. the stance is already closer than that
        entry["error"] = str(e)
    else:
        round_swing(result["you"]["swing"])
        round_swing(result["ghost"]["swing"])
        entry["file"] = f"compare_2116_{fix}.json"
        write(entry["file"], result)
    fixes[fix] = entry

entry = {
    "id": swing["id"],
    "label": "Backhand · two-camera stereo · 120 fps",
    "stroke": STROKE,
    "swing": SWING_FILE,
    "coach": "coach_2116_bh_stereo.json",
    "fixes": fixes,
}
# Update only this swing's entry: keep the other samples and defaultSwing.
path = OUT / "catalogue.json"
catalogue = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"swings": []}
catalogue["fixes"] = list(FIXES)
catalogue["units"] = {fix: EDITS[edit]["unit"] for fix, (edit, _) in FIXES.items()}
catalogue["demoAmounts"] = DEMO_AMOUNT
others = [s for s in catalogue["swings"] if s["id"] != entry["id"]]
catalogue["swings"] = [entry] + others
path.write_text(json.dumps(catalogue, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
```

When physics adds a fix, add its demo size to `DEMO_AMOUNT` and run the script again. The page reads the fix list from the catalogue, so no code changes are needed.
