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
accepted swing, plus **`manifest.json`** listing files and rejected windows.
Load an individual swing file into the web replay, not the manifest or a wrapper.
Required fields match `lib/ghost/types.ts`; `side` and `metadata` are additive.
Shared TypeScript contracts and the frontend are unchanged.

```json
{
  "id": "<session>-swing-0001",
  "fps": 120,
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
  6 torso lengths / second, minimum peak spacing .5 real seconds), with .45 s
  before and .35 s after the peak. `--min-speed` adjusts the threshold.
- **Contact is estimated from the wrist-speed peak**, not an observed ball hit.
  `metadata.contactMethod` makes that explicit. Stroke side is also a heuristic;
  validate it against labels before using it to score technique.
- Essential-matrix self-calibration uses visible shared 2D joints, then
  triangulates. It rejects insufficient correspondences, poor cheirality and
  excessive median reprojection error. Each joint must be in front of both
  cameras and reproject within 12 pixels in each image.
- Focal lengths default to `1400 * source_width / 1920` pixels: an approximation,
  without lens-distortion calibration. Pass measured `--focal-a` and `--focal-b`
  where available. Metres are scaled using an assumed .5 m shoulder-mid to
  hip-mid torso; pass `--torso-m` for the player's measured length. This is an
  estimated-scale reconstruction, not a calibrated motion-capture measurement.
- Only short **bounded** missing runs are interpolated (default .1 real seconds,
  `--max-gap-s`). Longer gaps and missing endpoints stay invalid. A swing with
  any remaining missing joint is rejected, with its reason in the manifest;
  no NaN, Infinity or fabricated zero pose is serialized. Bone lengths are
  constrained to observed median lengths along the existing body chains.
- Exit 0: all detected swings written. Exit 2: some/all detected swings rejected
  (inspect manifest). Exit 1: invalid input, no swings, calibration/model failure,
  or output I/O failure. Existing nonempty output is never overwritten.
- No single-camera or mock-data fallback is presented as a stereo result.

## Testing

```bash
python -m pytest
```

Tests exercise sync interpolation, stereo reconstruction against known projected
3D points, clip-rate conversion, segmentation/side/contact indices, missing data,
strict JSON output, output preservation and CLI error handling. Synthetic inputs
are clearly confined to tests. Real clips and model weights must not be committed.
The legacy `python -m pipeline.run <clip>` single-camera tool remains available.
