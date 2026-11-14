# Wrist sensor (owner: Henoch)

The camera can't see a **rolled wrist** (the forearm rotating through contact). A phone
strapped to the forearm can. This folder turns a Sensor Logger recording into per-swing
forearm-roll numbers that the coach's `rolled_wrist` fault reads. It also exports a small
roll-angle graph for the ghost page.

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
python -m wrist.synth /tmp/wrist-mock
```
Writes a mock export, `contacts.csv` and `labels.csv`, then prints the next command.

```
python -m wrist.run ../data/raw/wrist/<export>.zip --contacts ../data/labels/labels.csv --run <pipeline_run> --video-tap <seconds>
```
Writes `data/raw/wrist/wrist_metrics.json` and `wrist_series.json`, and prints the taps,
impacts, alignment errors and every swing's numbers. `--contacts` can also be a folder of
pipeline swing JSONs.

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

## Outputs

`wrist_metrics.json` (one entry per swing, keyed by swing id):

```json
{"mock": false, "sensor": {...}, "sync": {...}, "warnings": [],
 "swings": {"<swing id>": {"usable": true, "skip_reason": null, "mock": false,
   "align_error_ms": 7.0, "impact_s": 41.406, "roll_change_deg": 58.5,
   "roll_change_abs_deg": 58.5, "roll_change_gyro_deg": 58.6,
   "peak_roll_rate_dps": 460, "peak_roll_rate_abs_dps": 460,
   "peak_angular_speed_dps": 1321, "window_ms": [-150, 100]}}}
```

`wrist_series.json`, **for Sammy's "wrist rotation" graph** (about 5 KB for 10 swings).
Mock example: [examples/wrist_series.mock.json](examples/wrist_series.mock.json).

```json
{"mock": true, "window_ms": [-150, 100], "forearm_axis": "y",
 "swings": {"<swing id>": {"t_ms": [-300, -290, ..., 200], "roll_deg": [...],
                           "roll_change_deg": 58.5, "usable": true}}}
```

`t_ms` is ms from contact, one point every 10 ms. `roll_deg` is 0 at -150 ms, so at
+100 ms it equals `roll_change_deg`, the number the coach quotes. Suggested drawing:
shade the window, and use orange `#FF8A3D` for the player's line. If `mock` is true,
show a MOCK label.

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
