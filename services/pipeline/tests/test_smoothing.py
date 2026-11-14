import numpy as np

from pipeline.smoothing import LIMB_JOINTS, smooth_guessed_arms


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
    P += rng.normal(0, 0.004, P.shape)  # triangulation jitter everywhere
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


def test_bone_lengths_are_locked():
    P, filled = _swing()
    S = smooth_guessed_arms(P, filled)
    for a, b in ((12, 14), (14, 16), (11, 13), (13, 15)):
        L = np.linalg.norm(S[:, b] - S[:, a], axis=1)
        assert L.std() < 1e-9
        L0 = np.linalg.norm(P[:, b] - P[:, a], axis=1)
        assert L0.std() > 1e-3  # the input did stretch


def test_protected_frames_and_torso_unchanged():
    P, filled = _swing()
    S = smooth_guessed_arms(P, filled, protect=(60, 80))
    assert np.allclose(S[60:81], P[60:81])
    torso = [j for j in range(33) if j not in LIMB_JOINTS]
    assert np.allclose(S[:, torso], P[:, torso])
