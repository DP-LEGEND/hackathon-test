# /ghost data

`/ghost` replays real output from `services/`. Nothing in the browser measures or computes a metric: it only shows the numbers in these files.

| File in `public/swings/` | Made by | What it holds |
|---|---|---|
| `swing_2116_bh_stereo.json` | pipeline (two-camera stereo, 120 fps) | The input swing, the same as `data/samples/swing_sample.json` |
| `coach_2116_bh_stereo.json` | `coach.agent.coach_swing(swing, "backhand")` plus `faults` from `coach.faults.detect_faults` | Top fault and cue (the caption), and every fault, worst first |
| `compare_2116_<fix>.json` | `physics.compare.compare(swing, fix, amount)` | You and ghost swings, metrics, deltas, both PREDICTED ball paths |

One compare file exists for each fix in `physics.ghost.FIXES`. The fix size comes from the fault library's `fix_amount` when the coach flagged that fault. Otherwise it uses a small demo size (12° elbow, 15° shoulders, 40 ms wrist, taken from compare.py's examples). Joint positions are rounded to 0.1 mm, the input's precision, after every metric has been computed.

## Regenerate

Save the script below as `make_swing_data.py` outside the repo, for example in Downloads. Then run it from inside `services/` with the venv activated.

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
from physics.ghost import FIXES

SRC = Path("../public/swings/swing_2116_bh_stereo.json")
OUT = Path("../public/swings")
STROKE = "backhand"  # the clip is a labelled backhand; stroke detection is low confidence
DEMO_AMOUNT = {"straighten_elbow": 12.0, "turn_shoulders_more": 15.0, "hold_wrist_cock": 40.0}


def round_swing(swing):
    for f in swing["frames"]:
        f["joints"] = [[round(c, 4) for c in p] for p in f["joints"]]
        for key in ("racketTip", "racketThroat"):
            if f.get(key) is not None:
                f[key] = [round(c, 4) for c in f[key]]


def write(name, data):
    (OUT / name).write_text(json.dumps(data, separators=(",", ":"), allow_nan=False))


swing = json.loads(SRC.read_text())
coach = coach_swing(swing, STROKE)
coach["faults"] = detect_faults(swing, metrics=measure_swing(swing, STROKE))
write("coach_2116_bh_stereo.json", coach)
flagged = {f["fix"]: f for f in coach["faults"]}

for fix in FIXES:
    amount = flagged[fix]["fix_amount"] if fix in flagged else DEMO_AMOUNT[fix]
    result = compare(swing, fix, amount)
    round_swing(result["you"]["swing"])
    round_swing(result["ghost"]["swing"])
    write(f"compare_2116_{fix}.json", result)
```

If physics adds a new fix, add its file to `CLIP.compare` in `ghost-replay.tsx`.
