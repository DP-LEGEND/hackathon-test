<!--
TODO (before recording): written against main at faf2168 (#84). Every number below is from
docs/pitch.md, docs/demo-runbook.md or docs/devpost-submission.md, apart from the Adaption 66%
(docs/devpost.md, #81). Three beats depend on open PRs. Check each gate on the morning's main:
- Over-rotation beat: #73 (ghost direction) changes the ghost's front wall from 1.88 m to 1.86 m
  and its landing from 7.32 m to 8.04 m. If docs/elevation-check.md changes the 12° forehand angle
  at 08:40, the wall heights change too and the voiceover must say the new angle. Read the Ball panel.
- Wrist beat: needs #74, #80 and #85 merged. Until then, use version C (spoken, no number).
- Real-ball beat: needs #85 (the badge) and physics' `validation` field in the hero compare file on
  main. Until then, cut the beat. The "about 1.8 m, checked by eye" line in the pitch and runbook is
  deliberately NOT used: the tracked check on feat/ball-validation disagrees with it. aryan decides
  the wording before anything about the real ball is recorded.
- Adaption: if the second AutoScientist run (Qwen3.5-4B) beats 66% before recording, update the
  number here and in docs/devpost.md together.
-->

# Ghost: demo video script (under 3:00)

The Devpost video, recorded from main after the 08:00 court session. Total **2:55**, with 5 s to spare.

**Rules (same as on stage)**
- Every number in the voiceover is on screen at that moment. The one exception is the **launch angle**, which is never shown, so the voiceover always calls it *assumed*.
- Say **predicted** the first time a ball path appears. Keep every *PREDICTED*, *MOCK*, *ESTIMATE* and *ASSUMED* label in frame. Never crop them out.
- Record only what's on main. If a gated beat's PR hasn't merged, use its fallback or cut it. Don't record from a branch.
- Timed at 150 words a minute (2.5 words a second), plus the clicks. If it runs long, cut words. Don't speed up the voice.
- If you shorten a wait (the upload's processing), caption the cut: *"Processing shortened"*.

| Beat | Time | Length |
|---|---|---|
| 1. Hook | 0:00–0:10 | 10 s |
| 2. Problem | 0:10–0:24 | 14 s |
| 3. Upload | 0:24–0:42 | 18 s |
| 4. Coach's call | 0:42–0:58 | 16 s |
| 5. Ghost side by side, PREDICTED paths | 0:58–1:18 | 20 s |
| 6. The over-rotation moment | 1:18–1:39 | 21 s |
| 7. Rolled wrist to firm wrist | 1:39–2:04 | 25 s (version C: 17 s) |
| 8. Real-ball check | 2:04–2:20 | 16 s (cut if not on main) |
| 9. Built with | 2:20–2:50 | 30 s |
| 10. Close | 2:50–2:55 | 5 s |
| **Total** | | **2:55** |

If beat 7 uses version C, every later beat starts 8 s earlier. If beat 8 is cut, every later beat starts 16 s earlier.

## The script

### 1. Hook (0:00–0:10)

| Time | Screen | Voiceover |
|---|---|---|
| 0:00–0:04 | The real IMG_2115 slow-motion forehand, the clip the hero ghost is built from. No caption. | *Every coach can tell you what you did wrong.* |
| 0:04–0:08 | Hard cut to `/ghost`, hero forehand, **The ghost** step, **Side by side**, 0.25× slow-mo: orange swing, cyan ghost. Then the court, with both *PREDICTED* paths. | *Ghost shows you the swing you haven't played yet.* |
| 0:08–0:10 | Title card: **GHOST** | |

Don't open on the 08:00 footage here: the ghost on screen is built from IMG_2115, so the clip before it has to be IMG_2115 too.

### 2. Problem (0:10–0:24)

| Time | Screen | Voiceover |
|---|---|---|
| 0:10–0:16 | 08:00 B-roll: a straight forehand drive at full speed (shot 2), then the contact close-up in slow motion (shot 3). | *Squash is fast: the swing is over before you feel what went wrong.* |
| 0:16–0:24 | The same drive, from the back wall, replaying at normal speed. | *A coach says "turn your shoulders less". You can't picture it, and video only shows what you did.* |

### 3. Upload (0:24–0:42)

| Time | Screen | Voiceover |
|---|---|---|
| 0:24–0:28 | Shot 4: over the shoulder of a teammate filming the player on a phone. | *Film one swing on your phone and drop it in.* |
| 0:28–0:36 | `/upload`: **Choose a video** with the 08:00 fresh clip, **Hitting hand**, **Stroke** and **Slowdown** on **Auto**, then **Build my ghost**. Progress: *Uploading your clip → Finding your swing… → Measuring… → Building your ghost…* Caption the jump cut *"Processing shortened"*. | *Ghost finds the swing, the hitting hand, and forehand or backhand, by itself.* |
| 0:36–0:42 | The fresh swing opens in `/ghost`. Drag to rotate the 3D skeleton. | *MediaPipe finds 33 joints in every frame, and the swing becomes a 3D skeleton.* |

Don't read the fresh swing's coach card in the voiceover: what it says depends on the clip. Beat 4 moves to the saved forehand, and says so.

### 4. Coach's call (0:42–0:58)

| Time | Screen | Voiceover |
|---|---|---|
| 0:42–0:44 | **Pick a swing**, then the top card **Forehand · over-rotation (acted and flagged) · iPhone 120 fps (IMG_2115 16:55)**. Lower third: *"Saved sample: forehand, acted fault"*. | |
| 0:44–0:58 | **The coach's call:** *"Over-rotation: hips turn 157°"*, cue *"Turn a little less and stay balanced through the ball."* | *This forehand has an acted fault. The code measured it: the hips turn 157 degrees. Too much. The coach names one fix, and only quotes numbers the code measured.* |

### 5. Ghost side by side, with the PREDICTED paths (0:58–1:18)

| Time | Screen | Voiceover |
|---|---|---|
| 0:58–1:08 | **Show the ghost** (it opens in Overlay), then **Side by side**. Fix *Turn shoulders less 52.6°*, badge *Coach's pick*. It's already playing: don't click **Play/Pause**. | *Orange is the swing they played. Cyan is their ghost: same body, same swing, shoulders turning less.* |
| 1:08–1:18 | **Show the court**: two paths, each tagged *PREDICTED · … · in*, and the ghost legend. Hold on it for 3 s. | *And here's where each ball goes. Both paths are predicted, not tracked.* |

### 6. The over-rotation moment (1:18–1:39)

| Time | Screen | Voiceover |
|---|---|---|
| 1:18–1:22 | Back to **The ghost** (step bar), still side by side. **0.25× slow-mo**, then **Contact**: it jumps to contact and pauses. Rotate slowly so both pairs of hips show. | *Freeze at contact: that's the over-rotation.* |
| 1:22–1:28 | Scroll with the pointer **beside** the replay (over it, scrolling zooms) to *What the fix changes*: Shoulder turn 137.6° → 85°. | *The ghost's shoulder turn drops from 137.6 to 85 degrees.* |
| 1:28–1:39 | **On court**, scrolled so the court and the **Ball** panel (*PREDICTED*) both show: ball speed 133.2 → 119.1 km/h, **front wall height 1.92 → 1.88 m**. | *Its predicted ball hits the front wall at 1.88 metres, the player's at 1.92, with an assumed 12-degree launch angle.* |

If #73 has merged, the panel reads **1.92 → 1.86 m**: say 1.86. Always read the heights from the panel in the take you use.

### 7. Rolled wrist to firm wrist (1:39–2:04)

Only on main with #74, #80 and #85 merged. Record version A or B only if the take shows all four of these:
1. the coach's call starts *"Rolled wrist"*;
2. the cue reads *"Keep your wrist firm through contact."*;
3. the fix chip reads *Keep your wrist firm … · Coach's pick*;
4. on court, the orange ball goes cross-court and the cyan ghost goes straight, both *PREDICTED*.

A real 08:00 sensor swing may come back with the wrist *not checked* (#74 only checks rolled wrists on gyro-peak-timed swings). If so, use version B or C.

**Version A: a real sensor swing from 08:00 (25 s)**

| Time | Screen | Voiceover |
|---|---|---|
| 1:39–1:45 | Shot 6 close-up: the phone strapped to the forearm, the two taps. | *The camera can't see wrist roll, so we strapped a phone to the forearm.* |
| 1:45–1:52 | The sensor swing in `/ghost` at **the coach's call**: *"Rolled wrist: …"*, cue *"Keep your wrist firm through contact."* | *A rolled wrist leads the coach's call: keep your wrist firm through contact.* |
| 1:52–2:04 | **Show the ghost** (fix *Keep your wrist firm*, *Coach's pick*), then **Show the court**: the orange ball pulls cross-court, the cyan ghost goes straight, the aim row labelled *ASSUMED*. | *The rolled ball is predicted to pull cross-court; the firm-wrist ghost goes straight. The face turn is assumed, and the screen says so.* |

**Version B: the mock sensor sample (25 s).** Same screens, using the sample from #80's `scripts/make_mock_wrist_sample.py`. Every wrist label must read *MOCK (sensor)* or *MOCK sensor data*. Voiceover:

> The camera can't see wrist roll, so we strapped a phone to the forearm. This swing is mock sensor data, and it's labelled. A rolled wrist leads the coach's call: keep your wrist firm through contact. The rolled ball is predicted to pull cross-court; the firm-wrist ghost goes straight.

**Version C: spoken, no number (17 s, 1:39–1:56).** Use it if the PRs haven't merged or no take passes the four checks. Screen: shot 6 (the strapped phone, the taps, a backhand). The pitch's line:

> The camera can't see wrist roll, which is why the coach couldn't check it. So we strapped a phone to the forearm. We've tried it on real practice swings without a ball, but the numbers aren't solid enough to quote yet.

If any 08:00 sensor swings were real hits, drop "without a ball".

### 8. Real-ball check (2:04–2:20)

Only if main has #85 and the hero compare file carries physics' `validation` field, so the court shows the badge. Otherwise cut the beat. Don't replace it with the by-eye 1.8 m line (see the note at the top).

| Time | Screen | Voiceover |
|---|---|---|
| 2:04–2:12 | Hero forehand, **On court**: the badge under the legend, *"Checked against the real ball: [P] m predicted, [T] m tracked"*, with *"Method: …"* below it. | *We checked one prediction against the real ball: [P] metres predicted, [T] tracked.* |
| 2:12–2:20 | Cut to the real clip, with the ball's tracked path to the front wall. Caption: *"Real ball, tracked in the video"*. | Pick the line that matches the badge (below). |

Read [P] and [T] exactly as the badge prints them. Then pick one:
- **Close:** *Close, but that's one swing: a check, not validation.*
- **Off:** *The real ball hit [lower/higher]: the launch angle and court spot are assumed, so racket tracking is next.*

Never say "validated" or "accurate".

### 9. Built with (2:20–2:50)

| Time | Screen | Voiceover |
|---|---|---|
| 2:20–2:30 | A live swing where the coach named a fault (the beat 3 upload if it named one, otherwise any uploaded clip with a fault), at **the coach's call**: the cue changes to Claude's wording (*"worded by Claude"*), then click **Hear the coach**. | *Claude turns the coach's fix into one spoken sentence, and code checks every number before it's spoken. ElevenLabs gives it a voice.* |
| 2:30–2:35 | Hold the frame. **Let the ElevenLabs audio play on its own**, with no voiceover. If it runs past 5 s, fade it out. | *(the coach's voice)* |
| 2:35–2:38 | The Figma frames beside the built pages: landing, upload, swing view (the Figma case study, node 60-452). | *Every screen started as a Figma frame.* |
| 2:38–2:50 | Title card, exactly: **Adaption · AutoScientist fine-tune of Qwen3.5-2B · 66% win rate vs the base model, on Adaption's own eval (target 70%) · SIMULATED training data · not used by the live coach yet** | *With Adaption we fine-tuned a small model on simulated data: a 66% win rate over its base model, on Adaption's own eval. It's not in the app yet.* |

Don't call it accuracy, and don't put it next to the 34% / 37% / 33% eval numbers: Adaption's win rate isn't comparable with them.

### 10. Close (2:50–2:55)

| Time | Screen | Voiceover |
|---|---|---|
| 2:50–2:55 | The hero forehand, side by side at 0.25×. End card: **GHOST · see the shot before you practise it** and the repo link. | *Ghost: see the shot before you practise it.* |

## Shot list: 08:00 court session

docs/elevation-check.md has priority at 08:00: its cameras (A behind the player, B on the side wall) and its 6 + 6 straight drives come first, unchanged. These shots fit around it. The **B-roll phone** is a third phone, handheld, and stays out of cameras A and B.

| # | Shot | Angle | Camera settings | Swings | Takes | Beat |
|---|---|---|---|---|---|---|
| 1 | Elevation-check hits | As docs/elevation-check.md: A from the back wall, B on the side wall | As that doc | 6 straight forehand drives, then 6 backhand drives | As that doc | Camera A's footage is spare B-roll for beat 2 |
| 2 | Full-speed drive | B-roll phone at the back wall, beside camera A: the whole court and the front wall in frame | Normal video, 60 fps, landscape | Straight forehand drives, during shot 1 | 3 | 2 |
| 3 | Contact close-up | B-roll phone side-on, out of cameras A and B, racket and ball filling the frame | Slo-mo, landscape | Forehand drives | 3 | 2 |
| 4 | Filming a swing | Over the shoulder of a teammate filming the player on a phone. Their phone screen is visible. | Normal video | 1 forehand per take | 2 | 3 |
| 5 | Fresh upload clip | Camera A position, behind the player, one player, whole body in frame | **60 fps normal video, not slow motion** (runbook step 4), a few seconds per clip | 1 forehand per clip | 3 (keep the cleanest) | 3. The same clip can be the stage's `~/Downloads/fresh.mov` |
| 6 | Wrist sensor block | Camera A behind the player (Slo-mo), plus B-roll close-ups of strapping the phone on and the two taps | Sensor Logger at 100 Hz on the forearm phone. Two taps on it in view of camera A before the first swing | Backhands: **at least 5 normal and 5 rolled usable** (wrist.tune's minimum). Film 8 of each so skipped swings don't sink it. Say "normal 1", "rolled 1" and so on before each, and log the label | 1 block of 16 | 7 |
| 7 | Front wall | B-roll phone at the back wall, zoomed on the front wall: the tin and the service line in frame | Slo-mo | Straight forehand drives | 3 | 8 (cutaway) |
| 8 | Courtside upload | Over the shoulder at the laptop: **Build my ghost** clicked on `/upload` | Normal video | None | 1 | 3 (optional) |

**Order:** shots 1–3 together (08:00–08:15), then 6 (sensor), then 5, 4, 7 and 8. Then hand over to the elevation-check decision at 08:40.

**Before you leave the court:**
- [ ] Watch one take of each shot on the phone: in focus, ball visible after contact, whole body in frame for shots 5 and 6.
- [ ] Only team members are in frame.
- [ ] AirDrop everything into `data/raw/` (git-ignored). Never commit a clip.

## Recording checklist

**Set up**
- [ ] Record from the demo folder on the latest main, as in the runbook's pre-flight step 1. Check which gated PRs (#73, #74, #80, #85) are in `git log`.
- [ ] Start the service with its own empty folder for the video, never `~/ghost-stage` (the show needs that empty): `mkdir -p ~/ghost-video`, then the runbook's tab 1 command with `GHOST_SWINGS_DIR=~/ghost-video` in place of `~/ghost-stage`. Add `SSL_CERT_FILE` as the runbook says if the voice check needs it.
- [ ] `scripts/demo_smoke.py` says *"5/5 checks passed"*.
- [ ] `.env.local` has both keys and the Mac is online, or **Hear the coach** won't appear. Never open `.env.local` or show a terminal with keys on screen.
- [ ] Browser window 1440 × 900, zoom 100%, bookmarks bar hidden. Type `localhost:3000/ghost` (`/` is the landing page).
- [ ] macOS: Do Not Disturb on, desktop clear, **Reduce motion off** (otherwise the replay starts paused).
- [ ] Screen recorder set to capture system audio, so the ElevenLabs clip is recorded. macOS's own screen recording doesn't capture it by default.
- [ ] Warm up: click the hero forehand through to the court once, so the first take doesn't wait for the page to compile.

**Record**
- [ ] Screen first, one take per beat, with a 2 s pause before and after each click.
- [ ] Voiceover last, in a quiet room, to the edited picture. Write the badge numbers (beat 8) and wall heights (beat 6) from the takes into the script before recording the voice.
- [ ] Scroll with the pointer beside the 3D view, never over it.

**Before you upload**
- [ ] Stopwatch the full cut: under 3:00.
- [ ] Hook: Ghost is named and shown within the first 10 s.
- [ ] Every number in the voiceover is on screen at that moment, except the launch angle, which is called assumed.
- [ ] *PREDICTED* is on every ball path and said the first time. *MOCK* labels are visible wherever they appear (beat 7, version B).
- [ ] Nothing in the cut is from a branch. No keys, notifications, emails or names that aren't the team's.
- [ ] Burn in captions: judges often watch muted.
- [ ] Export 1080p MP4. Upload it unlisted to YouTube or Vimeo, and paste the link into Devpost.
- [ ] Keep the takes. The runbook's stage backup video can reuse them.
