"""Body pose from a clip. Owner: Dev.

Runs the MediaPipe Pose Landmarker (tasks API) in VIDEO mode on one person and
keeps, per frame:
- `img`:   33 image landmarks (x, y in pixels, z relative), NaN when not detected
- `world`: 33 world landmarks (metres, centred on the hips), NaN when not detected
- `vis`:   33 visibility scores

Model file: set GHOST_POSE_MODEL or pass `model_path` (default
~/ghost-models/pose_landmarker_heavy.task). Download:
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

DEFAULT_MODEL = os.environ.get(
    "GHOST_POSE_MODEL", str(Path.home() / "ghost-models" / "pose_landmarker_heavy.task")
)


def _landmarker(model_path: str):
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision

    opts = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(opts)


def extract_raw(
    video_path: str,
    start_s: float = 0.0,
    end_s: float | None = None,
    model_path: str = DEFAULT_MODEL,
    max_width: int = 1280,
) -> dict:
    """Run pose on [start_s, end_s) of a clip. Returns numpy arrays (see module doc)."""
    import mediapipe as mp

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    f0 = int(start_s * fps)
    f1 = n_total if end_s is None else min(n_total, int(end_s * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f0)
    scale = min(1.0, max_width / w)

    t, img, world, vis = [], [], [], []
    with _landmarker(model_path) as lm:
        for i in range(f0, f1):
            ok, frame = cap.read()
            if not ok:
                break
            if scale < 1.0:
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = lm.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(i * 1000 / fps)
            )
            t.append(i / fps)
            if res.pose_landmarks:
                p, q = res.pose_landmarks[0], res.pose_world_landmarks[0]
                img.append([[l.x * w, l.y * h, l.z * w] for l in p])
                world.append([[l.x, l.y, l.z] for l in q])
                vis.append([l.visibility for l in p])
            else:
                img.append(np.full((33, 3), np.nan))
                world.append(np.full((33, 3), np.nan))
                vis.append(np.zeros(33))
    cap.release()
    return {
        "fps": fps,
        "size": (w, h),
        "t": np.asarray(t),
        "img": np.asarray(img, dtype=float),
        "world": np.asarray(world, dtype=float),
        "vis": np.asarray(vis, dtype=float),
    }


def smooth(x: np.ndarray, win: int = 5) -> np.ndarray:
    """Centred moving average over time (axis 0), ignoring NaNs."""
    if win <= 1:
        return x
    k = np.ones(win)
    valid = ~np.isnan(x)
    num = np.apply_along_axis(lambda a: np.convolve(a, k, "same"), 0, np.where(valid, x, 0.0))
    den = np.apply_along_axis(lambda a: np.convolve(a, k, "same"), 0, valid.astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        return num / den


def to_swing(raw: dict, f0: int = 0, f1: int | None = None, smooth_win: int = 3) -> dict:
    """Slice raw output into the `Swing` shape from lib/ghost/types.ts."""
    world = smooth(raw["world"][f0:f1], smooth_win)
    t = raw["t"][f0:f1]
    frames = [
        {"t": float(ti - t[0]), "joints": np.nan_to_num(wj).round(4).tolist()}
        for ti, wj in zip(t, world)
    ]
    return {"fps": float(raw["fps"]), "frames": frames}


def extract_pose(video_path: str) -> dict:
    """Return {"fps": ..., "frames": [{"t": seconds, "joints": [[x, y, z], ...33]}]}."""
    return to_swing(extract_raw(video_path))
