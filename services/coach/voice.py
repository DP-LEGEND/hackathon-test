"""Speak the coach's cue with ElevenLabs. Owners: aryan and Dev.

Server-side only. The key comes from ELEVENLABS_API_KEY in .env.local and is
never printed. If speech fails, callers should still show the cue as a caption.
Uses only the standard library, so no new package is needed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from coach.env import require_env

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs premade voice "Rachel"; override with ELEVENLABS_VOICE_ID
MODEL_ID = "eleven_turbo_v2_5"  # low latency
TIMEOUT_S = 20


class VoiceError(RuntimeError):
    """ElevenLabs could not produce audio."""


def synthesize(text: str) -> bytes:
    """Return MP3 bytes for `text`."""
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
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        hint = " Check ELEVENLABS_API_KEY." if exc.code in (401, 403) else ""
        raise VoiceError(f"ElevenLabs returned HTTP {exc.code}.{hint}") from exc
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
