# Stereo swing pipeline (Dev)

Run from **`services/`** in the Python 3.11/3.12 environment described in
`CLAUDE.md` (`pip install -r requirements.txt`). Download the MediaPipe model
using the URL in `pipeline/pose.py`, outside git, and set `GHOST_POSE_MODEL`
or pass `--model-path`. No automatic downloads or cloud uploads occur.

```bash
python -m pipeline ../data/raw/iphone.mov ../data/raw/ipad.mov ../data/processed/session-01
```

Inputs: two **already synced**, fixed-camera clips of one player, with a useful
stereo baseline, overlapping views, no cuts, and no changes in playback rate.
Default: both clips play in real time, start at the same instant, right-handed
player. The CLI does not infer sync, handedness, camera motion or variable
slow-motion ramps. MediaPipe extraction runs independently on both clips.

For a constant 4x slow iPhone export and real-time iPad:

```bash
python -m pipeline iphone.mov ipad.mov out/session-02 --slowdown-a 4 --offset-b 1.2 --side forehand
```

This means `B_time = A_time / 4 + 1.2` (all source times in playback seconds).
Use `--slowdown-b` if B is slowed too. Native high-frame-rate real-time video
still uses slowdown 1. `fps` and frame `t` in the output are **real-time**.
Use `--hand L` for a left-handed player. `--side forehand|backhand` overrides
the body-only automatic side heuristic for a known single-side recording.
Auto side can be `unknown` if the wrist is within 5 cm of the torso centreline.

## Output

A new/empty output directory receives one `<session>-swing-NNNN.json` per
accepted swing, **`manifest.json`** listing files and rejected windows, and a
local **`raw_cache.npz`** pose cache (see below).
Load an individual swing file into the web replay, not the manifest or a wrapper.
Required fields match `lib/ghost/types.ts`; `source`, `fpsReal`, `side` and
`metadata` are additive.
Shared TypeScript contracts and the frontend are unchanged.

```json
{
  "id": "<session>-swing-0001",
  "fps": 120,
  "fpsReal": 120,
  "source": "mono",
  "contactFrame": 54,
  "side": "forehand",
  "frames": [
    {"t": 0.0, "joints": [[0.1, 0.2, 0.3]]}
  ]
}
```

The example abbreviates `frames` and `joints`: real output has at least two
frames and **33 finite `[x,y,z]` joints per frame in MediaPipe order**, metres,
+y up, hips centred separately in each frame. Time starts at zero for each swing;
`contactFrame` is a zero-based index **inside that swing**. Metadata retains the
source start and contact frame indices for comparison with the source video.

## Measurement limits and quality

- Swing detection uses hip-relative dominant-wrist speed (default threshold
  **8 torso lengths / second**, minimum accepted-peak spacing .5 real seconds),
  with .45 s before and .35 s after the peak. `--min-speed` adjusts the threshold.
  Smoothing uses about .06 real seconds rather than a fixed frame count.
  A candidate also needs a pullback, fast forward sweep and follow-through;
  speed alone does not make a movement a swing. The direction is derived from
  the wrist near the peak, so hand choice and image rotation do not set its sign.
  Starting heuristic thresholds: .12 torso lengths of preceding pullback,
  .25 before the peak and .10 after it, .50 total forward sweep, and net/path
  coherence at least .60. Pattern filtering precedes duplicate suppression.
  These are conservative geometric heuristics, not validated classifications:
  a cropped/foreshortened backswing can be missed, and a feed with a genuine
  swing-like motion can still pass. Tune against labelled real recordings;
  audio-confirmed hits remain a separate follow-up.
- **Contact is estimated from the wrist-speed peak**, not an observed ball hit.
  `metadata.contactMethod` makes that explicit. Stroke side is also a heuristic;
  validate it against labels before using it to score technique.
- Essential-matrix self-calibration uses visible shared 2D joints, then
  triangulates. It rejects insufficient correspondences, poor cheirality and
  excessive median reprojection error. Each joint must be in front of both
  cameras and reproject within 12 pixels in each image to count as stereo.
- Selection is **per swing**, not a per-joint blend. Use `source: "stereo"`
  when both views yield the eight required joints for its whole window. Otherwise
  use the iPhone's MediaPipe world skeleton and label it `source: "mono"`.
  Missing iPad joints, failed calibration or unavailable overlapping coverage
  do not reject an otherwise usable iPhone swing. Mono depth is inferred by
  MediaPipe, not measured by stereo; do not present it as stereo accuracy.
  `metadata.fallbackReason` records why stereo was unavailable.
- Focal lengths default to `1400 * source_width / 1920` pixels: an approximation,
  without lens-distortion calibration. Pass measured `--focal-a` and `--focal-b`
  where available. Metres are scaled using an assumed .5 m shoulder-mid to
  hip-mid torso; pass `--torso-m` for the player's measured length. This is an
  estimated-scale reconstruction, not a calibrated motion-capture measurement.
- The iPhone must retain **shoulders (11/12), elbows (13/14), wrists (15/16)
  and hips (23/24)**. Mono requires finite image/world coordinates and
  **visibility above .1**. Stereo retains its stricter visibility threshold
  above .3. Per swing, `metadata.coreVisibility` reports the mean
  core-joint visibility (six decimal places), and `metadata.lowConfidence` flags
  values below .3 without discarding the swing. Nonfinite visibility is reported
  as zero confidence. Only **bounded** missing coordinate runs are interpolated
  (default **.25 real seconds**, `--max-gap-s`); longer gaps/endpoints in the
  required joints reject that swing.
  Knees, ankles, face, hand and foot landmarks are optional. Missing optional
  coordinates repeat their parent **after** orientation/scaling; their indices
  are disclosed in `metadata.approximatedJoints`. These are replay placeholders,
  not measurements to use for those joints' metrics. No NaN/Infinity is serialized.
  Torso direction supplies up when ankles are unavailable. Bone lengths are
  constrained to observed median lengths along the existing body chains.
- Exit 0: all detected swings written. Exit 2: some written, some rejected.
  Exit 1: none usable (`manifest.status: "failed"`), invalid input, no detections,
  model failure or output I/O failure. Existing accepted swing output is preserved.
- `fpsReal` equals `fps`. `contactFrame` is window-relative: an audio transient
  when confirmed within the same rate section, otherwise a wrist-speed estimate.

## Pose cache and safe reruns

Raw arrays for both cameras are saved **before reconstruction**. Rerun into an
output folder containing only `raw_cache.npz` and/or a zero-written failed
manifest to retry without the expensive pose step. `--no-cache` forces fresh
extraction and atomically refreshes the cache. Corrupt/stale caches are recomputed.
Cache identity includes both videos' contents in camera order, model contents,
extraction version and resize setting. Reconstruction/sync/threshold changes
reuse the same raw arrays. Cache reads use `allow_pickle=False`; weights and
videos must still be present to validate identity. Hashing still reads the files,
so a warm run is not zero I/O. Keep caches, recordings and generated output out of git.

For tuning **after successful output**, use a shared cache and a fresh output
directory rather than replacing accepted swings:

```bash
python -m pipeline iphone.mov ipad.mov out/run-01 --cache-dir out/fh-pose-cache --slowdown-a 4 --offset-b -57.95 --side forehand
python -m pipeline iphone.mov ipad.mov out/run-02 --cache-dir out/fh-pose-cache --slowdown-a 4 --offset-b -57.95 --side forehand --min-speed 8
```

Use the same commands with the active Python environment on Windows. If the first
run used the default cache, pass `--cache-dir out/run-01` on a fresh-output rerun.
Do not run two pipeline writers against the same output/cache directory at once.

## Testing

```bash
python -m pytest
```

Tests exercise sync interpolation, stereo reconstruction against known projected
3D points, clip-rate conversion, segmentation/side/contact indices, missing data,
strict JSON output, per-swing mono fallback, required/optional joints, cache reuse
and invalidation, output preservation and CLI error handling. Synthetic inputs
are clearly confined to tests. Real clips and model weights must not be committed.
The legacy `python -m pipeline.run <clip>` single-camera tool remains available.


## Follow-ups: early release, playback switches, tap filtering

The early-wrist block was lost at two checks: `_swing_pattern` required a
canonical pullback/sweep; surviving peaks then failed the complete core-joint
window gate. The CLI now permits plain speed peaks (`metadata.detection =
"speed_peak"`) and crops occluded window edges only when at least .15 s before
and .08 s after contact remain continuously tracked. It still rejects missing
core joints through contact. Rejections include joint IDs, playback peak seconds,
and the detection method, so inspect 715?950 s for IMG_2115. Synthetic regression
coverage proves these paths; actual recovery counts need the real cached poses.

Switch flags are **QuickTime playback seconds**, not real elapsed seconds:

- IMG_2115: `--slowdown-a 4 --a-realtime-after 1476` (24:36).
  PR #17 measured 1475.8; use that value if reproducing its exact boundary.
  Its initial real-speed duration was only estimated (~15 s); add
  `--a-realtime-before 15` only after checking the recording.
- IMG_2116: `--slowdown-a 4 --a-realtime-before 80 --a-realtime-after 1310`
  (01:20 and 21:50).
- Camera B has equivalent `--b-realtime-before` / `--b-realtime-after` flags.

Each clock integrates elapsed time continuously: initial real duration + slow
playback duration / slowdown + ending real duration. Stereo samples both cameras
on their mapped clocks. `--offset-b` means B playback seconds at A playback zero;
negative times extrapolate B's initial rate. When using an observed shared hit
at playback A=a, B=b, calculate the real offset as `clock_b.real(b) -
clock_a.real(a)`, then convert it back to B playback seconds for `--offset-b`.
The old constant-slowdown sync values must be rechecked when adding an initial
real-speed segment. Exported windows stop at switches, so their FPS, timestamps,
gap limits and contact indices all describe one constant real rate. Frames right
at a switch can therefore have shortened swing context.

`--hits-wav iphone-playback.wav` requires a transient within ?0.5 **real seconds**
and uses it for contact where possible. Supply 16 kHz mono PCM16 audio from the
same rendered A clip, with matching time zero; detection uses `rise_db=25`.
`--tap-filter --hits-wav iphone-playback.wav` additionally sets peak speed ?7
hip-relative torso lengths/real second and peak spacing ?2.5 real seconds.
Audio confirmation runs before spacing, including spacing across rate switches.
Without tap mode the existing speed threshold and .5 s spacing remain available.
Audio transients are candidate hits, not a semantic classifier of ball sounds.

## Swing and coach API

With the services Python environment active, start the API from the repository
root with one command (same command on Windows and Mac):

```sh
python -m uvicorn pipeline.server:app --app-dir services --port 8000
```

Set `GHOST_SWINGS_DIR` to an absolute processed-session folder or its parent.
The default processed directory is resolved relative to this source file.
Only manifest-listed files are served. When two runs contain the same swing ID,
list IDs are disambiguated as `<id>@<run-folder>`; use that ID for subsequent calls.
Missing output lists no swings. Unknown IDs return 404; corrupt catalogue data
returns 503; invalid measurement inputs return 422.

- `GET /swings` returns `{"swings":[{"id":"...","label":"early_wrist"}]}`.
  Labels come from `data/labels/labels.csv` (`swing`, `intended_fault` columns).
  `none` maps to `good`; accepted labels are good, early_wrist, over_rotation,
  straight_arm, open_stance and rolled_wrist. Missing/unlabelled rows return null.
  A matching `<id>@<run-folder>` row takes precedence over an unsuffixed row.
  Override the CSV location with `GHOST_LABELS_CSV`. Bad columns or duplicate IDs
  return 503. Labels describe the intended filming block, not measured faults.
- `GET /swings/{id}` returns the saved skeleton JSON.
- `POST /coach/{id}` runs deterministic `coach_swing` (which calls `detect_faults`).
  Returns `fault` (top fault or null), `cue`, `fix`, `amount`, `ghost_ready`,
  measured `metrics`, and the other coach fields. `fix` and `amount` can be sent
  directly to compare. No detected fault or an unsupported ghost edit returns
  null fix/amount; it never substitutes an unrelated correction. No AI key needed.
- `POST /compare/{id}`, JSON `{"fix":"bend_elbow","amount":12}`, returns the
  physics comparison: `you.swing`, `ghost.swing`, each side's metrics and `ball`,
  plus `delta` and `assumptions`. Both ball paths retain `label: "PREDICTED"` and
  `predicted: true`. Ball points are court metres: origin at front-left floor,
  x across the court, y up, z towards the back wall. Skeletons retain their
  original hip-centred coordinates; assumed ball launch/contact and estimated
  racket speed are disclosed in `assumptions` and the physics result.
  The previous `POST /swings/{id}/ghost` remains an alias.

Every measurement uses the saved pipeline `contactFrame` and `fpsReal` when
present. Missing/out-of-range contact frames return 422, never a newly inferred
wrist peak. Sound-timed pipeline outputs retain their audio-transient contact;
legacy/sample contacts remain estimates, as disclosed by `contactMethod`.

FastAPI CORS always permits `http://localhost:3000`; `GHOST_WEB_ORIGIN` adds an
optional second origin. Open `http://localhost:8000/docs` for endpoint schemas.
The Next.js catch-all forwards `/api/<path>` to the same FastAPI `<path>`.
`GHOST_API_URL` is server-only and defaults to `http://localhost:8000`; a configured
base path is preserved. For example, the web app calls `POST /api/coach/{id}` and
`POST /api/compare/{id}`. Upstream status/body are preserved; connection failure
or a 30-second timeout returns a clear 502. Responses are not cached.

Sample-based API tests run with `python -m pytest pipeline/tests/test_coach_api.py`
from services/. Proxy tests (Node 26) run from the repository root:

```sh
node --experimental-strip-types "app/api/[...path]/route.test.mjs"
```
