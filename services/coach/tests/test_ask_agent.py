"""'Ask the coach' agent: hidden unless configured, signed URL server-side, key never exposed."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from coach import ask_agent
from pipeline import server

KEY = "sk-test-not-a-real-key"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    """No .env.local in tests: each test sets exactly the variables it needs."""
    monkeypatch.setattr(ask_agent, "load_env", lambda: None)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_AGENT_ID", raising=False)
    return monkeypatch


class Reply:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.body


def test_hidden_without_key_or_agent(env) -> None:
    client = TestClient(server.app)
    assert client.get("/coach/agent").json() == {"available": False}
    env.setenv("ELEVENLABS_API_KEY", KEY)
    assert client.get("/coach/agent").json() == {"available": False}  # no agent id yet
    assert client.post("/coach/agent/session").status_code == 404


def test_session_returns_only_a_signed_url(env) -> None:
    env.setenv("ELEVENLABS_API_KEY", KEY)
    env.setenv("ELEVENLABS_AGENT_ID", "agent_test")
    seen: dict = {}

    def urlopen(request, **kwargs):
        seen["url"], seen["key"] = request.full_url, request.get_header("Xi-api-key")
        return Reply({"signed_url": "wss://api.elevenlabs.io/v1/convai/conversation?agent_id=agent_test&conversation_signature=x"})

    env.setattr(ask_agent.urllib.request, "urlopen", urlopen)
    client = TestClient(server.app)
    assert client.get("/coach/agent").json() == {"available": True}
    body = client.post("/coach/agent/session").json()
    assert set(body) == {"signedUrl"} and body["signedUrl"].startswith("wss://")
    assert KEY not in json.dumps(body)
    assert seen["key"] == KEY and "get-signed-url" in seen["url"] and "agent_id=agent_test" in seen["url"]


def test_elevenlabs_failure_is_a_502_without_the_key(env) -> None:
    env.setenv("ELEVENLABS_API_KEY", KEY)
    env.setenv("ELEVENLABS_AGENT_ID", "agent_test")

    def urlopen(request, **kwargs):
        raise ask_agent.urllib.error.URLError("down")

    env.setattr(ask_agent.urllib.request, "urlopen", urlopen)
    response = TestClient(server.app).post("/coach/agent/session")
    assert response.status_code == 502 and KEY not in response.text


def test_prompt_forbids_invented_numbers_and_says_predicted() -> None:
    prompt = ask_agent.PROMPT
    assert "ONLY numbers that a tool returned" in prompt and "Never estimate, round, convert or invent a number" in prompt
    assert "PREDICTED" in prompt
    assert [t["name"] for t in ask_agent.TOOLS] == ["get_coach_call", "get_swing_metrics", "get_ghost_result", "simulate_fix"]
