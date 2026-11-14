"""compare() with a forearm phone: your racket speed from the sensor, the ghost's scaled by the fix."""

import copy
import json

import pytest

from physics.ball import ball_speed_from_racket
from physics.compare import (
    GRIP_OFFSET_M, RACKET_LEVER_M, SENSOR_LABEL, SENSOR_MOCK_LABEL, VIDEO_LABEL, compare, racket_speeds,
    sensor_racket_speed,
)
from physics.skeleton import RACKET_HEAD_M
from physics.tests.swing_factory import make_swing


def _wrist(value=20.0, mock=False, usable=True, **extra):
    rs = {"value": value, "rawValue": value, "unit": "m/s", "estimate": True, "label": "ESTIMATE",
          "source": "wrist sensor", "method": "camera wrist velocity + gyro x lever, added as vectors",
          "leverM": RACKET_LEVER_M, "mock": mock, **extra}
    return {"usable": usable, "mock": mock, "skip_reason": None if usable else "alignment error 250 ms > 100 ms",
            "contact_source": "impact spike", "racket_speed_sensor": rs}


@pytest.fixture(scope="module")
def good():
    return make_swing()


def test_your_speed_is_the_sensors_and_the_ghost_keeps_only_the_fix(good):
    video = compare(good, "straighten_elbow", 12)
    sensed = compare({**good, "wrist": _wrist(20.0)}, "straighten_elbow", 12)
    you, ghost = sensed["you"]["racketSpeed"], sensed["ghost"]["racketSpeed"]
    assert you["value"] == 20.0 and you["label"] == SENSOR_LABEL and you["source"] == "wrist sensor"
    scale = video["ghost"]["racketSpeed"]["rawValue"] / video["you"]["racketSpeed"]["rawValue"]
    assert ghost["value"] == pytest.approx(20.0 * scale, abs=0.05) and ghost["label"] == SENSOR_LABEL
    assert ghost["scale"] == pytest.approx(scale, abs=1e-3) and "scaled by the fix" in ghost["source"]
    assert ghost["videoYouMs"] == video["you"]["racketSpeed"]["value"]
    assert sensed["you"]["ball"]["speedKmh"] == pytest.approx(ball_speed_from_racket(20.0) * 3.6, abs=0.1)
    assert sensed["assumptions"]["racketSpeed"]["source"] == "wrist sensor"
    assert video["assumptions"]["racketSpeed"] == {"source": "video", "label": VIDEO_LABEL,
                                                   "why": "no wrist sensor data for this swing"}
    json.dumps(sensed, allow_nan=False)


def test_a_fix_that_doesnt_change_the_video_speed_leaves_the_sensor_speed_alone(good):
    out = compare({**good, "wrist": _wrist(20.0)}, "hold_wrist_cock", 40)
    assert out["ghost"]["racketSpeed"]["value"] == out["you"]["racketSpeed"]["value"] == 20.0


def test_mock_sensor_data_is_labelled_mock_even_from_an_older_file(good):
    out = compare({**good, "wrist": _wrist(20.0, mock=True)}, "straighten_elbow", 12)  # stored label "ESTIMATE"
    assert out["you"]["racketSpeed"]["label"] == out["ghost"]["racketSpeed"]["label"] == SENSOR_MOCK_LABEL
    assert out["you"]["racketSpeed"]["mock"] is True and out["assumptions"]["racketSpeed"]["label"] == SENSOR_MOCK_LABEL


@pytest.mark.parametrize("wrist, why", [
    (None, "no wrist sensor data"),
    ("not a dict", "no wrist sensor data"),
    (_wrist(usable=False), "unusable: alignment error 250 ms"),
    (_wrist(value=None, reason="no camera swing: the wrist's own speed comes from the camera"), "no camera swing"),
    (_wrist(value=float("nan")), "no racket speed"),
    (_wrist(value=0.0), "no racket speed"),
    (_wrist(value=True), "no racket speed"),
    ({"usable": True}, "no racket speed"),
])
def test_without_a_usable_sensor_speed_it_falls_back_to_the_video_and_says_why(good, wrist, why):
    swing = {**good, "wrist": wrist} if wrist is not None else good
    out = compare(swing, "straighten_elbow", 12)
    assert out["you"]["racketSpeed"]["label"] == VIDEO_LABEL and out["you"]["racketSpeed"]["source"] == "video"
    note = out["assumptions"]["racketSpeed"]
    assert note["source"] == "video" and why in note["why"]


def test_a_sensor_speed_outside_the_ball_models_range_is_clamped_and_flagged(good):
    out = compare({**good, "wrist": _wrist(120.0)}, "straighten_elbow", 12)
    you = out["you"]["racketSpeed"]
    assert you["value"] == 80.0 and you["clamped"] is True and you["rawValue"] == 120.0


def test_the_ghost_never_carries_your_wrist_data_and_nothing_is_mutated(good):
    swing = {**good, "wrist": _wrist(20.0)}
    before = copy.deepcopy(swing)
    out = compare(swing, "straighten_elbow", 12)
    assert "wrist" not in out["ghost"]["swing"], "nothing may coach the ghost with your forearm data"
    assert out["you"]["swing"]["wrist"] == swing["wrist"]
    assert swing == before


def test_racket_speeds_falls_back_when_the_video_estimate_is_zero(good):
    you_video = {"value": 1.0, "rawValue": 0.0, "label": VIDEO_LABEL}
    you, ghost, note = racket_speeds({"wrist": _wrist(20.0)}, you_video, dict(you_video))
    assert you is you_video and note["source"] == "video" and "zero" in note["why"]


def test_one_lever_for_both_methods():
    assert RACKET_LEVER_M == pytest.approx(RACKET_HEAD_M + GRIP_OFFSET_M) == 0.55
    assert sensor_racket_speed({"wrist": _wrist(20.0)})[0]["leverM"] == RACKET_LEVER_M
