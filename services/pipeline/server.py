"""Local, read-only swing catalogue and measured physics comparison API.

Run from services/: python -m uvicorn pipeline.server:app --port 8000
GHOST_SWINGS_DIR points to a session or a directory of session folders.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from coach.agent import coach_swing
from physics.compare import compare
from physics.ghost import FIXES

app = FastAPI(title="Ghost local service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list({"http://localhost:3000", os.environ.get("GHOST_WEB_ORIGIN", "http://localhost:3000")}),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fix: str
    amount: float = Field(allow_inf_nan=False, ge=-1000, le=1000)


def catalogue() -> dict[str, Path]:
    root = Path(os.environ.get("GHOST_SWINGS_DIR", str(
        Path(__file__).resolve().parents[2] / "data" / "processed"))).resolve()
    if not root.is_dir():
        return {}
    grouped: dict[str, list[Path]] = {}
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
                paths = grouped.setdefault(identifier, [])
                if path in paths:
                    raise ValueError("Duplicate manifest entry")
                paths.append(path)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Swing catalogue is invalid or unavailable") from None
    return {f"{identifier}@{path.parent.name}" if len(paths) > 1 else identifier: path
            for identifier, paths in grouped.items() for path in paths}


def load_swing(identifier: str) -> dict:
    path = catalogue().get(identifier)
    if path is None:
        raise HTTPException(404, "Unknown swing id")
    try:
        swing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(swing, dict) or swing.get("id") != path.stem or not swing.get("frames"):
            raise ValueError("Invalid swing")
        return {**swing, "id": identifier}
    except (OSError, ValueError):
        raise HTTPException(503, "Swing data is invalid or unavailable") from None


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/swings")
def list_swings() -> dict:
    entries = catalogue()
    labels = read_labels()
    return {"swings": [
        {"id": identifier, "label": labels.get(f"{identifier}@{entries[identifier].parent.name}",
                                               labels.get(identifier))}
        for identifier in sorted(entries)
    ]}


@app.get("/swings/{identifier}")
def get_swing(identifier: str) -> dict:
    return load_swing(identifier)


@app.post("/compare/{identifier}")
@app.post("/swings/{identifier}/ghost")
def compare_swing(identifier: str, request: CompareRequest) -> dict:
    swing = measurement_swing(identifier)
    if request.fix not in FIXES:
        raise HTTPException(422, {"error": "Unknown fix", "fixes": sorted(FIXES)})
    try:
        return compare(swing, request.fix, request.amount, fps_real=swing.get("fpsReal"))
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(422, "Swing cannot be compared with this fix") from None


LABELS = {"good", "early_wrist", "over_rotation", "straight_arm", "open_stance", "rolled_wrist"}


def read_labels() -> dict[str, str | None]:
    path = Path(os.environ.get("GHOST_LABELS_CSV", str(
        Path(__file__).resolve().parents[2] / "data" / "labels" / "labels.csv")))
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not {"swing", "intended_fault"}.issubset(reader.fieldnames or []):
                raise ValueError("Invalid label columns")
            labels = {}
            for row in reader:
                identifier = row["swing"].strip()
                label = row["intended_fault"].strip()
                label = "good" if label == "none" else label
                if identifier in labels:
                    raise ValueError("Duplicate label id")
                labels[identifier] = label if label in LABELS else None
            return labels
    except (OSError, ValueError, TypeError, AttributeError, csv.Error):
        raise HTTPException(503, "Swing labels are invalid or unavailable") from None


def measurement_swing(identifier: str) -> dict:
    swing = load_swing(identifier)
    contact = swing.get("contactFrame")
    # Never silently replace a sound-timed pipeline contact with a speed peak.
    if isinstance(contact, bool) or not isinstance(contact, int) or not 0 <= contact < len(swing["frames"]):
        raise HTTPException(422, "Swing needs a valid pipeline contactFrame for measurements")
    return swing


@app.post("/coach/{identifier}")
def coach(identifier: str) -> dict:
    swing = measurement_swing(identifier)
    side = swing.get("stroke") or swing.get("side")
    stroke = side if side in ("forehand", "backhand") else None
    try:
        # coach_swing measures, calls detect_faults, and selects its top fault.
        result = coach_swing(swing, stroke=stroke, fps_real=swing.get("fpsReal"))
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(422, "Swing cannot be measured for coaching") from None
    # Unsupported edits must not be presented as actionable ghost fixes.
    ready = result["ghost_ready"] and result["fix"] in FIXES
    return {**result, "fix": result["fix"] if ready else None,
            "amount": result["fix_amount"] if ready else None,
            "ghost_ready": ready, "contactFrame": swing["contactFrame"],
            "contactMethod": swing.get("metadata", {}).get("contactMethod", "provided-contact-estimate")}
