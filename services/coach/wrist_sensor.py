"""Wrist-sensor numbers for the coach. Owner: Henoch (with aryan and Dev's OK for coach/).

The camera can't see forearm roll, so rolled_wrist only exists when a phone was strapped
to the forearm. services/wrist turns that recording into wrist_metrics.json; a swing
carries its own entry as the optional field swing["wrist"] (attach_wrist does it).

Only an entry marked "usable" is read. Anything else (no sensor, sync off, orientation
failing the gyro check, a missing number) leaves every wrist-sensor measurement None, so
rolled_wrist is skipped and listed in not_measured, never guessed. wrist_sensor_skipped
says why.
"""

from __future__ import annotations

import math
from typing import Any, Optional

# wrist_metrics.json key -> coach measurement name (coach/faults.py MEASUREMENTS)
FROM_WRIST = {
    "roll_change_abs_deg": "forearm_roll_deg",
    "peak_roll_rate_abs_dps": "forearm_roll_rate_dps",
    "peak_angular_speed_dps": "forearm_speed_dps",
}
NO_SENSOR = "no wrist sensor data for this swing"


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def sensor_metrics(wrist: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The coach's wrist-sensor measurements for one swing (None where not measured).

    wrist_sensor: "sensor", "mock sensor" (synthetic data: say so on screen) or None.
    """
    out: dict[str, Any] = {name: None for name in FROM_WRIST.values()}
    out["wrist_sensor"] = None
    if not isinstance(wrist, dict):
        out["wrist_sensor_skipped"] = NO_SENSOR
        return out
    if not wrist.get("usable"):
        out["wrist_sensor_skipped"] = wrist.get("skip_reason") or "wrist data marked unusable"
        return out
    missing = [k for k in FROM_WRIST if not _finite(wrist.get(k))]
    if missing:
        out["wrist_sensor_skipped"] = f"wrist data has no {', '.join(missing)}"
        return out
    for key, name in FROM_WRIST.items():
        out[name] = float(wrist[key])
    out["wrist_sensor"] = "mock sensor" if wrist.get("mock") else "sensor"
    out["wrist_sensor_skipped"] = None
    return out


def attach_wrist(swing: dict[str, Any], wrist_metrics: dict[str, Any]) -> dict[str, Any]:
    """A copy of swing with swing["wrist"] = its entry in wrist_metrics.json (by swing id).

    A swing missing from the file gets an unusable entry saying so, so the skip is visible.
    """
    entry = (wrist_metrics.get("swings") or {}).get(str(swing.get("id")))
    if entry is None:
        entry = {"usable": False, "skip_reason": f"swing {swing.get('id')!r} isn't in the wrist file"}
    return {**swing, "wrist": entry}
