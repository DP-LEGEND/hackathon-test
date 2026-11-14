"""Local API server the web app calls. Owner: Dev.

Run (from services/):  python -m uvicorn pipeline.server:app --reload --port 8000
Then open http://localhost:8000/health

Endpoints to add once the contract is agreed (docs/interfaces.md):
- POST /swing    upload a clip, return skeleton + metrics
- POST /coach    run the coach on a swing, return one fix + ghost + ball paths
"""

from fastapi import FastAPI

app = FastAPI(title="Ghost local service")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
