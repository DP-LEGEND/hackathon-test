"""Live clips never abort on guessed joints: they publish an unchanged comparison instead."""

import json
import math
from pathlib import Path

import numpy as np

from coach.agent import coach_swing
from coach.faults import measure_swing
from pipeline.live import live_comparison

SAMPLE = Path(__file__).resolve().parents[3] / "public" / "swings" / "swing_2116_bh_stereo.json"


def _backhand() -> dict:
    s = json.loads(SAMPLE.read_text())
    s["fpsReal"] = 120.0
    s.setdefault("metadata", {})["hand"] = "R"
    return s


def _open_feet(s: dict, degrees: float = 60.0) -> dict:
    """Turn the right leg's foot points about the left ankle in the floor plane (feet more open)."""
    a = math.radians(degrees)
    rot = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    for f in s["frames"]:
        J = np.array(f["joints"])
        pivot = J[27].copy()
        for j in (28, 30, 32):
            J[j] = pivot + rot @ (J[j] - pivot)
        f["joints"] = J.tolist()
    return s


def test_no_fault_swing_with_guessed_elbow_gets_unchanged_comparison():
    s = _backhand()  # right elbow and wrist are guessed around contact in this sample
    coached = coach_swing(s, "backhand", 120)
    assert coached["fault"] is None
    comparison = live_comparison(s, coached, "R")
    assert comparison["noCorrection"] is True
    assert comparison["fix"]["amount"] == 0.0


def test_guessed_wrist_backhand_with_open_feet_is_measured_but_not_ghosted():
    s = _open_feet(_backhand())
    m = measure_swing(s, "backhand", 120)
    assert m["stance_direction"] == "front_wall_axis" and m["stance_open_deg"] > 40
    coached = coach_swing(s, "backhand", 120)
    stance = [f for f in [coached["fault"]] if f and f["id"] == "stance_too_open"]
    assert stance and stance[0]["ghost_ready"] is False
    comparison = live_comparison(s, coached, "R")
    assert comparison["noCorrection"] is True
