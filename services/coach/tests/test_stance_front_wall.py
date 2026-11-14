"""Stance is a feet measurement: a guessed hitting wrist must not drop the stance check."""

import copy
import json
from pathlib import Path

import pytest

from coach.faults import measure_swing
from coach.measure_extra import stance_open_front_wall_deg

SAMPLE = Path(__file__).resolve().parents[3] / "public" / "swings" / "swing_2116_bh_stereo.json"


def _swing(flag_wrist: bool = False, flag_ankle: bool = False) -> dict:
    s = json.loads(SAMPLE.read_text())
    s = copy.deepcopy(s)
    for f in s["frames"]:
        f["filled"] = [False] * 33
        f["visibility"] = [1.0] * 33
    c = 59
    for k in range(c - 3, c + 4):
        if flag_wrist:
            s["frames"][k]["filled"][16] = True
        if flag_ankle:
            s["frames"][k]["filled"][27] = True
    return s


def test_unflagged_uses_hitting_direction():
    m = measure_swing(_swing(), "backhand", 120)
    assert m["stance_direction"] == "hitting_direction"
    assert "stance_open_deg" not in m["guessed_joints"]


def test_guessed_wrist_judges_feet_against_front_wall():
    s = _swing(flag_wrist=True)
    m = measure_swing(s, "backhand", 120)
    assert m["stance_direction"] == "front_wall_axis"
    assert "stance_open_deg" not in m["guessed_joints"]
    assert m["stance_open_deg"] == pytest.approx(stance_open_front_wall_deg(s, m["contact_frame"]))
    assert 0.0 <= m["stance_open_deg"] <= 90.0


def test_guessed_ankle_still_skips_stance():
    m = measure_swing(_swing(flag_wrist=True, flag_ankle=True), "backhand", 120)
    assert m["stance_open_deg"] is None


def test_front_wall_axis_ignores_direction_sign():
    s = _swing()
    flipped = copy.deepcopy(s)
    for f in flipped["frames"]:
        f["joints"] = [[-x, y, -z] for x, y, z in f["joints"]]  # pipeline frame -> court frame
    assert stance_open_front_wall_deg(flipped, 59) == pytest.approx(stance_open_front_wall_deg(s, 59), abs=1e-6)
