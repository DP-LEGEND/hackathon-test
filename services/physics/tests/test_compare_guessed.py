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
