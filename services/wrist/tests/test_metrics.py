"""Per-swing wrist numbers against the synthetic truth (MOCK data from wrist.synth)."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation, Slerp

from wrist.load import Recording
from wrist.metrics import (
    SERIES_MS, WINDOW_MS, _axial_deg, axis_vector, body_rotations, gyro_convention, swing_metrics, twist_deg,
    wrist_metrics,
)


@pytest.mark.parametrize("name", ["session", "session_inverse"])
def test_numbers_match_the_truth_for_either_quaternion_convention(name: str, request) -> None:
    s = request.getfixturevalue(name)
    assert s.metrics["sensor"]["quaternion"]["convention"] == s.truth["quat_convention"]
    assert s.metrics["sensor"]["quaternion"]["ok"]
    for swing, truth in s.truth["swings"].items():
        m = s.metrics["swings"][swing]
        assert m["usable"] and m["skip_reason"] is None and m["mock"] is True
        assert m["roll_change_deg"] == pytest.approx(truth["roll_change_deg"], abs=1.5)
        assert m["roll_change_abs_deg"] == abs(m["roll_change_deg"])
        assert m["roll_change_gyro_deg"] == pytest.approx(truth["roll_change_deg"], abs=1.5)
        assert m["peak_roll_rate_dps"] == pytest.approx(truth["peak_roll_rate_dps"], rel=0.03)
        assert m["peak_angular_speed_dps"] == pytest.approx(truth["peak_angular_speed_dps"], rel=0.03)
        assert m["window_ms"] == list(WINDOW_MS)


def test_rolled_swings_roll_more_than_normal_ones(session) -> None:
    rolls = {lab: [session.metrics["swings"][sid]["roll_change_abs_deg"]
                   for sid, t in session.truth["swings"].items() if t["label"] == lab]
             for lab in ("none", "rolled_wrist")}
    assert min(rolls["rolled_wrist"]) > max(rolls["none"])


def test_series_is_small_and_ends_the_window_on_the_quoted_number(session) -> None:
    assert set(session.series["swings"]) == set(session.truth["swings"])
    assert session.series["mock"] is True
    for swing, ser in session.series["swings"].items():
        t, roll = ser["t_ms"], ser["roll_deg"]
        assert len(t) == len(roll) == (SERIES_MS[1] - SERIES_MS[0]) // 10 + 1
        assert t[0] == SERIES_MS[0] and t[-1] == SERIES_MS[1] and 0 in t
        assert roll[t.index(WINDOW_MS[0])] == pytest.approx(0.0, abs=0.05)
        assert roll[t.index(WINDOW_MS[1])] == pytest.approx(ser["roll_change_deg"], abs=0.11)
        assert ser["roll_change_deg"] == session.metrics["swings"][swing]["roll_change_deg"]
    assert len(json.dumps(session.series, separators=(",", ":"))) < 20_000


def test_outputs_are_valid_json(session) -> None:
    json.dumps(session.metrics, allow_nan=False)
    json.dumps(session.series, allow_nan=False)


def test_twist_ignores_the_swing_about_other_axes() -> None:
    y = axis_vector("y")
    for swing_deg in (0, 45, 120):
        rel = Rotation.from_euler("z", swing_deg, degrees=True) * Rotation.from_euler("y", 30, degrees=True)
        assert twist_deg(rel, y)[0] == pytest.approx(30.0)
    assert twist_deg(Rotation.from_euler("y", -50, degrees=True), y)[0] == pytest.approx(-50.0)
    assert twist_deg(Rotation.from_euler("y", 30, degrees=True), axis_vector("-y"))[0] == pytest.approx(-30.0)


def test_axis_vector() -> None:
    assert axis_vector("Y").tolist() == [0, 1, 0] and axis_vector("-x").tolist() == [-1, 0, 0]
    with pytest.raises(ValueError):
        axis_vector("w")


def test_wrong_forearm_axis_is_flagged(session) -> None:
    metrics, _ = wrist_metrics(session.rec, session.sync, axis="x")
    assert metrics["sensor"]["axis_hint"] == {"chosen": "x", "dominant_accel_axis": "y", "agrees": False}
    assert any("--axis" in w for w in metrics["warnings"])
    assert session.metrics["sensor"]["axis_hint"]["agrees"] is True


def test_orientation_that_disagrees_with_the_gyro_falls_back_to_the_integrated_gyro(session) -> None:
    rec = copy.copy(session.rec)
    rng = np.random.default_rng(3)
    rec.quat = Rotation.random(rec.t.size, random_state=rng).as_quat()  # nonsense attitude
    assert gyro_convention(rec)["ok"] is False
    metrics, series = wrist_metrics(rec, session.sync)
    used = metrics["sensor"]["orientation_used"]
    assert used["source"] == "integrated gyro" and "doesn't match its gyro" in used["why_not_phone"]
    assert any("integrated gyro" in w for w in metrics["warnings"])
    for sid, m in metrics["swings"].items():
        assert m["usable"] and m["orientation_source"] == "integrated gyro" and "gyro integrated" in m["roll_method"]
        assert m["roll_change_deg"] == pytest.approx(session.truth["swings"][sid]["roll_change_deg"], abs=1.5)
        assert series["swings"][sid]["roll_deg"][series["swings"][sid]["t_ms"].index(WINDOW_MS[1])] == \
            pytest.approx(m["roll_change_deg"], abs=0.1), "the graph still ends on the quoted number"


def test_no_orientation_file_uses_the_biased_gyro_and_still_matches_the_truth(no_orientation) -> None:
    s = no_orientation
    assert s.rec.quat is None and s.rec.orientation == "none"
    used = s.metrics["sensor"]["orientation_used"]
    assert used["source"] == "integrated gyro" and used["why_not_phone"] == "the export has no Orientation.csv"
    assert used["bias_from"] == "around the sync taps" and used["warning"] is None
    for sid, m in s.metrics["swings"].items():
        assert m["usable"] and m["roll_change_deg"] == pytest.approx(s.truth["swings"][sid]["roll_change_deg"], abs=1.5)
    json.dumps(s.metrics, allow_nan=False)


def test_fallback_roll_has_the_gyro_bias_removed() -> None:
    # Still arm apart from one big swing about z (across the forearm, so no roll), and a
    # constant 5 deg/s gyro offset along the forearm (y). No Orientation.csv: the fallback.
    rate, c, taps = 100.0, 5.0, [2.0, 2.45]
    t = np.arange(800) / rate
    gyro = np.zeros((t.size, 3))
    gyro[:, 1] = np.radians(5.0)
    gyro[:, 2] = np.radians(800.0) * np.exp(-0.5 * ((t - c) / 0.08) ** 2)
    acc = np.tile([0.0, 9.81, 0.0], (t.size, 1))
    acc[int(c * rate):int(c * rate) + 2, 1] += 80.0  # the impact knock
    rec = Recording(t=t, acc=acc, gyro=gyro, quat=None, rate_hz=rate, orientation="none", mock=True, source="test")
    sync = {"taps_s": taps, "warnings": [], "alignment": {
        "pairs": [{"swing": "s1", "contact_video_s": c, "impact_s": c, "ok": True, "error_ms": 0.0}],
        "tolerance_ms": 60.0, "unpaired_swings": [], "tap_only": []}}

    metrics, series = wrist_metrics(rec, sync)
    used = metrics["sensor"]["orientation_used"]
    assert used["source"] == "integrated gyro" and used["bias_dps"] == pytest.approx([0.0, 5.0, 0.0], abs=1e-3)
    m, ser = metrics["swings"]["s1"], series["swings"]["s1"]
    window_s = (WINDOW_MS[1] - WINDOW_MS[0]) / 1000
    raw = _axial_deg(rec, axis_vector("y"), c + WINDOW_MS[0] / 1000, c + WINDOW_MS[1] / 1000)
    assert raw == pytest.approx(5.0 * window_s, abs=0.01), "uncorrected, the offset alone reads as 1.25 deg of roll"
    assert m["usable"] and "gyro integrated" in m["roll_method"]
    assert m["roll_change_deg"] == pytest.approx(0.0, abs=0.1)
    assert m["roll_change_gyro_deg"] == pytest.approx(0.0, abs=0.1)
    assert ser["roll_deg"] == pytest.approx([0.0] * len(ser["roll_deg"]), abs=0.1), "the whole graph, -300..+200 ms"


def test_a_shadow_swing_gets_every_number_but_the_impact(shadow, fused) -> None:
    m = shadow.metrics["swings"]["synth-05"]
    truth = shadow.truth["swings"]["synth-05"]
    assert m["contact_source"] == "double tap" and m["usable"] is True and m["skip_reason"] is None
    assert m["impact"] is None and m["impact_s"] is None and m["align_error_ms"] is None
    assert m["roll_change_deg"] == pytest.approx(truth["roll_change_deg"], abs=2.0)
    assert m["tempo"]["backswing_to_contact_ms"] > 0 and m["tempo"]["reasons"] == []
    assert m["racket_speed_sensor"]["value"] == pytest.approx(truth["camera"]["racket_speed_ms"], rel=0.08)
    assert m["occlusion_fill"]["applied"] is True
    ser = shadow.series["swings"]["synth-05"]
    assert ser["impact"] is None and ser["contact_source"] == "double tap"
    assert list(shadow.metrics["swings"]) == list(fused.metrics["swings"]), "still in contact order"
    for sid, other in shadow.metrics["swings"].items():  # the other nine are exactly the fused session's
        if sid != "synth-05":
            want = fused.metrics["swings"][sid]
            assert other["contact_source"] == "impact spike" and other["impact_s"] == want["impact_s"]
            for k in ("roll_change_deg", "peak_roll_rate_dps", "tempo", "racket_speed_sensor"):
                assert other[k] == want[k], (sid, k)
            assert other["impact"]["ring_down_ms"] == pytest.approx(want["impact"]["ring_down_ms"], abs=1)
    json.dumps(shadow.metrics, allow_nan=False)
    json.dumps(shadow.series, allow_nan=False)


def test_misaligned_and_unpaired_swings_are_skipped_with_a_reason(session) -> None:
    sync = copy.deepcopy(session.sync)
    first = sync["alignment"]["pairs"][0]
    first["ok"], first["error_ms"] = False, 250.0
    sync["alignment"]["unpaired_swings"] = ["lost-swing"]
    metrics, series = wrist_metrics(session.rec, sync)
    assert metrics["swings"][first["swing"]]["usable"] is False
    assert "250 ms" in metrics["swings"][first["swing"]]["skip_reason"]
    assert "roll_change_deg" not in metrics["swings"][first["swing"]], "no numbers for an untrusted impact"
    assert first["swing"] not in series["swings"]
    assert metrics["swings"]["lost-swing"] == {
        "usable": False, "mock": True, "align_error_ms": None, "skip_reason": "no impact paired with this swing"}


def test_window_off_the_recording_gives_none(session) -> None:
    rec = session.rec
    slerp = Slerp(rec.t, body_rotations(rec, "body_to_world"))
    assert swing_metrics(rec, slerp, float(rec.t[0]) + 0.05, axis_vector("y")) is None
    assert swing_metrics(rec, slerp, float(rec.t[-1]) - 0.05, axis_vector("y")) is None
