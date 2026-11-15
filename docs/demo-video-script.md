<!--
Before recording. Rules: 2:00 hard cut, no logos, intros or music. Every sped-up part shows its
speed (e.g. "4x") and the real run time.
Gates (check the morning of recording, on main, not from this note):
- On main already: #85 (real-ball badge), #86 (hit spot, 1.45 m predicted vs 1.17 m tracked),
  #94 (Ask the coach agent), #101 (Hear the coach word reveal), #107 and #111 (multi upload).
- Wrist beat (6): needs a shadow-swing sample with sensor data in public/swings/catalogue.json
  (an entry with "wristSeries"). Its panel must read "MEASURED (sensor)" with no MOCK badge. On
  main at c5c4f99..2cfbd58 no sample has wrist data, so the beat is out until one lands.
- Ask beat (7): the spoken test in "Set up" passes 3 of 3 on the demo Mac, timing included.
- Front knee line (4): pause on Contact in Side by side and check that the ghost's racket head
  is level with its front knee. If it isn't, drop that clause from the voiceover.
-->

# Ghost: demo video script (1:52)

The Devpost video. It runs **1:52**, 3 s under the 1:55 target and 8 s under the **2:00 hard cut**. It has no logos, intros or music: the first frame is the landing page, and the last frame is the product.

**Rules**
- Every number in the voiceover is on screen at that moment, and every claim is on screen or on main.
- Any sped-up part carries a caption with its speed and the real run time, e.g. *"4x · real run time 16 s"*. Slow-motion parts say *slow motion* (the app's own *0.25×* button counts).
- Keep every *PREDICTED*, *ASSUMED*, *ESTIMATE*, *TARGET* and *MEASURED* label in frame.
- Timed at 150 words a minute (2.5 words a second). If it runs long, cut words. Don't speed up the voice.
- Record only what's on main.

**Honest lines, word for word.** Don't soften or drop these:
- Uploading a second angle or a wrist file on real footage is *"being finished"*. The upload in the video is one video.
- The wrist rule is *"calibrated on shadow swings"* (no ball). Say *"shadow swing"* when its sample is on screen.

| # | Beat | Time | Length |
|---|---|---|---|
| 1 | Landing and the process slider | 0:00–0:09 | 9 s |
| 2 | Upload: three drop zones, then a live one-video upload | 0:09–0:24 | 15 s |
| 3 | Two-camera stereo backhand | 0:24–0:36 | 12 s |
| 4 | The coach's call and Hear the coach | 0:36–0:52 | 16 s |
| 5 | The ghost, side by side | 0:52–1:04 | 12 s |
| 6 | Court: 1.45 → 1.44 m and the real-ball check | 1:04–1:21 | 17 s |
| 7 | Wrist panel on the shadow-swing sample (gated) | 1:21–1:31 | 10 s |
| 8 | Ask the coach (gated) | 1:31–1:41 | 10 s |
| 9 | Close: one phone to start | 1:41–1:52 | 11 s |
| | **Total** | | **1:52** |

If beat 7 or 8 is out, cut it and move the later beats up. Don't stretch other beats to fill the gap: without both, the video runs 1:32.

## What's automated, and what isn't

| Step | How it's done | Chip |
|---|---|---|
| Upload: swing, slow motion, hand, stroke, 3D skeleton | Automated, live, from one video | AUTOMATED |
| A second angle or a wrist file in the upload | On the page, but on real footage it's being finished. Not used in the video | BEING FINISHED |
| The stereo backhand | Two real cameras (an iPhone and an iPad), triangulated by the pipeline. A saved sample | TWO CAMERAS |
| The coach's call, *"Over-rotation: hips turn 157°"* | Automated: code measures and picks the fix | AUTOMATED |
| Claude's wording and the voice | Claude words the cue, code checks it, ElevenLabs speaks it. Live uploads only. Needs both keys and the Mac online | AUTOMATED |
| The ghost | Automated: physics edits the skeleton | AUTOMATED |
| Both ball paths | Simulated: PREDICTED. Launch angle ASSUMED, racket speed ESTIMATE | PREDICTED |
| Where the ball was hit from | MEASURED from the court lines. Run offline, so only on the saved copy | OFFLINE |
| Real-ball check | Ball found and tracked automatically. Court lines picked by hand, once per clip. Run offline | BY HAND + OFFLINE |
| Wrist panel | A forearm phone's gyro, measured. The rolled-wrist rule is an ESTIMATE, calibrated on one shadow session (no ball) | ESTIMATE |
| Ask the coach | A real-time ElevenLabs voice agent. Its numbers come only from Ghost's tools (`get_coach_call`, `get_swing_metrics`, `get_ghost_result`, `simulate_fix`) | AUTOMATED |

## The script

The hero forehand (IMG_2115) is recorded in two passes:
- **Live pass (beats 2 and 4):** the one-swing hero clip is uploaded, and the app gives the coach's call and voice. Only live uploads have a voice.
- **Saved-copy pass (beats 5, 6 and 8):** the same swing from the saved hero files (#86), which add the measured hit spot and the real-ball badge. The seam caption in beat 5 says so.

| # | Time | Screen | Voiceover |
|---|---|---|---|
| 1 | 0:00–0:09 | `/` landing: *"See your swing. Find your edge."* Scroll to **Your swing. Three perspectives.** and drag the **Explore the process** slider through **Input**, **Coach's call** and **Predicted shots**. | *This is Ghost. One phone films your squash swing, and Ghost shows you the swing you haven't played yet.* |
| 2 | 0:09–0:13 | `/upload`, held still: the three drop zones, **Your video**, **Second camera angle (optional, for measured depth)** and **Wrist sensor export (.zip or .csv, optional)**. Caption: *"Second angle and wrist upload on real footage: being finished"*. Chip: BEING FINISHED. | *The upload takes one video, a second angle and a wrist sensor. Multi-upload on real footage is being finished, so today: one video.* |
| 2 | 0:13–0:24 | Drop the one-swing hero clip on **Your video**. **Hitting hand**, **Stroke** and **Slowdown** on **Auto**, then **Build my ghost**. The progress panel sped up, captioned *"[k]x · real run time [N] s"*. It opens `/ghost` on the live swing. Chip: AUTOMATED. | *It finds the swing, the hand and every joint in 3D.* |
| 3 | 0:24–0:36 | The two real source videos of the backhand, side by side, with the iPhone and iPad angles playing in sync, for 4 s. Then `/ghost` on **Backhand · two-camera stereo · 120 fps**: drag to rotate the skeleton. Open **How this was predicted** so *"This swing: two cameras."* is in frame. Chip: TWO CAMERAS. | *Two cameras filmed this backhand from two real angles. Matching them triangulates every joint, so depth is measured, not estimated.* |
| 4 | 0:36–0:45 | Back to the live hero upload at **the coach's call**: *"Over-rotation: hips turn 157°"*. The cue changes to Claude's wording, marked *"worded by Claude"*. | *Code measured it: hips turn 157 degrees, too much. Claude words the fix, code checks every number, ElevenLabs speaks it.* |
| 4 | 0:45–0:52 | Click **Hear the coach**. The ElevenLabs audio plays and the cue's words light up in step with it. Fade the audio out at 0:52 if it runs longer. | *(the coach's voice, no voiceover)* |
| 5 | 0:52–1:04 | **Seam caption, 3 s:** *"Same swing, saved copy: adds the hit spot measured from the court lines (offline)"*. Then the saved hero forehand, **The ghost** step, **Side by side**, **0.25×** (slow motion), and pause on **Contact**. Chip: AUTOMATED. | *Same swing, saved copy. Orange is Aryan. Cyan is Aryan's ghost: same body, turning less, meeting the ball level with the front knee.* |
| 6 | 1:04–1:13 | **Show the court**: two paths, each tagged *PREDICTED*. Orange goes cross-court, cyan goes straight. The change panel's **Front wall height** row in frame: *1.45 → 1.44 m*. Then the badge under the legend: *"Reference check against a real ball: 1.45 m predicted, 1.17 m tracked"*, *"Method: tracked"*. Chips: PREDICTED, TARGET. | *Both balls are predicted, not tracked. Aryan's goes cross-court, the ghost's goes straight. Front wall: 1.45 to 1.44 metres.* |
| 6 | 1:13–1:21 | Cut to the real clip with the ball's tracked path to the front wall (the validate_ball debug image). Caption: *"Real ball, tracked automatically · court lines picked by hand"*. Keep the badge's *1.45* and *1.17* on screen as a caption. Chip: BY HAND + OFFLINE. | *The real-ball check: code tracked the actual ball at 1.17 metres, against 1.45 predicted. The launch angle is assumed.* |
| 7 | 1:21–1:31 | **Gated.** The shadow-swing sample in `/ghost`, scrolled to the **Wrist sensor** panel: *MEASURED (sensor)*, the forearm roll chart, and the coach's rolled-wrist line as the app prints it. Caption: *"Shadow swing: no ball · wrist rule calibrated on shadow swings · ESTIMATE"*. | *A forearm phone reads wrist roll a camera can't see. This shadow swing has no ball; the wrist rule is calibrated on shadow swings.* |
| 8 | 1:31–1:41 | **Gated.** The saved hero copy at **the coach's call**, the **Ask the coach** panel already reading *"Listening: ask why, or what you should feel"*. The slot opens as Aryan says "Why?" out loud. The panel switches to *"The coach is speaking"* and the answer fills the **Conversation** transcript. Caption for the whole beat: *"Real-time ElevenLabs voice agent: numbers only from Ghost's tools"*. | Aryan: "Why?", then the agent's answer. No voiceover. |
| 9 | 1:41–1:52 | Back to the hero's side-by-side ghost at 0.25×. Caption, one line per phone: *"1 phone: a 3D swing, depth estimated"*, *"+ a second phone: depth measured"*, *"+ a forearm phone: the wrist"*. Hard cut at 1:52. | *One phone to start. A second phone adds measured depth, a forearm phone adds the wrist. Ghost shows the swing you haven't played yet.* |

**Word counts, checked against the slots** (2.5 words a second): 1: 19 words, 8 s of 9. 2: 23 + 11 words, 13 s of 15 (the first line runs on over the drop). 3: 20, 8 s of 12. 4: 20, 8 s of 9. 5: 23, 9 s of 12. 6: 19 + 19, 8 s of 9 and 8 s of 8. 7: 24, 10 s of 10. 9: 24, 10 s of 11.

### Beat notes

- **Beat 2:** the three drop zones show what the product takes. Never drop a second file on camera: the multi-upload isn't finished on real footage.
- **Beat 3:** the two source videos live in `data/raw/` (the iPhone and iPad clips of IMG_2116). Ask Dev which ones the stereo sample came from. Don't open the backhand's coach's call: on this swing it reads *"Nothing to fix on this swing"*, which is honest but costs time.
- **Beat 4:** the call must read exactly *"Over-rotation: hips turn 157°"*, matching the saved copy, or the seam in beat 5 isn't true. If it doesn't, use any live upload whose coach names a fault, caption it *"a live upload, not the hero swing"*, and change the voiceover's number to the one on screen.
- **Beat 5:** say *"level with the front knee"* only if the Contact frame shows it (see the gate at the top).
- **Beat 6:** the 1.45 → 1.44 m row is the predicted front-wall height, Aryan's then the ghost's. The real-ball check compares Aryan's 1.45 m with the tracked 1.17 m. Don't mix them up in the edit.
- **Beat 7:** say *"shadow swing"*. If the sample's panel shows a *MOCK* badge or *SAMPLE (sensor)*, the beat is out.
- **Beat 8:** the gap between "Why?" and the answer is real time, so never cut it. If the answer runs past 10 s, fade it and add *"answer cut short"*. Every number spoken before the fade must be in the transcript on screen. No voiceover repeating the agent's numbers.

## Recording checklist

**Set up**
- [ ] The morning of recording, check main's git log, and check the catalogue for a wrist sample:
  ```
  git -C ~/hackathon-demo fetch origin
  ```
  ```
  git -C ~/hackathon-demo log --oneline origin/main | grep -E "pull request #(85|86|94|101|107|111) "
  ```
  ```
  git -C ~/hackathon-demo show origin/main:public/swings/catalogue.json | grep -o '"wristSeries"' | head -1
  ```
  No `"wristSeries"` line means no wrist sample: beat 7 is out.
- [ ] Make the one-swing hero clip from IMG_2115. Ask Dev for the safest cut: sharing can change the frame rate. Rehearse its upload: the call must read exactly *"Over-rotation: hips turn 157°"*. If Auto picks the wrong speed, set **Slowdown** by hand.
- [ ] Run the service on its own empty folder: `mkdir -p ~/ghost-video`, then the runbook's tab 1 command with `GHOST_SWINGS_DIR=~/ghost-video` in place of `~/ghost-stage`.
- [ ] Both keys in `.env.local`, and the Mac online. Never open `.env.local` on screen.
- [ ] **Ask beat only:** add `ELEVENLABS_AGENT_ID` to `~/hackathon-demo/.env.local` for the recording (without it the panel stays hidden). Take it out again after recording, so the stage demo stays as rehearsed.
- [ ] **Ask beat spoken test, on the demo Mac,** on the saved hero copy. Screen-record each run with the microphone and system audio. Click **Ask the coach**, allow the microphone, let the greeting finish, and say "Why?" out loud. Run it 3 times. The beat is in only if all 3 pass every check:
  1. The agent answers by voice, and the answer appears in the **Conversation** transcript.
  2. Every number it says is in the transcript and is a value from the swing's tools.
  3. It names the same fault and the same direction of fix as the coach's call.
  4. No error (*"The coach couldn't connect."* or *"The coach isn't available right now."*).
  5. Timing, read off the screen recording, with 0 s as the start of "Why?": speaking by **3 s**, and the fault, its number and the fix said by **10 s**.
- [ ] Ask beat: wear headphones, so the agent doesn't hear itself.
- [ ] Browser window 1440 × 900, zoom 100%, Do Not Disturb on, desktop clear, macOS **Reduce motion off**.
- [ ] Screen recorder captures system audio, for the ElevenLabs clip.

**Record**
- [ ] Note the upload's real run time from the recording's own clock. The speed in the caption is the real time divided by the time on screen.
- [ ] Two passes: live (upload, call, Hear the coach), then the saved copy (ghost, court, badge, Ask). Pause 2 s before and after every click.
- [ ] Hear the coach: record the whole word reveal, and pick the 7 s in the edit.
- [ ] Ask beat: one continuous take. Only the greeting before "Why?" may be cut. If no take makes the 3 s and 10 s marks, the beat is out.
- [ ] Record the voiceover last, to the edited picture. Fill in [k] and [N] first.

**Before you upload**
- [ ] The cut is 1:52 (shorter if a gated beat is out), and never past 2:00. No logo, title or end card, and no music.
- [ ] Both honest lines are said: multi-upload *"being finished"*, and the wrist *"calibrated on shadow swings"* (if beat 7 is in).
- [ ] Every sped-up part shows its speed and real run time. The seam caption is on screen for at least 3 s.
- [ ] Every number in the voiceover is on screen at that moment: 157, 1.45, 1.44 and 1.17. *PREDICTED* is visible on both ball paths.
- [ ] Burn in the captions: judges often watch muted.
- [ ] Export 1080p MP4. Upload it unlisted to YouTube or Vimeo, and paste the link into Devpost.
