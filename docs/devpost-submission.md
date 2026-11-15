<!--
For pasting into Devpost at 11:00. Each "##" heading is one Devpost field: paste what's under it.
Sources: docs/devpost.md and main at 6302bce. Every claim was checked against main. Where
docs/devpost.md is older than main, this file follows main:
- forearm roll is the gyro integrated about the forearm (#75), not the phone's orientation;
- the wrist sensor has been tried on mock data and one real shadow session (services/wrist/README.md).
Before pasting:
- Figma: set the file's share link to "anyone with the link can view" and open it in a private window.
- If #73 (ghost direction), #74 (real wrist threshold), #81 (Adaption) or #83 (Figma case study)
  merge before 11:00, recheck the lines that mention their topics. #73 changes the ghost's front
  wall from 1.88 m to 1.86 m in screenshot 3.
Delete this comment before pasting.
-->

# Devpost submission: Ghost

## Project name

Ghost

## Tagline

Film one squash swing. Ghost measures it, names the one fix that matters, and shows a 3D ghost of you making it, with the predicted ball path for both swings.

## Inspiration

Squash is fast. The swing is over before you can feel what went wrong, and a coach's "turn your shoulders less" is hard to picture. Video replay shows what you did. It doesn't show the better swing on your own body, or where that ball would have gone. And most club players don't have a coach courtside every session.

We wanted to show a player the swing they haven't played yet.

## What it does

- **Film one swing.** You film one squash swing on your phone and drop the clip on the upload page. Ghost detects slow motion, the hitting hand and forehand or backhand by itself.
- **See it in 3D.** The swing becomes a 3D skeleton on a full-size squash court.
- **Get the coach's call.** The code measures the swing (shoulder and hip turn, elbow angles, when the wrist uncocks, stance) and names the one fix that matters. It quotes only numbers it measured. A fault it can't measure is listed as "not measured", never guessed.
- **Meet your ghost.** A cyan ghost of you makes that fix beside your orange swing: the same body, the same swing, one thing changed.
- **See where the ball goes.** Both balls fly on the court, yours and the ghost's, each labelled **PREDICTED**. There is no ball tracking.
- **Hear the coach.** On a swing you upload, Claude words the fix as one spoken sentence and ElevenLabs reads it aloud. A code checker rejects any sentence that changes a number or the direction of the fix. Without keys, the page shows the coach's plain cue.
- **Every number says where it came from.** On screen, each one is labelled measured, estimated, assumed, predicted or mock.

## How we built it

- **Two cameras, no calibration board.** An iPhone films in slow motion (120 frames per real second) and an iPad at normal speed. We sync the two videos on the sound of the hit, calibrate the cameras from the player's own joints, and triangulate a 3D skeleton, scaled to metres from the torso length. A single phone works too, with depth estimated.
- **Pose.** MediaPipe Pose Landmarker (heavy model) finds 33 joints in every frame. The pipeline splits a clip into swings and finds contact from the hit sound, or from the wrist's speed peak when there's no sound.
- **The coach is plain code.** Twelve fault rules turn the measurements into ranked faults, each with a size, a severity and a confidence, and pick one fix.
  - We filmed and labelled real forehands and backhands. In each block the player acted one fault or none.
  - 4 rules are tuned on those labelled swings, 6 use coaching defaults, and 2 wrist rules come from mock sensor data. The code marks each rule's source.
  - A fault that would rest on a joint the camera couldn't see is skipped and listed as not checked.
- **The ghost and the ball.** Physics edits your skeleton to make the fix (turn the shoulders less, bend or straighten the elbow, close the stance, hold the wrist cock), with bone lengths kept fixed. It then re-measures the ghost with the same code.
  - An effective-mass collision gives ball speed from racket speed.
  - The ball flies with gravity and drag on a court built to the World Squash Federation spec.
- **Voice.**
  - **Claude Opus 5.5** gets only the coach's fault, cue and tip, never the raw metrics, and returns one sentence through structured outputs.
  - **A code checker** rejects invented or changed numbers, negations and the opposite direction word; a sentence that fails is never spoken.
  - **ElevenLabs** (`eleven_turbo_v2_5`) speaks it, server-side.
  - **Caching:** a successful clip is cached per swing.
- **Wrist sensor.** A phone strapped to the forearm records with Sensor Logger at 100 Hz, synced to the video by two taps and the impact spikes.
  - Forearm roll is the gyro integrated about the forearm, and it feeds the coach's rolled-wrist rule.
  - The sensor also estimates racket speed for the predicted ball.
- **Adaption.** A fault-injection data generator built from our own real swings, exported in Adaption's format, and fine-tuned Qwen3.5-2B with AutoScientist: 66% win rate vs the base model on Adaption's own eval, below its 70% target. This is Adaption's own measure, judged on evaluations it derives from our training data. It isn't accuracy on our held-out swings, so it isn't comparable with our held-out test numbers. The data is SIMULATED, and Ghost's live coach doesn't use the tuned model yet.
- **Web app.**
  - **Front end:** Next.js 16, React 19, TypeScript and Tailwind CSS 4, with three.js for the 3D replay and the court.
  - **Back end:** a local FastAPI service, behind a same-origin proxy so the browser never talks to Python directly.
- **Design in Figma.** The Figma frames came first:
  - **#71:** the landing page.
  - **#76:** the shared header and the upload page.
  - **#82:** the swing view (step bar, coach card, ghost legend and PREDICTED tags).
- **Team.** Four people and several AI agents (Claude Code and Codex) worked in one repo under a shared `CLAUDE.md`: folder ownership, typed contracts and small pull requests (80 merged).

## Challenges we ran into

- **Slow-motion video hides the real time.** The same iPhone clip can report 30, 60 or 240 fps depending on how it was shared. Real-time speeds meant reading QuickTime edit lists, with a speed check as the fallback when the metadata was gone.
- **Two cameras and no calibration rig.** We calibrated from the player's own joints and synced on the sound of the ball, which also gave a better contact frame.
- **The wrist peaks after the hit.** On our forehand the hit sound is at frame 48, but the wrist is fastest at frame 54, in the follow-through. Using that peak would have overstated racket speed, so the hit sound wins when there is one.
- **Forehand or backhand?** Measuring along the shoulder line called our backhand a forehand, because the player is side-on at contact. Checking which side of the hips the racket head is on, in court axes, gets it right.
- **Racket speed without a racket tracker.** Scaling up wrist speed works on our two samples but is far off on some real backhands. We kept the estimate, labelled it, and built the wrist sensor rather than add a fudge factor.
- **Keeping Claude honest.** It's easy for a language model to sound precise. We kept all measuring and ranking in code and gave Claude only the words, with a checker on every number and on the direction of the fix. Automated code review kept finding new phrasings that slipped past the checker, and each one became a test.

## Accomplishments that we're proud of

- **It works end to end.** A phone clip becomes a 3D skeleton, the coach's call, a ghost making the fix, and two PREDICTED ball paths, all in the browser.
- **3D from two ordinary cameras with no calibration board**, synced on the sound of the hit.
- **A sanity check against video.** On two real swings, the predicted front-wall height was within about 0.1–0.3 m of where the ball hit in the video. That's a check on two swings, not validation: the launch angle is assumed, and we set it from those same clips.
- **A coach that never guesses.** It measures in code, skips any fault that would rest on a joint the camera couldn't see, and labels every number with its source.
- **A language model that can't invent a number.** Claude only words the fix, and code checks every sentence before it's spoken.
- **A real design system.** Our Figma frames drove three restyle PRs, and the data, the coach's wording and the PREDICTED labels didn't change.
- **Four people, about 24 hours, 80 merged pull requests.**

## What we learned

- **Real data settles arguments that mock data can't.** On the first real wrist-sensor recording, the phone's orientation twist scattered over ±180°. So forearm roll now comes from the gyro integrated about the forearm.
- **Video metadata lies.** The same slow-motion clip reports different frame rates depending on how it was shared, so real-time speeds need the container's timing data and a fallback check.
- **Contact timing changes everything downstream.** Taking the wrist's speed peak instead of the hit sound would have overstated racket speed.
- **Give a language model the words, not the numbers.** A strict checker plus automated review that turns every miss into a test kept the spoken coach truthful.
- **Labels need provenance.** Swing IDs repeat across pipeline runs, so a label has to say which run it belongs to.
- **Honest labels are a feature.** Saying measured, estimated, assumed or predicted on screen made it clear what the demo can and can't claim.

## What's next

- **Racket tracking.** Two strips of coloured tape give the racket's tip and throat in every frame, so racket speed, face angle and launch angle become measured.
- **A watch app.** Replace the strapped-on phone with a smartwatch streaming gyro data, so wrist roll and racket speed are measured on every swing.
- **Retune the rolled-wrist rule on real swings.** It still comes from mock data; the first real session is recorded.
- **The retest loop.** Swing again and see how much of the gap to your ghost you closed.
- **Two fixes at once**, for example close the stance and turn the shoulders less.
- **More labelled swings**, so every fault rule is tuned on data.

## Built with

mediapipe, opencv, numpy, scipy, ffmpeg, python, fastapi, next.js, react, typescript, tailwindcss, three.js, anthropic-claude, elevenlabs, figma, adaption, sensor-logger, claude-code, codex

## Links

- **Code:** https://github.com/DP-LEGEND/hackathon-test (check judges can open it).
- **Figma case study:** https://www.figma.com/design/QlNELzqmM4MHcgjGcgSZN2/UI-design?node-id=60-452 (the flow, the components and tokens, before and after). Only once the share link is public: see the note at the top.

## Screenshots to capture

Five, from the running app in a 1440 × 900 window. Keep every PREDICTED, SAMPLE and Live label in frame.

| # | Page | State | What it shows |
|---|---|---|---|
| 1 | `/ghost` | Forehand · over-rotation, **Coach's call** step | The step bar on step 2, the orange skeleton, and the coach card: *"Over-rotation: hips turn 157°"* and the cyan cue *"Turn a little less and stay balanced through the ball."* |
| 2 | `/ghost` | Same swing, **The ghost** step: click **Side by side** (it opens in Overlay), then scroll so the 3D view and the *What the fix changes* card both show | Orange swing and cyan ghost apart, the fix *Turn shoulders less 52.6°* with the *Coach's pick* badge, and *What the fix changes*: shoulder turn 137.6° → 85° |
| 3 | `/ghost` | Same swing, **On court** step, scrolled so the 3D court and the Ball card both show | Both PREDICTED ball paths with their tags, the ghost legend, and the Ball card (PREDICTED badge): 133.2 → 119.1 km/h, front wall 1.92 → 1.88 m |
| 4 | `/ghost?swing=<id>` after an upload | A **Live** swing you uploaded, at the coach's call, with the coach naming a fault | The **Hear the coach** button and *worded by Claude*, which needs both keys and the Mac online. Without the button, capture `/upload` with a clip chosen instead |
| 5 | `/` | Top of the landing page | The GHOST landing page built from the Figma frames, with the Home, Demo and Try your swing navigation |
