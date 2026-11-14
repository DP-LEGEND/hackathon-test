"""Ghost: edit the skeleton to apply one fix. Owner: aryan.

Placeholder. Edits keep bone lengths fixed and re-solve limbs with two-bone IK.
Fixes: rotate hips more, bend lower, contact earlier, keep wrist cocked,
lead with the elbow, more compact backswing.
Run in reverse (inject a fault of known size) to make synthetic training data.
"""


def apply_fix(swing: dict, fix_id: str, amount: float) -> dict:
    """Return a new swing with the fix applied. Never mutate the input."""
    raise NotImplementedError
