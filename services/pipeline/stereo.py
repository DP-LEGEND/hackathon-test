"""Two-camera 3D: triangulate MediaPipe 2D joints from two synced phones.

No checkerboard needed: the player's own joints, seen by both cameras over a whole
session, are the correspondences. We estimate the essential matrix from them
(focal lengths guessed, ~1400 px for 1080p phone wide cameras), recover the
relative pose, triangulate every frame, then scale and level the result:
- scale so the median torso (shoulder-mid to hip-mid) is `torso_m` metres,
- rotate so "up" is the mean ankle-mid -> shoulder-mid direction.

Time sync: clip B time = scale * clip A time + offset (from audio ball hits,
see segment.audio_hits). For an iPhone 4x slo-mo render vs a real-time iPad,
scale = 0.25.
"""

from __future__ import annotations

import cv2
import numpy as np

JOINTS = list(range(33))
CALIB_JOINTS = [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]


def _K(f: float, size=(1920, 1080)) -> np.ndarray:
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1.0]])


def sample_b_at_a(A: dict, B: dict, scale: float, offset: float):
    """For every frame of A, B's image joints + visibility at the same real moment (linear interp)."""
    tb = A["t"] * scale + offset
    times = np.asarray(B["t"])
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError("Camera B needs at least two increasing timestamps")
    i0 = np.clip(np.searchsorted(times, tb, side="right") - 1, 0, len(times) - 2)
    w = ((tb - times[i0]) / (times[i0 + 1] - times[i0]))[:, None, None]
    img = (1 - w) * B["img"][i0] + w * B["img"][i0 + 1]
    vis = np.minimum(B["vis"][i0], B["vis"][i0 + 1])
    for endpoint, weight in ((i0, 0.0), (i0 + 1, 1.0)):
        exact = np.isclose(w[:, 0, 0], weight, rtol=0, atol=1e-9)
        img[exact] = B["img"][endpoint[exact]]
        vis[exact] = B["vis"][endpoint[exact]]
    valid = (tb >= times[0]) & (tb <= times[-1])
    img[~valid] = np.nan
    vis[~valid] = 0
    return img, vis


def calibrate(A: dict, B: dict, scale: float, offset: float, f_a=1400.0, f_b=1400.0,
              min_vis=0.8, thresh_px=6.0) -> dict:
    imgB, visB = sample_b_at_a(A, B, scale, offset)
    J = CALIB_JOINTS
    m = (A["vis"][:, J] > min_vis) & (visB[:, J] > min_vis)
    m &= np.isfinite(A["img"][:, J, 0]) & np.isfinite(imgB[:, J, 0])
    pa, pb = A["img"][:, J, :2][m], imgB[:, J, :2][m]
    Ka, Kb = _K(f_a, tuple(A["size"])), _K(f_b, tuple(B["size"]))
    na = cv2.undistortPoints(pa.reshape(-1, 1, 2), Ka, None).reshape(-1, 2)
    nb = cv2.undistortPoints(pb.reshape(-1, 1, 2), Kb, None).reshape(-1, 2)
    E, inl = cv2.findEssentialMat(na, nb, np.eye(3), cv2.RANSAC, 0.999, thresh_px / ((f_a + f_b) / 2))
    _, R, t, _ = cv2.recoverPose(E, na, nb, np.eye(3), mask=inl.copy())
    return {"Ka": Ka, "Kb": Kb, "R": R, "t": t, "scale": scale, "offset": offset,
            "inliers": float(inl.mean()), "n": int(len(pa))}


def triangulate(A: dict, B: dict, cal: dict, f0: int, f1: int, min_vis=0.3) -> np.ndarray:
    """(f1-f0, 33, 3) metric 3D in camera-A frame, NaN where either camera lost the joint."""
    imgB, visB = sample_b_at_a(A, B, cal["scale"], cal["offset"])
    P1 = cal["Ka"] @ np.hstack([np.eye(3), np.zeros((3, 1))])
    P2 = cal["Kb"] @ np.hstack([cal["R"], cal["t"]])
    out = np.full((f1 - f0, 33, 3), np.nan)
    for k, i in enumerate(range(f0, f1)):
        a, b = A["img"][i, :, :2], imgB[i, :, :2]
        ok = np.isfinite(a[:, 0]) & np.isfinite(b[:, 0]) & (A["vis"][i] > min_vis) & (visB[i] > min_vis)
        if ok.sum() == 0:
            continue
        X = cv2.triangulatePoints(P1, P2, a[ok].T.astype(float), b[ok].T.astype(float))
        out[k, ok] = (X[:3] / X[3]).T
    return out


def normalise(X: np.ndarray, torso_m: float = 0.5) -> np.ndarray:
    """Scale to metres, centre on the hips, rotate so +y is up (MediaPipe-like but y up)."""
    sh = (X[:, 11] + X[:, 12]) / 2
    hp = (X[:, 23] + X[:, 24]) / 2
    an = (X[:, 27] + X[:, 28]) / 2
    s = torso_m / np.nanmedian(np.linalg.norm(sh - hp, axis=1))
    X = X * s
    up = np.nanmean((sh - an) * s, axis=0)
    up /= np.linalg.norm(up)
    fwd = np.array([0, 0, 1.0]) - up * up[2]
    fwd /= np.linalg.norm(fwd)
    right = np.cross(up, fwd)
    Rm = np.stack([right, up, fwd])
    centre = ((X[:, 23] + X[:, 24]) / 2)[:, None, :]
    return (X - centre) @ Rm.T


# parent -> child chains, walked outwards from the hips
CHAIN = [(23, 11), (24, 12), (11, 13), (13, 15), (15, 19), (12, 14), (14, 16), (16, 20),
         (23, 25), (25, 27), (27, 31), (24, 26), (26, 28), (28, 32), (11, 0)]


def clean(X: np.ndarray, win: int = 5) -> np.ndarray:
    """Fill short gaps, smooth over time, then force each bone to its median length."""
    from pipeline.pose import smooth

    Y = X.copy()
    for j in range(Y.shape[1]):
        for d in range(3):
            v = Y[:, j, d]
            ok = np.isfinite(v)
            if ok.sum() >= 2:
                Y[:, j, d] = np.interp(np.arange(len(v)), np.where(ok)[0], v[ok])
    Y = smooth(Y, win)
    for a, b in CHAIN:
        L = np.nanmedian(np.linalg.norm(Y[:, b] - Y[:, a], axis=1))
        d = Y[:, b] - Y[:, a]
        n = np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
        Y[:, b] = Y[:, a] + d / n * L
    return Y
