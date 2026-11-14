# Elevation check: 08:00, before the 09:00 freeze

**What we check:** the ball's launch angle is ASSUMED: **12° for a forehand, 3° for a backhand** (`services/physics/compare.py`). Each value was fitted to a single clip (IMG_2115 and IMG_2116), so this is the first test on new hits. One degree moves the predicted front-wall hit by about 0.125 m.

**Before you start:** check with Dev that PR #49 is merged, so live backhands get the backhand angle. Do a one-minute dry run of the `click` command below on any slow-motion clip.

## 1. Set up (07:50)
- [ ] **Camera A:** the demo phone behind the player, set up as for the live demo.
- [ ] **Camera B (side view):**
  - a second phone, in Slo-mo 240 fps, landscape;
  - on a stand about 1 m high;
  - set to Settings > Camera > Formats > **Most Compatible**, so the script can read the files.
- [ ] Place camera B against the side wall **opposite** the hitting side: the left wall for forehands, the right wall for backhands.
  - Stand it level with where the player hits the ball, about 7 m from the front wall.
  - Point it straight across the court.
- [ ] Turn the camera grid on. The floor line should look level, and the contact spot should sit near the middle of the frame.

## 2. Film (08:00)
- [ ] Clap once in view of both cameras, to sync them.
- [ ] Film **one clip per hit** on camera B: stop and start between hits. Say "forehand 1", "forehand 2", and so on, before each hit.
- [ ] Hit 6 straight forehand drives at demo pace.
- [ ] Move camera B to the other wall, then hit 6 straight backhand drives.
- [ ] Check one clip straight away: the ball must be visible for at least 4 frames after contact.
- [ ] AirDrop camera B's clips into `data/raw/elevation/`. That folder is git-ignored, so the clips never get committed.

## 3. Measure (08:15, about 2 minutes per hit)
From `services/` with the venv active (the same command on Mac and Windows), run this for each clip:

```
python -m physics.measure_launch click ../data/raw/elevation/fh1.mov --stroke forehand --hit 1 --csv ../data/raw/elevation/hits.csv
```

1. The viewer opens in the middle of the clip. Step with `a`/`d` (one frame) or `A`/`D` (ten frames) until you reach the hit.
2. Click the ball centre on the **first frame where it has clearly left the strings**.
3. The viewer jumps 4 frames ahead, about 0.6 m of flight. Click the ball again. (Add `--gap 2` if the clip is 120 fps.)
4. It prints the launch angle and adds a row to `hits.csv`.
- **Phone wasn't level?** Add `--level`, then first click two points on a horizontal court line, such as where the floor meets the far wall.
- **Mishit?** Skip that clip.
- **Viewer won't open?** Read the two ball positions in Preview instead, then run `python -m physics.measure_launch angle X1 Y1 X2 Y2` with the same `--stroke`, `--hit` and `--csv` options.

## 4. Check the outcome (camera A, at the same time)
- [ ] For each hit, note where the ball hit the front wall. Use the tin top (0.48 m) and the service line (1.78 m) as references, and enter it in the `actual_wall_m` column of `hits.csv`.
- [ ] Run the same hit through the live pipeline, as in the demo. Enter the predicted front-wall height in `predicted_wall_m`.

## 5. Decide (08:40)

```
python -m physics.measure_launch summary ../data/raw/elevation/hits.csv
```

For each stroke it prints the median, the spread and one decision:
- **Rule 11, keep:** the median is within 2° of the default. 2° is about 0.25 m on the front wall, roughly twice the measuring error of one hit.
- **Rule 12, change:** the median is off by 2° or more. Set that default to the median, rounded to a whole degree. The summary prints the new line to paste.
- **Rule 13, keep the angle:** the angle is within 2°, but the predicted wall height is off by more than 0.25 m. The error is in speed or launch height, not elevation, so log it for after the freeze.
- **Rule 14, keep:** some hit is more than 5° from the median, so one value can't represent these shots. The ASSUMED label stays.
- **Fewer than 3 usable hits for a stroke:** keep the default.

## 6. Only if a default changes (08:45, 10 minutes at most)
- [ ] Paste the printed line into `services/physics/compare.py`. Update the comment above it with the 08:00 numbers: the number of hits, the median and the spread.
- [ ] Update the tests that pin 12° or 3°, in `physics/tests/test_court.py` and `physics/tests/test_compare.py`. If the IMG_2115 or IMG_2116 wall checks then fall out of range, pass those clips their own angle (`elevation_deg=12` or `3`).
- [ ] Run `python -m pytest` from `services/`, make a new branch from `main`, and open a PR. Dev merges it before 09:00.
- [ ] **Not merged by 08:55? Ship as is.** The elevation is already labelled ASSUMED on screen.
