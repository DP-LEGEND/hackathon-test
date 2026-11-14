"""Swing metrics computed from the skeleton. Owner: aryan.

Placeholder. Each metric is a small pure function: skeleton in, number out.
First ones: contact frame (peak racket-head speed), contact point vs front foot,
racket-head speed, hip turn range, front-knee angle, wrist-to-racket angle.
"""


def contact_frame(swing: dict) -> int:
    """Index of the frame where racket-head speed peaks in the forward swing."""
    raise NotImplementedError
