"""Piecewise QuickTime playback seconds to elapsed real seconds."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Timeline:
    slowdown: float = 1.0
    realtime_before: float = 0.0
    realtime_after: float | None = None

    def __post_init__(self):
        if not np.isfinite(self.slowdown) or self.slowdown <= 0:
            raise ValueError("slowdown must be finite and positive")
        if not np.isfinite(self.realtime_before) or self.realtime_before < 0:
            raise ValueError("realtime_before must be finite and nonnegative")
        if self.realtime_after is not None and (
            not np.isfinite(self.realtime_after) or self.realtime_after <= self.realtime_before
        ):
            raise ValueError("realtime_after must be finite and greater than realtime_before")

    def real(self, seconds):
        t = np.asarray(seconds, dtype=float)
        end = np.inf if self.realtime_after is None else self.realtime_after
        slow_duration = np.maximum(0, np.minimum(t, end) - self.realtime_before)
        return t - slow_duration * (1 - 1 / self.slowdown)

    def factor(self, seconds):
        t = np.asarray(seconds)
        end = np.inf if self.realtime_after is None else self.realtime_after
        return np.where((t >= self.realtime_before) & (t < end), self.slowdown, 1.0)

    def sections(self, timestamps):
        factors = self.factor(timestamps)
        cuts = np.r_[0, np.flatnonzero(np.diff(factors)) + 1, len(factors)]
        return [(int(a), int(b), float(factors[a])) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]
