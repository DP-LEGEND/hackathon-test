"""What the coach avatar says after a swing. Owners: aryan and Dev.

avatar_script(swing) turns coach_swing's result into 2-3 short spoken lines (max 25
words each). Code measures, Claude explains: the lines only say numbers that are
already in the result, so nothing new is invented here.

Who speaks them:
- "anam": if ANAM_API_KEY is set in .env.local, the web avatar (Anam) speaks the lines.
  Python never calls Anam; it only hands the lines over.
- "elevenlabs": otherwise speak_avatar_script() voices them with ElevenLabs (voice.py).
If speech fails, the lines are still shown as captions.

Try it (from inside services/):

    python -m coach.avatar ../data/samples/swing_sample.json --stroke backhand
    python -m coach.avatar ../data/samples/swing_sample.json --stroke backhand --speak
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Literal, Optional, TypedDict

from coach.agent import coach_swing
from coach.env import load_env
from coach.faults import Stroke

Voice = Literal["anam", "elevenlabs"]

MAX_WORDS = 25
MAX_LINES = 3

NO_FAULT_LINES = ["Nice swing: there's nothing to fix this time.", "Hit the next one exactly the same way."]
GHOST_LINE = "Watch your ghost beside you: it makes that change."
# NOT SPOKEN YET: the live ghost (/compare route, web page, physics compare()) applies only
# ghost_fix, one edit, so claiming both would describe a change the screen doesn't show.
# Switch it back on once the live path applies coach_swing's ghost_edits.
GHOST_PAIR_LINE = "Watch your ghost beside you: it closes the stance and turns the shoulders a little less."
# When the ghost can't animate the fault just spoken and shows a fallback fix instead.
GHOST_OTHER_LINE = "Your ghost can't show that fix yet, so it shows another one: {fix}."

# How each ghost fix is said aloud.
FIX_PHRASES = {
    "straighten_elbow": "straightening the elbow",
    "bend_elbow": "leading with a bent elbow",
    "turn_shoulders_more": "turning the shoulders further",
    "turn_shoulders_less": "turning the shoulders a little less",
    "hold_wrist_cock": "holding the wrist cock longer",
    "close_stance": "closing the stance",
    "firm_wrist": "keeping the wrist firm through contact",
}

# Units as they should be said aloud.
SPOKEN_UNITS = {" deg": " degrees", " ms": " milliseconds"}


class AvatarScript(TypedDict):
    lines: list[str]
    voice: Voice
    fault: Optional[str]


def avatar_voice() -> Voice:
    """Anam when it's configured, otherwise ElevenLabs."""
    load_env()
    return "anam" if os.environ.get("ANAM_API_KEY", "").strip() else "elevenlabs"


def _spoken(text: str) -> str:
    for short, long in SPOKEN_UNITS.items():
        text = text.replace(short, long)
    return text


def _check(lines: list[str]) -> list[str]:
    if not 2 <= len(lines) <= MAX_LINES:
        raise ValueError(f"avatar needs 2-{MAX_LINES} lines, got {len(lines)}")
    for line in lines:
        words = len(line.split())
        if not line.strip() or words > MAX_WORDS:
            raise ValueError(f"avatar line has {words} words (max {MAX_WORDS}): {line!r}")
    return lines


def script_from_result(result: dict[str, Any], voice: Optional[Voice] = None) -> AvatarScript:
    """2-3 spoken lines from a coach_swing result, quoting only numbers it already has."""
    fault = result.get("fault")
    if fault is None:
        lines = list(NO_FAULT_LINES)
    else:
        # Line 1: what the code measured (the fault label, e.g. "Stance too open: stance
        # 80 deg open to the shot"), said with units in words.
        lines = [_spoken(fault["label"]) + "."]
        # Line 2: the cue.
        lines.append(fault["cue"])
        # Line 3: the tip if there is one, else what the ghost REALLY shows: only ghost_fix,
        # the one fix the live ghost animates (a paired second fix isn't rendered yet).
        # "It makes that change" only when that fix is for the fault just spoken; a
        # fallback ghost is named as a different fix (or ghost_note), never passed off.
        ghost = result.get("ghost_fault")
        if fault.get("tip"):
            lines.append(fault["tip"])
        elif ghost is not None and ghost.get("id") == fault["id"]:
            lines.append(GHOST_LINE)
        elif ghost is not None and ghost.get("fix") in FIX_PHRASES:
            lines.append(GHOST_OTHER_LINE.format(fix=FIX_PHRASES[ghost["fix"]]))
        elif ghost is not None and result.get("ghost_note"):
            lines.append(result["ghost_note"])
    return AvatarScript(lines=_check(lines), voice=voice or avatar_voice(),
                        fault=fault["id"] if fault else None)


def avatar_script(swing: dict, stroke: Optional[Stroke] = None, fps_real: Optional[float] = None,
                  voice: Optional[Voice] = None) -> AvatarScript:
    """Coach the swing, then return what the avatar says and who voices it."""
    return script_from_result(coach_swing(swing, stroke, fps_real), voice)


def speak_avatar_script(script: AvatarScript, out_path: Optional[Path] = None) -> Optional[Path]:
    """Voice the lines with ElevenLabs when Anam isn't the voice. Returns the MP3 path.

    Returns None for "anam": the web avatar speaks the lines itself.
    Raises coach.voice.VoiceError if ElevenLabs fails; show the lines as captions then.
    """
    if script["voice"] == "anam":
        return None
    from coach.voice import speak_cue

    return speak_cue(" ".join(script["lines"]), out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print (and optionally speak) the avatar's lines for one swing.")
    parser.add_argument("swing", help="path to a Swing JSON file")
    parser.add_argument("--stroke", choices=["forehand", "backhand"], help="override stroke detection")
    parser.add_argument("--speak", action="store_true", help="voice the lines with ElevenLabs if Anam isn't set up")
    args = parser.parse_args()
    with open(args.swing) as fh:
        script = avatar_script(json.load(fh), args.stroke)
    print(json.dumps(script, indent=2))
    if args.speak:
        from coach.voice import VoiceError, play

        try:
            path = speak_avatar_script(script)
        except (VoiceError, RuntimeError) as exc:
            raise SystemExit(f"Voice failed, lines shown above only. {exc}") from None
        if path is None:
            print("Voice is Anam: the web avatar speaks these lines.")
        else:
            print(f"Saved audio to {path}")
            play(path)


if __name__ == "__main__":
    main()
