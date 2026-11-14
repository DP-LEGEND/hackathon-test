# Team playbook

Roles, the git loop, and prompts you can paste straight into Claude Code. Claude Code reads `CLAUDE.md` automatically, so it already knows the project and who owns which folder.

## Roles

Kickoff confirmed main track 02 (Voice, Vision & Generative Media), so the voice coach is in scope.

| Who | AI tool | Owns | First goal |
|---|---|---|---|
| **aryan** | Claude Max | `services/physics/`, `services/coach/` (with Dev) | Ball flight with tests, then the fault injector and Adaption data generator by 13:00 |
| **Sammy** (`jeffrey-sammy`) | Claude Max | `app/ghost/`, `components/ghost/` | A rotating 3D skeleton replay of mock data |
| **Dev** (`DP-LEGEND`) | ChatGPT Pro, Codex | `services/pipeline/`, Ghost API routes, merging PRs, installing packages | A real clip in, skeleton JSON out, by 13:00 |
| **Henoch** | Claude Pro | `demo/`, `data/labels/`, `lib/integrations/voice/` | Labelled test clips, the demo stand and the demo script |

**Using your plan well**
- **Dev:** Codex reads `AGENTS.md`, which points it to the same rules as `CLAUDE.md`. The prompts below work in Codex unchanged.
- **Henoch (Claude Pro has the tightest limits):** use `/model` to pick Sonnet for everyday work, run `/clear` between tasks, and keep prompts to one task each. If you hit a limit, ask aryan or Sammy to run a prompt for you.
- **aryan and Sammy (Claude Max):** you have the most headroom, so take on the heavy prompts and help others when they're blocked.

## The git loop (same on Mac and Windows)

Run these in a terminal inside the repo folder. Or just tell Claude Code "start a new branch called feat/physics-ball" and it will do it.

**1. Start a task:** get the latest `main` and make your own branch.

```
git checkout main
```
```
git pull
```
```
git checkout -b feat/physics-ball
```

**2. Work** with Claude Code (prompts below).

**3. Save and upload** when something works (every 1 to 2 hours):

```
git add -A
```
```
git commit -m "Add ball flight model"
```
```
git push -u origin feat/physics-ball
```

Or tell Claude Code: "Commit and push my work and give me the pull request link."

**4. Open a pull request:** open the link Claude gives you (or the yellow "Compare & pull request" button on GitHub), then post the link in the team chat.

**5. Dev merges.** Then go back to step 1 for your next task.

**Every hour**, pull other people's merged work into your branch: `git pull origin main`. If it says "conflict", stop and ask Claude Code: "Explain this merge conflict. Don't fix it yet." Never let it delete someone else's side.

## How to prompt Claude Code

Good prompts say four things: **who you are, the goal, what done looks like, and which folder to stay in.** Paste the full error message, not a summary. Ask for a plan first on anything big.

### First task prompts (paste one at kickoff)

**Dev: pipeline**
> I'm Dev, I own services/pipeline/. Goal: turn one slow-motion clip into skeleton JSON. Use the MediaPipe Pose Landmarker in VIDEO mode, one person, 33 world landmarks per frame, lightly smoothed, in the Swing shape from lib/ghost/types.ts. Wire it into `python -m pipeline.run <clip>` and a POST /swing endpoint in pipeline/server.py. Done when a clip from data/raw/ prints valid JSON. Only edit services/pipeline/. Give me a plan first, then help me set up the Python environment.

**Dev: packages for the 3D page (do this early, only Dev installs packages)**
> I'm Dev, the repo owner. Sammy needs three.js for the 3D replay. Check the installed Next.js and React versions, then tell me the exact npm install command for three, @react-three/fiber, @react-three/drei and @types/three that works with them. Don't run it until I say so.

**aryan: physics**
> I'm aryan, I own services/physics/. Goal: build predict_ball_path in physics/ball.py: racket-head speed and direction at contact go in, an effective-mass collision gives ball speed, then a projectile with quadratic drag flies onto a squash court (front wall 9.75 m). Put every constant at the top with its source. Done when pytest checks a straight drive hits the front wall at a sensible height. Only edit services/physics/. Plan first, and explain the maths in plain words.

**aryan: fault injector (needed by 13:00 for the Adaption fine-tune)**
> I'm aryan, in services/physics/. Goal: in physics/ghost.py, write functions that take a good swing and inject one fault of a known size (late contact by N cm, hip turn reduced by N degrees, wrist released N ms early), keeping bone lengths fixed. Then a script that turns a folder of good swings into a CSV of labelled synthetic swings. Adaption credits are unlimited, so aim for thousands of rows. Plan first.

**Sammy: 3D page**
> I'm Sammy, I own app/ghost/ and components/ghost/. Goal: make /ghost show a 3D stick-figure swing I can rotate with the mouse, playing from mock data. Make a mock Swing (lib/ghost/types.ts) in components/ghost/mock-swing.ts, clearly labelled as mock. Draw the player in orange (#FF8A3D) and a slightly shifted copy as the ghost in cyan (#5BE7F0), semi-transparent. If three.js isn't installed yet, start with the layout and the mock data and tell me what to ask Dev for. Only edit my folders. Plan first, then go step by step.

**Henoch: data and demo**
> I'm Henoch, I own demo/ and data/labels/. Goal: (1) help me turn our filming notes into a labels CSV in data/labels/ using the columns in data/labels/README.md, and (2) write demo/script.md, a 90-second judge demo: the judge swings, a 3D replay appears, the coach names one fix, the ghost swings beside them with two predicted ball paths, the judge swings again. Mark who says and does what. Only edit my folders.

### Second task prompts (after the 14:00 kill gate)

**aryan and Dev: coach**
> We own services/coach/. Goal: a Claude coach that gets the metrics and faults for a swing, picks ONE fix in coaching priority (contact and stance, then preparation, rotation, wrist), explains it using only the measured numbers, picks a drill, and calls apply_fix and simulate to get the ghost and both ball paths. The API key comes from .env.local through python-dotenv, never hard-coded. Plan the tool schemas first so we can add them to docs/interfaces.md.

**Sammy: court and ball paths**
> I'm Sammy. Add a 3D squash court to /ghost with two ball paths from mock data: orange for the player, cyan for the ghost, each with an amber "PREDICTED" badge. Add the coach's caption underneath. Only edit my folders.

**Henoch: voice**
> I'm Henoch. Goal: the coach's caption is read aloud with ElevenLabs. Add a small server-side client in lib/integrations/voice/ using ELEVENLABS_API_KEY from .env.local (never in the browser, never printed). Show me how to test it on one sentence. If it fails, the caption must still show. Plan first.

### Prompts for any time

**What should I do next?**
> Read CLAUDE.md, TEAM.md, git status and my folder. What's the single next step for my role to hit the next gate? Keep it short.

**I'm stuck on an error**
> I ran `<command>` and got this error: `<paste the whole error>`. Explain in plain words what it means, then fix it. Stay in my folder.

**Something used to work and now doesn't**
> `<thing>` worked before and now `<what happens instead>`. Check git log and git diff to find what changed, explain the cause, and fix it in the smallest way.

**Before opening a PR**
> Review my changes against main. Check I only touched my folders, nothing secret is committed, and lint/tests pass. Then commit, push and give me the PR link.

**I don't understand this code**
> Explain `<file>` to me like I'm new to coding: what it does, what goes in, what comes out. Don't change anything.

**Merge conflict**
> git says there's a merge conflict. Show me both sides of each conflict and explain what each person was trying to do. Don't resolve anything until I agree.

## Timeline

| When | Gate |
|---|---|
| Sat 10:00 to 10:30 | Kickoff. Decide Ghost or Kin (backup) |
| 11:00 | Agree the data shapes: copy `lib/ghost/types.ts` into `docs/interfaces.md` |
| 12:00 | Idea locked |
| 13:00 | Fault injector ready (aryan) |
| **14:00** | **Kill gate:** a real clip in, a rotating 3D skeleton out. If not, switch to Kin |
| 18:00 | Ugly end-to-end: swing, metrics, one fix, ghost and two ball paths |
| Sun 01:00 | Core complete |
| 10:00 | Feature freeze, backup video recorded |
| 18:00 | End |

## Never

- Push to `main`, or run `git push --force`, `git reset --hard` or `git clean`.
- Paste an API key into chat, code or a commit. Keys go only in your own `.env.local`.
- Commit video files. Clips live in `data/raw/`, which git ignores.
- Run two Claude Code sessions in the same folder at once.
