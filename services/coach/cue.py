"""One fix plus a one-sentence cue from swing metrics. Owners: aryan and Dev.

Rule: code measures, Claude explains and decides. The metrics come from
physics/metrics.py; Claude only picks which one to fix and words the cue.
Any number Claude writes must be one of the measured numbers, or we reject it.

Try it (from inside services/, with ANTHROPIC_API_KEY in .env.local):

    python -m coach.cue            # MOCK metrics, prints the JSON
    python -m coach.cue --speak    # also reads the cue aloud with ElevenLabs
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from coach.env import require_env

MODEL = "claude-opus-5-5"

MetricName = Literal["elbow_bend", "shoulder_turn", "wrist_angle", "contact_point"]


class SwingMetrics(BaseModel):
    """Measured by code at the contact frame. Units are in the field names."""

    elbow_bend_deg: float = Field(description="Hitting-arm elbow angle; 180 = straight arm")
    shoulder_turn_deg: float = Field(description="Shoulder line rotation away from the front wall")
    wrist_angle_deg: float = Field(description="Forearm-to-racket angle; 180 = racket in line")
    contact_point_cm: float = Field(
        description="Ball contact distance in front of the front foot; negative = behind it"
    )


class CoachCue(BaseModel):
    """What the coach returns. This is the JSON the rest of the app reads."""

    metric: MetricName = Field(description="The one metric to fix")
    fix: str = Field(description="One or two plain sentences: what to change and why, quoting only given numbers")
    cue: str = Field(description="One short spoken sentence the player can act on during the next swing")


SYSTEM_PROMPT = """You are a squash coach. A player has just hit one swing and the code has measured it.

Pick exactly ONE fix, the one that matters most. Coaching priority, highest first:
1. contact_point (where the ball is struck relative to the front foot)
2. shoulder_turn (preparation and rotation)
3. elbow_bend
4. wrist_angle
Only skip a higher-priority metric if its measured value already looks sound.

Rules:
- Never invent or calculate a number. You may only quote numbers exactly as they appear in the metrics.
- `fix`: one or two plain sentences saying what to change and why.
- `cue`: one short sentence, under 12 words, spoken to the player before their next swing. No numbers in the cue.
"""


class CoachError(RuntimeError):
    """The coach could not produce a usable answer."""


def _format_number(value: float) -> str:
    return f"{value:g}"


def _allowed_numbers(metrics: SwingMetrics) -> set[str]:
    return {_format_number(v) for v in metrics.model_dump().values()}


def _numbers_in(text: str) -> list[str]:
    return [_format_number(float(n)) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]


def check_only_measured_numbers(result: CoachCue, metrics: SwingMetrics) -> None:
    """Enforce 'code measures, Claude explains': reject any number we did not measure."""
    allowed = _allowed_numbers(metrics)
    invented = [n for n in _numbers_in(result.fix + " " + result.cue) if n not in allowed]
    if invented:
        raise CoachError(f"Coach used numbers that were not measured: {invented}")


def get_cue(metrics: SwingMetrics, client: Optional[anthropic.Anthropic] = None) -> CoachCue:
    """Ask Claude for exactly one fix and a one-sentence cue for these metrics."""
    if client is None:
        client = anthropic.Anthropic(api_key=require_env("ANTHROPIC_API_KEY"))

    try:
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": "Measured metrics for this swing:\n"
                    + json.dumps(metrics.model_dump(), indent=2),
                }
            ],
            output_format=CoachCue,
            output_config={"effort": "low"},
            # If the main model declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise CoachError("Claude rejected the API key. Check ANTHROPIC_API_KEY in .env.local.") from exc
    except anthropic.RateLimitError as exc:
        raise CoachError("Claude is rate limiting us. Wait a few seconds and try again.") from exc
    except anthropic.APIStatusError as exc:
        raise CoachError(f"Claude API error {exc.status_code}.") from exc
    except anthropic.APIConnectionError as exc:
        raise CoachError("Could not reach the Claude API. Check the internet connection.") from exc

    if response.stop_reason == "refusal":
        raise CoachError("Claude declined this request.")
    if response.parsed_output is None:
        raise CoachError(f"Claude returned no usable JSON (stop_reason={response.stop_reason}).")

    result = response.parsed_output
    check_only_measured_numbers(result, metrics)
    return result


# MOCK numbers for trying this out. Not from a real swing.
MOCK_METRICS = SwingMetrics(
    elbow_bend_deg=148,
    shoulder_turn_deg=62,
    wrist_angle_deg=131,
    contact_point_cm=-18,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Get one fix and cue for MOCK swing metrics.")
    parser.add_argument("--speak", action="store_true", help="Read the cue aloud with ElevenLabs")
    args = parser.parse_args()

    print("Using MOCK metrics:", MOCK_METRICS.model_dump_json())
    result = get_cue(MOCK_METRICS)
    print(result.model_dump_json(indent=2))

    if args.speak:
        from coach.voice import play, speak_cue

        path = speak_cue(result.cue)
        print(f"Saved audio to {path}")
        play(path)


if __name__ == "__main__":
    main()
