# Wrist sensor (owner: Henoch)

The camera can't see a **rolled wrist** (the forearm rotating through contact). A phone
strapped to the forearm can. This folder turns a Sensor Logger recording into per-swing
forearm-roll numbers that the coach's `rolled_wrist` fault reads. It also exports a small
roll-angle graph for the ghost page.

It also produces four **ESTIMATES**, each labelled `"label": "ESTIMATE"`:
- **Tempo:** backswing start, top of backswing, contact and follow-through end.
- **Impact quality:** clean or mishit.
- **Racket speed** (needs the camera): camera wrist velocity + gyro x lever. Physics can use it.
- **Occlusion fill** (needs the camera): the camera's hidden forearm rebuilt from the phone.
  Comes with the camera/phone agreement error.

Code measures, Claude explains: the coach only quotes these numbers. Swings without
usable sensor data skip `rolled_wrist` (it shows under `not_measured`). Nothing is guessed.

**Everything here so far is tested on MOCK data** (`synth.py`). The threshold in
`coach/faults.py` comes from mock swings and must be retuned on real ones.

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
python -m wrist.synth /tmp/wrist-mock --camera --mishit 3
```
Writes a mock export, `contacts.csv` and `labels.csv`, then prints the next command.
`--camera` also writes MOCK pipeline swing JSONs (`swings/`): an occluded wrist or elbow
near contact, and a video contact frame a frame or two off. `--mishit 3` makes the 4th
swing ring like an off-centre hit.

```
python -m wrist.run ../data/raw/wrist/<export>.zip --contacts ../data/labels/labels.csv --run <pipeline_run> --video-tap <seconds>
```
Writes `data/raw/wrist/wrist_metrics.json` and `wrist_series.json`, and prints the taps,
impacts, alignment errors and every swing's numbers and ESTIMATES. `--contacts` can also be
a folder of pipeline swing JSONs.

Add `--swings <folder of pipeline swing JSONs>` for racket speed and the occlusion fill. If
`--contacts` is already that folder, you don't need it. Swings whose forearm was rebuilt go
to `data/raw/wrist/filled_swings/` (`--filled-out`). `--lever` sets the wrist-to-racket-head
lever (default 0.65 m).

```
python -m wrist.tune ../data/raw/wrist/wrist_metrics.json ../data/labels/labels.csv --run <pipeline_run>
```
Picks the threshold from the normal and rolled swings and reports how well they separate.
Copy its rule into `THRESHOLDS` in `coach/faults.py` by hand.

```
python -m coach.agent <swing>.json --wrist ../data/raw/wrist/wrist_metrics.json
```
Coaches one swing with its wrist data.

Windows: same commands, `python` inside the activated venv.

## What it measures (per swing, -150 ms to +100 ms around contact)

| Key in `wrist_metrics.json` | Coach measurement | Meaning |
|---|---|---|
| `roll_change_deg` / `roll_change_abs_deg` | `forearm_roll_deg` (the size) | Forearm roll over the window, from the orientation quaternions: the twist about the forearm axis, so the swing itself doesn't count |
| `roll_change_gyro_deg` | (cross-check) | The same roll, from integrating the gyro. It should agree with the quaternion number. |
| `peak_roll_rate_dps` / `_abs_dps` | `forearm_roll_rate_dps` | Fastest gyro rate about the forearm axis |
| `peak_angular_speed_dps` | `forearm_speed_dps` | Fastest total turn rate of the forearm (context only) |

Contact = the sensor's own impact spike, so sync error doesn't move these numbers.
Sync only decides which swing each impact belongs to.

Built-in checks, all reported in the output:
- **Quaternion direction.** Sensor Logger doesn't document it, so the code picks the one
  that matches the gyro. If neither matches, every swing is marked unusable.
- **Forearm axis.** Default is `y` (long edge along the forearm). If another axis carries
  more acceleration through contact, there's a warning: rerun with `--axis x` or `--axis z`.
- **Sync.** Two taps, then impacts. A spike only counts as an impact when the forearm is
  turning fast (more than 360 deg/s); footsteps and knocks are listed as rejected. The
  first tap gives the video-to-sensor offset. Contacts pair with impacts in order, and each
  pair reports its **alignment error in ms**. Pairs off by more than 100 ms are skipped.
  Without `--video-tap` the offset is fitted to the impacts, and the report says this
  is a weaker check.

## The ESTIMATES (tempo, impact, racket speed, occlusion fill)

All of these are tested on MOCK data only so far. Until real swings check them, quote
them as ESTIMATES.

**Tempo** (`tempo.py`, per swing `tempo`). This reads the forearm's total turn rate |gyro|,
smoothed over 30 ms. "Rest" = 50 deg/s or 5% of the swing's peak, whichever is higher.
- `backswing_start_ms`: the speed rises past rest before contact.
- `forward_start_ms`: the top of the backswing. Either the end of a pause at the top, or
  the dip where a looped swing turns forward.
- `follow_through_end_ms`: the speed is back under rest after contact.

All times are ms from contact (the sensor's impact spike). Also given: `backswing_ms`,
`forward_swing_ms`, `follow_through_ms`, and `tempo_ratio` (backswing / forward swing).
An event it can't find is `null`, with a reason: the arm never settled, or the gyro shows no
turn-around because the backswing was all shoulders.

**Impact quality** (`impact.py`, per swing `impact`).
- `peak_g`: the spike's height after the high-pass that sync uses.
- `width_ms`: how long it stays above half that height.
- `clipped`: true when the accelerometer hit its limit.

A clean hit is one sharp knock. An off-centre hit keeps the racket and arm shaking, so its
spike lasts longer. Each impact is judged against **the session's other impacts** (robust
z-scores), because nobody has labelled real mishits yet. It's a mishit when its height is
3 robust SDs from your usual (either way) or its width is 3 SDs longer. `score` goes from
100 (your usual) through 50 (on the line) to 0. Mock run: the ringing swing measured 69 ms
wide against the usual 12 ms, so it was flagged. The nine clean swings scored 78 to 99.

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

**Occlusion fill** (per swing `occlusion_fill`, and the swing JSONs in `filled_swings/`).
Frames where the hitting wrist or elbow is marked `filled` get their forearm direction from
the phone:
- **Wrist filled:** wrist = elbow + forearm length x phone direction. The hand points move
  with the wrist, so the hand bones keep their lengths. Their orientation stays the
  pipeline's own.
- **Elbow filled, wrist seen:** the elbow goes on the circle that keeps both arm bones'
  lengths, nearest the phone's direction.

`filled` flags stay true, because the camera still didn't see those joints.
`metadata.wristSensorFill` lists the frames. Mock run: rebuilt joints are within 1 cm of
the truth, against 1.5–15 cm for the pipeline's straight-line interpolation. Agreement and
holdout are both about 0.1 deg (the mock camera has no noise; real ones will be worse).

**Racket speed** (per swing `racket_speed_sensor`). This treats the forearm, hand and racket
as one rigid lever: locked wrist, racket along the forearm, 0.65 m from the wrist joint to
the head.
`v_head = v_wrist (camera) + w_forearm (gyro) x lever`.
- With a trusted alignment, the two parts are added as vectors.
- Otherwise they're added as if parallel, which is an upper bound; `method` says which.
- With no camera, `value` is null and `rotationMs` gives the gyro part alone.

The gyro is averaged over the 20 ms up to the impact. The camera wrist is the sensor-filled
one when the occlusion covers contact (`wristFromSensorFill`). Mock run: within 4% of the
truth.

### The physics hook (aryan)

`wrist.fuse.attach_racket_speed(swing, wrist_metrics)` returns a copy of the swing with
the optional field `swing["racketSpeedSensor"]`. It has the same shape as
`physics.compare.estimate_racket_speed()`: `value`, `unit`, `estimate`, `label`, `method`,
`clamped`, `rawValue`, plus sensor details. It's clamped to the same 1–80 m/s range. Physics
isn't edited here. A suggested hook in `compare()` / `_side()`:
use `racketSpeedSensor` for **your** side when `value` isn't null. For the **ghost**, scale it by
ghost pose estimate / your pose estimate, so the fix's effect is kept. The ghost swing is a
copy, so it carries the field too, and it mustn't reuse the measured value as is. The new
optional field needs the team's OK before it goes into `docs/interfaces.md`.

## Outputs

`wrist_metrics.json` (one entry per swing, keyed by swing id):

```json
{"mock": false, "sensor": {...}, "sync": {...}, "warnings": [],
 "estimates": {"label": "ESTIMATE", "lever_m": 0.65, "camera_swings": 10, "note": "..."},
 "swings": {"<swing id>": {"usable": true, "skip_reason": null, "mock": false,
   "align_error_ms": 7.0, "impact_s": 41.406, "roll_change_deg": 58.5,
   "roll_change_abs_deg": 58.5, "roll_change_gyro_deg": 58.6,
   "peak_roll_rate_dps": 460, "peak_roll_rate_abs_dps": 460,
   "peak_angular_speed_dps": 1321, "window_ms": [-150, 100],
   "tempo": {"label": "ESTIMATE", "backswing_start_ms": -719, "forward_start_ms": -163,
             "contact_ms": 0, "follow_through_end_ms": 174, "backswing_ms": 556,
             "forward_swing_ms": 163, "follow_through_ms": 174, "tempo_ratio": 3.41, ...},
   "impact": {"label": "ESTIMATE", "peak_g": 9.31, "width_ms": 12.2, "clipped": false,
              "quality": "clean", "score": 99, "z_peak": 0.0, "z_width": 0.0, "reasons": [], ...},
   "racket_speed_sensor": {"value": 18.9, "unit": "m/s", "estimate": true, "label": "ESTIMATE",
                           "method": "camera wrist velocity + gyro x lever, added as vectors",
                           "gyroDps": 1139, "leverM": 0.65, "rotationMs": 12.9, "wristSpeedMs": 6.09, ...},
   "occlusion_fill": {"label": "ESTIMATE", "applied": true, "frames": [109, ...], "joints": ["wrist", "hand"],
                      "agreement_deg": {"median": 0.1, "p90": 0.1, "max": 0.4, "n": 179},
                      "holdout_deg": {"median": 0.1, ...}, "time_shift_ms": 23.0,
                      "strap_axis_offset_deg": 5.2, "forearm_m": 0.26, "moved_m": {...}, ...}}}}
```

`wrist_series.json`, **for Sammy's "wrist rotation" graph** (about 22 KB for 10 swings
with camera swings). Mock example, with every field and one mishit (`synth-04`):
[examples/wrist_series.mock.json](examples/wrist_series.mock.json).

```json
{"mock": true, "window_ms": [-150, 100], "forearm_axis": "y",
 "angular_speed_t_ms": [-1500, -1480, ..., 1000],
 "swings": {"<swing id>": {"t_ms": [-300, -290, ..., 200], "roll_deg": [...],
                           "roll_change_deg": 58.5, "usable": true,
                           "angular_speed_dps": [3, 4, ..., null],
                           "tempo": {"label": "ESTIMATE", "backswing_start_ms": -719,
                                     "forward_start_ms": -163, "contact_ms": 0, "follow_through_end_ms": 174},
                           "impact": {"label": "ESTIMATE", "peak_g": 9.31, "width_ms": 12.2,
                                      "quality": "clean", "score": 99},
                           "racket_speed_sensor": {"value": 18.9, "unit": "m/s", "label": "ESTIMATE"},
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
- **Labels:** anything carrying `"label": "ESTIMATE"` should show ESTIMATE on screen.

## How the coach uses it

Each swing can carry its own entry as an optional field: `swing["wrist"]`
(`coach.wrist_sensor.attach_wrist` adds it). `measure_swing` reads it, and `rolled_wrist`
fires when `forearm_roll_deg` is past the threshold. Its fix is `firm_wrist`, which the
ghost can't animate yet, so it's never `ghost_ready`; the ghost shows the next fix instead.
Labels say `(wrist sensor)`, plus `(MOCK sensor data)` when the data is synthetic.

The optional `swing["wrist"]` field is new. It needs the team's OK before it goes into
`docs/interfaces.md`.

## Threshold, honestly

`python -m wrist.tune` puts the threshold halfway between the normal and rolled medians
(the fault library's rule for labelled data). It then reports:
- the margin between the two groups (negative means they overlap);
- in-sample accuracy (optimistic);
- **leave-one-out accuracy**: each swing judged by a threshold made from the others;
- Cohen's d (how far apart the groups are, in standard deviations).

It only says "set" with at least 5 swings in each group and leave-one-out of 80% or more.
With 5 vs 5 swings from one player, even a clean split is provisional.

The mock run gives normal 16.5 deg vs rolled 62.1 deg, threshold 39.3 deg, leave-one-out
100%. That only proves the code works, not that real swings split this cleanly.

## Known limits

- **Sensor ranges.** Phone gyros saturate around 2000 deg/s and accelerometers around 16 g.
  A fast forearm can hit both, and a clipped gyro under-reads roll rate.
- **Clock scale.** If contact times were read off slowed-down playback, pass `--video-scale`
  (real seconds per video second). Otherwise the alignment errors grow along the session.
- **Strap.** A strap that slips or rotates on the arm reads as forearm roll.
- **Threshold.** One threshold is used for forehand and backhand until real swings of each exist.
- **Lever and locked wrist.** Racket speed assumes the racket points along the forearm and
  the wrist doesn't snap. 0.65 m is a guess (physics uses 0.55 m to the sweet spot). The
  camera's wrist speed carries the pipeline's assumed-torso scale.
- **Alignment.** The fit assumes the camera's axes stay fixed during the swing (true for
  hip-centred pipeline output). It also assumes the strap doesn't slip, and that the
  camera's forearm is right where the camera saw it. A median agreement above 12 deg skips
  the fill.
- **Impact quality is relative.** It compares you with yourself in the same session, and
  needs 4 other impacts to compare with. At 100 Hz the phone only sees the arm's echo of
  the racket's vibration.
- **Mishit timing.** A ringing mishit's tallest spike can come a sample or two after the
  first knock. Its contact time, and so every window around it, can then sit about 20 ms
  late (19.5 ms in the mock).
