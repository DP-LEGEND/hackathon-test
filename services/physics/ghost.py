"""Ghost and fault injector: change a swing's skeleton by a known amount. Owner: aryan.

One function, two jobs:
- Fault injector: take a good swing and add a fault of known size
  (e.g. elbow bend +12 deg) to make labelled synthetic training data (physics/synth.py).
- Ghost: take the player's swing and apply the opposite edit to show the fix
  (e.g. apply_fix(swing, "straighten_elbow", 12)).

How bone lengths stay fixed: every edit rotates a rigid part of the body around a
joint (forearm about the elbow, hand about the wrist, upper body about the hips).
A rotation can't change the distance between two points, so no bone stretches.

Each edit fades in and out with a smooth cosine ramp so the replay never jumps.

Timing uses `fps_real`, the REAL capture rate (120 for a 4x slow-mo clip rendered at
30 fps). If it isn't given we use swing["fps"].
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from physics.metrics import (
    RELEASE_WINDOW_MS, contact_frame, real_fps, shoulder_coil, shoulder_yaw, wrist_angle,
)
from physics.skeleton import (
    ARM, L_HIP, R_HIP, RACKET_THROAT, RACKET_TIP, UPPER_BODY, from_array, hitting_hand, mid,
    rotate, to_array, up_vector,
)

# Signed edits. The sign says which way; a fault and its fix are the same edit with
# opposite signs.
EDITS = {
    "elbow_bend": {
        "unit": "deg", "max_abs": 60.0,
        "doc": "+ bends the hitting elbow more around contact, - straightens it",
    },
    "shoulder_turn": {
        "unit": "deg", "max_abs": 60.0,
        "doc": "+ turns the shoulders further in the backswing, - turns them less. "
               "Full size at the top of the backswing, zero at contact.",
    },
    "wrist_early": {
        "unit": "ms", "max_abs": 150.0,
        "doc": "+ breaks (uncocks) the wrist earlier, - holds the wrist cock longer",
    },
}

# Coaching fixes the ghost can show: fix id -> (edit id, sign of the amount).
FIXES = {
    "straighten_elbow": ("elbow_bend", -1.0),
    "turn_shoulders_more": ("shoulder_turn", +1.0),
    "hold_wrist_cock": ("wrist_early", -1.0),
}

# Elbow edit timing (ms around contact): full strength from 100 ms before to 50 ms after.
ELBOW_FULL_MS = (100.0, 50.0)
ELBOW_RAMP_MS = 150.0


def _envelope(n: int, fps: float, centre: int, before_ms: float, after_ms: float,
              ramp_ms: float, hold_after: bool = False) -> np.ndarray:
    """Weight per frame: 1 inside [centre-before, centre+after], cosine ramps to 0 outside."""
    t = (np.arange(n) - centre) / fps * 1000.0
    w = np.zeros(n)
    w[(t >= -before_ms) & (t <= after_ms)] = 1.0
    rise = (t < -before_ms) & (t > -before_ms - ramp_ms)
    w[rise] = 0.5 - 0.5 * np.cos(np.pi * (t[rise] + before_ms + ramp_ms) / ramp_ms)
    if hold_after:
        w[t > after_ms] = 1.0
    else:
        fall = (t > after_ms) & (t < after_ms + ramp_ms)
        w[fall] = 0.5 + 0.5 * np.cos(np.pi * (t[fall] - after_ms) / ramp_ms)
    return w


def _hinge_axes(a: np.ndarray, b: np.ndarray, min_sin: float = 0.05) -> np.ndarray:
    """Per-frame unit axis (a x b) for bending segment b relative to segment a.

    Rotating b by +x about this axis opens the angle between a and b by x.
    Where a and b are nearly in line (straight arm) the cross product is meaningless,
    so we borrow the nearest good frame's axis and make it perpendicular to b.
    NaN where no axis is available.
    """
    n = len(a)
    ax = np.cross(a, b)
    with np.errstate(invalid="ignore", divide="ignore"):
        norm = np.linalg.norm(ax, axis=1)
        lens = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
        good = np.isfinite(norm) & (lens > 0) & (norm > min_sin * lens)
        out = np.full((n, 3), np.nan)
        if not good.any():
            return out
        out[good] = ax[good] / norm[good, None]
        idx, bad = np.flatnonzero(good), np.flatnonzero(~good)
        if len(bad):
            pos = np.searchsorted(idx, bad)
            left = idx[np.clip(pos - 1, 0, len(idx) - 1)]
            right = idx[np.clip(pos, 0, len(idx) - 1)]
            near = np.where(np.abs(bad - left) <= np.abs(right - bad), left, right)
            borrowed = out[near]
            bn = b[bad] / np.linalg.norm(b[bad], axis=1, keepdims=True)
            borrowed = borrowed - np.sum(borrowed * bn, axis=1, keepdims=True) * bn
            bl = np.linalg.norm(borrowed, axis=1, keepdims=True)
            out[bad] = np.where(bl > 1e-6, borrowed / bl, np.nan)
    return out


def _bend(P: np.ndarray, joint: int, a: np.ndarray, b: np.ndarray, subtree: list[int],
          delta: np.ndarray) -> None:
    """Rotate `subtree` about `joint` so the angle between segments a and b opens by `delta`
    radians per frame (negative closes it). Clamped so a limb never folds through itself.
    Edits P in place."""
    axes = _hinge_axes(a, b)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.sum(a * b, 1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    phi = np.arccos(np.clip(cos, -1, 1))
    delta = np.clip(delta, -phi, np.pi - phi)
    for i in range(len(P)):
        if not (np.isfinite(delta[i]) and delta[i] != 0 and np.isfinite(axes[i]).all()
                and np.isfinite(P[i, joint]).all()):
            continue
        P[i, subtree] = rotate(P[i, subtree], P[i, joint], axes[i], delta[i])


def _elbow_bend(P, size, *, hand, contact, fps, up):
    j = ARM[hand]
    upper = P[:, j["el"]] - P[:, j["sh"]]
    fore = P[:, j["wr"]] - P[:, j["el"]]
    w = _envelope(len(P), fps, contact, *ELBOW_FULL_MS, ELBOW_RAMP_MS)
    # Opening the upper-arm/forearm direction angle closes the inside elbow angle: + = more bend.
    hand_and_racket = [j["wr"], j["pinky"], j["index"], j["thumb"], RACKET_TIP, RACKET_THROAT]
    _bend(P, j["el"], upper, fore, hand_and_racket, np.radians(size) * w)


def _shoulder_turn(P, size, *, hand, contact, fps, up):
    yaw = shoulder_yaw(P, up)
    _, turn = shoulder_coil(yaw, contact)
    if abs(turn) < 1.0:
        raise ValueError("the shoulders don't turn before contact, so there is no turn to change")
    if size <= -abs(turn):
        raise ValueError(f"can't reduce the shoulder turn by {-size:g} deg: it is only {abs(turn):.0f} deg")
    # Scale the coil: every frame before contact keeps its share of the turn, so the
    # top of the backswing moves by exactly `size` and contact doesn't move at all.
    s = np.sign(turn)
    w = np.zeros(len(P))
    pre = slice(0, contact + 1)
    w[pre] = np.clip(s * (yaw[pre] - yaw[contact]) / abs(turn), 0, 1)
    beta = np.radians(s * size * np.nan_to_num(w))
    centre = mid(P, L_HIP, R_HIP)
    for i in np.flatnonzero(beta):
        if np.isfinite(centre[i]).all():
            P[i, UPPER_BODY] = rotate(P[i, UPPER_BODY], centre[i], up, beta[i])


def _wrist_early(P, size, *, hand, contact, fps, up):
    j = ARM[hand]
    th = np.radians(wrist_angle(P, hand))
    ok = np.isfinite(th)
    if ok.sum() < 2:
        raise ValueError("the hitting wrist and hand aren't visible, so the wrist can't be edited")
    # Time-shift the wrist-angle curve: the new angle at time t is the old angle at
    # t + size. Full shift from the release window to the end; a ramp before it
    # (long enough that time never runs backwards).
    n = len(P)
    ramp = max(200.0, 3.0 * abs(size))
    w = _envelope(n, fps, contact, RELEASE_WINDOW_MS[0], 0.0, ramp, hold_after=True)
    t = np.arange(n) / fps
    tau = np.clip(t + size / 1000.0 * w, t[0], t[-1])
    target = np.interp(tau, t[ok], th[ok])
    fore = P[:, j["wr"]] - P[:, j["el"]]
    hand_dir = P[:, j["index"]] - P[:, j["wr"]]
    # Opening the forearm/hand direction angle by d closes the inside wrist angle by d.
    _bend(P, j["wr"], fore, hand_dir,
          [j["pinky"], j["index"], j["thumb"], RACKET_TIP, RACKET_THROAT], th - target)


_EDIT_FUNCS = {"elbow_bend": _elbow_bend, "shoulder_turn": _shoulder_turn, "wrist_early": _wrist_early}


def edit_swing(swing: dict, edits: Mapping[str, float], fps_real: float | None = None,
               hand: str | None = None) -> dict:
    """Return a new swing with the edits applied, in order. Never mutates the input.

    edits: e.g. {"elbow_bend": 12, "shoulder_turn": -15, "wrist_early": 40}
    fps_real: real capture rate (frames per real second). Default: swing["fps"].
    hand: "R" or "L". Default: whichever wrist moves fastest.

    The result carries `contactFrame` (filled in if the input lacked it),
    `synthetic: true`, and an `edits` list saying what was changed.
    """
    if not swing.get("frames"):
        raise ValueError("swing has no frames")
    for k, v in edits.items():
        if k not in EDITS:
            raise ValueError(f"unknown edit {k!r}; known edits: {', '.join(EDITS)}")
        if not np.isfinite(v) or abs(v) > EDITS[k]["max_abs"]:
            raise ValueError(f"{k} must be within +/-{EDITS[k]['max_abs']:g} {EDITS[k]['unit']}, got {v}")
    P = to_array(swing)
    fps = real_fps(swing, fps_real)
    hand = hand or hitting_hand(P)
    contact = contact_frame(swing, P, hand)
    up = up_vector(P)
    for k, v in edits.items():
        if v != 0:
            _EDIT_FUNCS[k](P, float(v), hand=hand, contact=contact, fps=fps, up=up)
    out = from_array(swing, P)
    out["contactFrame"] = contact
    out["synthetic"] = True
    out["edits"] = list(swing.get("edits") or []) + [
        {"id": k, "size": float(v), "unit": EDITS[k]["unit"]} for k, v in edits.items()
    ]
    if "id" in swing:
        out["id"] = f"{swing['id']}+" + "+".join(f"{k}{v:+g}" for k, v in edits.items())
    return out


def inject_fault(swing: dict, fault_id: str, size: float, fps_real: float | None = None,
                 hand: str | None = None) -> dict:
    """Add one fault of known size, e.g. inject_fault(good, "elbow_bend", 12)."""
    return edit_swing(swing, {fault_id: size}, fps_real, hand)


def apply_fix(swing: dict, fix_id: str, amount: float, fps_real: float | None = None,
              hand: str | None = None) -> dict:
    """Return the ghost: the swing with one coaching fix applied. Never mutates the input.

    fix_id: one of FIXES, e.g. apply_fix(swing, "straighten_elbow", 12).
    """
    if fix_id not in FIXES:
        raise ValueError(f"unknown fix {fix_id!r}; known fixes: {', '.join(FIXES)}")
    edit, sign = FIXES[fix_id]
    return edit_swing(swing, {edit: sign * amount}, fps_real, hand)
