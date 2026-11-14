"""The live coach voice: a Claude-worded cue and ElevenLabs audio for one coached swing.
Owners: aryan and Dev.

voice_for_swing(swing_id, result) takes the REAL coach result (what /coach/{id} returns,
from coach_swing) and returns {"cue", "audioUrl", "source"}:
- cue: one spoken sentence worded by Claude (needs ANTHROPIC_API_KEY), quoting only
  numbers the coach measured. Otherwise the plain coach caption, result["cue"].
- audioUrl: "data:audio/mpeg;base64,..." of ElevenLabs saying exactly `cue` (needs
  ELEVENLABS_API_KEY), else None. A data URL, so no second route serves files.
- source: "claude" or "caption", so the page can say who worded it.

Code measures, Claude explains: Claude gets only the coach's fault label, cue and tip,
never raw metrics, and any number it writes must already be in them, or we use the
caption instead.

Optional and safe: missing keys, API errors, refusals, timeouts or an invented number
never raise here; they fall back to the caption and/or audio None.

Cached so each swing calls each API at most once. Successes are kept in memory and on
disk (GHOST_VOICE_CACHE, default services/coach/.voice_cache/, which git-ignores itself),
keyed by swing id plus the coach facts, so a swing re-measured with different numbers
is worded afresh. A failed call is remembered until the server restarts, so a bad key
or a network outage isn't retried on every request.

Keys come only from .env.local (coach.env); nothing here prints them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

import anthropic
from pydantic import BaseModel, Field

from coach import voice
from coach.agent import NO_FAULT_CUE
from coach.avatar import _spoken
from coach.cue import MODEL, CoachError
from coach.env import load_env, require_env

log = logging.getLogger(__name__)

Source = Literal["claude", "caption"]

MAX_SPOKEN_WORDS = 20
CLAUDE_TIMEOUT_S = 20.0  # a live request: fail fast to the caption rather than hang
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / ".voice_cache"


class LiveVoice(TypedDict):
    cue: str
    audioUrl: Optional[str]
    source: Source


class WordedCue(BaseModel):
    cue: str = Field(description="One short spoken sentence the player can act on during the next swing")


SYSTEM_PROMPT = f"""You are a squash coach talking to a player between swings. The code has already
measured the swing and chosen the one fix that matters. Your job is only to say it well.

Write `cue`: ONE short spoken sentence (at most {MAX_SPOKEN_WORDS} words) telling the player what
to do on the next swing, in plain words they can act on mid-session.
- Keep the coach's fix. Don't add a second fix or change it.
- You may say the measured number, but only exactly as written in `measured`, as digits.
  Never invent, round or calculate a number.
- No lists, quotes, emoji or stage directions."""


# ---- What Claude may use ------------------------------------------------------------

def coach_facts(result: dict[str, Any]) -> Optional[dict[str, str]]:
    """The coach facts Claude words the cue from, or None when there's no fault to fix."""
    fault = result.get("fault")
    if not isinstance(fault, dict) or not fault.get("label") or not fault.get("cue"):
        return None
    facts = {"measured": _spoken(str(fault["label"])), "coach_cue": str(fault["cue"])}
    if result.get("stroke") in ("forehand", "backhand"):
        facts["stroke"] = str(result["stroke"])
    if fault.get("tip"):
        facts["why_it_matters"] = str(fault["tip"])
    return facts


# Unit spellings that mean the same unit; anything else after a number means no unit.
UNIT_ALIASES: dict[str, str] = {
    "°": "deg", "deg": "deg", "degs": "deg", "degree": "deg", "degrees": "deg",
    "%": "%", "percent": "%", "per cent": "%",
    "ms": "ms", "millisecond": "ms", "milliseconds": "ms",
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "cm": "cm", "centimetre": "cm", "centimetres": "cm", "centimeter": "cm", "centimeters": "cm",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "shoulder width": "shoulder widths", "shoulder widths": "shoulder widths",
}
_UNIT = "|".join(sorted(map(re.escape, UNIT_ALIASES), key=len, reverse=True))
# A number as written: an optional sign (-, the minus sign, "minus", "negative"), the digits
# (decimals and exponents kept as written), then an optional unit right after it ("80
# degrees", "80-degree", "80°", "15%"). A hyphen after a letter or digit ("70-80") isn't a sign.
_QUOTED = re.compile(
    r"(?<![\w.])(?P<sign>[-\u2212]|(?:minus|negative)\s+)?"
    r"(?P<num>(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)"
    rf"(?:(?:\s*|-)(?P<unit>{_UNIT})(?!\w))?",
    re.IGNORECASE,
)
# Spelled-out numbers can't be matched to the coach's digits, so with a unit they never pass
# ("eighty degrees", "twenty-five percent"). Only number words may sit between them.
_NUMBER_WORD = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
                r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
                r"sixty|seventy|eighty|ninety|hundred|thousand)")
_SPELLED = re.compile(
    rf"\b(?:minus\s+|negative\s+)?{_NUMBER_WORD}(?:[\s-]+(?:and\s+|point\s+)?{_NUMBER_WORD})*"
    rf"[\s-]+(?:{_UNIT})(?!\w)",
    re.IGNORECASE,
)


def quoted_numbers(text: str) -> list[tuple[str, str, Optional[str]]]:
    """Every number in `text` as (sign, digits as written, unit or None), e.g. ("-", "80", "deg")."""
    out = []
    for m in _QUOTED.finditer(text):
        unit = m.group("unit")
        out.append(("-" if m.group("sign") else "", m.group("num"),
                    UNIT_ALIASES[unit.lower()] if unit else None))
    return out


def check_worded_cue(cue: str, facts: dict[str, str]) -> str:
    """The cleaned cue if it's one short sentence quoting only numbers in the facts.

    Every number must match one in the coach facts EXACTLY: same sign, same digits as
    written and same unit (80 degrees is fine; -80 degrees, 80.0 degrees, 80 percent or
    a bare 80 aren't). Raises CoachError otherwise (the caller then uses the plain caption).
    """
    cue = " ".join(cue.split())
    if not cue:
        raise CoachError("Claude returned an empty cue.")
    if re.search(r"[.!?]+\s+\S", cue):
        raise CoachError(f"Cue must be one sentence: {cue!r}")
    if len(cue.split()) > MAX_SPOKEN_WORDS:
        raise CoachError(f"Cue has more than {MAX_SPOKEN_WORDS} words: {cue!r}")
    allowed = {n for text in facts.values() for n in quoted_numbers(text)}
    invented = [n for n in quoted_numbers(cue) if n not in allowed]
    if invented:
        shown = [f"{sign}{num}{' ' + unit if unit else ''}" for sign, num, unit in invented]
        raise CoachError(f"Cue used numbers the coach didn't measure as written: {shown}")
    spelled = _SPELLED.search(cue)
    if spelled:
        raise CoachError(f"Cue spelled out a measured number: {spelled.group(0)!r}")
    return cue


# ---- The two APIs (tests replace make_client and synthesize) -------------------------

def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"),
                               timeout=CLAUDE_TIMEOUT_S, max_retries=1)


def word_cue(facts: dict[str, str], client: Optional[anthropic.Anthropic] = None) -> str:
    """Claude's one-sentence spoken cue for these coach facts. Raises on any failure."""
    client = client or make_client()
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "The coach's result for this swing:\n"
                                              + json.dumps(facts, indent=2, sort_keys=True)}],
        output_format=WordedCue,
        output_config={"effort": "low"},  # a one-sentence rewording
        # If the main model declines, the API retries on a fallback model in the same call.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise CoachError("Claude declined this request.")
    if response.parsed_output is None:
        raise CoachError(f"Claude returned no usable JSON (stop_reason={response.stop_reason}).")
    return check_worded_cue(response.parsed_output.cue, facts)


def synthesize(text: str) -> bytes:
    """MP3 bytes of ElevenLabs saying `text` (coach.voice; raises VoiceError)."""
    return voice.synthesize(text)


def has_key(name: str) -> bool:
    load_env()
    return bool(os.environ.get(name, "").strip())


# ---- Cache ----------------------------------------------------------------------------

_memory: dict[str, Any] = {}  # cache key -> cue entry, or audio bytes
_failed: set[str] = set()  # cache keys whose API call failed in this process
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _cache_dir() -> Path:
    return Path(os.environ.get("GHOST_VOICE_CACHE", "") or DEFAULT_CACHE_DIR)


def _digest(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:32]


def _lock(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _read(name: str) -> Optional[bytes]:
    if name in _memory:
        return _memory[name]
    try:
        data = (_cache_dir() / name).read_bytes()
    except OSError:
        return None
    _memory[name] = data
    return data


def _write(name: str, data: bytes) -> None:
    """Keep in memory always; on disk when possible (a read-only disk only loses persistence)."""
    _memory[name] = data
    folder = _cache_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text("# Voice cache: generated per swing, never committed.\n*\n")
        tmp = folder / f".{name}.tmp"
        tmp.write_bytes(data)
        tmp.replace(folder / name)
    except OSError as exc:
        log.warning("Voice cache not written to disk (%s); kept in memory only.", type(exc).__name__)


def _reset_memory() -> None:
    """Forget the in-memory cache and failures (tests; a restarted server starts like this)."""
    _memory.clear()
    _failed.clear()


# ---- The live entry point ---------------------------------------------------------------

def _cue_for(swing_id: str, facts: Optional[dict[str, str]], caption: str,
             client: Optional[anthropic.Anthropic]) -> tuple[str, Source]:
    if facts is None:
        return caption, "caption"  # no fault: nothing for Claude to word
    name = f"cue-{_digest(swing_id, facts)}.json"
    with _lock(name):
        cached = _read(name)
        if cached is not None:
            entry = json.loads(cached)
            return entry["cue"], "claude"
        if name in _failed or not has_key("ANTHROPIC_API_KEY"):
            return caption, "caption"  # no entry written: adding a key later still works
        try:
            cue = word_cue(facts, client)
        except Exception as exc:  # optional feature: any failure falls back to the caption
            _failed.add(name)
            log.warning("Claude cue unavailable for %s, using the caption: %s", swing_id,
                        exc if isinstance(exc, CoachError) else type(exc).__name__)
            return caption, "caption"
        _write(name, json.dumps({"swing_id": swing_id, "cue": cue}).encode())
        return cue, "claude"


def _audio_for(swing_id: str, cue: str) -> Optional[str]:
    # Keyed by the exact text, so the audio always says the cue returned with it.
    name = f"audio-{_digest(swing_id, cue)}.mp3"
    with _lock(name):
        audio = _read(name)
        if audio is None:
            if name in _failed or not has_key("ELEVENLABS_API_KEY"):
                return None
            try:
                audio = synthesize(cue)
            except Exception as exc:  # optional feature: the cue still shows as a caption
                _failed.add(name)
                log.warning("ElevenLabs audio unavailable for %s: %s", swing_id,
                            exc if isinstance(exc, voice.VoiceError) else type(exc).__name__)
                return None
            if not audio:
                _failed.add(name)
                return None
            _write(name, audio)
    return "data:audio/mpeg;base64," + base64.b64encode(audio).decode("ascii")


def voice_for_swing(swing_id: str, result: dict[str, Any],
                    client: Optional[anthropic.Anthropic] = None) -> LiveVoice:
    """{cue, audioUrl, source} for one coached swing. Never raises for missing keys or API failures."""
    caption = str(result.get("cue") or NO_FAULT_CUE)
    cue, source = _cue_for(swing_id, coach_facts(result), caption, client)
    return LiveVoice(cue=cue, audioUrl=_audio_for(swing_id, cue), source=source)
