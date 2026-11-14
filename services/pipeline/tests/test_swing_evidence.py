"""Synthetic wrist trajectories exercise admission, not private clip accuracy."""
import numpy as np
import pytest
from scipy.special import erf

from pipeline.process import Options, swings_from_raw
from pipeline.segment import find_swings, swing_evidence
from pipeline.stereo import _K
from pipeline.tests.test_stereo_cli import stereo_pair


def wrist_motion(fps=120, delay=.25, speed=15., sigma=.035, reversal=True):
    times = np.arange(round(1.6 * fps) + 1) / fps
    turn = 1. - delay
    path = speed * sigma * np.sqrt(np.pi / 2) * erf((times - 1.) / (sigma * np.sqrt(2)))
    if reversal:
        # An actual pullback ends at `turn`, followed by the forward speed pulse.
        backward = -.1 * (1 - np.cos(np.pi * np.clip((times - turn + .15) / .15, 0, 1)))
        forward = -.2 + path - speed * sigma * np.sqrt(np.pi / 2) * erf((turn - 1.) / (sigma * np.sqrt(2)))
        path = np.where(times <= turn, backward, forward)
    path *= speed / np.max(np.abs(np.gradient(path, times)))
    world = np.zeros((len(times), 33, 3))
    world[:, 23, 0], world[:, 24, 0] = -.14, .14
    world[:, 16, 0] = path
    # Large whole-body drift must cancel out of the hip-relative measurement.
    world[:, :, 0] += (3 * times)[:, None]
    return world, times, path


@pytest.mark.parametrize('fps', [30, 60, 120, 240])
def test_reversal_then_15ms_peak_quarter_second_later_passes(fps):
    world, times, path = wrist_motion(fps=fps)
    assert times[np.argmin(path)] == pytest.approx(.75, abs=1 / fps)
    result = swing_evidence(world, times, 16, round(fps))
    assert result['peakWristSpeedMs'] == pytest.approx(15.)
    assert result['backswingVerified']


@pytest.mark.parametrize('delay', [.5, .59, .6])
def test_reversal_in_full_six_tenths_history_is_accepted(delay):
    world, times, _ = wrist_motion(delay=delay)
    assert swing_evidence(world, times, 16, 120)['backswingVerified']


def test_peak_between_old_and_new_width_limits_is_accepted():
    world, times, _ = wrist_motion(delay=.5, sigma=.105)
    assert swing_evidence(world, times, 16, 120)['peakWristSpeedMs'] == pytest.approx(15.)


def test_peak_wider_than_three_tenths_is_rejected():
    world, times, _ = wrist_motion(delay=.5, sigma=.15)
    with pytest.raises(ValueError, match='Not a swing'):
        swing_evidence(world, times, 16, 120)


@pytest.mark.parametrize('sigma,accepted', [(.105, True), (.16, False)])
def test_peak_width_uses_real_seconds_across_sampling_rate_switch(sigma, accepted):
    world, times, _ = wrist_motion(fps=240, delay=.5, sigma=sigma)
    keep = np.r_[np.arange(0, 240, 8), np.arange(240, len(times), 2)]
    world, times = world[keep], times[keep]
    peak = int(np.argmin(abs(times - 1.)))
    if accepted:
        assert swing_evidence(world, times, 16, peak)['backswingVerified']
    else:
        with pytest.raises(ValueError, match='Not a swing'):
            swing_evidence(world, times, 16, peak)


def test_slow_drift_without_reversal_is_rejected():
    world, times, _ = wrist_motion()
    world[:, 16, 0] = 3.2 * times
    with pytest.raises(ValueError, match='Not a swing'):
        swing_evidence(world, times, 16, 120)


def test_fast_catch_without_reversal_is_rejected():
    world, times, _ = wrist_motion(reversal=False)
    with pytest.raises(ValueError, match='Not a swing'):
        swing_evidence(world, times, 16, 120)


def test_peak_below_six_is_rejected_even_with_reversal():
    world, times, _ = wrist_motion(speed=5.9)
    with pytest.raises(ValueError, match='Not a swing'):
        swing_evidence(world, times, 16, 120)


@pytest.mark.parametrize('fps', [30, 60, 120, 240])
def test_reversal_before_a_tenth_second_gap_is_used_without_mutating_pose(fps):
    world, times, _ = wrist_motion(fps=fps, delay=.5)
    start = round(.65 * fps)
    world[start:start + round(.1 * fps), 16] = np.nan
    before = world.copy()
    assert swing_evidence(world, times, 16, fps)['backswingVerified']
    np.testing.assert_equal(world, before)


@pytest.mark.parametrize('count,accepted', [(30, True), (31, False)])
def test_reversal_gap_respects_quarter_second_limit(count, accepted):
    world, times, _ = wrist_motion(delay=.5)
    world[78:78 + count, 16] = np.nan
    if accepted:
        assert swing_evidence(world, times, 16, 120)['backswingVerified']
    else:
        with pytest.raises(ValueError, match='Not a swing'):
            swing_evidence(world, times, 16, 120)


def test_reversal_gap_respects_configured_limit():
    world, times, _ = wrist_motion(delay=.5)
    world[78:90, 16] = np.nan
    with pytest.raises(ValueError, match='Not a swing'):
        swing_evidence(world, times, 16, 120, max_gap_s=.05)


def test_long_gap_at_candidate_cannot_be_escaped_by_recentering():
    world, times, _ = wrist_motion(delay=.5)
    world[88:119, 16] = np.nan  # a valid speed peak is immediately after the gap
    with pytest.raises(ValueError, match='gap around candidate peak'):
        swing_evidence(world, times, 16, 118)


def test_reversal_older_than_six_tenths_is_not_used():
    world, times, _ = wrist_motion(delay=.8)
    with pytest.raises(ValueError, match='Not a swing'):
        swing_evidence(world, times, 16, 120)


@pytest.mark.parametrize('candidate', [-1, 193])
def test_candidate_outside_tracked_evidence_is_rejected(candidate):
    world, times, _ = wrist_motion()
    with pytest.raises(ValueError, match='outside tracked evidence'):
        swing_evidence(world, times, 16, candidate)


@pytest.mark.parametrize('slowdown', [1, 4])
@pytest.mark.parametrize('proposal_peak', [120, 132])
def test_pipeline_reads_reversal_before_candidate_window_and_preserves_contact(stereo_pair, monkeypatch, slowdown, proposal_peak):
    import pipeline.process as process
    a = stereo_pair[0]
    _, times, path = wrist_motion(delay=.5)
    n = len(times)
    a = {**a, **{key: a[key][:n].copy() for key in ('img', 'world', 'vis')}}
    a['t'], a['fps'] = times * slowdown, 120 / slowdown
    angle = -1.2 + path
    a['world'][:] = a['world'][0]
    a['world'][:, 14] = a['world'][:, 12] + .3 * np.c_[np.sin(angle + .3), np.cos(angle + .3), np.zeros(n)]
    a['world'][:, 16] = a['world'][:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(n)]
    pixels = a['world'] @ _K(900, a['size']).T
    a['img'][:, :, :2] = pixels[:, :, :2] / pixels[:, :, 2:]
    # Late sound trims the replay after the reversal; admission must still read
    # the earlier source trajectory without moving the selected contact.
    a['audio_hits'] = np.array([1.2])  # pure-array input uses real seconds
    monkeypatch.setattr(process, 'find_swings', lambda *args, **kwargs: [
        {'start': 96, 'end': 174, 'peak': proposal_peak, 'speed': 20, 'hit': 1.2}])
    swings, report = swings_from_raw(a, options=Options(hand='R', slowdown_a=slowdown))
    assert report['written'] == 1, report
    swing = swings[0]
    assert swing['metadata']['backswingVerified']
    assert swing['metadata']['sourceStartFrame'] == 72
    assert swing['metadata']['sourceContactFrame'] == 144
    assert swing['contactFrame'] == 72
    assert swing['frames'][swing['contactFrame']]['t'] == pytest.approx(.6)


@pytest.mark.parametrize('reference_hit', [1.2, .7])
def test_pipeline_reads_earlier_reversal_across_rate_boundary(stereo_pair, monkeypatch, reference_hit):
    import pipeline.process as process
    a = stereo_pair[0]
    _, times, path = wrist_motion(delay=.5)
    n = len(times)
    world = np.repeat(a['world'][:1], n, axis=0)
    angle = -1.2 + path
    world[:, 14] = world[:, 12] + .3 * np.c_[np.sin(angle + .3), np.cos(angle + .3), np.zeros(n)]
    world[:, 16] = world[:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(n)]
    pixels = world @ _K(900, a['size']).T
    image = np.concatenate([pixels[:, :, :2] / pixels[:, :, 2:], np.zeros((n, 33, 1))], axis=2)
    # First .8 real seconds at 30 Hz, then 120 Hz rendered as 4x slow motion.
    keep = np.r_[np.arange(0, 96, 4), np.arange(96, n)]
    a = {**a, 'world': world[keep], 'img': image[keep], 'vis': np.ones((len(keep), 33)),
         't': np.arange(len(keep)) / 30, 'fps': 30}
    a['audio_hits'] = np.array([reference_hit, 1.2])
    # A reference sound in the preceding rate section was not a measured
    # contact on main, so it must not replace the current section's sound.
    monkeypatch.setattr(process, 'find_swings', lambda raw, **kwargs: [] if raw['t'][0] < .8 else [
        {'start': 0, 'end': 84, 'peak': 24, 'speed': 20,
         'hit': reference_hit if kwargs.get('contact_reference') else 1.2}])
    swings, report = swings_from_raw(a, options=Options(hand='R', slowdown_a=4, a_realtime_before=.8))
    assert report['written'] == 1, report
    swing = swings[0]
    assert swing['metadata']['sourceStartFrame'] == 24
    assert swing['metadata']['sourceContactFrame'] == 72
    assert swing['contactFrame'] == 48 and swing['fpsReal'] == 120
    assert swing['frames'][swing['contactFrame']]['t'] == pytest.approx(.4)


def test_contact_reference_matches_main_with_hidden_and_missing_pixels(stereo_pair):
    a = stereo_pair[0]
    a['vis'][65:78, 16] = .05
    a['img'][70:72, 16] = np.nan
    candidates = find_swings(a, hits=np.array([.5, .6, 1.5]), confirm_s=.5,
                              speed_fallback=True, contact_reference=True)
    # Golden candidate/hit pairs checked against main's detector and smoother.
    # Visibility-masking or finite-run smoothing changes this fixture's peaks.
    assert [(event['peak'], event['hit']) for event in candidates] == [(73, .6), (181, 1.5)]


@pytest.mark.parametrize('contact_offset', [10, 12, 15])
@pytest.mark.parametrize('slowdown', [1, 4])
def test_repaired_candidate_keeps_original_sound_before_admitted_peak(stereo_pair, monkeypatch, contact_offset, slowdown):
    import pipeline.process as process
    a = stereo_pair[0]
    a['t'] *= slowdown
    a['fps'] /= slowdown
    contact = 72 - contact_offset
    a['audio_hits'] = np.array([contact / 120, .6])
    # Main attached the first transient to its original candidate. Recovered
    # pixels propose frame 72, whose nearest sound is now the second transient.
    def candidates(raw, **kwargs):
        reference = kwargs.get('contact_reference', False)
        return [{'start': 0, 'end': 114, 'peak': 60 if reference else 72,
                 'speed': 20, 'hit': contact / 120 if reference else .6}]
    monkeypatch.setattr(process, 'find_swings', candidates)
    swings, report = swings_from_raw(a, options=Options(hand='R', slowdown_a=slowdown))
    assert report['written'] == 1, report
    swing = swings[0]
    assert swing['metadata']['backswingVerified']
    assert swing['metadata']['sourcePeakSeconds'] == pytest.approx(a['t'][72])
    assert swing['metadata']['sourceContactFrame'] == contact
    assert swing['metadata']['sourceContactSeconds'] == pytest.approx(a['t'][contact])
    assert swing['metadata']['contactMethod'] == 'audio-transient'
    assert swing['metadata']['sourceStartFrame'] + swing['contactFrame'] == contact


@pytest.mark.parametrize('delta,original_hit', [(.12, .4), (.25, .4), (.2501, .4), (.12, None)])
def test_contact_anchor_range_and_unmatched_recovery(stereo_pair, monkeypatch, delta, original_hit):
    """Main's sound contact is kept within CONTACT_MATCH_S real seconds."""
    import pipeline.process as process
    from pipeline.segment import CONTACT_MATCH_S
    a = stereo_pair[0]
    a['audio_hits'] = np.array([.4, .6])
    # Place the original candidate exactly on/either side of the real-time
    # matching boundary; its native frame count alone cannot decide the match.
    reference_peak = 72 - int(round(delta * a['fps']))
    a['t'][reference_peak] = .6 - delta
    def candidates(raw, **kwargs):
        reference = kwargs.get('contact_reference', False)
        return [{'start': 0, 'end': 114, 'peak': reference_peak if reference else 72,
                 'speed': 20, 'hit': original_hit if reference else .6}]
    monkeypatch.setattr(process, 'find_swings', candidates)
    swings, report = swings_from_raw(a, options=Options(hand='R'))
    assert report['written'] == 1, report
    expected = 48 if delta <= CONTACT_MATCH_S and original_hit is not None else 72
    assert swings[0]['metadata']['sourceContactFrame'] == expected


def test_short_peak_gap_across_rate_boundary_does_not_crop_candidate_out(stereo_pair, monkeypatch):
    import pipeline.process as process
    a = stereo_pair[0]
    _, times, path = wrist_motion(delay=.5)
    n = len(times)
    world = np.repeat(a['world'][:1], n, axis=0)
    angle = -1.2 + path
    world[:, 14] = world[:, 12] + .3 * np.c_[np.sin(angle + .3), np.cos(angle + .3), np.zeros(n)]
    world[:, 16] = world[:, 14] + .32 * np.c_[np.sin(angle), np.cos(angle), np.zeros(n)]
    pixels = world @ _K(900, a['size']).T
    image = np.concatenate([pixels[:, :, :2] / pixels[:, :, 2:], np.zeros((n, 33, 1))], axis=2)
    keep = np.r_[np.arange(0, 120, 4), np.arange(120, n)]
    a = {**a, 'world': world[keep], 'img': image[keep], 'vis': np.ones((len(keep), 33)),
         't': np.arange(len(keep)) / 30, 'fps': 30}
    a['vis'][(times[keep] >= .95) & (times[keep] <= 1.025), 16] = 0
    # Per-section skeleton repair cannot fill a gap spanning both section edges.
    # Replay crops to the later finite run; evidence must retain the peak's index
    # and bridge the short gap using the full source clock.
    monkeypatch.setattr(process, 'find_swings', lambda raw, **kwargs: [] if raw['t'][0] < 1. else [
        {'start': 0, 'end': 70, 'peak': 0, 'speed': 20, 'hit': 1.2}])
    swings, report = swings_from_raw(a, options=Options(hand='R', slowdown_a=4, a_realtime_before=1.))
    assert report['written'] == 1, report
    swing = swings[0]
    assert swing['metadata']['sourceStartFrame'] > 30  # candidate peak is frame 30
    assert swing['metadata']['sourceContactFrame'] == 54
    assert swing['metadata']['sourceStartFrame'] + swing['contactFrame'] == 54
