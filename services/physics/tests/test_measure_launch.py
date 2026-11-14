"""measure_launch: launch angle from side-camera image points, and the keep/change rules. Synthetic data."""

import math

import numpy as np
import pytest

from physics.compare import DEFAULT_ELEVATION_DEG
from physics.measure_launch import (
    _Frames, append_hit, decide, format_summary, launch_angle_deg, main, read_hits, summarise,
)


def _picture(theta_deg: float, roll_deg: float = 0.0, leftwards: bool = False, metres: float = 0.6):
    """Image points (pixels, y down) of a ball launched at theta, filmed by a phone tilted by roll."""
    th, ro = math.radians(theta_deg), math.radians(roll_deg)
    ends = [(0.0, 0.0), ((-1 if leftwards else 1) * metres * math.cos(th), metres * math.sin(th))]
    out = []
    for x, y in ends:  # metres, level, up positive -> turned by the tilt -> 300 px/m, y down
        x, y = x * math.cos(ro) - y * math.sin(ro), x * math.sin(ro) + y * math.cos(ro)
        out.append((960.0 + 300.0 * x, 600.0 - 300.0 * y))
    return out


@pytest.mark.parametrize("theta", [-5.0, 0.0, 3.0, 12.0, 30.0])
@pytest.mark.parametrize("leftwards", [False, True])
def test_launch_angle_from_two_points(theta, leftwards):
    p1, p2 = _picture(theta, leftwards=leftwards)
    assert launch_angle_deg(p1, p2) == pytest.approx(theta, abs=1e-9)


@pytest.mark.parametrize("roll", [-6.0, 4.0])
def test_a_tilted_phone_is_corrected_with_a_level_line(roll):
    p1, p2 = _picture(12.0, roll_deg=roll)
    line = _picture(0.0, roll_deg=roll, metres=2.0)  # a horizontal court line, same tilted phone
    assert launch_angle_deg(p1, p2) == pytest.approx(12.0 + roll, abs=1e-9)  # uncorrected: off by the tilt
    assert launch_angle_deg(p1, p2, level=line) == pytest.approx(12.0, abs=1e-9)
    assert launch_angle_deg(p1, p2, level=line[::-1]) == pytest.approx(12.0, abs=1e-9)  # either click order


def test_side_view_of_a_cross_court_shot_is_off_by_well_under_a_degree():
    # Pinhole camera on the side wall, 5 m from the ball, looking straight across the court
    # (depth X towards the far wall, Z along the court, Y up). The ball aims 14 deg cross-court.
    th, az, f = math.radians(12.0), math.radians(14.0), 1500.0
    direction = np.array([-math.sin(az) * math.cos(th), math.sin(th), math.cos(az) * math.cos(th)])
    pixels = []
    for s in (0.0, 0.6):
        X, Y, Z = np.array([5.0, 0.0, 0.0]) + s * direction
        pixels.append((960.0 + f * Z / X, 540.0 - f * Y / X))
    measured = launch_angle_deg(*pixels)
    assert measured == pytest.approx(math.degrees(math.atan(math.tan(th) / math.cos(az))), abs=1e-9)
    assert 0 < measured - 12.0 < 0.5  # about 3%: the docs' "barely changes it"


def test_bad_points_are_refused():
    with pytest.raises(ValueError, match="same"):
        launch_angle_deg((5, 5), (5, 5))
    with pytest.raises(ValueError, match="horizontal court line"):
        launch_angle_deg((0, 0), (10, -2), level=((3, 1), (3, 9)))


# ---- Rules 11-14 ----

def test_rule_11_keep_when_the_median_is_within_2_degrees():
    d = decide([11.0, 12.5, 13.0, 11.5, 12.0, 10.5], 12.0)
    assert (d["decision"], d["rule"], d["newDefault"]) == ("keep", 11, None)
    assert d["median"] == pytest.approx(11.75) and d["spread"] == pytest.approx(1.25)


@pytest.mark.parametrize("angles,new", [([6.0, 7.0, 6.5, 7.5, 6.0, 7.0], 7), ([1.0, 1.0, 0.5, 1.5, 1.0], 1)])
def test_rule_12_change_to_the_rounded_median_when_off_by_2_or_more(angles, new):
    d = decide(angles, 3.0)  # medians 6.75 (+3.75) and exactly 1.0 (-2.0: the boundary changes)
    assert (d["decision"], d["rule"], d["newDefault"]) == ("change", 12, new)


def test_rule_13_angle_matches_but_the_wall_height_does_not():
    d = decide([12.0, 13.0, 11.0, 12.0, 11.5], 12.0, wall_errors=[0.30, 0.35, 0.28])
    assert (d["decision"], d["rule"]) == ("keep", 11) and "rule 13" in d["note"]
    assert decide([12.0, 13.0, 11.0], 12.0, wall_errors=[0.1, -0.2, 0.05])["note"] is None


def test_rule_14_keep_when_one_value_cant_represent_the_hits():
    d = decide([12.0, 12.0, 12.0, 25.0, 12.0, 12.0], 12.0)
    assert (d["decision"], d["rule"]) == ("keep", 14) and d["spread"] == pytest.approx(13.0)


def test_too_few_hits_keep():
    d = decide([6.0, 7.0], 3.0)
    assert (d["decision"], d["rule"]) == ("keep", None) and "need 3" in d["why"]


def test_summary_from_a_csv_built_by_the_angle_command(tmp_path, capsys):
    hits = tmp_path / "hits.csv"
    for hit, theta in enumerate([11.0, 12.5, 13.0, 11.5, 12.0, 10.5], 1):
        p1, p2 = _picture(theta)
        main(["angle", *map(str, (*p1, *p2)), "--stroke", "forehand", "--hit", str(hit), "--csv", str(hits)])
    for hit, theta in enumerate([6.0, 7.0, 6.5, 7.5, 6.0, 7.0], 1):
        p1, p2 = _picture(theta, leftwards=True)  # camera on the other wall: the ball goes the other way
        main(["angle", *map(str, (*p1, *p2)), "--stroke", "backhand", "--hit", str(hit), "--csv", str(hits)])
    capsys.readouterr()
    assert hits.read_text().count("stroke,hit,launch_deg") == 1  # header written once
    rows = read_hits(hits)
    assert len(rows) == 12 and rows[0]["launch_deg"] == 11.0 and rows[0]["actual_wall_m"] is None
    results = summarise(rows)
    assert results["forehand"]["decision"] == "keep" and results["backhand"]["newDefault"] == 7
    main(["summary", str(hits)])
    out = capsys.readouterr().out
    assert "forehand: 6 hits, median 11.8°" in out and "KEEP 12°" in out
    assert "backhand: 6 hits" in out and "CHANGE to 7°" in out
    forehand = DEFAULT_ELEVATION_DEG["forehand"]
    assert f'DEFAULT_ELEVATION_DEG = {{"forehand": {forehand}, "backhand": 7.0}}' in out  # pastes as is
    assert format_summary(results).splitlines()[0].startswith("forehand: 6 hits")


def test_the_wall_columns_feed_rule_13(tmp_path):
    hits = tmp_path / "hits.csv"
    hits.write_text("stroke,hit,launch_deg,predicted_wall_m,actual_wall_m\n"
                    "forehand,1,12.0,1.9,1.5\nforehand,2,11.5,2.0,1.6\n\nforehand,3,12.5,1.8,1.5\n")
    d = summarise(read_hits(hits))["forehand"]
    assert d["rule"] == 11 and "+0.40 m" in d["note"]


def test_unreadable_csv_rows_and_missing_stroke_are_clear_errors(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("stroke,hit,launch_deg\nlob,1,12\n")
    with pytest.raises(SystemExit, match="stroke must be forehand or backhand"):
        main(["summary", str(bad)])
    bad.write_text("stroke,hit,launch_deg\nforehand,1,twelve\n")
    with pytest.raises(SystemExit, match="launch_deg must be a number"):
        main(["summary", str(bad)])
    with pytest.raises(SystemExit, match="--csv needs --stroke"):
        main(["angle", "0", "0", "10", "-2", "--csv", str(tmp_path / "x.csv")])


# ---- The click viewer, driven by scripted keys and clicks (no screen needed) ----

@pytest.fixture
def scripted_viewer(monkeypatch):
    """Replace the window calls; returns the list of events to play: ("key", "d") or ("click", x, y)."""
    cv2 = pytest.importorskip("cv2")
    import physics.measure_launch as ml

    class Clip:  # 40 blank frames
        def __init__(self, clip):
            pass

        def count(self):
            return 40

        def get(self, k):
            return np.zeros((4, 4, 3), np.uint8) if 0 <= k < 40 else None

    events, handler = [], {}

    def wait_key(ms):
        if not events:
            return -1
        kind, *rest = events.pop(0)
        if kind == "key":
            return ord(rest[0])
        handler["on_mouse"](cv2.EVENT_LBUTTONDOWN, *rest)
        return -1

    monkeypatch.setattr(ml, "_Frames", Clip)
    for name in ("namedWindow", "setWindowTitle", "imshow", "destroyWindow"):
        monkeypatch.setattr(cv2, name, lambda *args: None)
    monkeypatch.setattr(cv2, "setMouseCallback", lambda window, fn: handler.update(on_mouse=fn))
    monkeypatch.setattr(cv2, "waitKey", wait_key)
    return events


def test_click_viewer_steps_then_jumps_ahead_for_the_second_ball_click(scripted_viewer, tmp_path, capsys):
    scripted_viewer += [("key", "d"), ("key", "d"), ("click", 100.0, 200.0), ("click", 160.0, 190.0)]
    hits = tmp_path / "hits.csv"
    main(["click", "side.mov", "20", "--stroke", "backhand", "--hit", "2", "--csv", str(hits)])
    out = capsys.readouterr().out
    assert "frames 22 and 26" in out  # opened at 20, stepped twice, then jumped GAP_FRAMES ahead
    angle = math.degrees(math.atan2(10, 60))
    assert f"launch angle {angle:.1f}°" in out
    assert read_hits(hits)[0] == {"stroke": "backhand", "launch_deg": round(angle, 1),
                                  "predicted_wall_m": None, "actual_wall_m": None}


def test_click_viewer_level_mode_and_quit(scripted_viewer):
    from physics.measure_launch import click_points
    scripted_viewer += [("click", 0.0, 100.0), ("click", 600.0, 110.0), ("click", 10.0, 50.0), ("click", 70.0, 40.0)]
    level, first, second = click_points("side.mov", 5, gap=2, level=True)
    assert level == [(0.0, 100.0), (600.0, 110.0)] and (first[0], second[0]) == (5, 7)
    scripted_viewer += [("key", "q")]
    with pytest.raises(SystemExit, match="cancelled"):
        click_points("side.mov", 5)


# ---- The click viewer's frame reader, on a synthetic clip ----

def test_frames_of_a_synthetic_clip_give_the_launch_angle(tmp_path):
    cv2 = pytest.importorskip("cv2")
    clip = tmp_path / "side.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 240, (640, 360))
    assert writer.isOpened()
    start = np.array([100.0, 300.0])
    step = 20.0 * np.array([1.0, -math.tan(math.radians(12.0))])  # 12 deg up, 20 px a frame
    for k in range(40):
        image = np.zeros((360, 640, 3), np.uint8)
        cv2.circle(image, tuple(int(round(v)) for v in start + k * step), 6, (255, 255, 255), -1)
        writer.write(image)
    writer.release()

    def ball(image):
        ys, xs = np.nonzero(image[..., 0] > 128)
        return xs.mean(), ys.mean()

    frames = _Frames(clip, keep=5)
    first, second = ball(frames.get(20)), ball(frames.get(24))  # what two clicks 4 frames apart see
    assert first == pytest.approx(tuple(start + 20 * step), abs=0.6)  # frame 20 really is frame 20
    assert launch_angle_deg(first, second) == pytest.approx(12.0, abs=0.3)
    assert ball(frames.get(3)) == pytest.approx(tuple(start + 3 * step), abs=0.6)  # stepping back past what is kept
    assert frames.get(1000) is None
