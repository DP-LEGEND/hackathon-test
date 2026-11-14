"""Fault injector / ghost tests. The swing is mock data from swing_factory."""

import copy
import json

import numpy as np
import pytest

from physics.ghost import EDITS, FIXES, LOWER_BODY, apply_fix, edit_swing, inject_fault
from physics.metrics import contact_frame, measure
from physics.skeleton import (
    L_ANKLE, L_HIP, L_SH, R_ANKLE, R_HIP, R_SH, UPPER_BODY, bone_lengths, floor_basis, mid, to_array, up_vector,
)
from physics.tests.swing_factory import make_swing

ONE_FRAME_MS = 1000 / 240
ARM_AND_TURN = ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_at_contact_deg", "wrist_release_ms")


@pytest.fixture(scope="module")
def good():
    return make_swing()


def max_bone_change(a: dict, b: dict) -> float:
    La, Lb = bone_lengths(to_array(a)), bone_lengths(to_array(b))
    ok = np.isfinite(La) & np.isfinite(Lb)
    return float(np.abs(La[ok] - Lb[ok]).max())


@pytest.mark.parametrize("edits", [
    {"elbow_bend": 15}, {"elbow_bend": -10},
    {"shoulder_turn": -20}, {"shoulder_turn": 10},
    {"wrist_early": 40}, {"wrist_early": -30},
    {"stance_open": -20}, {"stance_open": 10},
    {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 30, "stance_open": -20},
])
def test_bone_lengths_stay_fixed(good, edits):
    assert max_bone_change(good, edit_swing(good, edits)) < 1e-9


def test_elbow_bend_is_measured_at_its_exact_size(good):
    before, after = measure(good), measure(inject_fault(good, "elbow_bend", 15))
    assert after["elbow_at_contact_deg"] == pytest.approx(before["elbow_at_contact_deg"] - 15, abs=1e-6)
    assert after["shoulder_turn_deg"] == pytest.approx(before["shoulder_turn_deg"], abs=1e-6)


def test_shoulder_turn_is_measured_at_its_exact_size(good):
    edited = inject_fault(good, "shoulder_turn", -20)
    before, after = measure(good), measure(edited)
    assert after["shoulder_turn_deg"] == pytest.approx(before["shoulder_turn_deg"] - 20, abs=1e-6)
    P0, P1 = to_array(good), to_array(edited)
    # Hips and legs never move; the contact pose doesn't move; spine length is kept.
    assert np.allclose(P0[:, 23:33], P1[:, 23:33])
    c = good["contactFrame"]
    assert np.allclose(P0[c], P1[c], equal_nan=True)
    spine = lambda P: np.linalg.norm(mid(P, L_SH, R_SH) - mid(P, L_HIP, R_HIP), axis=1)  # noqa: E731
    assert np.allclose(spine(P0), spine(P1))


def test_wrist_early_shifts_release_by_its_size(good):
    before, after = measure(good), measure(inject_fault(good, "wrist_early", 40))
    assert after["wrist_release_ms"] - before["wrist_release_ms"] == pytest.approx(40, abs=ONE_FRAME_MS)
    assert after["elbow_at_contact_deg"] == pytest.approx(before["elbow_at_contact_deg"], abs=1e-6)


def test_ghost_fix_undoes_the_fault(good):
    faulty = inject_fault(good, "elbow_bend", 15)
    assert np.allclose(to_array(apply_fix(faulty, "straighten_elbow", 15)), to_array(good), equal_nan=True)
    faulty = inject_fault(good, "shoulder_turn", -20)
    assert np.allclose(to_array(apply_fix(faulty, "turn_shoulders_more", 20)), to_array(good), equal_nan=True)
    faulty = inject_fault(good, "wrist_early", 30)
    fixed = measure(apply_fix(faulty, "hold_wrist_cock", 30))
    assert fixed["wrist_release_ms"] == pytest.approx(measure(good)["wrist_release_ms"], abs=ONE_FRAME_MS)


# ---- The fixes the coach asks for (coach/faults.py): close_stance, bend_elbow, turn_shoulders_less ----

@pytest.mark.parametrize("fix,amount,metric", [
    ("close_stance", 15, "stance_open_deg"),       # stance_too_open
    ("bend_elbow", 10, "elbow_at_contact_deg"),    # straight_arm
    ("turn_shoulders_less", 15, "shoulder_turn_deg"),  # over_rotation
])
def test_new_fix_moves_its_own_metric_down_by_the_amount(good, fix, amount, metric):
    before, after = measure(good), measure(apply_fix(good, fix, amount))
    assert after[metric] == pytest.approx(before[metric] - amount, abs=1e-6)
    for k in ARM_AND_TURN:
        if k != metric:
            assert after[k] == pytest.approx(before[k], abs=1e-6), k
    if metric != "stance_open_deg":
        # The feet don't move, but the stance is measured against the racket's direction at
        # contact, and moving the arm turns that direction a little (about 4 deg here).
        assert after["stance_open_deg"] == pytest.approx(before["stance_open_deg"], abs=6.0)
        assert np.allclose(to_array(apply_fix(good, fix, amount))[:, LOWER_BODY],
                           to_array(good)[:, LOWER_BODY], equal_nan=True)


def test_close_stance_turns_only_the_legs_about_the_hips(good):
    P0, P1 = to_array(good), to_array(apply_fix(good, "close_stance", 20))
    assert np.allclose(P0[:, UPPER_BODY], P1[:, UPPER_BODY])  # arms, shoulders, racket untouched
    assert np.allclose(mid(P0, L_HIP, R_HIP), mid(P1, L_HIP, R_HIP))  # hip centre stays put
    up = up_vector(P0)
    assert np.allclose(P0[:, LOWER_BODY] @ up, P1[:, LOWER_BODY] @ up)  # feet stay on the floor


def test_close_stance_blends_in_before_contact_and_never_jumps(good):
    P0, P1 = to_array(good), to_array(apply_fix(good, "close_stance", 20))
    e1, e2 = floor_basis(up_vector(P0))

    def feet_heading(P):
        f = P[:, R_ANKLE] - P[:, L_ANKLE]
        return np.degrees(np.arctan2(f @ e2, f @ e1))

    turn = np.abs(feet_heading(P1) - feet_heading(P0))
    c = good["contactFrame"]
    full_from = c - int(0.200 * good["fps"])  # STANCE_FULL_MS before contact
    assert turn[0] < 20 - 1  # not yet at full size when the clip starts
    assert np.allclose(turn[full_from:], 20)  # full size through contact and after
    assert np.all(np.diff(turn[: full_from + 1]) >= -1e-9)  # only ever grows on the way in
    assert np.abs(np.diff(turn)).max() < 1.0  # under 1 deg per frame: no jump in the replay


def test_close_stance_matches_the_coach_measurement(good):
    measure_extra = pytest.importorskip("coach.measure_extra")
    no_racket = copy.deepcopy(good)
    for f in no_racket["frames"]:
        f.pop("racketTip"), f.pop("racketThroat")
    for s in (good, no_racket, apply_fix(good, "close_stance", 20)):
        assert measure(s)["stance_open_deg"] == pytest.approx(measure_extra.stance_open_deg(s), abs=1e-9)


def test_new_fixes_undo_their_opposites(good):
    for fault, fix, size in [({"stance_open": 15}, "close_stance", 15),
                             ({"elbow_bend": -12}, "bend_elbow", 12),
                             ({"shoulder_turn": 20}, "turn_shoulders_less", 20)]:
        back = apply_fix(edit_swing(good, fault), fix, size)
        assert np.allclose(to_array(back), to_array(good), equal_nan=True), fix


def test_stance_can_only_close_to_side_on_and_open_to_square(good):
    stance = measure(good)["stance_open_deg"]  # about 74 deg on the mock swing
    with pytest.raises(ValueError, match="only"):
        apply_fix(good, "close_stance", stance + 1)
    with pytest.raises(ValueError, match="square"):
        inject_fault(good, "stance_open", 90 - stance + 1)
    side_on = apply_fix(good, "close_stance", stance)
    assert measure(side_on)["stance_open_deg"] == pytest.approx(0, abs=1e-6)


def test_every_fix_is_labelled_with_its_edit(good):
    for fix, (edit, sign) in FIXES.items():
        out = apply_fix(good, fix, 5)
        assert out["synthetic"] is True
        assert out["edits"] == [{"id": edit, "size": sign * 5, "unit": EDITS[edit]["unit"]}]


def test_input_is_never_mutated(good):
    snapshot = copy.deepcopy(good)
    edit_swing(good, {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 30, "stance_open": -20})
    assert good == snapshot


def test_fps_real_overrides_the_clip_frame_rate(good):
    # A 4x slow-mo clip reports its playback rate (60 here); timing must use the real rate.
    clip = dict(good, fps=60.0)
    a = edit_swing(clip, {"wrist_early": 40}, fps_real=240.0)
    b = edit_swing(good, {"wrist_early": 40})
    assert np.allclose(to_array(a), to_array(b), equal_nan=True)
    assert measure(clip, fps_real=240.0)["wrist_release_ms"] == pytest.approx(measure(good)["wrist_release_ms"])


def test_contact_frame_fallback_when_missing(good):
    no_contact = {k: v for k, v in good.items() if k != "contactFrame"}
    no_racket = copy.deepcopy(no_contact)
    for f in no_racket["frames"]:
        f.pop("racketTip"), f.pop("racketThroat")
    assert contact_frame(no_racket) == good["contactFrame"]  # peak hitting-wrist speed
    assert abs(contact_frame(no_contact) - good["contactFrame"]) <= 12  # peak racket-tip speed, within 50 ms
    assert contact_frame(dict(good, contactFrame=10_000)) == contact_frame(no_contact)  # out of range -> fallback
    assert edit_swing(no_racket, {"elbow_bend": 5})["contactFrame"] == good["contactFrame"]


def test_y_up_skeleton_gives_the_same_numbers(good):
    up = make_swing(y_up=True)
    m_down, m_up = measure(good), measure(up)
    for k in ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_release_ms"):
        assert m_up[k] == pytest.approx(m_down[k], abs=1e-6)
    assert measure(inject_fault(up, "shoulder_turn", -20))["shoulder_turn_deg"] == pytest.approx(
        m_up["shoulder_turn_deg"] - 20, abs=1e-6)


def test_missing_points_are_left_alone(good):
    s = copy.deepcopy(good)
    s["frames"][3]["joints"] = [[0.0, 0.0, 0.0]] * 33  # whole frame lost by the tracker
    s["frames"][100]["joints"][16] = [0.0, 0.0, 0.0]  # hitting wrist lost for one frame
    for f in s["frames"][:10]:
        f["racketTip"] = None
    out = edit_swing(s, {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 30, "stance_open": -20})
    assert out["frames"][3]["joints"] == [[0.0, 0.0, 0.0]] * 33
    assert out["frames"][100]["joints"][16] == [0.0, 0.0, 0.0]
    assert all(f["racketTip"] is None for f in out["frames"][:10])
    # Nothing else became NaN: a lost point must not spread to its neighbours.
    finite = np.isfinite(to_array(out)).all(axis=2)
    expected = np.ones_like(finite)
    expected[3, :33] = False
    expected[100, 16] = False
    expected[:10, 33] = False
    assert (finite == expected).all()


def test_output_is_labelled_and_json_ready(good):
    out = apply_fix(good, "straighten_elbow", 10)
    json.dumps(out)
    assert out["synthetic"] is True
    assert out["edits"] == [{"id": "elbow_bend", "size": -10.0, "unit": "deg"}]
    assert out["id"] == "mock-forehand+elbow_bend-10"
    assert len(out["frames"]) == len(good["frames"])


@pytest.mark.parametrize("edits,msg", [
    ({"hip_turn": 10}, "unknown edit"),
    ({"elbow_bend": 90}, "within"),
    ({"wrist_early": float("nan")}, "within"),
    ({"shoulder_turn": -200}, "within"),
    ({"stance_open": -91}, "within"),
])
def test_bad_edits_are_rejected(good, edits, msg):
    with pytest.raises(ValueError, match=msg):
        edit_swing(good, edits)


def test_cannot_remove_more_turn_than_there_is(good):
    turn = measure(good)["shoulder_turn_deg"]
    small = edit_swing(good, {"shoulder_turn": -(turn - 25)})  # leaves ~25 deg of turn
    with pytest.raises(ValueError, match="only"):
        inject_fault(small, "shoulder_turn", -30)


def test_unknown_fix_is_rejected(good):
    with pytest.raises(ValueError, match="unknown fix"):
        apply_fix(good, "swing_harder", 5)
