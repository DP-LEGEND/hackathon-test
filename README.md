# Ghost

**Film a squash swing, find one fix, and see a 3D ghost of yourself making it, with PREDICTED ball paths for both swings.**

## What it does

- Takes a phone video, or opens the saved forehand and backhand samples for a demo with no keys.
- Measures the swing and names a coaching priority, its fix, and what could not be checked.
- Replays your motion beside a corrected 3D ghost, then compares their **PREDICTED** ball paths on a squash court.
- Shows a short coaching cue, with optional Claude wording and ElevenLabs speech for live uploads.

## How it works

**Phone video → MediaPipe pose → physics ball model PREDICTS the ball path from body motion → coach names one fault and fix, optionally worded by Claude → 3D ghost of the corrected swing → optional ElevenLabs voice.**

Code measures the joints, estimates racket motion, ranks faults and selects the fix. **Claude optionally words that selected fault and fix**; it does not invent the measurements. The ghost edits the skeleton while preserving bone lengths, then the same physics code measures the corrected swing. Without provider keys, the live pipeline keeps its deterministic coaching cue. Saved samples use committed results and make no provider calls.

An **optional wrist IMU workflow** uses a phone strapped to the forearm to add roll measurements and sensor-assisted estimates. It is a separate workflow, not a requirement for video uploads or the saved demo; see [the wrist sensor guide](services/wrist/README.md).

## Honest limits

- **Ball paths are PREDICTED, not tracked.** The displayed paths come from body motion, estimated racket motion and model assumptions. Single-camera depth is estimated, and launch angle is assumed.
- **Real-ball reference check:** on the forehand clip, the front-wall height was **1.17 m tracked vs 1.45 m predicted**. Tracking was a separate offline check with court landmarks marked by hand. Launch angles were chosen using the same demo clips, so this is a reference check, not independent accuracy validation. See [the validation results](services/physics/validation/results/7178110a0b06-swing-0027.json).
- **Adaption is an experiment, not the live coach.** A Qwen3.5-2B fine-tune used **SIMULATED** fault-injection data and achieved a **66% win rate against its base model on Adaption's own evaluation**. That is not accuracy on our held-out swings, and the fine-tune is **not used by the live coach**. See [the Adaption write-up](docs/devpost.md#adaption).
- **The wrist sensor is optional and limited.** Its real-data thresholds come from one shadow-swing session without a ball. Forearm roll is measured; its conversion to racket-face angle and ball aim is **ASSUMED**.

## Built with

- **Next.js**: React/TypeScript web app and 3D replay with Three.js.
- **FastAPI**: local Python processing and coaching API.
- **MediaPipe**: pose landmarks from video.
- **Claude**: optional coaching language grounded in measured values.
- **ElevenLabs**: optional spoken coaching cues.
- **Figma**: interface designs, components and visual direction.
- **Adaption**: the separate fine-tuning experiment described above.

## Quick start: judge the saved demo

Install **Git and Node.js 26**, then run:

```sh
git clone https://github.com/DP-LEGEND/hackathon-test.git
cd hackathon-test
npm ci
npm run dev
```

On Windows PowerShell, use `npm.cmd ci` and `npm.cmd run dev`.

Open **http://localhost:3000**, then **Demo → Start with the demo swing**. Follow **Show the ghost → Show the court**, then try the saved backhand. The saved demo needs **no API keys, Python service, pose-model download or camera**. Dependencies must be installed first; fonts and saved sample assets are served locally.

For a fresh video, follow the full setup below and open **http://localhost:3000/upload**. The [demo runbook](docs/demo-runbook.md) covers the presentation flow; [docs/devpost.md](docs/devpost.md) gives the longer project write-up.

**Contributors:** follow [WORKFLOW.md](WORKFLOW.md). Product rules and ownership are in [CLAUDE.md](CLAUDE.md), with starter prompts in [TEAM.md](TEAM.md).

## Team and roles

| Who | GitHub | Owns |
|---|---|---|
| Dev | DP-LEGEND | Pipeline, infra and live clips (`services/pipeline/`, Ghost API routes) |
| Sammy | jeffrey-sammy | Ghost UI and upload page (`app/ghost/`) |
| Henoch | 5quiwyrm | Coach thresholds, voice and the wrist sensor |
| aryan | Programmer-123 | Physics engine and court frame (`services/physics/`) |

## Run Ghost locally

Ghost has two parts: a Python API (`services/`, FastAPI on port 8000) and the Next.js web app (port 3000). The web app also works on its own: without the API, `/demo` and `/ghost` use the saved sample swings in `public/swings/`. The API is needed for new uploads.

The Python service has **no authentication** and is **for local use only**. Run both the web app and service on the same laptop, with the service bound to localhost.

### You need

- **Node.js 26**
- **Python 3.11 or 3.12** (MediaPipe may not have wheels for newer versions yet)
- **ffmpeg and ffprobe** on your PATH, to process new clips. Mac: `brew install ffmpeg`. Windows: `winget install Gyan.FFmpeg`, then open a new terminal.
- **The MediaPipe pose model**, to process new clips (step 3)

### 1. Install the web app

From the cloned repository root:

```
npm ci
```

Windows PowerShell: `npm.cmd ci`

### 2. Install the Python service (first time only)

macOS / Linux (commands use Python 3.12):
```sh
cd services
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
source .venv/bin/activate
```

Windows PowerShell:
```powershell
cd services
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\Activate.ps1
```

In each new terminal, activate the environment before running the Python commands below. If PowerShell blocks activation, stay in `services/` and use `.\.venv\Scripts\python.exe` wherever a command says `python`; no execution-policy change is needed.

### 3. Download the pose model (only needed for new clips)

Mac:
```
mkdir -p ~/ghost-models
curl -fL -o ~/ghost-models/pose_landmarker_heavy.task https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
```

Windows PowerShell:
```
New-Item -ItemType Directory -Force "$HOME\ghost-models"
curl.exe -fL -o "$HOME\ghost-models\pose_landmarker_heavy.task" https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
```

To keep the model somewhere else, set `GHOST_POSE_MODEL` in the Python process environment before starting the service. Likewise, set `GHOST_FFMPEG`, `GHOST_FFPROBE` and `GHOST_SWINGS_DIR` there when overriding their defaults; the pipeline does not automatically load these settings from `.env.local`.

### 4. API keys (optional)

The live upload flow needs no provider keys: measurements, fault ranking, the ghost and ball paths run in code. For live swings, `ANTHROPIC_API_KEY` optionally lets Claude reword the selected cue, with numbers checked against the measured values. Independently, `ELEVENLABS_API_KEY` enables speech, including speech of the plain deterministic cue without Claude. **Hear the coach** appears only when audio is available. If Claude is unconfigured or fails, the caption shows the coach's plain cue; ElevenLabs can still speak that cue if available. If only ElevenLabs is unconfigured or fails, Claude's sentence stays in the caption and there is simply no audio. Saved samples never request these providers.

The same keys also run two command-line demos:

- `python -m coach.cue` has Claude word a cue from MOCK metrics
- `python -m coach.cue --speak` also reads it aloud with ElevenLabs

If enabling these optional providers, copy `.env.example` to `.env.local` at the repo root, configure the provider privately, then restart the service. The quick start needs no environment file. Never commit `.env.local` or paste credentials into documentation.

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

Open http://localhost:3000. Use `/demo` for saved swings and `/upload` for a new clip; `/ghost` remains the replay route. The web app reaches the service through its `/api` proxy, so the browser never calls port 8000 directly. Only override the server-side `GHOST_API_URL` for a different local service port on the same laptop, before starting Next.js (or in its `.env.local`).

### 7. Try your own swing

Film one swing on a phone and upload it at http://localhost:3000/upload. Auto reads available timing metadata and may infer slowdown; choose a known slowdown manually when needed. Metadata-stripped exports cannot always recover the real timing. A successful upload opens its result at `/ghost?swing=<id>`.

Alternatively, from inside `services/` with the Python environment active:

```
python -m pipeline /path/to/clip.mov
```

Or send it to the running API (Windows: `curl.exe`):

```
curl -F "file=@clip.mov" http://localhost:8000/process
```

Each accepted swing is saved under `data/processed/` (or `GHOST_SWINGS_DIR`) with the coach's call and the ghost comparison. After a CLI/API upload, refresh `/ghost` to pick it. Add `--slowdown 4`, `--hand L` or `--stroke backhand` to override the automatic detection. If ffmpeg isn't on your PATH, set `GHOST_FFMPEG` and `GHOST_FFPROBE` to the two programs. More detail: [services/pipeline/README.md](services/pipeline/README.md).

Never commit clips or model files. Put videos in `data/raw/`, which git ignores.

### 8. Checks

From the repository root:

```
bash scripts/check.sh
```

Windows: `powershell -ExecutionPolicy Bypass -File scripts\check.ps1`. This runs lint, the production build, Python tests, the sample swing contract check and a Python-service import check. It does not run the browser suite. Stop `npm run dev` first, because the build uses the same folder.

## Team setup checklist

- [ ] Accept the GitHub invite and clone the repo
- [ ] `npm ci` then `npm run dev`, check http://localhost:3000 loads (Node.js 26, see section 2 below)
- [ ] Install the recommended VS Code extensions
- [ ] Claim Adaption credits (link in the hackathon page announcements) and start Figma for Education verification
- [ ] Configure provider keys only if enabling optional services. Never paste keys in WhatsApp, Discord or a commit
- [ ] Read the Ghost product rules in [CLAUDE.md](CLAUDE.md) and the team workflow before changing product scope

## Safety rules for humans and agents
Read `docs/COLLABORATION.md` before running any AI agent. Short version: one agent per folder (use `git worktree` for a second), nobody pushes to `main`, only the repo owner merges and installs packages, and agents never run destructive git commands.

## Original hackathon timeline (historical)

- 09:00 check-in, everyone there by 10:00 (after 12:00 = disqualified)
- After sponsor briefs: pick the idea, finish `PRODUCT_BRIEF.md`
- +1 h: agree the contracts between pieces in `docs/interfaces.md`
- 15:00: ugly end-to-end version working, then improve
- 21:00 venue closes, no overnight. Sunday: polish, rehearse, demo

---

# Maintainer and starter reference

Ghost grew from a reusable Next.js hackathon starter. The reference below preserves its contributor and setup guidance; template-specific steps apply when creating a separate project, not when running Ghost.

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

Ghost adds the Python pipeline and optional Claude/ElevenLabs integrations described above. It does not require a database or authentication for the local demo.

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

### Define the product when reusing the starter

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
| `lib/integrations/` | Starter integration scaffolding |
| `services/pipeline/` | Video processing and FastAPI service |
| `services/physics/` | Measurements, ghost edits and PREDICTED ball paths |
| `services/coach/` | Fault ranking, optional Claude wording and ElevenLabs voice |
| `services/wrist/` | Optional forearm IMU workflow |
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
| `npm run test:ui` | Run the UI-lab browser suite against an existing server |
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
8. The repo owner merges once all required checks and reviews pass.

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

Ghost's provider logic lives in `services/coach/`; `lib/integrations/` retains the starter scaffolding.

The `lib/api/client.ts` helper sends JSON POST requests. Ghost's video upload uses the multipart transport in `app/upload/process-clip.ts` instead.

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

Keep optional Claude and ElevenLabs credentials on the local Python service. Run the web app and service on the same laptop; the service has no authentication and is for local use only.

Never hardcode real credentials into prompts, screenshots, or committed source files.

## 9. Deployment

The Python service has **no authentication** and is **for local use only**. For live uploads, run both the Next.js web app and Python service on the same laptop, with the service bound to localhost. Do not expose the Python service publicly or point a public Vercel deployment's `GHOST_API_URL` at it. Vercel can host the web app's saved sample demo without a connection to the Python service.

For a separate project created from the starter:

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
- UI-lab Playwright smoke tests with `npm run test:ui`, using Microsoft Edge and a dedicated production server

The new hackathon repository should require the `validate` check before merging when GitHub ruleset support is available.

The repository has Python tests under `services/` and browser checks described in [docs/BROWSER_TESTING.md](docs/BROWSER_TESTING.md). The CI browser suite covers `/ui-lab`; Ghost's local demo smoke check is `python scripts/demo_smoke.py` from the repo root with both servers running. Python tests are included in `scripts/check.sh` / `scripts/check.ps1`, not the current CI job.

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
