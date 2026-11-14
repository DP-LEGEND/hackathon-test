"""PREDICTED ball flight from the racket at contact. Owner: aryan.

There is no real ball in the demo: everything here is a prediction and must be shown
with a "PREDICTED" badge. The output says so too (predicted: true, label: "PREDICTED").

The model, in plain words:
1. Racket -> ball. The racket head hits a light ball. A collision with the racket's
   "effective mass" (how heavy the racket feels at the hit point) gives
       ball speed = (1 + e) * M / (M + m) * racket speed  +  e_A * incoming ball speed
   which comes out at about 1.3x racket-head speed.
2. Flight. Gravity plus air drag that grows with speed squared, stepped every 1 ms.
3. Walls. The ball must hit the front wall between the tin and the out line, bounces
   off walls and floor losing most of its speed, and we follow it to its second
   floor bounce. The first floor bounce after the front wall is the landing spot.

Not modelled (first-order model): spin, ball warming up, the ball's size (it is
treated as a point at its centre).

Court coordinates (proposed for docs/interfaces.md), metres:
    origin on the floor at the front-left corner (player's left facing the front wall)
    x across: 0 = left wall -> 6.40 = right wall
    y up:     0 = floor
    z back:   0 = front wall -> 9.75 = back wall
"""

from __future__ import annotations

import math

import numpy as np

# ---- Court: World Squash Federation (WSF) singles court specification ----
COURT_LENGTH_M = 9.75     # front wall to back wall
COURT_WIDTH_M = 6.40      # side wall to side wall
FRONT_OUT_M = 4.57        # front-wall out line
TIN_M = 0.48              # top of the tin (WSF; PSA men's pro events use 0.43)
BACK_OUT_M = 2.13         # back-wall out line; the side-wall out line slopes 4.57 -> 2.13
SHORT_LINE_M = 5.44       # front wall to the short line on the floor (approx.)

# ---- Ball: WSF specification, double-yellow-dot ball ----
BALL_MASS_KG = 0.024      # 24.0 g +/- 1.0 g
BALL_DIAMETER_M = 0.040   # 40.0 mm +/- 0.5 mm

# ---- Air ----
AIR_DENSITY = 1.20        # kg/m^3, about 20 C at sea level (standard atmosphere)
DRAG_COEFF = 0.50         # sphere drag below the drag crisis (Re ~ 1e5): textbook sphere curve. Estimate.
GRAVITY = 9.81            # m/s^2

# ---- Racket-ball collision (Brody's effective-mass model; values are estimates) ----
RACKET_EFFECTIVE_MASS_KG = 0.08  # estimate: a ~140 g racket felt at the sweet spot (hand adds a little)
STRING_COR = 0.70                # estimate: bounciness of a warm squash ball on the strings
# With these, ball speed ~= 1.31 x racket-head speed. Tune against measured ball speeds.

# ---- Bounces off walls and floor (estimates) ----
WALL_COR = 0.30           # estimate: WSF rebound test at 45 C gives e ~0.5-0.57 from a slow drop, and
                          #   bounciness falls at match speeds. 0.30 makes a 165 km/h drive that hits the
                          #   front wall at ~1.1 m land around 7.5 m and then reach the back wall.
FLOOR_COR = 0.40          # estimate: floor impacts are slower, so a little bouncier
TANGENT_KEEP = 0.75       # estimate: share of along-the-surface speed kept (friction, spin ignored)

# ---- Simulation ----
DT_S = 0.001              # time step
MAX_TIME_S = 4.0          # stop following the ball after this
POINT_EVERY_S = 0.01      # output a path point this often (plus every bounce)
DEFAULT_CONTACT = (5.4, 0.6, 7.0)  # forehand drive spot for a right-hander: 1 m off the right wall, behind the short line

_K_DRAG = 0.5 * AIR_DENSITY * DRAG_COEFF * math.pi * (BALL_DIAMETER_M / 2) ** 2 / BALL_MASS_KG


def ball_speed_from_racket(racket_speed_ms: float, incoming_ball_speed_ms: float = 0.0) -> float:
    """Ball speed (m/s) leaving the strings.

    Effective-mass collision: v = (1 + e) M/(M + m) * racket speed + e_A * incoming,
    with apparent bounciness e_A = (e M - m)/(M + m).
    """
    M, m, e = RACKET_EFFECTIVE_MASS_KG, BALL_MASS_KG, STRING_COR
    return (1 + e) * M / (M + m) * racket_speed_ms + (e * M - m) / (M + m) * incoming_ball_speed_ms


def launch_direction(elevation_deg: float, azimuth_deg: float) -> np.ndarray:
    """Unit vector towards the front wall. azimuth 0 = parallel to the side walls,
    + = towards the right wall. elevation + = upwards."""
    el, az = math.radians(elevation_deg), math.radians(azimuth_deg)
    return np.array([math.sin(az) * math.cos(el), math.sin(el), -math.cos(az) * math.cos(el)])


def _accel(v: np.ndarray) -> np.ndarray:
    return np.array([0.0, -GRAVITY, 0.0]) - _K_DRAG * np.linalg.norm(v) * v


def _rk4(p: np.ndarray, v: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray]:
    k1v, k1p = _accel(v), v
    k2v, k2p = _accel(v + 0.5 * dt * k1v), v + 0.5 * dt * k1v
    k3v, k3p = _accel(v + 0.5 * dt * k2v), v + 0.5 * dt * k2v
    k4v, k4p = _accel(v + dt * k3v), v + dt * k3v
    return (p + dt / 6 * (k1p + 2 * k2p + 2 * k3p + k4p),
            v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v))


# (name, axis, wall position, inward normal)
_PLANES = [
    ("front_wall", 2, 0.0, np.array([0.0, 0.0, 1.0])),
    ("back_wall", 2, COURT_LENGTH_M, np.array([0.0, 0.0, -1.0])),
    ("left_wall", 0, 0.0, np.array([1.0, 0.0, 0.0])),
    ("right_wall", 0, COURT_WIDTH_M, np.array([-1.0, 0.0, 0.0])),
    ("floor", 1, 0.0, np.array([0.0, 1.0, 0.0])),
]


def _first_crossing(p0: np.ndarray, p1: np.ndarray):
    """Earliest plane the step p0 -> p1 crosses: (fraction of step, plane) or None."""
    best = None
    for plane in _PLANES:
        _, ax, pos, n = plane
        d0, d1 = (p0[ax] - pos) * n[ax], (p1[ax] - pos) * n[ax]
        if d0 >= 0 > d1:
            f = d0 / (d0 - d1)
            if best is None or f < best[0]:
                best = (f, plane)
    return best


def _bounce(v: np.ndarray, n: np.ndarray, cor: float) -> np.ndarray:
    vn = (v @ n) * n
    return -cor * vn + TANGENT_KEEP * (v - vn)


def _side_out_height(z: float) -> float:
    return BACK_OUT_M + (FRONT_OUT_M - BACK_OUT_M) * (1 - z / COURT_LENGTH_M)


def predict_ball_path(racket_speed_ms: float, elevation_deg: float, azimuth_deg: float = 0.0,
                      contact: tuple[float, float, float] = DEFAULT_CONTACT,
                      incoming_ball_speed_ms: float = 0.0) -> dict:
    """PREDICTED ball path from racket-head speed and launch angle at contact.

    racket_speed_ms: racket-head speed at contact, m/s
    elevation_deg:   launch angle above horizontal (negative = downwards)
    azimuth_deg:     0 = straight at the front wall, + = towards the right wall
    contact:         (x, y, z) court coordinates of the contact point, metres
    incoming_ball_speed_ms: speed of the ball arriving at the racket (0 = ball at rest)

    Returns the PredictedBallPath shape ({points, speedKmh}) plus:
      predicted, label        always True / "PREDICTED"
      outcome                 "in", "tin", "out", or "down" (floor before the front wall)
      frontWallHeightM        height where it hits the front wall (None if it never does)
      landing                 [x, z] of the first floor bounce after the front wall
      secondBounce            [x, z] of the second floor bounce (None if not reached)
      landsBehindShortLine    True/False once it has landed, else None
      events                  every wall/floor hit: {"type", "t", "point"}
    """
    _check_inputs(racket_speed_ms, elevation_deg, azimuth_deg, contact, incoming_ball_speed_ms)
    speed = ball_speed_from_racket(racket_speed_ms, incoming_ball_speed_ms)
    p = np.array(contact, dtype=float)
    v = speed * launch_direction(elevation_deg, azimuth_deg)
    t, next_point = 0.0, POINT_EVERY_S
    points, events = [p.copy()], []
    outcome, front_h, landing, second = None, None, None, None

    def event(kind: str, at: np.ndarray, when: float) -> None:
        events.append({"type": kind, "t": round(when, 3), "point": [round(float(c), 3) for c in at]})
        points.append(at.copy())

    while t < MAX_TIME_S and outcome is None:
        p1, v1 = _rk4(p, v, DT_S)
        hit = _first_crossing(p, p1)
        if hit is None:
            p, v, t = p1, v1, t + DT_S
            if t >= next_point:
                points.append(p.copy())
                next_point += POINT_EVERY_S
            continue
        f, (kind, ax, pos, n) = hit
        p = p + f * (p1 - p)
        p[ax] = pos
        v = v + f * (v1 - v)
        t += f * DT_S
        event(kind, p, t)
        if kind == "front_wall":
            if front_h is None:
                front_h = float(p[1])
                if front_h < TIN_M:
                    outcome = "tin"
                elif front_h > FRONT_OUT_M:
                    outcome = "out"
            v = _bounce(v, n, WALL_COR)
        elif kind == "floor":
            if front_h is None:
                outcome = "down"
            elif landing is None:
                landing = [round(float(p[0]), 3), round(float(p[2]), 3)]
            else:
                second = [round(float(p[0]), 3), round(float(p[2]), 3)]
                outcome = "in"
            v = _bounce(v, n, FLOOR_COR)
        else:  # side or back wall
            limit = BACK_OUT_M if kind == "back_wall" else _side_out_height(float(p[2]))
            if p[1] > limit:
                outcome = "out"
            v = _bounce(v, n, WALL_COR)

    if outcome is None:
        outcome = "in" if landing is not None else ("down" if front_h is None else "in")
    return {
        "predicted": True,
        "label": "PREDICTED",
        "points": [[round(float(c), 3) for c in q] for q in points],
        "speedKmh": round(speed * 3.6, 1),
        "outcome": outcome,
        "frontWallHeightM": None if front_h is None else round(front_h, 3),
        "landing": landing,
        "secondBounce": second,
        "landsBehindShortLine": None if landing is None else landing[1] > SHORT_LINE_M,
        "events": events,
    }


def _check_inputs(racket_speed_ms, elevation_deg, azimuth_deg, contact, incoming) -> None:
    vals = [racket_speed_ms, elevation_deg, azimuth_deg, incoming, *contact]
    if len(contact) != 3 or not all(math.isfinite(x) for x in vals):
        raise ValueError("inputs must be finite numbers and contact must be (x, y, z)")
    if not 0 < racket_speed_ms <= 80:
        raise ValueError(f"racket speed must be between 0 and 80 m/s, got {racket_speed_ms}")
    if not -45 <= elevation_deg <= 75:
        raise ValueError(f"elevation must be between -45 and 75 degrees, got {elevation_deg}")
    if not -80 <= azimuth_deg <= 80:
        raise ValueError(f"azimuth must be between -80 and 80 degrees (towards the front wall), got {azimuth_deg}")
    if not 0 <= incoming <= 60:
        raise ValueError(f"incoming ball speed must be between 0 and 60 m/s, got {incoming}")
    x, y, z = contact
    if not (0 < x < COURT_WIDTH_M and 0 < y < 3 and 0 < z < COURT_LENGTH_M):
        raise ValueError(f"contact {contact} is outside the court (x 0-6.40, y 0-3, z 0-9.75 m)")
