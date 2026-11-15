<!--
TODO (before judging): timed at 150 words a minute (2.5 words a second), each block rounded up,
plus the click/loading gaps written next to each beat. Total 2:59 with the longer wrist
version (2:51 spoken), so only 1 s to spare; rehearse with a stopwatch and cut, don't speed up. Voice and Claude in the live caption
are on main ("Hear the coach"), so judge questions 3 and 4 claim them. Not on main, so not
claimed: an Adaption fine-tune. If that changes, update the script and docs/devpost.md together.
WRIST BEAT: the only wrist results on main are mock (the mock run gives 62.1° vs 16.5° medians).
About 50 real shadow swings without a ball were recorded on 14 Nov and are tuned in PR #74 (not
merged), so no number from them is said on stage. Say numbers only from the morning sample's
`wrist.tune` output on screen, as printed. Without that sample, use the spoken version (no number).
-->

# Ghost: 3-minute pitch

**Rehearsal note:** If over 3:00, cut the forehand video-check sentence first.

**PRESENTER** speaks. **OPERATOR** clicks. Every click is below. The full set-up, checks and fallbacks are in [docs/demo-runbook.md](demo-runbook.md). Rehearse with a stopwatch.

| Section | Time | Length | Time if the wrist beat is spoken |
|---|---|---|---|
| Hook | 0:00–0:16 | 16 s | same |
| Problem | 0:16–0:34 | 18 s | same |
| Live demo: forehand | 0:34–1:16 | 42 s | same |
| Live demo: backhand | 1:16–1:34 | 18 s | same |
| Live demo: wrist sensor | 1:34–1:59 | 25 s | 1:34–1:51 (17 s) |
| Live demo: fresh clip | 1:59–2:21 | 22 s | 1:51–2:13 |
| How it works | 2:21–2:40 | 19 s | 2:13–2:32 |
| Honesty | 2:40–2:48 | 8 s | 2:32–2:40 |
| What's next | 2:48–2:59 | 11 s | 2:40–2:51 |
| **Total** | | **2:59** (under 3:00) | **2:51** |

Seconds are speaking time at 150 words a minute plus the click and loading gaps noted in each beat. **If the wrist beat is spoken, don't wait:** go straight on, and every later beat starts 8 s earlier (the last column, and the second time in each heading below).

**Rules**
- Only say a measurement that's on screen. There are two named exceptions, as in the runbook:
  - the **launch angle**, which you always call *assumed*
  - the **video-check height** (about 1.8 m on the forehand), which you always say was *checked by eye against the video*
- Say **predicted** the first time a ball path appears.
- **Wrist sensor:** say its numbers only when the morning sample's output is on screen, and call them a sensor **ESTIMATE**. Without the sample, say it's been tried on real practice swings without a ball, and say no number.

**Before you start** (the runbook has the full checks):
- **Terminal tab 1:** `cd ~/hackathon-demo/services`, then `mkdir -p ~/ghost-stage` (it must be empty), then `GHOST_SWINGS_DIR=~/ghost-stage ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000`
- **Terminal tab 2:** `cd ~/hackathon-demo`, then `npm run dev`
- **Terminal tab 3 (only if the morning sensor sample is ready):** already printed, as in the runbook's *Tab 3*:
  ```
  cd ~/hackathon-demo/services
  ```
  Edit the path to the morning `wrist_metrics.json` and the run name in the next two lines before you press Enter on each:
  ```
  WRIST_JSON=~/path/to/morning/wrist_metrics.json
  ```
  ```
  RUN=your_run_name
  ```
  ```
  clear
  ```
  ```
  ~/ghost-env/bin/python -m wrist.tune "$WRIST_JSON" ../data/labels/labels.csv --run "$RUN"
  ```
  Show this tab only if **all four** hold; otherwise use the spoken wrist beat:
  1. The first line does **not** say *MOCK DATA*, and it shows **at least 5 normal and 5 rolled** usable swings (wrist.tune's own minimum).
  2. There's a `roll_change_abs_deg (deg)` block with a `normal median …` line, a `rolled median …` line and an `in-sample: …` line. If it says *"roll_change_abs_deg: not measured in both groups"*, there are no medians to read.
  3. The rolled median is larger than the normal median.
  4. wrist.tune reports **no skipped swings**: the first line ends *"0 labelled swings skipped."*, with no `skipped …` lines under it.
- **Browser tab 1:** http://localhost:3000/ghost, full screen on **Pick a swing**
- **Browser tab 2:** http://localhost:3000/upload. **Choose a video**, pick `~/Downloads/fresh.mov` (one swing, 60 fps), and leave **Hitting hand**, **Stroke** and **Slowdown** on **Auto**. Don't click **Build my ghost** yet.

The replay in `/ghost` plays by itself. Don't click **Play/Pause**: it would pause it.

## Hook (0:00–0:16, 16 s)

**OPERATOR, at 0:00:** in browser tab 2, click **Build my ghost**, then switch to browser tab 1. **Keep tab 2 open:** leaving `/upload` cancels the upload. When the ghost is ready, tab 2 opens the new swing at the coach's call by itself.

> Every coach can tell you what you did wrong.
> None of them can show you the swing you haven't played yet.
> That's Ghost.
> Film one squash swing. See a ghost of yourself making the one fix that matters.

## Problem (0:16–0:34, 18 s)

> Squash is fast: the swing is over before you feel what went wrong.
> A coach says "turn your shoulders less", and you can't picture it.
> Video shows what you did, not the better swing on your body, or where that ball would have gone.

## Live demo (0:34–2:21, 107 s; 0:34–2:13, 99 s, if the wrist beat is spoken)

Same clicks as the runbook's beats 1–4, faster. The wrist sensor (runbook beat 4) now comes straight after the backhand. Don't fill the clicks and loading with talk.

### Forehand (0:34–1:16, 42 s)

| OPERATOR clicks | On screen | PRESENTER says | s |
|---|---|---|---|
| The top card, **Forehand · over-rotation** | The coach's call: *"Over-rotation: hips turn 157°"* | A real forehand, filmed in slow motion and rebuilt in 3D. Our code measured it: the hips turn 157 degrees. Too much. That's the one fix. | 13 (incl. 2 s click) |
| **Show the ghost**, then **0.25× slow-mo** (it's already playing) | Orange swing, cyan ghost. *Turn shoulders less*, *Coach's pick* | Orange is the swing they played. Cyan is their ghost: same body, same swing, shoulders turning less. | 9 (incl. 2 s click) |
| **Show the court** | Two paths, each *PREDICTED*. Front wall height 1.92 → 1.88 m | Where each ball goes: predicted, not tracked. Theirs hits the front wall at 1.92 metres, with an assumed 12-degree launch angle. Checked by eye against the video: about 1.8, a rough check. The ghost's hits at 1.88. | 20 (incl. 2 s click) |

### Backhand (1:16–1:34, 18 s)

| OPERATOR clicks | On screen | PRESENTER says | s |
|---|---|---|---|
| **Try another swing**, then **Backhand · two-camera stereo** | The coach's call: *"No fault found in what was checked"*, cue *"Nothing to fix in what the coach could check."* | A backhand, on two cameras at once. Nothing to fix in what the coach could check, and it says what it couldn't: the wrist, with no sensor, and the right elbow, which the camera couldn't see. | 18 (incl. 3 s clicks) |
| **Pick a swing** (the step bar at the top) | The swing list | | |

### Wrist sensor (1:34–1:59, 25 s; 1:34–1:51, 17 s, if spoken)

Mark it **ESTIMATE (sensor)**. The coach's call above already lists the wrist as not checked, so this beat follows straight on.

**Only if terminal tab 3 passes all four checks** in *Before you start* (not *MOCK DATA* with at least 5 normal and 5 rolled usable swings; both `roll_change_abs_deg` medians and the in-sample line printed; rolled median larger; no skipped swings), shown:

| OPERATOR clicks | On screen | PRESENTER says | s |
|---|---|---|---|
| Switch to terminal tab 3 | The morning `wrist.tune` output: `roll_change_abs_deg`, rolled vs normal medians, the in-sample split | The camera can't see wrist roll, which is why the coach couldn't check it. So we strapped a phone to the forearm. It's an estimate from one session: normal backhands turned [normal median]° through contact, rolled ones [rolled median]°, and every usable swing was sorted correctly. *(Read both medians exactly as tab 3 prints them under roll_change_abs_deg. Say 'estimate'. Don't subtract them out loud. Only say 'every usable swing sorted correctly' if the in-sample line shows 100% of rolled and 0% of normal.)* | 25 (incl. 2 s switch) |

**Otherwise, spoken only (17 s, 1:34–1:51).** Switch nothing, and don't say a number: without usable sample output there's no real measurement to quote. Then go straight on to the fresh clip at 1:51; every later beat uses its second, earlier time.

> The camera can't see wrist roll, which is why the coach couldn't check it. So we strapped a phone to the forearm. We've tried it on real practice swings without a ball, but the numbers aren't solid enough to quote yet.

### Fresh clip (1:59–2:21, 22 s; 1:51–2:13 if the wrist beat was spoken)

| OPERATOR clicks | On screen | PRESENTER says | s |
|---|---|---|---|
| Switch to browser tab 2 *(if it says "Your ghost is ready." but hasn't moved on, click **Open it in Ghost**)* | The new swing at the coach's call: *"Reading the coach's call…"*, then the call, or *"No fault found"* or *"No fault found in what was checked"* (see below) | This one we filmed today, on one phone. Slow motion, hand and stroke are detected automatically, and the coach measures it live. *(Read the caption exactly as shown.)* | 15 (incl. 6 s to read the caption) |
| If the coach named a fault: **Show the ghost** | *"Making the … ghost…"*, then the ghost and its fix | *(Say nothing yet; look at the badge.)* | |
| If the fix shows the badge *Coach's pick*: **Show the court** | Both *PREDICTED* paths | And there's their ghost, computed just now. | 7 (incl. 4 s loading) |

**If the caption says "No fault found" or "No fault found in what was checked":** read it as shown. Then do one of these:
- Stop the beat there and go to *How it works*.
- Or click **Show the ghost** and say: "This is an example edit at demo size, not a coached fix." The panel says *"Demo size: the coach didn't flag this fault."* Never call it the fix.

**If the coach named a fault but the panel says *"Demo size: the coach didn't flag this fault"*:** say "This is an example edit at demo size, not the coached fix." Never call it the fix, or stop and go to *How it works*.

**If tab 2 still shows the progress panel** (*Finding your swing… / Measuring… / Building your ghost…*) when this beat starts (1:59, or 1:51 if the wrist beat was spoken), skip this beat and say: "That clip is still processing, so here's how it works." Then go to *How it works*.

## How it works (2:21–2:40, 19 s; 2:13–2:32 if the wrist beat was spoken)

> MediaPipe finds 33 joints in every frame.
> Two cameras, synced on the sound of the hit, give a 3D skeleton, with no calibration board.
> The coach is plain code: four of its twelve rules are tuned on our labelled swings, the rest are defaults for now.

## Honesty (2:40–2:48, 8 s; 2:32–2:40 if the wrist beat was spoken)

> Joints and angles are measured.
> Racket speed is estimated.
> The launch angle is assumed.
> Every ball path is predicted.

## What's next (2:48–2:59, 11 s; 2:40–2:51 if the wrist beat was spoken)

> Next: track the racket, so speed and angle are measured.
> Then a watch app instead of the phone.
> Ghost: see the shot before you practise it.

## Likely judge questions

Two sentences each. Say less rather than more, and never a number that isn't in these answers or on screen.

**1. How accurate is it?**
On the two swings we checked against video, the predicted front-wall height landed within about 0.1 to 0.3 metres, but the launch angle is assumed and we set it from those same clips, so that's a sanity check, not validation. The coach's four tuned rules come from a small set of labelled swings, so expect misses on new players until we label more.

**2. What's measured and what's guessed?**
Joints, angles, wrist timing and stance come from the pose; with one camera the depth is estimated, and the screen says so. Racket speed is estimated, shot direction is estimated when the wrist motion is clear and otherwise assumed straight, the launch angle is assumed, every ball path is predicted, and the screen labels each one. When a joint the camera couldn't see would decide a fault, the coach skips that fault and lists it as not checked instead of guessing, like the right elbow on the backhand.

**3. Why Claude?**
Measuring and picking the fix are plain code, so the coach gives the same answer every time and works offline. Claude does the one thing code does badly, turning that fix into a natural spoken sentence for the **Hear the coach** button, and it only sees the coach's fault, cue and tip, never the raw metrics.

**4. What stops Claude saying something wrong?**
Every sentence goes through a code checker: a number must be one we measured, quoted once inside its measured phrase word for word, and a sentence with the opposite direction word or a negation like "don't" is rejected. If anything fails, Claude's sentence is never spoken and the coach's own cue is used instead, and the wrist cues the checker can't test are always spoken word for word.

**5. Is the wrist sensor real?**
The code is merged: it reads a phone strapped to the forearm through Sensor Logger, measures forearm roll and estimates racket speed, and before this morning it had been tested on mock data and on real practice swings without a ball. If the morning recording was on screen, its numbers come from one session and a handful of swings, so the threshold is provisional; if it wasn't, we claim no wrist number at all.

**6. What's next?**
First, track the racket so speed and launch angle are measured instead of estimated and assumed, and label more players to tune the other eight rules. Then player profiles: keep each player's swings over time, so the ghost compares you with your own best swing and shows whether the fix is sticking.

**7. What does it cost to run?**
Pose, coaching, the ghost and the ball physics run locally at no cost per swing; the only paid calls are one Claude sentence and one ElevenLabs clip per swing, and a successful result is cached, so replaying a swing costs nothing (a failed call can be retried). By our estimate that's around a cent of Claude at Opus 5.5 prices plus about 100 characters of speech per swing, and with no keys it still works, with the plain cue and no audio.

**8. Is this squash-specific?**
The pipeline is general: pose, the 3D skeleton, the ghost edit and the coach with its checker would work for any racket or bat swing. What's squash-specific is the fault library and its thresholds, tuned on squash swings, and the ball and court physics built to the World Squash Federation spec, so a new sport needs its own labelled faults and ball model, not a new pipeline.
