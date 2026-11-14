# Ghost: 2-minute pitch walkthrough

**Line:** see the shot before you practise it.
**Cast:** PRESENTER talks. OPERATOR drives the laptop. Times are targets; rehearse with a stopwatch and log each run in `demo/rehearsal-log.md`.

**Rules on stage**
- Only say a number that is on the screen at that moment. The numbers below are from `data/samples/swing_sample.json` and change with the clip.
- Every ball path is **PREDICTED**. Say the word out loud the first time it appears.
- Anything mocked is labelled MOCK on screen and said out loud.

## Before you go on

- Python service running from `services/`: `python -m uvicorn pipeline.server:app --port 8000`, and http://localhost:8000/health answers.
- `npm run dev` running; `/ghost` open full screen. If the page isn't ready, use the terminal fallback at the bottom.
- Real clip loaded: the backhand from IMG_2116 + IMG_5342 (two cameras, 120 fps). Raw video open in a second tab.
- `.env.local` has both keys. Speaker volume up. Backup video cued.
- Do one full run 5 minutes before you're called, so Claude and ElevenLabs are warm.

## Walkthrough

| Time | Who | Says / does | On screen |
|---|---|---|---|
| 0:00–0:15 | PRESENTER | "Every coach can tell you what you did wrong. None of them can show you the swing you haven't played yet. That's Ghost." | Title: *See the shot before you practise it.* |
| 0:15–0:35 | PRESENTER | "This is a real backhand, filmed this morning on two phones in slow motion." OPERATOR plays 2 seconds of the raw clip, then switches to the replay. "From that video we rebuild the player in 3D: 33 joints, every frame. That's the player, in orange." OPERATOR drags to rotate. | Raw clip, then orange 3D skeleton rotating |
| 0:35–1:00 | PRESENTER | "Our code measures the swing: shoulder turn, elbow, wrist timing, stance. Then Claude coaches. It never guesses a number; it can only quote what the code measured. It picks the one fix that matters." Read the caption as shown, e.g. *"Your wrist releases 56 ms before contact."* | Metric chips; coach caption with the fault and its number |
| 1:00–1:10 | (VOICE) | ElevenLabs reads the cue aloud, e.g. *"Keep your wrist cocked until the racket meets the ball."* PRESENTER stays quiet. | Cue shown as a caption too |
| 1:10–1:35 | PRESENTER | "Now the part no coach can do. This is the player's ghost, in cyan, making that one fix." Point at the cyan figure. "Same body, same swing; only the fix changes." If a ghost note is on screen: "The top fix isn't animated yet, so the ghost shows the next one." | Cyan ghost beside the orange swing; before/after line, e.g. *wrist release 56 → 10 ms* |
| 1:35–1:50 | PRESENTER | "And here's where each ball would go. Orange is the swing they played, cyan is the ghost's. These are **predicted** by physics from the racket speed; there's no ball tracking." Read the change line exactly as shown. | 3D court, two paths, each badged **PREDICTED** |
| 1:50–2:00 | PRESENTER | "Next swing, they try the fix and Ghost re-measures. See the shot before you practise it." | Gap-closed bar or title card |

## If something breaks

- **Voice fails:** keep going; the cue is on screen. Don't wait for it.
- **Coach call fails or hangs over 10 s:** say "here's the run from this morning" and play the backup video from the same moment.
- **`/ghost` not ready:** run this in a big-font terminal and read from it. Say it's the coach's raw output.

  ```
  python -m coach.agent ../data/samples/swing_sample.json --stroke backhand
  ```

- Never debug in front of the judges.

## Risks to fix before demo day

1. **The two ball paths can be identical.** On the sample the ghost's fix is wrist timing (`hold_wrist_cock`, 46 ms), and the predicted ball is unchanged: 130.4 → 130.4 km/h, same landing. Racket speed is estimated from the wrist, so a timing-only fix doesn't move the ball. Either demo a clip whose ghost fix changes the path, or say plainly: "this fix is about timing; the predicted ball is the same."
2. **The caption fault has no ghost yet.** On the sample the top fault is stance (low confidence) and `close_stance` isn't in physics yet, so the ghost shows the wrist fix instead. That's the ghost-note line in the 1:10 beat.
3. **Stroke side:** stroke detection calls the sample a forehand. Always pass the stroke (backhand) explicitly.
4. **Shot direction and contact spot are assumed**, not measured (physics `compare` says so). Don't claim the paths are exact.
