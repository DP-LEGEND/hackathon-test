<!--
TODO (9 AM feature freeze): these are under "In progress / demoed from branch" because they
aren't on main yet. When each one merges, move it into the built sections and delete its line.
- Wrist sensor: PR #44 (feat/wrist-sensor, Henoch)
- Upload page: PR #48 (feat/upload-page, Sammy) and the upload proxy, PR #47 (feat/upload-proxy, Dev)
- Stricter voice checks: PR #65 (fix/voice-guard, Henoch). When it merges, move its checks into
  "Voice coach" (negations, a measured number turned into an amount or target, 60 s retry)
- Anam avatar lines (coach/avatar.py) are on main but only run from the command line
- Adaption: physics/synth.py writes a local adaption.jsonl; no fine-tune has been run or used yet
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

**5. Predicted ball path.** From the racket speed and direction at contact, an effective-mass collision gives the ball speed (about 1.3 × racket-head speed). The ball then flies with gravity and drag that grows with speed squared, on a court built to the World Squash Federation (WSF) spec, with the tin, the out lines and wall bounces. Both swings and both balls are placed in one court coordinate frame, so your ball and the ghost's leave from each racket head. Every path is labelled **PREDICTED**: there is no ball tracking.

**Checked against video on 2 real swings.** The predicted front-wall contact point is within about 0.1–0.3 m of where the ball hits in the video:

| Clip | Predicted | In the video |
|---|---|---|
| Forehand (IMG_2115) | front wall at **1.92 m** high, 2.7 m from the right wall, 133 km/h | about **1.8 m** high, about 2.6 m from the right wall, 125–150 km/h |
| Backhand (IMG_2116) | front wall at **0.78 m** high | **0.5–0.8 m** high |

That's a check on two swings, not accuracy validation. The launch angle is ASSUMED, and we set it from these same clips.

## What's measured and what's estimated

We label every number on screen with where it came from.

| | Examples | How we get it |
|---|---|---|
| **Measured** | 3D joints, shoulder and hip turn, elbow angles, wrist uncock (degrees and ms), stance, contact frame | From the pose, by our code. Contact comes from the hit sound when there is one |
| **Estimated** | Racket-head speed, racket-head position, shot direction, depth in single-phone clips, stroke when it isn't labelled | Racket speed is wrist speed scaled by the lever out to the racket's sweet spot. Shot direction comes from the wrist's motion and is assumed straight when that's unclear. Labelled ESTIMATE |
| **Assumed** | Launch angle (elevation): 12° forehand, 3° backhand. Where on court the ball is struck | Fixed defaults, labelled ASSUMED. We don't track the racket face or the ball yet |
| **Predicted** | Both ball paths, landing spot, front-wall height | Physics from the numbers above, labelled PREDICTED |
| **Simulated** | Synthetic training swings (faults added to real swings) | Labelled SIMULATED wherever they appear |

## Live clips

Film a new swing on **one phone**, send the file, and Ghost does the rest: `POST /process` on the API, or `python -m pipeline clip.mov`.

- **Slow motion, detected automatically.** An AirDropped iPhone slow-mo arrives as a 30 fps video playing 4× slow. We read the QuickTime timing data (edit lists and capture-rate tags) and Apple's playback-intent flag. If that information has been stripped, we retry at 2×, 4× and 8× and keep the speed that gives a believable wrist speed (12–35 m/s).
- **Hitting hand, detected.** We track both wrists and take the faster one inside each swing.
- **Forehand or backhand, detected.** We check which side of the body the hitting wrist is on at contact. If that's ambiguous, the coach decides and it's saved as coach-inferred. Physics checks an automatic label against the skeleton, and the skeleton wins.
- You can override any of these (`--slowdown`, `--hand`, `--stroke`). Single-phone depth is estimated, and the saved swing says so (`source: "mono"`).

Each accepted swing is saved with the coach's call and the ghost comparison, and appears in the `/ghost` page's swing list after a refresh.

## Voice coach

On a swing's caption, press **Hear the coach**. Claude words the coach's fix as one spoken sentence, and ElevenLabs reads it aloud, server-side.

- **Claude only rewords.** The code has already chosen the fix. Claude gets the coach's fault, cue and tip, never the raw metrics. The caption says **worded by Claude** only when it was.
- **A checker on every sentence.** Any number must match one the code measured exactly as written: same sign, digits and unit. Spelled-out numbers are rejected. The fix can't be reversed: if the coach says "turn less", a sentence that says "more" is rejected. A sentence that fails is never used; the coach's own cue is shown instead.
- **Wrist cues are spoken word for word.** "Keep your wrist cocked until the racket meets the ball" has no direction the checker can test, so Claude isn't asked to reword it.
- **Safe without keys.** If there's no Claude key, or Claude takes over 10 s, the page shows the coach's plain cue. If there's no ElevenLabs key, or it takes over 12 s, there's no audio. The page never shows an error for either. Each swing is worded and voiced once, then cached.

## In progress / demoed from branch

These work on their own branches or from the command line and are being merged into the live flow.

**Wrist sensor (Henoch, PR #44).** The camera can't see a rolled wrist, and it can only estimate racket speed. A phone strapped to the forearm can measure both.
- Reads a Sensor Logger recording (accelerometer, gyroscope and orientation at 100 Hz) and syncs it to the video. The sync uses two start taps and the racket-impact spikes, and reports the alignment error for each swing.
- Measures the forearm roll from −150 to +100 ms around contact, which feeds a new `rolled_wrist` fault.
- Estimates racket speed from the camera's wrist speed plus the gyro's spin, and fills in wrist and elbow positions the camera lost behind the body. It also gives a swing tempo and an impact-quality score. All of these are labelled ESTIMATE.
- So far it's tested on **mock data only**: rebuilt joints within 1 cm and racket speed within 4% of the mock truth.

**Upload page (Sammy, PR #48, with Dev's upload proxy, PR #47).** A "Try your own swing" page: drop a clip from your phone, watch it process, and `/ghost` opens on your new swing. The proxy streams the video through the web app to the Python API.

**Stricter voice checks (Henoch, PR #65).** The checker also rejects negations ("don't", "never") and a measured number turned into an amount or a target ("bend your elbow to 109 degrees"). A failed Claude or ElevenLabs call is retried after 60 s.

**Anam avatar.** The coach writes the two or three short lines a talking avatar would say (`coach/avatar.py`). It runs from the command line; the web app doesn't show an avatar.

**Adaption.** Training-data export ready for Adaption fine-tuning. `physics/synth.py` adds faults of known size to real swings, re-measures them, and writes labelled rows to a local `adaption.jsonl`, all marked SIMULATED. We haven't run a fine-tune yet, and nothing in Ghost uses a fine-tuned model.

## Built with

| | Used for |
|---|---|
| **MediaPipe** Pose Landmarker | 33-joint pose in every frame |
| **OpenCV**, **NumPy**, **SciPy** | Two-camera calibration and triangulation, signal filtering, swing finding |
| **ffmpeg / ffprobe** | Reading slow-motion timing and turning clips into frames and audio |
| **FastAPI** | The local Python API: process a clip, list swings, coach, compare |
| **Next.js 16**, **React 19**, **TypeScript**, **Tailwind CSS 4** | The web app, plus a same-origin proxy so the browser never talks to Python directly |
| **three.js** | The 3D replay of you and your ghost, and the court with both PREDICTED ball paths |
| **Anthropic Claude** (Opus 5.5) | Words the coach's fix as one spoken sentence in `/ghost`, checked against the measured numbers and the fix direction |
| **ElevenLabs** | Reads that sentence aloud: the **Hear the coach** button |
| **Claude Code** and **Codex** | How four people built it in parallel in one weekend |

In progress: **Anam** (avatar), see *Anam avatar* above, and **Adaption** (training-data export), see *Adaption* above.

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
- **Racket speed without a racket tracker.** Scaling up wrist speed works on our two samples, but on some real backhands it's far too high or too low. We kept the estimate, labelled it, and are moving racket speed to the wrist sensor rather than adding a fudge factor.
- **Keeping Claude honest.** It's easy for a language model to sound precise. We kept all measuring and ranking in code and gave Claude only the words, with a checker on every number and on the direction of the fix. Automated code review kept finding new phrasings that slipped past the checker, so each one became a test.
- **Four people and several AI agents in one repo for 24 hours.** Folder ownership, typed contracts (`lib/ghost/types.ts`, `docs/interfaces.md`), git worktrees and small pull requests (more than 40) kept us from overwriting each other.

## What's next

- **Racket tracking.** Two strips of coloured tape on the racket give its tip and throat in every frame. Then racket speed, face angle and launch angle become measured, not estimated or assumed.
- **A watch app.** Swap the strapped-on phone for a smartwatch that streams gyro data, so wrist roll and racket speed are measured on every swing without extra kit.
- **The retest loop.** Swing again and see how much of the gap to your ghost you closed.
- **Two fixes at once**, for example close the stance and turn the shoulders less, now that the coach can pair them.
- **More labelled swings**, so every fault rule is tuned on data and none use defaults.
