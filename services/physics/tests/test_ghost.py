"""Fault injector / ghost tests. The swing is mock data from swing_factory."""

import copy
import json

import numpy as np
import pytest

from physics.ghost import apply_fix, edit_swing, inject_fault
from physics.metrics import contact_frame, measure
from physics.skeleton import L_HIP, L_SH, R_HIP, R_SH, bone_lengths, mid, to_array
from physics.tests.swing_factory import make_swing

ONE_FRAME_MS = 1000 / 240


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
    {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 30},
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


def test_input_is_never_mutated(good):
    snapshot = copy.deepcopy(good)
    edit_swing(good, {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 30})
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
    out = edit_swing(s, {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 30})
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
