<!--
TODO (9 AM feature freeze): these are under "In progress / demoed from branch" because they
aren't on main yet. When each one merges, move it into the built sections and delete its line.
- Anam avatar lines (coach/avatar.py) are on main but only run from the command line
- Adaption: generator, data prep, eval and status script are on main (#78 merged).
- Adaption win rate: the AutoScientist run on Qwen3.5-2B succeeded (15 Nov 04:30, 3 of 3 rounds):
  66% vs the base model, below its 70% target; filled in below. If a later run beats it before
  submission, update the model and the number (check with `python -m physics.adaption_status`).
- Figma: before submitting, set the Figma file's share link to "anyone with the link can view", or
  judges can't open the case study.
- The real-ball check, the measured hit spot and the straight-drive ghosts (sections 5 and the table
  under it) arrive with #86 (stacked on #73). If either hasn't merged, take them out before pasting.
Delete this comment before pasting into Devpost.
-->

# Ghost

**See the shot before you practise it.** Film one squash swing, and Ghost finds the one fix that matters and shows a ghost of you making it, with the predicted ball path for both swings.

## The problem

Squash is fast. The swing is over before you can feel what went wrong, and a coach's "turn your shoulders less" is hard to picture. Video replay shows what you did. It doesn't show what the better swing would look like on your body, or where that ball would have gone. Most club players also don't have a coach courtside every session.

Ghost closes that gap. You film a swing on your phone, then see yourself in 3D (orange) next to your ghost (cyan): the same body, the same swing, with one thing changed. Then a squash court shows where each ball would go.

## How it works

**1. Film.** Two cameras film the swing: an iPhone in slow motion and an iPad at normal speed. The slow-motion clip gives us 120 frames per real second. There's no calibration board. A single phone works too (see *Live clips*).

**2. 3D pose.** MediaPipe Pose Landmarker (heavy model) finds 33 joints in every frame of each video. We sync the two videos on the sound of the ball being hit. The two cameras are calibrated from the player's own joints, seen by both over the whole session. Then we triangulate each frame into a 3D skeleton and scale it to metres from the torso length. The pipeline splits a long clip into individual swings and finds the contact frame, using the hit sound when there is one and the wrist's speed peak when there isn't.

**3. Coach.** The code measures the swing: shoulder turn, hip turn, elbow angle before and at contact, how early the wrist uncocks, and stance width or openness. A fault library turns those numbers into ranked faults, each with a size, a severity and a confidence, and picks the one fix that matters. We filmed and labelled real swings, forehand and backhand. In each block the player acted one fault (early wrist, over-rotation, straight arm, open stance, rolled wrist) or none. **Coach thresholds are tuned on our labelled swings: 4 of the 12 rules are tuned, and the rest use default values until we have more data.** A rule the data can't support can be switched off. A fault we can't measure on a swing is listed as "not measured", never guessed. Ranking is plain code, so the coach gives the same answer every time and works offline.

**4. Ghost.** Physics edits your skeleton to make the fix: turn the shoulders less, bend or straighten the elbow, close the stance, or hold the wrist cock longer. Bone lengths stay fixed, so the ghost is still your body. The ghost then re-measures itself, so the before and after numbers come from the same code.

**5. Predicted ball path.** From the racket speed and direction at contact, an effective-mass collision gives the ball speed (about 1.3 × racket-head speed). The ball then flies with gravity and drag that grows with speed squared, on a court built to the World Squash Federation (WSF) spec, with the tin, the out lines and wall bounces. Both swings and both balls are placed in one court coordinate frame, so your ball and the ghost's leave from each racket head. Every path is labelled **PREDICTED**: the app doesn't track the ball. Where the player hit from is measured from the video when the camera sees the court lines (the floor lines and the player's feet); otherwise it is assumed. Every ghost aims a straight drive: on the demo forehand your PREDICTED ball goes cross-court and the ghost's goes straight down the right wall.

**Checked against the real ball on 2 real swings.** We tracked the ball after contact in the two demo clips and fitted its flight. On the forehand, the tracked ball hit the front wall at 1.17 m; Ghost predicted 1.45 m from body motion alone (0.28 m off, launch angle assumed).

| Clip | Ghost PREDICTED (body motion alone) | Tracked from the real video |
|---|---|---|
| Forehand (IMG_2115) | front wall at **1.45 m** high, 13.5° cross-court, 133 km/h | front wall at **1.17 m** high, 21° cross-court, 136 ± 41 km/h |
| Backhand (IMG_2116) | front wall at **0.77 m** high, straight (aim ASSUMED), 130 km/h | front wall at **0.69 m** high, 23° cross-court, 128 ± 11 km/h |

That's a check on two swings, not accuracy validation. The launch angle is ASSUMED (12° forehand, 3° backhand), and we set it from these same clips; the tracked forehand left at about 7.6°, flatter than the 12° we assume, which is most of the 0.28 m.

## What's measured and what's estimated

We label every number on screen with where it came from.

| | Examples | How we get it |
|---|---|---|
| **Measured** | 3D joints, shoulder and hip turn, elbow angles, wrist uncock (degrees and ms), stance, contact frame, forearm roll (wrist sensor) | From the pose, by our code. Contact comes from the hit sound when there is one. Forearm roll comes from the forearm phone's orientation sensor (its gyroscope if that's missing) |
| **Estimated** | Racket-head speed, racket-head position, shot direction, depth in single-phone clips, stroke when it isn't labelled | Racket speed is wrist speed scaled by the lever out to the racket's sweet spot; with the wrist sensor, it adds the gyro's spin. Shot direction comes from the wrist's motion and is assumed straight when that's unclear. Labelled ESTIMATE |
| **Assumed** | Launch angle (elevation): 12° forehand, 3° backhand. Where on court the ball is struck | Fixed defaults, labelled ASSUMED. We don't track the racket face or the ball yet |
| **Predicted** | Both ball paths, landing spot, front-wall height | Physics from the numbers above, labelled PREDICTED |
| **Simulated** | Synthetic training swings (faults added to real swings) | Labelled SIMULATED wherever they appear |

## Live clips

Film a new swing on **one phone**, drop it on the **Try your own swing** page (`/upload`), and Ghost does the rest. The API (`POST /process`) and the command line (`python -m pipeline clip.mov`) do the same.

- **Upload page.** Drag or pick a clip. Hitting hand, stroke and slow-motion speed default to Auto. Upload progress is real; the processing steps after it run on a timer, and the page says so. When it's done, `/ghost` opens on your new swing at the coach's call; if the coach named a fault, the caption has the **Hear the coach** button (see *Voice coach*). The web app's proxy streams the video to the Python API (up to 250 MB) without holding the whole file in memory.

- **Slow motion, detected automatically.** An AirDropped iPhone slow-mo arrives as a 30 fps video playing 4× slow. We read the QuickTime timing data (edit lists and capture-rate tags) and Apple's playback-intent flag. If that information has been stripped, we retry at 2×, 4× and 8× and keep the speed that gives a believable wrist speed (12–35 m/s).
- **Hitting hand, detected.** We track both wrists and take the faster one inside each swing.
- **Forehand or backhand, detected.** We check which side of the body the hitting wrist is on at contact. If that's ambiguous, the coach decides and it's saved as coach-inferred. Physics checks an automatic label against the skeleton, and the skeleton wins.
- You can override any of these (`--slowdown`, `--hand`, `--stroke`). Single-phone depth is estimated, and the saved swing says so (`source: "mono"`).

Each accepted swing is saved with the coach's call and the ghost comparison, and appears in the `/ghost` page's swing list after a refresh.

## Voice coach

Claude words the coach's fix as one spoken sentence, and ElevenLabs reads it aloud, server-side, from the **Hear the coach** button on the coach's call.

**How to reach it:** upload a swing at `/upload`. When `/ghost` opens on it at the coach's call and the coach has named a fault, the caption has a **Hear the coach** button. It's on uploaded (**Live**) swings only: the saved samples on `/ghost` and `/demo` never call Claude or ElevenLabs, and a caption that says *"No fault found in what was checked"* has no voice.

- **Claude only rewords.** The code has already chosen the fix. Claude gets the coach's fault, cue and tip, never the raw metrics. The caption says **worded by Claude** only when it was.
- **A checker on every sentence.** Any number must match one the code measured exactly as written: same sign, digits and unit. Spelled-out numbers are rejected. A sentence that uses the opposite direction word is rejected: if the coach says "turn less", a sentence that says "more" fails. So are negations ("don't", "never") and a measured number turned into an amount or a target ("bend your elbow to 109 degrees"). A sentence that fails is never used; the coach's own cue is shown instead.
- **Wrist cues are spoken word for word.** "Keep your wrist cocked until the racket meets the ball" has no direction the checker can test, so Claude isn't asked to reword it.
- **Safe without keys.** If there's no Claude key, or Claude takes over 10 s, the page shows the coach's plain cue. If there's no ElevenLabs key, or it takes over 12 s, there's no audio. The page never shows an error for either. A successful clip is cached per swing on disk, so replaying a swing costs nothing and plays offline. A failed call is retried after 60 s.

## Wrist sensor

The camera can't see a rolled wrist, and it can only estimate racket speed. A phone strapped to the forearm can measure both.

- Reads a Sensor Logger recording (accelerometer, gyroscope and orientation at 100 Hz) and syncs it to the video. The sync uses two taps on the phone and the racket-impact spikes, and reports the alignment error for each swing.
- Measures the forearm roll from −150 to +100 ms around contact, which feeds the coach's `rolled_wrist` fault. A swing without usable sensor data lists `rolled_wrist` as "not measured".
- Estimates racket speed from the camera's wrist speed plus the gyro's spin, and the predicted ball uses it when a swing has one. It also fills in wrist and elbow positions the camera lost behind the body, and gives a swing tempo and the impact's peak g and ring-down (reported, not judged). All of these are labelled ESTIMATE.
- The web app has a **Wrist sensor** panel for the coach's call: roll through contact, wrist speed at contact, and two small charts, labelled MEASURED (sensor). Neither demo swing has sensor data yet, so it doesn't appear on `/ghost` today. The API doesn't serve wrist data for live swings yet either.
- So far it's tested on **mock data only**, and labelled MOCK where it appears: rebuilt joints within 1 cm and racket speed within 4% of the mock truth. The `rolled_wrist` threshold comes from mock swings and has to be retuned on real ones.

## In progress / demoed from branch

These work on their own branches or from the command line and are being merged into the live flow.

**Anam avatar.** The coach writes the two or three short lines a talking avatar would say (`coach/avatar.py`). It runs from the command line; the web app doesn't show an avatar.

**Adaption.** A fault-injection data generator built from our own real swings, exported in Adaption's format, and fine-tuned Qwen3.5-2B with AutoScientist: 66% win rate vs the base model on Adaption's own eval, below its 70% target. The data is SIMULATED, and Ghost's live coach doesn't use the tuned model yet. See *Adaption* under *Sponsor tracks*.

## Built with

| | Used for |
|---|---|
| **MediaPipe** Pose Landmarker | 33-joint pose in every frame |
| **OpenCV**, **NumPy**, **SciPy** | Two-camera calibration and triangulation, signal filtering, swing finding |
| **ffmpeg / ffprobe** | Reading slow-motion timing and turning clips into frames and audio |
| **FastAPI** | The local Python API: process a clip, list swings, coach, compare |
| **Next.js 16**, **React 19**, **TypeScript**, **Tailwind CSS 4** | The web app, plus a same-origin proxy so the browser never talks to Python directly |
| **three.js** | The 3D replay of you and your ghost, and the court with both PREDICTED ball paths |
| **Sensor Logger** (phone app) | Records the forearm phone's accelerometer, gyroscope and orientation for the wrist sensor |
| **Anthropic Claude** (Opus 5.5) | Words the coach's fix as one spoken sentence on swings you upload, checked against the measured numbers and the fix direction |
| **ElevenLabs** | Reads that sentence aloud: the **Hear the coach** button on uploaded (Live) swings |
| **Claude Code** and **Codex** | How four people built it in parallel in one weekend |
| **Figma** | Designing the landing page, upload page and swing view; the build follows its frames |

In progress: **Anam** (avatar), see *Anam avatar* above, and **Adaption** (AutoScientist fine-tune on our fault-injection data), see *Adaption* above.

## Sponsor tracks

### Anthropic

Claude is the coach's voice, not its judge. Measuring the swing and choosing the fix are plain code. Claude does the one thing code does badly: it turns the chosen fix into one natural spoken sentence.

- **Where.** The **Hear the coach** button on a swing you upload at `/upload` (a **Live** swing), once the coach has named a fault (`services/coach/live_voice.py`). The saved samples on `/ghost` and `/demo` don't have it. Claude Opus 5.5 (`claude-opus-5-5`) gets the coach's fault, cue and tip, never the raw metrics, and returns one sentence.
- **How we call it.**
  - The Anthropic Python SDK with structured outputs: `messages.parse` against a one-field schema.
  - Low effort, since it's a one-sentence rewording.
  - Server-side fallback: if the model declines, the API retries on a fallback model in the same call.
  - A 10 s timeout and no client retries, so a slow call never holds up the page.
- **Checked by code before it's spoken.**
  - Every number must be one the code measured, written exactly (same sign, digits and unit) and quoted once inside its measured phrase.
  - Spelled-out numbers, negations ("don't", "never"), a measured number turned into an amount or a target, and the opposite direction word are rejected.
  - A sentence that fails is never spoken: the coach's own cue is used instead. The caption says **worded by Claude** only when it was.
- **Built with Claude Code.** Four people and several AI agents worked in one repo under a shared `CLAUDE.md`: folder ownership, git safety rules and the product's honesty rules (code measures, Claude explains; every ball path is PREDICTED).

### ElevenLabs

- **Where.** The same **Hear the coach** button, on swings uploaded at `/upload`: ElevenLabs reads Claude's sentence, or the coach's own cue, aloud (`services/coach/voice.py`). It runs server-side only. The key never reaches the browser, which gets the MP3 inside the response.
- **Model and voice.** `eleven_turbo_v2_5` for low latency, and the "George" voice, which works on the free plan. MP3 at 44.1 kHz.
- **Cheap and demo-safe.**
  - A successful clip is cached per swing on disk, so replaying a swing costs nothing and plays offline. A failed call is retried after 60 s.
  - A 12 s timeout keeps it inside the web proxy's 30 s limit.
  - With no key, or after a timeout, the caption still shows, with no audio and no error.
- **Also.** The coach's avatar lines (`coach/avatar.py`) can be voiced with ElevenLabs from the command line (`--speak`).

### Figma

- **Designed in Figma by Henoch.** The landing page (`/`) and the `/demo` entry follow the Figma frames: desktop and mobile landing, the three process panels, and the full-screen mobile menu (`components/ghost/DESIGN.md`).
- **Taken from the design.** The charcoal and mint palette, the wordmark hierarchy, and the ghost and trail artwork as separate SVGs, so the ghost moves as you scroll. There's a still version for reduced motion.
- **Checked against the frames** at desktop, tablet and phone sizes. The landing links only to flows that work: **Demo** (the saved 3D replay) and **Your swing** (upload). The process panels are labelled illustrations, not footage.
- **Case study in Figma:** [Ghost — case study](https://www.figma.com/design/QlNELzqmM4MHcgjGcgSZN2/UI-design?node-id=60-452). It has three parts:
  - the user flow: upload → swing view → coach's call → ghost replay → court;
  - the components the app uses, with their colour and type tokens;
  - before/after screenshots of the old UI and the restyle.

**How the Figma frames drove the restyle.** The Figma file came first, and each restyle pull request was built straight from its frames:
- **#71** turned the landing frames (desktop and mobile) and the process panels into the new home page and `/demo`.
- **#76** built `/upload` from the upload frame, and gave every page one shared header and navigation, local fonts and the charcoal-and-mint palette.
- **#82** restyles the swing view to the two Results frames: the step bar, the coach card, the ghost legend and the PREDICTED tags.

The data, the coach's wording and the PREDICTED labels didn't change; only the design did.

### Adaption

We built a fault-injection data generator on 94 real swings, then fine-tuned Qwen3.5-2B on its output with AutoScientist (66% win rate vs the base model on Adaption's own eval, below its 70% target). All of it is **SIMULATED**: the faults are injected by code into real swings.

- **A fault-injection data generator** (`services/physics/synth.py`). It takes a real swing, injects one fault of known size into the 3D skeleton (a more bent elbow at contact, less shoulder turn, or an earlier wrist release), then re-measures it with the same code the coach uses. Labels come from the re-measured change, not the requested one. From our 94 real swings it wrote 2,758 labelled rows.
- **Cleaned for training** (`services/physics/adaption_prep.py`).
  - Only the 24 swings that every label marks clean are used, so "none" really means no fault. Re-generated from those, that's 1,414 rows: 1,048 for training and 366 for testing.
  - The answer is the fault's name, never a number, so the model can't invent measurements.
  - Train and test are split by source swing (18 swings for training, 6 for testing), so no swing appears on both sides.
- **Exported in Adaption's format.** The training split is 1,048 rows from 18 swings. Faults outnumber "none" (18 rows), so we repeated the "none" rows up to 343, about the size of each fault class, giving the 1,373 prompt/completion rows we uploaded in raw mode. The 366 test rows from the other 6 swings were never uploaded (the export script checks this).
- **Fine-tuned Qwen3.5-2B with AutoScientist.** Qwen3.5-2B is a small 2-billion-parameter model; the run used LoRA and Adaption's defaults: up to 3 rounds, stopping early at a 0.7 win rate. It ran all 3 rounds, and the best came in the first. `services/physics/adaption_status.py` tracked the run.
  - **66% win rate vs the base model on Adaption's own eval, below its 70% target.** This is Adaption's own measure, judged on evaluations it derives from our training data. It isn't accuracy on our held-out swings, so it isn't comparable with the 34% / 37% / 33% below.
- **What the data taught us** (`services/physics/adaption_eval.py`). We scored a code rule and Claude Opus 5.5 on the same held-out swings.
  - **The injector is reliable.** Compared with the unedited copy of the same swing, all 366 test rows, from the 6 test swings, are named correctly (366 of 366).
  - **A player's average swing isn't a tight enough baseline.** Compared with the average of 8 to 10 of the player's clean swings, the code rule scores 34% on those 366 test rows and Claude 37% on a 200-row sample of them, against 33% for always answering the most common fault. The injected faults (median 16 to 19°, and 45 ms) are smaller than one player's own swing-to-swing spread (about 30°, and 65 to 82 ms).
  - That tells us what the next data has to be: more clean swings per player, so the baseline gets tight enough for faults to stand out.
- **Not in the live demo yet.** Ghost's coach is still the code-plus-Claude flow above. The aim is a small model that can name the fault without calling a large model.

## Team

| Who | Built |
|---|---|
| **aryan** | Physics engine and court frame: swing metrics, ghost edits, predicted ball flight |
| **Sammy** | Ghost UI and upload page: the three.js replay, ghost overlay, court and the `/ghost` flow |
| **Dev** | Pipeline, infra and live clips: pose, two-camera 3D, swing finding, the API and proxy |
| **Henoch** | Coach thresholds, voice and the wrist sensor |

## Challenges

- **Slow-motion video hides the real time.** The same iPhone clip can report 30, 60 or 240 fps depending on how it was shared. Getting real-time speeds meant reading QuickTime edit lists, and falling back to a speed check when the metadata was gone.
- **Two cameras and no calibration rig.** We calibrated from the player's own joints and synced on the sound of the ball, which also gave us a better contact frame.
- **The wrist peaks after the hit.** On our forehand the hit sound is at frame 48, but the wrist is fastest at frame 54, in the follow-through. Using that peak would have overstated racket speed, so the hit sound wins when there is one.
- **Forehand or backhand?** Measuring along the shoulder line called our backhand a forehand, because the player is side-on at contact. Checking which side of the hips the racket head is on, in court axes, gets it right.
- **Racket speed without a racket tracker.** Scaling up wrist speed works on our two samples, but on some real backhands it's far too high or too low. We kept the estimate and labelled it. Rather than add a fudge factor, we built the wrist sensor: when a swing has one, its racket speed is used instead (tested on mock data so far).
- **Keeping Claude honest.** It's easy for a language model to sound precise. We kept all measuring and ranking in code and gave Claude only the words, with a checker on every number and on the direction of the fix. Automated code review kept finding new phrasings that slipped past the checker, so each one became a test.
- **Four people and several AI agents in one repo for 24 hours.** Folder ownership, typed contracts (`lib/ghost/types.ts`, `docs/interfaces.md`), git worktrees and small pull requests (more than 40) kept us from overwriting each other.

## What's next

- **Racket tracking.** Two strips of coloured tape on the racket give its tip and throat in every frame. Then racket speed, face angle and launch angle become measured, not estimated or assumed.
- **A watch app.** Swap the strapped-on phone for a smartwatch that streams gyro data, so wrist roll and racket speed are measured on every swing without extra kit.
- **The retest loop.** Swing again and see how much of the gap to your ghost you closed.
- **Two fixes at once**, for example close the stance and turn the shoulders less, now that the coach can pair them.
- **More labelled swings**, so every fault rule is tuned on data and none use defaults.
- **A tighter per-player baseline**: more clean swings per player, so injected faults stand out from the player's own variation and the small model has a real signal to learn.
