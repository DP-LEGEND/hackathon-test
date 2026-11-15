<!--
TODO (before recording). Rules: 2:00 hard cut, no logos, intros or music. Every sped-up part
shows its speed (e.g. "4x") and the real run time. Gates, checked on the morning's main:
- #73 and #74 are merged. The court and real-ball rows need #86 (measured hit spot, rebuilt hero
  files: 1.45 m predicted vs 1.17 m tracked) and #85 (the badge). Until both merge, cut the
  real-ball row: see "If the gates aren't met".
- The voice only appears on live uploads (app/ghost/ghost-demo.tsx). The measured hit spot and
  the badge are only on the saved hero copy (#86: a live upload has no court lines). So the one
  swing is recorded in two passes, with the seam captioned.
- Sensor beat (optional, 5 s): only if a real sensor sample is on main by 09:00 and its coach's
  call reads "Rolled wrist…" with no MOCK label. On main, a real swing not timed at the forearm's
  fastest turn lists rolled_wrist as not measured (#74), so check the call, not just the file.
- [X] of [Y]: counted from shot 2 at 08:00. No success rate exists anywhere yet.
- Closest product: SwingVision (tennis and pickleball, tracks shot speed, depth and accuracy;
  no squash found, web search 15 Nov).
- Adaption: if the Qwen3.5-4B run beats 66%, update this file and docs/devpost.md together.
-->

# Ghost: demo video script (1:55)

The Devpost video. It runs **1:55**, under the **2:00 hard cut**. It has no logos, intros or music: the first frame is Aryan, and the last frame is the product.

**Rules**
- Every number in the voiceover is on screen at that moment, and every claim is on screen or on main.
- Any sped-up part carries a caption with its speed and the real run time, e.g. *"4x · real run time 16 s"*. Slow-motion parts say *slow motion* (the app's own *0.25×* button counts).
- Keep every *PREDICTED*, *ASSUMED*, *ESTIMATE*, *TARGET* and *MEASURED* label in frame.
- Timed at 150 words a minute (2.5 words a second). If it runs long, cut words. Don't speed up the voice.
- Record only what's on main.

| Part | Time | Length |
|---|---|---|
| 1. Problem, with Aryan | 0:00–0:15 | 15 s |
| 2. One real run, start to finish | 0:15–1:30 | 75 s (70 s if the sensor beat is used) |
| 2b. Sensor beat (optional) | 1:25–1:30 | 5 s, taken from part 2 |
| 3. How it's built | 1:30–1:50 | 20 s |
| 4. What's new, how often it works | 1:50–1:55 | 5 s |
| **Total** | | **1:55** (5 s under the cut) |

## What's automated, and what isn't

This decides the voiceover and the small caption chip on each step. There is no mock data in this run.

| Step | How it's done | Chip |
|---|---|---|
| Upload: swing, slow motion, hand, stroke, 3D skeleton | Automated, live | AUTOMATED |
| The coach's call, *"Over-rotation: hips turn 157°"* | Automated: code measures and picks the fix | AUTOMATED |
| Claude's wording and the voice | Automated: Claude words the cue, code checks it, ElevenLabs speaks it. Needs both keys and the Mac online | AUTOMATED |
| The ghost | Automated: physics edits the skeleton | AUTOMATED |
| Both ball paths | Simulated: PREDICTED. Launch angle ASSUMED, racket speed ESTIMATE | PREDICTED |
| The ghost's aim | A straight drive, the shot Aryan meant: TARGET, not measured | TARGET |
| Where the ball was hit from | MEASURED from the court lines. Run offline, so only on the saved copy | OFFLINE |
| Real-ball check | Ball found and tracked automatically. Court lines picked by hand, once per clip. Run offline | BY HAND + OFFLINE |

## The script

### 1. Problem (0:00–0:15)

| Time | Screen | Voiceover |
|---|---|---|
| 0:00–0:07 | The real IMG_2115 forehand at real speed. Caption: *"Aryan · forehand drive · real speed"* | *This is Aryan, aiming this forehand straight down the wall. It went cross-court.* |
| 0:07–0:15 | The same swing in slow motion. Caption: *"slow motion"* | *A coach would say "turn less". But what does "less" look like on your own body?* |

### 2. One real run, start to finish (0:15–1:30)

The same swing as part 1, recorded in two passes:
- **Live pass, 0:15–0:45:** the one-swing clip cut from IMG_2115 is uploaded, and the app gives the coach's call and voice.
- **Saved-copy pass, 0:45–1:30:** the same swing from the saved hero files (#86), which add the measured hit spot and the real-ball badge.

Use this version (A) only if the live call reads exactly *"Over-rotation: hips turn 157°"*, matching the saved copy. Otherwise use version B below.

| Time | Screen | Voiceover |
|---|---|---|
| 0:15–0:27 | `/upload`: **Choose a video** (the one-swing hero clip). **Hitting hand**, **Stroke** and **Slowdown** on **Auto**, then **Build my ghost**. The progress panel (*Uploading your clip → Finding your swing… → Measuring… → Building your ghost…*) sped up, captioned *"[k]x · real run time [N] s"*. It opens `/ghost` at the coach's call. Chip: AUTOMATED. | *We upload that one swing. From here it runs by itself: it finds the swing, the hand, the stroke, and every joint in 3D.* |
| 0:27–0:39 | **The coach's call:** *"Over-rotation: hips turn 157°"*. A few seconds later the cue changes to Claude's wording, *"worded by Claude"*. Click **Hear the coach**. | *The coach's call: hips turn 157 degrees, too much. Code measured that. Claude words the fix, code checks every number, and ElevenLabs speaks it.* |
| 0:39–0:45 | Hold the frame. **The ElevenLabs audio plays on its own**, with no voiceover. Fade it out at 0:45 if it runs longer. | *(the coach's voice)* |
| 0:45–0:58 | **Seam caption, 3 s:** *"Same swing, saved copy: adds the hit spot measured from the court lines (offline, not in the upload yet)"*. Then the saved hero forehand, **The ghost** step, **Side by side**, **0.25× slow-mo**, then **Contact**. Chip: AUTOMATED. | *Same swing, saved copy, with its hit spot measured offline. Orange is Aryan. Cyan is Aryan's ghost: same body, turning less.* |
| 0:58–1:12 | **Show the court**: two paths, each tagged *PREDICTED*. The orange ball goes cross-court, and the cyan ghost's goes straight down the right wall. Chips: PREDICTED, TARGET. | *Both balls are predicted, not tracked, with an assumed launch angle. Aryan's goes cross-court. The ghost's goes straight down the wall: the drive Aryan meant.* |
| 1:12–1:30 | The badge under the legend, exactly: *"Reference check against a real ball: 1.45 m predicted, 1.17 m tracked"*, with *"Method: tracked"* under it. Cut to the real clip with the ball's tracked path to the front wall (the validate_ball debug image), captioned *"Real ball, tracked automatically · court lines picked by hand"*. Chip: BY HAND + OFFLINE. | *Then we checked the real ball. Code tracked it by itself, from court lines we marked by hand: front wall 1.17 metres, against 1.45 predicted. The launch angle was assumed.* |

**With the sensor beat (2b),** part 2 gives up 5 s: ghost 0:45–0:57, court 0:57–1:10, real-ball check 1:10–1:25. The voiceover is unchanged; every row still fits.

**Version B: the live call doesn't match the saved copy.** There's no voice in the run, because saved copies never ask for one. The voice moves to part 3, from a live upload with a fault (see *Set up*).

| Time | Screen | Voiceover |
|---|---|---|
| 0:15–0:27 | As in A. Stop on the progress panel and don't show the live call. | As in A. |
| 0:27–0:37 | Seam caption: *"Same swing, saved copy: processed by the same pipeline, plus the hit spot measured offline"*. Then the saved copy at **the coach's call**, *"Over-rotation: hips turn 157°"*. | *Same swing, saved copy, with its hit spot measured offline. The coach's call: hips turn 157 degrees, too much. Code measured that.* |
| 0:37–0:50 | The ghost, as in A. | *Orange is Aryan. Cyan is Aryan's ghost: same body, turning less.* |
| 0:50–1:04 | The court, as in A. | As in A. |
| 1:04–1:22 | The badge and the real clip, as in A. | As in A. |
| 1:22–1:30 | Part 3 starts 8 s early, so the voice gets a full slot (see part 3, version B). With the sensor beat, it goes here (1:22–1:27) and part 3 starts 3 s early. | |

### 2b. Sensor beat (optional, 1:25–1:30)

Only if every gate in the note at the top holds: a real sample on main by 09:00, a call that starts *"Rolled wrist"*, and no *MOCK* label. Otherwise leave it out and keep the times above.

| Time | Screen | Voiceover |
|---|---|---|
| 1:25–1:30 | The real sensor sample in `/ghost` at **the coach's call**: the rolled-wrist call with its wrist-sensor label, as the app prints it. | *The forearm phone catches what the camera can't: a rolled wrist.* |

### 3. How it's built (1:30–1:50)

Each tool as it really looks on screen, with no logo cards. No API keys, emails or account names in frame.

| Time | Screen | Voiceover |
|---|---|---|
| 1:30–1:34 | **Figma:** the UI design file's case study page (node 60-452): the frames beside the built pages. | *Every screen was designed in Figma first.* |
| 1:34–1:40 | **Claude coach:** `services/coach/live_voice.py` in the editor: `word_cue` (the Claude call, structured output) and `check_worded_cue` (the checker). | *Claude only words the coach's fix; code rejects any changed number.* |
| 1:40–1:43 | **ElevenLabs:** the ElevenLabs web app with the coach's voice and the line it spoke. | *ElevenLabs is its voice.* |
| 1:43–1:50 | **Adaption:** the AutoScientist run page or leaderboard showing the Qwen3.5-2B run at a 66% win rate. Caption: *"vs its base model, on Adaption's own eval · SIMULATED data · not in the app"*. | *Adaption: a small model fine-tuned on simulated data, 66% win rate, not in the app.* |

**Version B (part 3 runs 1:22–1:50):** Figma 1:22–1:26, Claude 1:26–1:32, then ElevenLabs for **11 s, 1:32–1:43**. The voice clip needs that slot: cues run up to 20 words.
- On screen: the live upload from *Set up* at **the coach's call**, captioned *"a live upload, not the swing above"*. Click **Hear the coach**.
- Voiceover: *"ElevenLabs is its voice."* Then the clip plays on its own, faded out at 1:43 if it runs longer.
- Then Adaption 1:43–1:50, as above.
- With the sensor beat, Figma and Claude each give up time: Figma 1:27–1:30, Claude 1:30–1:35, ElevenLabs 1:35–1:43 (the clip gets 6 s).

### 4. What's new, how often it works (1:50–1:55)

| Time | Screen | Voiceover |
|---|---|---|
| 1:50–1:55 | The side-by-side ghost at 0.25×. Caption: *"Closest product: SwingVision tracks the shots you played (tennis, pickleball). New: Ghost shows the fix on your own body, and where that ball would go. Worked end to end on [X] of [Y] clips filmed 15 Nov."* Hard cut at 1:55. | *SwingVision tracks shots. Ghost plays the fix. [X] of [Y] worked.* |

"Worked" means the upload finished and the coach gave a call with a ghost.

**If shot 2 wasn't filmed,** replace the caption and the voiceover. [X] and [Y] aren't used.
- Caption: *"Closest product: SwingVision tracks the shots you played (tennis, pickleball). New: Ghost shows the fix on your own body, and where that ball would go. The real ball was tracked automatically in both clips we checked."*
- Voiceover: *"SwingVision tracks shots; Ghost plays the fix. Both real balls tracked."*

### If the gates aren't met

- **#86 or #85 not on main:** the saved copy has the older heights and no badge. Read the court panel as it is. Cut the real-ball row and give its 18 s to the ghost and court rows. Don't show validate_ball output from a branch. If shot 2 wasn't filmed either, drop the real-ball sentence from part 4's fallback caption and voiceover.
- **No keys or no internet:** no voice. Use version B, and keep the ElevenLabs row in part 3 on the web app.

## Shot list: 08:00 court session

docs/elevation-check.md has priority: its cameras and 6 + 6 drives come first, unchanged. The video's run uses IMG_2115, so the court session adds shots 2 to 4.

| # | Shot | Angle | Settings | Swings | Takes | Used in |
|---|---|---|---|---|---|---|
| 1 | Elevation-check hits | As docs/elevation-check.md | As that doc | 6 forehand + 6 backhand drives | As that doc | Not in the video |
| 2 | Clips to count how often it works | **Side-on**, whole body in frame | 60 fps normal video, one swing per clip, a few seconds | Mixed forehands and backhands, one player per clip | **10 single-swing clips** | Part 4: upload every one on `/upload` (Auto) and log pass or fail |
| 3 | Wrist-sensor block | Behind the player, where camera A stands, whole body in frame | Phone **tight on the forearm**, Sensor Logger at **100 Hz**. **Tap the phone 3 times** in view of the camera before the first hit | **8 good + 8 rolled-wrist forehand drives**. Say "good 1", "rolled 1" and so on before each, and log the label | 1 block of 16 | Sensor beat (2b), only if a real sample from it is on main by 09:00 |
| 4 | Aryan on court (optional) | Front-on or side-on, face visible | Normal video | None, or a practice swing | 2 | Part 1, as a 1 s cutaway before IMG_2115 if it fits |

**Order:** shot 1 (08:00–08:15), then shot 3 (sensor), then shot 2, then 4.

Upload the shot-2 clips into a separate `GHOST_SWINGS_DIR`, never `~/ghost-stage`. Keep the log (clip, stroke, pass or fail, error message) in `data/raw/` with the clips, never committed. Sensor Logger exports and their videos also go in `data/raw/`.

## Recording checklist

**Set up**
- [ ] On the morning's main, check `git log` for #85 and #86. The hero court step should show the badge *"Reference check against a real ball: 1.45 m predicted, 1.17 m tracked"*. Otherwise follow *If the gates aren't met*.
- [ ] Make the one-swing hero clip from IMG_2115. Ask Dev for the safest cut: sharing can change the frame rate, and the hit sound must survive. Rehearse its upload: the call must read exactly *"Over-rotation: hips turn 157°"*. Otherwise use version B. If Auto picks the wrong speed, set **Slowdown** by hand.
- [ ] Run the service on its own empty folder: `mkdir -p ~/ghost-video`, then the runbook's tab 1 command with `GHOST_SWINGS_DIR=~/ghost-video` in place of `~/ghost-stage`.
- [ ] **A faulted live swing for the voice, ready before recording.** Upload a clip where the coach names a fault into `~/ghost-video` (the hero clip if it matches, otherwise any shot-2 clip with a fault). Check that **Hear the coach** plays. Version B's part 3 needs this.
- [ ] Both keys in `.env.local`, and the Mac online. Never open `.env.local` on screen.
- [ ] Browser window 1440 × 900, zoom 100%, Do Not Disturb on, desktop clear, macOS **Reduce motion off**.
- [ ] Screen recorder captures system audio, for the ElevenLabs clip.
- [ ] Log into Figma, Adaption and ElevenLabs in advance. Hide emails, account names and keys.
- [ ] Sensor beat: at 09:00, decide in or out by the gates at the top, and pick the matching times.

**Record**
- [ ] Note the upload's real run time from the recording's own clock. That's the *"real run time"* in the caption. The speed in the caption is the real time divided by the time on screen.
- [ ] Two passes: live (upload, call, voice), then the saved copy (ghost, court, badge). Pause 2 s before and after every click.
- [ ] Record the voiceover last, to the edited picture. Fill in [k] and [N] first, and [X] and [Y] only if shot 2 was filmed.

**Before you upload**
- [ ] The cut is 1:55, and never past 2:00. No logo, title or end card, and no music.
- [ ] Every sped-up part shows its speed and real run time. The seam caption is on screen for at least 3 s.
- [ ] Every number in the voiceover is on screen at that moment. *PREDICTED* is visible on both ball paths.
- [ ] Burn in the captions: judges often watch muted.
- [ ] Export 1080p MP4. Upload it unlisted to YouTube or Vimeo, and paste the link into Devpost.
