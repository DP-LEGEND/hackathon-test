"""rolled_wrist on REAL swings: the per-swing numbers the committed thresholds were tuned on.

One shadow session (no ball), 14 Nov 2026: a phone strapped to the hitting forearm, 15 good
and 14 rolled-wrist backhands, 10 good and 11 rolled forehands, labelled by block. Each number
is the size of the forearm roll (the gyro integrated about the forearm's own axis, wrist.metrics
swing_metrics(..., roll_from="gyro")) over -150..+100 ms around the forearm's fastest turn,
which stands in for contact. Backhands roll one way (+), forehands the other (-); the coach
reads the size (roll_change_abs_deg). Kept here as constants: no sensor files in the repo.

Caveat these tests can't see: the split depends on where contact sits. Moving it 25 ms
earlier makes good and rolled overlap on both strokes, so retune once real hits (contact
from the ball's impact) are in.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from coach.faults import THRESHOLDS, detect_faults

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "samples" / "swing_sample.json"

# swing number -> roll size in degrees, per block ("bh-good-01" is BH_GOOD["01"])
BH_GOOD = {
    "01": 112.7, "02": 116.9, "03": 117.7, "04": 114.6, "05": 99.9, "06": 95.9, "07": 99.3,
    "08": 95.6, "09": 97.8, "10": 98.9, "11": 120.3, "12": 98.9, "13": 99.0, "14": 98.0,
    "15": 114.1,
}
BH_ROLLED = {
    "01": 132.4, "02": 141.7, "03": 145.6, "04": 138.9, "05": 130.1, "06": 134.9, "07": 141.3,
    "08": 134.8, "09": 137.8, "10": 128.3, "11": 149.7, "12": 143.4, "13": 136.8, "14": 130.2,
}
FH_GOOD = {
    "01": 140.5, "02": 137.4, "03": 121.8, "04": 144.8, "05": 136.1, "06": 143.6, "07": 142.5,
    "08": 119.8, "09": 135.1, "10": 120.9,
}
FH_ROLLED = {
    "01": 165.0, "02": 159.5, "03": 154.4, "04": 161.3, "05": 158.8, "06": 146.7, "07": 157.7,
    "08": 148.1, "09": 160.5, "10": 161.2, "11": 155.6,
}
SESSION = {"backhand": (BH_GOOD, BH_ROLLED), "forehand": (FH_GOOD, FH_ROLLED)}
CASES = [(stroke, f"{stroke[:2]}-{label}-{n}", roll, label == "rolled")
         for stroke, (good, rolled) in SESSION.items()
         for label, block in (("good", good), ("rolled", rolled))
         for n, roll in block.items()]


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text())


def with_roll(sample: dict, swing_id: str, roll: float, sign: int) -> dict:
    """The sample swing carrying one real swing's wrist numbers (real, not mock)."""
    wrist = {"usable": True, "mock": False, "roll_change_deg": sign * roll, "roll_change_abs_deg": roll,
             "peak_roll_rate_abs_dps": 900.0, "peak_angular_speed_dps": 1500.0, "skip_reason": None}
    return {**sample, "id": swing_id, "wrist": wrist}


@pytest.mark.parametrize(("stroke", "swing_id", "roll", "is_rolled"), CASES, ids=[c[1] for c in CASES])
def test_every_real_swing_sorts(sample: dict, stroke: str, swing_id: str, roll: float, is_rolled: bool) -> None:
    swing = with_roll(sample, swing_id, roll, +1 if stroke == "backhand" else -1)
    fault = next((f for f in detect_faults(swing, stroke) if f["id"] == "rolled_wrist"), None)
    if is_rolled:
        assert fault is not None, f"{swing_id} rolled {roll} deg and wasn't flagged"
        assert fault["value"] == roll and "MOCK" not in fault["label"]
    else:
        assert fault is None, f"{swing_id} was good ({roll} deg) and got flagged"


@pytest.mark.parametrize("stroke", SESSION)
def test_line_is_the_midpoint_of_the_gap_and_says_where_it_came_from(stroke: str) -> None:
    good, rolled = SESSION[stroke]
    rule = THRESHOLDS[stroke]["rolled_wrist"]
    assert max(good.values()) < min(rolled.values()), "the session no longer separates"
    assert rule["threshold"] == pytest.approx((max(good.values()) + min(rolled.values())) / 2)
    assert rule["target"] == pytest.approx(statistics.median(good.values()), abs=0.06)  # rounded to 0.1
    assert rule["severe_at"] == pytest.approx(statistics.median(rolled.values()), abs=0.06)
    n = len(good) + len(rolled)
    assert rule["source"].startswith(f"ESTIMATE, tuned on one session (n={n} ")
    assert f"{len(good)} good, {len(rolled)} rolled" in rule["source"]


def test_strokes_need_their_own_lines() -> None:
    """A good forehand rolls more than a rolled backhand: one shared line can't sort both."""
    assert max(FH_GOOD.values()) > min(BH_ROLLED.values())
    assert THRESHOLDS["forehand"]["rolled_wrist"]["threshold"] != THRESHOLDS["backhand"]["rolled_wrist"]["threshold"]
