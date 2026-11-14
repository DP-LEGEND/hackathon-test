"""Synthetic motion patterns, not validation against labelled player recordings."""
import numpy as np
import pytest

from pipeline.segment import _swing_pattern, find_swings, wrist_speed


def motion_clip(fps=120, slowdown=1, hand='R', angle=0, kind='swing', contacts=(.8,)):
    real = np.arange(int(2.5 * fps)) / fps
    img = np.zeros((len(real), 33, 3))
    img[:, 11, :2] = [-20, -100]
    img[:, 12, :2] = [20, -100]
    img[:, 23, :2] = [-15, 0]
    img[:, 24, :2] = [15, 0]
    def step(time, width):
        return (1 + np.tanh((real - time) / width)) / 2
    path = np.zeros((len(real), 2))
    for contact in contacts:
        if kind == 'swing':
            path[:, 0] += -.4 * step(contact - .24, .07) + 1.6 * step(contact, .035)
        elif kind == 'feed':
            path[:, 0] += 1.6 * step(contact, .035)  # fast, but no backswing
        elif kind == 'jitter':
            path[np.argmin(abs(real - contact)), 0] = 2  # isolated tracking spike
    if kind == 'walk':
        path[:, 0] = .08 * np.sin(2 * np.pi * 1.8 * real)
    if hand == 'L':
        path[:, 0] *= -1
    radians = np.radians(angle)
    rotation = np.array([[np.cos(radians), -np.sin(radians)],
                         [np.sin(radians), np.cos(radians)]])
    path = path @ rotation.T
    img[:, 16 if hand == 'R' else 15, :2] = [50, -20] + 100 * path
    # A moving player's large image-space translation must not look like a swing.
    img[:, :, 0] += (350 * real)[:, None]
    img[:, :, 1] += (20 * np.sin(2 * real))[:, None]
    return {'img': img, 'fps': fps / slowdown, 't': real * slowdown}


@pytest.mark.parametrize('fps,slowdown', [(30, 1), (120, 1), (240, 1), (120, 4)])
@pytest.mark.parametrize('hand,angle', [('R', 0), ('L', 0), ('R', 60), ('L', -60)])
def test_swing_pattern_survives_rates_slowdown_mirroring_and_rotation(fps, slowdown, hand, angle):
    raw = motion_clip(fps, slowdown, hand, angle)
    swings = find_swings(raw, slowdown=slowdown, wrist=16 if hand == 'R' else 15)
    assert len(swings) == 1
    assert raw['t'][swings[0]['peak']] / slowdown == pytest.approx(.8, abs=.05)
    assert swings[0]['speed'] >= 8


@pytest.mark.parametrize('kind', ['feed', 'jitter'])
def test_fast_non_swing_is_rejected_by_pattern_not_only_speed(kind):
    raw = motion_clip(kind=kind)
    assert wrist_speed(raw).max() > 8
    assert find_swings(raw) == []


def test_walking_translation_and_arm_pumping_are_not_swings():
    raw = motion_clip(kind='walk')
    assert np.linalg.norm(np.diff(raw['img'][:, 16, :2], axis=0), axis=1).max() * raw['fps'] / 100 > 3
    assert find_swings(raw) == []


def test_minimum_speed_remains_configurable_and_separated_swings_survive():
    raw = motion_clip(contacts=(.6, 1.5))
    assert len(find_swings(raw)) == 2
    assert find_swings(raw, min_speed=100) == []


def test_cropped_pullback_is_not_assumed_to_be_a_complete_swing():
    raw = motion_clip()
    start = int(.75 * raw['fps'])
    raw['img'] = raw['img'][start:]
    raw['t'] = raw['t'][start:]
    assert find_swings(raw) == []


def test_stronger_feed_peak_does_not_suppress_nearby_valid_swing():
    raw = motion_clip(contacts=(.9,))
    t = raw['t']
    raw['img'][:, 16, 0] += 250 * (1 + np.tanh((t - .55) / .02)) / 2
    swings = find_swings(raw)
    assert wrist_speed(raw).max() > 30
    assert len(swings) == 1
    assert t[swings[0]['peak']] == pytest.approx(.9, abs=.05)


def test_modest_landmark_noise_does_not_erase_complete_swing():
    raw = motion_clip()
    raw['img'][:, 16, :2] += np.random.default_rng(42).normal(0, 1.5, (len(raw['t']), 2))
    assert len(find_swings(raw)) == 1


def test_degenerate_local_motion_axis_is_rejected():
    track = np.zeros((300, 2))
    track[100, 0] = 5  # apparent peak, but its surrounding endpoints coincide
    assert not _swing_pattern(track, 100, 120)
