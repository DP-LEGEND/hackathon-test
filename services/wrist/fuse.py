"""Phone + camera fusion: forearm alignment, occlusion fill and racket speed. Owner: Henoch.

Everything here is an ESTIMATE, and every output says so ("label": "ESTIMATE"). Code
measures, Claude explains: the coach may quote these numbers with that label, never
improve on them.

Time. A camera frame's sensor time is impact_s + (t_frame - t_contactFrame) + shift.
The sensor's impact spike anchors contact. `shift` (searched within +-60 ms) absorbs a
video contact frame that is a frame or two off.

Alignment (align_swing). On frames where the camera saw the hitting elbow and wrist (not
"filled"), the camera's forearm direction (elbow -> wrist) should equal the phone's forearm
axis turned by the phone's orientation, then by one fixed rotation from the sensor's world
axes to the camera's. We fit that rotation and the exact strap axis by alternating least
squares (no strap is perfectly straight). Then we report the angle between the two
directions on those frames: the AGREEMENT ERROR. That error is in-sample, so a holdout check
also hides the visible frames nearest contact, refits, and reports the error on them. That
tells you how well the fill should do inside an occlusion. Both camera sources are
right-handed (pipeline/stereo.py normalise() is a proper rotation), so the fit is too.

Occlusion fill (fill_swing). On frames where the camera's hitting elbow or wrist is marked
"filled", the forearm direction comes from the phone instead, and bone lengths stay fixed:
- Wrist filled: wrist = elbow + forearm length x phone direction. The hand points move with
  the wrist, so the hand bones keep their lengths too.
- Elbow filled, wrist seen: the elbow goes on the circle that keeps both the upper-arm and
  forearm lengths, at the point closest to wrist - forearm length x phone direction.
The filled flags stay true (the camera still didn't see those joints). The fill is listed
in metadata.wristSensorFill. Racket points, if a swing has them, aren't touched.

Racket speed (racket_speed). The forearm, hand and racket are treated as one rigid lever:
locked wrist, racket along the forearm.
    v_head = v_wrist (camera) + w_forearm (gyro) x LEVER_M along the forearm
The two parts are added as vectors when the alignment is trusted, otherwise as if
parallel (an upper bound). The result has the same shape as physics.compare's
estimate_racket_speed(), so a swing can carry it as the optional field
swing["racketSpeedSensor"] (attach_racket_speed). Physics' compare() can then use it in
place of the pose estimate. That hook is aryan's to add.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from physics.compare import RACKET_SPEED_RANGE_MS
from physics.metrics import contact_frame
from physics.skeleton import ARM, from_array, swing_hand, to_array
from wrist.load import Recording

LEVER_M = 0.65                  # ESTIMATE: wrist joint to the racket head
SPEED_WINDOW_MS = (-20.0, 0.0)  # "at contact": the 20 ms up to the impact spike
SHIFT_MAX_MS, SHIFT_STEP_MS = 60.0, 5.0   # camera contact-frame error searched, then refined to 1 ms
AGREE_OK_DEG = 12.0             # median agreement must be below this to fill or to add vectors
MIN_VISIBLE = 12                # visible forearm frames needed for a fit
MIN_SPREAD = 0.1                # the forearm must sweep: 2nd / 1st singular value of its directions
STRAP_MAX_DEG = 30.0            # a fitted strap axis further than this from the nominal one is rejected
HOLDOUT_FRACTION = 0.25         # visible frames nearest contact hidden for the holdout check
FIT_ITERS = 8
HAND_KEYS = ("pinky", "index", "thumb")
ESTIMATE = {"estimate": True, "label": "ESTIMATE"}


def read_swings(path: str | Path) -> dict[str, dict[str, Any]]:
    """Pipeline swing JSONs (a folder, or one file): {swing id: swing}."""
    path = Path(path)
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(path.rglob("*.json")) if path.is_dir() else [path]:
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        items = data if isinstance(data, list) else data.get("swings", [data]) if isinstance(data, dict) else []
        for s in items:
            if isinstance(s, dict) and s.get("frames"):
                out[str(s.get("id", p.stem))] = s
    return out


def frame_times(swing: dict[str, Any]) -> np.ndarray:
    """Real seconds per frame: the frames' own t when it increases, else frame / fpsReal."""
    t = np.array([f.get("t", np.nan) for f in swing["frames"]], float)
    if np.isfinite(t).all() and (np.diff(t) > 0).all():
        return t
    return np.arange(len(t)) / float(swing.get("fpsReal") or swing["fps"])


def filled_flags(swing: dict[str, Any]) -> Optional[np.ndarray]:
    """(frames, 33) filled flags, or None when any frame lacks them (provenance unknown)."""
    rows = [f.get("filled") for f in swing["frames"]]
    if any(not isinstance(r, list) or len(r) != 33 for r in rows):
        return None
    return np.array(rows, bool)


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return v / np.where(n > 0, n, np.nan)


def _angle_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.degrees(np.arccos(np.clip(np.sum(_unit(a) * _unit(b), axis=-1), -1.0, 1.0)))


def _summary(err: np.ndarray) -> dict[str, Any]:
    return {"median": round(float(np.median(err)), 1), "p90": round(float(np.percentile(err, 90)), 1),
            "max": round(float(err.max()), 1), "n": int(err.size)}


def fit_alignment(cam_dirs: np.ndarray, rots: Rotation, axis0: np.ndarray) -> tuple[Rotation, np.ndarray, np.ndarray]:
    """Fixed rotation R (sensor world -> camera) and strap axis a (phone axes, unit) with
    cam_dirs ~ R(rots(a)), by alternating least squares from +axis0 and -axis0.

    Returns (R, a, per-frame angle error in deg).
    """
    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # spread is checked by the caller
        for sign in (1.0, -1.0):
            a = sign * axis0 / np.linalg.norm(axis0)
            for _ in range(FIT_ITERS):
                R = Rotation.align_vectors(cam_dirs, rots.apply(a))[0]
                a = rots.inv().apply(R.inv().apply(cam_dirs)).sum(axis=0)
                a = a / np.linalg.norm(a)
            R = Rotation.align_vectors(cam_dirs, rots.apply(a))[0]
            err = _angle_deg(cam_dirs, R.apply(rots.apply(a)))
            if best is None or np.median(err) < np.median(best[2]):
                best = (R, a, err)
    assert best is not None
    return best


def align_swing(rec: Recording, slerp: Slerp, swing: dict[str, Any], impact_s: float,
                axis: np.ndarray, orientation_ok: bool = True) -> dict[str, Any]:
    """Camera <-> phone alignment for one swing.

    Always returns the timing (hand, contact frame, frame times). "ok" says whether the
    fit is trusted, and "reason" says why not.
    """
    P = to_array(swing)
    hand = swing_hand(swing, P)
    j = ARM[hand]
    t = frame_times(swing)
    cf = contact_frame(swing, P, hand)
    filled = filled_flags(swing)
    cam = _unit(P[:, j["wr"]] - P[:, j["el"]])
    seen = np.isfinite(cam).all(axis=1)
    if filled is not None:
        seen &= ~filled[:, j["el"]] & ~filled[:, j["wr"]]
    rel = t - t[cf]
    out: dict[str, Any] = {"ok": False, "reason": None, "hand": hand, "contact_frame": cf, "t": t, "rel": rel,
                           "seen": seen, "provenance_known": filled is not None, "filled": filled, "P": P,
                           "shift_s": 0.0, "R": None, "a": None, "err": None, "holdout": None,
                           "strap_offset_deg": None, "warnings": []}

    def fit(shift_s: float, mask: np.ndarray) -> Optional[tuple[Rotation, np.ndarray, np.ndarray, np.ndarray]]:
        ts = impact_s + rel + shift_s
        m = mask & (ts >= rec.t[0]) & (ts <= rec.t[-1])
        if m.sum() < MIN_VISIBLE:
            return None
        R, a, err = fit_alignment(cam[m], slerp(ts[m]), axis)
        return R, a, err, m

    if seen.sum() < MIN_VISIBLE:
        out["reason"] = f"only {int(seen.sum())} frames show the hitting forearm (need {MIN_VISIBLE})"
        return out
    sv = np.linalg.svd(cam[seen], compute_uv=False)
    if sv[1] / sv[0] < MIN_SPREAD:
        out["reason"] = "the forearm barely changes direction on the visible frames, so the alignment is undetermined"
        return out

    scores: dict[float, float] = {}

    def score(ms: float) -> float:
        if ms not in scores:
            r = fit(ms / 1000, seen)
            scores[ms] = np.inf if r is None else float(np.median(r[2]))
        return scores[ms]

    best = min(np.arange(-SHIFT_MAX_MS, SHIFT_MAX_MS + 1e-9, SHIFT_STEP_MS), key=score)
    best = min(np.arange(best - SHIFT_STEP_MS + 1, best + SHIFT_STEP_MS), key=score)
    r = fit(best / 1000, seen)
    if r is None:
        out["reason"] = "the visible frames fall outside the sensor recording"
        return out
    R, a, err, m = r
    strap = float(min(_angle_deg(a, axis), _angle_deg(a, -axis)))
    out.update(shift_s=float(best) / 1000, R=R, a=a, err=err, strap_offset_deg=strap)
    if abs(best) >= SHIFT_MAX_MS - 1:
        out["warnings"].append(f"camera-sensor time shift {best:+.0f} ms is at the search edge")

    # Holdout: hide the visible frames nearest contact (like an occlusion there), refit, test on them.
    idx = np.flatnonzero(m)
    n_hold = int(round(HOLDOUT_FRACTION * idx.size))
    hold = np.zeros_like(m)
    hold[idx[np.argsort(np.abs(rel[idx]))[:n_hold]]] = True
    rh = fit(out["shift_s"], m & ~hold) if n_hold >= 3 else None
    if rh is not None:
        Rh, ah, _, _ = rh
        ts = impact_s + rel[hold] + out["shift_s"]
        out["holdout"] = _angle_deg(cam[hold], Rh.apply(slerp(ts).apply(ah)))

    if not orientation_ok:
        out["reason"] = "the phone's orientation doesn't match its gyro"
    elif np.median(err) > AGREE_OK_DEG:
        out["reason"] = f"camera and phone disagree by {np.median(err):.0f} deg (median) on the visible frames"
    elif strap > STRAP_MAX_DEG:
        out["reason"] = (f"the fitted strap axis is {strap:.0f} deg off the phone's forearm axis: "
                         "check how the phone was strapped (--axis)")
    else:
        out["ok"] = True
    return out


def _elbow_on_circle(sh: np.ndarray, wr: np.ndarray, l_up: float, l_fore: float,
                     target: np.ndarray) -> tuple[np.ndarray, bool]:
    """Elbow with |elbow - shoulder| = l_up and |elbow - wrist| = l_fore, closest to target.

    Falls back to target (only the forearm length kept) when the shoulder is missing or
    the wrist is out of the arm's reach; the bool says whether both lengths were kept.
    """
    if not (np.isfinite(sh).all() and np.isfinite(l_up)):
        return target, False
    v = wr - sh
    d = float(np.linalg.norm(v))
    if d < 1e-9 or d > l_up + l_fore or d < abs(l_up - l_fore):
        return target, False
    n = v / d
    along = (l_up ** 2 - l_fore ** 2 + d ** 2) / (2 * d)
    radius = float(np.sqrt(max(l_up ** 2 - along ** 2, 0.0)))
    centre = sh + along * n
    p = target - centre
    p = p - (p @ n) * n
    if np.linalg.norm(p) < 1e-9:
        p = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    return centre + radius * p / np.linalg.norm(p), True


def _median_length(P: np.ndarray, a: int, b: int, mask: np.ndarray) -> float:
    lengths = np.linalg.norm(P[mask, a] - P[mask, b], axis=1)
    lengths = lengths[np.isfinite(lengths)]
    return float(np.median(lengths)) if lengths.size else float("nan")


def fill_swing(swing: dict[str, Any], al: dict[str, Any], slerp: Slerp, impact_s: float,
               mock: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """(copy of swing with the occluded forearm rebuilt from the phone, fill report).

    The swing comes back unchanged (a copy) whenever nothing is filled; the report's
    "reason" says why.
    """
    info: dict[str, Any] = {**ESTIMATE, "applied": False, "reason": None, "frames": [], "joints": [],
                            "visible_frames": int(al["seen"].sum()),
                            "agreement_deg": None if al["err"] is None else _summary(al["err"]),
                            "holdout_deg": None if al["holdout"] is None else _summary(al["holdout"]),
                            "time_shift_ms": round(al["shift_s"] * 1000, 1),
                            "strap_axis_offset_deg": None if al["strap_offset_deg"] is None
                            else round(al["strap_offset_deg"], 1)}
    filled = al["filled"]
    if filled is None:
        info["reason"] = "this swing has no filled flags (older file: provenance unknown), so nothing to fill"
        return dict(swing), info
    if not al["ok"]:
        info["reason"] = f"alignment not trusted: {al['reason']}"
        return dict(swing), info
    j = ARM[al["hand"]]
    ts_all = impact_s + al["rel"] + al["shift_s"]
    need = (filled[:, j["el"]] | filled[:, j["wr"]]) & (ts_all >= slerp.times[0]) & (ts_all <= slerp.times[-1])
    if not need.any():
        info["reason"] = "no filled hitting-arm frames inside the sensor recording"
        return dict(swing), info

    P = al["P"].copy()
    seen = al["seen"]
    l_fore = _median_length(P, j["wr"], j["el"], seen)
    up_seen = np.isfinite(P[:, j["sh"]]).all(axis=1) & ~filled[:, j["sh"]] & ~filled[:, j["el"]]
    l_up = _median_length(P, j["el"], j["sh"], up_seen)
    frames = np.flatnonzero(need)
    dirs = al["R"].apply(slerp(ts_all[frames]).apply(al["a"]))
    moved, joints, kept_both = [], set(), True
    for i, d in zip(frames, dirs):
        if filled[i, j["wr"]] or not np.isfinite(P[i, j["wr"]]).all():
            # Anchor at the elbow (seen, or the pipeline's own estimate); the hand moves with the wrist.
            new = P[i, j["el"]] + l_fore * d
            delta = new - P[i, j["wr"]]
            P[i, j["wr"]] = new
            for key in HAND_KEYS:
                if np.isfinite(P[i, j[key]]).all():
                    P[i, j[key]] += delta
            moved.append(float(np.linalg.norm(delta)))
            joints.update(["wrist", "hand"])
        else:
            new, both = _elbow_on_circle(P[i, j["sh"]], P[i, j["wr"]], l_up, l_fore, P[i, j["wr"]] - l_fore * d)
            kept_both &= both
            moved.append(float(np.linalg.norm(new - P[i, j["el"]])))
            P[i, j["el"]] = new
            joints.add("elbow")
    out = from_array(swing, P)
    order = [k for k in ("elbow", "wrist", "hand") if k in joints]
    info.update(applied=True, frames=frames.tolist(), joints=order,
                forearm_m=round(l_fore, 3), upper_arm_m=None if not np.isfinite(l_up) else round(l_up, 3),
                moved_m={"median": round(float(np.median(moved)), 3), "max": round(float(np.max(moved)), 3)})
    if not kept_both:
        info["note"] = "on some elbow frames the shoulder was missing or out of reach: only the forearm length was kept"
    out["metadata"] = {**(out.get("metadata") or {}), "wristSensorFill": {
        **ESTIMATE, "source": "forearm phone orientation, aligned to the camera on the visible frames",
        "frames": info["frames"], "joints": order, "agreementDeg": info["agreement_deg"]["median"],
        "mock": bool(mock)}}
    return out, info


def racket_speed(rec: Recording, slerp: Slerp, impact_s: float, axis: np.ndarray, lever_m: float = LEVER_M,
                 swing: Optional[dict[str, Any]] = None, al: Optional[dict[str, Any]] = None,
                 fill_frames: Optional[list[int]] = None) -> dict[str, Any]:
    """ESTIMATED racket-head speed at contact (see the module docstring).

    Without a camera swing, value is None. rotationMs (the gyro x lever part) is still given.
    """
    ts = impact_s + np.linspace(*SPEED_WINDOW_MS, 5) / 1000
    w = np.column_stack([np.interp(ts, rec.t, rec.gyro[:, k]) for k in range(3)])  # rad/s, phone axes
    aligned = al is not None and al["ok"]
    a = al["a"] if aligned else axis / np.linalg.norm(axis)
    w_perp = w - (w @ a)[:, None] * a   # spin about the forearm itself doesn't move a head on its axis
    rot_ms = float(np.linalg.norm(w_perp, axis=1).mean() * lever_m)
    out: dict[str, Any] = {
        "value": None, "unit": "m/s", **ESTIMATE, "source": "wrist sensor", "method": None,
        "gyroDps": round(float(np.degrees(np.linalg.norm(w_perp, axis=1).mean()))), "leverM": lever_m,
        "rotationMs": round(rot_ms, 1), "wristSpeedMs": None, "windowMs": list(SPEED_WINDOW_MS),
        "clamped": False, "rawValue": None, "reason": None, "mock": rec.mock,
    }
    if swing is None or al is None:
        out["reason"] = "no camera swing: the wrist's own speed comes from the camera"
        return out
    wr = to_array(swing)[:, ARM[al["hand"]]["wr"]]
    t = al["t"]
    ok = np.isfinite(wr).all(axis=1)
    if ok.sum() < 3:
        out["reason"] = "the camera lost the hitting wrist"
        return out
    v = np.gradient(wr[ok], t[ok], axis=0)
    cam_t = t[al["contact_frame"]] + (ts - impact_s) - al["shift_s"]  # camera times of the same instants
    v_wr = np.column_stack([np.interp(cam_t, t[ok], v[:, k]) for k in range(3)])
    if aligned:
        rots = slerp(np.clip(ts, rec.t[0], rec.t[-1]))
        tangential = al["R"].apply(np.cross(rots.apply(w), lever_m * rots.apply(a)))
        raw = float(np.linalg.norm(v_wr + tangential, axis=1).mean())
        method = "camera wrist velocity + gyro x lever, added as vectors"
    else:
        raw = float(np.linalg.norm(v_wr, axis=1).mean()) + rot_ms
        method = "camera wrist speed + gyro x lever, added as if parallel (camera alignment not trusted)"
    lo, hi = RACKET_SPEED_RANGE_MS
    near = np.flatnonzero((t >= cam_t.min() - 0.02) & (t <= cam_t.max() + 0.02))
    out.update(value=round(min(max(raw, lo), hi), 1), rawValue=round(raw, 1), clamped=not lo <= raw <= hi,
               method=method, wristSpeedMs=round(float(np.linalg.norm(v_wr, axis=1).mean()), 2),
               wristFromSensorFill=bool(set(near.tolist()) & set(fill_frames or [])))
    return out


def attach_racket_speed(swing: dict[str, Any], wrist_metrics: dict[str, Any]) -> dict[str, Any]:
    """A copy of swing with the optional field racketSpeedSensor when the wrist file has one.

    The field has estimate_racket_speed()'s shape (value, unit, estimate, label, method, ...),
    so physics.compare can use it in place of the pose estimate. A swing without one comes
    back unchanged.
    """
    entry = (wrist_metrics.get("swings") or {}).get(str(swing.get("id"))) or {}
    rs = entry.get("racket_speed_sensor")
    if not isinstance(rs, dict) or rs.get("value") is None:
        return dict(swing)
    return {**swing, "racketSpeedSensor": rs}
