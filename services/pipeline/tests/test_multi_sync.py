"""Dominant-event gates and sequence offsets shared by multi audio and gyro."""
import numpy as np
import pytest

from pipeline.multi_sync import match_sequence, select_swing_peaks


def test_small_feeds_before_each_swing_are_discarded_by_amplitude_and_local_maximum():
    # Some feed taps clear the session threshold but still lose to the nearby
    # full swing. Unrelated tiny ball pickups fail the session threshold itself.
    big = np.array([3., 7., 12., 18.])
    times = np.r_[big - .9, big - .25, big, [1., 10., 16.]]
    strength = np.r_[[1, 2, 1, 2], [6, 6, 7, 6], [10, 11, 12, 10], [1, 1, 1]]
    selected, amplitudes = select_swing_peaks(times, strength)
    assert selected == pytest.approx(big)
    assert amplitudes == pytest.approx([10, 11, 12, 10])


def test_top_five_reference_is_a_median_not_an_outlier_maximum():
    times = np.array([1, 4, 7, 10, 13, 16, 19], dtype=float)
    selected, _ = select_swing_peaks(times, [1000, 10, 10, 10, 10, 4.9, 5])
    assert selected == pytest.approx([1, 4, 7, 10, 13, 19])


def test_every_selected_event_is_the_single_largest_in_its_two_second_neighborhood():
    selected, _ = select_swing_peaks([0, 1.5, 3, 6, 7, 10], [7, 8, 9, 10, 10, 10])
    assert selected == pytest.approx([3, 6, 10])
    # 0 is suppressed by 1.5 even though 1.5 itself loses to 3.


def test_dense_small_gyro_peaks_are_ignored_before_local_suppression():
    times = np.arange(0, 60, .04)
    strengths = np.ones(len(times))
    swings = [3, 8, 15, 24, 35]
    for when in swings:
        strengths[np.argmin(abs(times - when))] = 100
    selected, _ = select_swing_peaks(times, strengths)
    assert selected == pytest.approx(swings)


def test_sequence_ignores_missing_leading_swing_and_returns_source_indices():
    a = np.array([2., 5., 9., 14., 20.])
    b = a[1:] + 1.25 + np.array([.01, -.01, 0, 0])
    result = match_sequence(a, b)
    assert result['offsetSeconds'] == pytest.approx(1.25)
    assert result['matchedCount'] == 4
    assert result['residualMs'] == pytest.approx(10)
    assert result['pairs'] == [[1, 0], [2, 1], [3, 2], [4, 3]]


@pytest.mark.parametrize('a,b', [([1], [2]), ([1, 4], [2, 5]), ([], [2, 5, 10])])
def test_one_or_two_events_never_establish_a_sequence_clock(a, b):
    with pytest.raises(ValueError, match='at least 3'):
        match_sequence(a, b)


def test_regular_repeated_sequence_is_ambiguous():
    with pytest.raises(ValueError, match='ambiguous'):
        match_sequence([1, 4, 7], [1, 4, 7, 10])


def test_different_spacing_does_not_match_just_the_largest_peak():
    with pytest.raises(ValueError, match='spacing does not agree'):
        match_sequence([1, 4, 8, 13], [1.5, 5, 11, 19])
