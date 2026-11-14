# Ghost clip pipeline

## Film one clip live

One-time demo setup: install the existing `services/requirements.txt` environment,
put the MediaPipe heavy pose model at `~/ghost-models/pose_landmarker_heavy.task`
(or set `GHOST_POSE_MODEL`), and have **ffmpeg and ffprobe** on PATH. Portable
binaries can instead be selected with `GHOST_FFMPEG` and `GHOST_FFPROBE`. These
are server-side executable paths. No API keys are needed for deterministic coaching.

With that environment active, from `services/`:

```sh
python -m pipeline /path/to/new-clip.mov
```

Camera B and the output directory are optional. This reads timing metadata,
normalizes to real-time cadence, extracts camera-A pose, detects both wrists,
and chooses the higher wrist-speed peak **inside each swing window**. The hitting
wrist's contact position in a torso-aligned basis determines forehand/backhand.
The output goes to a new run under `data/processed/` (or `GHOST_SWINGS_DIR`).
The CLI prints the first swing ID. All accepted swings are saved with coach and
comparison JSON files, plus a manifest. Single-camera output is labelled
`source: "mono"`, `metadata.depth: "estimated"`; inferred depth is not stereo.

Manual overrides always win over automatic values:

```sh
python -m pipeline /path/to/new-clip.mov --slowdown 4 --hand L --stroke backhand --out-dir ../data/processed/live-manual
```

`--slowdown` is a uniform factor relative to the encoded/native cadence; 1 forces
real time. `--hand R|L` and `--stroke forehand|backhand` override inference. The
saved provenance is `auto` or `manual` for explicit/ordinary detection;
slowdown heuristics use `playback-intent` or `speed-retry`, and ambiguous strokes
resolved by the coach use `coach-inferred`; `metadata.hand` and `metadata.stroke` carry the resolved values. The
pipeline passes the resolved hand onward; the coach's standalone metadata-hand
handling remains owned by PR #38, with measure_extra.py kept equal to main.
The old three-positional stereo command remains supported below, including its
explicit sync and rate-switch controls. `--slowdown`/`--stroke` also override the
primary camera's legacy stereo settings.

### Timing metadata and its limits

The probe reads `avg_frame_rate`, `r_frame_rate`, stream/container tags, and video
QuickTime `elst` entries (versions 0 and 1). Non-unit edit rates are undone on the
native media clock: empty edits are padding, trims are retained, and slow sections
are mapped back to real seconds before pose extraction. `metadata.timeMapping`
preserves those rates; `sourceContactPlaybackSeconds` maps contact back to the
original movie. Intermediate processing is CFR, at most 120 fps; `fps`/`fpsReal`
describe that actual processing cadence, and `captureFps` records capture evidence.
Live `sourceContactSeconds` uses normalized real seconds even after a slowdown
retry; it is derived from the real window start plus the saved contact frame time.

Explicit numeric QuickTime extensions `com.apple.quicktime.capture.fps`,
`com.apple.quicktime.capture-frame-rate`, and `com.apple.quicktime.video-frame-rate`
are used **only if present**. They are not assumed to exist on every iPhone file.
When `com.apple.quicktime.full-frame-rate-playback-intent` is present without
non-unit edits, the AirDrop heuristic assumes factor 4 and records
`slowdownSource: "playback-intent"`. This is a heuristic, not a numeric capture
FPS in that tag; `--slowdown 1` overrides it for real-time footage with that tag.
The guessed timestamp base `r_frame_rate` is not treated as capture FPS: normal
60 fps and VFR 60 fps inputs without the playback-intent hint stay factor 1.
When capture/mapping metadata has been stripped (e.g. a burned-in slow render),
physical timing cannot be recovered from frame rates alone. Auto uses encoded
real-time cadence, records `timingBasis`/`timingWarning`, and allows `--slowdown`
to supply the missing information. If auto factor 1 produces no accepted swing,
the existing pose arrays are retried at factors 2, 4 and 8. A candidate is accepted
only if its hip-relative peak wrist speed is 12-35 m/s; among plausible candidates
the nearest to the interval midpoint wins. The selected factor is recorded as
`speed-retry` with a warning and the measured retry wrist speed. Manual slowdown
values are never retried. This is a demo recovery heuristic, not capture-rate
calibration. Manual timing retains edit-list trims and contact playback mapping;
it changes the source timing factor without restoring trimmed-away frames.
It never silently assumes every high-FPS clip is slow motion. Freeze/reverse edits and malformed timing are rejected clearly.

Optional audio transients provide a contact frame when one is nearby. Silence,
missing audio, or no matching transient always falls back to the hitting wrist's
speed peak; audio is never a required filter. Ball paths remain PREDICTED and
shot assumptions remain visible in the comparison result. An ambiguous geometric
stroke is handed to the coach with no forced stroke; its inference is stored
under `metadata.stroke` with `strokeSource: "coach-inferred"`. A valid later
swing in the upload is not lost just because an earlier stroke was ambiguous.

Metadata references: [FFmpeg frame-rate fields](https://www.ffmpeg.org/doxygen/9.0/structAVStream.html),
[QuickTime edit list](https://developer.apple.com/documentation/quicktime-file-format/edit_list_atom/edit_list_table),
and [Apple full-frame-rate playback intent](https://developer.apple.com/documentation/avfoundation/avmetadataidentifier/quicktimemetadatafullframerateplaybackintent).

### Upload API

Start from the repo root, with the Python environment active:

```sh
python -m uvicorn pipeline.server:app --app-dir services --port 8000
```

`GET /health` checks the local server. `POST /process` accepts multipart `file`
plus optional `slowdown`, `hand` and `stroke` fields; no settings are required:

```sh
curl -F "file=@new-clip.mov" http://localhost:8000/process
```

Use `curl.exe` in Windows PowerShell. Example manual fields are `-F slowdown=4
-F hand=L -F stroke=backhand`. The request runs in a worker thread and waits until
pose, deterministic coach and physics ghost results are saved. It returns 201
with `swingId`, `swingIds`, `coach`, `compare`, `webPath: "/ghost"`, and the run
report. A no-fault/unavailable-fix result has an unchanged comparison marked
`noCorrection: true`, with amount 0; it does not invent a correction.

Saved swings are immediately available from `GET /swings` and `GET /swings/{id}`,
and the existing `/coach/{id}` and `/compare/{id}` routes work with their resolved
hand/stroke. The current `/ghost` page can list API swings after refreshing its
API list; its existing picker selects them. This PR does not add an upload UI,
query-string auto-selection, or live coach captions to frontend-owned files.
The response carries the completed coaching/comparison for a future upload UI.
When the top fault cannot be animated, `/coach/{id}` returns the coach's supported
`ghost_fix`/`ghost_fix_amount` as actionable `fix`/`amount`; top fault/cue stay intact.
Only fixes in the physics library are returned, and `ghost_ready` reflects whether
an actionable fix is returned. Upload comparisons use the same selection.
Call FastAPI directly for processing: the existing Next.js catch-all proxy has a
30-second timeout, while CPU pose extraction may take longer.

Uploads are local MOV/MP4/M4V/AVI, at most 250 MB, 4K, five playback minutes and
30 real seconds. Only local-file protocols/container formats are allowed in the
media tools. Temporary uploads and decoded frames are removed after processing;
only JSON outputs remain. Failed processing publishes no manifest. Invalid
inputs/no tracked swing return 422, oversized uploads 413, and missing model/tools
or unavailable output storage 503. Existing outputs are never overwritten.
POST /process admits one job at a time using a non-blocking process-local
semaphore, acquired only after the upload is fully received and size-checked.
A slow uploader does not reserve the processing slot. A completed valid upload
gets 429 "A clip is already processing" if another job is running. Oversized
Content-Length gets 413 before the body is read. The slot is released on processing
success or failure. Use the default single-worker
API command when one job total is required; multiple server workers have separate
semaphores.

## Live validation

`python -m pytest pipeline/tests/test_live_clip.py` covers automatic timing,
hand, stroke, optional sound, manual provenance, upload validation and persistence.
The real-model integration case requires `GHOST_POSE_MODEL`, ffmpeg/ffprobe, and
`GHOST_LIVE_TEST_IMAGE` pointing to the official
[MediaPipe pose.jpg test asset](https://storage.googleapis.com/mediapipe-assets/pose.jpg).
It generates a short image-motion AVI under pytest's temporary directory and runs
upload -> real decoder -> real MediaPipe -> rejection of the rotating photograph
as a non-swing. No pose functions are mocked in that case. Successful saved swing,
coach and ghost integration uses a separate articulated synthetic pose fixture.
Neither is validation of squash technique or of a live phone recording. Without those
optional test assets it is explicitly skipped; no videos/models are committed.

## Stereo swing pipeline (Dev)

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
`metadata` are additive. New frames also include optional `filled` provenance
and `visibility` confidence; legacy files without these remain valid.
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
    {"t": 0.0, "joints": [[0.1, 0.2, 0.3]], "filled": [false], "visibility": [0.95]}
  ]
}
```

The example abbreviates `frames`, `joints`, `filled` and `visibility`: real output has at least two
frames and **33 finite `[x,y,z]` joints per frame in MediaPipe order**, metres,
+y up, hips centred separately in each frame. Time starts at zero for each swing;
`contactFrame` is a zero-based index **inside that swing**. Metadata retains the
source start and contact frame indices for comparison with the source video.

## Filled joint flags

Every newly serialized frame includes `filled`: 33 booleans parallel to `joints`.
True means that joint used temporal interpolation, bounded gap filling,
evidence below .5 visibility, a one-view depth estimate, or a parent copy.
Partial-coordinate repairs mark the whole joint. Stereo joints that
use camera B interpolated between recorded timestamps are also marked. Fallback
to mono uses the original camera-A observation mask. Flags are recorded before
cleaning, so smoothing cannot hide a gap; copying optional children marks each
copied joint at exactly the affected frames.

Observed joints remain false after ordinary smoothing, bone-length constraints
or coordinate transforms when their anchors were observed. Rebuilding a child
from a filled parent also marks the child. Flags describe reconstruction rather than confidence,
3D accuracy or ghost edits. Old frames may omit `filled`; absence means unknown
provenance. `scripts/check_swing.py` accepts old files and checks that present
flags contain exactly 33 booleans. Shared frontend types remain unchanged; the
additive wire field is documented in `docs/interfaces.md`.

`visibility` contains 33 finite values in [0, 1], in the same MediaPipe order as
`filled` and `joints`. Mono uses camera A's observation confidence; stereo uses
the maximum available camera confidence per joint. Missing/nonfinite image
observations contribute zero. Filling does not raise this exported confidence.
Consumers should skip a guessed joint when `filled[j]` is true, even if another
camera saw its 2D position confidently. Coach implementation and shared interface
files are outside this change; older JSON does not gain confidence retrospectively.

`metadata.hittingArmFilledPercent` is the percentage of saved frames where **any**
hitting-side shoulder, elbow or wrist is filled (11/13/15 for L; 12/14/16 for R).
It is a frame percentage, not a percentage of all 33 joint samples.

## Measurement limits and quality

- Swing proposals use hip-relative dominant-wrist speed (default threshold
  **8 torso lengths / second**, minimum accepted-peak spacing .5 real seconds),
  followed by a mandatory measured 3D gate: peak wrist speed at least **6 m/s**,
  prominence at least 3 m/s, half-prominence peak width at most .3 real seconds,
  and a preceding hip-relative wrist-track reversal. `--min-speed` adjusts proposal
  sensitivity; it does not bypass the metric gate. `metadata.peakWristSpeedMs`
  and `metadata.backswingVerified` record the accepted evidence. Saved windows
  start .6 real seconds before the selected contact, clipped at recording/rate
  boundaries or an unrepairable occlusion, and retain the follow-through.
  Smoothing uses about .06 real seconds rather than a fixed frame count.
  Speed-peak fallback proposes candidates but cannot admit a catch/feed without
  the metric peak and backswing. The direction is derived from
  the wrist near the peak, so hand choice and image rotation do not set its sign.
  The final gate searches the full .6 real seconds before the measured peak
  for a pullback followed by the forward sweep. It uses the local 3D sweep
  direction, with a minimum turn prominence of .04 torso lengths (2 cm at the
  default scale) to exclude tiny jitter; it does not require a fixed forward
  sweep distance, follow-through displacement or path coherence. Source history
  includes .05 s before the search boundary to confirm an edge reversal and
  .12 s for the allowed difference between image and metric peaks. This extra
  evidence can cross a rate boundary; peak widths and lookback bounds use real
  timestamps. It does not move the replay window or contact. No missing trajectory is
  interpolated by the admission check.
  The earlier 2D proposal heuristic still uses .12 torso lengths of pullback,
  .25 before the peak and .10 after it, .50 total forward sweep, and net/path
  coherence at least .60. Candidate spacing matches main: .5 real seconds,
  or 2.5 with `--tap-filter`, before the final reconstruction and metric gates.
  Backswing evidence stays inside the contiguous tracked hitting-wrist run;
  a cropped replay window never reintroduces an earlier missing interval.
  These are conservative geometric heuristics, not validated classifications:
  a cropped/foreshortened backswing can be missed, and a feed with a genuine
  swing-like motion can still pass. Tune against labelled real recordings;
  optional audio-confirmed contact is available without gating detection.
- **Contact uses a nearby audio transient when present, otherwise the wrist-speed
  peak estimate**. `metadata.contactMethod` makes that explicit. Stroke side is also a heuristic;
  validate it against labels before using it to score technique.
- Essential-matrix self-calibration uses visible shared 2D joints, then
  triangulates using confidence-weighted DLT (each camera's equations weighted
  by the square root of its visibility). Finite joints with positive visibility
  remain weighted evidence even below .5; they are flagged `filled` so a guessed
  position can support replay without silently becoming a coach measurement.
  It rejects insufficient correspondences, poor cheirality and
  excessive median reprojection error. Each joint must be in front of both
  cameras and reproject within 12 pixels in each image. If stereo fails and one
  reliable view remains, its ray is intersected with a bone-length sphere around a
  recovered parent. Length is learned from jointly observed frames; a reliable
  bone direction within .25 real seconds disambiguates depth. Without an anchor,
  length or consistent ray, the joint stays missing. The bad camera is not used.
  Recovered depths are flagged `filled`, and missing A detection pixels can use
  the recovered projection instead of hidden wrist predictions. Missing camera-B
  frames are never treated as confident observations by timestamp resampling;
  ordinary resampling between adjacent recorded frames remains supported.
- Selection is **per swing**, not a per-joint blend. Use `source: "stereo"`
  when calibrated reconstruction yields the eight required joints for its whole
  window (including explicitly flagged single-view recovery). Otherwise
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
- The selected reconstruction must retain **shoulders (11/12), elbows (13/14),
  wrists (15/16) and hips (23/24)**; camera B can rescue a hidden A joint.
  Mono retains finite image/world coordinates with **visibility > .1**, matching
  main's fallback policy. Values below .5 remain available but are marked filled.
  Per swing, `metadata.coreVisibility` reports the mean
  core-joint visibility (six decimal places), and `metadata.lowConfidence` flags
  values below .3 without discarding the swing. Nonfinite visibility is reported
  as zero confidence. Only bounded gaps are repaired by interpolating
  unit bone directions on the sphere (joint angles), retaining observed median
  bone lengths; the translating root uses bounded position interpolation.
  The default tolerance is **.25 real seconds**, matching main (30 missing
  frames at 120 fps, 7 at 30). `--max-gap-s` changes this tolerance. Cleaning
  is independent within each rate section; smoothing never mixes opposite sides
  of an unfilled gap. Ten-to-fifteen-frame hidden-arm intervals at 120 fps can
  be filled with explicit provenance; an A-only gap may also be reconstructed
  from actual B observations. Low visibility alone does not erase a joint.
  Longer/end gaps in required joints cause cropping or rejection.
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

`--hits-wav iphone-playback.wav` looks for a transient within +/-0.5 **real seconds**
and uses it for contact where possible; unmatched swings use a speed-peak estimate. Supply 16 kHz mono PCM16 audio from the
same rendered A clip, with matching time zero; detection uses `rise_db=25`.
`--tap-filter --hits-wav iphone-playback.wav` additionally sets peak speed ?7
hip-relative torso lengths/real second and peak spacing ?2.5 real seconds.
Audio remains optional; peak spacing also applies across rate switches.
Without tap mode the existing speed threshold and .5 s spacing remain available.
Audio transients are candidate hits, not a semantic classifier of ball sounds.

## Swing and coach API

With the services Python environment active, start the API from the repository
root with one command (same command on Windows and Mac; no clips/model needed
to start the server or check health):

```sh
python -m uvicorn pipeline.server:app --app-dir services --port 8000
```

`GET http://localhost:8000/health` returns `{"ok":true}` independently of the
swing catalogue, label CSV, clips, and model weights.

Set `GHOST_SWINGS_DIR` to an absolute processed-session folder or its parent.
The default processed directory is resolved relative to this source file.
Only manifest-listed files are served. When two runs contain the same swing ID,
list IDs are disambiguated as `<id>@<run-folder>`; use that ID for subsequent calls.
Missing output lists no swings. Unknown IDs return 404; corrupt catalogue data
returns 503; invalid measurement inputs return 422.

- `GET /swings` returns `{"swings":[{"id":"...","label":"early_wrist"}]}`.
  Labels come from `data/labels/labels.csv` (`pipeline_run`, `swing`,
  `intended_fault` columns). The join always uses run folder + swing file stem.
  `none` maps to `good`; accepted labels are good, early_wrist, over_rotation,
  straight_arm, open_stance and rolled_wrist. Missing/unlabelled rows return null.
  A legacy `<id>@<run-folder>` value can supply the run; if `pipeline_run` is
  also present they must agree. Unscoped rows are ignored, never applied to an
  arbitrary run. Override the CSV location with `GHOST_LABELS_CSV`. Bad columns,
  conflicting run declarations, or duplicate (run, swing) pairs
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
