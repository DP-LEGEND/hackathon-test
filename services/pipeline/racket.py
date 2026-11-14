"""Racket line from bright tape markers. Owner: Dev.

Placeholder: no implementation yet.

Plan: find the two tape colours (racket tip and throat) in each frame with
simple OpenCV colour thresholds, and return their 2D positions per frame.
Combined with the wrist, that gives the racket-head path and speed.
"""


def track_racket(video_path: str) -> list[dict]:
    """Return one {"t": seconds, "tip": [x, y] | None, "throat": [x, y] | None} per frame."""
    raise NotImplementedError("racket tracking not built yet")
