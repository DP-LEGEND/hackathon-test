# Interfaces between pieces

Agree these on Saturday at 11:00, before anyone builds. Each piece reads and writes exactly these formats.

## core → agent
_(example shape, replace on Saturday)_
```json
{ "metrics": {}, "flags": [] }
```

## agent → frontend
```json
{ "summary": "", "actions": [] }
```


## Pipeline swing reconstruction provenance

The existing Swing fields remain required: `id`, positive `fps`, zero-based
`contactFrame`, and at least two `frames`. Each frame has `t` in real seconds
from the swing start and `joints`: 33 finite `[x, y, z]` positions in MediaPipe
order, metres, hip-centred, y up. Pipeline output may also include the existing
`fpsReal`, `source`, `side`, and `metadata` fields.

Each frame now supports this **optional, additive** field:

```ts
filled?: boolean[]; // exactly 33 entries, parallel to joints
```

`frames[i].filled[j]` is true when the selected reconstruction for joint j at
frame i contains a temporal interpolation, a repaired missing coordinate, or a
copy from a parent joint. A partially missing xyz coordinate marks the whole
joint. In stereo output, sampling camera B between its recorded frames also
marks the reconstructed joint true, even when camera A observed that instant.
Monocular fallback uses camera A's provenance, not the rejected stereo mask.

False means the selected source joint passed observation/quality gates before
repair at that sample. Ordinary smoothing of an observed joint, bone-length
constraints, coordinate rotation, scaling and hip-centring do not by themselves
mark it filled. This is reconstruction provenance, not a confidence score or a
claim of calibrated 3D accuracy. It does not track edits applied by the ghost.

New pipeline outputs include the flags. Old files may omit `filled` on any frame;
absence means provenance is **unknown**, not that every joint was observed.
Readers must tolerate its absence. The standard-library `scripts/check_swing.py`
accepts both versions and validates 33 actual booleans when the field is present.
Joint coordinates remain finite and the contact-frame convention is unchanged.

## Optional wrist-sensor entry on a swing

A swing may carry an **optional, additive** top-level `wrist` object: that swing's
entry from the `wrist_metrics.json` that `python -m wrist.run` writes from a phone
strapped to the forearm (`services/wrist`). Entries are keyed by swing `id`;
`coach.wrist_sensor.attach_wrist` copies one in, and gives a swing missing from the
file `{"usable": false, "skip_reason": "..."}` so the skip stays visible. Today only
`python -m coach.agent <swing.json> --wrist <wrist_metrics.json>` adds it: the pipeline
doesn't write it and the web app doesn't read it.

The coach reads only these fields:

```ts
wrist?: {
  usable: boolean;                 // false: unpaired, alignment off, or orientation fails the gyro check
  skip_reason: string | null;      // why it's unusable; null when usable
  mock?: boolean;                  // true for synthetic recordings (wrist/synth.py); absent = false
  roll_change_abs_deg?: number;    // size of the forearm roll, -150..+100 ms around contact
  peak_roll_rate_abs_dps?: number; // fastest roll rate about the forearm axis in that window
  peak_angular_speed_dps?: number; // fastest total forearm turn rate in that window
};
```

`wrist.run` writes more per-swing fields (signed roll, `impact_s`, `align_error_ms`,
`tempo`, `impact`, `racket_speed_sensor`, `occlusion_fill`; see `services/wrist/README.md`).
Readers must ignore fields they don't use.

The coach uses the entry only when `usable` is true and all three numbers are finite.
Otherwise, including when `wrist` is absent, every sensor measurement is null and
`rolled_wrist` is skipped and listed in `not_measured`, never guessed. Absence means no
sensor, not "no roll". Every coach result's `metrics` carries these keys, with or without
a sensor:

| Key | Value |
|---|---|
| `forearm_roll_deg` | from `roll_change_abs_deg`, deg, or null |
| `forearm_roll_rate_dps` | from `peak_roll_rate_abs_dps`, deg/s, or null |
| `forearm_speed_dps` | from `peak_angular_speed_dps`, deg/s, or null |
| `wrist_sensor` | `"sensor"`, `"mock sensor"`, or null when unused |
| `wrist_sensor_skipped` | why the sensor wasn't used, or null when it was |

When `mock` is true, sensor fault labels end in "(MOCK sensor data)", and screens must
show the data as mock. The `rolled_wrist` thresholds come from mock swings (source
"mock wrist-sensor swings") until `python -m wrist.tune` is rerun on real ones. Its fix,
`firm_wrist`, isn't animated, so it is never `ghost_ready`.

## Swing label join

The API joins labels on the pair `(pipeline_run, swing_id)`, using the processed
run folder's name and the swing file's stem. CSV rows use `pipeline_run`, `swing`,
and `intended_fault`. A legacy `swing_id@run_id` value can supply the run when the
column is absent; if both exist they must agree. Labels without a run are ignored;
there is no swing-ID-only fallback. Duplicate pairs or conflicting runs return
503, while the same swing ID in different runs is valid.

`none` maps to `good`; other exposed labels are `early_wrist`, `over_rotation`,
`straight_arm`, `open_stance`, and `rolled_wrist`. Missing/unknown labels are null.
These are intended filming labels, not measured fault diagnoses.
