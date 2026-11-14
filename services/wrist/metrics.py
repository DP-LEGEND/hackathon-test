"""Per-swing wrist numbers from the forearm phone. Owner: Henoch.

Code measures, Claude explains: these are the only wrist-roll numbers the coach may quote.
Contact = the sensor's own impact spike (sync.py), so sync error doesn't move any number.

Per swing, in the window -150 ms .. +100 ms around contact:
- roll_change_deg: forearm ROLL (rotation about the forearm's long axis) over the
  window, from the orientation quaternions. It's the twist of the phone's rotation
  between the window's ends, about the forearm axis (swing-twist decomposition), so the
  big swing about the elbow and shoulder doesn't leak in. Signed (+ = right-hand turn
  about the axis); the rolled_wrist fault uses its size.
- roll_change_gyro_deg: the same from integrating the gyro about the axis, a cross-check.
- peak_roll_rate_dps: the gyro about the forearm axis at its fastest (signed).
- peak_angular_speed_dps: the forearm's fastest total turn rate (|gyro|), as seen by the
  phone on the wrist strap. Not used by the fault; context for the coach.

The forearm axis is the PHONE axis lying along the forearm: "y" when the phone is strapped
with its long edge along the forearm (the README's setup). axis_hint() checks it: during
a swing the pull toward the elbow runs along the forearm, so that axis should carry the
most acceleration.

Quaternion convention: Sensor Logger doesn't document whether its quaternion maps phone
to world or world to phone. gyro_convention() picks the one whose frame-to-frame
rotation matches the gyro, and reports the mismatch; if neither matches, swings are
marked unusable.

ESTIMATES added per swing (each block says "label": "ESTIMATE"):
- tempo (tempo.py): backswing start, top of backswing, follow-through end, from |gyro|.
- impact (impact.py): spike height and width at impact -> clean / mishit, relative to the
  session's other impacts.
- racket_speed_sensor and occlusion_fill (fuse.py): need the camera's pipeline swing JSON.
  Racket speed = camera wrist velocity + gyro x lever. The fill rebuilds the camera's
  occluded hitting forearm from the phone and reports the camera/phone agreement error.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
from scipy.integrate import trapezoid
from scipy.spatial.transform import Rotation, Slerp

from physics.skeleton import ARM, to_array
from wrist.fuse import LEVER_M, align_swing, fill_swing, racket_speed
from wrist.impact import clip_levels, impact_shape, judge
from wrist.load import Recording
from wrist.sync import spike_signal
from wrist.tempo import series_grid_ms, speed_dps, speed_series, tempo

WINDOW_MS = (-150, 100)
SERIES_MS = (-300, 200)     # the exported graph spans a bit more than the window
SERIES_STEP_MS = 10
GYRO_MATCH_OK = 0.3         # median |orientation rate - gyro| / median |gyro| must be below this
MOVING_RAD_S = 1.0          # judge the match only where the arm is turning


def axis_vector(name: str) -> np.ndarray:
    """"x", "y", "z", optionally signed ("-y"), as a unit vector in phone axes."""
    s = name.strip().lower()
    sign = -1.0 if s.startswith("-") else 1.0
    s = s.lstrip("+-")
    if s not in ("x", "y", "z"):
        raise ValueError(f"forearm axis must be x, y or z (optionally signed), got {name!r}")
    v = np.zeros(3)
    v["xyz".index(s)] = sign
    return v


def gyro_convention(rec: Recording) -> dict[str, Any]:
    """Which way the quaternions point, judged against the gyro."""
    R = Rotation.from_quat(rec.quat)
    dt = np.diff(rec.t)[:, None]
    w_gyro = (rec.gyro[:-1] + rec.gyro[1:]) / 2
    speed = np.linalg.norm(w_gyro, axis=1)
    moving = speed > MOVING_RAD_S
    if moving.sum() < 10:
        moving = np.ones_like(moving)
    mismatch = {}
    for name, Rb in (("body_to_world", R), ("world_to_body", R.inv())):
        w = (Rb[:-1].inv() * Rb[1:]).as_rotvec() / dt
        err = np.linalg.norm(w - w_gyro, axis=1)
        mismatch[name] = float(np.median(err[moving]) / max(np.median(speed[moving]), 1e-9))
    best = min(mismatch, key=mismatch.get)
    return {"convention": best, "mismatch": round(mismatch[best], 3),
            "other_mismatch": round(mismatch[next(k for k in mismatch if k != best)], 3),
            "ok": mismatch[best] < GYRO_MATCH_OK}


def body_rotations(rec: Recording, convention: str) -> Rotation:
    """Rotations that map phone axes to world axes."""
    R = Rotation.from_quat(rec.quat)
    return R if convention == "body_to_world" else R.inv()


def twist_deg(rel: Rotation, axis: np.ndarray) -> np.ndarray:
    """Signed angle (deg, -180..180] of each rotation's twist about `axis` (phone axes)."""
    q = np.atleast_2d(rel.as_quat())
    ang = 2 * np.arctan2(q[:, :3] @ axis, q[:, 3])
    return np.degrees((ang + np.pi) % (2 * np.pi) - np.pi)


def axis_hint(rec: Recording, impacts_s: list[float], axis: str) -> dict[str, Any]:
    """Which phone axis carries the most acceleration through contact (should be the forearm axis)."""
    lo, hi = WINDOW_MS[0] / 1000, WINDOW_MS[1] / 1000
    total = np.zeros(3)
    for c in impacts_s:
        mask = (rec.t >= c + lo) & (rec.t <= c + hi)
        if mask.any():
            total += np.abs(rec.acc[mask]).mean(axis=0)
    if not total.any():
        return {"chosen": axis, "dominant_accel_axis": None, "agrees": None}
    dominant = "xyz"[int(np.argmax(total))]
    return {"chosen": axis, "dominant_accel_axis": dominant, "agrees": dominant == axis.strip().lstrip("+-").lower()}


def swing_metrics(rec: Recording, slerp: Slerp, impact_s: float, axis: np.ndarray) -> Optional[dict[str, Any]]:
    """The wrist numbers for one swing, or None if the window runs off the recording."""
    t0, t1 = impact_s + WINDOW_MS[0] / 1000, impact_s + WINDOW_MS[1] / 1000
    if t0 < rec.t[0] or t1 > rec.t[-1]:
        return None
    ends = slerp([t0, t1])
    roll = float(twist_deg(ends[0].inv() * ends[1], axis)[0])

    rate_all = rec.gyro @ axis  # rad/s about the forearm
    fine = np.linspace(t0, t1, 251)
    roll_gyro = float(np.degrees(trapezoid(np.interp(fine, rec.t, rate_all), fine)))
    mask = (rec.t >= t0) & (rec.t <= t1)
    rate = np.degrees(rate_all[mask])
    i = int(np.argmax(np.abs(rate)))
    speed = float(np.degrees(np.linalg.norm(rec.gyro[mask], axis=1).max()))
    return {
        "impact_s": round(impact_s, 3),
        "roll_change_deg": round(roll, 1),
        "roll_change_abs_deg": round(abs(roll), 1),
        "roll_change_gyro_deg": round(roll_gyro, 1),
        "peak_roll_rate_dps": round(float(rate[i])),
        "peak_roll_rate_abs_dps": round(abs(float(rate[i]))),
        "peak_angular_speed_dps": round(speed),
        "window_ms": list(WINDOW_MS),
    }


def roll_series(rec: Recording, slerp: Slerp, impact_s: float, axis: np.ndarray) -> dict[str, Any]:
    """Forearm roll every 10 ms from -300 to +200 ms, zeroed at the window start (-150 ms).

    So the value at +100 ms is exactly roll_change_deg: the graph ends the window on the
    number the coach quotes.
    """
    t_ms = np.arange(SERIES_MS[0], SERIES_MS[1] + 1, SERIES_STEP_MS)
    times = impact_s + t_ms / 1000
    keep = (times >= rec.t[0]) & (times <= rec.t[-1])
    ref = slerp(impact_s + WINDOW_MS[0] / 1000)
    roll = twist_deg(ref.inv() * slerp(times[keep]), axis)
    # + 0.0 turns -0.0 into 0.0 for the graph.
    return {"t_ms": t_ms[keep].astype(int).tolist(), "roll_deg": [round(float(v), 1) + 0.0 for v in roll]}


def wrist_metrics(rec: Recording, sync: dict[str, Any], axis: str = "y",
                  swings: Optional[dict[str, dict[str, Any]]] = None,
                  lever_m: float = LEVER_M) -> tuple[dict[str, Any], dict[str, Any]]:
    """(metrics JSON keyed by swing, small series JSON keyed by swing). See wrist_report."""
    metrics, series, _ = wrist_report(rec, sync, axis, swings, lever_m)
    return metrics, series


def _fill_points(al: dict[str, Any], info: dict[str, Any], filled: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The rebuilt joints on the filled frames, small enough for the graph file."""
    if not info.get("applied"):
        return None
    P, j, frames = to_array(filled), ARM[al["hand"]], info["frames"]
    t_ms = [round(float(al["rel"][i] + al["shift_s"]) * 1000) for i in frames]
    pts = {name: [[round(float(v), 4) for v in P[i, j[key]]] for i in frames]
           for name, key in (("elbow", "el"), ("wrist", "wr"))}
    return {"estimate": True, "label": "ESTIMATE", "frames": frames, "t_ms": t_ms, **pts,
            "agreement_deg": info["agreement_deg"]["median"]}


def wrist_report(rec: Recording, sync: dict[str, Any], axis: str = "y",
                 swings: Optional[dict[str, dict[str, Any]]] = None,
                 lever_m: float = LEVER_M) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    """(metrics JSON keyed by swing, small series JSON keyed by swing, filled camera swings).

    Every swing the video has gets an entry. "usable": false (with skip_reason) when its
    impact isn't trusted (alignment off, unpaired) or the orientation fails the gyro check;
    the coach then skips rolled_wrist for it instead of guessing.

    swings: the camera's pipeline swing JSONs by id. Without them racket speed has no value
    and occlusion_fill isn't applied (both say why). Filled swings come back only for swings
    whose fill was applied.
    """
    conv = gyro_convention(rec)
    slerp = Slerp(rec.t, body_rotations(rec, conv["convention"]))
    ax = axis_vector(axis)
    alignment = sync["alignment"]
    hp, clip, speed = spike_signal(rec), clip_levels(rec), speed_dps(rec)
    out: dict[str, Any] = {}
    series: dict[str, Any] = {}
    shapes: dict[str, Optional[dict[str, Any]]] = {}
    filled_swings: dict[str, dict[str, Any]] = {}
    for p in alignment["pairs"]:
        sid = p["swing"]
        base = {"usable": False, "mock": rec.mock, "align_error_ms": p["error_ms"]}
        if not p["ok"]:
            out[sid] = {**base, "skip_reason": (
                f"alignment error {p['error_ms']:.0f} ms > {alignment['tolerance_ms']:.0f} ms")}
            continue
        impact = p["impact_s"]
        m = swing_metrics(rec, slerp, impact, ax)
        if m is None:
            out[sid] = {**base, "skip_reason": "the window runs off the recording"}
            continue
        reason = None if conv["ok"] else (
            f"orientation doesn't match the gyro (mismatch {conv['mismatch']:.2f} >= {GYRO_MATCH_OK})")

        tempo_block = tempo(rec, impact, speed)
        shapes[sid] = impact_shape(rec, hp, impact, clip)
        camera = (swings or {}).get(sid)
        fill_pts = None
        if camera is None:
            racket = racket_speed(rec, slerp, impact, ax, lever_m)
            fill_info = {"estimate": True, "label": "ESTIMATE", "applied": False,
                         "reason": "no camera swing with this id" if swings else "no camera swings given (--swings)"}
        else:
            al = align_swing(rec, slerp, camera, impact, ax, orientation_ok=conv["ok"])
            filled, fill_info = fill_swing(camera, al, slerp, impact, rec.mock)
            racket = racket_speed(rec, slerp, impact, ax, lever_m, filled, al, fill_info["frames"])
            fill_info["warnings"] = al["warnings"]
            fill_pts = _fill_points(al, fill_info, filled)
            if fill_info["applied"]:
                filled_swings[sid] = filled

        out[sid] = {**base, **m, "usable": conv["ok"], "skip_reason": reason, "tempo": tempo_block,
                    "racket_speed_sensor": racket, "occlusion_fill": fill_info}
        series[sid] = {**roll_series(rec, slerp, impact, ax), "roll_change_deg": m["roll_change_deg"],
                       "usable": conv["ok"],
                       "tempo": {k: tempo_block[k] for k in ("estimate", "label", "backswing_start_ms",
                                                              "forward_start_ms", "contact_ms",
                                                              "follow_through_end_ms")},
                       "angular_speed_dps": speed_series(rec, impact, speed),
                       "racket_speed_sensor": {k: racket[k] for k in ("value", "unit", "estimate", "label")},
                       "forearm_fill": fill_pts}
    for sid, verdict in judge(shapes, rec.rate_hz).items():
        out[sid]["impact"] = verdict
        series[sid]["impact"] = {k: verdict[k] for k in ("estimate", "label", "peak_g", "width_ms",
                                                         "quality", "score")}
    for s in alignment["unpaired_swings"]:
        out[s] = {"usable": False, "mock": rec.mock, "align_error_ms": None,
                  "skip_reason": "no impact paired with this swing"}

    impacts = [p["impact_s"] for p in alignment["pairs"] if p["ok"]]
    hint = axis_hint(rec, impacts, axis)
    warnings = list(sync.get("warnings", []))
    if not conv["ok"]:
        warnings.append("orientation doesn't match the gyro: roll numbers are not trusted")
    if hint["agrees"] is False:
        warnings.append(f"forearm axis is {axis} but the {hint['dominant_accel_axis']} axis carries the most "
                        "acceleration through contact: check how the phone was strapped (--axis)")
    if swings and not set(swings) & set(out):
        warnings.append(f"none of the {len(swings)} camera swings match a sensor swing id")
    sync_out = {k: v for k, v in sync.items() if k not in ("impacts", "warnings")}
    sync_out["rejected_spikes"] = sync_out.get("rejected_spikes", [])[:20]
    metrics = {
        "mock": rec.mock,
        "source": rec.source,
        "sensor": {"rate_hz": rec.rate_hz, "orientation": rec.orientation, "forearm_axis": axis,
                   "quaternion": conv, "axis_hint": hint},
        "window_ms": list(WINDOW_MS),
        "estimates": {"label": "ESTIMATE", "lever_m": lever_m, "camera_swings": len(swings or {}),
                      "note": "tempo, impact, racket_speed_sensor and occlusion_fill are ESTIMATES: "
                              "show them labelled ESTIMATE"},
        "warnings": warnings,
        "sync": sync_out,
        "swings": out,
    }
    series_json = {
        "mock": rec.mock,
        "about": ("Forearm roll (deg) from the wrist sensor, every 10 ms. t_ms is ms from contact "
                  "(the sensor's impact spike); roll_deg is zero at the window start (-150 ms), so "
                  "its value at +100 ms is roll_change_deg, the number the coach quotes. "
                  "angular_speed_dps is the forearm's turn rate on angular_speed_t_ms (ms from contact); "
                  "tempo marks its events. tempo, impact, racket_speed_sensor and forearm_fill are "
                  "ESTIMATES: label them so."),
        "window_ms": list(WINDOW_MS),
        "forearm_axis": axis,
        "angular_speed_t_ms": series_grid_ms(),
        "swings": series,
    }
    return metrics, series_json, filled_swings
