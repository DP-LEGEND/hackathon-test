"""swing_hand(): the hand the pipeline recorded beats the wrist-speed guess. Swing is MOCK data from swing_factory."""

import copy

import numpy as np
import pytest

from physics.compare import compare
from physics.ghost import edit_swing
from physics.metrics import measure
from physics.skeleton import ARM, hitting_hand, swing_hand, to_array
from physics.tests.swing_factory import make_swing


def _left_wrist_flails(swing: dict) -> dict:
    """Copy of a right-handed swing whose LEFT (free) wrist shakes faster than the right one swings."""
    out = copy.deepcopy(swing)
    wr = ARM["L"]["wr"]
    for i, f in enumerate(out["frames"]):
        f["joints"][wr][0] += 0.5 * np.sin(1.3 * i)
    return out


@pytest.fixture(scope="module")
def flailing():
    swing = _left_wrist_flails(make_swing())
    assert hitting_hand(to_array(swing)) == "L"  # the guess alone picks the wrong arm
    return swing


def test_recorded_right_hand_beats_a_faster_left_wrist(flailing):
    swing = {**flailing, "metadata": {"hand": "R"}}
    assert swing_hand(swing) == "R"
    assert measure(swing)["hand"] == "R"
    assert compare(swing, "straighten_elbow", 12)["hand"] == "R"
    # edit_swing works on the right arm too: the left wrist is left exactly where it was.
    before, after = to_array(swing), to_array(edit_swing(swing, {"elbow_bend": 12}))
    assert np.allclose(after[:, ARM["L"]["wr"]], before[:, ARM["L"]["wr"]], equal_nan=True)
    assert not np.allclose(after[:, ARM["R"]["wr"]], before[:, ARM["R"]["wr"]], equal_nan=True)


def test_without_a_recorded_hand_measure_still_guesses(flailing):
    assert measure(flailing)["hand"] == "L"


@pytest.mark.parametrize("extra, expected", [
    ({"metadata": {"hand": "R"}}, "R"),
    ({"hand": "R"}, "R"),                              # top-level field counts too
    ({"metadata": {"hand": "L"}, "hand": "R"}, "L"),  # metadata wins over top-level
    ({"metadata": {"hand": "right"}}, "L"),           # not "R"/"L": fall back to the guess
    ({"metadata": None}, "L"),
    ({}, "L"),
])
def test_swing_hand_reads_metadata_then_falls_back(flailing, extra, expected):
    swing = {**flailing, **extra}
    assert swing_hand(swing) == expected
    assert swing_hand(swing, to_array(swing)) == expected
