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
from physics.compare import (
    AZIMUTH_LIMIT_DEG, FIX_TARGETS, compare, contact_turn_for_intent, decide_stroke, drive_spot, estimate_azimuth,
    ghost_azimuth, main, racket_line_heading, swing_stroke,
)
from physics.ghost import apply_fix
from physics.skeleton import (
    ARM, FEET, L_HIP, L_SH, N_POINTS, NOSE, R_HIP, R_SH, bone_lengths, court_axes, court_shift, mid, racket_head,
    rotate, swing_hand, to_array, to_court, up_vector,
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
    return compare(forehand, "straighten_elbow", 12, intent=None)  # the fix alone, no aim held


def _facing_z(P: np.ndarray, frame: int) -> float:
    """z of the nose minus the shoulder midpoint. Negative = facing the front wall (z = 0)."""
    return float((P[frame, NOSE] - mid(P, L_SH, R_SH)[frame])[2])


def _handedness(P: np.ndarray) -> np.ndarray:
    """Signed volume of three body vectors per frame. A mirror image flips its sign; a rotation can't."""
    a, b, c = P[:, R_SH] - P[:, L_SH], P[:, NOSE] - P[:, L_SH], P[:, L_HIP] - P[:, L_SH]
    return np.einsum("ij,ij->i", a, np.cross(b, c))


def _head(result: dict, side: str) -> list[float]:
    return racket_head(to_array(result[side]["swing"]), result["hand"])[result["contactFrame"]].tolist()


def _front_wall_x(ball: dict) -> float:
    """Where the PREDICTED ball first hits the front wall, metres from the left wall."""
    return next(e["point"][0] for e in ball["events"] if e["type"] == "front_wall")


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
    back = r["assumptions"]["laterContact"]["backM"]  # the straight-drive ghost meets the ball further back
    assert r["assumptions"]["laterContact"]["applied"] is (back > 0)
    for side in ("you", "ghost"):
        start = r[side]["ball"]["points"][0]
        expected = np.asarray(_head(r, side)) + ([0.0, 0.0, back] if side == "ghost" else 0.0)
        assert start == pytest.approx(expected, abs=5e-4)  # ball points are rounded to the mm
        assert start == r["assumptions"]["launch"][side]["point"]


def test_real_forehand_hits_the_front_wall_where_the_video_shows(forehand):
    r = compare(forehand, "turn_shoulders_less", 15)
    launch, ball = r["assumptions"]["launch"]["you"], r["you"]["ball"]
    assert launch["point"][1] == pytest.approx(0.60, abs=0.01)  # racket head 0.6 m above the lowest foot
    az = launch["azimuth"]
    assert az["label"] == "ESTIMATE" and not az["clamped"] and abs(az["value"]) <= AZIMUTH_LIMIT_DEG
    assert az["value"] == pytest.approx(-13.5, abs=0.5)  # wrist (1.9, 0.9, 7.8) m/s: towards the left wall
    assert 1.4 <= ball["frontWallHeightM"] <= 2.2  # video: about 1.8 m
    assert 3.4 <= _front_wall_x(ball) <= 4.2  # metres from the left wall (video: ~2.6 m from the right)
    assert 125 <= ball["speedKmh"] <= 150  # video: 125-150 km/h
    assert r["assumptions"]["stroke"] == {"value": "forehand", "source": "recorded", "label": "RECORDED"}
    assert r["assumptions"]["launch"]["elevation"] == {"value": 12.0, "unit": "deg", "assumed": True,
                                                       "label": "ASSUMED", "method": "default for a forehand"}


def test_you_and_the_ghost_share_the_court_translation(forehand, fh_elbow):
    c = fh_elbow["contactFrame"]
    a = fh_elbow["assumptions"]["anchor"]
    anchor = (a["x"], a["z"])
    assert anchor == (DEFAULT_CONTACT[0], DEFAULT_CONTACT[2]) and a["label"] == "ASSUMED"

    # Court minus the turned pipeline swing is one rigid slide, and it is the same slide for
    # both: the one that puts YOUR racket head on the anchor.
    played = {**forehand, "contactFrame": c}
    pipeline = {"you": to_array(played), "ghost": to_array(apply_fix(played, "straighten_elbow", 12, None, "R"))}
    expected = court_shift(pipeline["you"], "R", c, anchor)
    for side in ("you", "ghost"):
        slide = (to_array(fh_elbow[side]["swing"]) - court_axes(pipeline[side]))[:, :33]
        np.testing.assert_allclose(slide, np.broadcast_to(expected, slide.shape), atol=1e-9)

    # So the bodies overlap: everything the elbow fix leaves alone is exactly on top of you.
    you, ghost = to_array(fh_elbow["you"]["swing"]), to_array(fh_elbow["ghost"]["swing"])
    moved = {ARM["R"][k] for k in ("wr", "pinky", "index", "thumb")}
    still = [j for j in range(33) if j not in moved]
    np.testing.assert_allclose(ghost[:, still], you[:, still], atol=1e-12)
    assert not np.allclose(ghost[c, ARM["R"]["wr"]], you[c, ARM["R"]["wr"]])  # the fix itself shows

    # Your racket head is on the anchor. The ghost's is where the fix moved it (~10 cm off),
    # and its ball starts there.
    assert [_head(fh_elbow, "you")[i] for i in (0, 2)] == pytest.approx(anchor, abs=1e-9)
    gx, _, gz = _head(fh_elbow, "ghost")
    assert 0.05 < np.hypot(gx - anchor[0], gz - anchor[1]) < 0.2
    assert fh_elbow["ghost"]["ball"]["points"][0] == pytest.approx(_head(fh_elbow, "ghost"), abs=5e-4)
    # Straightening the elbow lowers the racket head, so the fix (and only the fix) moves the ball.
    assert _head(fh_elbow, "ghost")[1] < _head(fh_elbow, "you")[1] - 0.05
    assert fh_elbow["ghost"]["ball"]["frontWallHeightM"] < fh_elbow["you"]["ball"]["frontWallHeightM"]


def test_backhand_sample_matches_the_video(backhand):
    r = compare(backhand, "straighten_elbow", 12)  # no stroke recorded: measured from the contact
    a = r["assumptions"]
    assert a["stroke"] == {"value": "backhand", "source": "measured", "label": "ESTIMATE"}
    assert (a["anchor"]["x"], a["anchor"]["z"]) == (2.0, 7.0)  # right-handed backhand spot
    assert a["launch"]["elevation"] == {"value": 3.0, "unit": "deg", "assumed": True, "label": "ASSUMED",
                                        "method": "default for a backhand"}
    assert r["contactFrame"] == 59  # the stored contact stays
    ball = r["you"]["ball"]
    assert 0.4 <= ball["frontWallHeightM"] <= 0.9  # video: 0.5-0.8 m
    assert 1.5 <= _front_wall_x(ball) <= 2.5  # video: 1.5-2.5 m from the left wall
    for side in ("you", "ghost"):
        start = r[side]["ball"]["points"][0]
        assert start[0] < 3.2  # left half
        assert start == pytest.approx(_head(r, side), abs=5e-4)
        az = a["launch"][side]["azimuth"]
        assert az["label"] == "ASSUMED" and az["estimate"] is False  # the ghost inherits your aim's label
        assert _facing_z(to_array(r[side]["swing"]), r["contactFrame"]) < 0
    you_az, ghost_az = a["launch"]["you"]["azimuth"], a["launch"]["ghost"]["azimuth"]
    assert you_az["value"] == 0.0 and you_az["rawValue"] > 25  # the wrist moves ~53 deg off straight: sideways
    # The ghost's aim is yours turned by the elbow fix's turn of the racket line at contact.
    assert ghost_az["value"] == pytest.approx(you_az["value"] + ghost_az["racketLineTurnDeg"], abs=0.051)


def test_elevation_can_be_set_for_one_swing(backhand):
    r = compare(backhand, "close_stance", 15, elevation_deg=2)
    assert r["assumptions"]["launch"]["elevation"] == {"value": 2.0, "unit": "deg", "assumed": True,
                                                       "label": "ASSUMED", "method": "given for this swing"}
    assert r["assumptions"]["launchElevationDeg"] == 2.0
    low = r["you"]["ball"]["frontWallHeightM"]
    assert low < compare(backhand, "close_stance", 15)["you"]["ball"]["frontWallHeightM"]  # 2 < 3 deg default


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


# ---- The ghost's aim: yours, turned with the racket line at contact ----

def _arm_pose() -> np.ndarray:
    """MOCK court-axes pose at frame 0: right elbow and wrist out to the right, hips at x = 5."""
    Pc = np.full((1, N_POINTS, 3), np.nan)
    Pc[0, L_HIP], Pc[0, R_HIP] = (4.85, 0.9, 7.3), (5.15, 0.9, 7.3)
    Pc[0, ARM["R"]["el"]], Pc[0, ARM["R"]["wr"]] = (5.35, 0.9, 7.1), (5.55, 0.7, 6.9)
    return Pc


@pytest.mark.parametrize("trunk_deg,turn,value,clamped", [
    (0.0, 0.0, -13.5, False),
    (10.0, -10.0, -20.0, True),   # opens 10 deg further: -23.5, clamped to the limit
    (-10.0, 10.0, -3.5, False),   # 10 deg less open: 10 deg towards the line
])
def test_ghost_aim_turns_with_the_trunk_at_contact(trunk_deg, turn, value, clamped):
    # Turning the upper body counter-clockwise seen from above (the way a right-hander's forehand
    # unwinds) opens it: the racket line, and so the ball, swings towards the left wall.
    you = _arm_pose()
    ghost = you.copy()
    centre = mid(you, L_HIP, R_HIP)[0]
    ghost[0, :23] = rotate(you[0, :23], centre, np.array([0.0, 1.0, 0.0]), np.radians(trunk_deg))
    you_aim = {"value": -13.5, "estimate": True, "label": "ESTIMATE"}
    az = ghost_azimuth(you_aim, you, ghost, "R", 0)
    assert az["racketLineTurnDeg"] == pytest.approx(turn, abs=0.05)
    assert racket_line_heading(ghost, "R", 0) - racket_line_heading(you, "R", 0) == pytest.approx(turn, abs=1e-9)
    assert (az["value"], az["clamped"], az["label"], az["estimate"]) == (pytest.approx(value), clamped, "ESTIMATE", True)
    assert az["rawValue"] == pytest.approx(-13.5 + turn, abs=0.05) and az["youDeg"] == -13.5


def test_hero_ghost_keeps_your_line_because_its_contact_is_yours(forehand):
    # turn_shoulders_less only shrinks the backswing and fades to zero at contact, so the ghost's
    # trunk, forearm and racket head at contact are yours: same racket face, same aim. The ghost's
    # own wrist direction said -15.1 deg, from where the edit blends back into your swing.
    r = compare(forehand, "turn_shoulders_less", 52.6, intent=None)
    c, launch = r["contactFrame"], r["assumptions"]["launch"]
    you, ghost = to_array(r["you"]["swing"]), to_array(r["ghost"]["swing"])
    np.testing.assert_array_equal(ghost[c], you[c])
    assert launch["ghost"]["azimuth"]["racketLineTurnDeg"] == 0.0
    assert launch["ghost"]["azimuth"]["value"] == launch["you"]["azimuth"]["value"] == -13.5
    assert _front_wall_x(r["ghost"]["ball"]) == _front_wall_x(r["you"]["ball"])  # one line, less pace
    # From the ASSUMED drive spot (no court lines, as on a live upload). The demo's numbers, from
    # the MEASURED spot, are pinned in test_court_spot.py.
    d = r["delta"]["ball"]
    assert (d["speedKmh"]["you"], d["speedKmh"]["ghost"]) == (133.2, 119.1)
    assert (d["frontWallHeightM"]["you"], d["frontWallHeightM"]["ghost"]) == (1.92, 1.87)
    assert (d["landingDepthM"]["you"], d["landingDepthM"]["ghost"]) == (8.97, 7.6)


def test_elbow_fix_turns_the_aim_with_the_forearm(fh_elbow):
    c, launch = fh_elbow["contactFrame"], fh_elbow["assumptions"]["launch"]
    you, ghost = (to_array(fh_elbow[side]["swing"]) for side in ("you", "ghost"))
    turn = racket_line_heading(ghost, "R", c) - racket_line_heading(you, "R", c)
    az = launch["ghost"]["azimuth"]
    assert abs(turn) > 3  # straightening the elbow swings the forearm, and the racket with it
    assert az["racketLineTurnDeg"] == pytest.approx(turn, abs=0.05)
    assert az["value"] == pytest.approx(launch["you"]["azimuth"]["value"] + turn, abs=0.06)


@pytest.mark.parametrize("hand,side,x", [("R", "forehand", 5.4), ("R", "backhand", 2.0),
                                         ("L", "forehand", 1.0), ("L", "backhand", 4.4)])
def test_drive_spot_per_stroke_mirrored_for_a_left_hand(hand, side, x):
    assert drive_spot(hand, side) == (pytest.approx(x), DEFAULT_CONTACT[2])


def test_stroke_given_beats_recorded_beats_measured(backhand):
    recorded = {**backhand, "side": "forehand"}
    a = compare(recorded, "close_stance", 15)["assumptions"]
    assert a["stroke"] == {"value": "forehand", "source": "recorded", "label": "RECORDED"}
    assert a["anchor"]["x"] == DEFAULT_CONTACT[0] and a["launchElevationDeg"] == 12.0
    a = compare(recorded, "close_stance", 15, side="backhand")["assumptions"]
    assert a["stroke"] == {"value": "backhand", "source": "given", "label": "RECORDED"}
    assert a["anchor"]["x"] == 2.0 and a["launchElevationDeg"] == 3.0
    a = compare({**backhand, "stroke": "backhand", "side": "forehand"}, "close_stance", 15)["assumptions"]
    assert a["stroke"]["value"] == "backhand"  # "stroke" is read before "side", as pipeline/server.py does
    with pytest.raises(ValueError, match="side"):
        compare(backhand, "close_stance", 15, side="lob")


def test_an_auto_classified_stroke_label_is_checked_against_the_skeleton(backhand, forehand):
    # pipeline/process.py's auto classifier can call IMG_2116 a forehand; the skeleton says backhand.
    misread = {**backhand, "side": "forehand", "metadata": {"strokeSource": "auto"}}
    a = compare(misread, "close_stance", 15)["assumptions"]
    assert a["stroke"] == {"value": "backhand", "source": "measured (auto label overridden)", "label": "ESTIMATE"}
    assert (a["anchor"]["x"], a["anchor"]["z"]) == (2.0, 7.0) and a["launchElevationDeg"] == 3.0

    agrees = {**backhand, "side": "backhand", "metadata": {"strokeSource": "auto"}}
    assert compare(agrees, "close_stance", 15)["assumptions"]["stroke"] == {
        "value": "backhand", "source": "recorded", "label": "RECORDED"}
    # A manual label, side= and a file without strokeSource are trusted as before.
    manual = {**backhand, "side": "forehand", "metadata": {"strokeSource": "manual"}}
    assert compare(manual, "close_stance", 15)["assumptions"]["stroke"]["source"] == "recorded"
    assert compare(misread, "close_stance", 15, side="forehand")["assumptions"]["stroke"]["source"] == "given"
    assert compare({**backhand, "side": "forehand"}, "close_stance", 15)["assumptions"]["anchor"]["x"] == 5.4
    # Too close to call (racket head 4 cm from the hips at frame 62): the auto label stands.
    unsure = {**misread, "contactFrame": 62}
    assert compare(unsure, "close_stance", 15)["assumptions"]["stroke"]["source"] == "recorded"

    # The hero forehand is unchanged, with or without an auto label (the skeleton agrees).
    for swing in (forehand, {**forehand, "metadata": {**forehand["metadata"], "strokeSource": "auto"}}):
        r = compare(swing, "turn_shoulders_less", 15)
        assert r["assumptions"]["stroke"] == {"value": "forehand", "source": "recorded", "label": "RECORDED"}
        assert r["you"]["ball"]["frontWallHeightM"] == pytest.approx(1.92, abs=0.005)
        assert r["you"]["ball"]["speedKmh"] == pytest.approx(133.2, abs=0.05)


def test_a_coach_inferred_stroke_label_is_checked_like_an_auto_one(backhand):
    # pipeline/live.py hands an ambiguous stroke to the coach, whose shoulder-line detector calls
    # IMG_2116 a forehand, and saves its answer with strokeSource "coach-inferred".
    misread = {**backhand, "side": "forehand", "metadata": {"strokeSource": "coach-inferred"}}
    a = compare(misread, "close_stance", 15)["assumptions"]
    assert a["stroke"] == {"value": "backhand", "source": "measured (auto label overridden)", "label": "ESTIMATE"}
    assert (a["anchor"]["x"], a["anchor"]["z"]) == (2.0, 7.0) and a["launchElevationDeg"] == 3.0
    # The shape live.py actually saves: the coach's stroke in "stroke" and metadata, side "unknown".
    live = {**backhand, "side": "unknown", "stroke": "forehand",
            "metadata": {"stroke": "forehand", "strokeSource": "coach-inferred"}}
    assert compare(live, "close_stance", 15)["assumptions"]["anchor"]["x"] == 2.0
    # When the skeleton agrees, or is too close to call (frame 62), the coach's label stands.
    agrees = {**misread, "side": "backhand"}
    assert compare(agrees, "close_stance", 15)["assumptions"]["stroke"]["source"] == "recorded"
    assert compare({**misread, "contactFrame": 62}, "close_stance", 15)["assumptions"]["stroke"] == {
        "value": "forehand", "source": "recorded", "label": "RECORDED"}


def test_a_stroke_decided_before_coaching_is_kept_as_an_estimate(backhand):
    # pipeline/live.py calls decide_stroke() and writes the answer back before coaching.
    misread = {**backhand, "side": "forehand", "metadata": {"strokeSource": "auto"}}
    assert decide_stroke(misread) == ("backhand", "measured (auto label overridden)")
    assert decide_stroke({**backhand, "side": "unknown"}) == ("backhand", "measured")
    for source in ("measured", "measured (auto label overridden)"):
        written_back = {**backhand, "stroke": "backhand", "metadata": {"strokeSource": source}}
        a = compare(written_back, "close_stance", 15)["assumptions"]
        assert a["stroke"] == {"value": "backhand", "source": source, "label": "ESTIMATE"}
        assert a["anchor"]["x"] == 2.0


@pytest.mark.filterwarnings("ignore:Mean of empty slice")  # the all-NaN skeleton below
def test_unknown_stroke_is_a_forehand_labelled_assumed(backhand):
    # At frame 62 (IMG_2116's hit sound) the racket head is only 4 cm to one side of the hips:
    # too close to call, and nothing records the stroke, so it is ASSUMED, never silently.
    timed = {**copy.deepcopy(backhand), "contactFrame": 62, "metadata": {"contactMethod": "audio-transient"}}
    a = compare(timed, "close_stance", 15)["assumptions"]
    assert a["stroke"] == {"value": "forehand", "source": "assumed", "label": "ASSUMED"}
    assert (a["anchor"]["x"], a["launchElevationDeg"]) == (DEFAULT_CONTACT[0], 12.0)
    P = np.full((3, N_POINTS, 3), np.nan)  # nothing visible at all
    assert swing_stroke({}, P, "R", 1) == ("forehand", "assumed")


def test_a_court_frame_swing_is_refused(fh_elbow):
    with pytest.raises(ValueError, match="already in court coordinates"):
        compare(fh_elbow["you"]["swing"], "close_stance", 10)


def test_cli_takes_side_and_elevation(backhand, tmp_path, capsys):
    path = tmp_path / "bh.json"
    path.write_text(json.dumps(backhand))
    main([str(path), "close_stance", "15", "--side", "backhand", "--elevation", "2", "--no-swings"])
    out = json.loads(capsys.readouterr().out)
    assert out["coordinateSystem"] == "court" and "swing" not in out["you"]
    assert out["assumptions"]["stroke"]["source"] == "given"
    assert out["assumptions"]["launchElevationDeg"] == 2.0


# ---- Real backhands from the pipeline (only on machines that have data/processed) ----

PROCESSED = ROOT / "data/processed"
REAL_BACKHANDS = ("0054", "0045", "0052", "0050", "0046", "0041")


def _real_backhands() -> list[Path]:
    return sorted(p for n in REAL_BACKHANDS for p in PROCESSED.glob(f"bh-*/*-swing-{n}.json"))


@pytest.mark.skipif(not _real_backhands(), reason="no real backhand runs (data/processed/bh-*) on this machine")
@pytest.mark.xfail(strict=False, raises=AssertionError,
                   reason="known gap (PR #42): the wrist-speed racket estimate gives 32-203 km/h on these mono "
                          "swings. Kept on purpose, no cap. Fix: wrist-sensor racket speed (Henoch's PR #44, "
                          "gyro angular velocity) plus bh-05 audio-sync checks in the pipeline.")
def test_real_backhands_are_plausible_drives():
    for path in _real_backhands():
        r = compare(json.loads(path.read_text()), "straighten_elbow", 5)
        ball = r["you"]["ball"]
        assert r["assumptions"]["stroke"]["value"] == "backhand", path.name
        assert ball["points"][0] == pytest.approx(_head(r, "you"), abs=5e-4), path.name
        assert 90 <= ball["speedKmh"] <= 170 and ball["outcome"] == "in", (path.name, ball["speedKmh"], ball["outcome"])


# ---- Stated intent: a straight drive (aryan's call for the IMG_2115 hero) ----

def _first_hit(ball: dict) -> str:
    return ball["events"][0]["type"]


def test_hero_aiming_a_straight_drive_holds_the_smallest_turn_that_sends_it_straight(forehand):
    plain = compare(forehand, "turn_shoulders_less", 52.6, intent=None)
    r = compare(forehand, "turn_shoulders_less", 52.6, intent="straight drive")
    a = r["assumptions"]
    # Solved, not set: your aim is -13.5, so the racket line must turn +13.5 deg, i.e. the
    # shoulders hold 13.5 deg less turn at contact. Well inside the fix's 52.6 deg.
    assert {k: a["aim"][k] for k in ("intent", "applied", "contactTurnDeg", "headingTurnDeg", "capDeg", "capped")} == {
        "intent": "straight drive", "applied": True, "contactTurnDeg": -13.5, "headingTurnDeg": 13.5,
        "capDeg": 52.6, "capped": False}
    ghost_az = a["launch"]["ghost"]["azimuth"]
    assert ghost_az["racketLineTurnDeg"] == 13.5 and ghost_az["value"] == 0.0  # measured from the ghost's pose
    # It goes straight: the ball meets the front wall level with where it left the racket.
    ball, start = r["ghost"]["ball"], a["launch"]["ghost"]["point"]
    assert _first_hit(ball) == "front_wall" and _front_wall_x(ball) == pytest.approx(start[0], abs=1e-3)
    assert COURT_WIDTH_M - start[0] == pytest.approx(0.94, abs=0.01)  # 0.94 m off the right wall
    # You are untouched; the coil still drops by exactly the coach's 52.6 deg.
    assert r["you"] == plain["you"] and a["launch"]["you"] == plain["assumptions"]["launch"]["you"]
    assert (r["you"]["metrics"]["shoulder_turn_deg"], r["ghost"]["metrics"]["shoulder_turn_deg"]) == (137.6, 85.0)
    # From the ASSUMED drive spot (no court lines, as on a live upload). The demo's numbers, from
    # the MEASURED spot, are pinned in test_court_spot.py.
    d = r["delta"]["ball"]
    assert (d["speedKmh"]["you"], d["speedKmh"]["ghost"]) == (133.2, 119.1)
    assert (d["frontWallHeightM"]["you"], d["frontWallHeightM"]["ghost"]) == (1.92, 1.89)
    assert (d["landingDepthM"]["you"], d["landingDepthM"]["ghost"]) == (8.97, 7.98)
    # Labelled on screen: the court note under the PREDICTED ball, and the fix for the legend.
    assert r["fix"]["aiming"] == "straight drive" and "aiming" not in plain["fix"]
    assert ("Aiming: straight drive (the player's stated intent). Smallest change that sends "
            "your drive straight: −13.5° of shoulder turn at contact.") in a["note"]
    assert a["note"].endswith("ASSUMPTION: the straight-drive ghost meets the ball later, 0.2 m further back "
                              "beside the body.")


def test_the_hold_is_capped_at_the_fix(forehand):
    r = compare(forehand, "turn_shoulders_less", 5, intent="straight drive")
    a = r["assumptions"]
    assert (a["aim"]["contactTurnDeg"], a["aim"]["capped"]) == (-5.0, True)
    assert a["launch"]["ghost"]["azimuth"]["value"] == -8.5  # 5 deg towards the line, short of it
    assert "Capped at the fix's 5°" in a["note"]


@pytest.mark.parametrize("y_up", [False, True], ids=["y-down", "y-up"])
@pytest.mark.parametrize("fix,amount", [("turn_shoulders_less", 15), ("turn_shoulders_more", 15)])
def test_the_solved_hold_lands_the_ghost_on_the_line_either_way_up(y_up, fix, amount):
    # The mock's own aim is ASSUMED (its wrist moves sideways), so give it a measured one: the
    # sign from court heading to the shoulders' turn must hold for y-up and y-down skeletons.
    swing = make_swing(y_up=y_up)
    c, P = swing["contactFrame"], to_array(make_swing(y_up=y_up))
    Pc = court_axes(P)
    you_aim = {"value": -10.0, "estimate": True, "label": "ESTIMATE"}
    aim, turn = contact_turn_for_intent(P, Pc, "R", c, you_aim, "straight drive", fix, amount)
    assert aim["applied"] and aim["headingTurnDeg"] == 10.0
    ghost = court_axes(to_array(apply_fix(swing, fix, amount, None, "R", contact_turn_deg=turn)))
    assert ghost_azimuth(you_aim, Pc, ghost, "R", c)["value"] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("fix,amount", [("straighten_elbow", 12), ("bend_elbow", 12), ("close_stance", 15),
                                        ("turn_shoulders_more", 15), ("turn_shoulders_less", 52.6)])
def test_every_ghost_aims_a_straight_drive_by_default(forehand, fix, amount):
    # aryan's rule: every ghost aims a straight drive, down the right wall from the forehand spot.
    # On top of the fix, the smallest turn held at contact puts the ghost's MEASURED aim on 0 deg;
    # your swing and ball never change.
    plain = compare(forehand, fix, amount, intent=None)
    r = compare(forehand, fix, amount)
    aim = r["assumptions"]["aim"]
    assert aim["applied"] and aim["label"] == "TARGET" and aim["intent"] == "straight drive"
    fix_turn = plain["assumptions"]["launch"]["ghost"]["azimuth"]["racketLineTurnDeg"]
    assert aim["headingTurnDeg"] == pytest.approx(13.5 - fix_turn, abs=0.06)  # your aim is -13.5
    ghost_az = r["assumptions"]["launch"]["ghost"]["azimuth"]
    assert ghost_az["value"] == 0.0 and ghost_az["label"] == "ESTIMATE"  # measured from the ghost's pose
    ball, start = r["ghost"]["ball"], r["assumptions"]["launch"]["ghost"]["point"]
    assert _first_hit(ball) == "front_wall" and _front_wall_x(ball) == pytest.approx(start[0], abs=0.01)
    assert start[0] > COURT_WIDTH_M / 2  # the right half: down the right wall
    assert r["you"] == plain["you"] and r["fix"]["aiming"] == "straight drive"
    # The fix itself is unchanged: its measurement moves by the same amount with or without the
    # hold. Except the stance, which is measured against the shot line (the wrist's direction at
    # contact): aiming straight turns that line, so the stance to it changes by the held turn too.
    metric = FIX_TARGETS[fix][0]
    held, alone = r["delta"]["metrics"][metric]["change"], plain["delta"]["metrics"][metric]["change"]
    if metric == "stance_open_deg":
        assert abs(held - alone) == pytest.approx(abs(aim["headingTurnDeg"]), abs=0.2)
        assert "against the straight shot line" in r["fix"]["explain"]
    else:
        assert held == alone
    assert "every ghost's target" in r["assumptions"]["note"]


def test_assumed_aims_and_unchanged_ghosts_hold_nothing(forehand, backhand):
    # The backhand's aim is ASSUMED straight (its wrist moves sideways): nothing measured to turn,
    # and it already goes straight, down the left wall from the backhand spot.
    r = compare(backhand, "turn_shoulders_less", 15)
    assert r["assumptions"]["aim"]["applied"] is False and "assumed" in r["assumptions"]["aim"]["why"]
    assert r["ghost"] == compare(backhand, "turn_shoulders_less", 15, intent=None)["ghost"]
    assert r["assumptions"]["launch"]["ghost"]["azimuth"]["value"] == 0.0
    assert r["assumptions"]["launch"]["ghost"]["point"][0] < COURT_WIDTH_M / 2
    # Amount 0 is "unchanged": the ghost is your swing, nothing held.
    zero = compare(forehand, "straighten_elbow", 0)
    assert zero["assumptions"]["aim"]["applied"] is False and zero["ghost"]["ball"] == zero["you"]["ball"]
    with pytest.raises(ValueError, match="intent must be one of"):
        compare(forehand, "turn_shoulders_less", 15, intent="boast")


def test_a_non_shoulder_fix_holds_at_most_the_limit(forehand):
    # A fix other than the shoulder fixes may hold at most AIM_HOLD_LIMIT_DEG at contact.
    from physics.compare import AIM_HOLD_LIMIT_DEG
    r = compare(forehand, "bend_elbow", 30)
    aim = r["assumptions"]["aim"]
    if aim["capped"]:
        assert abs(aim["contactTurnDeg"]) == AIM_HOLD_LIMIT_DEG and "Capped at 20°" in r["assumptions"]["note"]
    else:
        assert abs(aim["contactTurnDeg"]) <= AIM_HOLD_LIMIT_DEG


def _vertical_forearm_at_contact(swing: dict) -> dict:
    """MOCK: the swing with the hitting hand and racket swung about the elbow so the forearm
    hangs straight down at contact (and the frames either side), as rigid as the real arm."""
    P = to_array(swing)
    j, c = ARM["R"], swing["contactFrame"]
    down = up_vector(P) * -1.0
    hand = [j["wr"], j["pinky"], j["index"], j["thumb"], 33, 34]  # + racket tip and throat
    for i in (c - 1, c, c + 1):
        v = P[i, j["wr"]] - P[i, j["el"]]
        axis = np.cross(v, down)
        angle = np.arccos(np.clip(v @ down / np.linalg.norm(v), -1, 1))
        P[i, hand] = rotate(P[i, hand], P[i, j["el"]], axis / np.linalg.norm(axis), angle)
    from physics.skeleton import from_array
    return from_array(swing, P)


def test_a_vertical_forearm_at_contact_leaves_the_ghost_on_your_aim():
    # Codex P2 on PR #73: a forearm hanging straight down has no floor heading, so the fix's
    # turn of the racket line is unmeasured. compare() must still answer, with your aim.
    swing = _vertical_forearm_at_contact(make_swing())
    c = swing["contactFrame"]
    Pc = court_axes(to_array(swing))
    fore = Pc[c, ARM["R"]["wr"]] - Pc[c, ARM["R"]["el"]]
    assert np.hypot(fore[0], fore[2]) < 1e-9 and racket_line_heading(Pc, "R", c) is None
    for fix, amount, intent in (("straighten_elbow", 12, None), ("turn_shoulders_less", 15, "straight drive")):
        r = compare(swing, fix, amount, intent=intent)
        you_az, ghost_az = r["assumptions"]["launch"]["you"]["azimuth"], r["assumptions"]["launch"]["ghost"]["azimuth"]
        assert ghost_az["value"] == you_az["value"] and ghost_az["label"] == you_az["label"]
        assert ghost_az["racketLineTurnDeg"] is None and "unmeasured" in ghost_az["method"]
        assert r["ghost"]["ball"]["label"] == "PREDICTED"
        if intent:
            assert r["assumptions"]["aim"]["applied"] is False
