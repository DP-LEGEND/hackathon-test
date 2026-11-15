"""'Ask the coach': a real-time ElevenLabs voice agent for the swing view. Owner: Henoch.

The agent answers follow-up questions about the coach's call ("why?", "what should I feel?").
It may only quote numbers its tools return. The tools are client tools: the browser runs them
on the data the swing view already loaded from our service (lib/integrations/voice/ask-coach.tsx).

Keys stay server-side. ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID live only in .env.local.
The browser gets a short-lived signed URL from POST /coach/agent/session, never the key.

Create the agent once (from services/; uses your ElevenLabs account):

    python -m coach.ask_agent create

It creates the four client tools and the agent, and appends ELEVENLABS_AGENT_ID to .env.local
without reading or printing the file. Neither id is printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from coach import voice
from coach.env import REPO_ROOT, load_env

API = "https://api.elevenlabs.io/v1/convai"
TIMEOUT_S = 10

PROMPT = """You are Ghost's squash coach, answering a player's follow-up questions about ONE swing by voice.

Rules you must never break:
- Numbers: quote ONLY numbers that a tool returned in this conversation, exactly as written, in digits with their unit (say "157°", never spell it out). Never estimate, round, convert or invent a number. If no tool gives the number, say you don't have it.
- Call get_coach_call before you explain the coach's call, and get_ghost_result or simulate_fix before you talk about the ghost or the ball.
- A bare "why?" means "why did the coach make this call?": call get_coach_call and explain the fault, its measured number and the fix.
- Every ball path, ball speed, wall height and landing spot is PREDICTED, not tracked: there is no real ball. Say "predicted" whenever you mention one.
- Keep each tool value's label: say "estimated" for an ESTIMATE, "assumed" for an ASSUMED value, "measured" for a measured one.
- If the coach did not check something (it is listed as not checked or not measured), say so. Never guess it.
- Never contradict the coach's call or its direction (if it says turn less, never say turn more).
- This conversation is about this one swing only. If the player asks about another swing (for example "what about my backhand?"), say you can only see this swing and that they can pick that swing in the swing list and ask there.
- Talk like a coach on court: short, plain sentences, two or three per answer, no lists, no jargon. For "what should I feel?", describe the body feeling of the coach's cue, without new numbers.
"""

FIRST_MESSAGE = "I'm your coach for this swing. Ask me why, or what you should feel."

FIXES = ["straighten_elbow", "bend_elbow", "turn_shoulders_more", "turn_shoulders_less", "hold_wrist_cock", "close_stance"]

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_coach_call",
        "description": "The coach's call for this swing: the fault with its measured value and unit, the coach's cue, the fix, confidence, and the checks the coach skipped or could not measure.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_swing_metrics",
        "description": "This swing's measured body numbers (shoulder turn, elbow angles, wrist timing, stance) with units, and the racket speed with its label.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_ghost_result",
        "description": "The ghost now on screen: the fix and its size, what it changes on the body (you to ghost), and both PREDICTED balls (speed, front-wall height, landing depth, in or out), with the ball model's assumptions.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "simulate_fix",
        "description": "Make the ghost with another fix for this swing and return the same result as get_ghost_result. Fixes the coach didn't flag are a demo size, not a coached fix.",
        "parameters": {
            "type": "object",
            "properties": {"fix": {"type": "string", "description": "One of: " + ", ".join(FIXES)}},
            "required": ["fix"],
        },
    },
]


class AgentError(RuntimeError):
    """The agent isn't configured, or ElevenLabs couldn't start a session."""


def _env(name: str) -> str:
    load_env()
    return os.environ.get(name, "").strip()


def configured() -> bool:
    """True when both the key and the agent id are set. Never returns or logs either value."""
    return bool(_env("ELEVENLABS_API_KEY") and _env("ELEVENLABS_AGENT_ID"))


def _call(method: str, url: str, body: dict | None = None) -> dict:
    key = _env("ELEVENLABS_API_KEY")
    if not key:
        raise AgentError("ELEVENLABS_API_KEY is not set.")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S, context=voice._ssl_context()) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise AgentError(f"ElevenLabs returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise AgentError("Could not reach ElevenLabs.") from None


def signed_url() -> str:
    """A short-lived signed WebSocket URL for one conversation with the agent."""
    agent = _env("ELEVENLABS_AGENT_ID")
    if not (agent and _env("ELEVENLABS_API_KEY")):
        raise AgentError("Ask the coach is not configured.")
    reply = _call("GET", f"{API}/conversation/get-signed-url?" + urllib.parse.urlencode({"agent_id": agent}))
    url = reply.get("signed_url")
    if not isinstance(url, str) or not url.startswith("wss://"):
        raise AgentError("ElevenLabs returned no signed URL.")
    return url


def create() -> None:
    """Create the client tools and the agent, then append ELEVENLABS_AGENT_ID to .env.local."""
    if _env("ELEVENLABS_AGENT_ID"):
        raise AgentError("ELEVENLABS_AGENT_ID is already set; not creating another agent.")
    tool_ids = []
    for tool in TOOLS:
        reply = _call("POST", f"{API}/tools", {"tool_config": {
            "type": "client", **tool, "expects_response": True, "response_timeout_secs": 20}})
        tool_ids.append(reply["id"])
    reply = _call("POST", f"{API}/agents/create", {
        "name": "Ghost: ask the coach",
        "conversation_config": {
            "agent": {
                "first_message": FIRST_MESSAGE,
                "language": "en",
                "prompt": {"prompt": PROMPT, "llm": "claude-sonnet-4-5", "tool_ids": tool_ids},
            },
            "tts": {"voice_id": voice.DEFAULT_VOICE_ID},
        },
        "platform_settings": {"auth": {"enable_auth": True}},
    })
    agent_id = reply["agent_id"]
    with (REPO_ROOT / ".env.local").open("a", encoding="utf-8") as stream:
        stream.write(f"\nELEVENLABS_AGENT_ID={agent_id}\n")
    print(f"Created the agent and {len(tool_ids)} client tools; ELEVENLABS_AGENT_ID was added to .env.local.")


def update() -> None:
    """Push PROMPT and FIRST_MESSAGE to the existing agent, keeping its tools."""
    agent = _env("ELEVENLABS_AGENT_ID")
    if not agent:
        raise AgentError("ELEVENLABS_AGENT_ID is not set.")
    current = _call("GET", f"{API}/agents/{urllib.parse.quote(agent)}")
    prompt = current.get("conversation_config", {}).get("agent", {}).get("prompt", {})
    tool_ids = prompt.get("tool_ids") or []
    if len(tool_ids) != len(TOOLS):
        raise AgentError(f"The agent has {len(tool_ids)} tools, expected {len(TOOLS)}; not updating.")
    _call("PATCH", f"{API}/agents/{urllib.parse.quote(agent)}", {"conversation_config": {"agent": {
        "first_message": FIRST_MESSAGE,
        "prompt": {"prompt": PROMPT, "llm": prompt.get("llm", "claude-sonnet-4-5"), "tool_ids": tool_ids}}}})
    print(f"Updated the agent's prompt; kept its {len(tool_ids)} tools.")


if __name__ == "__main__":
    commands = {"create": create, "update": update}
    if len(sys.argv) == 2 and sys.argv[1] in commands:
        try:
            commands[sys.argv[1]]()
        except AgentError as exc:
            sys.exit(str(exc))
    else:
        sys.exit("Usage: python -m coach.ask_agent create|update")
