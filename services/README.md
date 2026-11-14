# Python services (Ghost)

One Python environment for everything in this folder. Run every command from inside `services/`.

| Folder | Owner | What it does |
|---|---|---|
| `pipeline/` | Dev | Slow-mo clip in, MediaPipe pose plus racket tape tracking, skeleton JSON out. Runs the local API server. |
| `physics/` | aryan | Metrics, fault library, ghost skeleton edits, predicted ball flight. Pure functions with tests. |
| `coach/` | aryan and Dev | The Claude coach: picks one fix from the metrics, calls the physics tools, runs the retest loop. |

Setup and run commands for Mac and Windows are in the root `CLAUDE.md`.

- The Next.js app talks to the server in `pipeline/server.py` (http://localhost:8000) through a route in `app/api/`, never with secrets in the browser.
- Request and response shapes are agreed in `docs/interfaces.md` (draft types in `lib/ghost/types.ts`).
- Clips go in `data/raw/` at the repo root. Videos are git-ignored, so never commit them.
