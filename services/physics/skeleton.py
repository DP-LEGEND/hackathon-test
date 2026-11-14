"""Skeleton helpers shared by metrics, ghost and synth. Owner: aryan.

A Swing (lib/ghost/types.ts) is turned into one numpy array `P` of shape
(frames, 35, 3): the 33 MediaPipe joints, then racketTip (33) and racketThroat (34).
Missing points are NaN inside `P`. The pipeline writes a joint it lost as [0, 0, 0],
so an exact [0, 0, 0] joint is read as missing and written back unchanged.

Works with either "up" convention: MediaPipe world landmarks have y pointing DOWN,
the stereo pipeline has y pointing UP. We never assume one; `up_vector` measures it
from the body (ankles to shoulders).

Swings arrive hip-centred and facing +z (towards the front wall). `to_court` puts one on
the court, in the coordinates of physics/ball.py: metres, x 0..6.40 across from the left
wall, y up from the floor, z 0..9.75 back from the front wall (so the player faces -z).
"""

from __future__ import annotations

import copy

import numpy as np

# MediaPipe Pose landmark indices.
NOSE = 0
L_SH, R_SH = 11, 12
L_EL, R_EL = 13, 14
L_WR, R_WR = 15, 16
L_PINKY, R_PINKY = 17, 18
L_INDEX, R_INDEX = 19, 20
L_THUMB, R_THUMB = 21, 22
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_FOOT, R_FOOT = 31, 32
RACKET_TIP, RACKET_THROAT = 33, 34
N_POINTS = 35

# Points that touch the floor: ankles, heels and toes (MediaPipe's foot index points).
FEET = [L_ANKLE, R_ANKLE, L_HEEL, R_HEEL, L_FOOT, R_FOOT]

# ESTIMATE until racket tracking exists: the racket head is this far beyond the hitting
# wrist, along the forearm line (elbow -> wrist).
RACKET_HEAD_M = 0.45

ARM = {
    "L": dict(sh=L_SH, el=L_EL, wr=L_WR, pinky=L_PINKY, index=L_INDEX, thumb=L_THUMB),
    "R": dict(sh=R_SH, el=R_EL, wr=R_WR, pinky=R_PINKY, index=R_INDEX, thumb=R_THUMB),
}

# Everything that moves with the torso when the shoulders turn: head, shoulders,
# both arms and hands, and the racket. Hips and legs stay put.
UPPER_BODY = list(range(0, 23)) + [RACKET_TIP, RACKET_THROAT]

# Rigid bones (a, b): no edit may change these lengths.
# The hip->shoulder diagonals are left out on purpose: the spine twists when the
# shoulders turn. Edits keep the spine length (hip centre to shoulder centre) instead.
BONES = [
    (L_SH, R_SH), (L_HIP, R_HIP),
    (L_SH, L_EL), (L_EL, L_WR), (R_SH, R_EL), (R_EL, R_WR),
    (L_WR, L_PINKY), (L_WR, L_INDEX), (L_WR, L_THUMB),
    (R_WR, R_PINKY), (R_WR, R_INDEX), (R_WR, R_THUMB),
    (L_HIP, L_KNEE), (L_KNEE, L_ANKLE), (R_HIP, R_KNEE), (R_KNEE, R_ANKLE),
    (L_ANKLE, L_HEEL), (L_ANKLE, L_FOOT), (R_ANKLE, R_HEEL), (R_ANKLE, R_FOOT),
]

# The racket is rigid with the HITTING wrist only.
def racket_bones(hand: str) -> list[tuple[int, int]]:
    wr = ARM[hand]["wr"]
    return [(RACKET_THROAT, RACKET_TIP), (wr, RACKET_TIP), (wr, RACKET_THROAT)]


def to_array(swing: dict) -> np.ndarray:
    """Swing dict -> (frames, 35, 3) float array, NaN where a point is missing."""
    frames = swing["frames"]
    P = np.full((len(frames), N_POINTS, 3), np.nan)
    for i, f in enumerate(frames):
        J = np.asarray(f["joints"], dtype=float)
        J[np.all(J == 0.0, axis=1)] = np.nan
        P[i, :33] = J
        for k, key in ((RACKET_TIP, "racketTip"), (RACKET_THROAT, "racketThroat")):
            if f.get(key) is not None:
                P[i, k] = f[key]
    return P


def from_array(swing: dict, P: np.ndarray) -> dict:
    """Deep copy of `swing` with its points replaced by `P`. Never mutates `swing`."""
    out = copy.deepcopy(swing)
    for i, f in enumerate(out["frames"]):
        f["joints"] = np.nan_to_num(P[i, :33], nan=0.0).tolist()
        for k, key in ((RACKET_TIP, "racketTip"), (RACKET_THROAT, "racketThroat")):
            if f.get(key) is not None:
                f[key] = P[i, k].tolist()
    return out


def mid(P: np.ndarray, a: int, b: int) -> np.ndarray:
    return (P[:, a] + P[:, b]) / 2


def up_vector(P: np.ndarray) -> np.ndarray:
    """Unit vector pointing up, measured from the body (ankles -> shoulders).

    Both skeleton sources have a vertical y axis (MediaPipe: y down, stereo: y up),
    so when the body is roughly along y we snap to exactly +y or -y. That keeps "up"
    identical before and after an edit, so re-measuring an edited swing is exact.
    """
    sh = mid(P, L_SH, R_SH)
    low = mid(P, L_ANKLE, R_ANKLE)
    if not np.isfinite(low).all(axis=1).any():
        low = mid(P, L_HIP, R_HIP)
    u = np.nanmean(sh - low, axis=0)
    n = np.linalg.norm(u)
    if not np.isfinite(n) or n < 1e-9:
        raise ValueError("can't tell which way is up: shoulders, hips and ankles are all missing")
    u = u / n
    if abs(u[1]) >= 0.7:
        return np.array([0.0, float(np.sign(u[1])), 0.0])
    return u


def floor_basis(up: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two unit vectors e1, e2 spanning the floor plane, with e1 x e2 = up.

    With this orientation a rotation of +a about `up` raises a heading
    atan2(v.e2, v.e1) by exactly +a.
    """
    ref = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    e1 = ref - (ref @ up) * up
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(up, e1)
    return e1, e2


def speed(points: np.ndarray, fps: float) -> np.ndarray:
    """Speed (units per second) of one point over time, shape (frames,)."""
    if len(points) < 2:
        return np.zeros(len(points))
    return np.linalg.norm(np.gradient(points, axis=0), axis=1) * fps


def hitting_hand(P: np.ndarray) -> str:
    """'R' or 'L': the hand whose wrist moves fastest relative to the hips."""
    hip = mid(P, L_HIP, R_HIP)
    best = {}
    for side in ("L", "R"):
        v = speed(P[:, ARM[side]["wr"]] - hip, 1.0)
        best[side] = np.nanpercentile(v, 95) if np.isfinite(v).any() else -1.0
    return "L" if best["L"] > best["R"] else "R"


def swing_hand(swing: dict, P: np.ndarray | None = None) -> str:
    """'R' or 'L': the hand the swing was played with.

    Trusts the hand the pipeline recorded (swing["metadata"]["hand"], else swing["hand"])
    when it is "R" or "L". Only guesses from the skeleton (`hitting_hand`) when neither is
    set, because the guess picks the wrong arm whenever the free arm moves faster.
    """
    meta = swing.get("metadata")
    recorded = meta.get("hand") if isinstance(meta, dict) else None
    for hand in (recorded, swing.get("hand")):
        if hand in ("R", "L"):
            return hand
    return hitting_hand(to_array(swing) if P is None else P)


def rotate(points: np.ndarray, centre: np.ndarray, axis: np.ndarray, angle: float) -> np.ndarray:
    """Rotate points (k, 3) by `angle` radians about the line through `centre` along unit `axis`.

    Right-hand rule. A rotation never changes the distance between two points, which is
    why every edit in ghost.py keeps bone lengths fixed.
    """
    v = points - centre
    c, s = np.cos(angle), np.sin(angle)
    return centre + v * c + np.cross(axis, v) * s + np.outer(v @ axis, axis) * (1 - c)


def bone_lengths(P: np.ndarray, hand: str = "R") -> np.ndarray:
    """(frames, bones) lengths for BONES + racket_bones(hand). NaN where a point is missing."""
    pairs = BONES + racket_bones(hand)
    return np.stack([np.linalg.norm(P[:, b] - P[:, a], axis=1) for a, b in pairs], axis=1)


def racket_head(P: np.ndarray, hand: str) -> np.ndarray:
    """(frames, 3) ESTIMATED racket head: the hitting wrist plus RACKET_HEAD_M along elbow -> wrist.

    No racket tracking yet, so this is an estimate from the forearm. NaN where the
    hitting elbow or wrist is missing.
    """
    j = ARM[hand]
    fore = P[:, j["wr"]] - P[:, j["el"]]
    with np.errstate(invalid="ignore", divide="ignore"):
        unit = fore / np.linalg.norm(fore, axis=1, keepdims=True)
    return P[:, j["wr"]] + RACKET_HEAD_M * unit


def court_axes(P: np.ndarray) -> np.ndarray:
    """Turn a skeleton that faces +z so it faces the front wall (-z) with y up. Not placed yet.

    y up (pipeline swings): rotate 180 deg about y, [x, y, z] -> [-x, y, -z].
    y down (raw MediaPipe, the mock swings): rotate 180 deg about x, [x, y, z] -> [x, -y, -z].
    The pipeline's y-up frame is MediaPipe's turned 180 deg about z (pipeline/stereo.py
    normalise), so both give the same court pose. Both are rotations, not mirror images:
    bone lengths are kept and the right hand stays on the player's right.
    """
    up = up_vector(P)
    if abs(up[1]) != 1.0:
        raise ValueError("can't turn the swing to face the front wall: the body isn't upright along y")
    s = up[1]
    return P * np.array([-s, s, -1.0])


def to_court(P: np.ndarray, hand: str, contact: int, anchor: tuple[float, float]) -> np.ndarray:
    """The skeleton in court coordinates (physics/ball.py), placed where it strikes the ball.

    1. Turn it to face the front wall (court_axes). A rotation, so no bone changes length.
    2. Stand it on the floor: the lowest foot point over the whole swing goes to y = 0.
    3. Slide it across the floor so the racket head (racket_head) at `contact` sits over
       `anchor`, a floor position (x, z). The racket head keeps its MEASURED height.

    P: (frames, 35, 3) from to_array, facing +z (the pipeline's convention), y up or down.
    Returns a new array. Missing points stay NaN.
    """
    return court_axes(P) + court_shift(P, hand, contact, anchor)


def court_shift(P: np.ndarray, hand: str, contact: int, anchor: tuple[float, float]) -> np.ndarray:
    """The slide to_court adds after court_axes, shape (3,): steps 2 and 3 of to_court.

    Add it to another swing's court_axes to place that swing exactly like this one. compare.py
    places the ghost with the player's shift, so the two bodies overlap.
    """
    if hand not in ARM:
        raise ValueError(f"hand must be 'R' or 'L', got {hand!r}")
    if not 0 <= contact < len(P):
        raise ValueError(f"contact frame {contact} is outside the swing (0-{len(P) - 1})")
    if len(anchor) != 2 or not np.isfinite(anchor).all():
        raise ValueError(f"anchor must be a finite floor position (x, z), got {anchor!r}")
    Q = court_axes(P)
    feet = Q[:, FEET, 1]
    if not np.isfinite(feet).any():
        raise ValueError("can't stand the swing on the floor: no ankle, heel or toe is visible")
    head = racket_head(Q, hand)[contact]
    if not np.isfinite(head).all():
        raise ValueError("can't place the swing on the court: the hitting elbow or wrist is missing at contact")
    x, z = anchor
    return np.array([x - head[0], -np.nanmin(feet), z - head[2]])
