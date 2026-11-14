<!--
TODO (9 AM freeze): written against main at 34b9298 (wrist sensor #44 merged).
The upload page (#48) has since merged (cca6a0d). Beat 3 still sends the clip from the terminal,
which works on main; switching beat 3 to /upload would need its own check.
If #53 (ghost honesty: measured vs guessed joints) merges, re-check beat 2 and the
"What each screen should show" table.
Beat 2 already assumes #54 (honest backhand sample): the backhand coach call is "No fault found"
(stance 27°, judged from the feet). #54 is NOT on main yet. If it hasn't merged by the demo,
use main's backhand beat in docs/pitch.md.
-->

# Ghost live demo runbook

For the live demo on aryan's Mac. Code: `~/hackathon-demo` (a git worktree). Python: `~/ghost-env`. Everything runs on this Mac at `localhost`. The live flow needs no API keys, and nothing in it calls the internet.

Two people: **PRESENTER** talks, **OPERATOR** drives the laptop and terminal.

## Before you go on (30 minutes before)

**1. Put the demo folder on the latest main.**

```
git -C ~/hackathon-demo fetch origin
```
```
git -C ~/hackathon-demo checkout --detach origin/main
```
```
git -C ~/hackathon-demo log --oneline -1
```

The last line should be the commit you're demoing (34b9298 or later). `package-lock.json` shows as modified in that folder. Leave it: main hasn't changed `package.json` or `package-lock.json`, so `node_modules` is still right. If `package.json` changes at the freeze, run `npm ci` in `~/hackathon-demo`.

**2. Check ports 3000 and 8000 are free.**

```
lsof -nP -iTCP:3000 -iTCP:8000 -sTCP:LISTEN
```

This should print nothing. If it lists anything (for example a dev server from `~/hackathon-test`), stop it with Ctrl+C in its terminal, or ask whoever started it. Otherwise the demo app may start on another port, and the URLs below won't work.

**3. Check the upload tools.** Each command must succeed, or uploads fail.

```
which ffmpeg ffprobe
```
```
ls ~/ghost-models/pose_landmarker_heavy.task
```
```
~/ghost-env/bin/python -c "import mediapipe, fastapi, cv2; print('ok')"
```

This Mac has Node 22, and the repo targets Node 26. Rehearse with the same Node you'll demo with.

**4. Have the fresh clip ready.** Film one swing at **60 fps (normal video, not slow motion)**: a few seconds, one player, whole body in frame. AirDrop it to the Mac and rename it `~/Downloads/fresh.mov`. Upload it once in rehearsal to time it: the app gives up after **120 seconds**.

**Rehearse in a separate folder.** Every upload is saved under `GHOST_SWINGS_DIR/live-<id>/`, and the service lists every saved swing. So a rehearsal upload in the stage folder would show up on stage. For rehearsal, start tab 1 (below) with the same `cd ~/hackathon-demo/services`, then this instead:

```
GHOST_SWINGS_DIR=~/ghost-rehearsal ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000
```

Stop it with Ctrl+C when you're done, then start tab 1 for the show as below.

**5. Optional: make the mock wrist-sensor data (once).**

```
cd ~/hackathon-demo/services
```
```
~/ghost-env/bin/python -m wrist.synth ~/wrist-mock --camera --mishit 3
```

## Start Ghost (three terminal tabs)

**Tab 1: Python service, with a fresh empty folder for the show**

```
cd ~/hackathon-demo/services
```
```
mkdir -p ~/ghost-stage
```
```
ls ~/ghost-stage
```

`ls` should print nothing. If `~/ghost-stage` has anything in it from an earlier run, use a new folder name (for example `~/ghost-stage2`) in both commands. Then:

```
GHOST_SWINGS_DIR=~/ghost-stage ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000
```

Don't add `--reload` for the demo, so a saved file can't restart the service mid-upload. To check it's up:

```
curl http://localhost:8000/health
```

It should answer `{"ok":true}`.

**Tab 2: web app**

```
cd ~/hackathon-demo
```
```
npm run dev
```

Wait for "Ready". The first page load compiles the page, so open it before you go on.

**Tab 3: demo commands** (big font)

```
cd ~/hackathon-demo/services
```

## Browser tabs, in this order

1. **http://localhost:3000/ghost**: the whole demo happens here. Full screen.
2. **http://localhost:8000/health**: shows `{"ok":true}`. Reload it if you're unsure whether the service is up.
3. **The backup video**, once it's recorded at the freeze.

**Warm up:** in tab 1, click through the forehand and the backhand all the way to the court, then click **Try another swing**. The dashed box under the swing list should say *"The live service is running but has no processed swings…"*. That's right for the show: `~/ghost-stage` stays empty until the stage upload. If it lists live swings, tab 1 isn't running with an empty `~/ghost-stage`. If it says *"The live Python service isn't running"*, tab 1 isn't up.

## The 3-minute click path

The page has four steps: **Pick a swing → Coach's call → The ghost → On court**. On the replay: drag to rotate and scroll to zoom. **Play**, **0.25× slow-mo** and **Contact** control playback. **Side by side** / **Overlay** and **Court view** / **Player view** change the layout, and **Reset view** undoes rotation.

**OPERATOR, at 0:00, before the hook** (or before beat 1 if there's no pitch): start the upload in terminal tab 3 (the command is in beat 3), then switch to the browser. This matches `docs/pitch.md`. The clip processes while beats 1 and 2 are on screen. The app gives up after 120 seconds.

### Beat 1: forehand over-rotation ghost (0:00–1:10)

| Click | Screen shows | PRESENTER says |
|---|---|---|
| The top card, **"Forehand · over-rotation (acted and flagged) · iPhone 120 fps (IMG_2115 16:55)"** (badges *Saved sample*, *Demo swing*) | **The coach's call:** *"Over-rotation: hips turn 157°"*, cue *"Turn a little less and stay balanced through the ball."* | Code measured the swing; the coach names one fix and only quotes numbers the code measured. |
| **Show the ghost** | **Your ghost makes the fix.** Fix *Turn shoulders less*, badge *Coach's pick*. *What the fix changes:* Shoulder turn 137.6° → 85°. Click **Play**, then **0.25× slow-mo** | Orange is the swing they played, cyan is the same body with one fix. |
| **Show the court** | **Where the ball goes:** two paths, each labelled *PREDICTED · … · in*. Panel: ball speed 133.2 → 119.1 km/h, **front wall height 1.92 → 1.88 m** | These are **PREDICTED**; there's no real ball. Launch angle is **assumed, 12° for a forehand**. Checked by eye against the video, the real ball hit about 1.8 m. |

### Beat 2: backhand, nothing to fix (1:10–1:30)

**This beat needs #54 on main.** If the backhand's coach's call still says *"Stance too open: stance 80° open to the shot"*, #54 hasn't landed. Use main's backhand beat in `docs/pitch.md` instead.

| Click | Screen shows | PRESENTER says |
|---|---|---|
| **Try another swing**, then **"Backhand · two-camera stereo · 120 fps"** | **The coach's call:** *"No fault found"*, cue *"Nothing to fix on this swing. Hit the next one the same way."* | A backhand, filmed on two cameras at once. Nothing to fix in what the camera could see, and it couldn't see the wrist. That's exactly why we strapped a sensor to the arm. |
| **Pick a swing** (the step bar at the top) | The swing list | |

Don't click **Show the ghost** here. With nothing flagged, the page would show an uncoached example edit.

### Beat 3: the coach's call on a fresh 60 fps clip (1:30–2:45)

The upload command (tab 3, started at 0:00):

```
curl -sS -o ~/last-upload.json -w "%{http_code}\n" -F "file=@$HOME/Downloads/fresh.mov" http://localhost:3000/api/process
```

It prints **201** once the swing, the coach's call and the ghost are saved. Any other number means something went wrong: see the fallback table. `cat ~/last-upload.json` shows the reason.

| Click | Screen shows | PRESENTER says |
|---|---|---|
| **Check again** in the dashed box (you're already on **Pick a swing** after beat 2) | *"1 live swing from the Python service."* A new card with a **Live** badge: *"The coach measures it live; ghosts are computed on request"*. No Live card yet: see *Upload still processing* in the fallback table | One phone, 60 fps. Speed, hitting hand and forehand/backhand are detected automatically. Depth is estimated from one camera. |
| The **Live** card | *"Reading the coach's call…"*, then the coach's call for this swing, or *"No fault found"* (see below) | Read the caption as shown. Its numbers depend on the swing. |
| Only if the coach named a fault: **Show the ghost**, then **Show the court** | *"Making the … ghost…"*, then the ghost (badge *Coach's pick*) and both PREDICTED paths | Same as before, computed just now. |

**If the caption says "No fault found":** read it as shown. Then do one of these:
- Stop beat 3 there and go on to beat 4.
- Or click **Show the ghost** and say: "This is an example edit at demo size, not a coached fix." The panel says *"Demo size: the coach didn't flag this fault."* Never call it the fix.

### Beat 4: wrist sensor (2:45–3:00, optional)

Merged (#44), but **MOCK data only** and **terminal only**: there's no wrist screen in `/ghost`. In tab 3:

```
~/ghost-env/bin/python -m wrist.run ~/wrist-mock/export --contacts ~/wrist-mock/contacts.csv --swings ~/wrist-mock/swings --video-tap 3.304 --out ~/wrist-mock/wrist_metrics.json --series-out ~/wrist-mock/wrist_series.json --filled-out ~/wrist-mock/filled
```

It shows **"MOCK DATA. 100 Hz, 73 s recorded."** and *"10/10 pairs within 100 ms"*. Forearm roll is about +9° to +21° on the normal swings and +58° to +70° on the rolled ones, and synth-04 is flagged *mishit*. Say **"mock"** out loud: the camera can't see a rolled wrist, but a phone on the forearm can. A real recording comes next.

## What each screen should show

All of these come from the saved samples in `public/swings/` and are the same on every run.

| | Forehand over-rotation | Backhand (with #54) |
|---|---|---|
| Coach's call | Over-rotation: hips turn 157° | No fault found |
| Cue | Turn a little less and stay balanced through the ball. | Nothing to fix on this swing. Hit the next one the same way. |
| Ghost fix (Coach's pick) | Turn shoulders less, 52.6° | None: the coach flagged nothing, so beat 2 stops at the coach's call |
| Body change | Shoulder turn 137.6° → 85° | Not shown |
| Ball speed (PREDICTED) | 133.2 → 119.1 km/h | Not shown |
| **Front wall height (PREDICTED)** | **1.92 → 1.88 m** | 0.78 m, not shown in beat 2 |
| Lands from front wall | 8.97 → 7.32 m | Not shown |
| Racket speed (ESTIMATE) | 28.3 → 25.3 m/s | Not shown |
| **Launch angle (ASSUMED)** | **12°**, not on screen | 3°, not said in beat 2 |
| Court | Two paths | Not shown |
| Video check (checked by eye, not on screen) | Real ball hit about 1.8 m high | Real ball hit 0.5–0.8 m high, not said in beat 2 |

**Without #54 (main today),** the backhand still shows the old call: *"Stance too open: stance 80° open to the shot"*, ghost *Close stance* 64.9°, stance 79.9° → 15°, and one PREDICTED path at 130.4 km/h with front wall 0.78 m. For that case, use main's backhand beat in `docs/pitch.md`.

The launch angle isn't shown as a number. The court panel's footnote says the launch angle and the spot on court are assumed, so say the angle out loud and call it assumed.

## If X breaks, do Y

| If | You'll see | Do this |
|---|---|---|
| **Python service down** | *"The live Python service isn't running, so these are the saved samples."* The health tab doesn't load | Beats 1 and 2 don't need it: the saved swings always work. Re-run the tab 1 command with the same `GHOST_SWINGS_DIR=~/ghost-stage` (so the stage upload is kept), then click **Check again**. If it won't start, skip beat 3 and say the upload needs the service. |
| **Upload still processing** | No **Live** card after **Check again**, and curl in tab 3 hasn't printed a number yet | Say "that clip is still processing" and carry on. Click **Check again** before the end, or skip beat 3. |
| **Upload times out** | curl prints **502** after about 2 minutes (the app's 120 s limit) | Python usually keeps working on the clip after the app gives up, and saves it when done. Carry on with the demo and click **Check again** in a minute. If it never appears, resend straight to Python, which has no 120 s limit: the same command with `http://localhost:8000/process` instead of `http://localhost:3000/api/process`. A **429** means the first clip is still processing. |
| **Upload refused** | **429**, *"A clip is already processing"* | Only one clip at a time. Wait for the first one, then click **Check again**. |
| **Slow-mo clip fails** | **422**, *"No fully tracked swing found; keep the whole body in frame and film one clear swing"*, or a swing with a wildly wrong speed | Resend with the speed set by hand: add `-F slowdown=1` for a normal 60 fps video, or `-F slowdown=4` for an AirDropped iPhone slow-mo. Add `-F stroke=forehand` or `-F hand=R` if those were misread. To show the rehearsal swing instead, stop tab 1 (Ctrl+C), restart it with `GHOST_SWINGS_DIR=~/ghost-rehearsal ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000`, then click **Check again**. |
| **Pipeline missing** | **503**, *"Live pipeline unavailable; configure the pose model and ffmpeg/ffprobe"* | Pre-flight step 3 failed. Skip beat 3 and use the saved swings. |
| **Wi-Fi dies** | Nothing, as long as the app is already running | Keep going: the service, the coach and the ghost all run on this Mac. Don't restart the app or run a build while offline (the fonts come from Google Fonts). If anything misbehaves, **use the saved swings** (beats 1 and 2) and skip beat 3. |
| **A ghost won't load** | *"Couldn't make this ghost: …"* | Click **Try again**. If it fails again, click **Try another swing** and pick a saved sample. |
| **Everything is broken** | | Play the backup video from the same moment. Never debug in front of the judges. |

## Rules on stage

- Only say numbers that are on screen. There are two named exceptions:
  - the **launch angle** (12° forehand, 3° backhand), which you always call **assumed**
  - the **video-check heights** (about 1.8 m forehand, 0.5–0.8 m backhand), which you always say were **checked by eye against the video**
- Every ball path is **PREDICTED**. Say the word the first time a path appears.
- Anything mock is **MOCK**: today that's the wrist sensor.

After the demo, stop tabs 1 and 2 with Ctrl+C.
