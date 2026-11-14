"""Tests for the live coach voice. Offline: Claude and ElevenLabs are mocked, .env.local is never read."""

from __future__ import annotations

import base64
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import anthropic
import pytest

from coach import live_voice
from coach.agent import NO_FAULT_CUE, coach_swing
from coach.cue import CoachError
from coach.live_voice import WordedCue, check_worded_cue, coach_facts, voice_for_swing
from coach.voice import VoiceError

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "swing_sample.json"
MP3 = b"ID3\x03fake-mp3-bytes"


@pytest.fixture(scope="module")
def result() -> dict:
    """The real coach result for the sample backhand: stance too open, 80 deg."""
    return coach_swing(json.loads(SAMPLE.read_text()), stroke="backhand")


class FakeClaude:
    """Stands in for anthropic.Anthropic: records calls, answers with `cue` (or raises)."""

    def __init__(self, cue: str = "Close your stance so your hips can hold the turn.",
                 stop_reason: str = "end_turn", error: Optional[Exception] = None, delay: float = 0.0):
        self.cue, self.stop_reason, self.error, self.delay = cue, stop_reason, error, delay
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        time.sleep(self.delay)
        if self.error:
            raise self.error
        parsed = None if self.stop_reason == "refusal" else WordedCue(cue=self.cue)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=parsed)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """No real keys, no .env.local, a fresh cache dir; returns helpers to switch keys and fakes on."""
    monkeypatch.setattr(live_voice, "load_env", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setenv("GHOST_VOICE_CACHE", str(tmp_path / "voice"))
    live_voice._reset_memory()
    state = SimpleNamespace(claude=FakeClaude(), spoken=[], voice_error=None)
    monkeypatch.setattr(live_voice, "make_client", lambda: state.claude)

    def fake_synthesize(text: str) -> bytes:
        state.spoken.append(text)
        if state.voice_error:
            raise state.voice_error
        return MP3

    monkeypatch.setattr(live_voice, "synthesize", fake_synthesize)

    def keys(*names: str) -> None:
        for name in names:
            monkeypatch.setenv(name, "test-not-real")

    state.keys = keys
    state.cache = tmp_path / "voice"
    yield state
    live_voice._reset_memory()


def _audio(url: Optional[str]) -> bytes:
    assert url and url.startswith("data:audio/mpeg;base64,")
    return base64.b64decode(url.split(",", 1)[1])


# ---- No keys: the plain caption, never an error --------------------------------------

def test_no_keys_returns_the_plain_caption_and_no_audio(env, result: dict) -> None:
    out = voice_for_swing("sample", result)
    assert out == {"cue": result["cue"], "audioUrl": None, "source": "caption"}
    assert env.claude.calls == [] and env.spoken == []
    assert not env.cache.exists()  # nothing cached, so adding a key later still works


def test_no_fault_uses_the_no_fault_caption_without_claude(env) -> None:
    env.keys("ANTHROPIC_API_KEY")
    out = voice_for_swing("clean", {"fault": None, "cue": NO_FAULT_CUE})
    assert out["cue"] == NO_FAULT_CUE and out["source"] == "caption" and env.claude.calls == []
    assert voice_for_swing("empty", {})["cue"] == NO_FAULT_CUE  # even a bare result never errors


# ---- Claude words the cue from the coach's facts only --------------------------------

def test_claude_words_the_cue_from_the_real_coach_result(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY")
    out = voice_for_swing("sample", result)
    assert out == {"cue": "Close your stance so your hips can hold the turn.", "audioUrl": None,
                   "source": "claude"}
    (call,) = env.claude.calls
    facts = json.loads(call["messages"][0]["content"].split("\n", 1)[1])
    assert facts == coach_facts(result)
    assert facts["measured"] == "Stance too open: stance 80 degrees open to the shot"  # units spoken
    assert set(facts) <= {"measured", "coach_cue", "stroke", "why_it_matters"}  # no raw metrics
    assert call["model"] == "claude-opus-5-5" and call["output_format"] is WordedCue
    assert call["fallbacks"] == "default" and call["output_config"] == {"effort": "low"}


def test_claude_may_quote_the_measured_number(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY")
    env.claude.cue = "Your stance is 80 degrees open, so close it and hold the turn."
    assert voice_for_swing("sample", result)["source"] == "claude"


@pytest.mark.parametrize("bad", [
    "Close your stance to 25 degrees and hold the turn.",  # a number the coach never measured
    "Close your stance. Then hold the turn.",  # two sentences
    " ".join(["word"] * 21) + ".",  # too long to say mid-session
    "   ",
])
def test_a_bad_claude_cue_falls_back_to_the_caption(env, result: dict, bad: str) -> None:
    env.keys("ANTHROPIC_API_KEY")
    env.claude.cue = bad
    out = voice_for_swing("sample", result)
    assert out["cue"] == result["cue"] and out["source"] == "caption"


@pytest.mark.parametrize("error", [
    anthropic.APIConnectionError(request=None),  # type: ignore[arg-type]
    CoachError("boom"),
    RuntimeError("ANTHROPIC_API_KEY is not set."),
])
def test_claude_errors_fall_back_to_the_caption(env, result: dict, error: Exception) -> None:
    env.keys("ANTHROPIC_API_KEY")
    env.claude.error = error
    assert voice_for_swing("sample", result) == {"cue": result["cue"], "audioUrl": None, "source": "caption"}


def test_a_refusal_falls_back_to_the_caption(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY")
    env.claude.stop_reason = "refusal"
    assert voice_for_swing("sample", result)["source"] == "caption"


def test_check_worded_cue_only_allows_numbers_from_the_facts() -> None:
    facts = {"measured": "Straight arm: elbow never bends past 109 degrees before contact"}
    assert check_worded_cue("  Bend   the elbow below 109 degrees. ", facts) == "Bend the elbow below 109 degrees."
    with pytest.raises(CoachError, match="didn't measure"):
        check_worded_cue("Bend it to 90 degrees.", facts)


# ---- ElevenLabs voices exactly the cue that is returned -------------------------------

def test_both_keys_give_claudes_cue_and_its_audio(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    out = voice_for_swing("sample", result)
    assert out["source"] == "claude" and _audio(out["audioUrl"]) == MP3
    assert env.spoken == [out["cue"]]  # the audio says the returned cue, word for word


def test_elevenlabs_only_voices_the_plain_caption(env, result: dict) -> None:
    env.keys("ELEVENLABS_API_KEY")
    out = voice_for_swing("sample", result)
    assert out["cue"] == result["cue"] and out["source"] == "caption"
    assert _audio(out["audioUrl"]) == MP3 and env.spoken == [result["cue"]] and env.claude.calls == []


def test_voice_failure_keeps_the_cue_with_no_audio(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    env.voice_error = VoiceError("ElevenLabs returned HTTP 401.")
    out = voice_for_swing("sample", result)
    assert out["source"] == "claude" and out["audioUrl"] is None


# ---- Cache: each swing calls each API at most once -----------------------------------

def test_each_swing_calls_each_api_once(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    first = voice_for_swing("sample", result)
    assert voice_for_swing("sample", result) == first
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1
    voice_for_swing("another-swing", result)  # a different swing is its own entry
    assert len(env.claude.calls) == 2 and len(env.spoken) == 2


def test_the_cache_survives_a_server_restart(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    first = voice_for_swing("sample", result)
    live_voice._reset_memory()  # a restarted server: only the disk cache is left
    assert voice_for_swing("sample", result) == first
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1
    assert (env.cache / ".gitignore").read_text().splitlines()[-1] == "*"  # never committed


def test_failures_are_not_retried_on_every_request(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    env.claude.error = anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]
    env.voice_error = VoiceError("quota")
    for _ in range(3):
        assert voice_for_swing("sample", result) == {"cue": result["cue"], "audioUrl": None, "source": "caption"}
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1
    live_voice._reset_memory()  # after a restart a failed call is tried once more
    env.claude.error, env.voice_error = None, None
    assert voice_for_swing("sample", result)["source"] == "claude"


def test_adding_a_key_later_upgrades_the_caption(env, result: dict) -> None:
    assert voice_for_swing("sample", result)["source"] == "caption"
    env.keys("ANTHROPIC_API_KEY")
    assert voice_for_swing("sample", result)["source"] == "claude"


def test_new_coach_numbers_for_the_same_swing_are_worded_afresh(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY")
    voice_for_swing("sample", result)
    changed = {**result, "fault": {**result["fault"], "label": "Stance too open: stance 70 deg open to the shot"}}
    voice_for_swing("sample", changed)
    assert len(env.claude.calls) == 2


def test_parallel_requests_for_one_swing_call_claude_once(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    env.claude.delay = 0.2
    outs: list[dict] = []
    threads = [threading.Thread(target=lambda: outs.append(voice_for_swing("sample", result))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1
    assert all(o == outs[0] for o in outs) and outs[0]["source"] == "claude"


def test_a_read_only_cache_dir_still_caches_in_memory(env, result: dict, monkeypatch: pytest.MonkeyPatch,
                                                      tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("a file where the cache dir should be")
    monkeypatch.setenv("GHOST_VOICE_CACHE", str(blocker / "voice"))
    env.keys("ANTHROPIC_API_KEY")
    assert voice_for_swing("sample", result)["source"] == "claude"
    assert voice_for_swing("sample", result)["source"] == "claude"
    assert len(env.claude.calls) == 1


# ---- The route: GET /coach/{swing_id}/voice ---------------------------------------------

@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from pipeline.server import app

    run = tmp_path / "swings" / "sample-run"
    run.mkdir(parents=True)
    sample = json.loads(SAMPLE.read_text())
    sample.update(id="sample", fps=30, fpsReal=120, contactFrame=12, side="backhand")
    (run / "sample.json").write_text(json.dumps(sample))
    (run / "manifest.json").write_text(json.dumps({"files": ["sample.json"]}))
    monkeypatch.setenv("GHOST_SWINGS_DIR", str(tmp_path / "swings"))
    monkeypatch.setenv("GHOST_LABELS_CSV", str(tmp_path / "labels.csv"))
    return TestClient(app)


def test_route_with_no_keys_returns_the_caption_and_null_audio(env, api) -> None:
    coached = api.post("/coach/sample").json()
    response = api.get("/coach/sample/voice")
    assert response.status_code == 200, response.text
    assert response.json() == {"cue": coached["cue"], "audioUrl": None, "source": "caption"}


def test_route_with_keys_returns_claudes_cue_and_audio_once(env, api) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    body = api.get("/coach/sample/voice").json()
    assert body["source"] == "claude" and _audio(body["audioUrl"]) == MP3
    assert api.get("/coach/sample/voice").json() == body
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1


def test_route_unknown_swing_is_404(env, api) -> None:
    assert api.get("/coach/nope/voice").status_code == 404
