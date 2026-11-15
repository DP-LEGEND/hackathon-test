"""compare() never shows or edits a number read from a guessed joint."""

import json
from pathlib import Path

import pytest

from physics.compare import GuessedFixError, compare

SWINGS = Path(__file__).resolve().parents[3] / "public" / "swings"


def _unflagged(path: str) -> dict:
    s = json.loads((SWINGS / path).read_text())
    for f in s["frames"]:
        f.pop("filled", None)
        f.pop("visibility", None)
    return s


def _wrist_guessed() -> dict:
    s = _unflagged("swing_2116_bh_stereo.json")
    for k in range(56, 63):
        s["frames"][k]["filled"] = [False] * 33
        s["frames"][k]["filled"][16] = True  # right wrist guessed around contact (59)
    return s


def test_unflagged_swing_keeps_every_metric():
    r = compare(_unflagged("swing_fh_over_rotation.json"), "turn_shoulders_less", 20, fps_real=120, hand="R",
                side="forehand")
    assert r["notMeasured"] == {}
    assert set(r["delta"]["metrics"]) == set(r["you"]["metrics"]) and len(r["you"]["metrics"]) == 5


def test_guessed_metrics_are_left_out_not_shown():
    r = compare(_wrist_guessed(), "turn_shoulders_more", 15, fps_real=120, hand="R", side="backhand")
    for k in ("wrist_at_contact_deg", "wrist_release_ms", "stance_open_deg", "elbow_at_contact_deg"):
        assert k in r["notMeasured"], k
        assert k not in r["delta"]["metrics"] and k not in r["you"]["metrics"] and k not in r["ghost"]["metrics"]
    assert list(r["delta"]["metrics"]) == ["shoulder_turn_deg"]
    assert not any("wrist" in line or "stance" in line or "elbow" in line for line in r["delta"]["summary"])


@pytest.mark.parametrize("fix,joint", [("straighten_elbow", "elbow"), ("bend_elbow", "elbow"),
                                       ("hold_wrist_cock", "wrist"), ("close_stance", "wrist")])
def test_fix_editing_a_guessed_measurement_is_refused(fix, joint):
    with pytest.raises(GuessedFixError, match=f"couldn't see the right {joint} around contact"):
        compare(_wrist_guessed(), fix, 10, fps_real=120, hand="R", side="backhand")


def test_amount_zero_unchanged_comparison_always_works():
    r = compare(_wrist_guessed(), "straighten_elbow", 0.0, fps_real=120, hand="R", side="backhand")
    assert r["fix"]["amount"] == 0.0 and "elbow_at_contact_deg" in r["notMeasured"]


def test_shoulder_fixes_are_refused_when_shoulders_are_guessed():
    s = _wrist_guessed()
    for f in s["frames"]:
        f["filled"] = (f.get("filled") or [False] * 33)
        f["filled"][12] = True
    with pytest.raises(GuessedFixError, match="couldn't see the right shoulder"):
        compare(s, "turn_shoulders_more", 15, fps_real=120, hand="R", side="backhand")


def test_racket_and_ball_speed_flagged_when_wrist_guessed_at_contact():
    r = compare(_wrist_guessed(), "turn_shoulders_more", 15, fps_real=120, hand="R", side="backhand")
    for k in ("racket_speed", "ball_speed"):
        assert "joint 16" in r["notMeasured"][k]
    assert r["you"]["ball"]["speedKmh"] > 0  # still predicted and shown, just flagged


def test_unflagged_swing_has_no_speed_flags():
    r = compare(_unflagged("swing_fh_over_rotation.json"), "turn_shoulders_less", 20, fps_real=120, hand="R",
                side="forehand")
    assert "racket_speed" not in r["notMeasured"]


@pytest.mark.parametrize("flag,joint,why", [("filled", 16, "joint 16 filled at frame 48"),
                                            ("visibility", 14, "joint 14 visibility 0.30 at contact")])
def test_no_aim_is_held_on_a_guessed_arm(flag, joint, why):
    # Codex P2 on #73: the straight-drive hold turns the racket line, which runs from the elbow
    # through the wrist. If either is guessed at contact, nothing is held and `why` says so.
    s = _unflagged("swing_fh_over_rotation.json")
    s["frames"][48][flag] = [False] * 33 if flag == "filled" else [0.99] * 33
    s["frames"][48][flag][joint] = True if flag == "filled" else 0.3
    kw = dict(fps_real=120, hand="R", side="forehand")
    r = compare(s, "turn_shoulders_less", 52.6, intent="straight drive", **kw)
    aim = r["assumptions"]["aim"]
    assert aim["applied"] is False and why in aim["why"] and "guessed" in aim["why"]
    assert "aiming" not in r["fix"] and "Aiming" not in r["assumptions"]["note"]
    assert r["ghost"] == compare(s, "turn_shoulders_less", 52.6, intent=None, **kw)["ghost"]
