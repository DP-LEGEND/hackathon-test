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
    m &= np.isfinite(A["img"][:, J, :2]).all(axis=-1) & np.isfinite(imgB[:, J, :2]).all(axis=-1)
    pa, pb = A["img"][:, J, :2][m], imgB[:, J, :2][m]
    if len(pa) < 12:
        raise ValueError("Not enough shared visible joints for stereo calibration; check sync and camera overlap")
    Ka, Kb = _K(f_a, tuple(A["size"])), _K(f_b, tuple(B["size"]))
    na = cv2.undistortPoints(pa.reshape(-1, 1, 2), Ka, None).reshape(-1, 2)
    nb = cv2.undistortPoints(pb.reshape(-1, 1, 2), Kb, None).reshape(-1, 2)
    E, inl = cv2.findEssentialMat(na, nb, np.eye(3), cv2.RANSAC, 0.999, thresh_px / ((f_a + f_b) / 2))
    if E is None or inl is None:
        raise ValueError("Stereo calibration failed; check sync, focal lengths and camera baseline")
    candidates = []
    for candidate in np.split(E, len(E) // 3):
        count, R, t, mask = cv2.recoverPose(candidate, na, nb, np.eye(3), mask=inl.copy())
        candidates.append((count, R, t, mask))
    count, R, t, mask = max(candidates, key=lambda item: item[0])
    if count < 12 or count / len(pa) < 0.25:
        raise ValueError("Stereo calibration has too few points in front of both cameras")
    good = mask.ravel() != 0
    p1 = Ka @ np.hstack([np.eye(3), np.zeros((3, 1))])
    p2 = Kb @ np.hstack([R, t])
    homogeneous = cv2.triangulatePoints(p1, p2, pa[good].T, pb[good].T)
    with np.errstate(divide="ignore", invalid="ignore"):
        xyz = homogeneous[:3] / homogeneous[3]
        proj_a = Ka @ xyz
        proj_b = Kb @ (R @ xyz + t)
        error = np.maximum(np.linalg.norm((proj_a[:2] / proj_a[2]).T - pa[good], axis=1),
                           np.linalg.norm((proj_b[:2] / proj_b[2]).T - pb[good], axis=1))
    reprojection = float(np.median(error))
    if not np.isfinite(reprojection) or reprojection > thresh_px:
        raise ValueError("Stereo reprojection error exceeds calibration tolerance")
    return {"Ka": Ka, "Kb": Kb, "R": R, "t": t, "scale": scale, "offset": offset,
            "inliers": float(good.mean()), "n": int(len(pa)), "reprojectionErrorPx": reprojection}


def triangulate(A: dict, B: dict, cal: dict, f0: int, f1: int, min_vis=0.3) -> np.ndarray:
    """(f1-f0, 33, 3) metric 3D in camera-A frame, NaN where either camera lost the joint."""
    imgB, visB = sample_b_at_a(A, B, cal["scale"], cal["offset"])
    P1 = cal["Ka"] @ np.hstack([np.eye(3), np.zeros((3, 1))])
    P2 = cal["Kb"] @ np.hstack([cal["R"], cal["t"]])
    out = np.full((f1 - f0, 33, 3), np.nan)
    for k, i in enumerate(range(f0, f1)):
        a, b = A["img"][i, :, :2], imgB[i, :, :2]
        ok = np.isfinite(a).all(axis=-1) & np.isfinite(b).all(axis=-1) & (A["vis"][i] > min_vis) & (visB[i] > min_vis)
        if ok.sum() == 0:
            continue
        X = cv2.triangulatePoints(P1, P2, a[ok].T.astype(float), b[ok].T.astype(float))
        out[k, ok] = (X[:3] / X[3]).T
    # Keep only points in front of both cameras and consistent with both images.
    for k, i in enumerate(range(f0, f1)):
        xyz = out[k]
        za = xyz[:, 2]
        xb = xyz @ cal["R"].T + cal["t"].reshape(3)
        pa = xyz @ cal["Ka"].T
        pb = xb @ cal["Kb"].T
        with np.errstate(divide="ignore", invalid="ignore"):
            ea = np.linalg.norm(pa[:, :2] / pa[:, 2:] - A["img"][i, :, :2], axis=1)
            eb = np.linalg.norm(pb[:, :2] / pb[:, 2:] - imgB[i, :, :2], axis=1)
        valid = (za > 0) & (xb[:, 2] > 0) & (ea <= 12) & (eb <= 12)
        out[k, ~valid] = np.nan
    return out


def normalise(X: np.ndarray, torso_m: float = 0.5) -> np.ndarray:
    """Scale to metres, centre on the hips, rotate so +y is up (MediaPipe-like but y up)."""
    sh = (X[:, 11] + X[:, 12]) / 2
    hp = (X[:, 23] + X[:, 24]) / 2
    an = (X[:, 27] + X[:, 28]) / 2
    lengths = np.linalg.norm(sh - hp, axis=1)
    lengths = lengths[np.isfinite(lengths) & (lengths > 1e-6)]
    if not len(lengths) or not np.isfinite(torso_m) or torso_m <= 0:
        raise ValueError("Cannot set metric scale: no valid stereo torso")
    s = torso_m / np.median(lengths)
    X = X * s
    up = np.nanmean((sh - an) * s, axis=0)
    if not np.isfinite(up).all() or np.linalg.norm(up) < 1e-6:
        raise ValueError("Cannot level skeleton: no valid shoulder-to-ankle direction")
    up /= np.linalg.norm(up)
    fwd = np.array([0, 0, 1.0]) - up * up[2]
    if np.linalg.norm(fwd) < 1e-6:
        fwd = np.array([1., 0, 0]) - up * up[0]
    fwd /= np.linalg.norm(fwd)
    right = np.cross(up, fwd)
    Rm = np.stack([right, up, fwd])
    centre = ((X[:, 23] + X[:, 24]) / 2)[:, None, :]
    return (X - centre) @ Rm.T


# parent -> child chains, walked outwards from the hips
CHAIN = [(23, 11), (24, 12), (11, 13), (13, 15), (15, 19), (12, 14), (14, 16), (16, 20),
         (23, 25), (25, 27), (27, 31), (24, 26), (26, 28), (28, 32), (11, 0)]


def clean(X: np.ndarray, win: int = 5, max_gap: int = 12) -> np.ndarray:
    """Fill only bounded short gaps, smooth, and constrain observed bone lengths.

    Never extrapolate a limb through an occlusion or fill an entire missing joint.
    """
    from pipeline.pose import smooth

    Y = X.copy()
    for j in range(Y.shape[1]):
        for d in range(3):
            v = Y[:, j, d]
            observed = np.flatnonzero(np.isfinite(v))
            for left, right in zip(observed[:-1], observed[1:]):
                if 1 < right - left <= max_gap + 1:
                    v[left + 1:right] = np.interp(np.arange(left + 1, right), [left, right], v[[left, right]])
    missing = ~np.isfinite(Y)
    Y = smooth(Y, win)
    Y[missing] = np.nan
    for a, b in CHAIN:
        d = Y[:, b] - Y[:, a]
        lengths = np.linalg.norm(d, axis=1)
        valid = np.isfinite(lengths) & (lengths > 1e-9)
        if valid.any():
            length = np.median(lengths[valid])
            Y[valid, b] = Y[valid, a] + d[valid] / lengths[valid, None] * length
    return Y
