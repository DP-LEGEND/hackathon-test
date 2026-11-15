# Wrist sensor (owner: Henoch)

The camera can't see a **rolled wrist** (the forearm rotating through contact). A phone
strapped to the forearm can. This folder turns a Sensor Logger recording into per-swing
forearm-roll numbers that the coach's `rolled_wrist` fault reads. It also exports a small
roll-angle graph for the ghost page.

It also produces four **ESTIMATES**, each labelled:
- **Tempo:** backswing start, top of backswing, contact, follow-through end, and backswing
  start to contact.
- **Impact:** peak g and ring-down time. **Reported, not judged**: nothing says clean or mishit.
- **Racket speed** (needs the camera): camera wrist velocity + gyro x lever, labelled
  `ESTIMATE (sensor)` (`MOCK (sensor)` on mock data). Physics' `compare()` prefers it to the
  video estimate.
- **Occlusion fill** (needs the camera): the camera's hidden forearm rebuilt from the phone,
  marked `sensorAssisted`. Comes with the camera/phone agreement error.

Code measures, Claude explains: the coach only quotes these numbers. Swings without
usable sensor data skip `rolled_wrist` (it shows under `not_measured`). Nothing is guessed.
A **shadow swing** (no ball, so no impact) is timed from the double tap; its impact fields
are null. Without the phone's own orientation, the integrated gyro takes over.

**Tested on MOCK data** (`synth.py`) **and one real shadow session** (no ball: see
[Shadow sessions](#shadow-sessions-no-ball)). The real-data `rolled_wrist` lines in
`coach/faults.py` come from that one shadow session (`WRIST_SESSION_FH` / `WRIST_SESSION_BH`:
forehand 145.75°, backhand 124.3°). They judge only rolls timed at the forearm's fastest turn
(`contact_source: "gyro peak"`), as that session's were, and must be retuned on real hits.
`MOCK_ROLLED_WRIST` (39.2°) is for mock entries (`synth.py`) only, never for real data.

## Recording (tonight)

1. Sensor Logger: turn on **Accelerometer, Gyroscope, Orientation** at the fastest rate (100 Hz).
2. Strap the phone to the **forearm of the hitting arm**, long edge along the forearm,
   screen facing out. It must not slip.
3. Start the camera, then start Sensor Logger.
4. **Tap the strapped phone twice, sharply, in view of the camera** (about half a second apart).
5. Play: 5 normal swings, then 5 rolled-wrist swings (or the other way round). Keep the arm
   still between swings if you can.
6. Stop, export as **CSV (zip)**, and put it in `data/raw/wrist/` (git-ignored).
   **Never commit real CSVs or video.** This folder's `.gitignore` blocks `*.csv` and `*.zip`.
7. Note the video time of the **first tap** (QuickTime seconds, the same clock as the contact
   times). Add the swings to `data/labels/labels.csv` as usual, labelled `none` or `rolled_wrist`.

## Run it

From inside `services/` with the venv active:

```
python -m wrist.synth /tmp/wrist-mock --camera --mishit 3 --shadow 4
```
Writes a mock export, `contacts.csv` and `labels.csv`, then prints the next command.
`--camera` also writes MOCK pipeline swing JSONs (`swings/`): an occluded wrist or elbow
near contact, and a video contact frame a frame or two off. `--mishit 3` makes the 4th
swing ring like an off-centre hit. `--shadow 4` makes the 5th a shadow swing: same motion,
no impact.

```
python -m wrist.run ../data/raw/wrist/<export>.zip --contacts ../data/labels/labels.csv --run <pipeline_run> --video-tap <seconds>
```
Writes `data/raw/wrist/wrist_metrics.json` and `wrist_series.json`, and prints the taps,
impacts, alignment errors and every swing's numbers and ESTIMATES. `--contacts` can also be
a folder of pipeline swing JSONs.

Add `--swings <folder of pipeline swing JSONs>` for racket speed and the occlusion fill. If
`--contacts` is already that folder, you don't need it. Every camera swing is then written to
`data/raw/wrist/swings/` (`--swings-out`; the old `--filled-out` still works) with its wrist
entry attached as `swing["wrist"]` and the forearm rebuilt where it was occluded. `--lever`
sets the wrist-to-sweet-spot lever (default 0.55 m, physics' `RACKET_LEVER_M`).

```
python -m wrist.tune ../data/raw/wrist/wrist_metrics.json ../data/labels/labels.csv --run <pipeline_run>
```
Picks the threshold from the normal and rolled swings and reports how well they separate.
Copy its rule into `THRESHOLDS` in `coach/faults.py` by hand.

```
python -m coach.agent ../data/raw/wrist/swings/<id>.json
python -m physics.compare ../data/raw/wrist/swings/<id>.json straighten_elbow 12 --no-swings
```
Coaches one swing with its wrist data, and compares it with its ghost using the sensor's
racket speed. (`coach.agent <swing>.json --wrist wrist_metrics.json` attaches the entry itself.)

Windows: same commands, `python` inside the activated venv.

## What it measures (per swing, -150 ms to +100 ms around contact)

| Key in `wrist_metrics.json` | Coach measurement | Meaning |
|---|---|---|
| `roll_change_deg` / `roll_change_abs_deg` | `forearm_roll_deg` (the size) | Forearm roll over the window: the gyro integrated about the forearm axis (on the integrated-gyro fallback, with the estimated still bias removed first). `roll_method` says so. |
| `roll_change_gyro_deg` | (same number) | Kept for readers of older files; equal to `roll_change_deg`. |
| `roll_change_twist_deg` | (cross-check only) | The twist of the orientation over the window about the forearm axis. Ill-conditioned when the swing turns near a half-turn, which real swings do (Known limits), so it is never coached. |
| `peak_roll_rate_dps` / `_abs_dps` | `forearm_roll_rate_dps` | Fastest gyro rate about the forearm axis |
| `peak_angular_speed_dps` | `forearm_speed_dps` | Fastest total turn rate of the forearm (context only) |

Contact = the sensor's own impact spike, so sync error doesn't move these numbers.
Sync only decides which swing each impact belongs to. The exception is a swing with no
impact (`contact_source: "double tap"`): its contact is the double tap's prediction, so the
sync error does move its window. In a shadow session (`shadow.py`, no ball at all) contact is
each swing's fastest forearm turn (`contact_source: "gyro peak"`, an ESTIMATE).

Built-in checks, all reported in the output:
- **Orientation.** Sensor Logger doesn't document its quaternion's direction, so the code
  picks the one that matches the gyro. If neither matches, or the export has no
  `Orientation.csv`, it falls back to the **integrated gyro** (`orient.py`): the gyro's
  offset is measured on the still stretch around the two taps and removed, then the gyro is
  integrated. `sensor.orientation_used` and each swing's `orientation_source` say which, and
  there's a warning. The taps are at the start, so they can't bound drift for later swings;
  the camera fit is redone for every swing, which cancels slow drift.
- **Forearm axis.** Default is `y` (long edge along the forearm). If another axis carries
  more acceleration through contact, there's a warning: rerun with `--axis x` or `--axis z`.
- **Sync.** Two taps, then impacts. A spike only counts as an impact when the forearm is
  turning fast (more than 360 deg/s) and it's at least 2 g high; footsteps, knocks and a fast
  swing's own ~1 g centripetal bump are listed as rejected. The first tap gives the
  video-to-sensor offset. Contacts pair with impacts in order, and each pair reports its
  **alignment error in ms**. Pairs off by more than 100 ms are skipped. Without
  `--video-tap` the offset is fitted to the impacts, and the report says this is a weaker
  check.
- **Shadow swings.** With `--video-tap`, a video contact with no impact within 300 ms of its
  tap-predicted time, while the forearm is swinging there, is timed from the double tap
  alone: every number except the impact, with `impact`, `impact_s` and `align_error_ms` null.
  If the arm isn't swinging at that time (a typo, a swing the phone never felt), it stays
  untrusted.

## The ESTIMATES (tempo, impact, racket speed, occlusion fill)

All of these are tested on MOCK data only so far. Until real swings check them, quote
them as ESTIMATES.

**Tempo** (`tempo.py`, per swing `tempo`). This reads the forearm's total turn rate |gyro|,
smoothed over 30 ms. "Rest" = 50 deg/s or 5% of the swing's peak, whichever is higher.
- `backswing_start_ms`: the speed rises past rest before contact.
- `forward_start_ms`: the top of the backswing. Either the end of a pause at the top, or
  the dip where a looped swing turns forward.
- `follow_through_end_ms`: the speed is back under rest after contact.

All times are ms from contact (the sensor's impact spike, or the double tap's prediction).
Also given: `backswing_ms`, `forward_swing_ms`, `follow_through_ms`, `tempo_ratio` (backswing /
forward swing), and `backswing_to_contact_ms`, the whole swing from backswing start to contact.
An event it can't find is `null`, with a reason: the arm never settled, or the gyro shows no
turn-around because the backswing was all shoulders.

**Impact** (`impact.py`, per swing `impact`; null for a shadow swing). **Reported, not
judged** (`"judged": false`): nobody has labelled real clean hits and mishits yet.
- `peak_g`: the spike's height after the high-pass that sync uses.
- `width_ms`: how long it stays above half that height.
- `ring_down_ms`: from the peak until the shaking dies away, i.e. the last sample above
  `threshold_g` (10% of the peak, or the noise floor if higher) before 50 ms of quiet.
  `ring_down_capped` means no 50 ms of quiet was found before the search stopped: either
  it was still shaking 300 ms later, or the recording ended first (an impact less than
  300 ms before the end). Either way `ring_down_ms` is only a floor.
- `clipped`: true when the accelerometer hit its limit. `resolution_ms`: 10 at 100 Hz.

A clean hit is one sharp knock; an off-centre hit keeps the racket and arm shaking. Mock
run: the ringing swing rang down in 73-75 ms, the nine clean ones in 27-34 ms.

**Camera alignment** (`fuse.py`). On the frames where the camera saw the hitting elbow and
wrist (not `filled`), the camera's forearm direction should equal the phone's forearm axis,
turned by the phone's orientation and then by one fixed rotation into the camera's axes.
The code fits that rotation, the exact strap axis, and a camera time shift (up to +-60 ms,
for a contact frame that's a frame or two off). Reported in `occlusion_fill`:
- `agreement_deg`: the angle between the camera's and the phone's forearm, on the visible
  frames (median, p90, max). This one is in-sample.
- `holdout_deg`: hide the quarter of visible frames nearest contact, refit, and measure on
  them. This is the honest number for how well the fill does inside an occlusion.
- `time_shift_ms`, `strap_axis_offset_deg`.

The fill only runs when the median agreement is under 12 deg.

**Occlusion fill** (per swing `occlusion_fill`, and the swing JSONs in `swings/`).
Frames where the hitting wrist or elbow is marked `filled` get their forearm direction from
the phone:
- **Wrist filled:** wrist = elbow + forearm length x phone direction. The hand points move
  with the wrist, so the hand bones keep their lengths. Their orientation stays the
  pipeline's own.
- **Elbow filled, wrist seen:** the elbow goes on the circle that keeps both arm bones'
  lengths, nearest the phone's direction.

`filled` flags stay true, because the camera still didn't see those joints. Instead, every
frame gets a `sensorAssisted` list (33 booleans, parallel to `joints`), true for each joint
the phone set: the wrist and the hand it carried, or the elbow. That's how a reader tells
"sensor-assisted" from "guessed" (proposed for `docs/interfaces.md`, pending the team's OK).
`metadata.wristSensorFill` lists the frames and the `orientationSource`. Mock run: rebuilt
joints are within 1 cm of the truth (0.3-2 cm with the integrated gyro), against 1.5–15 cm
for the pipeline's straight-line interpolation. Agreement and holdout are both about 0.1 deg
(the mock camera has no noise; real ones will be worse).

**Racket speed** (per swing `racket_speed_sensor`, labelled `ESTIMATE (sensor)`, or
`MOCK (sensor)` on mock data). This treats the forearm, hand and racket as one rigid lever:
locked wrist, racket along the forearm, 0.55 m from the wrist joint to the sweet spot. That's
physics' `RACKET_LEVER_M` = `RACKET_HEAD_M` (0.45 m) + `GRIP_OFFSET_M` (0.10 m), the same
lever the video estimate uses.
`v_head = v_wrist (camera) + w_forearm (gyro) x lever`.
- With a trusted alignment, the two parts are added as vectors.
- Otherwise they're added as if parallel, which is an upper bound; `method` says which.
- With no camera, `value` is null and `rotationMs` gives the gyro part alone.

The gyro is averaged over the 20 ms up to the synced contact. The camera wrist is the
sensor-filled one when the occlusion covers contact (`wristFromSensorFill`). Mock run:
within 4% of the truth.

### In physics' compare()

`compare()` reads `swing["wrist"]` (`wrist.fuse.attach_wrist_entries` puts it there; `wrist.run
--swings-out` writes the swings). When the entry is usable and its `racket_speed_sensor` has a
value, **your** racket speed is the sensor's, labelled `ESTIMATE (sensor)` / `MOCK (sensor)`.
The **ghost** has no sensor, so its speed is yours x (ghost / you) video estimates: only the
fix changes it. Otherwise both sides use the video estimate (`ESTIMATE (video)`).
`assumptions.racketSpeed` says which source was used and why. The ghost's output swing never
carries your `wrist` entry.

## Outputs

`wrist_metrics.json` (one entry per swing, keyed by swing id):

```json
{"mock": false, "sensor": {"orientation_used": {"source": "phone", ...}, ...}, "sync": {...}, "warnings": [],
 "estimates": {"label": "ESTIMATE", "lever_m": 0.55, "camera_swings": 10, "note": "..."},
 "swings": {"<swing id>": {"usable": true, "skip_reason": null, "mock": false,
   "contact_source": "impact spike", "align_error_ms": 7.0, "impact_s": 41.406, "contact_s": 41.406,
   "roll_change_deg": 58.6, "roll_change_abs_deg": 58.6, "roll_change_gyro_deg": 58.6,
   "roll_change_twist_deg": 58.5, "roll_method": "gyro integrated about the forearm axis",
   "peak_roll_rate_dps": 460, "peak_roll_rate_abs_dps": 460,
   "peak_angular_speed_dps": 1321, "window_ms": [-150, 100], "orientation_source": "phone",
   "tempo": {"label": "ESTIMATE", "backswing_start_ms": -719, "forward_start_ms": -163,
             "contact_ms": 0, "follow_through_end_ms": 174, "backswing_ms": 556,
             "forward_swing_ms": 163, "follow_through_ms": 174, "tempo_ratio": 3.41,
             "backswing_to_contact_ms": 719, ...},
   "impact": {"label": "ESTIMATE", "peak_g": 9.31, "width_ms": 12.2, "ring_down_ms": 32.9,
              "ring_down_capped": false, "threshold_g": 0.93, "clipped": false,
              "resolution_ms": 10.0, "judged": false, "note": "..."},
   "racket_speed_sensor": {"value": 17.0, "unit": "m/s", "estimate": true, "label": "ESTIMATE (sensor)",
                           "method": "camera wrist velocity + gyro x lever, added as vectors",
                           "gyroDps": 1139, "leverM": 0.55, "rotationMs": 10.9, "wristSpeedMs": 6.09, ...},
   "occlusion_fill": {"label": "ESTIMATE", "applied": true, "orientation_source": "phone",
                      "frames": [109, ...], "joints": ["wrist", "hand"],
                      "agreement_deg": {"median": 0.1, "p90": 0.1, "max": 0.4, "n": 179},
                      "holdout_deg": {"median": 0.1, ...}, "time_shift_ms": 23.0,
                      "strap_axis_offset_deg": 5.2, "forearm_m": 0.26, "moved_m": {...}, ...}}}}
```

A shadow swing's entry has `"contact_source": "double tap"`, `contact_s` (the tap
prediction), and `impact`, `impact_s` and `align_error_ms` null. Everything else is there.

`wrist_series.json`, **for Sammy's "wrist rotation" graph** (about 22 KB for 10 swings
with camera swings). Mock example, with every field, one mishit (`synth-04`) and one shadow
swing (`synth-05`, impact null):
[examples/wrist_series.mock.json](examples/wrist_series.mock.json).

```json
{"mock": true, "window_ms": [-150, 100], "forearm_axis": "y",
 "angular_speed_t_ms": [-1500, -1480, ..., 1000],
 "swings": {"<swing id>": {"t_ms": [-300, -290, ..., 200], "roll_deg": [...],
                           "roll_change_deg": 58.5, "usable": true, "contact_source": "impact spike",
                           "angular_speed_dps": [3, 4, ..., null],
                           "tempo": {"label": "ESTIMATE", "backswing_start_ms": -719,
                                     "forward_start_ms": -163, "contact_ms": 0, "follow_through_end_ms": 174,
                                     "backswing_to_contact_ms": 719},
                           "impact": {"label": "ESTIMATE", "peak_g": 9.31, "width_ms": 12.2,
                                      "ring_down_ms": 32.9, "judged": false},
                           "racket_speed_sensor": {"value": 17.0, "unit": "m/s", "label": "ESTIMATE (sensor)"},
                           "forearm_fill": {"label": "ESTIMATE", "frames": [...], "t_ms": [...],
                                            "elbow": [[x, y, z], ...], "wrist": [[x, y, z], ...],
                                            "agreement_deg": 0.1}}}}
```

`t_ms` is ms from contact, one point every 10 ms. `roll_deg` is 0 at -150 ms, so at
+100 ms it equals `roll_change_deg`, the number the coach quotes. Suggested drawing:
shade the window, and use orange `#FF8A3D` for the player's line. If `mock` is true,
show a MOCK label.

The new parts:
- **Tempo graph:** draw `angular_speed_dps` (every 20 ms on `angular_speed_t_ms`, `null`
  off the recording), with the `tempo` events as markers.
- **`forearm_fill`:** the rebuilt elbow and wrist (camera axes, metres) on the swing's
  filled frames, at `t_ms` from contact. It's `null` when nothing was filled.
- **Labels:** show each block's own `label` on screen (ESTIMATE, ESTIMATE (sensor), MOCK
  (sensor)). `impact` is `null` for a shadow swing: say "no impact" rather than a number.

## How the coach uses it

Each swing can carry its own entry as an optional field: `swing["wrist"]`
(`wrist.run --swings-out` writes the swings with it; `coach.wrist_sensor.attach_wrist` adds
it too). `measure_swing` reads it, and `rolled_wrist` fires when `forearm_roll_deg` is past
the threshold. Its fix is `firm_wrist`, which `physics/ghost.py` animates: its `wrist_roll`
edit lowers the forearm roll by the coach's amount (the roll above the stroke's good median).
So a sensor-backed `rolled_wrist` is `ghost_ready` and `firm_wrist` is the coach's `ghost_fix`,
with `ghost_fix_amount` set. `/ghost` offers `firm_wrist` only when the coach names it
(`COACH_ONLY_FIXES` in `app/ghost/compare.ts`, #85), not from the catalogue. Labels say `(wrist sensor)`, plus
`(MOCK sensor data)` when the data is synthetic. The field's contract is in
`docs/interfaces.md`. The coach still treats `sensorAssisted` joints as guessed (it reads
`filled`); trusting them is a coach change for later.

## Threshold, honestly

`python -m wrist.tune` puts the threshold halfway between the normal and rolled medians
(the fault library's rule for labelled data). It then reports:
- the margin between the two groups (negative means they overlap);
- in-sample accuracy (optimistic);
- **leave-one-out accuracy**: each swing judged by a threshold made from the others;
- Cohen's d (how far apart the groups are, in standard deviations).

It only says "set" with at least 5 swings in each group and leave-one-out of 80% or more.
With 5 vs 5 swings from one player, even a clean split is provisional.

The mock run gives normal 16.5 deg vs rolled 62.0 deg, threshold 39.2 deg, leave-one-out
100%. That only proves the code works, not that real swings split this cleanly. On the
first real session (below) even GOOD drives rolled 96-145 deg in the window, so this mock
threshold would flag every real swing: retune per stroke on real labelled swings.

## Shadow sessions (no ball)

`shadow.py` handles a session of blocks with no ball, e.g. good backhands, then backhands
with a rolled wrist. Tap the strapped phone two or more times before each block, in view of
a camera. With no impacts, each swing's contact is its fastest forearm turn (`"contact_source":
"gyro peak"`, an ESTIMATE), and the summary compares each faulty block with the good one of
the same stroke (mean, SD, Cohen's d, AUC, overlap). The module docstring has the details.

```
python -m wrist.shadow ../data/raw/wrist/<export>.zip --segments segments.csv --video-taps 140.333,279.550,377.400,503.967
```

`segments.csv` has one row per block: `segment,stroke,fault,video_start_s,video_end_s` (or
`start_s,end_s` in sensor seconds); a blank end runs to the next block. `--video-taps` takes
the playback second of the frame where the hand first touches the phone, one per tap event.
A tap is timed from its onset (the first sample of the knock), not its peak, which is often
the phone's rebound 10-20 ms later.

### First real session (14 Nov, one player, all ESTIMATE (sensor))

- **Video time base.** Both iPhone slow-motion exports ran at **4x** (each 30 fps frame is
  1/120 s of real time), not the 8x a 240 fps capture suggests. The taps fit scale 0.24998,
  so timestamps read off those files are playback time.
- **Sync.** Four tap events (5, 2, 2, 2 taps), matched to the frames where the hand lands
  on the phone. All 11 taps fit within 13 ms (front camera, rms 6 ms) and 4 ms (behind,
  rms 2 ms). A clock from correlating pose speed with the gyro was 255 ms off on the front
  camera, one tap interval, so sync on the taps.
- **Swings:** 15 good backhands, 10 good forehands, 14 rolled backhands, and 5 rolled
  forehands inside the marked block (11 to the end of the recording).
- **Separation.** Roll through contact (size, mean ± SD, range):

  | Stroke | Good | Rolled wrist | Difference |
  |---|---|---|---|
  | Backhand | 105.3 ± 9.3 deg (96-120) | 137.6 ± 6.3 deg (128-150) | +32.3 deg, d 4.0, AUC 1.00, no overlap |
  | Forehand | 134.2 ± 9.8 deg (120-145) | 159.8 ± 3.9 deg (154-165) | +25.6 deg, d 3.0, AUC 1.00, no overlap |

  With all 11 rolled forehands: +22.9 deg, d 2.9, AUC 1.00, no overlap.
- **Contact placement matters on forehands.** The swing-only turn rate peaks 10-20 ms
  before the total turn rate on backhands, and 50-80 ms before it on forehands. With
  contact at that earlier peak, backhands still separate (90.5 ± 7.7 vs 126.5 ± 6.9 deg)
  but forehands overlap (86.9 ± 4.6 vs 94.6 ± 7.1 deg). Real hits, timed from the impact,
  should settle it.
- **Racket speed, rotation part only** (no camera): backhand 9.0 ± 1.2 good vs 10.0 ± 1.0
  rolled; forehand 4.9 ± 0.8 vs 3.5 ± 0.4 m/s. One backhand fused with the camera: 8.9 m/s.
- **Occlusion fill on a real swing (one good backhand).** Stereo failed the pipeline's
  gates, so the swing is the behind camera's mono pose. That camera lost the right elbow
  and wrist on 57 of 97 frames. Alignment on the 40 seen frames: median 9.9 deg, holdout
  16.1 deg, strap axis 27 deg off nominal (near the 30 deg limit). On the 57 frames, the
  front camera saw the arm. Fitting phone to front camera on the 40 frames and testing on
  the 57, the phone's forearm direction is 18 deg off (median); the pipeline's straight-line
  fill is 44 deg off. **Limit:** when the elbow is hidden too, the phone can't place it, so
  the rebuilt forearm hangs from the pipeline's interpolated elbow. In the front image
  that elbow is about 1.5 forearm lengths off.
- **Coach threshold.** Don't copy these numbers into `coach/faults.py`: contact here is the
  gyro peak of a swing with no ball. Retune per stroke on labelled real hits.

## Known limits

- **Sensor ranges.** Phone gyros saturate around 2000 deg/s and accelerometers around 16 g.
  A fast forearm can hit both, and a clipped gyro under-reads roll rate.
- **Clock scale.** If contact times were read off slowed-down playback, pass `--video-scale`
  (real seconds per video second). Otherwise the alignment errors grow along the session.
- **Strap.** A strap that slips or rotates on the arm reads as forearm roll.
- **Threshold.** One threshold is used for forehand and backhand until real swings of each exist.
- **Lever and locked wrist.** Racket speed assumes the racket points along the forearm and
  the wrist doesn't snap. 0.55 m (0.45 m + a 0.10 m grip offset) is an estimate, shared with
  the video estimate. The camera's wrist speed carries the pipeline's assumed-torso scale.
- **Roll near a half-turn.** The forearm turns about 180 deg about another axis in the roll
  window (178.7 deg on the mock). There the twist of the window's rotation is
  ill-conditioned: on the mock, a 0.5 deg error in the rotation moved it 20-30 deg. The
  first real recording settled it: the twist scattered over +-180 deg (SD 86-156 deg per
  block) while the axial gyro integral's SD was 5-10 deg. So `roll_change_deg` is now the
  axial gyro integral on every path, and the twist is only reported as
  `roll_change_twist_deg`. The integral reads the forearm's whole turn about its own
  axis, so shoulder rotation with a straight elbow counts as roll too.
- **Integrated gyro.** Its offset is measured on the still stretch around the taps, so any
  arm sway there leaks in (on the mock, 2.3 deg/s on one axis). That moves roll over 250 ms
  by about 0.5 deg, and the per-swing camera fit absorbs most of the drift (fill within 2 cm).
- **Shadow swings and soft hits.** A swing timed from the double tap carries the sync error
  (the video tap and contact marks, up to 100 ms), so its window can sit tens of ms off. An
  impact under 2 g is treated as no impact: a genuinely soft hit would look like a shadow
  swing. The 2 g floor is from the mock (impacts ~10 g, swing bumps ~1 g): tune it on real hits.
- **Alignment.** The fit assumes the camera's axes stay fixed during the swing (true for
  hip-centred pipeline output). It also assumes the strap doesn't slip, and that the
  camera's forearm is right where the camera saw it. A median agreement above 12 deg skips
  the fill.
- **Impact isn't judged.** At 100 Hz the phone only sees the arm's echo of the racket's
  vibration, 10 ms at a time. Peak g and ring-down are reported; a clean/mishit rule needs
  labelled real hits first.
- **Mishit timing.** A ringing mishit's tallest spike can come a sample or two after the
  first knock. Its contact time, and so every window around it, can then sit about 20 ms
  late (19.5 ms in the mock).
