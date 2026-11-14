"""compare(): the swing next to its ghost. The swing is mock data from swing_factory."""

import copy
import json

import pytest

import physics.compare as cmp
from physics.ball import COURT_WIDTH_M, DEFAULT_CONTACT, predict_ball_path
from physics.compare import METRICS, RACKET_LEVER_M, compare, estimate_racket_speed, main
from physics.ghost import FIXES
from physics.tests.swing_factory import make_swing


@pytest.fixture(scope="module")
def good():
    return make_swing()


@pytest.fixture(scope="module")
def elbow(good):
    return compare(good, "straighten_elbow", 12)


def test_result_is_plain_json_and_every_ball_path_is_predicted(elbow):
    back = json.loads(json.dumps(elbow, allow_nan=False))
    assert set(back) >= {"fix", "you", "ghost", "delta", "assumptions"}
    for side in ("you", "ghost"):
        assert back[side]["ball"]["predicted"] is True and back[side]["ball"]["label"] == "PREDICTED"
        assert back[side]["racketSpeed"]["estimate"] is True and back[side]["racketSpeed"]["label"] == "ESTIMATE"
    assert back["delta"]["ball"]["predicted"] is True and back["delta"]["ball"]["label"] == "PREDICTED"
    assert any(line.startswith("PREDICTED ball") for line in back["delta"]["summary"])
    # The coach measures for itself (coach/faults.py measure_swing); compare() doesn't speak its schema.
    assert "coachMetrics" not in back["you"] and "coachMetrics" not in back["ghost"]
    assert set(back["you"]["metrics"]) == set(METRICS)


def test_ghost_metrics_move_by_the_fix_and_nothing_else(elbow):
    d = elbow["delta"]["metrics"]
    assert d["elbow_at_contact_deg"]["change"] == pytest.approx(12.0)  # straighten = bigger inside angle
    assert d["elbow_at_contact_deg"]["ghost"] == pytest.approx(d["elbow_at_contact_deg"]["you"] + 12, abs=0.11)
    assert d["shoulder_turn_deg"]["change"] == 0.0
    assert d["wrist_release_ms"]["change"] == 0.0
    # Not 0: the stance is measured against the racket's direction at contact, which moves with the arm.
    assert abs(d["stance_open_deg"]["change"]) < 6.0
    assert d["elbow_at_contact_deg"]["unit"] == "deg" and d["wrist_release_ms"]["unit"] == "ms"
    assert elbow["delta"]["summary"][0] == (
        f"elbow at contact {d['elbow_at_contact_deg']['you']:g} -> {d['elbow_at_contact_deg']['ghost']:g} deg (+12)")


def test_ghost_swing_is_the_fixed_synthetic_swing(good, elbow):
    ghost, you = elbow["ghost"]["swing"], elbow["you"]["swing"]
    assert ghost["synthetic"] is True
    assert ghost["edits"] == [{"id": "elbow_bend", "size": -12.0, "unit": "deg"}]
    assert ghost["contactFrame"] == you["contactFrame"] == elbow["contactFrame"] == good["contactFrame"]
    assert len(ghost["frames"]) == len(you["frames"])
    assert elbow["fix"] == {"id": "straighten_elbow", "amount": 12.0, "unit": "deg"}


def test_more_shoulder_turn_swings_faster_so_the_predicted_ball_is_faster(good):
    r = compare(good, "turn_shoulders_more", 15)
    assert r["delta"]["metrics"]["shoulder_turn_deg"]["change"] == pytest.approx(15.0)
    assert r["ghost"]["racketSpeed"]["value"] > r["you"]["racketSpeed"]["value"]
    assert r["delta"]["ball"]["speedKmh"]["change"] > 0


# The new fixes: the ghost moves the fix's own metric by the amount; feet-only and
# shoulder-only edits leave the arm alone, so the PREDICTED ball can only change through
# the racket speed estimate.
@pytest.mark.parametrize("fix,amount,metric", [
    ("close_stance", 15, "stance_open_deg"),
    ("bend_elbow", 10, "elbow_at_contact_deg"),
    ("turn_shoulders_less", 15, "shoulder_turn_deg"),
])
def test_new_fixes_work_in_compare(good, fix, amount, metric):
    r = json.loads(json.dumps(compare(good, fix, amount), allow_nan=False))
    d = r["delta"]["metrics"]
    assert d[metric]["change"] == pytest.approx(-amount, abs=0.11)
    for k in ("elbow_at_contact_deg", "shoulder_turn_deg", "wrist_at_contact_deg", "wrist_release_ms"):
        if k != metric:
            assert d[k]["change"] == 0.0, k
    assert r["fix"] == {"id": fix, "amount": float(amount), "unit": "deg"}
    assert r["ghost"]["swing"]["synthetic"] is True
    assert r["ghost"]["ball"]["label"] == "PREDICTED"
    assert any(line.startswith(METRICS[metric][1]) for line in r["delta"]["summary"])


def test_closing_the_stance_doesnt_change_the_predicted_ball(good):
    r = compare(good, "close_stance", 15)
    assert r["ghost"]["racketSpeed"] == r["you"]["racketSpeed"]
    assert r["ghost"]["ball"] == r["you"]["ball"]


def test_ball_path_is_ball_py_from_the_racket_head_with_the_estimated_speed_and_aim(elbow):
    you, launch = elbow["you"], elbow["assumptions"]["launch"]["you"]
    expected = predict_ball_path(you["racketSpeed"]["value"], cmp.DEFAULT_ELEVATION_DEG["forehand"],
                                 launch["azimuth"]["value"], tuple(launch["point"]))
    assert you["ball"] == expected
    assert elbow["assumptions"]["stroke"]["value"] == "forehand"  # mock: measured from the right-hand contact
    assert elbow["assumptions"]["launchElevationDeg"] == cmp.DEFAULT_ELEVATION_DEG["forehand"] == 12.0
    assert elbow["assumptions"]["launch"]["elevation"]["label"] == "ASSUMED"
    assert elbow["assumptions"]["contactSpot"] == launch["point"]
    anchor = elbow["assumptions"]["anchor"]
    assert (anchor["x"], anchor["z"]) == (DEFAULT_CONTACT[0], DEFAULT_CONTACT[2])  # right-handed forehand spot
    assert launch["point"][0] == anchor["x"] and launch["point"][2] == anchor["z"]


def test_racket_speed_is_wrist_speed_times_the_lever_ratio(good):
    r = estimate_racket_speed(good)
    ratio = (r["forearmM"] + RACKET_LEVER_M) / r["forearmM"]
    assert r["value"] == pytest.approx(r["wristSpeedMs"] * ratio, abs=0.1)
    assert r["forearmM"] == pytest.approx(0.26, abs=1e-3)  # swing_factory's forearm
    assert not r["clamped"] and 25 < r["value"] < 60  # a plausible drive


def test_racket_speed_uses_the_real_capture_rate(good, monkeypatch):
    # The same frames captured at half the rate means everything moved half as fast.
    # (Shrink the median window to its 3-frame minimum: it is in real ms, so it would
    # otherwise cover a different number of frames at each rate.)
    monkeypatch.setattr(cmp, "SPEED_WINDOW_MS", 0.0)
    slow, fast = estimate_racket_speed(good, fps_real=120), estimate_racket_speed(good)
    assert fast["value"] == pytest.approx(2 * slow["value"], abs=0.2)


def test_impossible_racket_speed_is_clamped_and_flagged(good):
    r = estimate_racket_speed(good, fps_real=2400)
    assert r["clamped"] is True and r["value"] == 80.0 and r["rawValue"] > 80
    assert compare(good, "straighten_elbow", 5, fps_real=2400)["you"]["ball"]["predicted"] is True


def test_outcome_change_is_reported(good, monkeypatch):
    # Stand-in ball model: slower than the ghost's racket hits the tin, so tin -> in.
    you_speed = estimate_racket_speed(good)["value"]

    def fake_ball(speed, *args, **kwargs):
        r = predict_ball_path(speed, *args, **kwargs)
        r["outcome"] = "tin" if speed <= you_speed else "in"
        return r

    monkeypatch.setattr(cmp, "predict_ball_path", fake_ball)
    r = compare(good, "turn_shoulders_more", 15)
    assert r["delta"]["ball"]["outcome"] == {"you": "tin", "ghost": "in", "changed": True}
    assert r["delta"]["summary"][-1].startswith("PREDICTED ball tin -> in, ")


def test_left_hander_drives_from_the_mirrored_spot(good):
    r = compare(good, "straighten_elbow", 5, hand="L")
    x = COURT_WIDTH_M - DEFAULT_CONTACT[0]
    assert r["hand"] == "L" and r["assumptions"]["contactSpot"][0] == pytest.approx(x)
    assert r["you"]["ball"]["points"][0][0] == pytest.approx(x)


def test_input_is_never_mutated(good):
    snapshot = copy.deepcopy(good)
    compare(good, "turn_shoulders_more", 10)
    assert good == snapshot


def test_bad_inputs_give_clear_errors(good):
    with pytest.raises(ValueError, match="fixes that use it are 'straighten_elbow', 'bend_elbow'"):
        compare(good, "elbow_bend", 12)  # an edit name, not a fix
    with pytest.raises(ValueError, match="unknown fix"):
        compare(good, "swing_harder", 12)
    with pytest.raises(ValueError, match="hand"):
        compare(good, "straighten_elbow", 12, hand="right")
    with pytest.raises(ValueError, match="within"):
        compare(good, "straighten_elbow", 500)


def test_every_fix_runs_through_compare(good):
    for fix in FIXES:
        r = compare(good, fix, 10)
        assert r["fix"]["id"] == fix and r["ghost"]["swing"]["synthetic"] is True


def test_cli_prints_the_json(good, tmp_path, capsys):
    path = tmp_path / "swing.json"
    path.write_text(json.dumps(good))
    main([str(path), "straighten_elbow", "12", "--no-swings"])
    out = json.loads(capsys.readouterr().out)
    assert "swing" not in out["you"] and "swing" not in out["ghost"]
    assert out["delta"]["metrics"]["elbow_at_contact_deg"]["change"] == pytest.approx(12.0)

    main([str(path), "hold_wrist_cock", "-20", "--fps-real", "240"])  # negative amount = the opposite edit
    out = json.loads(capsys.readouterr().out)
    assert out["ghost"]["swing"]["synthetic"] is True and out["fpsReal"] == 240.0


def test_cli_reports_errors_without_a_traceback(tmp_path):
    path = tmp_path / "swing.json"
    path.write_text(json.dumps(make_swing(duration=0.5)))
    with pytest.raises(SystemExit, match="unknown fix"):
        main([str(path), "swing_harder", "1"])
    with pytest.raises(SystemExit, match="No such file"):
        main([str(tmp_path / "missing.json"), "straighten_elbow", "1"])
