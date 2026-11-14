"""PREDICTED ball flight tests."""

import json

import pytest

from physics.ball import (
    COURT_LENGTH_M, COURT_WIDTH_M, DEFAULT_CONTACT, FRONT_OUT_M, SHORT_LINE_M, TIN_M,
    ball_speed_from_racket, predict_ball_path,
)


def test_ball_leaves_about_1_3x_faster_than_the_racket_head():
    assert ball_speed_from_racket(40) / 40 == pytest.approx(1.31, abs=0.02)
    # An incoming ball adds a little speed (apparent bounciness ~0.31).
    assert ball_speed_from_racket(40, 10) - ball_speed_from_racket(40) == pytest.approx(3.08, abs=0.01)


def test_straight_drive_is_a_good_length():
    r = predict_ball_path(35, 5)  # 35 m/s racket head, 5 deg up, straight, from the default spot
    assert r["predicted"] is True and r["label"] == "PREDICTED"
    assert r["outcome"] == "in"
    assert 140 < r["speedKmh"] < 200
    assert TIN_M < r["frontWallHeightM"] < 2.0
    assert r["events"][0]["type"] == "front_wall"
    assert r["landing"][1] > SHORT_LINE_M and r["landsBehindShortLine"] is True
    assert r["points"][0] == list(DEFAULT_CONTACT)
    assert all(p[0] == pytest.approx(DEFAULT_CONTACT[0]) for p in r["points"])  # straight: no drift sideways


def test_low_shot_hits_the_tin():
    r = predict_ball_path(35, -2)
    assert r["outcome"] == "tin" and r["frontWallHeightM"] < TIN_M and r["landing"] is None


def test_high_shot_goes_out_above_the_front_wall_line():
    r = predict_ball_path(35, 35)
    assert r["outcome"] == "out" and r["frontWallHeightM"] > FRONT_OUT_M


def test_ball_hitting_the_floor_before_the_front_wall_is_down():
    r = predict_ball_path(35, -20, contact=(5.4, 0.3, 7.0))
    assert r["outcome"] == "down" and r["frontWallHeightM"] is None


def test_cross_court_drive_lands_on_the_other_side():
    r = predict_ball_path(35, 6, azimuth_deg=-20)
    assert r["outcome"] == "in" and r["landing"][0] < COURT_WIDTH_M / 2


def test_lower_front_wall_hit_lands_shorter():
    low, good = predict_ball_path(35, 2), predict_ball_path(35, 5)
    assert low["frontWallHeightM"] < good["frontWallHeightM"]
    assert low["landing"][1] < good["landing"][1]


def test_harder_hit_means_faster_ball():
    speeds = [predict_ball_path(v, 5)["speedKmh"] for v in (20, 30, 40)]
    assert speeds == sorted(speeds) and len(set(speeds)) == 3


@pytest.mark.parametrize("shot", [(35, 5, 0), (35, 6, -20), (40, 10, 25), (25, 15, 0), (35, -2, 0)])
def test_path_stays_inside_the_court(shot):
    for x, y, z in predict_ball_path(*shot)["points"]:
        assert -1e-9 <= x <= COURT_WIDTH_M + 1e-9
        assert y >= -1e-9
        assert -1e-9 <= z <= COURT_LENGTH_M + 1e-9


def test_output_matches_the_contract_and_is_json_ready():
    r = predict_ball_path(35, 5)
    json.dumps(r)
    assert isinstance(r["speedKmh"], float)
    assert all(len(p) == 3 and all(isinstance(c, float) for c in p) for p in r["points"])


@pytest.mark.parametrize("kwargs,msg", [
    (dict(racket_speed_ms=0, elevation_deg=5), "racket speed"),
    (dict(racket_speed_ms=200, elevation_deg=5), "racket speed"),
    (dict(racket_speed_ms=35, elevation_deg=90), "elevation"),
    (dict(racket_speed_ms=35, elevation_deg=5, azimuth_deg=120), "azimuth"),
    (dict(racket_speed_ms=35, elevation_deg=5, contact=(8.0, 0.6, 7.0)), "outside the court"),
    (dict(racket_speed_ms=float("nan"), elevation_deg=5), "finite"),
])
def test_bad_inputs_are_rejected(kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        predict_ball_path(**kwargs)
