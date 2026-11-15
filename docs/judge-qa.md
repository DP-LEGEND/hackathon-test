<!--
Facts from main at faf2168: docs/devpost.md, services/ and public/swings/.
Two answers depend on open pull requests. Q2 and Q3 each give the answer that's true on main
now, then the one to use once #86 (stacked on #73) has merged.
- Use the #86 answers only after public/swings has also been rebuilt
  (python -m physics.demo_files --write). Until then the screen still shows the forehand's front
  wall at 1.92 m.
- Once #86's answer is in use, stop saying "about 1.8 m, checked by eye": the tracked ball says
  1.17 m.
-->

# Ghost: judge Q&A

Fifteen hard questions, each with a 2–3 sentence answer. Say less rather than more, and never a number that isn't here or on screen. Every ball path is **PREDICTED**, and the launch angle is always **assumed**.

## The ball

**1. How do you predict where the ball goes without tracking it?**
We estimate racket-head speed and direction at contact from the wrist's motion (plus the gyro's spin when the forearm phone is worn), and an effective-mass collision turns that into a ball speed of about 1.3 × racket-head speed. The ball then flies with gravity and drag on a court built to the World Squash Federation spec, with the tin, the out lines and wall bounces. The launch angle (12° forehand, 3° backhand) and the spot on court are assumed, so every path is labelled PREDICTED.

**2. How accurate is it?**
*On main now:* We checked it against the video on two real swings, and the predicted front-wall height came within about 0.1–0.3 m. On the forehand it predicts 1.92 m against about 1.8 m checked by eye; on the backhand, 0.78 m against 0.5–0.8 m. That's a sanity check, not validation, because the launch angle is assumed and we set it from those same clips.

*Once #86 has merged and the demo files are rebuilt:*
- We now track the real ball in the demo clips automatically and compare its flight with our prediction.
- On the forehand the real ball hit the front wall at 1.17 m and we predict 1.45 m, 0.28 m off, now that the hit spot is measured from the court lines (it was 0.75 m off with the assumed spot).
- The rest of the gap is the launch angle: it's still assumed at 12°, while the real ball left at about 7.6°, and we deliberately don't fit it to the ball.

**3. Why does the ghost's ball go straight?**
*On main now:* It doesn't yet. Each ball's direction is estimated from the hitting wrist's motion at contact, and the ghost's comes out slightly more across the court than the player's. It's labelled ESTIMATE.

*Once #86 has merged:* Every ghost aims a straight drive, parallel to the side walls, labelled TARGET, or STATED when the player told us the shot he meant: "we aimed it at the straight drive the player said he meant." On our forehand the fix doesn't turn the racket at contact at all, so without a target the ghost's ball would go where the player's did; the player's own swing and ball never change.

## The coach and the ghost

**4. Is the ghost just an animation?**
No. It's the player's own skeleton, edited by physics to make one fix (turn the shoulders less, bend or straighten the elbow, close the stance, or hold the wrist cock), with bone lengths kept fixed. The ghost is then re-measured with the same code as the player's swing, so the before and after numbers come from one measurement.

**5. How do you know the coaching is right?**
We filmed blocks of real forehands and backhands where the player acted one fault or none, and labelled them. 4 of the coach's 12 rules are tuned on those labelled swings, 6 use coaching defaults, and 2 wrist rules come from mock sensor data; the code marks each rule's source. It's a small labelled set, so expect misses on new players until we label more.

**6. What happens when the camera can't see a joint?**
The pose model still guesses a joint it can't see. So the coach skips any fault that would rest on a guessed joint and lists it as not checked instead of guessing. The ghost also refuses a fix that would edit a guessed joint: on our backhand the right elbow was hidden, so the elbow fixes say "not available on this swing".

**7. Does it work with one phone?**
Yes. Drop one clip on the upload page, and it detects:
- slow motion, from the video's timing data;
- the hitting hand, from the faster wrist;
- forehand or backhand, from which side of the body the wrist is on at contact.

Depth from one camera is estimated, not measured, and the screen says "one-camera depth".

**8. What does the wrist sensor add that pose can't see?**
The camera can't see the forearm roll behind a rolled wrist, so a phone strapped to the forearm measures it with its gyro, synced to the video by two taps and the impact spikes, and feeds the coach's rolled-wrist rule. It also adds the forearm's spin to the racket-speed estimate and fills in wrist and elbow positions the camera lost behind the body. It's been tried on mock data and one real shadow session without a ball, and the rolled-wrist threshold still comes from mock swings.

## Sponsors' tech

**9. What did the Adaption fine-tune do, and does the coach use it?**
We built a generator that injects one fault of known size into our real swings and re-measures them, then fine-tuned Qwen3.5-2B on that **SIMULATED** data with Adaption's AutoScientist. It scored a 66% win rate against the base model on Adaption's own eval, below its 70% target; that's Adaption's measure, not accuracy on our held-out swings. The live coach doesn't use it yet.

**10. Where does Claude come in, and how do you stop it inventing things?**
Measuring and choosing the fix are plain code. Claude Opus 5.5 only rewords the coach's fault, cue and tip into one spoken sentence for the **Hear the coach** button, and never sees the raw metrics. A code checker rejects, and replaces with the coach's own cue, any sentence that:
- uses a number the code didn't measure, or changes its sign or unit;
- spells a number out;
- adds a negation;
- uses the opposite direction word.

**11. What does ElevenLabs do, and what if there's no network?**
ElevenLabs (`eleven_turbo_v2_5`) reads that sentence aloud server-side, on swings you upload, so the key never reaches the browser. Without keys, without a network, or after a 12 s timeout, the caption still shows the coach's plain cue, with no audio and no error. A clip that worked is cached per swing, so it replays offline.

**12. How did Figma shape the design?**
The Figma file came first:
- #71 built the landing page and `/demo` from its landing frames;
- #76 built the upload page and the shared header from its upload frame;
- #82 built the swing view from its two Results frames.

The data, the coach's wording and the PREDICTED labels didn't change, only the design. The file's case-study page shows the flow, the components and tokens, and before-and-after screens.

## Limits

**13. What happens to my video and data?**
The pipeline runs on our laptop: the browser sends the clip through the web app's same-origin proxy to a local Python service, which processes it in a temporary folder and keeps only the skeleton, the coach's call and the comparison, not the video. All that leaves the machine is the coach's fault, cue and tip sent to Claude, and the one sentence sent to ElevenLabs, on uploaded swings when the keys are set. Videos and sensor recordings are never committed to the repo.

**14. What fails today?**
A clip without one fully tracked swing is rejected ("keep the whole body in frame and film one clear swing"), and stripped slow-motion metadata can need the speed set by hand. Racket speed is estimated from the wrist and is far off on some real backhands; the launch angle is assumed; and one-camera depth is estimated. Only one clip processes at a time, and the coach is tuned on a small labelled set.

**15. What's next?**
Racket tracking with two strips of coloured tape, so racket speed, face angle and launch angle become measured, then a watch app instead of the strapped-on phone. After that: the retest loop (swing again and see how much of the gap to your ghost you closed), the rolled-wrist rule retuned on real swings, and more labelled swings so every rule is tuned on data.

## Sponsors: exactly how we used them

- **Anthropic:** Claude Opus 5.5 rewords the coach's chosen fix into one spoken sentence (structured outputs, checked by code before it's spoken), and we built Ghost with Claude Code under a shared `CLAUDE.md`.
- **ElevenLabs:** `eleven_turbo_v2_5` speaks that sentence server-side for the **Hear the coach** button on uploaded swings, cached per swing.
- **Figma:** Henoch designed the landing page, upload page and swing view in Figma, and #71, #76 and #82 built them from those frames.
- **Adaption:** we fine-tuned Qwen3.5-2B with AutoScientist on our SIMULATED fault-injection data (66% win rate against the base model on Adaption's own eval, below its 70% target), and the live coach doesn't use it yet.
