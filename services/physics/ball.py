"""Predicted ball flight. Owner: aryan.

Placeholder. First-order model, labelled "predicted" everywhere:
racket-head velocity at contact -> effective-mass collision (literature COR)
-> launch direction (face opens by about ds/R when contact is late)
-> projectile with quadratic drag onto a squash court (front wall ~9.75 m).
"""


def predict_ball_path(racket_speed: float, launch_dir: tuple[float, float, float]) -> list[list[float]]:
    """Return [[x, y, z], ...] points in metres, court coordinates."""
    raise NotImplementedError
