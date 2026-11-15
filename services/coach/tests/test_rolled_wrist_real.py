"""rolled_wrist on REAL swings: the per-swing numbers the committed thresholds were tuned on.

One shadow session (no ball), 14 Nov 2026: a phone strapped to the hitting forearm, 15 good
and 14 rolled-wrist backhands, 10 good and 11 rolled forehands, labelled by block. Each number
is the size of the forearm roll (the gyro integrated about the forearm's own axis, wrist.metrics
swing_metrics(..., roll_from="gyro")) over -150..+100 ms around the forearm's fastest turn,
which stands in for contact. Backhands roll one way (+), forehands the other (-); the coach
reads the size (roll_change_abs_deg). Kept here as constants: no sensor files in the repo.

Caveat these tests can't see: the split depends on where contact sits. Moving it 25 ms
earlier makes good and rolled overlap on both strokes, so retune once real hits (contact
from the ball's impact) are in. Until then the real lines judge only swings timed the same
way (contact_source "gyro peak"); any other real swing is listed as not checked.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import pytest

from coach.agent import coach_swing
from coach.faults import NOT_GYRO_PEAK, THRESHOLDS, detect_faults

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


def with_roll(sample: dict, swing_id: str, roll: float, sign: int, contact_source: str | None = "gyro peak",
              mock: bool = False) -> dict:
    """The sample swing carrying one real swing's wrist numbers (real, not mock), timed as the
    session was (the forearm's fastest turn) unless contact_source says otherwise."""
    wrist = {"usable": True, "mock": mock, "roll_change_deg": sign * roll, "roll_change_abs_deg": roll,
             "peak_roll_rate_abs_dps": 900.0, "peak_angular_speed_dps": 1500.0, "skip_reason": None,
             "contact_source": contact_source}
    return {**sample, "id": swing_id, "wrist": wrist}


# Codex P1 on #74: the real lines were tuned with the roll window on the gyro peak; an
# impact-timed hit's window sits elsewhere, and 25 ms is enough to swap good and rolled.
ROLLED_MEDIAN = {"forehand": 158.8, "backhand": 137.3}   # past each stroke's threshold


@pytest.mark.parametrize("stroke", SESSION)
def test_a_gyro_peak_timed_real_swing_over_the_line_fires(sample: dict, stroke: str) -> None:
    roll = ROLLED_MEDIAN[stroke]
    assert roll > THRESHOLDS[stroke]["rolled_wrist"]["threshold"]
    result = coach_swing(with_roll(sample, "gp", roll, +1, "gyro peak"), stroke)
    assert "rolled_wrist" in [result["fault"]["id"], *result["other_faults"]]
    assert result["metrics"]["wrist_sensor"] == "sensor" and result["metrics"]["forearm_roll_deg"] == roll
    assert "rolled_wrist" not in result["not_measured"] and "rolled_wrist" not in result["disabled_faults"]


@pytest.mark.parametrize("contact_source", ["impact", "impact spike", "double tap", None])
@pytest.mark.parametrize("stroke", SESSION)
def test_the_same_roll_timed_any_other_way_is_not_checked(sample: dict, stroke: str,
                                                          contact_source: str | None) -> None:
    """No fault, and the coach says the wrist wasn't checked (never that it's firm)."""
    result = coach_swing(with_roll(sample, "hit", ROLLED_MEDIAN[stroke], +1, contact_source), stroke)
    fired = [result["fault"]["id"]] + result["other_faults"] if result["fault"] else []
    assert "rolled_wrist" not in fired
    assert "rolled_wrist" in result["not_measured"]   # the page's "Not checked on this swing"
    assert result["disabled_faults"]["rolled_wrist"] == NOT_GYRO_PEAK == (
        "threshold tuned on gyro-peak-timed practice swings; not checked on impact-timed hits")
    m = result["metrics"]
    # wrist_sensor null + this reason: the page's wrist panel shows "not judged" with it, not "firm"
    assert m["wrist_sensor"] is None and m["wrist_sensor_skipped"] == NOT_GYRO_PEAK
    assert m["forearm_roll_deg"] is None and m["wrist_contact_source"] == contact_source
    assert not any(f["id"] == "rolled_wrist" for f in detect_faults(with_roll(sample, "hit", 170.0, +1, contact_source),
                                                                    stroke))


def test_mock_data_keeps_its_own_timing(sample: dict) -> None:
    """Only the real lines are tied to the gyro peak: mock swings (impact-timed) still reach the coach."""
    result = coach_swing(with_roll(sample, "mock", 60.8, +1, "impact spike", mock=True), "forehand")
    assert result["metrics"]["wrist_sensor"] == "mock sensor" and result["metrics"]["wrist_sensor_skipped"] is None
    assert "rolled_wrist" not in result["disabled_faults"]


def test_without_a_sensor_nothing_new_is_said(sample: dict) -> None:
    result = coach_swing(sample, "forehand")
    assert result["not_measured"] == ["rolled_wrist"] and "rolled_wrist" not in result["disabled_faults"]
    assert "wrist_contact_source" not in result["metrics"]
    assert result["metrics"]["wrist_sensor_skipped"] == "no wrist sensor data for this swing"


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
