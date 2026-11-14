"""Local, read-only swing catalogue and measured physics comparison API.

Run from services/: python -m uvicorn pipeline.server:app --port 8000
GHOST_SWINGS_DIR points to a session or a directory of session folders.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from physics.compare import compare
from physics.ghost import FIXES

app = FastAPI(title="Ghost local service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("GHOST_WEB_ORIGIN", "http://localhost:3000")],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fix: str
    amount: float = Field(allow_inf_nan=False, ge=-1000, le=1000)


def catalogue() -> dict[str, Path]:
    root = Path(os.environ.get("GHOST_SWINGS_DIR", "../data/processed")).resolve()
    if not root.is_dir():
        return {}
    entries: dict[str, Path] = {}
    manifests = ([root / "manifest.json"] if (root / "manifest.json").is_file()
                 else sorted(root.glob("*/manifest.json")))
    try:
        for manifest in manifests:
            if not manifest.resolve().is_relative_to(root):
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("files"), list):
                raise ValueError("Invalid manifest")
            for name in data["files"]:
                if not isinstance(name, str) or Path(name).name != name or not name.endswith(".json"):
                    raise ValueError("Invalid manifest entry")
                path = (manifest.parent / name).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise ValueError("Unavailable swing file")
                identifier = path.stem
                if identifier in entries:
                    raise ValueError("Duplicate swing id")
                entries[identifier] = path
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Swing catalogue is invalid or unavailable") from None
    return entries


def load_swing(identifier: str) -> dict:
    path = catalogue().get(identifier)
    if path is None:
        raise HTTPException(404, "Unknown swing id")
    try:
        swing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(swing, dict) or swing.get("id") != identifier or not swing.get("frames"):
            raise ValueError("Invalid swing")
        return swing
    except (OSError, ValueError):
        raise HTTPException(503, "Swing data is invalid or unavailable") from None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/swings")
def list_swings() -> dict:
    return {"swings": [{"id": identifier} for identifier in sorted(catalogue())]}


@app.get("/swings/{identifier}")
def get_swing(identifier: str) -> dict:
    return load_swing(identifier)


@app.post("/swings/{identifier}/ghost")
def compare_swing(identifier: str, request: CompareRequest) -> dict:
    swing = load_swing(identifier)
    if request.fix not in FIXES:
        raise HTTPException(422, {"error": "Unknown fix", "fixes": sorted(FIXES)})
    try:
        return compare(swing, request.fix, request.amount)
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(422, "Swing cannot be compared with this fix") from None
