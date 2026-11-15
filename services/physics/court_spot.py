"""Where the player hit from, measured from the video. Owner: aryan.

compare() places your racket head at contact over an anchor on the court floor, and the
PREDICTED ball launches from there. Without a measurement that anchor is the ASSUMED drive spot
for the stroke (compare.DRIVE_SPOT_RIGHT_HANDED). When the camera sees enough court lines, this
measures it instead:

1. Floor homography: image -> court floor (x, z), from the court-line landmarks that lie on the
   floor (front-wall corners, short line, service-box and half-court lines). They are picked once
   per camera set-up (validation/court_<clip>.json); at least 4 floor points are needed.
2. The hitting-side foot at contact: its heel and toe from the pose model, put on the floor
   through the homography.
3. The racket head's ground position: that foot plus the skeleton's own offset from the same heel
   and toe to its racket head (court axes, metres, measured by the pose). That is the anchor.
   The skeleton's axes are the camera's, so the camera must face the front wall: its yaw, solved
   from the same court lines, must be within MAX_CAMERA_YAW_DEG.

Code measures: nothing here is fitted to the ball. The launch angle stays ASSUMED in compare().

From services/ (clip in data/raw/):
    python -m physics.court_spot ../data/raw/IMG_2115.MOV --court physics/validation/court_IMG_2115.json \
        --swing ../public/swings/swing_fh_over_rotation.json --contact-file-frame 30450
prints the spot as JSON (pass it to compare with --spot-file).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

from physics.ball import COURT_LENGTH_M, COURT_WIDTH_M
from physics.skeleton import court_axes, racket_head, to_array

MIN_FLOOR_POINTS = 4
MAX_CAMERA_YAW_DEG = 10.0
MIN_FOOT_VIS = 0.5
HEEL = {"L": 29, "R": 30}
TOE = {"L": 31, "R": 32}     # MediaPipe "foot index"
SPOT_LABEL = "MEASURED"


def load_court(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def floor_homography(court: dict) -> tuple[np.ndarray, float | None, int]:
    """(H image -> floor (x, z), landmark RMS in metres or None with exactly 4 points, floor points)."""
    pts = [p for p in court["points"] if abs(p["court"][1]) < 1e-9]
    if len(pts) < MIN_FLOOR_POINTS:
        raise ValueError(f"need at least {MIN_FLOOR_POINTS} court-line landmarks on the floor, got {len(pts)}: "
                         "the camera doesn't see enough court lines, so the spot stays ASSUMED")
    px = np.array([p["px"] for p in pts], float)
    xz = np.array([[p["court"][0], p["court"][2]] for p in pts], float)
    H, _ = cv2.findHomography(px, xz, 0)
    if H is None:
        raise ValueError("couldn't solve the floor homography from the court lines")
    rms = None
    if len(pts) > MIN_FLOOR_POINTS:
        rms = float(np.sqrt(np.mean(np.sum((to_floor(H, px) - xz) ** 2, axis=1))))
    return H, rms, len(pts)


def to_floor(H: np.ndarray, px) -> np.ndarray:
    """Floor (x, z) of image point(s) px through the homography."""
    p = np.atleast_2d(np.asarray(px, float))
    q = np.column_stack([p, np.ones(len(p))]) @ H.T
    out = q[:, :2] / q[:, 2:3]
    return out[0] if np.ndim(px) == 1 else out


def camera_yaw_deg(court: dict) -> float:
    """Camera yaw from the court lines: 0 = looking straight at the front wall."""
    from physics.validate_ball import calibrate

    world = np.array([p["court"] for p in court["points"]], float)
    px = np.array([p["px"] for p in court["points"]], float)
    cam, _ = calibrate(world, px, tuple(court["frameSize"]))
    axis = cam.R.T @ np.array([0.0, 0.0, 1.0])
    return math.degrees(math.atan2(axis[0], -axis[2]))


def pose_at(clip: Path, frame: int) -> tuple[np.ndarray, np.ndarray]:
    """(image landmarks (33, 3), visibility (33,)) at one file frame, from the pipeline's pose model.

    The model tracks, so it runs from 30 frames earlier and keeps the last frame.
    """
    from pipeline.pose import extract_raw

    fps = cv2.VideoCapture(str(clip)).get(cv2.CAP_PROP_FPS)
    if not fps:
        raise FileNotFoundError(f"can't read {clip}")
    # Half-frame offsets so extract_raw's int(seconds * fps) lands on frame - 30 .. frame.
    raw = extract_raw(str(clip), (frame - 30 + 0.5) / fps, (frame + 1 + 0.5) / fps)
    if round(raw["t"][-1] * fps) != frame:
        raise ValueError(f"pose ended on frame {round(raw['t'][-1] * fps)}, not frame {frame}")
    return raw["img"][-1], raw["vis"][-1]


def hitting_foot_px(img: np.ndarray, vis: np.ndarray, hand: str) -> list[tuple[float, float]]:
    """Heel and toe pixels of the hitting-side foot (the right foot for a right-hander)."""
    pts = [(float(img[j, 0]), float(img[j, 1])) for j in (HEEL[hand], TOE[hand])
           if vis[j] >= MIN_FOOT_VIS and np.isfinite(img[j, :2]).all()]
    if len(pts) < 2:
        raise ValueError("the pose model didn't see the hitting-side heel and toe at contact")
    return pts


def measure_spot(swing: dict, hand: str, contact: int, foot_px, court: dict) -> dict:
    """The anchor compare() uses, measured: the racket head's ground position at contact.

    swing: the pipeline swing (as compare() takes it); contact: its contact frame (swing frames);
    foot_px: the hitting-side heel and toe pixels at that moment; court: the camera's landmarks.
    """
    yaw = camera_yaw_deg(court)
    if abs(yaw) > MAX_CAMERA_YAW_DEG:
        raise ValueError(f"the camera is turned {yaw:.1f} deg from the front wall (limit {MAX_CAMERA_YAW_DEG:g}); "
                         "the skeleton's axes wouldn't be the court's, so the spot stays ASSUMED")
    H, rms, n_floor = floor_homography(court)
    foot = np.mean(to_floor(H, np.asarray(foot_px, float)), axis=0)
    Q = court_axes(to_array(swing))
    skel_foot = np.nanmean(Q[contact, [HEEL[hand], TOE[hand]]][:, [0, 2]], axis=0)
    head = racket_head(Q, hand)[contact][[0, 2]]
    if not (np.isfinite(skel_foot).all() and np.isfinite(head).all()):
        raise ValueError("the skeleton's hitting-side foot or racket head is missing at contact")
    offset = head - skel_foot
    x, z = (foot + offset).tolist()
    if not (0.0 <= x <= COURT_WIDTH_M and 0.0 < z <= COURT_LENGTH_M):
        raise ValueError(f"the measured spot ({x:.2f}, {z:.2f}) m is off the court")
    side = "right" if hand == "R" else "left"
    return {
        "x": round(x, 3), "z": round(z, 3), "label": SPOT_LABEL,
        "method": (f"video: the {side} foot at contact put on the floor through the court lines "
                   f"({n_floor} floor landmarks), plus the skeleton's foot-to-racket-head offset"),
        "footM": [round(float(c), 3) for c in foot],
        "offsetM": [round(float(c), 3) for c in offset],
        "floorLandmarkRmsM": None if rms is None else round(rms, 3),
        "cameraYawDeg": round(yaw, 1),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure where the player hit from (compare's anchor) from the video.")
    ap.add_argument("clip", type=Path)
    ap.add_argument("--court", type=Path, required=True, help="court landmarks JSON for this camera set-up")
    ap.add_argument("--swing", type=Path, required=True, help="the pipeline swing JSON")
    ap.add_argument("--contact-file-frame", type=int, required=True,
                    help="the video frame (file frames) of the swing's contact frame")
    ap.add_argument("--hand", choices=["R", "L"], default=None, help="hitting hand (default: the swing's)")
    args = ap.parse_args(argv)
    try:
        from physics.compare import ball_contact, swing_hand

        swing = json.loads(args.swing.read_text())
        P = to_array(swing)
        hand = args.hand or swing_hand(swing, P)
        contact, _ = ball_contact(swing, P, hand)
        img, vis = pose_at(args.clip, args.contact_file_frame)
        spot = measure_spot(swing, hand, contact, hitting_foot_px(img, vis, hand), load_court(args.court))
    except (OSError, ValueError, KeyError) as exc:
        print(f"court_spot: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(spot, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
