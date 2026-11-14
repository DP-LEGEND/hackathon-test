<!--
TODO (9 AM freeze): written against main at e648366. The demo section follows
docs/demo-runbook.md (PR #52) click by click. Not on main, so not claimed here: the upload
page (#48), voice in the live flow, and an Adaption fine-tune. If any of them merges,
update the script and docs/devpost.md together.
If PR #54 merges, the backhand sample's coach call becomes "Nothing to fix" (stance 27°, judged
from the feet), so the backhand beat here and in the runbook must be rewritten.
-->

# Ghost: 3-minute pitch

**PRESENTER** speaks. **OPERATOR** clicks, following [docs/demo-runbook.md](demo-runbook.md). Rehearse with a stopwatch.

| Section | Time | Length |
|---|---|---|
| Hook | 0:00–0:15 | 15 s |
| Problem | 0:15–0:35 | 20 s |
| Live demo | 0:35–2:05 | 90 s |
| How it works | 2:05–2:40 | 35 s |
| Honesty | 2:40–2:50 | 10 s |
| What's next | 2:50–3:00 | 10 s |

**Rules**
- Only say a measurement that's on screen. The one exception is the launch angle, and you always call it *assumed*.
- Say **predicted** the first time a ball path appears.
- The wrist sensor is **mock data** so far. Say so.

**Before you start:** everything in the runbook's "Before you go on" and "Start Ghost" is done. `/ghost` is open full screen on **Pick a swing**. The fresh 60 fps clip is in `~/Downloads/fresh.mov`. The wrist-sensor output is already printed in terminal tab 3.

## Hook (0:00–0:15)

**OPERATOR, at 0:00:** in terminal tab 3, start the upload (runbook beat 3), then switch back to `/ghost`. It processes while you talk. The app gives up after 120 seconds.

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

Same clicks as the runbook, faster: all three swings, each to the court. The wrist sensor (beat 4) moves to *How it works*. About 60 seconds is talking. The rest is clicks, loading and the replay, so don't fill the pauses.

### Forehand (0:35–1:15)

| OPERATOR clicks | On screen | PRESENTER says |
|---|---|---|
| The top card, **Forehand · over-rotation** | The coach's call: *"Over-rotation: hips turn 157°"* | This is a real forehand, filmed in slow motion and rebuilt in 3D. Our code measured it. The hips turn 157 degrees. Too much. The coach picks that one fix. |
| **Show the ghost**, then **Play**, then **0.25× slow-mo** | Orange swing, cyan ghost. *Turn shoulders less*, *Coach's pick* | Orange is the swing they played. Cyan is their ghost: same body, same swing, shoulders turning less. |
| **Show the court** | Two paths, each *PREDICTED*. Front wall height 1.92 → 1.88 m | Here's where each ball goes. These paths are predicted. There's no real ball. Their ball hits the front wall at 1.92 metres, with an assumed launch angle of 12 degrees. The ghost's hits at 1.88. Both are in. |

### Backhand (1:15–1:35)

| OPERATOR clicks | On screen | PRESENTER says |
|---|---|---|
| **Try another swing**, then **Backhand · two-camera stereo** | *"Stance too open: stance 80° open to the shot"* | A backhand, filmed on two cameras at once. Stance 80 degrees open. |
| **Show the ghost**, then **Show the court** | One path. *"This fix changes your body position, not the ball"*. Front wall 0.78 m | The ghost closes the stance. The ball doesn't change, and we say so. We don't invent a difference. |

### Fresh clip (1:35–2:05)

| OPERATOR clicks | On screen | PRESENTER says |
|---|---|---|
| **Try another swing**, then **Check again** | A new card with a **Live** badge | This one we filmed today on one phone, at 60 frames a second. Slow motion, hitting hand, and forehand or backhand are all detected automatically. |
| The **Live** card from this upload | *"Reading the coach's call…"*, then the coach's call | The coach measures it live. *(Read the caption exactly as shown.)* |
| **Show the ghost**, then **Show the court** | The ghost, then both *PREDICTED* paths | And there's their ghost, computed just now. |

If the upload isn't back by 1:35, skip this beat and say: "That clip is still processing, so here's how it works." Then go to *How it works*.

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
The measuring and the choice of fix are plain code, so the coach can never invent a number and works offline. Claude writes the cue from those measured numbers, with a checker that rejects any number we didn't measure, but that runs from the command line today, not in the live page yet.

**3. How do you know the coaching is right?**
We filmed blocks of swings where the player acted one fault, labelled them, and tuned four of the twelve rules on the gap between good and faulty swings. The other eight use coaching defaults until we have more data, and the code marks every rule as tuned or default.

**4. Why didn't the backhand ghost change the ball?**
Closing the stance changes the body position but not the estimated racket speed at contact, so physics predicts the same ball. We show that honestly instead of inventing a difference.

**5. Is the wrist sensor real?**
The code is merged: it reads a phone strapped to the forearm, syncs it to the video, and measures forearm roll and racket speed. So far it's tested on mock data only, and a real recording is next.
