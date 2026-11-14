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
    "Your stance is 80° open to the shot, so close it.",  # "close" kept >3 words from 80
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


# ---- Review fix on #60: any spelled-out number is rejected, whatever follows it --------
# The coach writes numbers as digits, so a number word can only be invented. "one" is
# allowed as everyday English, unless a unit-like noun follows it.

STANCE_LIVE_FACTS = {"measured": "Stance too open: stance 80 degrees open to the shot",
                     "coach_cue": "Your open stance lets your hips fly open early. Close it so you can hold the turn."}
LIVE_CUE = "Close your stance on this backhand, it's 80 degrees open, so your hips hold the turn longer."


@pytest.mark.parametrize("cue", [
    "Close your stance by two inches.",  # Codex's case: an unknown unit
    "Close your stance by half a foot.",
    "Close your stance one inch.",
    "Close your stance one more inch.",
    "Close your stance by twenty-five centimetres.",
    "Take a dozen swings with a closed stance.",
    "Close your stance a quarter turn.",
])
def test_any_spelled_out_number_is_rejected(cue: str) -> None:
    with pytest.raises(CoachError, match="spelled out a number"):
        check_worded_cue(cue, STANCE_LIVE_FACTS)


@pytest.mark.parametrize("facts, cue", [
    (OVER_FACTS, "Turn a little less, one smooth swing."),
    # ("one more swing" against a "less" fix is still rejected, by the direction guard's "more")
    (STANCE_LIVE_FACTS, "One more swing with a closed stance, so your hips hold the turn."),
    (STANCE_LIVE_FACTS, LIVE_CUE),  # the cue Claude gave live
    (STANCE_LIVE_FACTS, "Close your stance so your hips can hold the turn."),
    (STANCE_LIVE_FACTS, "Hold one closed stance so your hips keep the turn."),
])
def test_one_as_everyday_english_and_the_live_cues_still_pass(facts: dict, cue: str) -> None:
    assert check_worded_cue(cue, facts) == cue


# ---- Review fix on #60: cues with no direction to guard are spoken verbatim ------------

from coach.faults import FAULTS  # noqa: E402


def _fault_result(fault_id: str, label: str) -> dict:
    cue = FAULTS[fault_id]["cue"]
    return {"stroke": "forehand", "cue": cue, "fault": {"label": label, "cue": cue, "tip": None}}


def test_only_the_wrist_cues_are_unguarded_today() -> None:
    unguarded = {fid for fid, spec in FAULTS.items() if not live_voice.guarded({"coach_cue": spec["cue"]})}
    assert unguarded == {"early_wrist_snap", "rolled_wrist"}


@pytest.mark.parametrize("fault_id, label", [
    ("early_wrist_snap", "Early wrist snap: wrist uncocks 61 deg before contact"),
    ("rolled_wrist", "Rolled wrist: forearm rolls 45 deg through contact"),
])
def test_an_unguarded_coach_cue_is_spoken_verbatim_without_claude(env, fault_id: str, label: str) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    env.claude.cue = "Snap your wrist before contact."  # the reversal Claude must never get to say
    out = voice_for_swing(f"swing-{fault_id}", _fault_result(fault_id, label))
    coach_cue = FAULTS[fault_id]["cue"]
    assert out["cue"] == coach_cue and out["source"] == "caption"
    assert env.claude.calls == []  # Claude isn't called at all
    assert env.spoken == [coach_cue] and _audio(out["audioUrl"]) == MP3  # the coach's own words are voiced


def test_an_old_cached_claude_cue_for_an_unguarded_fault_is_not_served(env) -> None:
    result = _fault_result("early_wrist_snap", "Early wrist snap: wrist uncocks 61 deg before contact")
    path = env.cache / f"cue-{live_voice._digest('wrist', coach_facts(result))}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"swing_id": "wrist", "cue": "Snap your wrist before contact."}))
    assert voice_for_swing("wrist", result)["cue"] == FAULTS["early_wrist_snap"]["cue"]


def test_guarded_turn_and_stance_cues_still_go_through_claude(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY")
    over = _fault_result("over_rotation", "Over-rotation: hips turn 110 deg")
    env.claude.cue = "Turn a little less and stay balanced."
    assert voice_for_swing("over", over) == {"cue": "Turn a little less and stay balanced.", "audioUrl": None,
                                            "source": "claude"}
    env.claude.cue = "Close your stance so your hips can hold the turn."
    assert voice_for_swing("sample", result)["source"] == "claude"  # the real stance result
    assert len(env.claude.calls) == 2


# ---- Review fix on #60: Claude + ElevenLabs finish inside the proxy's 30 s ---------------

def test_claude_has_no_retries_and_a_10_second_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_voice, "require_env", lambda name: "test-not-real")  # never read .env.local
    client = live_voice.make_client()
    assert client.max_retries == 0 and client.timeout == 10.0


def test_elevenlabs_gets_the_short_live_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake(text: str, timeout_s: float = 99) -> bytes:
        seen["timeout_s"] = timeout_s
        return MP3

    monkeypatch.setattr("coach.voice.synthesize", fake)
    assert live_voice.synthesize("Close your stance.") == MP3
    assert seen["timeout_s"] == live_voice.TTS_TIMEOUT_S
    assert live_voice.CLAUDE_TIMEOUT_S + live_voice.TTS_TIMEOUT_S <= 25  # proxy aborts at 30 s


def test_timeouts_still_fall_back_to_the_caption_and_no_audio(env, result: dict) -> None:
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    env.claude.error = anthropic.APITimeoutError(request=None)  # type: ignore[arg-type]
    env.voice_error = VoiceError("Could not reach ElevenLabs. Check the internet connection.")
    assert voice_for_swing("sample", result) == {"cue": result["cue"], "audioUrl": None, "source": "caption"}


def test_voice_synthesize_default_timeout_is_unchanged() -> None:
    import inspect

    from coach import voice

    assert inspect.signature(voice.synthesize).parameters["timeout_s"].default == voice.TIMEOUT_S == 20


# ---- Retry after a failure once it is 60 s old -------------------------------------------

def test_a_failed_call_is_retried_after_60_seconds(env, result: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(live_voice, "_now", lambda: clock["t"])
    env.keys("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY")
    env.claude.error = anthropic.APITimeoutError(request=None)  # type: ignore[arg-type]
    env.voice_error = VoiceError("Could not reach ElevenLabs.")
    assert voice_for_swing("sample", result)["source"] == "caption"
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1

    clock["t"] += 59  # still inside the window: no retry
    voice_for_swing("sample", result)
    assert len(env.claude.calls) == 1 and len(env.spoken) == 1

    clock["t"] += 2  # 61 s after the failure: both APIs are tried again
    env.claude.error, env.voice_error = None, None
    out = voice_for_swing("sample", result)
    assert out["source"] == "claude" and _audio(out["audioUrl"]) == MP3
    assert len(env.claude.calls) == 2  # the cue retried
    assert env.spoken[-1] == out["cue"]  # the audio retried, for the new cue


def test_a_failed_audio_alone_is_retried_after_60_seconds(env, result: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"t": 0.0}
    monkeypatch.setattr(live_voice, "_now", lambda: clock["t"])
    env.keys("ELEVENLABS_API_KEY")
    env.voice_error = VoiceError("quota")
    assert voice_for_swing("sample", result)["audioUrl"] is None
    clock["t"] = 61.0
    env.voice_error = None
    assert _audio(voice_for_swing("sample", result)["audioUrl"]) == MP3
    assert env.spoken == [result["cue"], result["cue"]]


# ---- Stricter cue check: no number as an amount, no negations, more number words ---------

OVER95_FACTS = {"measured": "Over-rotation: hips turn 95 degrees",
                "coach_cue": "Turn a little less and stay balanced through the ball."}
UNDER_FACTS = {"measured": "Under-rotation: shoulders turn 40 degrees",
               "coach_cue": "Turn your shoulders further before you swing."}


def test_a_number_next_to_a_change_word_is_rejected() -> None:
    with pytest.raises(CoachError, match="next to a change"):
        check_worded_cue("Turn 95 degrees less", OVER95_FACTS)
    with pytest.raises(CoachError, match="next to a change"):
        check_worded_cue("Close your stance by 80 degrees.", STANCE_LIVE_FACTS)


def test_restating_the_measurement_is_not_a_change() -> None:
    assert check_worded_cue(LIVE_CUE, STANCE_LIVE_FACTS) == LIVE_CUE  # "80 degrees open" is the label's own phrase
    ok = "Your hips turn 95 degrees, so turn a little less."  # "less" is more than 3 words from 95
    assert check_worded_cue(ok, OVER95_FACTS) == ok


@pytest.mark.parametrize("facts, cue", [
    (UNDER_FACTS, "Don't turn your shoulders further"),
    (STANCE_LIVE_FACTS, "Stop closing your stance so much"),
    (UNDER_FACTS, "Don’t rush, turn your shoulders further."),  # curly apostrophe
    (UNDER_FACTS, "Do not stop the turn early, go further."),
    (OVER95_FACTS, "Never turn more than you need."),
    (STANCE_LIVE_FACTS, "Avoid opening your stance, close it."),
    (STANCE_LIVE_FACTS, "No longer leave your stance open, close it."),
])
def test_negations_are_rejected(facts: dict, cue: str) -> None:
    with pytest.raises(CoachError, match="negates"):
        check_worded_cue(cue, facts)


@pytest.mark.parametrize("cue", [
    "Close your stance twice as much.",
    "Double the turn in your stance.",
    "Triple your stance width.",
    "Close your stance by a third.",
    "Close it by thirds.",
    "Close it a couple of inches.",
])
def test_the_new_number_words_are_rejected(cue: str) -> None:
    with pytest.raises(CoachError, match="spelled out a number"):
        check_worded_cue(cue, STANCE_LIVE_FACTS)
