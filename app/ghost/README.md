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

### Opening a swing by link

`/ghost?swing=<id>` opens on that swing at the coach's call. `/upload` ("Try your own swing", linked from the header) sends a clip to the pipeline and then opens the new swing this way. The page waits for both lists before it decides, and a live swing wins over a saved sample with the same ID, so the swing on screen never switches. If neither list has the ID, the page says so and offers **Check again** (re-reads the live list) instead of showing a different swing. The demo reads the query in the browser, so `page.tsx` wraps it in `<Suspense>` (required by `useSearchParams` when the page is prerendered). It is keyed by the ID, so a new `?swing=` starts fresh even when Next has kept the page alive in the background.

### The coach's voice

Once a swing's coach result has loaded, the page asks `GET /api/coach/{id}/voice` (Henoch's #60) for `{cue, audioUrl, source}`, unless the live service is known to be offline. A first call can take a few seconds (Claude, then ElevenLabs), so the plain caption shows meanwhile. Then `cue` replaces the caption's cue. **Hear the coach** plays `audioUrl` with `new Audio(audioUrl).play()`, and a new play stops the one before. The button is hidden when `audioUrl` is null. The caption says **worded by Claude** only when `source` is `"claude"`. A 404 (before #60 is merged, or a swing the service doesn't know, such as a saved sample whose run isn't in `data/processed`), any error, a 60 s timeout or a malformed answer all keep the plain caption, with no message. Only an inline `data:audio/…` clip or a same-origin path is played.

The ghost starts on the coach's `ghost_fix` with `ghost_fix_amount`, and the caption shows `ghost_note` when the ghost shows a different fix from the top fault. Older coach files without those fields fall back to the worst fault physics can fix. Fixes the coach didn't flag use a small fixed demo size (`demoAmounts` in the catalogue). A fix physics can't apply to a swing shows its reason. When a fix leaves both PREDICTED paths identical, the court step draws one path and says so.

## Where the player stands (display only)

Pipeline skeletons are hip-centred, y up, and face +z. The court's front wall is at z = 0, so `skeleton-scene.ts` turns both figures 180° about y (`[x, y, z] -> [-x, y, -z]`). Seen from behind, a right-handed forehand then hits on the player's right, as in the phone video. On the court step, the player moves so the hitting wrist at the contact frame is exactly over the PREDICTED ball's first point in x and z. The wrist is joint 16 for `R` and 15 for `L`, from `metadata.hand`, else the hand compare used. The ghost moves by the same offset. Height isn't snapped: the wrist is about 0.9 m up at contact and the ball's assumed start is 0.6 m, so the feet stay on the floor and the ball leaves about 30 cm below the hand. Physics would need to start the ball at the measured hand height for both to line up.

None of that applies when a compare response has top-level `"coordinateSystem": "court"`: physics has then already placed the swings in court coordinates. Those swings are drawn exactly as given, with no turn, floor offset or placement. Only the side-by-side 1.1 m ghost shift stays, and the ghost's PREDICTED ball path moves with it, so it still leaves from the ghost's hand. The page notes that this is display only. The camera aims at the hips at contact. Any other value, or no field, means hip-centred. The raw swing shown before a compare loads is always hip-centred.

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
