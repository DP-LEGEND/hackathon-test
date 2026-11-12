# Optional Python services

Only if the product needs Python (for example computer vision, physics or data processing that is easier in Python than in the browser).

- One folder per service, e.g. `services/<name>/`, with its own `requirements.txt`.
- Expose a small HTTP API (e.g. FastAPI) whose request and response shapes are written in `docs/interfaces.md`.
- The Next.js app calls it from a server route in `app/api/`, never directly from the browser with secrets.
