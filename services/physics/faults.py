"""Fault library: one small rule per coaching point. Owner: aryan.

Placeholder. Each rule compares a metric with a reference band and returns
{"id", "label", "size", "unit", "confidence"} when the swing is outside it.
Adding a coaching point = one metric + one band + one sentence.
"""


def detect_faults(metrics: dict) -> list[dict]:
    raise NotImplementedError
