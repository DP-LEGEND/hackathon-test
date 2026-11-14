<!--
TODO (9 AM freeze): written against main at cca6a0d (upload page #48 merged). The demo section
follows docs/demo-runbook.md (PR #52) click by click; merge #56 before #52. Not on main, so not
claimed here: voice or Claude in the live flow, and an Adaption fine-tune. If either changes,
update the script and docs/devpost.md together.
-->

# Ghost: 3-minute pitch

**PRESENTER** speaks. **OPERATOR** clicks. Every click is below. The full set-up, checks and fallbacks are in [docs/demo-runbook.md](demo-runbook.md) (PR #52). Rehearse with a stopwatch.

| Section | Time | Length |
|---|---|---|
| Hook | 0:00–0:15 | 15 s |
| Problem | 0:15–0:35 | 20 s |
| Live demo | 0:35–2:05 | 90 s |
| How it works | 2:05–2:40 | 35 s |
| Honesty | 2:40–2:50 | 10 s |
| What's next | 2:50–3:00 | 10 s |

**Rules**
- Only say a measurement that's on screen. There are two named exceptions, as in the runbook:
  - the **launch angle**, which you always call *assumed*
  - the **video-check height** (about 1.8 m on the forehand), which you always say was *checked by eye against the video*
- Say **predicted** the first time a ball path appears.
- The wrist sensor is **mock data** so far. Say so.

**Before you start** (the runbook has the full checks):
- **Terminal tab 1:** `cd ~/hackathon-demo/services`, then `mkdir -p ~/ghost-stage` (it must be empty), then `GHOST_SWINGS_DIR=~/ghost-stage ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000`
- **Terminal tab 2:** `cd ~/hackathon-demo`, then `npm run dev`
- **Terminal tab 3:** the mock wrist-sensor output already printed (runbook beat 4)
- **Browser tab 1:** http://localhost:3000/ghost, full screen on **Pick a swing**
- **Browser tab 2:** http://localhost:3000/upload. **Choose a video**, pick `~/Downloads/fresh.mov` (one swing, 60 fps), and leave **Hitting hand**, **Stroke** and **Slowdown** on **Auto**. Don't click **Build my ghost** yet.

The replay in `/ghost` plays by itself. Don't click **Play/Pause**: it would pause it.

## Hook (0:00–0:15)

**OPERATOR, at 0:00:** in browser tab 2, click **Build my ghost**, then switch to browser tab 1. **Keep tab 2 open:** leaving `/upload` cancels the upload. When the ghost is ready, tab 2 opens the new swing at the coach's call by itself.

> Every coach can tell you what you did wrong.
> None of them can show you the swing you haven't played yet.
> That's Ghost.
> Film one squash swing. See a ghost of yourself making the one fix that matters.

## Problem (0:15–0:35)

> Squash is fast.
> The swing is over before you can feel what went wrong.
> A coach says "turn your shoulders less". You nod. But you can't picture it.
> Video shows what you did.
> It can't show the better swing on your body, or where that ball would have gone.

## Live demo (0:35–2:05)

Same clicks as the runbook's beats 1–3, faster. The wrist sensor (beat 4) moves to *How it works*. About 60 seconds is talking. The rest is clicks, loading and the replay, so don't fill the pauses.

### Forehand (0:35–1:15)

| OPERATOR clicks | On screen | PRESENTER says |
|---|---|---|
| The top card, **Forehand · over-rotation** | The coach's call: *"Over-rotation: hips turn 157°"* | A real forehand, filmed in slow motion and rebuilt in 3D. Our code measured it: the hips turn 157 degrees. Too much. That's the one fix. |
| **Show the ghost**, then **0.25× slow-mo** (it's already playing) | Orange swing, cyan ghost. *Turn shoulders less*, *Coach's pick* | Orange is the swing they played. Cyan is their ghost: same body, same swing, shoulders turning less. |
| **Show the court** | Two paths, each *PREDICTED*. Front wall height 1.92 → 1.88 m | Here's where each ball goes. These paths are predicted, not tracked. Their ball hits the front wall at 1.92 metres, with an assumed launch angle of 12 degrees. Checked by eye against the video, about 1.8 metres. The ghost's hits at 1.88. |

### Backhand (1:15–1:35)

| OPERATOR clicks | On screen | PRESENTER says |
|---|---|---|
| **Try another swing**, then **Backhand · two-camera stereo** | The coach's call: *"No fault found"*, cue *"Nothing to fix on this swing. Hit the next one the same way."* | A backhand, filmed on two cameras at once. Nothing to fix in what the camera could see, and it couldn't see the wrist. That's exactly why we strapped a sensor to the arm. |
| **Pick a swing** (the step bar at the top) | The swing list | |

### Fresh clip (1:35–2:05)

| OPERATOR clicks | On screen | PRESENTER says |
|---|---|---|
| Switch to browser tab 2 | The new swing at the coach's call: *"Reading the coach's call…"*, then the call, or *"No fault found"* (see below) | This one we filmed today on one phone. Slow motion, hitting hand, and forehand or backhand are all detected automatically. The coach measures it live. *(Read the caption exactly as shown.)* |
| Only if the coach named a fault: **Show the ghost**, then **Show the court** | The ghost (*Coach's pick*), then both *PREDICTED* paths | And there's their ghost, computed just now. |

**If the caption says "No fault found":** read it as shown. Then do one of these:
- Stop the beat there and go to *How it works*.
- Or click **Show the ghost** and say: "This is an example edit at demo size, not a coached fix." The panel says *"Demo size: the coach didn't flag this fault."* Never call it the fix.

**If tab 2 still shows the progress panel** (*Finding your swing… / Measuring… / Building your ghost…*) at 1:35, skip this beat and say: "That clip is still processing, so here's how it works." Then go to *How it works*.

## How it works (2:05–2:40)

**OPERATOR (optional), at the wrist-sensor line:** switch to terminal tab 3. The first line reads **MOCK DATA**.

> Two cameras film the swing.
> MediaPipe finds 33 joints in every frame.
> We sync the cameras on the sound of the hit and build a 3D skeleton. No calibration board.
> Physics places both swings on a full-size court and flies each ball.
> The coach is plain code. It measures and picks one fix.
> Four of its twelve rules are tuned on our labelled swings. The rest are defaults for now.
> A camera can't see a rolled wrist, so there's a phone on the forearm. Mock data so far.

## Honesty (2:40–2:50)

> Joints and angles are measured.
> Racket speed is estimated from the wrist.
> The launch angle is assumed.
> Every ball path is predicted.

## What's next (2:50–3:00)

> Next: track the racket, so speed and angle are measured.
> Then a watch app instead of the phone.
> Ghost: see the shot before you practise it.

## Likely judge questions

**1. How accurate is the predicted ball path?**
We checked it against the video on two real swings, and the front-wall contact point came within about 0.1 to 0.3 metres. That's a check, not validation, because we set the launch angle from those same two clips.

**2. Where does Claude come in?**
The measuring and the choice of fix are plain code, so the live coach can never invent a number and works offline. The Claude-worded cue currently runs on mock numbers in a command-line demo, not in the live app, and a checker rejects any number in it that wasn't measured.

**3. How do you know the coaching is right?**
We filmed blocks of swings where the player acted one fault, labelled them, and tuned four of the twelve rules on the gap between good and faulty swings. The other eight use coaching defaults until we have more data, and the code marks every rule as tuned or default.

**4. Is the wrist sensor real?**
The code is merged: it reads a phone strapped to the forearm, syncs it to the video, and measures forearm roll and racket speed. So far it's tested on mock data only, and a real recording is next.
