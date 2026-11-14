"""Tools the Claude coach can call. Owners: aryan and Dev.

Placeholder. Each tool wraps a physics function and returns plain JSON:
- get_metrics(swing_id)          -> metrics + faults with sizes and confidence
- apply_fix(swing_id, fix_id)    -> ghost swing id
- simulate(swing_id)             -> predicted ball path
- compare_swings(a_id, b_id)     -> how much of the gap closed
The tool schemas go in docs/interfaces.md once agreed.
"""
