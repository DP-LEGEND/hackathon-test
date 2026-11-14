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
  and hips (23/24)**. Mono accepts finite image/world coordinates **regardless
  of visibility**, including zero; visibility estimates occlusion rather than
  whether MediaPipe returned a position. Only stereo retains its visibility
  threshold above .3. Per swing, `metadata.coreVisibility` reports the mean
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
- `fpsReal` equals `fps`; `contactFrame` remains the window-relative peak index
  returned by `find_swings`, including when a swing uses mono fallback.

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
