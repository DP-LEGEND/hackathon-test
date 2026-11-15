"""Where the player hit from (physics/court_spot.py), and compare()'s spot, explain and validation.

The camera and court pixels are synthetic (MOCK); the swings are the saved demo swings.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

import physics.court_spot as cs
import physics.validate_ball as vb
from physics.compare import compare
from physics.skeleton import court_axes, racket_head, to_array

ROOT = Path(__file__).resolve().parents[3]
FOREHAND = ROOT / "public/swings/swing_fh_over_rotation.json"
SPOTS = Path(vb.SPOTS_DIR)
COURT = [  # court landmarks (x, y, z) m: four on the front wall, five on the floor
    (0, 4.545, 0), (6.4, 4.545, 0), (0, 1.755, 0), (6.4, 1.755, 0),
    (0, 0, 0), (6.4, 0, 0), (3.2, 0, 5.415), (4.8, 0, 5.415), (6.4, 0, 5.415)]


def _camera(yaw_deg: float = 0.0) -> vb.Camera:
    """MOCK: the demo phone at the back wall, 1.15 m up, looking at the front wall, turned by yaw_deg."""
    base = np.array([[1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]])
    p, y = math.radians(5.0), math.radians(yaw_deg)
    tilt = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    turn = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    R = tilt @ base @ turn
    C = np.array([4.0, 1.15, 9.7])
    return vb.Camera(1540.0, 960.0, 540.0, R, -R @ C)


def _court(cam: vb.Camera, points=COURT) -> dict:
    px = cam.project(np.array(points, float))
    return {"frameSize": [1920, 1080], "source": "MOCK",
            "points": [{"name": str(i), "court": list(map(float, X)), "px": list(map(float, p))}
                       for i, (X, p) in enumerate(zip(points, px))]}


@pytest.fixture(scope="module")
def forehand():
    return json.loads(FOREHAND.read_text())


def test_the_floor_homography_puts_pixels_back_on_the_floor():
    cam = _camera()
    H, rms, n = cs.floor_homography(_court(cam))
    assert n == 5 and rms < 1e-4
    feet = np.array([(4.85, 0.0, 4.5), (1.7, 0.0, 4.6)])
    np.testing.assert_allclose(cs.to_floor(H, cam.project(feet)), feet[:, [0, 2]], atol=1e-4)


def test_too_few_floor_lines_keeps_the_assumed_spot():
    court = _court(_camera(), COURT[:4] + COURT[6:9])  # 3 floor points
    with pytest.raises(ValueError, match="at least 4 court-line landmarks on the floor"):
        cs.floor_homography(court)


def test_the_spot_is_the_foot_on_the_floor_plus_the_skeletons_foot_to_racket_offset(forehand):
    cam = _camera()
    foot = [(4.80, 0.0, 4.45), (4.90, 0.0, 4.55)]   # heel and toe on the court
    spot = cs.measure_spot(forehand, "R", 48, [tuple(p) for p in cam.project(foot)], _court(cam))
    Q = court_axes(to_array(forehand))
    offset = racket_head(Q, "R")[48][[0, 2]] - np.nanmean(Q[48, [cs.HEEL["R"], cs.TOE["R"]]][:, [0, 2]], axis=0)
    assert (spot["x"], spot["z"]) == (pytest.approx(4.85 + offset[0], abs=2e-3), pytest.approx(4.5 + offset[1], abs=2e-3))
    assert spot["label"] == "MEASURED" and spot["footM"] == [pytest.approx(4.85, abs=2e-3), pytest.approx(4.5, abs=2e-3)]
    assert abs(spot["cameraYawDeg"]) < 0.5


def test_a_camera_turned_away_from_the_front_wall_keeps_the_assumed_spot(forehand):
    cam = _camera(yaw_deg=20)
    px = [tuple(p) for p in cam.project([(4.8, 0.0, 4.45), (4.9, 0.0, 4.55)])]
    with pytest.raises(ValueError, match="turned"):
        cs.measure_spot(forehand, "R", 48, px, _court(cam))


def test_the_hitting_foot_must_be_seen():
    img = np.zeros((33, 3))
    vis = np.ones(33)
    vis[cs.TOE["R"]] = 0.2
    with pytest.raises(ValueError, match="heel and toe"):
        cs.hitting_foot_px(img, vis, "R")
    vis[cs.TOE["R"]] = 0.9
    assert len(cs.hitting_foot_px(img, vis, "R")) == 2


# ---- compare() with a MEASURED spot ----

def test_compare_launches_from_the_measured_spot_and_says_so(forehand):
    spot = json.loads((SPOTS / "7178110a0b06-swing-0027.json").read_text())
    assumed = compare(forehand, "turn_shoulders_less", 52.6, intent=None)
    measured = compare(forehand, "turn_shoulders_less", 52.6, intent=None, spot=spot)
    anchor = measured["assumptions"]["anchor"]
    assert (anchor["x"], anchor["z"], anchor["label"], anchor["assumed"]) == (spot["x"], spot["z"], "MEASURED", False)
    point = measured["assumptions"]["launch"]["you"]["point"]
    assert (point[0], point[2]) == (pytest.approx(spot["x"]), pytest.approx(spot["z"]))  # your racket head on it
    assert "spot on court is measured from the video" in measured["assumptions"]["note"]
    assert measured["assumptions"]["launch"]["elevation"]["label"] == "ASSUMED"  # the launch angle stays assumed
    assert assumed["assumptions"]["anchor"]["label"] == "ASSUMED"
    # Same swing, speed and aim; nearer the front wall, so it meets the wall lower.
    assert measured["you"]["ball"]["speedKmh"] == assumed["you"]["ball"]["speedKmh"]
    assert measured["you"]["ball"]["frontWallHeightM"] < assumed["you"]["ball"]["frontWallHeightM"]


@pytest.mark.parametrize("spot,msg", [
    ({"x": 5.4, "z": 4.2, "label": "ASSUMED"}, "labelled MEASURED"),
    ({"x": 7.5, "z": 4.2, "label": "MEASURED"}, "off the court"),
    ({"x": float("nan"), "z": 4.2, "label": "MEASURED"}, "finite"),
])
def test_compare_refuses_a_spot_it_cant_trust(forehand, spot, msg):
    with pytest.raises(ValueError, match=msg):
        compare(forehand, "turn_shoulders_less", 15, spot=spot)


def test_the_saved_spots_feed_the_before_after_check():
    entries = json.loads((vb.VALIDATION_DIR / "swings.json").read_text())["swings"]
    for entry in entries:
        r = vb.spot_check(entry)
        spot = json.loads((SPOTS / f"{entry['swing']}.json").read_text())
        assert r["before"]["contactPointM"][2] == 7.0  # the ASSUMED drive spot
        assert (r["after"]["contactPointM"][0], r["after"]["contactPointM"][2]) == (
            pytest.approx(spot["x"]), pytest.approx(spot["z"]))
        assert r["errorAfter"] == vb.errors(r["tracked"], r["after"])
        assert r["after"]["elevationDeg"] == r["before"]["elevationDeg"]  # not fitted to the ball


# ---- validation and fix.explain ----

def _result() -> dict:
    return json.loads((vb.RESULTS_DIR / "7178110a0b06-swing-0027.json").read_text())


def test_validation_puts_your_predicted_ball_next_to_the_tracked_one(forehand):
    r = compare(forehand, "turn_shoulders_less", 52.6, tracked=_result())
    v = r["validation"]
    tracked = _result()["tracked"]
    assert v["predicted"] == round(r["you"]["ball"]["frontWallHeightM"], 2)
    assert v["tracked"] == round(tracked["frontWall"]["heightM"], 2)
    assert v["error_m"] == round(v["tracked"] - v["predicted"], 2)
    assert v["error_deg"] == round(tracked["azimuthDeg"] - r["assumptions"]["launch"]["you"]["azimuth"]["value"], 1)
    assert v["method"] in ("tracked", "hand-labelled") and v["errorSign"] == "tracked minus predicted"
    assert "validation" not in compare(forehand, "turn_shoulders_less", 52.6)


def test_validation_refuses_another_swings_result_or_an_unknown_method(forehand):
    other = {**_result(), "swing": "someone-else"}
    with pytest.raises(ValueError, match="not '7178110a0b06-swing-0027'"):
        compare(forehand, "turn_shoulders_less", 15, tracked=other)
    with pytest.raises(ValueError, match="method"):
        compare(forehand, "turn_shoulders_less", 15, tracked={**_result(), "method": "guessed"})


def _numbers(obj, out: list[float]) -> list[float]:
    """Every number in a compare() result, leaving out the skeletons and the path points."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("swing", "points"):
                _numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append(float(obj))
    return out


@pytest.mark.parametrize("fix,amount", [("turn_shoulders_less", 52.6), ("straighten_elbow", 12), ("close_stance", 15)])
def test_explain_quotes_only_numbers_compare_measured_or_solved(forehand, fix, amount):
    spot = json.loads((SPOTS / "7178110a0b06-swing-0027.json").read_text())
    r = compare(forehand, fix, amount, spot=spot)
    text = r["fix"]["explain"]
    known = _numbers({k: v for k, v in r.items() if k != "fix"}, [amount])
    for token in re.findall(r"\d+(?:\.\d+)?", text):
        nd = len(token.split(".")[1]) if "." in token else 0
        assert any(round(abs(v), nd) == float(token) for v in known), f"{token} isn't in the compare result"
    for label in ("PREDICTED", "MEASURED", "ASSUMED"):
        assert label in text
    assert "down the right wall" in text  # every ghost aims a straight drive
