"""The racket face from the forearm roll (physics/wrist_face.py) and how compare() aims with it.

Swings are mock data from swing_factory; the wrist entries are hand-made. The last tests guard
the locked demo numbers: with no sensor data, nothing changes.
"""

import json
from pathlib import Path

import pytest

from physics.compare import GuessedFixError, compare
from physics.tests.swing_factory import make_swing
from physics.wrist_face import (
    FACE_CAP_DEG, FACE_PER_ROLL_DEG, GOOD_ROLL_DEG, MOCK_GOOD_ROLL_DEG, cross_court_sign, face_deg, good_roll,
    sensor_roll,
)

SWINGS = Path(__file__).resolve().parents[3] / "public" / "swings"


@pytest.fixture(scope="module")
def good():
    return make_swing()


def with_roll(swing: dict, roll: float, mock: bool = False) -> dict:
    return {**swing, "wrist": {"usable": True, "mock": mock, "roll_change_abs_deg": roll, "roll_change_deg": roll}}


def aims(r: dict) -> tuple[float, float]:
    launch = r["assumptions"]["launch"]
    return launch["you"]["azimuth"]["value"], launch["ghost"]["azimuth"]["value"]


# ---- the face model ------------------------------------------------------------------

def test_face_is_the_assumed_factor_times_the_roll_above_the_good_median_capped() -> None:
    assert FACE_PER_ROLL_DEG == 0.3 and FACE_CAP_DEG == 15.0
    assert face_deg(99.3, 99.3) == 0.0 and face_deg(80.0, 99.3) == 0.0   # at or below the median: square
    assert face_deg(137.6, 99.3) == pytest.approx(0.3 * 38.3, abs=0.05)   # a typical rolled backhand: 11.5
    assert face_deg(400.0, 99.3) == FACE_CAP_DEG


def test_good_median_is_per_stroke_and_mock_has_its_own() -> None:
    assert good_roll("backhand", False) == GOOD_ROLL_DEG["backhand"] == 99.3
    assert good_roll("forehand", False) == GOOD_ROLL_DEG["forehand"] == 136.8
    assert good_roll("forehand", True) == good_roll("backhand", True) == MOCK_GOOD_ROLL_DEG == 16.5


def test_cross_court_is_the_far_side_from_the_drive_spot() -> None:
    assert cross_court_sign(5.4) == -1.0   # right-handed forehand, right of centre: towards the left wall
    assert cross_court_sign(2.0) == +1.0   # right-handed backhand: towards the right wall
    assert cross_court_sign(1.0) == +1.0 and cross_court_sign(4.4) == -1.0  # left-hander, mirrored


def test_only_a_usable_entry_with_a_roll_counts() -> None:
    assert sensor_roll({}) is None
    assert sensor_roll({"wrist": {"usable": False, "roll_change_abs_deg": 60}}) is None
    assert sensor_roll({"wrist": {"usable": True, "roll_change_abs_deg": None}}) is None
    assert sensor_roll(with_roll({}, 60.8, mock=True)) == {"roll": 60.8, "mock": True}


# ---- compare() with wrist-sensor data -------------------------------------------------

@pytest.mark.parametrize("side", ["forehand", "backhand"])
def test_rolled_ball_goes_cross_court_and_the_firm_wrist_ghost_goes_straight(good, side: str) -> None:
    median = GOOD_ROLL_DEG[side]
    roll = median + 38.3                          # ~ a typical rolled real backhand above its median
    r = compare(with_roll(good, roll), "firm_wrist", roll - median, side=side)   # the coach's amount
    you, ghost = aims(r)
    sign = -1 if side == "forehand" else 1        # right-handed: forehand cross-court = left wall
    assert you == pytest.approx(sign * 0.3 * 38.3, abs=0.05) and ghost == 0.0
    face = r["assumptions"]["face"]
    assert face["you"]["faceDeg"] > 0 and face["ghost"] == {"rollDeg": median, "faceDeg": 0.0}
    assert face["assumed"] is True and face["label"] == "ASSUMED" and face["intent"]["value"] == "straight drive"
    # where the PREDICTED balls meet the front wall: the ghost's straight in front of the drive spot,
    # yours over a metre towards the cross-court side (the mock swing is fast, so both may go out)
    you_x, ghost_x = (next(e["point"][0] for e in r[s]["ball"]["events"] if e["type"] == "front_wall")
                      for s in ("you", "ghost"))
    assert ghost_x == pytest.approx(r["assumptions"]["anchor"]["x"], abs=0.01)
    assert sign * (you_x - ghost_x) > 1.0
    assert r["delta"]["ball"]["label"] == "PREDICTED" and r["you"]["ball"]["predicted"] is True
    # only the aim changes: the body, the racket speed and the launch angle are the same
    assert r["you"]["racketSpeed"]["value"] == r["ghost"]["racketSpeed"]["value"]
    assert r["ghost"]["swing"]["frames"] == r["you"]["swing"]["frames"]


def test_the_caveat_says_assumed_next_to_the_factor(good) -> None:
    r = compare(with_roll(good, 140.0), "firm_wrist", 40.7, side="backhand")
    note = r["assumptions"]["note"]
    assert note.startswith("Ball paths are PREDICTED.")
    assert "assumed to turn 0.3° per degree of forearm roll" in note and "capped at 15°" in note
    method = r["assumptions"]["launch"]["you"]["azimuth"]["method"]
    assert "face assumed 0.3 deg per degree of roll above the good median (not measured)" in method
    assert r["assumptions"]["launch"]["you"]["azimuth"]["cameraAim"]["label"] in ("ESTIMATE", "ASSUMED")


def test_mock_roll_uses_the_mock_median_and_says_mock(good) -> None:
    r = compare(with_roll(good, 60.8, mock=True), "firm_wrist", 60.8 - 16.5, side="forehand")
    you, ghost = aims(r)
    assert you == pytest.approx(-13.3) and ghost == 0.0
    az = r["assumptions"]["launch"]["you"]["azimuth"]
    assert az["label"] == "MOCK (sensor)" and az["method"].count("MOCK forearm roll") == 1
    assert "MOCK forearm roll" in r["assumptions"]["note"] and r["assumptions"]["face"]["mock"] is True


def test_other_fixes_keep_your_face(good) -> None:
    r = compare(with_roll(good, 140.0), "straighten_elbow", 12, side="backhand")
    you, ghost = aims(r)
    assert you == ghost == pytest.approx(0.3 * (140.0 - 99.3), abs=0.05)


def test_a_partial_firm_wrist_only_partly_squares_the_face(good) -> None:
    r = compare(with_roll(good, 139.3), "firm_wrist", 20.0, side="backhand")   # 40 above -> 20 above
    assert r["assumptions"]["face"]["ghost"] == {"rollDeg": 119.3, "faceDeg": 6.0}


def test_the_face_is_capped(good) -> None:
    r = compare(with_roll(good, 99.3 + 80), "firm_wrist", 0.0, side="backhand")
    az = r["assumptions"]["launch"]["you"]["azimuth"]
    assert az["value"] == FACE_CAP_DEG and az["clamped"] is True


def test_firm_wrist_needs_sensor_data(good) -> None:
    with pytest.raises(GuessedFixError, match="needs the forearm roll from a wrist sensor"):
        compare(good, "firm_wrist", 20)
    with pytest.raises(GuessedFixError):
        compare({**good, "wrist": {"usable": False, "skip_reason": "sync off"}}, "firm_wrist", 20)
    r = compare(good, "firm_wrist", 0)       # amount 0 = unchanged, as for every fix
    assert "face" not in r["assumptions"]


# ---- no sensor data: nothing changes ---------------------------------------------------

def test_without_sensor_data_there_is_no_face_and_the_note_is_unchanged(good) -> None:
    r = compare(good, "straighten_elbow", 12)
    assert "face" not in r["assumptions"]
    assert "Aim:" not in r["assumptions"]["note"] and "cameraAim" not in r["assumptions"]["launch"]["you"]["azimuth"]


def _saved(entry_id: str, fix: str) -> tuple[dict, dict, float]:
    cat = json.loads((SWINGS / "catalogue.json").read_text())
    e = next(s for s in cat["swings"] if s["id"] == entry_id)
    saved = json.loads((SWINGS / e["fixes"][fix]["file"]).read_text())
    return json.loads((SWINGS / e["swing"]).read_text()), saved, e["fixes"][fix]["amount"]


def test_locked_hero_numbers_are_unchanged() -> None:
    swing, saved, amount = _saved("7178110a0b06-swing-0027", "turn_shoulders_less")
    r = compare(swing, "turn_shoulders_less", amount, fps_real=saved["fpsReal"])
    ball = r["delta"]["ball"]
    assert (ball["speedKmh"]["you"], ball["speedKmh"]["ghost"]) == (133.2, 119.1)
    assert (ball["frontWallHeightM"]["you"], ball["frontWallHeightM"]["ghost"]) == (1.92, 1.88)
    assert "face" not in r["assumptions"]


def test_locked_backhand_numbers_are_unchanged() -> None:
    swing, saved, amount = _saved("sample_2116_backhand_stereo", "turn_shoulders_more")
    r = compare(swing, "turn_shoulders_more", amount, fps_real=saved["fpsReal"])
    assert r["you"]["ball"]["speedKmh"] == 130.4 and round(r["you"]["ball"]["frontWallHeightM"], 2) == 0.78
    assert "face" not in r["assumptions"]
