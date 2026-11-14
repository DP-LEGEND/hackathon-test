import numpy as np

from pipeline.smoothing import LIMB_JOINTS, slerp, smooth_guessed_arms


def _swing(n=120, seed=0):
    rng = np.random.default_rng(seed)
    a = np.linspace(0, 2.0, n)
    P = np.zeros((n, 33, 3))
    P[:, 23], P[:, 24] = [-0.1, 0, 0], [0.1, 0, 0]
    P[:, 11], P[:, 12], P[:, 0] = [-0.2, 0.5, 0], [0.2, 0.5, 0], [0, 0.7, 0]
    P[:, 14] = P[:, 12] + np.stack([0.28 * np.sin(a), -0.28 * np.cos(a), np.zeros(n)], 1)
    P[:, 16] = P[:, 14] + np.stack([0.26 * np.sin(1.5 * a), -0.26 * np.cos(1.5 * a), 0.05 * a], 1)
    for j, p in ((13, 11), (15, 13), (25, 23), (27, 25), (26, 24), (28, 26)):
        P[:, j] = P[:, p] + [0.0, -0.3, 0.0]
    for j, p in ((17, 15), (19, 15), (21, 15), (18, 16), (20, 16), (22, 16), (29, 27), (31, 27), (30, 28), (32, 28)):
        P[:, j] = P[:, p] + [0.0, -0.08, 0.02]
    filled = np.zeros((n, 33), bool)
    filled[20:45, 16] = True
    P[20:45, 16] += rng.normal(0, 0.05, (25, 3))  # noisy fill
    return P, filled


def _accel(x):
    return np.linalg.norm(np.diff(x, 2, axis=0), axis=-1)


def test_guessed_run_follows_a_smooth_arc():
    P, filled = _swing()
    S = smooth_guessed_arms(P, filled)
    assert np.median(_accel(S[18:47, 16])) < 0.2 * np.median(_accel(P[18:47, 16]))


def test_only_guessed_frames_change():
    P, filled = _swing()
    S = smooth_guessed_arms(P, filled)
    assert np.allclose(S[~filled[:, 16]], P[~filled[:, 16]])
    other = [j for j in range(33) if j != 16]
    assert np.allclose(S[:, other], P[:, other])


def test_protected_frames_unchanged():
    P, filled = _swing()
    filled[60:80, 16] = True
    S = smooth_guessed_arms(P, filled, protect=(60, 80))
    assert np.allclose(S[60:81], P[60:81])


def test_guessed_bone_keeps_its_length():
    P, filled = _swing()
    S = smooth_guessed_arms(P, filled)
    L = np.linalg.norm(S[20:45, 16] - S[20:45, 14], axis=1)
    assert np.allclose(L, np.median(np.linalg.norm(P[~filled[:, 16], 16] - P[~filled[:, 16], 14], axis=1)))


def test_slerp_never_collapses_even_near_opposite():
    u = np.array([1.0, 0.0, 0.0])
    v = np.array([-0.999, 0.0447, 0.0])
    w = slerp(u, v, np.linspace(0, 1, 11))
    assert np.allclose(np.linalg.norm(w, axis=1), 1.0, atol=1e-6)


def test_ends_more_than_120_degrees_apart_keep_the_fill_shape():
    P, filled = _swing()
    P[19, 16] = P[19, 14] + [0.26, 0, 0]
    P[45, 16] = P[45, 14] + [-0.26, 0.01, 0]  # ~180 degrees apart: no slerp through the body
    S = smooth_guessed_arms(P, filled)
    L = np.linalg.norm(S[20:45, 16] - S[20:45, 14], axis=1)
    assert (L > 0.2).all()  # never collapses


def test_middle_ground_calms_measured_frames_but_not_contact():
    P, filled = _swing()
    rng = np.random.default_rng(1)
    P[:, 14] += rng.normal(0, 0.01, P[:, 14].shape)  # measured but noisy elbow
    S = smooth_guessed_arms(P, filled, protect=(60, 80), smooth_measured=True)
    assert np.allclose(S[60:81], P[60:81])
    assert np.median(_accel(S[:50, 14])) < 0.5 * np.median(_accel(P[:50, 14]))
    torso = [j for j in range(33) if j not in LIMB_JOINTS]
    assert np.allclose(S[:, torso], P[:, torso])
