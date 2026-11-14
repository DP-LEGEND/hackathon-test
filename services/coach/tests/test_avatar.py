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


# ---- Review fix on #38: a fallback ghost is never passed off as the spoken fix -----

def test_fallback_ghost_is_named_not_claimed() -> None:
    # Codex P2: top fault not animatable (rolling wrist) + an animatable stance ghost.
    result = _fault_result(
        "forehand", "rolling_wrist",
        ghost_fault={"id": "stance_too_open", "fix": "close_stance"},
        ghost_fixes=[{"fix": "close_stance", "amount": 45}],
        ghost_note="The ghost shows the next fix, because the top one isn't animated yet.")
    lines = script_from_result(result)["lines"]
    assert lines[1] == FAULTS["rolling_wrist"]["cue"]
    assert lines[2] == "Your ghost can't show that fix yet, so it shows another one: closing the stance."
    assert GHOST_LINE not in lines and GHOST_PAIR_LINE not in lines
    assert "makes that change" not in " ".join(lines)


def test_fallback_pair_is_named_by_its_primary_fix_not_the_pair_line() -> None:
    result = _fault_result(
        "forehand", "rolling_wrist", ghost_fault={"id": "over_rotation", "fix": "turn_shoulders_less"},
        ghost_fixes=[{"fix": "turn_shoulders_less", "amount": 15}, {"fix": "close_stance", "amount": 45}])
    line = script_from_result(result)["lines"][2]
    assert line.endswith("turning the shoulders a little less.") and line != GHOST_PAIR_LINE


def test_unknown_fallback_fix_uses_ghost_note_or_drops_the_line() -> None:
    note = "The ghost shows the next fix, because the top one isn't animated yet."
    unknown = {"id": "stance_too_open", "fix": "some_new_fix"}
    with_note = script_from_result(_fault_result("forehand", "rolling_wrist", ghost_fault=unknown, ghost_note=note))
    assert with_note["lines"][2] == note
    without = script_from_result(_fault_result("forehand", "rolling_wrist", ghost_fault=unknown))
    assert len(without["lines"]) == 2


def test_every_fix_phrase_fits_the_line_limit() -> None:
    from coach.avatar import FIX_PHRASES, GHOST_OTHER_LINE
    from physics.ghost import FIXES

    assert set(FIXES) <= set(FIX_PHRASES), "every physics fix needs a spoken phrase"
    for phrase in FIX_PHRASES.values():
        assert len(GHOST_OTHER_LINE.format(fix=phrase).split()) <= MAX_WORDS


def test_real_coach_result_with_a_fallback_ghost(monkeypatch: pytest.MonkeyPatch, sample: dict) -> None:
    """End to end through coach_swing: top fault can't be animated, the next one can."""
    from coach.agent import GHOST_SHOWS_NEXT
    from physics.ghost import FIXES

    monkeypatch.delitem(FIXES, "bend_elbow", raising=False)  # straight arm: no ghost
    rules = THRESHOLDS["backhand"]
    m: dict = {"stroke": "backhand", "stroke_source": "given"}
    for rule in rules.values():
        m.setdefault(rule["measurement"], rule["target"])
    m["elbow_min_before_deg"] = rules["straight_arm"]["severe_at"]  # priority 1, not animatable
    m["wrist_uncock_ms"] = rules["early_wrist_snap"]["severe_at"]  # priority 4, animatable
    monkeypatch.setattr("coach.agent.measure_swing", lambda swing, stroke, fps_real: m)

    script = avatar_script(sample, stroke="backhand")
    assert script["fault"] == "straight_arm"
    assert script["lines"][1] == FAULTS["straight_arm"]["cue"]
    assert script["lines"][2] == "Your ghost can't show that fix yet, so it shows another one: holding the wrist cock longer."
    from coach.agent import coach_swing
    assert coach_swing(sample, stroke="backhand")["ghost_note"] == GHOST_SHOWS_NEXT
