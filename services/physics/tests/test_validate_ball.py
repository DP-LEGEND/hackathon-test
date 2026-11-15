"""physics/validate_ball.py: checking the PREDICTED ball against the real ball.

Everything here is synthetic (a made-up camera, a made-up flight, MOCK frames), except the last
test, which checks the saved results against the saved compare files.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

import physics.validate_ball as vb
from physics.ball import launch_direction


def _camera(center=(5.3, 1.15, 9.7), pitch_deg=5.0, focal=1540.0) -> vb.Camera:
    """Looks at the front wall (along -z), tilted down by pitch_deg, like the demo phone."""
    base = np.array([[1.0, 0, 0], [0, -1.0, 0], [0, 0, -1.0]])  # image x = court x, image y = down
    p = math.radians(pitch_deg)
    tilt = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    R = tilt @ base
    C = np.array(center, float)
    return vb.Camera(focal, 960.0, 540.0, R, -R @ C)


COURT = np.array([[0, 4.545, 0], [6.4, 4.545, 0], [0, 1.755, 0], [6.4, 1.755, 0], [0, 0.455, 0],
                  [6.4, 0.455, 0], [0, 0, 0], [6.4, 0, 0], [3.2, 0, 5.415], [4.8, 0, 5.415], [6.4, 0, 5.415]])


def test_calibration_recovers_a_known_camera():
    cam = _camera()
    rng = np.random.default_rng(0)
    px = cam.project(COURT) + rng.normal(0, 0.7, (len(COURT), 2))
    got, rms = vb.calibrate(COURT, px, (1920, 1080))
    assert got.focal == pytest.approx(1540, rel=0.03)
    assert np.linalg.norm(got.center - cam.center) < 0.08
    assert rms < 1.5


def test_calibration_needs_six_landmarks():
    with pytest.raises(ValueError, match="at least 6"):
        vb.calibrate(COURT[:5], _camera().project(COURT[:5]), (1920, 1080))


def _synthetic_pixels(cam, contact=(5.7, 0.62, 4.5), kmh=136.0, az=-20.0, el=7.5,
                      rebound=(-4.0, 0.5, 9.0), frames=range(16, 52), noise=0.7, seed=1):
    v0 = kmh / 3.6 * launch_direction(el, az)
    times = np.array([f / 120.0 for f in frames])
    fl = vb.flight(contact, v0, rebound, times.max() + 0.01)
    px = cam.project(vb._positions_at(fl, times)) + np.random.default_rng(seed).normal(0, noise, (len(times), 2))
    return times, px, fl["wall"], cam.project(contact)[0]


def test_the_fit_finds_the_real_wall_hit_from_pixels_and_the_feet():
    cam = _camera()
    times, px, wall, cpx = _synthetic_pixels(cam)
    fit = vb.fit_flight(cam, cpx, times, px, z_feet=4.5)
    got = fit["flight"]["wall"]
    assert got["point"][1] == pytest.approx(wall["point"][1], abs=0.05)   # height on the front wall
    assert got["point"][0] == pytest.approx(wall["point"][0], abs=0.15)   # across the wall
    assert fit["x"][2] == pytest.approx(-20.0, abs=2.5)                    # direction
    assert fit["rmsPx"] < 2.0
    assert fit["sigma"]["frontWallHeightM"] < 0.1


def test_without_the_feet_depth_trades_off_against_speed():
    # Same pixels, contact assumed 2 m further back: the wall hit barely moves, the speed does.
    cam = _camera()
    times, px, wall, cpx = _synthetic_pixels(cam)
    near = vb.fit_flight(cam, cpx, times, px, z_feet=4.5)
    far = vb.fit_flight(cam, cpx, times, px, z_feet=6.5)
    assert abs(near["flight"]["wall"]["point"][1] - far["flight"]["wall"]["point"][1]) < 0.1
    assert far["x"][1] > near["x"][1] + 3  # m/s: further away needs a faster ball


def test_feet_go_on_the_floor_through_the_camera():
    cam = _camera()
    feet = [(5.0, 0.0, 4.4), (4.8, 0.0, 4.6)]
    x, z = vb.feet_on_floor(cam, [tuple(p) for p in cam.project(feet)])
    assert (x, z) == (pytest.approx(4.9, abs=0.01), pytest.approx(4.5, abs=0.01))


def test_the_tracker_follows_a_moving_ball_and_drops_still_marks():
    bg = np.full((180, 320), 200, np.int16)
    dets = {}
    for f in range(20):
        g = bg.copy()
        g[60:64, 40:44] = 20                                # a mark on the wall, there every frame
        u, v = 250 - 8 * f, 90 + 0.1 * f * f                 # the ball, moving left and dropping
        g[int(v) - 2:int(v) + 2, int(u) - 2:int(u) + 2] = 15
        g[120:170, 140 + 2 * f:180 + 2 * f] = 30             # the player: far too big to be the ball
        dets[f] = vb.detect(g.astype(np.uint8), bg)
    tr = vb.best_track(vb.link(vb.drop_still(dets)))
    assert tr is not None and len(tr) >= 18
    for f, u, v, _ in tr:
        assert u == pytest.approx(250 - 8 * f, abs=1.5) and v == pytest.approx(90 + 0.1 * f * f, abs=1.5)


def test_the_contact_pixel_comes_from_a_steady_incoming_ball_not_a_hand():
    ball = [(f, 1084 + 0.4 * (f - 100), 680 + 2.3 * (f - 100), 100) for f in range(100, 112)]
    hand = [(f, 800 + 6 * (f - 100), 600 + 2 * (f - 100), 160 - 13 * (f - 100)) for f in range(100, 116)]
    u, v = vb.contact_pixel([ball, hand], 116)
    assert (u, v) == (pytest.approx(1090.4, abs=0.5), pytest.approx(716.8, abs=0.5))
    assert vb.contact_pixel([hand], 116) is None  # its blob shrinks from 160 to 5 px: not a ball


def test_errors_are_measured_minus_predicted():
    tracked = {"azimuthDeg": -21.2, "speedKmh": 136.0, "elevationDeg": 7.6, "contactPointM": [5.73, 0.62, 4.48],
               "frontWall": {"xM": 4.0, "heightM": 1.17, "tS": 0.133}}
    predicted = {"azimuthDeg": -13.5, "speedKmh": 133.2, "elevationDeg": 12.0, "contactPointM": [5.4, 0.6, 7.0],
                 "frontWall": {"xM": 3.72, "heightM": 1.92, "tS": 0.211}}
    e = vb.errors(tracked, predicted)
    assert e == {"directionDeg": -7.7, "frontWallHeightM": -0.75, "frontWallXM": 0.28, "speedKmh": 2.8,
                 "elevationDeg": -4.4, "timeToWallS": -0.078, "contactSpotM": 2.54}


def _entry_files(tmp_path, monkeypatch, cam):
    """A fake clip, court file and swing entry; compare file from the repo."""
    monkeypatch.setattr(vb, "VALIDATION_DIR", tmp_path)
    (tmp_path / "clip.mov").write_bytes(b"MOCK")
    court = {"frameSize": [1920, 1080], "source": "MOCK",
             "points": [{"name": str(i), "court": list(map(float, X)), "px": list(map(float, p))}
                        for i, (X, p) in enumerate(zip(COURT, cam.project(COURT)))]}
    (tmp_path / "court.json").write_text(json.dumps(court))
    return {"swing": "mock-swing", "stroke": "forehand", "clip": "clip.mov", "court": "court.json",
            "compare": "public/swings/compare_fh_over_rotation_turn_shoulders_less.json",
            "contactFileFrame": 1000, "contactSource": "MOCK", "fpsReal": 120, "slowdown": 4}


def test_hand_labels_stand_in_when_the_tracker_fails_and_the_result_says_so(tmp_path, monkeypatch):
    cam = _camera()
    entry = _entry_files(tmp_path, monkeypatch, cam)
    times, px, wall, cpx = _synthetic_pixels(cam, frames=range(16, 52, 4), noise=0.0)
    labels = {"contactPx": [float(cpx[0]), float(cpx[1])], "note": "MOCK",
              "ball": [[1000 + round(t * 120), float(u), float(v)] for t, (u, v) in zip(times, px)]}
    (tmp_path / "labels_mock-swing.json").write_text(json.dumps(labels))
    feet = [tuple(p) for p in cam.project([(4.9, 0.0, 4.5), (4.9, 0.0, 4.5)])]
    r = vb.check_swing(entry, tmp_path, None, tracker=lambda *a: {"contactPx": None, "points": []},
                       feet=lambda *a: feet)
    assert r["method"] == "hand-labelled"
    assert any("hand-labelled" in n for n in r["notes"])
    assert r["tracked"]["frontWall"]["heightM"] == pytest.approx(wall["point"][1], abs=0.05)
    assert r["predicted"]["label"] == "PREDICTED" and r["predicted"]["elevationLabel"] == "ASSUMED"


def test_no_ball_and_no_labels_is_an_error_not_a_guess(tmp_path, monkeypatch):
    cam = _camera()
    entry = _entry_files(tmp_path, monkeypatch, cam)
    feet = [tuple(p) for p in cam.project([(4.9, 0.0, 4.5), (4.9, 0.0, 4.5)])]
    with pytest.raises(ValueError, match="no hand labels"):
        vb.check_swing(entry, tmp_path, None, tracker=lambda *a: {"contactPx": (900.0, 700.0), "points": []},
                       feet=lambda *a: feet)


def test_saved_results_quote_the_saved_compare_files():
    # If a compare file changes, its saved validation is stale: rerun python -m physics.validate_ball.
    entries = json.loads((vb.VALIDATION_DIR / "swings.json").read_text())["swings"]
    for entry in entries:
        result = json.loads((vb.RESULTS_DIR / f"{entry['swing']}.json").read_text())
        cmp = json.loads((vb.REPO / entry["compare"]).read_text())
        assert result["predicted"] == vb.predicted_from_compare(cmp), entry["swing"]
        assert result["method"] in ("tracked", "hand-labelled")
        assert result["error"] == vb.errors(result["tracked"], result["predicted"])
