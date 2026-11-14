"""Body pose from a slow-motion clip. Owner: Dev.

Placeholder: no implementation yet.

Plan:
- Open the clip with OpenCV, read every frame in order.
- Run the MediaPipe Pose Landmarker in VIDEO mode, one person only.
- Keep the 33 "world" landmarks (metres, centred on the hips) for each frame.
- Smooth the landmarks over time to remove jitter.
- Return a swing dict that matches `Swing` in lib/ghost/types.ts.
"""


def extract_pose(video_path: str) -> dict:
    """Return {"fps": ..., "frames": [{"t": seconds, "joints": [[x, y, z], ...33]}]}."""
    raise NotImplementedError("pose extraction not built yet")
