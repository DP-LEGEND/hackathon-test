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
    intervals = np.diff(times)
    cadence = 1 / B['fps'] if 'fps' in B else float(np.median(intervals))
    contiguous = np.asarray(B.get('frame_contiguous', intervals <= 1.5 * cadence), dtype=bool)
    # Ordinary resampling between adjacent recorded frames is allowed. Missing
    # camera frames are not confident observations, regardless of endpoint vis.
    exact_sample = np.zeros(len(tb), dtype=bool)
    for endpoint, weight in ((i0, 0.0), (i0 + 1, 1.0)):
        exact = np.isclose(w[:, 0, 0], weight, rtol=0, atol=1e-9)
        exact_sample |= exact
        img[exact] = B["img"][endpoint[exact]]
        vis[exact] = B["vis"][endpoint[exact]]
    valid = (tb >= times[0]) & (tb <= times[-1]) & (exact_sample | contiguous[i0])
    img[~valid] = np.nan
    vis[~valid] = 0
    return img, vis


def calibrate(A: dict, B: dict, scale: float, offset: float, f_a=1400.0, f_b=1400.0,
              min_vis=0.8, thresh_px=6.0, *, diagnostics: dict | None = None) -> dict:
    imgB, visB = sample_b_at_a(A, B, scale, offset)
    J = CALIB_JOINTS
    m = (A["vis"][:, J] > min_vis) & (visB[:, J] > min_vis)
    m &= np.isfinite(A["img"][:, J, :2]).all(axis=-1) & np.isfinite(imgB[:, J, :2]).all(axis=-1)
    pa, pb = A["img"][:, J, :2][m], imgB[:, J, :2][m]
    if diagnostics is not None:
        diagnostics.update(sharedJointSamples=int(len(pa)), requiredJointSamples=12,
                           reprojectionErrorPx=None, tolerancePx=float(thresh_px), status="failed")
    if len(pa) < 12:
        if diagnostics is not None:
            diagnostics['reason'] = 'too few tracked joints'
        raise ValueError("Not enough shared visible joints for stereo calibration; check sync and camera overlap")
    Ka, Kb = _K(f_a, tuple(A["size"])), _K(f_b, tuple(B["size"]))
    na = cv2.undistortPoints(pa.reshape(-1, 1, 2), Ka, None).reshape(-1, 2)
    nb = cv2.undistortPoints(pb.reshape(-1, 1, 2), Kb, None).reshape(-1, 2)
    E, inl = cv2.findEssentialMat(na, nb, np.eye(3), cv2.RANSAC, 0.999, thresh_px / ((f_a + f_b) / 2))
    if E is None or inl is None:
        if diagnostics is not None:
            diagnostics['reason'] = 'calibration could not estimate camera geometry'
        raise ValueError("Stereo calibration failed; check sync, focal lengths and camera baseline")
    candidates = []
    for candidate in np.split(E, len(E) // 3):
        count, R, t, mask = cv2.recoverPose(candidate, na, nb, np.eye(3), mask=inl.copy())
        candidates.append((count, R, t, mask))
    count, R, t, mask = max(candidates, key=lambda item: item[0])
    if count < 12 or count / len(pa) < 0.25:
        if diagnostics is not None:
            diagnostics.update(reason='too few tracked joints in front of both cameras',
                               positiveDepthJointSamples=int(count))
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
    if diagnostics is not None:
        diagnostics['reprojectionErrorPx'] = reprojection if np.isfinite(reprojection) else None
    if not np.isfinite(reprojection) or reprojection > thresh_px:
        if diagnostics is not None:
            diagnostics['reason'] = 'calibration reprojection error exceeds tolerance'
        raise ValueError("Stereo reprojection error exceeds calibration tolerance")
    if diagnostics is not None:
        diagnostics.update(status='calibrated', reason=None)
    return {"Ka": Ka, "Kb": Kb, "R": R, "t": t, "scale": scale, "offset": offset,
            "inliers": float(good.mean()), "n": int(len(pa)), "reprojectionErrorPx": reprojection}


def triangulate(A: dict, B: dict, cal: dict, f0: int, f1: int, min_vis=.1,
                *, provenance: bool = False):
    """Weighted stereo, or a confident ray constrained by an observed bone.

    The optional provenance tuple is (points, filled, visibility). One-view
    depths are estimates even when their image landmark is confidently seen.
    A landmark with visibility <= min_vis (default .1, the same cutoff the
    swing finder uses) is hidden: its predicted pixels never enter the DLT, so
    the bone-constrained one-view recovery can place it from the other camera.
    """
    from pipeline.kinematics import PARENTS

    imgB, visB = sample_b_at_a(A, B, cal["scale"], cal["offset"])
    images = [A['img'][f0:f1, :, :2], imgB[f0:f1, :, :2]]
    confidence = [np.clip(np.nan_to_num(v[f0:f1], nan=0., posinf=0., neginf=0.), 0, 1)
                  for v in (A['vis'], visB)]
    visible = [np.isfinite(p).all(axis=-1) & (v > min_vis)
               for p, v in zip(images, confidence)]
    confident = [seen & (v >= .5) for seen, v in zip(visible, confidence)]
    confidence = [np.where(np.isfinite(p).all(axis=-1), v, 0.) for p, v in zip(images, confidence)]
    matrices = [cal['Ka'] @ np.hstack([np.eye(3), np.zeros((3, 1))]),
                cal['Kb'] @ np.hstack([cal['R'], cal['t']])]
    out = np.full((f1 - f0, 33, 3), np.nan)
    both = visible[0] & visible[1]
    frame, joint = np.nonzero(both)
    if len(frame):
        equations = []
        for camera in (0, 1):
            pixels = images[camera][frame, joint]
            projection = matrices[camera]
            weight = np.sqrt(confidence[camera][frame, joint])[:, None]
            equations.extend([(pixels[:, 0, None] * projection[2] - projection[0]) * weight,
                              (pixels[:, 1, None] * projection[2] - projection[1]) * weight])
        _, _, vt = np.linalg.svd(np.stack(equations, axis=1))
        homogeneous = vt[:, -1]
        with np.errstate(divide='ignore', invalid='ignore'):
            xyz = homogeneous[:, :3] / homogeneous[:, 3:]
        valid = np.isfinite(xyz).all(axis=1)
        for camera in (0, 1):
            projected = np.c_[xyz, np.ones(len(xyz))] @ matrices[camera].T
            with np.errstate(divide='ignore', invalid='ignore'):
                error = np.linalg.norm(projected[:, :2] / projected[:, 2:] - images[camera][frame, joint], axis=1)
            valid &= (projected[:, 2] > 0) & (error <= 12)
        out[frame[valid], joint[valid]] = xyz[valid]
    stereo = out.copy()
    # Low visibility is weighted evidence, not an absent landmark. Retain it
    # while marking the result as guessed so downstream metrics can skip it.
    filled = ~np.isfinite(out).all(axis=2) | ~(confident[0] & confident[1])
    stereo[~(confident[0] & confident[1])] = np.nan
    times = np.asarray(A['t'][f0:f1])
    centers = [np.zeros(3), -cal['R'].T @ cal['t'].reshape(3)]
    inverse = [np.linalg.inv(cal['Ka']), cal['R'].T @ np.linalg.inv(cal['Kb'])]
    # The root can be hidden too. Recover it from an observed adjacent hip or
    # shoulder before walking outward; never bootstrap two missing anchors.
    for child, parent in [(23, 24), (23, 11), *PARENTS.items()]:
        bones = stereo[:, child] - stereo[:, parent]
        lengths = np.linalg.norm(bones, axis=1)
        reference = np.flatnonzero(np.isfinite(lengths) & (lengths > 1e-9))
        if not len(reference):
            continue
        length = float(np.median(lengths[reference]))
        candidates = np.flatnonzero(((visible[0][:, child] ^ visible[1][:, child])
                                     | (confident[0][:, child] ^ confident[1][:, child]))
                                    & np.isfinite(out[:, parent]).all(axis=1)
                                    & ~np.isfinite(out[:, child]).all(axis=1))
        for frame in candidates:
            nearest = reference[np.argmin(abs(times[reference] - times[frame]))]
            if abs(times[nearest] - times[frame]) > .25:
                continue  # ambiguous depth with no recent reliable direction
            camera = int(confidence[1][frame, child] > confidence[0][frame, child])
            center = centers[camera]
            ray = inverse[camera] @ np.r_[images[camera][frame, child], 1.]
            ray /= np.linalg.norm(ray)
            offset = center - out[frame, parent]
            along = float(np.dot(ray, offset))
            discriminant = along * along - (np.dot(offset, offset) - length * length)
            if discriminant < -1e-9:
                continue
            roots = -along + np.array([-1., 1.]) * np.sqrt(max(0., discriminant))
            points = center + roots[:, None] * ray
            valid = (roots > 0) & (points[:, 2] > 0) & ((points @ cal['R'].T + cal['t'].reshape(3))[:, 2] > 0)
            points = points[valid]
            if not len(points):
                continue
            expected = out[frame, parent] + bones[nearest] / lengths[nearest] * length
            out[frame, child] = points[np.argmin(np.linalg.norm(points - expected, axis=1))]
    visibility = np.maximum(*confidence)
    return (out, filled, visibility) if provenance else out


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
    directions = sh - an
    valid = np.isfinite(directions).all(axis=1)
    up = np.mean(directions[valid], axis=0) if valid.any() else np.zeros(3)
    if np.linalg.norm(up) < 1e-6:
        # Feet can leave the frame: use the required torso, not invented ankles.
        directions = sh - hp
        valid = np.isfinite(directions).all(axis=1)
        if not valid.any():
            raise ValueError("Cannot level skeleton: no valid torso direction")
        up = np.mean(directions[valid], axis=0)
    if np.linalg.norm(up) < 1e-6:
        raise ValueError("Cannot level skeleton: degenerate torso direction")
    up /= np.linalg.norm(up)
    fwd = np.array([0, 0, 1.0]) - up * up[2]
    if np.linalg.norm(fwd) < 1e-6:
        fwd = np.array([1., 0, 0]) - up * up[0]
    fwd /= np.linalg.norm(fwd)
    right = np.cross(up, fwd)
    Rm = np.stack([right, up, fwd])
    centre = ((X[:, 23] + X[:, 24]) / 2)[:, None, :]
    return (X - centre) @ Rm.T


def clean(X: np.ndarray, win: int = 5, max_gap: int = 12, *, filled=None, provenance=False):
    """Repair only short bounded bone-angle gaps, preserving lengths."""
    from pipeline.kinematics import repair_pose
    return repair_pose(X, max_gap=max_gap, win=win, filled=filled, provenance=provenance)
