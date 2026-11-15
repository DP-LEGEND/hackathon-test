"""Speak the coach's cue with ElevenLabs. Owners: aryan and Dev.

Server-side only. The key comes from ELEVENLABS_API_KEY in .env.local and is
never printed. If speech fails, callers should still show the cue as a caption.
Uses only the standard library, so no new package is needed.
"""

from __future__ import annotations

import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from coach.env import require_env

try:
    import certifi  # installed with mediapipe; listed in requirements.txt
except ImportError:  # never let a missing CA package stop the server: fall back to the system store
    certifi = None

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
# ElevenLabs default voice "George". Works on the free plan; "library" voices (e.g. the
# old default "Rachel") return HTTP 402 for free accounts. Override with ELEVENLABS_VOICE_ID.
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MODEL_ID = "eleven_turbo_v2_5"  # low latency
TIMEOUT_S = 20


def _ssl_context() -> ssl.SSLContext:
    """TLS context for the ElevenLabs call, trusting certifi's CA bundle.

    The python.org macOS Python has no CA store until "Install Certificates.command" is run,
    so HTTPS fails certificate checks and the voice reports "Could not reach ElevenLabs".
    certifi's bundle works on every machine. Without certifi, use the system default.
    certifi is added on top of the default roots, so the system store and SSL_CERT_FILE still apply.
    """
    context = ssl.create_default_context()
    if certifi is not None:
        context.load_verify_locations(cafile=certifi.where())
    return context


class VoiceError(RuntimeError):
    """ElevenLabs could not produce audio."""


def _explain_http_error(exc: urllib.error.HTTPError) -> str:
    """Turn an ElevenLabs error into one plain sentence, using its own reason when given.

    The error body holds a status code and message, never the API key.
    """
    try:
        detail = json.loads(exc.read() or b"{}").get("detail")
    except (ValueError, AttributeError, OSError):
        detail = None
    reason, message = None, ""
    if isinstance(detail, dict):
        reason = detail.get("code") or detail.get("status")
        message = detail.get("message") or ""
    elif isinstance(detail, str):
        message = detail
    hints = {
        "paid_plan_required": " Pick a voice your plan allows and set ELEVENLABS_VOICE_ID in .env.local.",
        "quota_exceeded": " The account is out of characters this month.",
        "missing_permissions": " The key lacks text-to-speech permission; make a new key that has it.",
    }
    hint = hints.get(reason or "", " Check ELEVENLABS_API_KEY." if exc.code in (401, 403) else "")
    text = f"ElevenLabs returned HTTP {exc.code}"
    if reason:
        text += f" ({reason})"
    if message:
        text += f": {message}"
    if not text.endswith("."):
        text += "."
    return text + hint


def synthesize(text: str, timeout_s: float = TIMEOUT_S) -> bytes:
    """Return MP3 bytes for `text`. timeout_s: per-request socket timeout (live callers pass less)."""
    text = text.strip()
    if not text:
        raise VoiceError("Nothing to say: the cue is empty.")

    api_key = require_env("ELEVENLABS_API_KEY")  # also loads .env.local
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or DEFAULT_VOICE_ID

    request = urllib.request.Request(
        API_URL.format(voice_id=voice_id),
        data=json.dumps({"text": text, "model_id": MODEL_ID}).encode("utf-8"),
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s, context=_ssl_context()) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        raise VoiceError(_explain_http_error(exc)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise VoiceError("Could not reach ElevenLabs. Check the internet connection.") from exc

    if not audio:
        raise VoiceError("ElevenLabs returned empty audio.")
    return audio


def speak_cue(text: str, out_path: Optional[Path] = None) -> Path:
    """Synthesize `text` to an MP3 file and return its path (a temp file by default)."""
    audio = synthesize(text)
    if out_path is None:
        handle, name = tempfile.mkstemp(prefix="ghost-cue-", suffix=".mp3")
        os.close(handle)
        out_path = Path(name)
    out_path.write_bytes(audio)
    return out_path


def play(path: Path) -> None:
    """Best-effort local playback for testing (macOS afplay, or ffplay if installed)."""
    if sys.platform == "darwin" and shutil.which("afplay"):
        subprocess.run(["afplay", str(path)], check=False)
    elif shutil.which("ffplay"):
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)], check=False)
    else:
        print(f"No audio player found. Open {path} to listen.")
