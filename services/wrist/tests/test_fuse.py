"""Phone + camera fusion against the synthetic truth (MOCK camera swings from wrist.synth)."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest
from scipy.spatial.transform import Slerp

from physics.compare import GRIP_OFFSET_M, RACKET_LEVER_M, SENSOR_MOCK_LABEL, estimate_racket_speed
from physics.skeleton import ARM, RACKET_HEAD_M, to_array
from wrist.fuse import (
    AGREE_OK_DEG, LEVER_M, _elbow_on_circle, align_swing, attach_wrist_entries, fill_swing, racket_speed, read_swings,
)
from wrist.metrics import axis_vector, body_rotations, gyro_convention
from wrist.synth import R_EL, R_SH, R_WR

R = ARM["R"]


def _tools(s):
    slerp = Slerp(s.rec.t, body_rotations(s.rec, gyro_convention(s.rec)["convention"]))
    impacts = {p["swing"]: p["impact_s"] for p in s.sync["alignment"]["pairs"] if p["ok"]}
    return slerp, impacts, axis_vector("y")


def test_alignment_agrees_finds_the_time_shift_and_the_strap(fused) -> None:
    for sid, m in fused.metrics["swings"].items():
        fill = m["occlusion_fill"]
        cam = fused.truth["swings"][sid]["camera"]
        assert fill["applied"] and fill["label"] == "ESTIMATE" and fill["estimate"] is True
        assert fill["agreement_deg"]["median"] < 1.0 and fill["agreement_deg"]["n"] == fill["visible_frames"]
        assert fill["holdout_deg"]["median"] < 2.0, "refit without the frames nearest contact still predicts them"
        # The video's contact frame is off by up to 2 frames; the shift search finds it.
        expected_ms = (cam["frame_sensor_s"][cam["contact_frame"]] - m["impact_s"]) * 1000
        assert fill["time_shift_ms"] == pytest.approx(expected_ms, abs=3)
        assert fill["strap_axis_offset_deg"] == pytest.approx(6.0, abs=1.5)
        assert fill["warnings"] == []


def test_fill_rebuilds_the_occluded_joint_far_better_than_interpolation(fused) -> None:
    for sid, filled in fused.filled.items():
        cam = fused.truth["swings"][sid]["camera"]
        frames = cam["filled_frames"]
        joint = R_WR if cam["occluded"] == "wrist" else R_EL
        true = np.array(cam["true_positions"][str(joint)])
        rebuilt = to_array(filled)[frames, joint]
        interpolated = to_array(fused.swings[sid])[frames, joint]
        error = np.linalg.norm(rebuilt - true, axis=1).max()
        assert error < 0.01
        assert error < 0.4 * np.linalg.norm(interpolated - true, axis=1).max()
        assert fused.metrics["swings"][sid]["occlusion_fill"]["frames"] == frames


def test_fill_keeps_bone_lengths_flags_and_the_original(fused) -> None:
    before = copy.deepcopy(fused.swings)
    for sid, filled in fused.filled.items():
        fill = fused.metrics["swings"][sid]["occlusion_fill"]
        P, P0 = to_array(filled), to_array(fused.swings[sid])
        frames = fill["frames"]
        forearm = np.linalg.norm(P[frames, R["wr"]] - P[frames, R["el"]], axis=1)
        assert forearm == pytest.approx(fill["forearm_m"], abs=1e-3)
        if fill["joints"] == ["elbow"]:
            upper = np.linalg.norm(P[frames, R["el"]] - P[frames, R["sh"]], axis=1)
            assert upper == pytest.approx(fill["upper_arm_m"], abs=1e-3)
        else:
            for key in ("pinky", "index", "thumb"):  # the hand moved with the wrist: same bones
                bone = np.linalg.norm(P[frames, R[key]] - P[frames, R["wr"]], axis=1)
                bone0 = np.linalg.norm(P0[frames, R[key]] - P0[frames, R["wr"]], axis=1)
                assert bone == pytest.approx(bone0, abs=1e-9)
        untouched = np.setdiff1d(np.arange(len(P)), frames)
        assert np.array_equal(P[untouched], P0[untouched], equal_nan=True)
        assert [f["filled"] for f in filled["frames"]] == [f["filled"] for f in fused.swings[sid]["frames"]]
        meta = filled["metadata"]["wristSensorFill"]
        assert meta["label"] == "ESTIMATE" and meta["mock"] is True and meta["frames"] == frames
        assert meta["orientationSource"] == "phone" and fill["orientation_source"] == "phone"
    assert fused.swings == before, "the camera swings are never mutated"


def test_sensor_assisted_marks_exactly_the_joints_the_phone_set(fused) -> None:
    for sid, filled in fused.filled.items():
        fill = fused.metrics["swings"][sid]["occlusion_fill"]
        assisted = np.array([f["sensorAssisted"] for f in filled["frames"]])
        assert assisted.shape == (len(filled["frames"]), 33) and assisted.dtype == bool
        frames = np.flatnonzero(assisted.any(axis=1)).tolist()
        assert frames == fill["frames"], "only the filled frames, all of them"
        hit = sorted({int(j) for j in np.flatnonzero(assisted.any(axis=0))})
        if fill["joints"] == ["elbow"]:
            assert hit == [R["el"]]
        else:
            assert hit == sorted([R["wr"], R["pinky"], R["index"], R["thumb"]]), "the wrist and the hand it carried"
        flags = np.array([f["filled"] for f in filled["frames"]])
        assert flags[frames][:, R["wr"] if fill["joints"] != ["elbow"] else R["el"]].all(), "filled stays true"
    assert all("sensorAssisted" not in f for s in fused.swings.values() for f in s["frames"]), "inputs untouched"


def test_lever_is_the_racket_head_plus_the_grip_offset() -> None:
    assert LEVER_M == RACKET_LEVER_M == pytest.approx(RACKET_HEAD_M + GRIP_OFFSET_M) == pytest.approx(0.55)


def test_racket_speed_matches_the_truth_and_physics_shape(fused) -> None:
    pose = estimate_racket_speed(next(iter(fused.swings.values())))
    for sid, m in fused.metrics["swings"].items():
        r = m["racket_speed_sensor"]
        assert r["value"] == pytest.approx(fused.truth["swings"][sid]["camera"]["racket_speed_ms"], rel=0.06)
        assert r["label"] == SENSOR_MOCK_LABEL and r["estimate"] is True and r["unit"] == "m/s" and r["mock"] is True
        assert "vectors" in r["method"] and r["leverM"] == 0.55 and r["source"] == "wrist sensor"
        assert r["wristFromSensorFill"] is True, "the occlusion covers contact, so the filled wrist is used"
        assert set(pose) - {"wristSpeedMs", "forearmM", "racketLeverM"} <= set(r), "drop-in for compare()"


def test_without_camera_racket_speed_has_no_value_but_says_why(session) -> None:
    for m in session.metrics["swings"].values():
        r = m["racket_speed_sensor"]
        assert r["value"] is None and "camera" in r["reason"] and r["rotationMs"] > 5
        assert m["occlusion_fill"]["applied"] is False and "--swings" in m["occlusion_fill"]["reason"]


def test_racket_speed_falls_back_to_parallel_when_alignment_fails(fused) -> None:
    slerp, impacts, ax = _tools(fused)
    sid = "synth-01"
    al = align_swing(fused.rec, slerp, fused.swings[sid], impacts[sid], ax)
    al["ok"] = False
    r = racket_speed(fused.rec, slerp, impacts[sid], ax, swing=fused.swings[sid], al=al)
    assert "parallel" in r["method"]
    assert r["value"] == pytest.approx(r["wristSpeedMs"] + r["rotationMs"], abs=0.15)


def test_swing_without_filled_flags_is_not_filled(fused) -> None:
    slerp, impacts, ax = _tools(fused)
    swing = copy.deepcopy(fused.swings["synth-01"])
    for f in swing["frames"]:
        del f["filled"]
    al = align_swing(fused.rec, slerp, swing, impacts["synth-01"], ax)
    out, info = fill_swing(swing, al, slerp, impacts["synth-01"])
    assert info["applied"] is False and "provenance unknown" in info["reason"]
    assert out == swing


def test_scrambled_camera_forearm_is_not_trusted(fused) -> None:
    slerp, impacts, ax = _tools(fused)
    swing = copy.deepcopy(fused.swings["synth-01"])
    rng = np.random.default_rng(0)
    for f in swing["frames"]:  # an elbow and wrist that wander at random: nothing to agree with
        f["joints"][R_WR] = (np.array(f["joints"][R_EL]) + 0.26 * rng.normal(size=3)).tolist()
    al = align_swing(fused.rec, slerp, swing, impacts["synth-01"], ax)
    assert al["ok"] is False and "disagree" in al["reason"] and np.median(al["err"]) > AGREE_OK_DEG
    _, info = fill_swing(swing, al, slerp, impacts["synth-01"])
    assert info["applied"] is False and info["reason"].startswith("alignment not trusted")


def test_elbow_on_circle_keeps_both_lengths_or_says_it_could_not() -> None:
    sh, wr = np.zeros(3), np.array([0.4, 0.0, 0.0])
    elbow, both = _elbow_on_circle(sh, wr, 0.3, 0.26, target=np.array([0.2, 0.3, 0.0]))
    assert both and np.linalg.norm(elbow - sh) == pytest.approx(0.3) and np.linalg.norm(elbow - wr) == pytest.approx(0.26)
    assert elbow[1] > 0, "the point of the circle nearest the target"
    target = np.array([0.9, 0.1, 0.0])
    assert _elbow_on_circle(sh, np.array([0.9, 0.0, 0.0]), 0.3, 0.26, target)[1] is False  # out of reach
    assert _elbow_on_circle(np.full(3, np.nan), wr, 0.3, 0.26, target)[1] is False       # no shoulder


def test_attach_wrist_entries_puts_each_entry_on_its_filled_swing(fused) -> None:
    before = copy.deepcopy(fused.swings)
    extra = {**fused.swings, "unseen": {**fused.swings["synth-01"], "id": "unseen"}}
    out = attach_wrist_entries(extra, fused.metrics, fused.filled)
    assert set(out) == set(extra)
    for sid in fused.swings:
        assert out[sid]["wrist"] == fused.metrics["swings"][sid]
        assert out[sid]["frames"] == fused.filled[sid]["frames"], "the sensor-filled swing, not the raw one"
    assert out["unseen"]["wrist"]["usable"] is False and "no video contact" in out["unseen"]["wrist"]["skip_reason"]
    assert out["unseen"]["wrist"]["mock"] is True
    out["synth-01"]["wrist"]["usable"] = False
    assert fused.metrics["swings"]["synth-01"]["usable"] is True and fused.swings == before, "copies only"


def test_gyro_fallback_still_fills_the_occlusion(no_orientation) -> None:
    s = no_orientation
    for sid, filled in s.filled.items():
        cam = s.truth["swings"][sid]["camera"]
        fill = s.metrics["swings"][sid]["occlusion_fill"]
        assert fill["orientation_source"] == "integrated gyro"
        assert filled["metadata"]["wristSensorFill"]["orientationSource"] == "integrated gyro"
        assert fill["agreement_deg"]["median"] < 2.0
        joint = R_WR if cam["occluded"] == "wrist" else R_EL
        true = np.array(cam["true_positions"][str(joint)])
        error = np.linalg.norm(to_array(filled)[cam["filled_frames"], joint] - true, axis=1).max()
        interpolated = np.linalg.norm(to_array(s.swings[sid])[cam["filled_frames"], joint] - true, axis=1).max()
        assert error < 0.03, "a couple of cm (vs < 1 cm with the phone's own orientation)"
        if cam["occluded"] == "wrist":  # interpolation is 12-15 cm off here
            assert error < 0.3 * interpolated
        else:  # a short elbow gap: interpolation is already ~1.5 cm, and the fill matches it
            assert error < interpolated + 0.005
        r = s.metrics["swings"][sid]["racket_speed_sensor"]
        assert r["value"] == pytest.approx(cam["racket_speed_ms"], rel=0.06)
    assert len(s.filled) == len(s.truth["swings"])


def test_read_swings_reads_a_folder_or_a_file(fused, tmp_path) -> None:
    assert set(fused.swings) == set(fused.truth["swings"])
    one = tmp_path / "one.json"
    one.write_text(json.dumps(fused.swings["synth-03"]))
    (tmp_path / "manifest.json").write_text(json.dumps({"swings": ["synth-03.json"]}))  # not a swing
    assert list(read_swings(one)) == ["synth-03"]
    assert list(read_swings(tmp_path)) == ["synth-03"]


def test_series_carries_the_fill_points(fused) -> None:
    for sid, ser in fused.series["swings"].items():
        pts = ser["forearm_fill"]
        assert pts["label"] == "ESTIMATE" and len(pts["frames"]) == len(pts["t_ms"]) == len(pts["wrist"])
        assert pts["frames"] == fused.truth["swings"][sid]["camera"]["filled_frames"]
        assert ser["racket_speed_sensor"]["label"] == SENSOR_MOCK_LABEL and ser["racket_speed_sensor"]["value"] > 0
    assert len(json.dumps(fused.series, separators=(",", ":"))) < 30_000


def test_shoulder_joint_index_matches_physics() -> None:
    assert (R["sh"], R["el"], R["wr"]) == (R_SH, R_EL, R_WR)
