"""Tests for the avatar's spoken lines. Offline: no Anam, no ElevenLabs, no Claude."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coach import avatar
from coach.avatar import (
    GHOST_LINE, GHOST_PAIR_LINE, MAX_WORDS, NO_FAULT_LINES, avatar_script, script_from_result,
    speak_avatar_script,
)
from coach.cue import _numbers_in
from coach.faults import FAULTS, THRESHOLDS, detect_faults

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "swing_sample.json"
STROKES = ("forehand", "backhand")


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text())


@pytest.fixture(autouse=True)
def no_anam(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never read the real .env.local here; start with Anam not configured."""
    monkeypatch.setattr(avatar, "load_env", lambda: None)
    monkeypatch.delenv("ANAM_API_KEY", raising=False)


def _fault_result(stroke: str, fault_id: str, **extra) -> dict:
    rule = THRESHOLDS[stroke][fault_id]
    m: dict = {"stroke": stroke, rule["measurement"]: rule["severe_at"]}
    fault = next(f for f in detect_faults({}, metrics=m) if f["id"] == fault_id)
    return {"fault": fault, "ghost_fault": None, "ghost_fixes": [], **extra}


def test_sample_script_has_short_lines_and_elevenlabs_voice(sample: dict) -> None:
    script = avatar_script(sample, stroke="backhand")
    assert 2 <= len(script["lines"]) <= 3
    assert all(0 < len(line.split()) <= MAX_WORDS for line in script["lines"])
    assert script["voice"] == "elevenlabs" and script["fault"] == "stance_too_open"
    assert script["lines"][1] == FAULTS["stance_too_open"]["cue"]
    assert script["lines"][2] == FAULTS["stance_too_open"]["tip"]


def test_lines_only_say_numbers_the_coach_measured(sample: dict) -> None:
    from coach.agent import coach_swing

    for stroke in STROKES:
        result = coach_swing(sample, stroke=stroke)
        measured = {f"{result['fault']['value']:.0f}"}
        said = {f"{float(n):.0f}" for line in script_from_result(result)["lines"] for n in _numbers_in(line)}
        assert said <= measured, (stroke, said, measured)


def test_units_are_spoken_in_words(sample: dict) -> None:
    text = " ".join(avatar_script(sample, stroke="backhand")["lines"])
    assert " degrees" in text and " deg " not in text and not text.endswith(" deg.")


@pytest.mark.parametrize("stroke", STROKES)
@pytest.mark.parametrize("fault_id", sorted(FAULTS))
def test_every_fault_fits_the_avatar_limits(stroke: str, fault_id: str) -> None:
    script = script_from_result(_fault_result(stroke, fault_id, ghost_fault={"id": fault_id}))
    assert 2 <= len(script["lines"]) <= 3
    assert all(len(line.split()) <= MAX_WORDS for line in script["lines"])
    assert script["lines"][1] == FAULTS[fault_id]["cue"]


def test_third_line_is_tip_then_ghost_pair_then_ghost() -> None:
    with_tip = script_from_result(_fault_result("forehand", "stance_too_open"))
    assert with_tip["lines"][2] == FAULTS["stance_too_open"]["tip"]

    pair = script_from_result(_fault_result(
        "forehand", "over_rotation", ghost_fault={"id": "over_rotation"},
        ghost_fixes=[{"fix": "turn_shoulders_less", "amount": 15}, {"fix": "close_stance", "amount": 45}]))
    assert pair["lines"][2] == GHOST_PAIR_LINE

    single = script_from_result(_fault_result("forehand", "over_rotation", ghost_fault={"id": "over_rotation"}))
    assert single["lines"][2] == GHOST_LINE

    no_ghost = script_from_result(_fault_result("forehand", "over_rotation"))
    assert len(no_ghost["lines"]) == 2


def test_no_fault_script() -> None:
    script = script_from_result({"fault": None})
    assert script["lines"] == NO_FAULT_LINES and script["fault"] is None


def test_anam_is_the_voice_only_when_configured(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    assert avatar_script(sample, stroke="backhand")["voice"] == "elevenlabs"
    monkeypatch.setenv("ANAM_API_KEY", "test-not-real")
    assert avatar_script(sample, stroke="backhand")["voice"] == "anam"
    monkeypatch.setenv("ANAM_API_KEY", "   ")
    assert avatar_script(sample, stroke="backhand")["voice"] == "elevenlabs"


def test_elevenlabs_voices_the_lines_when_anam_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_speak(text: str, out_path=None) -> Path:
        calls.append(text)
        return tmp_path / "cue.mp3"

    monkeypatch.setattr("coach.voice.speak_cue", fake_speak)
    script = script_from_result(_fault_result("backhand", "straight_arm"), voice="elevenlabs")
    assert speak_avatar_script(script) == tmp_path / "cue.mp3"
    assert calls == [" ".join(script["lines"])]

    calls.clear()
    anam = script_from_result(_fault_result("backhand", "straight_arm"), voice="anam")
    assert speak_avatar_script(anam) is None and calls == []  # the web avatar speaks


def test_too_long_lines_are_rejected() -> None:
    with pytest.raises(ValueError, match="words"):
        avatar._check(["one two three.", " ".join(["word"] * (MAX_WORDS + 1))])
    with pytest.raises(ValueError, match="lines"):
        avatar._check(["only one line."])
