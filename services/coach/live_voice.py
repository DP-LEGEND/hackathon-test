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
is worded afresh. A failed call is remembered for FAILURE_RETRY_S (60 s), so a bad key
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
import time
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
# The web proxy (app/api/[...path]/route.ts) aborts every request except /process after
# 30 s, so Claude plus ElevenLabs must finish well inside that: at most 10 s + 12 s, with no
# SDK retries (a retry would double Claude's time). A timeout falls back to the caption
# (Claude) or to no audio (ElevenLabs), never to the proxy's 502.
CLAUDE_TIMEOUT_S = 10.0
TTS_TIMEOUT_S = 12.0
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
- If you quote the measured number, copy its measured phrase word for word, once
  (for "Over-rotation: hips turn 157 degrees", say "hips turn 157 degrees").
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
# The coach writes every number as digits, so a spelled-out number can only be invented:
# any of these words is rejected whatever follows it ("two inches", "half a foot").
_NUMBER_WORD = (r"(?:zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
                r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
                r"sixty|seventy|eighty|ninety|hundreds?|thousands?|half|halves|quarters?|dozens?|"
                r"twice|double|triple|thirds?|couple)")
_SPELLED = re.compile(rf"\b{_NUMBER_WORD}\b", re.IGNORECASE)
# "one" is everyday English ("one more swing", "one smooth turn"), so it only counts as a
# number before a unit-like noun, allowing one word between ("one inch", "one more inch").
UNIT_NOUNS = sorted(set(UNIT_ALIASES) | {
    "inch", "inches", "foot", "feet", "yard", "yards", "mm", "millimetre", "millimetres",
    "millimeter", "millimeters", "minute", "minutes", "step", "steps", "pace", "paces",
}, key=len, reverse=True)
_ONE_UNIT = re.compile(
    rf"\bone(?:[\s-]+[a-z]+)?[\s-]+(?:{'|'.join(map(re.escape, UNIT_NOUNS))})(?!\w)", re.IGNORECASE)


def quoted_numbers(text: str) -> list[tuple[str, str, Optional[str]]]:
    """Every number in `text` as (sign, digits as written, unit or None), e.g. ("-", "80", "deg")."""
    out = []
    for m in _QUOTED.finditer(text):
        unit = m.group("unit")
        out.append(("-" if m.group("sign") else "", m.group("num"),
                    UNIT_ALIASES[unit.lower()] if unit else None))
    return out


# Opposite fix directions, each as the word forms a cue may use. Claude may reword the
# coach's fix but never reverse it ("turn less" must not become "turn more").
OPPOSITES: list[tuple[frozenset[str], frozenset[str]]] = [
    (frozenset({"more", "further", "farther"}), frozenset({"less", "fewer"})),
    (frozenset({"open", "opens", "opened", "opening", "opener"}),
     frozenset({"close", "closes", "closed", "closing", "closer"})),
    (frozenset({"bend", "bends", "bent", "bending"}),
     frozenset({"straighten", "straightens", "straightened", "straightening", "straight"})),
    (frozenset({"earlier", "sooner"}), frozenset({"later"})),
    (frozenset({"wider", "widen", "widens", "widening"}), frozenset({"narrower", "narrow", "narrows", "narrowing"})),
    (frozenset({"higher", "raise", "raises", "raised", "raising"}), frozenset({"lower", "lowers", "lowered", "lowering"})),
    (frozenset({"faster", "quicker"}), frozenset({"slower"})),
    (frozenset({"forward", "forwards"}), frozenset({"back", "backward", "backwards"})),
]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def check_direction(cue: str, facts: dict[str, str]) -> None:
    """Raise CoachError if the cue reverses the coach's fix direction.

    For each opposite pair the coach cue uses, the fix side is the one it says ("less"
    in "Turn a little less"). When it says both, as the stance cue does ("Your open stance
    ... Close it"), the measured label names the fault ("Stance too open"), so the other
    side is the fix; if the label can't tell, any word of that pair is rejected.
    A cue may use the opposite side only to restate the fault: the word is in the measured
    label and the cue also says the fix ("80 degrees open, so close it"). So "Open your
    stance further" for an open stance is rejected.
    """
    coach, fault, said = _words(facts.get("coach_cue", "")), _words(facts.get("measured", "")), _words(cue)
    for a, b in OPPOSITES:
        in_a, in_b = bool(coach & a), bool(coach & b)
        if not (in_a or in_b):
            continue
        if in_a and in_b:
            if bool(fault & a) == bool(fault & b):
                if said & (a | b):
                    raise CoachError(f"Can't tell the coach's fix direction, so the cue may not say "
                                     f"{sorted(said & (a | b))}")
                continue
            fix, opposite = (b, a) if fault & a else (a, b)
        else:
            fix, opposite = (a, b) if in_a else (b, a)
        used = said & opposite
        if used and not (fault & opposite and said & fix):
            raise CoachError(f"Cue reverses the coach's fix: coach says {sorted(coach & fix)}, "
                             f"cue says {sorted(used)}")


def guarded(facts: dict[str, str]) -> bool:
    """True if check_direction can guard Claude's rewording of this coach cue.

    It can only when the coach cue uses a word from an OPPOSITES pair. Cues without one
    (today early_wrist_snap's "Keep your wrist cocked..." and rolled_wrist's "Keep your
    wrist firm...") have no direction to check, so Claude could reverse them unnoticed
    ("Snap your wrist before contact."). Those are spoken verbatim instead.
    """
    coach = _words(facts.get("coach_cue", ""))
    return any(coach & (a | b) for a, b in OPPOSITES)


# A cue must say the coach's fix, never countermand it.
_NEGATION = re.compile(r"\b(?:don[\'\u2019]?t|do\s+not|never|stop|avoid|no\s+longer)\b", re.IGNORECASE)
# Words that turn a quoted number into an amount to change by ("Turn 95 degrees less",
# "close it by 80") or a target to reach ("Bend your elbow to 109 degrees", "until it
# reaches 109"): the coach only measured the number, it never set an amount or a target.
TARGET_WORDS = frozenset({"to", "until", "reach", "reaches", "reaching"})
_CHANGE_FAMILIES: list[frozenset[str]] = [*(side for pair in OPPOSITES[:3] for side in pair),
                                          frozenset({"by"}), TARGET_WORDS]
CHANGE_WINDOW = 5  # words either side of a quoted number
_CLAUSE_BREAK = {",", ";", ":"}


def _tokens(text: str) -> list[str]:
    """Lower-case words, numbers and clause breaks (, ; :) in order."""
    return re.findall(r"[a-z]+|\d+(?:\.\d+)?(?:e[-+]?\d+)?|[,;:]", text.lower())


def _change_words_near(tokens: list[str], number: str) -> set[frozenset[str]]:
    """The change-word families near each `number` in tokens.

    Before the number: up to CHANGE_WINDOW words, across clause breaks, so the verb and a
    target word count ("Bend your elbow, to 109 degrees"). After it: up to CHANGE_WINDOW
    words, stopping at a clause break, so a fix in the next clause doesn't count ("80
    degrees open, so close it"). Target words count only before the number, where a
    target sits ("to 109"); after it they're ordinary words ("80 degrees open to the shot").
    """
    near: set[frozenset[str]] = set()
    for i, tok in enumerate(tokens):
        if tok != number:
            continue
        before = [w for w in reversed(tokens[:i]) if w not in _CLAUSE_BREAK][:CHANGE_WINDOW]
        after: list[str] = []
        for w in tokens[i + 1:]:
            if w in _CLAUSE_BREAK or len(after) == CHANGE_WINDOW:
                break
            after.append(w)
        for word in before:
            near.update(f for f in _CHANGE_FAMILIES if word in f)
        for word in after:
            near.update(f for f in _CHANGE_FAMILIES if word in f and f is not TARGET_WORDS)
    return near


def check_number_context(cue: str, facts: dict[str, str]) -> None:
    """Raise CoachError if a quoted number sits near a change or target word.

    Change words: more/less/further, open/close, bend/straighten (any form) and "by";
    target words: to, until, reach (see _change_words_near for the window). Allowed only
    when the measured label has the same kind of word that close to the same number,
    i.e. the cue restates the measurement ("80 degrees open" from "stance 80 degrees
    open to the shot"), so the live cue stays valid.
    """
    cue_tokens, label_tokens = _tokens(cue), _tokens(facts.get("measured", ""))
    for _, number, _ in quoted_numbers(cue):
        extra = _change_words_near(cue_tokens, number.lower()) - _change_words_near(label_tokens, number.lower())
        if extra:
            words = sorted({w for w in cue_tokens if any(w in f for f in extra)})
            raise CoachError(f"Cue puts {number} next to a change {words}: the coach only measured it")


# A quoted number must keep its measured phrase, word for word, and appear only once: the
# label's words from up to two before the number through up to one after its unit ("hips
# turn 157 degrees" from "Over-rotation: hips turn 157 degrees"). Keyword lists kept missing
# new ways to turn a measurement into a target ("at 109 degrees", "aim for ... 109 degrees").
_UNIT_TOKENS = sorted((tuple(re.findall(r"[a-z]+", u)) for u in UNIT_ALIASES if re.search(r"[a-z]", u)),
                      key=len, reverse=True)
PHRASE_WORDS_BEFORE = 2
PHRASE_WORDS_AFTER_UNIT = 1


def _measured_phrase(tokens: list[str], i: int) -> list[str]:
    """The label's words around the number at tokens[i]: up to PHRASE_WORDS_BEFORE words
    before it and up to PHRASE_WORDS_AFTER_UNIT after its unit, clipped at the label's
    start or end or a clause break (, ; :)."""
    start = i
    while start > 0 and i - start < PHRASE_WORDS_BEFORE and tokens[start - 1] not in _CLAUSE_BREAK:
        start -= 1
    end = i + 1
    for unit in _UNIT_TOKENS:
        if tuple(tokens[end:end + len(unit)]) == unit:
            end += len(unit)
            break
    after = 0
    while end < len(tokens) and after < PHRASE_WORDS_AFTER_UNIT and tokens[end] not in _CLAUSE_BREAK:
        end += 1
        after += 1
    return tokens[start:end]


def _contains_run(tokens: list[str], run: list[str]) -> bool:
    n = len(run)
    return any(tokens[k:k + n] == run for k in range(len(tokens) - n + 1))


def check_number_anchor(cue: str, facts: dict[str, str]) -> None:
    """Raise CoachError unless every quoted number keeps its measured phrase, once.

    - A number from facts["measured"] may appear at most once in the cue ("Cue repeats 157").
    - The cue must contain the number's measured phrase (_measured_phrase) as an exact,
      unbroken run of words: label "Over-rotation: hips turn 157 degrees" needs "hips turn
      157 degrees", so "Turn 157 degrees." fails ("Cue moves 157 out of its measured phrase").
    Word for word means the unit is spelled as in the label: "157°" or "157 deg" fail.
    """
    cue_tokens, label_tokens = _tokens(cue), _tokens(facts.get("measured", ""))
    for _, number, _ in quoted_numbers(cue):
        n = number.lower()
        if n in label_tokens and cue_tokens.count(n) > 1:
            raise CoachError(f"Cue repeats {number}")
        phrases = [_measured_phrase(label_tokens, i) for i, tok in enumerate(label_tokens) if tok == n]
        if not any(_contains_run(cue_tokens, phrase) for phrase in phrases):
            raise CoachError(f"Cue moves {number} out of its measured phrase")


def check_worded_cue(cue: str, facts: dict[str, str]) -> str:
    """The cleaned cue if it's one short sentence quoting only numbers in the facts.

    Every number must match one in the coach facts EXACTLY: same sign, same digits as
    written and same unit (80 degrees is fine; -80 degrees, 80.0 degrees, 80 percent or
    a bare 80 aren't). No number words, no negations (don't, never, stop...), no number
    next to a change word (check_number_context), every number quoted once inside its
    measured phrase, word for word (check_number_anchor), and the coach's fix direction kept
    (check_direction).
    Raises CoachError otherwise (the caller then uses the plain caption).
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
    spelled = _SPELLED.search(cue) or _ONE_UNIT.search(cue)
    if spelled:
        raise CoachError(f"Cue spelled out a number: {spelled.group(0)!r}")
    negation = _NEGATION.search(cue)
    if negation:
        raise CoachError(f"Cue negates an instruction: {negation.group(0)!r}")
    check_number_context(cue, facts)
    check_number_anchor(cue, facts)
    check_direction(cue, facts)
    return cue


# ---- The two APIs (tests replace make_client and synthesize) -------------------------

def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"),
                               timeout=CLAUDE_TIMEOUT_S, max_retries=0)


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
    return voice.synthesize(text, timeout_s=TTS_TIMEOUT_S)


def has_key(name: str) -> bool:
    load_env()
    return bool(os.environ.get(name, "").strip())


# ---- Cache ----------------------------------------------------------------------------

_memory: dict[str, Any] = {}  # cache key -> cue entry, or audio bytes
_failed: dict[str, float] = {}  # cache key -> when its API call last failed (_now())
FAILURE_RETRY_S = 60.0  # a failed call is tried again once its failure is this old


def _now() -> float:
    return time.monotonic()


def _recently_failed(name: str) -> bool:
    at = _failed.get(name)
    return at is not None and _now() - at < FAILURE_RETRY_S
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

def _cached_cue(data: bytes) -> Optional[str]:
    """The cue in a cue cache entry, or None if the entry is unreadable or the wrong shape."""
    try:
        entry = json.loads(data)
    except ValueError:  # also covers bad UTF-8 (UnicodeDecodeError)
        return None
    cue = entry.get("cue") if isinstance(entry, dict) else None
    return cue if isinstance(cue, str) and cue.strip() else None


def _discard(name: str, swing_id: str, why: str) -> None:
    """Forget a bad cache entry in memory and on disk, so it's regenerated or skipped."""
    _memory.pop(name, None)
    try:
        (_cache_dir() / name).unlink(missing_ok=True)
    except OSError:
        pass
    log.warning("Ignored a voice cache entry for %s: %s.", swing_id, why)


def _cue_for(swing_id: str, facts: Optional[dict[str, str]], caption: str,
             client: Optional[anthropic.Anthropic]) -> tuple[str, Source]:
    if facts is None:
        return caption, "caption"  # no fault: nothing for Claude to word
    if not guarded(facts):
        return caption, "caption"  # no direction to guard: speak the coach's cue verbatim
    name = f"cue-{_digest(swing_id, facts)}.json"
    with _lock(name):
        cached = _read(name)
        if cached is not None:
            cue = _cached_cue(cached)
            if cue is None:
                _discard(name, swing_id, "unreadable or wrong shape")  # treat as a miss
            else:
                # Re-check against today's rules: a cue cached under an older, weaker check
                # (an invented number, a reversed fix) must not be served or voiced.
                try:
                    return check_worded_cue(cue, facts), "claude"
                except CoachError as exc:
                    _discard(name, swing_id, f"fails the current checks ({exc})")  # treat as a miss
        if _recently_failed(name) or not has_key("ANTHROPIC_API_KEY"):
            return caption, "caption"  # no entry written: adding a key later still works
        try:
            cue = word_cue(facts, client)
        except Exception as exc:  # optional feature: any failure falls back to the caption
            _failed[name] = _now()
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
            if _recently_failed(name) or not has_key("ELEVENLABS_API_KEY"):
                return None
            try:
                audio = synthesize(cue)
            except Exception as exc:  # optional feature: the cue still shows as a caption
                _failed[name] = _now()
                log.warning("ElevenLabs audio unavailable for %s: %s", swing_id,
                            exc if isinstance(exc, voice.VoiceError) else type(exc).__name__)
                return None
            if not audio:
                _failed[name] = _now()
                return None
            _write(name, audio)
    return "data:audio/mpeg;base64," + base64.b64encode(audio).decode("ascii")


def voice_for_swing(swing_id: str, result: dict[str, Any],
                    client: Optional[anthropic.Anthropic] = None) -> LiveVoice:
    """{cue, audioUrl, source} for one coached swing. Never raises for missing keys or API failures."""
    caption = str(result.get("cue") or NO_FAULT_CUE)
    cue, source = _cue_for(swing_id, coach_facts(result), caption, client)
    return LiveVoice(cue=cue, audioUrl=_audio_for(swing_id, cue), source=source)
