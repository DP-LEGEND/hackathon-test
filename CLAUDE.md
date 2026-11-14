# Claude Code instructions

Follow the team rules in AGENTS.md (shared with Codex):

@AGENTS.md

For UI work also follow UI_WORKFLOW.md. Contracts between pieces live in docs/interfaces.md. TEAM.md has the git steps and starter prompts.

## What we're building: Ghost

The product is decided, so this overrides "product undecided" in AGENTS.md. The Pulse dashboard and `/ui-lab` are still starter demo content.

**Ghost shows you a squash swing you haven't played yet.** A phone films one swing in slow motion. We turn it into a 3D skeleton, a Claude coach names the one fix that matters, and a translucent "ghost" of the player makes that fix beside them, with the predicted ball path for both swings on a 3D court. The player swings again and the coach re-measures.

Hard rules for the product:
- **Code measures, Claude explains and decides.** Claude never guesses an angle or speed. It only quotes numbers the code computed.
- Ball paths are always labelled **PREDICTED**. There is no real ball in the demo.
- Mock or simulated data is labelled as mock on screen.
- Colours: orange `#FF8A3D` = what the player did, cyan `#5BE7F0` = the ghost or the fix.

## Who owns what

Only edit the folders that belong to the person you're helping. If you don't know their role, ask once at the start. If a task needs another person's folder, stop and tell them who to ask.

| Folder | Owner | What lives there |
|---|---|---|
| `services/pipeline/` | Dev | Clip in, MediaPipe pose plus racket tape tracking, skeleton JSON out. Local API server. |
| `services/physics/` | aryan | Metrics, fault library, ghost skeleton edits, predicted ball flight. Pure Python functions with pytest tests. |
| `services/coach/` | aryan and Dev | Claude coach with tools (`get_metrics`, `apply_fix`, `simulate`, `compare_swings`) and the retest loop. |
| `app/ghost/`, `components/ghost/` | Sammy | The web demo: 3D replay, ghost overlay, court with two ball paths, captions. |
| `app/api/` (Ghost routes) | Dev | Next.js routes that call the Python service. |
| `demo/`, `data/labels/`, `lib/integrations/voice/` | Henoch | Test clips and labels, demo script, pitch, ElevenLabs voice, backup video. |
| `lib/ghost/types.ts`, `docs/interfaces.md` | Whole team | Data contracts. Change only after the team agrees. |
| Shared files (`package.json`, lockfile, `app/layout.tsx`, `app/globals.css`, `components/ui/`, config, this file) | Dev only | Ask Dev in the team chat. |

## How to run things

Web app (Node.js 26). Mac uses `npm`, Windows PowerShell uses `npm.cmd`:

```
npm ci            # Windows: npm.cmd ci
npm run dev       # Windows: npm.cmd run dev
```

Open http://localhost:3000/ghost

Python (3.11 or 3.12), always from inside `services/`. First time only:

```
cd services
python3 -m venv .venv                 # Windows: py -3.12 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If Windows blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

After that, activate the environment in each new terminal, then:

```
python -m uvicorn pipeline.server:app --reload --port 8000   # local service, check http://localhost:8000/health
python -m pipeline.run ../data/raw/<clip>.mov                 # one clip to skeleton JSON
python -m pytest                                              # Python tests
```

Checks before every pull request: `npm run lint` for any web change, `npm run build` for changes to types or pages, and `python -m pytest` for any Python change. Report which checks you actually ran.

Secrets: API keys live only in `.env.local` at the repo root (see `.env.example`). Never read, print or commit it, and never hard-code a key. Videos go in `data/raw/`, which is git-ignored; never commit clips or model weights.

## How to work with this team

Most of the team is new to Claude Code and some are new to coding, so act as their coordinator:
- Speak plainly. One step at a time, and put each terminal command in its own code block, with the Windows version when it differs.
- Before writing code, run `git status` and `git branch --show-current`. If they are on `main`, help them create a branch first: `feat/<area>-<thing>`, e.g. `feat/physics-ball`.
- For anything bigger than a small fix, give a short plan and wait for their OK.
- Keep changes small. Suggest a commit and a pull request every 1 to 2 hours, or whenever something works.
- When they ask, commit and push to their own branch, and give them the link to open a pull request: https://github.com/DP-LEGEND/hackathon-test/compare/main...BRANCH. Never push to `main`. Dev is the only person who merges.
- When they ask "what next?", read TEAM.md's timeline and their folder, then suggest the single next step that moves their part towards the next gate.
- When you finish a task, say what changed, how to try it, and which checks you ran.

Key times on Saturday: contracts agreed 11:00, idea locked 12:00, fault injector ready 13:00, **kill gate 14:00** (a real clip in, a rotating 3D skeleton out), ugly end-to-end 18:00. Sunday: core complete 01:00, feature freeze and backup video 10:00.
