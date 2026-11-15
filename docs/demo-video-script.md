<!--
TODO (before recording). Rules: 2:00 hard cut, no logos, intros or music. Every sped-up part
shows its speed (e.g. "4x") and the real run time. Gates, checked on the morning's main:
- The court and real-ball beats need #73 and #86 merged, then aryan's go on
  `python -m physics.demo_files --write`, which rebuilds the saved hero files (player front wall
  1.45 m with the hit spot MEASURED, plus the `validation` field), and #85 for the badge. Until
  then the app shows 1.92 m and no badge, so don't record those beats: see "If the gates aren't met".
- The voice only appears on live uploads (app/ghost/ghost-demo.tsx), and the measured hit spot and
  the real-ball check only on the saved hero copy (#86: "without court lines, as on a live upload,
  the ASSUMED drive spot stays"). So the one swing is recorded in two passes, with the seam captioned.
- [PLAYER]: the hero forehand's player, by name, with their OK to be named and shown.
- [X] of [Y]: counted at the 08:00 session (shot 2). No success rate exists anywhere yet.
- Closest product: SwingVision (tennis and pickleball, tracks shot speed, depth and accuracy;
  no squash found, web search 15 Nov). Spherely lists squash, but its features weren't checked.
- Adaption: if the Qwen3.5-4B run beats 66%, update this file and docs/devpost.md together.
-->

# Ghost: demo video script (1:55)

The Devpost video. It runs **1:55**, under the **2:00 hard cut**. It has no logos, intros or music: the first frame is the player, and the last frame is the product.

**Rules**
- Every number in the voiceover is on screen at that moment.
- Any sped-up part carries a caption with its speed and the real run time, e.g. *"4x · real run time 16 s"*. Slow-motion parts say *slow motion* (the app's own *0.25×* button counts).
- Keep every *PREDICTED*, *ASSUMED*, *ESTIMATE*, *TARGET* and *MEASURED* label in frame.
- Timed at 150 words a minute (2.5 words a second). If it runs long, cut words. Don't speed up the voice.
- Record only what's on main.

| Part | Time | Length |
|---|---|---|
| 1. Problem, with [PLAYER] | 0:00–0:15 | 15 s |
| 2. One real run, start to finish | 0:15–1:30 | 75 s |
| 3. How it's built | 1:30–1:50 | 20 s |
| 4. What's new, how often it works | 1:50–1:55 | 5 s |
| **Total** | | **1:55** (5 s under the cut) |

## What's automated, and what isn't

This decides the voiceover and the small caption chip on each step. There is no mock data in this run.

| Step | How it's done | Chip |
|---|---|---|
| Upload: swing, slow motion, hand, stroke, 33 joints, 3D skeleton | Automated, live | AUTOMATED |
| The coach's call, *"Over-rotation: hips turn 157°"* | Automated: code measures and picks the fix | AUTOMATED |
| Claude's wording and the voice | Automated: Claude words the cue, code checks it, ElevenLabs speaks it. Needs both keys and the Mac online | AUTOMATED |
| The ghost | Automated: physics edits the skeleton | AUTOMATED |
| Both ball paths | Simulated: PREDICTED. Launch angle ASSUMED, racket speed ESTIMATE | PREDICTED |
| The ghost's aim | A straight drive, the shot the player said they meant: TARGET, not measured | TARGET |
| Where the ball was hit from | MEASURED from the court lines. Run offline, so only on the saved copy | OFFLINE |
| Real-ball check | Ball found and tracked automatically. Court lines picked by hand, once per clip. Run offline | BY HAND + OFFLINE |

## The script

### 1. Problem (0:00–0:15)

| Time | Screen | Voiceover |
|---|---|---|
| 0:00–0:07 | The real IMG_2115 forehand at real speed. Caption: *"[PLAYER] · forehand drive · real speed"* | *This is [PLAYER]. They meant to hit this forehand straight down the wall. It went cross-court.* |
| 0:07–0:15 | The same swing in slow motion. Caption: *"slow motion"* | *A coach would say "turn less". But what does "less" look like on your own body?* |

### 2. One real run, start to finish (0:15–1:30)

The same swing as part 1, recorded in two passes:
- **Live pass, 0:15–0:45:** the one-swing clip cut from IMG_2115 is uploaded, and the app gives the coach's call and voice.
- **Saved-copy pass, 0:45–1:30:** the same swing from the saved hero files, which add the measured hit spot and the real-ball check.

Use this version only if the live call reads exactly *"Over-rotation: hips turn 157°"*, matching the saved copy. Otherwise use version B below.

| Time | Screen | Voiceover |
|---|---|---|
| 0:15–0:27 | `/upload`: **Choose a video** (the one-swing hero clip). **Hitting hand**, **Stroke** and **Slowdown** on **Auto**, then **Build my ghost**. The progress panel (*Uploading your clip → Finding your swing… → Measuring… → Building your ghost…*) sped up, captioned *"[k]x · real run time [N] s"*. It opens `/ghost` at the coach's call. Chip: AUTOMATED. | *We upload that one swing. From here it runs by itself: it finds the swing, the hand, the stroke, and 33 joints in 3D.* |
| 0:27–0:39 | **The coach's call:** *"Over-rotation: hips turn 157°"*. A few seconds later the cue changes to Claude's wording, *"worded by Claude"*. Click **Hear the coach**. | *The coach's call: hips turn 157 degrees, too much. Code measured that. Claude words the fix, code checks every number, and ElevenLabs speaks it.* |
| 0:39–0:45 | Hold the frame. **The ElevenLabs audio plays on its own**, with no voiceover. Fade it out at 0:45 if it runs longer. | *(the coach's voice)* |
| 0:45–0:58 | **Seam caption, 3 s:** *"Same swing, saved copy: adds the hit spot measured from the court lines (offline, not in the upload yet)"*. Then the saved hero forehand, **The ghost** step, **Side by side**, **0.25× slow-mo**, then **Contact**. Chip: AUTOMATED. | *Same swing, saved copy, with its hit spot measured offline. Orange is [PLAYER]. Cyan is their ghost: same body, turning less.* |
| 0:58–1:12 | **Show the court**: two paths, each tagged *PREDICTED*. The orange ball goes cross-court, and the cyan ghost's goes straight down the right wall. Chips: PREDICTED, TARGET. | *Both balls are predicted, not tracked, with an assumed launch angle. [PLAYER]'s goes cross-court. The ghost's goes straight down the wall: the drive they meant.* |
| 1:12–1:30 | The badge under the legend: *"Checked against the real ball: 1.45 m predicted, 1.17 m tracked"*, *"Method: tracked"*. Cut to the real clip with the ball's tracked path to the front wall (the validate_ball debug image), captioned *"Real ball, tracked automatically · court lines picked by hand"*. Chip: BY HAND + OFFLINE. | *Then we checked the real ball. Code tracked it by itself, from court lines we marked by hand: front wall 1.17 metres, against 1.45 predicted. Most of the gap is the assumed launch angle.* |

**Version B: the live call doesn't match the saved copy.**
- 0:15–0:27: same as above. Stop on the progress panel and don't show the live call.
- 0:27: cut to the saved copy at **the coach's call**, captioned *"Same swing, saved copy: processed by the same pipeline, plus the hit spot measured offline"*.
- The voiceover runs as above, without the Claude and ElevenLabs sentence. There's no voice in the run: saved copies never ask for one.
- 0:27–0:45: let the ghost and court rows start 12 s earlier and hold each one longer.
- The voice is then heard in part 3 instead (see the ElevenLabs row).

### 3. How it's built (1:30–1:50)

Each tool as it really looks on screen, with no logo cards. No API keys, emails or account names in frame.

| Time | Screen | Voiceover |
|---|---|---|
| 1:30–1:34 | **Figma:** the UI design file's case study page (node 60-452): the frames beside the built pages. | *Every screen was designed in Figma first.* |
| 1:34–1:41 | **Claude coach:** `services/coach/live_voice.py` in the editor: `word_cue` (the Claude call, structured output) and `check_worded_cue` (the checker). | *Claude Opus 5.5 only words the coach's fix; code rejects any changed number.* |
| 1:41–1:43 | **ElevenLabs:** the ElevenLabs web app with the coach's voice and the line it just spoke. In version B, the run's ElevenLabs line is played here, from a live upload. | *ElevenLabs is its voice.* |
| 1:43–1:50 | **Adaption:** the AutoScientist run page or leaderboard showing the Qwen3.5-2B run at a 66% win rate. Caption: *"vs its base model, on Adaption's own eval · SIMULATED data · not in the app"*. | *Adaption: a small model fine-tuned on simulated data, 66% win rate, not in the app.* |

### 4. What's new, how often it works (1:50–1:55)

| Time | Screen | Voiceover |
|---|---|---|
| 1:50–1:55 | The side-by-side ghost at 0.25×. Caption: *"Closest product: SwingVision tracks the shots you played (tennis, pickleball). New: Ghost shows the fix on your own body, and where that ball would go. Worked end to end on [X] of [Y] clips filmed 15 Nov."* Hard cut at 1:55. | *SwingVision tracks shots. Ghost plays the fix. [X] of [Y] worked.* |

"Worked" means the upload finished, and the coach gave a call with a ghost. If shot 2 wasn't filmed, use: *"It found the real ball by itself in both clips we checked."*

### If the gates aren't met

- **#86 or `demo_files --write` not on main:** the saved copy shows a front wall of 1.92 m (1.86 m for the ghost after #73), with no badge.
  - The court row still works: read the panel.
  - The real-ball row can't say 1.45, because 1.45 isn't on screen. Cut it, and give its 18 s to the court and ghost rows.
  - Don't show the validate_ball output from the branch.
- **#73 not merged either:** the ghost's ball doesn't go straight down the wall. Drop "the drive they meant", and say only that both balls are predicted.
- **No keys or no internet:** no voice. Use version B, and leave the ElevenLabs row in part 3 on the web app.

## Shot list: 08:00 court session

docs/elevation-check.md has priority: its cameras and 6 + 6 drives come first, unchanged. The video's run uses IMG_2115, so the court session only needs to add two things.

| # | Shot | Angle | Settings | Swings | Takes | Used in |
|---|---|---|---|---|---|---|
| 1 | Elevation-check hits | As docs/elevation-check.md | As that doc | 6 forehand + 6 backhand drives | As that doc | Not in the video |
| 2 | Clips to count how often it works | Behind the player, where camera A stands, whole body in frame | **60 fps normal video** (runbook step 4), one swing per clip, a few seconds | Mix forehands and backhands, one player per clip | 10 clips | Part 4: upload every one on `/upload` (Auto), and log pass or fail as defined there |
| 3 | [PLAYER] on court (optional) | Front-on or side-on, face visible, only with their OK | Normal video | None, or a practice swing | 2 | Part 1, as a 1 s cutaway before IMG_2115 if it fits |

Upload the shot-2 clips into a separate `GHOST_SWINGS_DIR`, never `~/ghost-stage`. Keep the log (clip, stroke, pass or fail, error message) in `data/raw/` with the clips, never committed.

## Recording checklist

**Set up**
- [ ] On the morning's main, check `git log` for #73, #85 and #86, and that the saved hero file was rebuilt (`physics.demo_files --write`). The court step should show 1.45 m for the player and the real-ball badge. Otherwise follow *If the gates aren't met*.
- [ ] Make the one-swing hero clip from IMG_2115. Ask Dev for the safest cut: sharing can change the frame rate, and the hit sound must survive. Rehearse its upload: the call must read exactly *"Over-rotation: hips turn 157°"* (otherwise use version B). If Auto picks the wrong speed, set **Slowdown** by hand.
- [ ] Run the service on its own empty folder: `mkdir -p ~/ghost-video`, then the runbook's tab 1 command with `GHOST_SWINGS_DIR=~/ghost-video` in place of `~/ghost-stage`.
- [ ] Both keys in `.env.local`, and the Mac online. Never open `.env.local` on screen.
- [ ] Browser window 1440 × 900, zoom 100%, Do Not Disturb on, desktop clear, macOS **Reduce motion off**.
- [ ] Screen recorder captures system audio, for the ElevenLabs clip.
- [ ] Log into Figma, Adaption and ElevenLabs in advance. Hide emails, account names and keys.
- [ ] [PLAYER] has agreed to be named and shown.

**Record**
- [ ] Note the upload's real run time from the recording's own clock. That's the *"real run time"* in the caption. The speed in the caption is the real time divided by the time on screen.
- [ ] Two passes: live (upload, call, voice), then the saved copy (ghost, court, badge). Pause 2 s before and after every click.
- [ ] Record the voiceover last, to the edited picture, and fill in [PLAYER], [k], [N], [X] and [Y] first.

**Before you upload**
- [ ] The cut is 1:55, and never past 2:00. No logo, title or end card, and no music.
- [ ] Every sped-up part shows its speed and real run time. The seam caption is on screen for at least 3 s.
- [ ] Every number in the voiceover is on screen at that moment. *PREDICTED* is visible on both ball paths.
- [ ] Burn in the captions: judges often watch muted.
- [ ] Export 1080p MP4. Upload it unlisted to YouTube or Vimeo, and paste the link into Devpost.
