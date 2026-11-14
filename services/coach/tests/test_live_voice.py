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


# ---- Review fix on #60: numbers must match the coach's EXACTLY as written ---------------
# Same sign, same digits, same unit. Spellings of one unit are equal (degrees, deg, °).

STANCE_FACTS = {"measured": "Stance too open: stance 80 degrees open to the shot",
                "coach_cue": "Close it so you can hold the turn."}
RELEASE_FACTS = {"measured": "Early wrist snap: wrist releases -20 milliseconds before contact",
                 "coach_cue": "Keep your wrist cocked until the racket meets the ball."}


@pytest.mark.parametrize("facts, cue", [
    (STANCE_FACTS, "Your stance is -80 degrees open, so close it and hold the turn."),
    (STANCE_FACTS, "Your stance is minus 80 degrees open, so close it and hold the turn."),
    (STANCE_FACTS, "Your stance is −80 degrees open, so close it and hold the turn."),  # the minus sign
    (RELEASE_FACTS, "You release 20 milliseconds before contact, so hold the cock longer."),  # sign dropped
])
def test_a_sign_flip_falls_back(facts: dict, cue: str) -> None:
    with pytest.raises(CoachError, match="as written"):
        check_worded_cue(cue, facts)


@pytest.mark.parametrize("cue", [
    "Your stance is 80 percent open, so close it and hold the turn.",
    "Your stance is 80% open, so close it and hold the turn.",
    "Wait 80 milliseconds longer, then close your stance.",
    "Your stance is 80 open, so close it and hold the turn.",  # unit dropped
    "Your stance is 80.0 degrees open, so close it.",  # digits not as written
    "Your stance is 8e1 degrees open, so close it.",
])
def test_a_unit_change_or_reformatted_number_falls_back(cue: str) -> None:
    with pytest.raises(CoachError, match="as written"):
        check_worded_cue(cue, STANCE_FACTS)


@pytest.mark.parametrize("cue", [
    "Your stance is 80 degrees open, so close it and hold the turn.",
    "Your stance is 80 deg open, so close it and hold the turn.",
    "Your stance is 80° open, so close it and hold the turn.",
    "An 80-degree open stance lets the hips fly, so close it.",
])
def test_the_same_number_and_unit_in_another_spelling_passes(cue: str) -> None:
    assert check_worded_cue(cue, STANCE_FACTS) == cue


def test_a_negative_measurement_quoted_with_its_sign_passes() -> None:
    for cue in ("You release -20 milliseconds before contact, so hold the cock.",
                "You release minus 20 ms before contact, so hold the cock."):
        assert check_worded_cue(cue, RELEASE_FACTS) == cue


def test_spelled_out_numbers_with_a_unit_fall_back() -> None:
    for cue in ("Your stance is eighty degrees open, so close it.", "Close your stance one degree more."):
        with pytest.raises(CoachError, match="spelled out"):
            check_worded_cue(cue, STANCE_FACTS)
    assert check_worded_cue("Hold one stance and close it before you swing.", STANCE_FACTS)  # "one" alone is fine


@pytest.mark.parametrize("cue", [
    "Your stance is -80 degrees open, so close it and hold the turn.",
    "Your stance is 80 percent open, so close it and hold the turn.",
])
def test_the_live_voice_uses_the_caption_after_a_sign_or_unit_change(env, result: dict, cue: str) -> None:
    env.keys("ANTHROPIC_API_KEY")
    env.claude.cue = cue
    assert voice_for_swing("sample", result) == {"cue": result["cue"], "audioUrl": None, "source": "caption"}


# ---- Review fix on #60: Claude may reword the coach's fix but never reverse it ---------

OVER_FACTS = {"measured": "Over-rotation: shoulders turn 120 degrees", "coach_cue": "Turn your shoulders less"}


def test_a_reversed_direction_is_rejected() -> None:
    with pytest.raises(CoachError, match="reverses the coach's fix"):
        check_worded_cue("Turn your shoulders more next swing", OVER_FACTS)


def test_the_same_direction_reworded_passes() -> None:
    assert check_worded_cue("Turn your shoulders a little less", OVER_FACTS) == "Turn your shoulders a little less"


def test_open_stance_fix_cannot_become_open_it_further(result: dict) -> None:
    facts = coach_facts(result)  # the real stance cue says both "open" (the fault) and "Close" (the fix)
    assert "open" in facts["coach_cue"] and "Close" in facts["coach_cue"]
    with pytest.raises(CoachError, match="reverses"):
        check_worded_cue("Open your stance further so your hips can turn.", facts)
    # Restating the fault while giving the fix is fine (the real cue Claude gave live).
    live = "Close your stance on this backhand, it's 80 degrees open, so your hips hold the turn longer."
    assert check_worded_cue(live, facts) == live


def test_a_reversed_cue_falls_back_to_the_caption_and_is_not_cached(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY")
    env.claude.cue = "Open your stance further so your hips can turn."
    assert voice_for_swing("sample", result) == {"cue": result["cue"], "audioUrl": None, "source": "caption"}
    assert not list(env.cache.glob("cue-*.json"))  # a rejected cue is never written to the cache


# ---- Review fix on #60: a bad cue cache file is a miss, never a 500 ---------------------

def _cue_file(env, result: dict) -> Path:
    return env.cache / f"cue-{live_voice._digest('sample', coach_facts(result))}.json"


@pytest.mark.parametrize("garbage", [b"\xff\xfe\x00not json at all", b"[1, 2, 3]", b'{"swing_id": "sample"}',
                                     b'{"cue": ""}', b'{"cue": 42}'])
def test_a_garbage_cue_cache_file_returns_the_caption_without_raising(env, result: dict, garbage: bytes) -> None:
    path = _cue_file(env, result)
    path.parent.mkdir(parents=True)
    path.write_bytes(garbage)
    assert voice_for_swing("sample", result) == {"cue": result["cue"], "audioUrl": None, "source": "caption"}
    assert not path.exists()  # the bad file is deleted, not served again


def test_a_garbage_cue_cache_file_is_rewritten_when_claude_is_available(env, result: dict) -> None:
    path = _cue_file(env, result)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00\x01truncated")
    env.keys("ANTHROPIC_API_KEY")
    out = voice_for_swing("sample", result)
    assert out["source"] == "claude" and len(env.claude.calls) == 1
    assert json.loads(path.read_bytes())["cue"] == out["cue"]


def test_a_garbage_entry_already_in_memory_is_dropped(env, result: dict) -> None:
    name = _cue_file(env, result).name
    live_voice._memory[name] = b"not json"
    assert voice_for_swing("sample", result)["source"] == "caption"
    assert name not in live_voice._memory


# ---- Review fix on #60: cached cues are re-checked before they're served ---------------

def test_a_cached_cue_that_reverses_the_fix_is_dropped_and_the_caption_returned(env) -> None:
    # Well-formed, as an older validator could have cached it, but "more" reverses "less".
    result = {"stroke": "forehand", "cue": "Turn your shoulders less",
              "fault": {"label": "Over-rotation: shoulders turn 120 deg", "cue": "Turn your shoulders less"}}
    path = env.cache / f"cue-{live_voice._digest('swing', coach_facts(result))}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"swing_id": "swing", "cue": "Turn your shoulders more"}))
    assert voice_for_swing("swing", result) == {"cue": "Turn your shoulders less", "audioUrl": None,
                                                "source": "caption"}
    assert not path.exists()
