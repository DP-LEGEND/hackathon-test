"""Court frame: skeleton.to_court and compare()'s court output.

Real clips: IMG_2115 forehand (public/swings/swing_fh_over_rotation.json, contact timed by the
hit sound) and IMG_2116 backhand (data/samples/swing_sample.json, no side or audio contact
recorded). Everything else is MOCK data from swing_factory.
"""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from physics.ball import COURT_WIDTH_M, DEFAULT_CONTACT
from physics.compare import AZIMUTH_LIMIT_DEG, compare, drive_spot, estimate_azimuth, main
from physics.skeleton import (
    ARM, FEET, L_HIP, L_SH, N_POINTS, NOSE, R_SH, bone_lengths, mid, racket_head, swing_hand, to_array,
    to_court, up_vector,
)
from physics.tests.swing_factory import make_swing

ROOT = Path(__file__).resolve().parents[3]
FOREHAND = ROOT / "public/swings/swing_fh_over_rotation.json"
BACKHAND = ROOT / "data/samples/swing_sample.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def forehand():
    return _load(FOREHAND)


@pytest.fixture(scope="module")
def backhand():
    return _load(BACKHAND)


@pytest.fixture(scope="module")
def fh_elbow(forehand):
    return compare(forehand, "straighten_elbow", 12)


def _facing_z(P: np.ndarray, frame: int) -> float:
    """z of the nose minus the shoulder midpoint. Negative = facing the front wall (z = 0)."""
    return float((P[frame, NOSE] - mid(P, L_SH, R_SH)[frame])[2])


def _handedness(P: np.ndarray) -> np.ndarray:
    """Signed volume of three body vectors per frame. A mirror image flips its sign; a rotation can't."""
    a, b, c = P[:, R_SH] - P[:, L_SH], P[:, NOSE] - P[:, L_SH], P[:, L_HIP] - P[:, L_SH]
    return np.einsum("ij,ij->i", a, np.cross(b, c))


def _head(result: dict, side: str) -> list[float]:
    return racket_head(to_array(result[side]["swing"]), result["hand"])[result["contactFrame"]].tolist()


# ---- to_court ----

@pytest.mark.parametrize("make", [make_swing, lambda: make_swing(y_up=True), lambda: _load(FOREHAND),
                                  lambda: _load(BACKHAND)],
                         ids=["mock-y-down", "mock-y-up", "IMG_2115", "IMG_2116"])
def test_to_court_turns_and_slides_without_stretching_or_mirroring(make):
    swing = make()
    P = to_array(swing)
    hand, c = swing_hand(swing, P), swing["contactFrame"]
    C = to_court(P, hand, c, (2.0, 6.0))
    np.testing.assert_allclose(bone_lengths(C, hand), bone_lengths(P, hand), atol=1e-9)
    np.testing.assert_allclose(_handedness(C), _handedness(P), atol=1e-12)
    assert up_vector(C)[1] == 1.0                                   # y up, whichever way it came in
    assert np.nanmin(C[:, FEET, 1]) == pytest.approx(0.0, abs=1e-12)  # lowest foot on the floor
    head = racket_head(C, hand)[c]
    assert head[[0, 2]] == pytest.approx([2.0, 6.0], abs=1e-12)    # racket head at contact over the anchor
    up = up_vector(P)
    measured = (racket_head(P, hand)[c] @ up) - np.nanmin(P[:, FEET] @ up)
    assert head[1] == pytest.approx(measured, abs=1e-12)            # ...at its measured height


@pytest.mark.parametrize("path", [FOREHAND, BACKHAND], ids=["IMG_2115 forehand", "IMG_2116 backhand"])
def test_real_swings_face_the_front_wall_after_to_court(path):
    swing = _load(path)
    P, c = to_array(swing), swing["contactFrame"]
    assert _facing_z(P, c) > 0  # pipeline swings face +z
    C = to_court(P, "R", c, (3.2, 6.0))
    assert _facing_z(C, c) < 0
    # Not every frame: the over-rotation forehand turns its back to the front wall in the backswing.
    assert np.nanmedian((C[:, NOSE] - mid(C, L_SH, R_SH))[:, 2]) < 0


def test_mock_swings_face_the_front_wall_either_way_up():
    for swing in (make_swing(), make_swing(y_up=True)):
        C = to_court(to_array(swing), "R", swing["contactFrame"], (3.2, 6.0))
        assert ((C[:, NOSE] - mid(C, L_SH, R_SH))[:, 2] < 0).all()


def test_to_court_rejects_what_it_cannot_place():
    swing = make_swing()
    P, c = to_array(swing), swing["contactFrame"]
    with pytest.raises(ValueError, match="anchor"):
        to_court(P, "R", c, (5.4, 0.6, 7.0))  # a floor position (x, z), not a point
    with pytest.raises(ValueError, match="contact frame"):
        to_court(P, "R", len(P), (5.4, 7.0))
    with pytest.raises(ValueError, match="hand"):
        to_court(P, "right", c, (5.4, 7.0))
    lost = P.copy()
    lost[c, ARM["R"]["wr"]] = np.nan
    with pytest.raises(ValueError, match="elbow or wrist"):
        to_court(lost, "R", c, (5.4, 7.0))


# ---- compare() in court coordinates ----

def test_compare_output_is_all_court_coordinates(forehand, fh_elbow):
    r = json.loads(json.dumps(fh_elbow, allow_nan=False))
    assert r["coordinateSystem"] == "court"
    assert r["contactFrame"] == 48 and r["contactMethod"] == "audio-transient"
    for side in ("you", "ghost"):
        swing = r[side]["swing"]
        assert swing["coordinateSystem"] == swing["metadata"]["coordinateSystem"] == "court"
        C = to_array(swing)
        assert np.nanmin(C[:, FEET, 1]) == pytest.approx(0.0, abs=1e-9)
        assert _facing_z(C, r["contactFrame"]) < 0
    assert forehand["metadata"]["coordinateSystem"] == "hip-centred-y-up-metres"  # input untouched


@pytest.mark.parametrize("fix,amount", [("straighten_elbow", 12), ("bend_elbow", 12), ("turn_shoulders_less", 15)])
def test_each_ball_starts_at_its_own_racket_head_at_contact(forehand, fix, amount):
    r = compare(forehand, fix, amount)
    for side in ("you", "ghost"):
        start = r[side]["ball"]["points"][0]
        assert start == pytest.approx(_head(r, side), abs=5e-4)  # ball points are rounded to the mm
        assert start == r["assumptions"]["launch"][side]["point"]


def test_real_forehand_hits_the_front_wall_where_the_video_shows(forehand):
    r = compare(forehand, "turn_shoulders_less", 15)
    launch, ball = r["assumptions"]["launch"]["you"], r["you"]["ball"]
    assert launch["point"][1] == pytest.approx(0.60, abs=0.01)  # racket head 0.6 m above the lowest foot
    az = launch["azimuth"]
    assert az["label"] == "ESTIMATE" and not az["clamped"] and abs(az["value"]) <= AZIMUTH_LIMIT_DEG
    assert az["value"] == pytest.approx(-13.5, abs=0.5)  # wrist (1.9, 0.9, 7.8) m/s: towards the left wall
    assert 1.4 <= ball["frontWallHeightM"] <= 2.2  # video: about 1.8 m
    wall_x = next(e["point"][0] for e in ball["events"] if e["type"] == "front_wall")
    assert 2.0 <= COURT_WIDTH_M - wall_x <= 3.2  # video: about 2.6 m from the right wall
    assert r["assumptions"]["launch"]["elevation"] == {"value": 12.0, "unit": "deg", "assumed": True,
                                                       "label": "ASSUMED"}


def test_you_and_the_ghost_share_the_anchor(fh_elbow):
    a = fh_elbow["assumptions"]["anchor"]
    anchor = (a["x"], a["z"])
    assert anchor == (DEFAULT_CONTACT[0], DEFAULT_CONTACT[2])
    assert (a["side"], a["sideSource"], a["label"]) == ("forehand", "recorded", "ASSUMED")
    for side in ("you", "ghost"):
        start = fh_elbow[side]["ball"]["points"][0]
        assert (start[0], start[2]) == anchor
        assert [_head(fh_elbow, side)[i] for i in (0, 2)] == pytest.approx(anchor, abs=1e-9)
    # Straightening the elbow lowers the racket head, so the fix (and only the fix) moves the ball.
    assert _head(fh_elbow, "ghost")[1] < _head(fh_elbow, "you")[1] - 0.05
    assert fh_elbow["ghost"]["ball"]["frontWallHeightM"] < fh_elbow["you"]["ball"]["frontWallHeightM"]


def test_backhand_sample_launches_from_the_left_with_an_assumed_straight_aim(backhand):
    r = compare(backhand, "straighten_elbow", 12)  # no side recorded: measured from the contact
    a = r["assumptions"]
    assert (a["anchor"]["side"], a["anchor"]["sideSource"]) == ("backhand", "measured")
    assert a["anchor"]["x"] == pytest.approx(COURT_WIDTH_M - DEFAULT_CONTACT[0])  # 1.0 m off the left wall
    for side in ("you", "ghost"):
        start = r[side]["ball"]["points"][0]
        assert start[0] < 3.2  # left half
        assert start == pytest.approx(_head(r, side), abs=5e-4)
        az = a["launch"][side]["azimuth"]
        assert abs(az["value"]) <= 5 and az["label"] == "ASSUMED" and az["estimate"] is False
        assert az["rawValue"] > 25  # the wrist moves ~53 deg off straight: sideways, so it isn't used
        assert _facing_z(to_array(r[side]["swing"]), r["contactFrame"]) < 0


def test_elevation_is_per_swing_and_fits_the_low_backhand(backhand):
    r = compare(backhand, "close_stance", 15, elevation_deg=2)
    assert r["assumptions"]["launch"]["elevation"] == {"value": 2.0, "unit": "deg", "assumed": True,
                                                       "label": "ASSUMED"}
    assert r["assumptions"]["launchElevationDeg"] == 2.0
    assert 0.5 <= r["you"]["ball"]["frontWallHeightM"] <= 0.8  # a low backhand drive


def test_audio_contact_in_the_metadata_is_the_contact(backhand):
    # IMG_2116's hit sound is file frame 62. The sample doesn't record it: its contactFrame 59 is the
    # pipeline's wrist-speed estimate, which stays (pipeline/tests/test_coach_api.py relies on that).
    plain = compare(backhand, "close_stance", 15)
    assert (plain["contactFrame"], plain["contactMethod"]) == (59, "provided-contact-estimate")
    timed = {**copy.deepcopy(backhand), "contactFrame": 62, "metadata": {"contactMethod": "audio-transient"}}
    r = compare(timed, "close_stance", 15, side="backhand")
    assert (r["contactFrame"], r["contactMethod"]) == (62, "audio-transient")
    assert r["you"]["swing"]["contactFrame"] == r["ghost"]["swing"]["contactFrame"] == 62
    start = r["you"]["ball"]["points"][0]
    assert start[0] < 3.2 and start == pytest.approx(_head(r, "you"), abs=5e-4)


def test_without_a_contact_frame_the_wrist_speed_peak_is_used():
    good = make_swing()
    r = compare({k: v for k, v in good.items() if k != "contactFrame"}, "close_stance", 10)
    assert r["contactFrame"] == good["contactFrame"]  # swing_factory's contact is the wrist-speed peak
    assert r["contactMethod"] == "wrist-speed-peak-estimate"


@pytest.mark.parametrize("deg,value,label,clamped", [
    (-13.5, -13.5, "ESTIMATE", False),
    (22.0, 20.0, "ESTIMATE", True),    # trusted, clamped to the limit
    (-24.9, -20.0, "ESTIMATE", True),
    (30.0, 0.0, "ASSUMED", False),     # more than 25 deg off straight: assumed straight
    (-53.0, 0.0, "ASSUMED", False),
])
def test_aim_uses_the_wrist_only_near_straight(deg, value, label, clamped):
    Pc = np.zeros((3, N_POINTS, 3))
    step = np.array([np.sin(np.radians(deg)), 0.0, -np.cos(np.radians(deg))])  # + = towards the right wall
    Pc[:, ARM["R"]["wr"]] = np.outer(np.arange(3), step)
    az = estimate_azimuth(Pc, "R", 1)
    assert az["value"] == pytest.approx(value) and az["label"] == label and az["clamped"] is clamped
    assert az["rawValue"] == pytest.approx(deg, abs=0.05)


def test_unmeasurable_aim_is_assumed_straight():
    Pc = np.full((3, N_POINTS, 3), np.nan)
    az = estimate_azimuth(Pc, "R", 1)
    assert (az["value"], az["label"], az["rawValue"]) == (0.0, "ASSUMED", None)


@pytest.mark.parametrize("hand,side,x", [("R", "forehand", 5.4), ("R", "backhand", 1.0),
                                         ("L", "forehand", 1.0), ("L", "backhand", 5.4)])
def test_drive_spot_mirrors_for_a_backhand_and_for_a_left_hand(hand, side, x):
    assert drive_spot(hand, side) == (pytest.approx(x), DEFAULT_CONTACT[2])


def test_side_given_beats_recorded_beats_measured(backhand):
    recorded = {**backhand, "side": "forehand"}
    a = compare(recorded, "close_stance", 15)["assumptions"]["anchor"]
    assert (a["side"], a["sideSource"], a["x"]) == ("forehand", "recorded", DEFAULT_CONTACT[0])
    a = compare(recorded, "close_stance", 15, side="backhand")["assumptions"]["anchor"]
    assert (a["side"], a["sideSource"]) == ("backhand", "given") and a["x"] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="side"):
        compare(backhand, "close_stance", 15, side="lob")


def test_a_court_frame_swing_is_refused(fh_elbow):
    with pytest.raises(ValueError, match="already in court coordinates"):
        compare(fh_elbow["you"]["swing"], "close_stance", 10)


def test_cli_takes_side_and_elevation(backhand, tmp_path, capsys):
    path = tmp_path / "bh.json"
    path.write_text(json.dumps(backhand))
    main([str(path), "close_stance", "15", "--side", "backhand", "--elevation", "2", "--no-swings"])
    out = json.loads(capsys.readouterr().out)
    assert out["coordinateSystem"] == "court" and "swing" not in out["you"]
    assert out["assumptions"]["anchor"]["sideSource"] == "given"
    assert out["assumptions"]["launchElevationDeg"] == 2.0
