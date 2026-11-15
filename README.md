# Imperial AI Hackathon (14–15 Nov 2026)

**Team: follow [WORKFLOW.md](WORKFLOW.md)** for the exact steps (start a task, test, PR, merge, after a merge). Roles and prompts are in [TEAM.md](TEAM.md).

Team repo for the Imperial AI Hackathon. Our product is **Ghost**: film one squash swing, and Ghost finds the one fix that matters and shows a ghost of you making it, with the PREDICTED ball path for both swings. The Devpost write-up is in [docs/devpost.md](docs/devpost.md); product rules and folder ownership are in [CLAUDE.md](CLAUDE.md).

## Team and roles
| Who | GitHub | Owns |
|---|---|---|
| Dev | DP-LEGEND | Pipeline, infra and live clips (`services/pipeline/`, Ghost API routes) |
| Sammy | jeffrey-sammy | Ghost UI and upload page (`app/ghost/`) |
| Henoch | 5quiwyrm | Coach thresholds, voice and the wrist sensor |
| aryan | Programmer-123 | Physics engine and court frame (`services/physics/`) |

## Run Ghost locally

Ghost has two parts: a Python API (`services/`, FastAPI on port 8000) and the Next.js web app (port 3000). The web app also works on its own: without the API, `/ghost` falls back to the saved sample swings in `public/swings/`.

### You need

- **Node.js 26**
- **Python 3.11 or 3.12** (MediaPipe may not have wheels for newer versions yet)
- **ffmpeg and ffprobe** on your PATH, to process new clips. Mac: `brew install ffmpeg`. Windows: `winget install Gyan.FFmpeg`, then open a new terminal.
- **The MediaPipe pose model**, to process new clips (step 3)

### 1. Install the web app

```
npm ci
```

Windows PowerShell: `npm.cmd ci`

### 2. Install the Python service (first time only)

Mac:
```
cd services
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:
```
cd services
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If Windows blocks the activate script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. In every new terminal, activate the environment again before running Python.

### 3. Download the pose model (only needed for new clips)

Mac:
```
mkdir -p ~/ghost-models
curl -L -o ~/ghost-models/pose_landmarker_heavy.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
```

Windows PowerShell:
```
New-Item -ItemType Directory -Force "$HOME\ghost-models"
curl.exe -L -o "$HOME\ghost-models\pose_landmarker_heavy.task" https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
```

To keep the model somewhere else, set `GHOST_POSE_MODEL` to its path.

### 4. API keys (optional)

The live flow (the API, `/ghost` and new clips) needs no keys: coaching, the ghost and the ball paths are all plain code. With keys, the live `/ghost` caption has a **Hear the coach** button: Claude rewords the coach's cue (`ANTHROPIC_API_KEY`), a checker rejects any number the code didn't measure, and ElevenLabs speaks it (`ELEVENLABS_API_KEY`). Without keys it falls back to the plain cue.

The same keys also run two command-line demos:

- `python -m coach.cue` has Claude word a cue from MOCK metrics
- `python -m coach.cue --speak` also reads it aloud with ElevenLabs

To use them, copy `.env.example` to `.env.local` at the repo root and fill in those keys, then restart the service and reload `/ghost`. Never commit `.env.local`.

### 5. Start the API

From inside `services/`, with the environment active:

```
python -m uvicorn pipeline.server:app --reload --port 8000
```

Check http://localhost:8000/health shows `{"ok":true}`.

### 6. Start the web app

In a second terminal, from the repo root:

```
npm run dev
```

Windows PowerShell: `npm.cmd run dev`

Open http://localhost:3000/ghost. The page reaches the API through its own `/api` route, so the browser never calls port 8000 directly. To point it at another API, set `GHOST_API_URL` in `.env.local`.

### 7. Try your own swing

Film one swing on a phone (slow motion is detected automatically). Then, from inside `services/`:

```
python -m pipeline /path/to/clip.mov
```

Or send it to the running API (Windows: `curl.exe`):

```
curl -F "file=@clip.mov" http://localhost:8000/process
```

Each accepted swing is saved under `data/processed/` (or `GHOST_SWINGS_DIR`) with the coach's call and the ghost comparison. Refresh `/ghost` to pick it. Add `--slowdown 4`, `--hand L` or `--stroke backhand` to override the automatic detection. If ffmpeg isn't on your PATH, set `GHOST_FFMPEG` and `GHOST_FFPROBE` to the two programs. More detail: [services/pipeline/README.md](services/pipeline/README.md).

Never commit clips or model files. Put videos in `data/raw/`, which git ignores.

### 8. Checks

```
bash scripts/check.sh
```

Windows: `powershell -ExecutionPolicy Bypass -File scripts\check.ps1`. This runs lint, the production build, the Python tests and the sample swing check. Stop `npm run dev` first, because the build uses the same folder.

## Before Saturday (setup only, no product code)
- [ ] Accept the GitHub invite and clone the repo
- [ ] `npm ci` then `npm run dev`, check http://localhost:3000 loads (Node.js 26, see section 2 below)
- [ ] Install the recommended VS Code extensions
- [ ] Claim Adaption credits (link in the hackathon page announcements) and start Figma for Education verification
- [ ] Put your own keys in `.env.local` (never committed). Never paste keys in WhatsApp, Discord or a commit
- [ ] Draft `PRODUCT_BRIEF.md` for the top two ideas so Saturday starts fast

## Safety rules for humans and agents
Read `docs/COLLABORATION.md` before running any AI agent. Short version: one agent per folder (use `git worktree` for a second), nobody pushes to `main`, only the repo owner merges and installs packages, and agents never run destructive git commands.

## Saturday timeline
- 09:00 check-in, everyone there by 10:00 (after 12:00 = disqualified)
- After sponsor briefs: pick the idea, finish `PRODUCT_BRIEF.md`
- +1 h: agree the contracts between pieces in `docs/interfaces.md`
- 15:00: ugly end-to-end version working, then improve
- 21:00 venue closes, no overnight. Sunday: polish, rehearse, demo

---

# Starter guide (from DP-LEGEND/hackathon-test)

A reusable, production-oriented Next.js starter designed for rapid AI product development at hackathons.

Built for a four-person team working collaboratively with Codex or Claude Code, GitHub, and Vercel.

**Goal:** Go from sponsor announcement to a polished, functional MVP as quickly as possible.

## 1. Technology Stack

| Category | Technology |
|---|---|
| Framework | Next.js 16 — App Router |
| Frontend | React 19, TypeScript |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui, Base UI, Nova preset |
| Icons | Lucide React |
| AI Development | OpenAI Codex |
| Version Control | Git and GitHub |
| Deployment | Vercel |
| CI | GitHub Actions |

The starter includes a responsive application shell, reusable components, UI state patterns, an example API route, and an API request helper.

It does not include a working AI provider, database, or authentication system. These are configured according to the chosen product.

## 2. Starting a New Hackathon Project

### Get the repository

Accept the GitHub invite, then clone the repository:

`git clone https://github.com/DP-LEGEND/hackathon-test.git`

Open the folder in VS Code and install the recommended extensions when prompted.

### Install dependencies

Run `npm ci` from the project root.

Use Node.js 26 to match the existing CI configuration.

Start the development server with `npm run dev`.

Open `http://localhost:3000`.

On Windows PowerShell, use `npm.cmd` if PowerShell blocks npm scripts.

### Define the product

1. Copy `PRODUCT_BRIEF.template.md` to `PRODUCT_BRIEF.md`.
2. Complete the product brief with your team.
3. Agree on the core demo journey, MVP scope, technical ownership, and initial design direction.
4. Open Codex or Claude Code in VS Code.
5. Prompt it: **"Read HACKATHON_START_PROMPT.md and begin."**

Codex reads `AGENTS.md` directly; Claude Code reads `CLAUDE.md`, which points to `AGENTS.md`. Both should follow `UI_WORKFLOW.md` for UI work.

## 3. Repository Structure

| Path | Purpose |
|---|---|
| `AGENTS.md` | Project-wide coding and Codex instructions |
| `UI_WORKFLOW.md` | UI/UX design and implementation methodology |
| `PRODUCT_BRIEF.template.md` | Product planning template |
| `HACKATHON_START_PROMPT.md` | Master Codex execution prompt |
| `app/` | Next.js pages, layouts, and routes |
| `app/api/` | Server-side API routes |
| `components/layout/` | Application shell and navigation |
| `components/shared/` | Reusable loading, empty, and error states |
| `components/ui/` | shadcn/Base UI components |
| `lib/api/` | Frontend API request helpers |
| `lib/integrations/` | External AI and sponsor-service integrations |
| `.env.example` | Environment variable template |
| `.github/workflows/ci.yml` | Automated validation |

## 4. Development Commands

| Command | Purpose |
|---|---|
| `npm ci` | Install dependencies from the lockfile |
| `npm run dev` | Start local development |
| `npm run lint` | Run ESLint |
| `npm run build` | Verify a production build |
| `npm run start` | Serve the production build |
| `npm audit` | Inspect dependency advisories |

Run lint and build before requesting a merge.

Do not introduce breaking dependency upgrades without coordinating with the team.

## 5. Team Git Workflow

Use short-lived feature branches instead of developing directly on `main`.

Recommended branch naming:

- `feat/frontend-dashboard`
- `feat/ai-agent`
- `feat/backend-api`
- `feat/integration`
- `fix/mobile-navigation`
- `docs/readme`

For each feature:

1. Switch to `main` and pull the latest changes.
2. Create a new feature branch.
3. Implement and validate your work.
4. Commit your changes with a meaningful message.
5. Push the branch to GitHub.
6. Open a pull request targeting `main`.
7. Wait for CI and any required review.
8. Merge once all required checks pass.

**Do not force-push to `main` or commit secrets.**

For urgent hackathon fixes, coordinate an accelerated review rather than silently bypassing safeguards.

## 6. Working with Codex

### Project-wide instructions

`AGENTS.md` defines the engineering rules, existing stack, architecture, security practices, and validation requirements.

### UI development

For substantial interface work, instruct Codex to read `UI_WORKFLOW.md`.

The workflow prioritises product-specific design, clear visual hierarchy, responsiveness, accessibility, and consistent components.

### Product development

Once the product brief is complete, use `HACKATHON_START_PROMPT.md` to guide the initial implementation.

### Important principles

- Inspect existing code before making changes.
- Prefer reusable components and existing dependencies.
- Build the shortest complete user journey first.
- Keep API contracts explicit and typed.
- Avoid unnecessary shared-file modifications.
- Validate changes rather than assuming generated code works.
- Review important Codex changes before committing.

## 7. APIs and External Integrations

Place Next.js API route handlers in `app/api/`.

Place external provider logic in `lib/integrations/`.

Use the existing `lib/api/client.ts` helper for supported frontend POST requests.

The `POST /api/example` endpoint is a demonstration route that echoes supplied input. It is not a production AI integration.

When implementing real integrations:

- Validate incoming data.
- Keep credentials on the server.
- Handle upstream errors and timeouts.
- Provide typed request and response contracts.
- Communicate expected contracts to teammates.
- Never present mocked outputs as real AI results.

## 8. Environment Variables and Security

Copy `.env.example` to `.env.local` and populate only the variables required by the product.

**Never commit `.env.local`, credentials, access tokens, or private API keys.**

Variables prefixed with `NEXT_PUBLIC_` can be included in the client-side bundle. Do not store secrets in them.

Configure production credentials separately through Vercel environment settings.

Never hardcode real credentials into prompts, screenshots, or committed source files.

## 9. Deployment

Use Vercel to deploy the application.

For each new project:

1. Create the new repository from this template.
2. Connect that repository to a new Vercel project.
3. Configure the required environment variables.
4. Deploy the application.
5. Verify the live production URL.
6. Use preview deployments to review pull requests.

**Important:** Creating a repository from this template does not automatically copy the original project's Vercel connection, collaborators, repository secrets, or branch protection settings. Configure these for the new repository.

## 10. Continuous Integration

GitHub Actions runs the `validate` job for pull requests targeting `main` and pushes to `main`.

It verifies:

- Dependency installation with `npm ci`
- ESLint with `npm run lint`
- Production compilation and TypeScript checking with `npm run build`

The new hackathon repository should require the `validate` check before merging when GitHub ruleset support is available.

The starter does not currently define a separate automated test suite.

## 11. Hackathon-Day Priorities

**Phase 1 — Define**

Choose the track, agree on the problem, write the product brief, establish the demo journey, and divide responsibilities.

**Phase 2 — Build**

Implement one complete functional path through the product. Connect the necessary AI and external services.

**Phase 3 — Integrate**

Merge working components frequently, validate API contracts, and verify deployments.

**Phase 4 — Polish**

Improve interface quality, responsiveness, loading/error states, and the user experience.

**Phase 5 — Demonstrate**

Rehearse the exact judge-facing journey, verify the deployed application, and maintain a fallback demo plan.

## 12. Definition of Done

A feature is ready to merge when:

- [ ] It performs the intended task.
- [ ] Relevant input and error handling work.
- [ ] TypeScript and lint checks pass.
- [ ] The production build passes.
- [ ] Responsive behaviour is acceptable.
- [ ] No secrets or unrelated changes are committed.
- [ ] The pull request clearly explains the change.
- [ ] Required CI checks and reviews pass.

A working, understandable demonstration is more valuable than numerous unfinished features.

---

**Build fast. Integrate early. Keep the demo working.**