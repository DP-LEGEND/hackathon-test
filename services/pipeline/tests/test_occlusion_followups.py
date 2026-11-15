"""Real-clip feedback regressions; no private source recordings are required."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

from pipeline.process import Options, swings_from_raw
from pipeline.segment import find_swings, swing_evidence
from pipeline.stereo import _K, clean, normalise
from pipeline.tests.test_stereo_cli import stereo_pair


@pytest.mark.parametrize('count', [10, 12, 15])
@pytest.mark.parametrize('mode', ['mono', 'stereo', 'fallback'])
def test_low_visibility_arm_is_kept_flagged_and_contact_is_unchanged(stereo_pair, count, mode):
    a, b, *_ = stereo_pair
    options = Options(hand='R', focal_a=900, focal_b=900)
    a['audio_hits'] = np.array([.6, 1.5])
    if mode == 'fallback':
        b['vis'][:] = 0
    second = None if mode == 'mono' else b
    baseline, _ = swings_from_raw(a, second, options)
    for raw in (a, b) if mode == 'stereo' else (a,):
        raw['vis'][66:66 + count, [12, 14, 16]] = .3
    swings, report = swings_from_raw(a, second, options)
    assert report['written'] == 2
    assert [s['metadata']['sourceContactFrame'] for s in swings] == [72, 180]
    assert [s['contactFrame'] for s in swings] == [s['contactFrame'] for s in baseline]
    first = swings[0]
    offset = first['metadata']['sourceStartFrame']
    for frame in first['frames'][66 - offset:66 + count - offset]:
        assert all(frame['filled'][joint] for joint in (12, 14, 16))
        assert all(frame['visibility'][joint] == .3 for joint in (12, 14, 16))
    assert first['metadata']['hittingArmFilledPercent'] == pytest.approx(100 * count / len(first['frames']))
    if mode == 'fallback':
        assert first['source'] == 'mono' and first['metadata']['fallbackReason']


def test_bounded_missing_root_uses_mono_fill(stereo_pair):
    a, _, *_ = stereo_pair
    a['audio_hits'] = np.array([.6])
    a['img'][65:77, 23] = np.nan
    a['world'][65:77, 23] = np.nan
    swings, report = swings_from_raw(a, options=Options(hand='R'))
    assert report['written'] == 2
    assert swings[0]['metadata']['sourceContactFrame'] == 72
    assert swings[0]['frames'][swings[0]['contactFrame']]['filled'][23]


@pytest.mark.parametrize('target', [9.7, 11.9])
def test_moderate_speed_articulated_swing_with_backswing_is_written(stereo_pair, target):
    a = stereo_pair[0]
    times = a['t']
    fixed = np.repeat(a['world'][:1], len(times), axis=0)

    def pose(width):
        angle = (-1.2 - .4 * (1 + np.tanh((times - .65) / .045)) / 2
                 + 2.8 * (1 + np.tanh((times - 1.) / width)) / 2)
        world = fixed.copy()
        world[:, 14] = world[:, 12] + .3 * np.c_[np.sin(angle + .3), np.cos(angle + .3), np.zeros(len(times))]
        world[:, 16] = world[:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(len(times))]
        return world

    def peak(width):
        measured = normalise(clean(pose(width)), .5)
        return np.linalg.norm(np.gradient(measured[:, 16], times, axis=0), axis=1).max()

    width = brentq(lambda value: peak(value) - target, .035, .16)
    a['world'] = pose(width)
    projection = a['world'] @ _K(900, a['size']).T
    a['img'][:, :, :2] = projection[:, :, :2] / projection[:, :, 2:]
    a['audio_hits'] = np.array([1.])
    swings, report = swings_from_raw(a, options=Options(hand='R'))
    assert report['written'] == 1, report
    assert swings[0]['metadata']['peakWristSpeedMs'] == pytest.approx(target, abs=.01)
    assert swings[0]['metadata']['backswingVerified']
    assert swings[0]['metadata']['sourceContactFrame'] == 120


@pytest.mark.parametrize('tap_filter,expected', [(False, 2), (True, 1)])
def test_candidate_spacing_matches_main_before_quality_checks(stereo_pair, tap_filter, expected):
    a = stereo_pair[0]
    candidates = find_swings(a, min_gap_real_s=2.5 if tap_filter else .5,
                             min_speed=7 if tap_filter else 8, speed_fallback=True)
    _, report = swings_from_raw(a, options=Options(hand='R', tap_filter=tap_filter))
    assert report['detected'] == len(candidates) == expected


def test_cropped_hitting_wrist_does_not_reintroduce_hidden_evidence(stereo_pair, monkeypatch):
    import pipeline.process as process
    a = stereo_pair[0]
    a['vis'][:35, 16] = 0
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 0, 'end': 110, 'peak': 72, 'speed': 10}])
    swings, report = swings_from_raw(a, options=Options(hand='R'))
    assert report['written'] == 1, report
    assert swings[0]['metadata']['sourceStartFrame'] == 35
    assert swings[0]['metadata']['sourceContactFrame'] == 72


@pytest.mark.parametrize('name,contact', [('swing_fh_over_rotation.json', 48),
                                         ('swing_2116_bh_stereo.json', 59)])
def test_gate_accepts_checked_in_hero_skeleton_without_changing_contact(name, contact):
    # These are saved public skeletons, not a re-run of the private source videos.
    swing = json.loads((Path(__file__).resolve().parents[3] / 'public/swings' / name).read_text())
    before = copy.deepcopy(swing)
    evidence = swing_evidence(np.array([frame['joints'] for frame in swing['frames']]),
                              np.array([frame['t'] for frame in swing['frames']]),
                              15 if swing.get('metadata', {}).get('hand') == 'L' else 16,
                              swing['contactFrame'])
    assert 6 <= evidence['peakWristSpeedMs'] < 12 and evidence['backswingVerified']
    assert swing == before and swing['contactFrame'] == contact


def test_auto_hand_skips_a_wrist_that_is_hidden_at_the_peak(stereo_pair, monkeypatch):
    """Real clip IMG_2115 swing 0022: the off-hand wrist reappears at the peak
    and out-speeds the tracked racket wrist. The gate tests the tracked wrist."""
    import pipeline.process as process
    a = stereo_pair[0]
    a['vis'][:73, 15] = 0                 # off-hand hidden through the peak
    a['img'][73:, 15, 0] += 400           # its reappearance is a pixel jump
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 24, 'end': 114, 'peak': 72, 'speed': 10}])
    swings, report = swings_from_raw(a, options=Options(hand='auto'))
    assert report['written'] == 1, report
    assert swings[0]['metadata']['hand'] == 'R'
    assert swings[0]['metadata']['backswingVerified']
    assert swings[0]['metadata']['sourceContactFrame'] == 72


def test_manual_hand_never_switches_to_the_other_wrist(stereo_pair, monkeypatch):
    import pipeline.process as process
    a = stereo_pair[0]
    a['vis'][:73, 15] = 0
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 24, 'end': 114, 'peak': 72, 'speed': 10}])
    swings, report = swings_from_raw(a, options=Options(hand='L'))
    assert report['written'] == 0 and swings == []
