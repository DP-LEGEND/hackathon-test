"""The coach agent loop. Owners: aryan and Dev.

Placeholder. Rule: code measures, Claude explains and decides.
Claude picks ONE fix (stance and contact first, then preparation, rotation, wrist),
names the numbers behind it, picks a drill, and re-tests on the next swing.
The API key comes from .env.local at the repo root (python-dotenv). Never hard-code it.
"""


def coach_swing(swing_id: str) -> dict:
    """Return {"fix", "why", "drill", "ghost_swing_id", "ball_paths"}."""
    raise NotImplementedError
