<!--
TODO (before judging): beat 4 and every beat time follow docs/pitch.md from PR #70, so merge #70
first. The Wi-Fi row's local fonts arrive with #76. #73 changes the forehand ghost's front wall
(1.88 → 1.86 m) and landing (7.32 → 8.04 m) in this file: leave those numbers to #73. The aim
answer under "Rules on stage" is #73's behaviour.
Earlier: written against main at 34b9298 (wrist sensor #44 merged).
Beat 3 uses the /upload page (#48, merged in cca6a0d; flow checked in app/upload/ on main).
If #53 (ghost honesty: measured vs guessed joints) merges, re-check beat 2 and the
"What each screen should show" table.
-->

# Ghost live demo runbook

For the live demo on aryan's Mac. Code: `~/hackathon-demo` (a git worktree). Python: `~/ghost-env`. Everything runs on this Mac at `localhost`. The live flow works with no API keys and no internet. If `.env.local` has the Claude or ElevenLabs key and the Mac is online, the coach card may reword its cue a few seconds later (*"worded by Claude"*) and show a play-voice button; offline or without keys it keeps the plain cue.

Two people: **PRESENTER** talks, **OPERATOR** drives the laptop and terminal.

## Before you go on (30 minutes before)

**1. Put the demo folder on the latest main.**

```
git -C ~/hackathon-demo fetch origin
```

This undoes the known local `package-lock.json` change in that folder, so it can't block the checkout:

```
git -C ~/hackathon-demo checkout -- package-lock.json
```
```
git -C ~/hackathon-demo checkout --detach origin/main
```
```
git -C ~/hackathon-demo log --oneline -1
```

The last line should be the commit you're demoing (34b9298 or later). Then always reinstall the packages, so `node_modules` matches main:

```
cd ~/hackathon-demo && npm ci
```

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

**4. Have the fresh clip ready.** Film one swing at **60 fps (normal video, not slow motion)**: a few seconds, one player, whole body in frame. AirDrop it to the Mac and rename it `~/Downloads/fresh.mov`. Upload it once in rehearsal through `/upload` to time it. If the page says *"Still processing, but this page stopped waiting"*, the clip took longer than the app waits, so trim it closer to the swing.

**Rehearse in a separate folder.** Every upload is saved under `GHOST_SWINGS_DIR/live-<id>/`, and the service lists every saved swing. So a rehearsal upload in the stage folder would show up on stage. If `~/ghost-rehearsal` already exists from an earlier rehearsal, move it aside first:

```
mv ~/ghost-rehearsal ~/ghost-rehearsal-old-$(date +%H%M)
```
```
mkdir -p ~/ghost-rehearsal
```

For rehearsal, start terminal tab 1 (below) with the same `cd ~/hackathon-demo/services`, then this instead:

```
GHOST_SWINGS_DIR=~/ghost-rehearsal ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000
```

In a second terminal tab, start the web app so /upload works:

```
cd ~/hackathon-demo
```
```
npm run dev
```

Stop both with Ctrl+C when you're done, then start terminal tabs 1 and 2 for the show as below.

**5. Voice check (during the rehearsal in step 4).** With the rehearsal tabs still running, upload a swing with a fault through `/upload`: one where the coach names a fault, not *"No fault found"*. At the coach's call, wait a few seconds for **Hear the coach**, click it and listen. It needs both keys in `.env.local` and the Mac online. Without them there's no button, and that's expected, not a failure.

If there's no **Hear the coach** button and terminal tab 1 printed *"ElevenLabs audio unavailable … Could not reach ElevenLabs"*, this Python can't verify ElevenLabs' certificate. Stop terminal tab 1 (Ctrl+C) and start it again with `SSL_CERT_FILE` in front:

```
SSL_CERT_FILE="$(~/ghost-env/bin/python -m certifi)" GHOST_SWINGS_DIR=~/ghost-rehearsal ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000
```

Reload the swing in `/ghost` and click **Hear the coach** again. If that fixed it, put the same `SSL_CERT_FILE=...` in front of the show's tab 1 command too (see *Tab 1* below).

**6. Optional: the morning wrist-sensor sample (for beat 4).** If the morning recording has been run through `wrist.run` into a `wrist_metrics.json`, beat 4 can show it; *Tab 3* below says how to print and check it. Otherwise beat 4 is spoken, with no number. Don't use the mock data (`wrist.synth`) on stage: beat 4 never shows *MOCK DATA*.

**7. Run the smoke check** (`~/ghost-env/bin/python scripts/demo_smoke.py`) once terminal tabs 1 and 2 are up: see tab 3 below.

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

`ls` should print nothing. If it prints anything, move the old folder aside and make a fresh one, so every command below still uses `~/ghost-stage`:

```
mv ~/ghost-stage ~/ghost-stage-old-$(date +%H%M)
```
```
mkdir -p ~/ghost-stage
```

Run `ls ~/ghost-stage` again; it must print nothing. Then:

```
GHOST_SWINGS_DIR=~/ghost-stage ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000
```

If the voice check (pre-flight step 5) needed `SSL_CERT_FILE`, start it like this instead:

```
SSL_CERT_FILE="$(~/ghost-env/bin/python -m certifi)" GHOST_SWINGS_DIR=~/ghost-stage ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000
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

**Tab 3: smoke check, then the morning wrist sample for beat 4** (big font)

With tabs 1 and 2 running, check the service, the web app and the saved swings:

```
cd ~/hackathon-demo
```
```
~/ghost-env/bin/python scripts/demo_smoke.py
```

Every line should say PASS, ending *"5/5 checks passed"*. A FAIL line says what's wrong: fix it before you go on.

Then, only if the morning wrist sample is ready (pre-flight step 6), print it last, so it's what's on screen at beat 4:

```
cd ~/hackathon-demo/services
```

Edit the path to the morning `wrist_metrics.json` and the run name in the next two lines before you press Enter on each:

```
WRIST_JSON=~/path/to/morning/wrist_metrics.json
```
```
RUN=your_run_name
```
```
clear
```
```
~/ghost-env/bin/python -m wrist.tune "$WRIST_JSON" ../data/labels/labels.csv --run "$RUN"
```

Beat 4 shows this tab only if **all four** hold. Otherwise beat 4 is spoken and this tab stays hidden:
1. The first line does **not** say *MOCK DATA*, and it shows **at least 5 normal and 5 rolled** usable swings (wrist.tune's own minimum).
2. There's a `roll_change_abs_deg (deg)` block with a `normal median …` line, a `rolled median …` line and an `in-sample: …` line. If it says *"roll_change_abs_deg: not measured in both groups"*, there are no medians to read.
3. The rolled median is larger than the normal median.
4. wrist.tune reports **no skipped swings**: the first line ends *"0 labelled swings skipped."*, with no `skipped …` lines under it.

## Browser tabs, in this order

1. **http://localhost:3000/ghost**: beats 1 and 2. Type this address: `/` is now a landing page. Full screen.
2. **http://localhost:3000/upload**: beat 3. Before you go on, click **Choose a video**, pick `~/Downloads/fresh.mov`, and leave all three settings (**Hitting hand**, **Stroke**, **Slowdown**) on **Auto**. Don't click **Build my ghost** yet.
3. **http://localhost:8000/health**: shows `{"ok":true}`. Reload it if you're unsure whether the service is up.
4. **The backup video**, once it's recorded at the freeze.

**Saved-sample backup:** with the web app and Python service running, run `npx playwright install chromium` once to prepare the browser and video encoder.
Run `node scripts/record_backup_demo.ts` (Node 26); set `GHOST_DEMO_URL` for a different localhost port.
It saves silent 1920×1080 video to ignored `out/backup-demo.webm`, holding each beat for 3 seconds using saved samples only (no live upload, camera or keys). Never commit the video.

**Warm up:** in tab 1, click through the forehand and the backhand all the way to the court, then click **Try another swing**. The dashed box under the swing list should say *"The live service is running but has no processed swings…"*. That's right for the show: `~/ghost-stage` stays empty until the stage upload. If it lists live swings, terminal tab 1 isn't running with an empty `~/ghost-stage`. If it says *"The live Python service isn't running"*, terminal tab 1 isn't up.

## The 3-minute click path

The page has four steps: **Pick a swing → Coach's call → The ghost → On court**. On the replay: drag to rotate and scroll to zoom.
- **The replay plays by itself.** Don't click **Play/Pause**: it would pause it. The exception is when macOS **Reduce motion** is on: then the replay starts paused at contact, and you click **Play**.
- **0.25× slow-mo** only changes speed. **Contact** jumps to contact and pauses.
- **Side by side** / **Overlay** and **Court view** / **Player view** change the layout, and **Reset view** undoes rotation.

**OPERATOR, at 0:00, before the hook** (or before beat 1 if there's no pitch): in browser tab 2 (`/upload`, clip already chosen, settings on Auto), click **Build my ghost**, then switch to browser tab 1. This matches `docs/pitch.md`. **Keep browser tab 2 open:** leaving `/upload` cancels the upload, so don't click the top navigation in that tab either (Home, Demo, …). While it works, browser tab 2 shows *Uploading your clip → Finding your swing… → Measuring… → Building your ghost…*. When the ghost is ready, browser tab 2 opens `/ghost?swing=<id>` at the coach's call by itself.

Beat times are the pitch's (`docs/pitch.md`), counted from the hook at 0:00. The order is beat 1, beat 2, **beat 4 (wrist sensor)**, then beat 3 (the fresh clip), as in the pitch.

### Beat 1: forehand over-rotation ghost (0:34–1:16)

Browser tab 1 is http://localhost:3000/ghost, opened directly: `/` is now a landing page.

| Click | Screen shows | PRESENTER says |
|---|---|---|
| The top card, **"Forehand · over-rotation (acted and flagged) · iPhone 120 fps (IMG_2115 16:55)"** (badges *Saved sample*, *Demo swing*) | **The coach's call:** *"Over-rotation: hips turn 157°"*, cue *"Turn a little less and stay balanced through the ball."* | Code measured the swing; the coach names one fix and only quotes numbers the code measured. |
| **Show the ghost** | **Your ghost makes the fix.** Fix *Turn shoulders less*, badge *Coach's pick*. *What the fix changes:* Shoulder turn 137.6° → 85°. It's already playing: click **0.25× slow-mo** only | Orange is the swing they played, cyan is the same body with one fix. |
| **Show the court** | **Where the ball goes:** two paths, each labelled *PREDICTED · … · in* | These are **PREDICTED**; there's no real ball. Launch angle is **assumed, 12° for a forehand**. Checked by eye against the video, the real ball hit about 1.8 m. We set the 12° from this clip, so it's a sanity check, not a test. |
| Scroll down with the pointer **beside** the replay, not over it (scrolling over the 3D view zooms it) | The **Ball** panel (*PREDICTED*): ball speed 133.2 → 119.1 km/h, **front wall height 1.92 → 1.88 m** | *(Read the front wall heights from this panel.)* |
| Scroll back up to the top, again with the pointer beside the replay | The step bar and **Try another swing** | |

### Beat 2: backhand, nothing to fix (1:16–1:34)

| Click | Screen shows | PRESENTER says |
|---|---|---|
| **Try another swing**, then **"Backhand · two-camera stereo · 120 fps"** | **The coach's call:** *"No fault found in what was checked"*, cue *"Nothing to fix in what the coach could check."* | A backhand, filmed on two cameras at once. Nothing to fix in what the coach could check. It also says what it couldn't check: the wrist (no sensor on this swing) and checks that need the right elbow, which the camera couldn't see. That's exactly why we strapped a sensor to the arm. |
| **Pick a swing** (the step bar at the top) | The swing list | |

Don't click **Show the ghost** here. With nothing flagged, the page would show an uncoached example edit.

### Beat 4: wrist sensor (1:34–1:59, straight after beat 2)

As in `docs/pitch.md`, this beat now runs between beats 2 and 3. There's no wrist screen in `/ghost`: it's terminal tab 3 or nothing. Call any sensor number an **ESTIMATE**, and never show *MOCK DATA* on stage.

**Show terminal tab 3 only if it passes all four checks** in *Tab 3* above (not *MOCK DATA*, with at least 5 normal and 5 rolled usable swings; both `roll_change_abs_deg` medians and the `in-sample:` line printed; rolled median larger; no skipped swings). Then (25 s, 1:34–1:59):

| Click | Screen shows | PRESENTER says |
|---|---|---|
| Switch to terminal tab 3 | The morning `wrist.tune` output: `roll_change_abs_deg (deg)`, the normal and rolled medians, the in-sample line | The camera can't see wrist roll, which is why the coach couldn't check it. So we strapped a phone to the forearm. It's an estimate from one session: normal backhands turned [normal median]° through contact, rolled ones [rolled median]°, and every usable swing was sorted correctly. *(Read both medians exactly as printed. Say "estimate". Don't subtract them out loud. Only say "every usable swing sorted correctly" if the in-sample line shows 100% of rolled and 0% of normal.)* |

**Otherwise, including whenever tab 3 prints *MOCK DATA*, don't show the tab** (17 s, 1:34–1:51). Switch nothing and say no number:

> The camera can't see wrist roll, which is why the coach couldn't check it. So we strapped a phone to the forearm. We've tried it on real practice swings without a ball, but the numbers aren't solid enough to quote yet.

Then go straight on to beat 3. After the spoken version it starts at 1:51, and every later time is 8 s earlier.

### Beat 3: the coach's call on a fresh 60 fps clip (1:59–2:21, or 1:51–2:13 if beat 4 was spoken)

The clip was sent at 0:00 from browser tab 2 (`/upload`: **Choose a video**, settings on **Auto**, **Build my ghost**).

| Click | Screen shows | PRESENTER says |
|---|---|---|
| Switch to browser tab 2 | It has opened `/ghost?swing=<id>` at **the coach's call** for the fresh swing: *"Reading the coach's call…"*, then the call, or *"No fault found"* or *"No fault found in what was checked"* (see below). If it still shows the progress panel, see *Upload still processing* in the fallback table | One phone. Speed, hitting hand and forehand/backhand are detected automatically. Depth is estimated from one camera. Then read the caption as shown: its numbers depend on the swing. |
| If the coach named a fault: **Show the ghost** | *"Making the … ghost…"*, then the ghost and its fix | *(Say nothing yet; look at the badge.)* |
| If the fix shows the badge *Coach's pick*: **Show the court** | Both PREDICTED paths | Same as before, computed just now. |

If browser tab 2 says *"Your ghost is ready."* but hasn't moved on, click **Open it in Ghost**.

**If the caption says "No fault found" or "No fault found in what was checked":** read it as shown. Then do one of these:
- Stop beat 3 there and go on (in the pitch, to *How it works*).
- Or click **Show the ghost** and say: "This is an example edit at demo size, not a coached fix." The panel says *"Demo size: the coach didn't flag this fault."* Never call it the fix.

**If the coach named a fault but the panel says *"Demo size: the coach didn't flag this fault"*:** the coach's fault has no ghost yet. Say: "This is an example edit at demo size, not the coached fix." Never call it the fix, or stop beat 3 there and go on (in the pitch, to *How it works*).

## What each screen should show

All of these come from the saved samples in `public/swings/` and are the same on every run.

| | Forehand over-rotation | Backhand |
|---|---|---|
| Coach's call | Over-rotation: hips turn 157° | No fault found in what was checked |
| Cue | Turn a little less and stay balanced through the ball. | Nothing to fix in what the coach could check. |
| Ghost fix (Coach's pick) | Turn shoulders less, 52.6° | None: the coach flagged nothing, so beat 2 stops at the coach's call |
| Body change | Shoulder turn 137.6° → 85° | Not shown |
| Ball speed (PREDICTED) | 133.2 → 119.1 km/h | Not shown |
| **Front wall height (PREDICTED)** | **1.92 → 1.88 m** | 0.78 m, not shown in beat 2 |
| Lands from front wall | 8.97 → 7.32 m | Not shown |
| Racket speed (ESTIMATE) | 28.3 → 25.3 m/s | Not shown |
| **Launch angle (ASSUMED)** | **12°**, not on screen | 3°, not said in beat 2 |
| Court | Two paths | Not shown |
| Video check (checked by eye, not on screen) | Real ball hit about 1.8 m high | Real ball hit 0.5–0.8 m high, not said in beat 2 |

The launch angle isn't shown as a number. The court panel's footnote says the launch angle and the spot on court are assumed, so say the angle out loud and call it assumed.

## If X breaks, do Y

| If | You'll see | Do this |
|---|---|---|
| **Python service down** | `/ghost`: *"The live Python service isn't running, so these are the saved samples."* `/upload`: *"The Ghost service isn't running"*. The health tab doesn't load | Beats 1 and 2 don't need it: the saved swings always work. Re-run the terminal tab 1 command with the same `GHOST_SWINGS_DIR=~/ghost-stage` (so the stage upload is kept). If it won't start, skip beat 3 and say the upload needs the service. |
| **Upload still processing** | Browser tab 2 still shows the progress panel (*Finding your swing… / Measuring… / Building your ghost…*) | Skip beat 3, as the pitch does: say "That clip is still processing, so here's how it works." and go on to *How it works*. Don't switch back to browser tab 2 later: switching tabs mid-pitch looks shaky. |
| **Upload times out** | `/upload` (browser tab 2): *"Still processing, but this page stopped waiting"* | The Python service keeps going and saves the swing when done. Carry on. Later, in browser tab 1, go to **Pick a swing** and click **Check again**: the swing appears as a **Live** card. `~/ghost-stage` started empty, so it's the only **Live** card, unless you already re-uploaded after a wrong speed: then there are two **Live** cards in no set order, so open each and use the one whose speed looks right. |
| **Upload refused** | `/upload` (browser tab 2): *"A clip is already processing"* | Only one clip at a time. Wait for the first one, then click **Try again**. |
| **Slow-mo clip fails** | `/upload` (browser tab 2): *"Couldn't build your ghost"* with the server's message (e.g. *"No fully tracked swing found; keep the whole body in frame and film one clear swing"*) | Set **Slowdown** by hand: **1×** for a normal 60 fps video, **4×** or **8×** for slow motion. Set **Hitting hand** or **Stroke** if those were misread. Then click **Try again**. To show the rehearsal swing instead, stop terminal tab 1 (Ctrl+C), restart it with `GHOST_SWINGS_DIR=~/ghost-rehearsal ~/ghost-env/bin/python -m uvicorn pipeline.server:app --port 8000`, then in browser tab 1 go to **Pick a swing** and click **Check again**. |
| **Speed wildly wrong** | Browser tab 2 opened the fresh swing in `/ghost`, but its speed is wildly wrong | There's no **Try again** here: a finished upload jumps to `/ghost`, and `/upload` resets. In browser tab 2, go back to http://localhost:3000/upload, click **Choose a video** and pick `~/Downloads/fresh.mov` again. Set **Slowdown** (**1×** for a normal 60 fps video, **4×** or **8×** for slow motion), and **Hitting hand** or **Stroke** if those were misread. Then click **Build my ghost**. |
| **Pipeline missing** | `/upload` (browser tab 2): *"Couldn't build your ghost"* with *"Live pipeline unavailable; configure the pose model and ffmpeg/ffprobe"* | Pre-flight step 3 failed. Skip beat 3 and use the saved swings. |
| **Wi-Fi dies** | Nothing, as long as the app is already running | Keep going: the service, the coach and the ghost all run on this Mac. The fonts are local, so nothing loads from Google. That's true once #76 merges; until then the fonts come from Google Fonts, so don't restart the app or run a build while offline. If anything misbehaves, **use the saved swings** (beats 1 and 2) and skip beat 3. |
| **A ghost won't load** | *"Couldn't make this ghost: …"* | Click **Try again**. If it fails again, click **1 Pick a swing** in the steps at the top and pick a saved sample. |
| **Everything is broken** | | Play the backup video from the same moment. Never debug in front of the judges. |

## Rules on stage

- Only say numbers that are on screen. There are two named exceptions:
  - the **launch angle** (12° forehand, 3° backhand), which you always call **assumed**
  - the **video-check heights** (about 1.8 m forehand, 0.5–0.8 m backhand), which you always say were **checked by eye against the video**
- Every ball path is **PREDICTED**. Say the word the first time a path appears.
- The wrist sensor: show terminal tab 3 only when it passes the checks in *Tab 3*, and call its numbers an **ESTIMATE**. Never show *MOCK DATA* on stage; if you mention the mock tests, say **mock**.
- If a judge asks about the ghost's aim, the answer is: "We aimed it at the straight drive the player said he meant." That's #73's behaviour: until #73 merges, the ghost's ball direction comes from its own wrist motion, so don't give this answer before then.

After the demo, stop terminal tabs 1 and 2 with Ctrl+C.
