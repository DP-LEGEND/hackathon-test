"""Local, read-only swing catalogue and measured physics comparison API.

Run from repo root: python -m uvicorn pipeline.server:app --app-dir services --port 8000
GHOST_SWINGS_DIR points to a session or a directory of session folders.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
import uuid
import threading
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from coach import ask_agent
from coach.agent import coach_swing
from coach.live_voice import voice_for_swing
from physics.compare import GuessedFixError, compare
from physics.ghost import FIXES
from pipeline.live import LiveOptions, process_live_clip, ghost_choice

MAX_UPLOAD_BYTES = 250 * 1024 * 1024
PROCESS_SEMAPHORE = threading.Semaphore(1)


class ProcessUploadGuard:
    """Reject oversized declared bodies before FastAPI parses multipart data."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope['type'] != 'http' or scope.get('method') != 'POST'
                or scope.get('path', '').rstrip('/') != '/process'):
            await self.app(scope, receive, send)
            return
        try:
            lengths = [int(value) for key, value in scope.get('headers', []) if key.lower() == b'content-length']
            if any(length < 0 for length in lengths):
                raise ValueError('Negative length')
        except ValueError:
            await JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)(scope, receive, send)
            return
        if any(length > MAX_UPLOAD_BYTES for length in lengths):
            await JSONResponse({'detail': 'Video exceeds the 250 MB upload limit'}, status_code=413)(scope, receive, send)
            return
        await self.app(scope, receive, send)


app = FastAPI(title="Ghost local service")
app.add_middleware(ProcessUploadGuard)
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
    manifests = ([root / "manifest.json"] if (root / "manifest.json").is_file() else []) + sorted(root.glob("*/manifest.json"))
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
        {"id": identifier, "label": labels.get((entries[identifier].parent.name, entries[identifier].stem))}
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
    except GuessedFixError as exc:
        # The fix would edit a guessed joint: return the unchanged comparison (amount 0) for
        # the same fix id, marked noCorrection, with the reason, so the page still loads.
        try:
            unchanged = compare(swing, request.fix, 0.0, fps_real=swing.get("fpsReal"))
        except (ValueError, KeyError, IndexError, TypeError):
            raise HTTPException(422, str(exc)) from None
        unchanged["noCorrection"] = True
        unchanged["ghostNote"] = str(exc)
        return unchanged
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(422, "Swing cannot be compared with this fix") from None


LABELS = {"good", "early_wrist", "over_rotation", "straight_arm", "open_stance", "rolled_wrist"}


def read_labels() -> dict[tuple[str, str], str | None]:
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
                run = (row.get("pipeline_run") or "").strip()
                if "@" in identifier:
                    identifier, suffix_run = identifier.rsplit("@", 1)
                    if run and run != suffix_run:
                        raise ValueError("Label run conflicts with swing suffix")
                    run = suffix_run
                if not run:
                    continue  # An unscoped swing ID cannot safely label a run.
                key = (run, identifier)
                label = row["intended_fault"].strip()
                label = "good" if label == "none" else label
                if key in labels:
                    raise ValueError("Duplicate run/swing label")
                labels[key] = label if label in LABELS else None
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
    side = (swing.get("metadata") or {}).get("stroke") or swing.get("stroke") or swing.get("side")
    stroke = side if side in ("forehand", "backhand") else None
    try:
        # coach_swing measures, calls detect_faults, and selects its top fault.
        result = coach_swing(swing, stroke=stroke, fps_real=swing.get("fpsReal"))
    except (ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(422, "Swing cannot be measured for coaching") from None
    # Unsupported edits must not be presented as actionable ghost fixes.
    fix, amount = ghost_choice(result)
    return {**result, "fix": fix, "amount": amount,
            "ghost_ready": fix is not None, "contactFrame": swing["contactFrame"],
            "contactMethod": swing.get("metadata", {}).get("contactMethod", "provided-contact-estimate")}


@app.get("/coach/agent")
def coach_agent() -> dict:
    """Whether "Ask the coach" is configured (coach/ask_agent.py). Never returns a key or id."""
    return {"available": ask_agent.configured()}


@app.post("/coach/agent/session")
def coach_agent_session() -> dict:
    """A short-lived signed URL for one "Ask the coach" conversation; the key stays here."""
    if not ask_agent.configured():
        raise HTTPException(404, "Ask the coach is not configured")
    try:
        return {"signedUrl": ask_agent.signed_url()}
    except ask_agent.AgentError as exc:
        raise HTTPException(502, str(exc)) from None


@app.get("/coach/{identifier}/voice")
def coach_voice(identifier: str) -> dict:
    """{cue, audioUrl, source} for /coach's result (coach/live_voice.py); missing keys never error."""
    return dict(voice_for_swing(identifier, coach(identifier)))


@app.post("/process", status_code=201)
def process_video(
    file: Annotated[UploadFile, File(description="One local MOV, MP4, AVI or M4V clip")],
    slowdown: Annotated[float | None, Form(gt=0, le=16, allow_inf_nan=False)] = None,
    hand: Annotated[Literal["R", "L", "auto"] | None, Form()] = None,
    stroke: Annotated[Literal["forehand", "backhand", "auto"] | None, Form()] = None,
) -> dict:
    """Blocking worker-thread job; publish only after pose, coach and ghost succeed."""
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.mov', '.mp4', '.m4v', '.avi'):
        raise HTTPException(422, 'Upload a MOV, MP4, M4V or AVI video')
    root = Path(os.environ.get('GHOST_SWINGS_DIR', str(
        Path(__file__).resolve().parents[2] / 'data' / 'processed'))).resolve()
    options = LiveOptions(slowdown=slowdown, hand=None if hand == 'auto' else hand,
                          stroke=None if stroke == 'auto' else stroke,
                          model_path=os.environ.get('GHOST_POSE_MODEL', LiveOptions.model_path))
    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='ghost-upload-') as temporary:
            upload = Path(temporary) / f'clip{suffix}'
            size = 0
            with upload.open('wb') as stream:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, 'Video exceeds the 250 MB upload limit')
                    stream.write(chunk)
            if not size:
                raise HTTPException(422, 'Video upload is empty')
            # A client still sending its body must never reserve the job slot.
            # Admit only complete, size-checked uploads to expensive processing.
            if not PROCESS_SEMAPHORE.acquire(blocking=False):
                raise HTTPException(429, 'A clip is already processing')
            try:
                return process_live_clip(upload, root / f'live-{uuid.uuid4().hex}', options)
            finally:
                PROCESS_SEMAPHORE.release()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except RuntimeError:
        raise HTTPException(503, 'Live pipeline unavailable; configure the pose model and ffmpeg/ffprobe') from None
    except OSError:
        raise HTTPException(503, 'Live processing output is unavailable') from None
    finally:
        file.file.close()
