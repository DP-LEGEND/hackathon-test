"""Check the PREDICTED ball against the real ball in the clip. Owner: aryan.

The demo's ball paths are PREDICTED from the body alone (racket speed from the wrist, aim from
the wrist, ASSUMED launch angle and drive spot). The clips were filmed with a real ball, so
this measures where that ball really went and prints the error. Code measures; nothing here
changes the model.

Steps, in plain words:
1. Camera. Court landmarks (tin, service line, out line, front corners, short line) are
   hand-picked once per clip on a median of frames, which removes the player
   (validation/court_<clip>.json). From those we solve the focal length and the camera's
   position and direction (principal point at the image centre, no lens distortion) and report
   the landmark reprojection error.
2. Ball. Frame differencing against a background median: small blobs much darker than the
   background (a black ball on a white wall or light floor), with a size and shape filter,
   inside the image of the court between the front wall and the racket, away from the player.
   Blobs are linked into tracks with a constant-velocity gate; the longest moving track after
   contact is the ball. The ball's pixel at contact comes from the incoming ball's track,
   extrapolated to the contact frame. If detection fails, hand-labelled points
   (validation/labels_<swing>.json) are used instead, and the result says so
   (method "hand-labelled").
3. 3D. One flight from the contact point (on the camera ray through the contact pixel, depth
   fitted) to the front wall, then a free rebound, with gravity and drag from ball.py.
   Least squares on the pixel positions with known frame times (frame / fps_real). Points after
   the rebound reaches a side wall or the floor are dropped.
4. Compare with the PREDICTED path: direction (degrees), front-wall height and position
   (metres), speed, launch angle, time to the wall.

Run from services/ (clips in data/raw/, git-ignored):
    python -m physics.validate_ball            # every swing in validation/swings.json
    python -m physics.validate_ball --swing 7178110a0b06-swing-0027
Writes validation/results/<swing>.json and a debug image in data/processed/validation/
(git-ignored: it shows the player).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from physics.ball import (AIR_DENSITY, BALL_DIAMETER_M, BALL_MASS_KG, COURT_WIDTH_M, DRAG_COEFF,
                          FRONT_OUT_M, GRAVITY, launch_direction)

SERVICES = Path(__file__).resolve().parents[1]
REPO = SERVICES.parent
VALIDATION_DIR = Path(__file__).resolve().parent / "validation"
RESULTS_DIR = VALIDATION_DIR / "results"
SPOTS_DIR = VALIDATION_DIR / "spots"   # where the player hit from, MEASURED (physics/court_spot.py)
DEBUG_DIR = REPO / "data" / "processed" / "validation"
CLIP_DIR = REPO / "data" / "raw"

K_DRAG = 0.5 * AIR_DENSITY * DRAG_COEFF * math.pi * (BALL_DIAMETER_M / 2) ** 2 / BALL_MASS_KG
FIT_DT_S = 0.004          # flight step for the fit (RK4; positions between steps are interpolated)
COURT_HEIGHT_M = FRONT_OUT_M + 0.6

# ---- Ball detection ----
DARK_DIFF = 40            # grey levels darker than the background median
DARK_MAX = 130            # and darker than this grey level (the ball is near-black)
BALL_AREA_PX = (4, 300)   # blob area; larger dark blobs are the player or the racket
MAX_ASPECT = 4.0          # motion blur stretches the ball, but not into a line
PLAYER_MARGIN_PX = 12     # ignore blobs this close to a large dark blob
BG_FRAMES = (-90, 150, 6)  # background median: file frames contact-90 .. contact+150, every 6th
INCOMING_FRAMES = 15      # look for the incoming ball this many file frames before contact
OUTGOING_FRAMES = 90      # and for the hit ball this many after
MAX_MISS = 4              # a track may skip this many frames (occlusion)
MIN_TRACK = 6             # fewer tracked points than this: detection failed
MIN_SPEED_PX = 2.0        # a track moving less than this per frame is a mark on the wall
STILL_RADIUS_PX = 3.0     # a candidate seen within this radius ...
STILL_FRAMES = 8          # ... in this many frames is a still mark, not the ball
OUTLIER_PX = 15.0         # a tracked point this far off a smooth curve through the track is dropped
MIN_INCOMING_SPEED_PX = 1.0  # the incoming ball comes mostly towards the camera, so it moves slowly
INCOMING_GAP = 6          # the incoming ball's track may end this many frames before contact
MAX_AREA_RATIO = 3.0      # a ball's blob keeps its size along a track (within this ratio)
FEET = (29, 30, 31, 32)   # MediaPipe heels and toes: on the floor at contact
MIN_FOOT_VIS = 0.5
ROI_BEHIND_FEET_M = 1.0   # the region in front of the racket: front wall to 1 m behind the feet

# ---- Fit ----
MAX_AFTER_WALL_S = 0.30   # use at most this much of the rebound
FIT_STARTS = [(az, el) for az in (-15.0, 0.0, 15.0) for el in (0.0, 12.0)]
FIT_REFINE = 3            # optimise from the best few starting points
# The contact pixel fixes a camera ray; how far along it the ball was trades off against speed
# in the pixels alone. The player's feet (pose, on the floor through the calibrated camera)
# anchor it: the ball is struck within about half a metre of the feet along the court.
CONTACT_Z_SIGMA_M = 0.5
PRIOR_PX = 2.5            # one sd of the feet prior costs as much as a 2.5 px pixel error


def _robust_cost(r: np.ndarray, scale: float = 2.0) -> float:
    z = (r / scale) ** 2
    return float(np.sum(2 * (np.sqrt(1 + z) - 1)))


# ---------------------------------------------------------------- camera

@dataclass
class Camera:
    focal: float
    cx: float
    cy: float
    R: np.ndarray       # world -> camera rotation
    t: np.ndarray       # world -> camera translation (OpenCV convention)

    @property
    def center(self) -> np.ndarray:
        return -self.R.T @ self.t

    def project(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, float))
        c = X @ self.R.T + self.t
        return np.column_stack([self.focal * c[:, 0] / c[:, 2] + self.cx,
                                self.focal * c[:, 1] / c[:, 2] + self.cy])

    def depth(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, float))
        return (X @ self.R.T + self.t)[:, 2]

    def ray(self, px) -> np.ndarray:
        """Unit direction (world) of the ray through pixel px."""
        d = np.array([(px[0] - self.cx) / self.focal, (px[1] - self.cy) / self.focal, 1.0])
        d = self.R.T @ d
        return d / np.linalg.norm(d)


def calibrate(world: np.ndarray, pixels: np.ndarray, size: tuple[int, int]) -> tuple[Camera, float]:
    """Camera from >= 6 non-coplanar court landmarks: (camera, reprojection RMS in px)."""
    world, pixels = np.asarray(world, float), np.asarray(pixels, float)
    if len(world) < 6:
        raise ValueError(f"need at least 6 court landmarks, got {len(world)}")
    w, h = size
    cx, cy = w / 2.0, h / 2.0
    best = None
    for f in np.linspace(0.5 * w, 2.5 * w, 41):
        K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
        ok, rvec, tvec = cv2.solvePnP(world, pixels, K, None, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            continue
        proj, _ = cv2.projectPoints(world, rvec, tvec, K, None)
        err = float(np.sqrt(np.mean(np.sum((proj[:, 0] - pixels) ** 2, axis=1))))
        if best is None or err < best[0]:
            best = (err, f, rvec.ravel(), tvec.ravel())
    if best is None:
        raise ValueError("could not solve the camera from the court landmarks")

    def residuals(p):
        f, rvec, tvec = p[0], p[1:4], p[4:7]
        K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
        proj, _ = cv2.projectPoints(world, rvec, tvec, K, None)
        return (proj[:, 0] - pixels).ravel()

    sol = least_squares(residuals, np.concatenate([[best[1]], best[2], best[3]]), method="lm")
    f, rvec, tvec = sol.x[0], sol.x[1:4], sol.x[4:7]
    cam = Camera(float(f), cx, cy, cv2.Rodrigues(rvec)[0], tvec.astype(float))
    rms = float(np.sqrt(np.mean(sol.fun.reshape(-1, 2) ** 2) * 2))
    return cam, rms


def load_court(path: Path) -> tuple[np.ndarray, np.ndarray, tuple[int, int], dict]:
    data = json.loads(Path(path).read_text())
    pts = data["points"]
    world = np.array([p["court"] for p in pts], float)
    pixels = np.array([p["px"] for p in pts], float)
    return world, pixels, tuple(data["frameSize"]), data


# ---------------------------------------------------------------- frames and detection

def read_frames(clip: Path, first: int, last: int) -> dict[int, np.ndarray]:
    """File frames first..last (inclusive) as grey images, read in order from one seek."""
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise FileNotFoundError(f"can't open {clip}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, first))
    out = {}
    for i in range(max(0, first), last + 1):
        ok, frame = cap.read()
        if not ok:
            break
        out[i] = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cap.release()
    return out


def read_colour(clip: Path, index: int) -> np.ndarray:
    cap = cv2.VideoCapture(str(clip))
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"can't read frame {index} of {clip}")
    return frame


def background(clip: Path, contact: int, n_frames: int) -> np.ndarray:
    lo, hi, step = BG_FRAMES
    picks = [i for i in range(contact + lo, contact + hi + 1, step) if 0 <= i < n_frames]
    cap = cv2.VideoCapture(str(clip))
    frames = []
    for i in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if ok:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    cap.release()
    if len(frames) < 5:
        raise ValueError("not enough frames for a background")
    return np.median(np.stack(frames), axis=0).astype(np.int16)


def detect(gray: np.ndarray, bg: np.ndarray, roi: np.ndarray | None = None) -> list[tuple[float, float, int]]:
    """Ball candidates in one frame: (u, v, area) of small blobs much darker than the background."""
    g = gray.astype(np.int16)
    mask = ((g < bg - DARK_DIFF) & (g < DARK_MAX)).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask)
    big = np.zeros_like(mask)
    for j in range(1, n):
        if stats[j][4] > BALL_AREA_PX[1]:
            big[lab == j] = 1
    if big.any():
        k = 2 * PLAYER_MARGIN_PX + 1
        big = cv2.dilate(big, np.ones((k, k), np.uint8))
    out = []
    for j in range(1, n):
        x, y, w, h, area = stats[j]
        if not BALL_AREA_PX[0] <= area <= BALL_AREA_PX[1]:
            continue
        if max(w, h) > MAX_ASPECT * max(1, min(w, h)) + 2:
            continue
        u, v = float(cent[j][0]), float(cent[j][1])
        iu, iv = int(round(u)), int(round(v))
        if big[iv, iu] or (roi is not None and not roi[iv, iu]):
            continue
        out.append((u, v, int(area)))
    return out


def link(dets: dict[int, list[tuple[float, float, int]]]) -> list[list[tuple[int, float, float, int]]]:
    """Constant-velocity tracks through per-frame candidates: [(frame, u, v, area), ...]."""
    active: list[list] = []
    done: list[list] = []
    for f in sorted(dets):
        cands = list(dets[f])
        used = set()
        for tr in sorted(active, key=len, reverse=True):
            fl, ul, vl, _ = tr[-1]
            gap = f - fl
            if len(tr) >= 2:
                f0, u0, v0, _ = tr[-2]
                du, dv = (ul - u0) / (fl - f0), (vl - v0) / (fl - f0)
                gate = 6.0 + 0.6 * math.hypot(du, dv) * gap
            else:
                du = dv = 0.0
                gate = 30.0 * gap
            pu, pv = ul + du * gap, vl + dv * gap
            best, best_d = None, gate
            for k, (u, v, a) in enumerate(cands):
                d = math.hypot(u - pu, v - pv)
                if k not in used and d <= best_d:
                    best, best_d = k, d
            if best is not None:
                used.add(best)
                tr.append((f, *cands[best]))
        for k, c in enumerate(cands):
            if k not in used:
                active.append([(f, *c)])
        still = []
        for tr in active:
            (done if f - tr[-1][0] > MAX_MISS else still).append(tr)
        active = still
    return done + active


def _speed(tr) -> float:
    """Net pixels per frame from the first point to the last (jitter on a still mark adds nothing)."""
    if len(tr) < 2:
        return 0.0
    (f0, u0, v0, _), (f1, u1, v1, _) = tr[0], tr[-1]
    return math.hypot(u1 - u0, v1 - v0) / max(1, f1 - f0)


def drop_still(dets: dict[int, list[tuple[float, float, int]]]) -> dict[int, list[tuple[float, float, int]]]:
    """Remove candidates that sit in the same spot in many frames: marks on the wall, a still shoe."""
    pts = [(f, u, v) for f, cs in dets.items() for u, v, _ in cs]
    if not pts:
        return dets
    arr = np.array(pts, float)
    out = {}
    for f, cs in dets.items():
        keep = []
        for c in cs:
            near = np.hypot(arr[:, 1] - c[0], arr[:, 2] - c[1]) <= STILL_RADIUS_PX
            if len(set(arr[near, 0].astype(int))) < STILL_FRAMES:
                keep.append(c)
        out[f] = keep
    return out


def smooth(tr: list, max_px: float = OUTLIER_PX) -> list:
    """Drop points far from a quadratic through the track (a stray blob linked at either end)."""
    tr = list(tr)
    for _ in range(3):
        if len(tr) < 5:
            return tr
        f = np.array([p[0] for p in tr], float)
        fu = np.polyval(np.polyfit(f, [p[1] for p in tr], 2), f)
        fv = np.polyval(np.polyfit(f, [p[2] for p in tr], 2), f)
        off = np.hypot(fu - [p[1] for p in tr], fv - [p[2] for p in tr])
        worst = int(np.argmax(off))
        if off[worst] <= max_px:
            return tr
        tr.pop(worst)
    return tr


def best_track(tracks, min_points: int = MIN_TRACK) -> list | None:
    moving = [smooth(t) for t in tracks if len(t) >= min_points and _speed(t) >= MIN_SPEED_PX]
    moving = [t for t in moving if len(t) >= min_points]
    return max(moving, key=len) if moving else None


def court_roi(cam: Camera, size: tuple[int, int], z_max: float) -> np.ndarray:
    """Image of the court box from the front wall to z_max (the region in front of the racket)."""
    w, h = size
    z_max = float(np.clip(z_max, 0.5, cam.center[2] - 0.3))
    corners = np.array([[x, y, z] for x in (-0.2, COURT_WIDTH_M + 0.2)
                        for y in (0.0, COURT_HEIGHT_M) for z in (0.0, z_max)])
    px = cam.project(corners)
    mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(np.round(px).astype(np.int32)), 1)
    return mask.astype(bool)


def on_floor(cam: Camera, px) -> np.ndarray | None:
    """Court point where the camera ray through px meets the floor (None if it never does)."""
    d = cam.ray(px)
    if d[1] >= -1e-6:
        return None
    return cam.center + (-cam.center[1] / d[1]) * d


def feet_on_floor(cam: Camera, feet_px) -> tuple[float, float]:
    """(x, z) of the player's feet: the mean of the heels and toes placed on the floor."""
    pts = [p for p in (on_floor(cam, px) for px in feet_px) if p is not None]
    if not pts:
        raise ValueError("none of the feet points is below the horizon")
    m = np.mean(pts, axis=0)
    return float(m[0]), float(m[2])


def pose_feet(clip: Path, contact: int) -> list[tuple[float, float]]:
    """Heel and toe pixels at the contact frame from the pipeline's pose model (MediaPipe)."""
    from pipeline.pose import extract_raw

    fps = cv2.VideoCapture(str(clip)).get(cv2.CAP_PROP_FPS)
    # Half-frame offsets so extract_raw's int(seconds * fps) lands on contact - 30 .. contact.
    raw = extract_raw(str(clip), (contact - 30 + 0.5) / fps, (contact + 1 + 0.5) / fps)
    if round(raw["t"][-1] * fps) != contact:
        raise ValueError(f"pose ended on frame {round(raw['t'][-1] * fps)}, not the contact frame {contact}")
    img, vis = raw["img"][-1], raw["vis"][-1]
    feet = [(float(img[j, 0]), float(img[j, 1])) for j in FEET
            if vis[j] >= MIN_FOOT_VIS and np.isfinite(img[j, :2]).all()]
    if len(feet) < 2:
        raise ValueError("the pose model didn't find the player's feet at contact")
    return feet


def _steady_size(tr) -> bool:
    areas = [p[3] for p in tr]
    return max(areas) <= MAX_AREA_RATIO * min(areas)


def contact_pixel(tracks, contact: int) -> tuple[float, float] | None:
    """The incoming ball's pixel at the contact frame: its track, extrapolated linearly.

    The ball merges with the racket a few frames before contact, so the track may end up to
    INCOMING_GAP frames early. A ball keeps its size; a hand or a shadow doesn't.
    """
    near = [t for t in tracks if len(t) >= 4 and 0 <= contact - t[-1][0] <= INCOMING_GAP
            and _speed(t) >= MIN_INCOMING_SPEED_PX and _steady_size(t)]
    if not near:
        return None
    tr = max(near, key=len)[-4:]
    f = np.array([p[0] for p in tr], float)
    u = np.polyfit(f, [p[1] for p in tr], 1)
    v = np.polyfit(f, [p[2] for p in tr], 1)
    return float(np.polyval(u, contact)), float(np.polyval(v, contact))


def track_ball(clip: Path, cam: Camera, size, contact: int, z_roi: float) -> dict:
    """Tracked pixels after contact plus the contact pixel; empty lists when detection fails.

    z_roi: the far edge (from the front wall) of the region in front of the racket.
    """
    n_frames = int(cv2.VideoCapture(str(clip)).get(cv2.CAP_PROP_FRAME_COUNT))
    bg = background(clip, contact, n_frames)
    frames = read_frames(clip, contact - INCOMING_FRAMES, contact + OUTGOING_FRAMES)
    before = {i: detect(g, bg) for i, g in frames.items() if i <= contact}
    cpx = contact_pixel(link(before), contact)
    roi = court_roi(cam, size, z_roi)
    after = drop_still({i: detect(g, bg, roi) for i, g in frames.items() if i > contact})
    tr = best_track(link(after))
    return {"contactPx": cpx, "points": [] if tr is None else [(f, u, v) for f, u, v, _ in tr]}


# ---------------------------------------------------------------- flight fit

def _accel(v):
    s = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (-K_DRAG * s * v[0], -GRAVITY - K_DRAG * s * v[1], -K_DRAG * s * v[2])


def _rk4(p, v, dt):
    a1 = _accel(v)
    v2 = tuple(v[i] + 0.5 * dt * a1[i] for i in range(3))
    a2 = _accel(v2)
    v3 = tuple(v[i] + 0.5 * dt * a2[i] for i in range(3))
    a3 = _accel(v3)
    v4 = tuple(v[i] + dt * a3[i] for i in range(3))
    a4 = _accel(v4)
    p1 = tuple(p[i] + dt / 6 * (v[i] + 2 * v2[i] + 2 * v3[i] + v4[i]) for i in range(3))
    vn = tuple(v[i] + dt / 6 * (a1[i] + 2 * a2[i] + 2 * a3[i] + a4[i]) for i in range(3))
    return p1, vn


def flight(p0, v0, v_rebound, t_end: float, dt: float = FIT_DT_S) -> dict:
    """Contact -> front wall (z = 0) -> free rebound. Samples every dt plus the wall hit."""
    p, v, t = tuple(map(float, p0)), tuple(map(float, v0)), 0.0
    ts, ps = [0.0], [p]
    wall = None
    while t < t_end - 1e-12:
        p1, v1 = _rk4(p, v, dt)
        if wall is None and p1[2] <= 0.0 < p[2]:
            f = p[2] / (p[2] - p1[2])
            tw = t + f * dt
            pw = tuple(p[i] + f * (p1[i] - p[i]) for i in range(3))
            pw = (pw[0], pw[1], 0.0)
            vw = tuple(v[i] + f * (v1[i] - v[i]) for i in range(3))
            wall = {"t": tw, "point": pw, "velocity": vw}
            ts.append(tw)
            ps.append(pw)
            p, v, t = pw, tuple(map(float, v_rebound)), tw
            continue
        p, v, t = p1, v1, t + dt
        ts.append(t)
        ps.append(p)
    return {"t": np.array(ts), "p": np.array(ps), "wall": wall}


def _positions_at(fl: dict, times: np.ndarray) -> np.ndarray:
    return np.column_stack([np.interp(times, fl["t"], fl["p"][:, k]) for k in range(3)])


def _unpack(x, cam: Camera, cpx):
    s, speed, az, el = x[:4]
    p0 = cam.center + s * cam.ray(cpx)
    v0 = speed * launch_direction(el, az)
    return p0, v0, x[4:7]


def _first_rebound_hit(fl: dict) -> float | None:
    """Time the rebound first reaches a side wall or the floor (where the free flight ends)."""
    if fl["wall"] is None:
        return None
    after = fl["t"] > fl["wall"]["t"]
    p = fl["p"][after]
    hit = (p[:, 0] < 0) | (p[:, 0] > COURT_WIDTH_M) | (p[:, 1] < 0)
    return float(fl["t"][after][np.argmax(hit)]) if hit.any() else None


def fit_flight(cam: Camera, cpx, times: np.ndarray, pixels: np.ndarray, z_feet: float | None = None) -> dict:
    """Least squares on pixel positions: contact depth, launch speed/aim/angle, rebound velocity.

    z_feet: the player's feet along the court; the contact is kept within CONTACT_Z_SIGMA_M (1 sd).
    """
    times, pixels = np.asarray(times, float), np.asarray(pixels, float)
    C, d = cam.center, cam.ray(cpx)
    keep = np.ones(len(times), bool)

    def residuals(x, sel):
        p0, v0, vr = _unpack(x, cam, cpx)
        fl = flight(p0, v0, vr, float(times[sel].max()) + FIT_DT_S)
        r = (cam.project(_positions_at(fl, times[sel])) - pixels[sel]).ravel()
        if z_feet is not None:
            r = np.append(r, (p0[2] - z_feet) / CONTACT_Z_SIGMA_M * PRIOR_PX)
        return r

    lo = [0.3, 5.0, -70.0, -30.0, -40.0, -30.0, 0.0]
    hi = [30.0, 80.0, 70.0, 50.0, 40.0, 30.0, 40.0]
    best = None
    for _ in range(3):
        sel = keep.copy()
        # Start depths: level with the feet, or where the contact ray is 0.6 m or 1.0 m high.
        if z_feet is not None and d[2] < -1e-6:
            depths = [(C[2] - z_feet) / -d[2]]
        else:
            depths = [(C[1] - h) / -d[1] for h in (0.6, 1.0) if d[1] < -1e-6 and C[1] > h] or [3.0]
        starts = [np.clip([s0, sp0, az0, el0, 0.0, 2.0, 8.0], lo, hi)
                  for s0 in depths for sp0 in (20.0, 35.0) for az0, el0 in FIT_STARTS]
        scored = sorted(starts, key=lambda x0: _robust_cost(residuals(x0, sel)))
        best = None
        for x0 in scored[:FIT_REFINE]:
            sol = least_squares(residuals, x0, bounds=(lo, hi), args=(sel,),
                                loss="soft_l1", f_scale=2.0, x_scale="jac", max_nfev=300)
            if best is None or sol.cost < best.cost:
                best = sol
        p0, v0, vr = _unpack(best.x, cam, cpx)
        fl = flight(p0, v0, vr, float(times.max()) + FIT_DT_S)
        stop = _first_rebound_hit(fl)
        limit = None if fl["wall"] is None else fl["wall"]["t"] + MAX_AFTER_WALL_S
        if stop is not None:
            limit = stop if limit is None else min(limit, stop)
        new_keep = np.ones(len(times), bool) if limit is None else times <= limit
        if (new_keep == keep).all():
            break
        keep = new_keep
    sel = keep
    res = residuals(best.x, sel)
    res = res[: 2 * int(sel.sum())].reshape(-1, 2)
    p0, v0, vr = _unpack(best.x, cam, cpx)
    fl = flight(p0, v0, vr, float(times[sel].max()) + FIT_DT_S)
    wall_t = None if fl["wall"] is None else fl["wall"]["t"]
    out = {
        "x": best.x, "flight": fl, "used": sel,
        "rmsPx": float(np.sqrt(np.mean(np.sum(res ** 2, axis=1)))),
        "pointsBeforeWall": int(np.sum(sel & (times < (wall_t if wall_t is not None else np.inf)))),
        "pointsAfterWall": int(np.sum(sel & (times >= (wall_t if wall_t is not None else np.inf)))),
    }
    out["sigma"] = _sigma(best, sel, cam, cpx, times)
    return out


def _derived(x, cam: Camera, cpx, t_end: float) -> np.ndarray:
    """[speed km/h, azimuth, elevation, wall x, wall height, wall t] from fit parameters."""
    p0, v0, vr = _unpack(x, cam, cpx)
    fl = flight(p0, v0, vr, t_end)
    w = fl["wall"]
    wx, wy, wt = (w["point"][0], w["point"][1], w["t"]) if w else (np.nan, np.nan, np.nan)
    return np.array([x[1] * 3.6, x[2], x[3], wx, wy, wt])


def _sigma(sol, sel, cam, cpx, times) -> dict:
    """1-sigma from the fit (Gauss-Newton covariance), propagated to the reported numbers."""
    J = sol.jac
    m, n = J.shape
    if m <= n:
        return {}
    s2 = 2 * sol.cost / (m - n)
    try:
        cov = np.linalg.inv(J.T @ J) * s2
    except np.linalg.LinAlgError:
        return {}
    t_end = float(times[sel].max()) + 0.5
    base = _derived(sol.x, cam, cpx, t_end)
    G = np.zeros((len(base), n))
    for k in range(n):
        h = 1e-4 * max(1.0, abs(sol.x[k]))
        xk = sol.x.copy()
        xk[k] += h
        G[:, k] = (_derived(xk, cam, cpx, t_end) - base) / h
    sd = np.sqrt(np.clip(np.diag(G @ cov @ G.T), 0, None))
    names = ["speedKmh", "azimuthDeg", "elevationDeg", "frontWallXM", "frontWallHeightM", "timeToWallS"]
    return {k: (None if not np.isfinite(v) else round(float(v), 3)) for k, v in zip(names, sd)}


# ---------------------------------------------------------------- comparison

def predicted_from_compare(cmp: dict) -> dict:
    """What the model said about the player's own ball (compare()'s `you` side)."""
    ball = cmp["you"]["ball"]
    launch = cmp["assumptions"]["launch"]["you"]
    elevation = cmp["assumptions"]["launchElevationDeg"]
    wall = next((e for e in ball["events"] if e["type"] == "front_wall"), None)
    az = launch["azimuth"]
    return {
        "label": "PREDICTED",
        "contactPointM": launch["point"],
        "speedKmh": ball["speedKmh"],
        "azimuthDeg": az["value"],
        "azimuthLabel": az.get("label"),
        "elevationDeg": elevation,
        "elevationLabel": "ASSUMED",
        "frontWall": None if wall is None else {
            "xM": wall["point"][0], "heightM": wall["point"][1], "tS": wall["t"]},
    }


def errors(tracked: dict, predicted: dict) -> dict:
    """Measured minus predicted, for every number both sides have."""
    def diff(a, b, nd):
        return None if a is None or b is None else round(a - b, nd)
    tw, pw = tracked.get("frontWall") or {}, predicted.get("frontWall") or {}
    spot = None
    if tracked.get("contactPointM") and predicted.get("contactPointM"):
        a, b = tracked["contactPointM"], predicted["contactPointM"]
        spot = round(math.hypot(a[0] - b[0], a[2] - b[2]), 2)
    return {
        "directionDeg": diff(tracked.get("azimuthDeg"), predicted.get("azimuthDeg"), 1),
        "frontWallHeightM": diff(tw.get("heightM"), pw.get("heightM"), 2),
        "frontWallXM": diff(tw.get("xM"), pw.get("xM"), 2),
        "speedKmh": diff(tracked.get("speedKmh"), predicted.get("speedKmh"), 1),
        "elevationDeg": diff(tracked.get("elevationDeg"), predicted.get("elevationDeg"), 1),
        "timeToWallS": diff(tw.get("tS"), pw.get("tS"), 3),
        "contactSpotM": spot,
    }


def measure(cam: Camera, cpx, points, contact: int, fps_real: float, z_feet: float | None = None) -> dict:
    """3D flight from tracked pixels: the measured launch and front-wall hit."""
    # Each file frame is one captured frame: 1 / fps_real of real time (the file plays it
    # `slowdown` times slower, at fps_real / slowdown).
    times = np.array([(f - contact) / fps_real for f, _, _ in points], float)
    pixels = np.array([(u, v) for _, u, v in points], float)
    fit = fit_flight(cam, cpx, times, pixels, z_feet)
    p0, v0, vr = _unpack(fit["x"], cam, cpx)
    w = fit["flight"]["wall"]
    return {
        "contactPointM": [round(float(c), 3) for c in p0],
        "speedKmh": round(float(fit["x"][1]) * 3.6, 1),
        "azimuthDeg": round(float(fit["x"][2]), 1),
        "elevationDeg": round(float(fit["x"][3]), 1),
        "frontWall": None if w is None else {
            "xM": round(w["point"][0], 3), "heightM": round(w["point"][1], 3), "tS": round(w["t"], 3)},
        "reboundVelocityMs": [round(float(c), 2) for c in vr],
        "fit": {"rmsPx": round(fit["rmsPx"], 2), "pointsBeforeWall": fit["pointsBeforeWall"],
                "pointsAfterWall": fit["pointsAfterWall"], "pointsDropped": int(np.sum(~fit["used"])),
                "sigma1": fit["sigma"]},
        "_flight": fit["flight"],
    }


def load_labels(path: Path) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return {"contactPx": tuple(data["contactPx"]) if data.get("contactPx") else None,
            "points": [tuple(p) for p in data.get("ball", [])], "note": data.get("note", "")}


def check_swing(entry: dict, clip_dir: Path = CLIP_DIR, debug_dir: Path | None = DEBUG_DIR,
                tracker=track_ball, feet=pose_feet) -> dict:
    """One swing: track, fit, compare. entry is one item of validation/swings.json."""
    clip = Path(clip_dir) / entry["clip"]
    if not clip.exists():
        raise FileNotFoundError(f"{clip} doesn't exist: copy the clip into {clip_dir}")
    world, pixels, size, court = load_court(VALIDATION_DIR / entry["court"])
    cam, cal_rms = calibrate(world, pixels, size)
    contact, fps_real, slowdown = int(entry["contactFileFrame"]), float(entry["fpsReal"]), float(entry["slowdown"])

    feet_px = feet(clip, contact)
    feet_x, feet_z = feet_on_floor(cam, feet_px)
    found = tracker(clip, cam, size, contact, feet_z + ROI_BEHIND_FEET_M)
    labels = load_labels(VALIDATION_DIR / f"labels_{entry['swing']}.json")
    method, notes = "tracked", []
    cpx, points = found["contactPx"], found["points"]
    if len(points) < MIN_TRACK:
        if labels is None or len(labels["points"]) < 3:
            raise ValueError(f"{entry['swing']}: the tracker found {len(points)} ball points after contact "
                             f"(need {MIN_TRACK}) and there are no hand labels")
        points, method = labels["points"], "hand-labelled"
        notes.append(f"tracker found {len(found['points'])} points; used {len(points)} hand-labelled points")
    if cpx is None:
        if labels is None or labels["contactPx"] is None:
            raise ValueError(f"{entry['swing']}: no incoming ball track for the contact pixel and no hand label")
        cpx = labels["contactPx"]
        method = "hand-labelled"
        notes.append("contact pixel hand-labelled (no incoming ball track)")
    else:
        notes.append("contact pixel from the incoming ball's track, extrapolated to the contact frame")

    tracked = measure(cam, cpx, points, contact, fps_real, feet_z)
    cmp = json.loads((REPO / entry["compare"]).read_text())
    predicted = predicted_from_compare(cmp)
    result = {
        "swing": entry["swing"],
        "clip": entry["clip"],
        "stroke": entry["stroke"],
        "method": method,
        "notes": notes,
        "contact": {"fileFrame": contact, "source": entry["contactSource"],
                    "px": [round(float(c), 1) for c in cpx], "fpsReal": fps_real, "slowdown": slowdown,
                    "feetPx": [[round(u, 1), round(v, 1)] for u, v in feet_px],
                    "feetFloorM": [round(feet_x, 2), round(feet_z, 2)],
                    "depthPrior": f"contact within {CONTACT_Z_SIGMA_M} m (1 sd) of the feet along the court; "
                                  "feet from the pipeline's pose model, placed on the floor by the camera"},
        "camera": {"focalPx": round(cam.focal, 1), "positionM": [round(float(c), 3) for c in cam.center],
                   "landmarks": len(world), "landmarkRmsPx": round(cal_rms, 2), "source": court.get("source")},
        "trackedPoints": [[int(f), round((f - contact) / fps_real, 4), round(float(u), 1),
                           round(float(v), 1)] for f, u, v in points],
        "tracked": {k: v for k, v in tracked.items() if not k.startswith("_")},
        "predicted": predicted,
        "error": errors(tracked, predicted),
    }
    if debug_dir is not None:
        result["debugImage"] = str(debug_image(clip, cam, world, pixels, cpx, points, tracked, cmp,
                                               contact, Path(debug_dir) / f"{entry['swing']}.jpg"
                                               ).relative_to(REPO))
    return result


# ---------------------------------------------------------------- debug image

ORANGE, PURPLE, YELLOW, GREEN, RED = (61, 138, 255), (220, 80, 200), (0, 230, 255), (0, 200, 0), (0, 0, 255)


def _polyline(img, cam: Camera, P: np.ndarray, colour, thick=2):
    P = P[cam.depth(P) > 0.2]
    if len(P) >= 2:
        cv2.polylines(img, [np.round(cam.project(P)).astype(np.int32)], False, colour, thick, cv2.LINE_AA)


def debug_image(clip, cam, world, pixels, cpx, points, tracked, cmp, contact, out: Path) -> Path:
    img = read_colour(clip, contact)
    for X, px in zip(world, pixels):
        q = cam.project(X)[0]
        cv2.drawMarker(img, tuple(int(round(c)) for c in px), GREEN, cv2.MARKER_CROSS, 14, 2)
        cv2.circle(img, tuple(int(round(c)) for c in q), 4, RED, 1, cv2.LINE_AA)
    fl = tracked["_flight"]
    _polyline(img, cam, fl["p"], ORANGE, 3)
    pred = np.array(cmp["you"]["ball"]["points"], float)
    wall_i = next((i for i, q in enumerate(pred) if q[2] <= 1e-6), len(pred) - 1)
    _polyline(img, cam, pred[: wall_i + 12], PURPLE, 2)
    for f, u, v in points:
        cv2.circle(img, (int(round(u)), int(round(v))), 5, YELLOW, -1, cv2.LINE_AA)
        if (f - contact) % 5 == 0:
            cv2.putText(img, f"+{f - contact}", (int(u) + 7, int(v) - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        YELLOW, 1, cv2.LINE_AA)
    cv2.drawMarker(img, tuple(int(round(c)) for c in cpx), ORANGE, cv2.MARKER_TILTED_CROSS, 22, 3)
    if tracked["frontWall"]:
        w = tracked["frontWall"]
        q = cam.project([w["xM"], w["heightM"], 0.0])[0]
        cv2.circle(img, tuple(int(round(c)) for c in q), 14, ORANGE, 3, cv2.LINE_AA)
    pw = next((e for e in cmp["you"]["ball"]["events"] if e["type"] == "front_wall"), None)
    if pw:
        q = cam.project(pw["point"])[0]
        cv2.circle(img, tuple(int(round(c)) for c in q), 14, PURPLE, 3, cv2.LINE_AA)
    lines = [("yellow dots: tracked ball (+file frames after contact)", YELLOW),
             ("orange: 3D fit of the real ball, ring = front-wall hit", ORANGE),
             ("purple: PREDICTED path from the body, ring = its front-wall hit", PURPLE),
             ("green +: court landmarks, red o: reprojected", GREEN)]
    for k, (text, colour) in enumerate(lines):
        cv2.putText(img, text, (20, img.shape[0] - 20 - 26 * (len(lines) - 1 - k)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, text, (20, img.shape[0] - 20 - 26 * (len(lines) - 1 - k)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, colour, 2, cv2.LINE_AA)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out


# ---------------------------------------------------------------- table and CLI

def _fmt(v, nd=2, sign=False):
    if v is None:
        return "n/a"
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def table(results: list[dict]) -> str:
    rows = ["| Swing | Method | Direction (deg) tracked / PREDICTED / error | Front wall height (m) "
            "tracked / PREDICTED / error | Front wall x (m) tracked / PREDICTED / error | "
            "Speed (km/h) tracked / PREDICTED | Launch angle (deg) tracked / ASSUMED | Fit RMS (px) |",
            "|---|---|---|---|---|---|---|---|"]
    for r in results:
        t, p, e = r["tracked"], r["predicted"], r["error"]
        tw, pw = t.get("frontWall") or {}, p.get("frontWall") or {}
        sg = t["fit"]["sigma1"]
        rows.append(
            f"| {r['swing']} ({r['stroke']}) | {r['method']} | "
            f"{_fmt(t['azimuthDeg'], 1)} ± {_fmt(sg.get('azimuthDeg'), 1)} / {_fmt(p['azimuthDeg'], 1)} / "
            f"**{_fmt(e['directionDeg'], 1, True)}** | "
            f"{_fmt(tw.get('heightM'))} ± {_fmt(sg.get('frontWallHeightM'))} / {_fmt(pw.get('heightM'))} / "
            f"**{_fmt(e['frontWallHeightM'], 2, True)}** | "
            f"{_fmt(tw.get('xM'))} ± {_fmt(sg.get('frontWallXM'))} / {_fmt(pw.get('xM'))} / "
            f"**{_fmt(e['frontWallXM'], 2, True)}** | "
            f"{_fmt(t['speedKmh'], 1)} ± {_fmt(sg.get('speedKmh'), 1)} / {_fmt(p['speedKmh'], 1)} | "
            f"{_fmt(t['elevationDeg'], 1)} / {_fmt(p['elevationDeg'], 1)} | {_fmt(t['fit']['rmsPx'])} |")
    return "\n".join(rows)


def spot_check(entry: dict) -> dict | None:
    """Before and after measuring where the player hit from, next to the tracked ball.

    before: your PREDICTED ball as the saved compare file has it (the ASSUMED drive spot).
    after: the same compare() run (same fix, amount, rate, hand, stroke and ASSUMED launch angle)
    with the MEASURED spot from validation/spots/<swing>.json. Nothing is fitted to the ball:
    the spot comes from the court lines and the feet. None when the swing has no measured spot.
    """
    path = SPOTS_DIR / f"{entry['swing']}.json"
    if not path.exists():
        return None
    from physics.compare import compare

    saved = json.loads((REPO / entry["compare"]).read_text())
    swing = json.loads((REPO / entry["swingFile"]).read_text())
    result = json.loads((RESULTS_DIR / f"{entry['swing']}.json").read_text())
    a = saved["assumptions"]
    after = compare(swing, saved["fix"]["id"], saved["fix"]["amount"], saved["fpsReal"], saved["hand"],
                    a["launchElevationDeg"], side=a["stroke"]["value"], intent=None,
                    spot=json.loads(path.read_text()))
    before, now = predicted_from_compare(saved), predicted_from_compare(after)
    return {"swing": entry["swing"], "stroke": entry["stroke"], "method": result["method"],
            "tracked": result["tracked"], "before": before, "after": now,
            "spot": after["assumptions"]["anchor"],
            "errorBefore": errors(result["tracked"], before), "errorAfter": errors(result["tracked"], now)}


def spot_table(rows: list[dict]) -> str:
    out = ["| Swing | Method | Spot (x, z) m: ASSUMED → MEASURED | Front wall height (m): tracked / before / after "
           "(error before → after) | Direction (deg): tracked / PREDICTED (error) |",
           "|---|---|---|---|---|"]
    for r in rows:
        t, b, a = r["tracked"], r["before"], r["after"]
        eb, ea = r["errorBefore"], r["errorAfter"]
        out.append(
            f"| {r['swing']} ({r['stroke']}) | {r['method']} | "
            f"({b['contactPointM'][0]:.2f}, {b['contactPointM'][2]:.2f}) → "
            f"({a['contactPointM'][0]:.2f}, {a['contactPointM'][2]:.2f}) | "
            f"{_fmt(t['frontWall']['heightM'])} / {_fmt(b['frontWall']['heightM'])} / {_fmt(a['frontWall']['heightM'])} "
            f"(**{_fmt(eb['frontWallHeightM'], 2, True)} → {_fmt(ea['frontWallHeightM'], 2, True)}**) | "
            f"{_fmt(t['azimuthDeg'], 1)} / {_fmt(a['azimuthDeg'], 1)} ({_fmt(ea['directionDeg'], 1, True)}) |")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check the PREDICTED ball against the real ball in the clip.")
    ap.add_argument("--swing", action="append", help="swing id from validation/swings.json (default: all)")
    ap.add_argument("--clips", type=Path, default=CLIP_DIR, help="folder with the clips (default data/raw)")
    ap.add_argument("--no-save", action="store_true", help="print only; don't write results or images")
    ap.add_argument("--spot", action="store_true",
                    help="no tracking: print the saved results before / after the MEASURED spot (validation/spots)")
    args = ap.parse_args(argv)
    entries = json.loads((VALIDATION_DIR / "swings.json").read_text())["swings"]
    if args.swing:
        entries = [e for e in entries if e["swing"] in args.swing]
        if not entries:
            print("no such swing in validation/swings.json", file=sys.stderr)
            return 1
    if args.spot:
        rows = [r for r in map(spot_check, entries) if r is not None]
        print(spot_table(rows))
        return 0 if rows else 1
    results = []
    for entry in entries:
        try:
            r = check_swing(entry, args.clips, None if args.no_save else DEBUG_DIR)
        except (FileNotFoundError, ValueError) as exc:
            print(f"{entry['swing']}: {exc}", file=sys.stderr)
            continue
        results.append(r)
        if not args.no_save:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            (RESULTS_DIR / f"{r['swing']}.json").write_text(json.dumps(r, indent=1) + "\n")
    if results:
        print(table(results))
    return 0 if len(results) == len(entries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
