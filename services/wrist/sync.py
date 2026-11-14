"""Line the wrist sensor up with the video. Owner: Henoch.

Recording routine: start Sensor Logger, then tap the strapped phone twice, sharply, in
view of the camera. Then play. Every racket impact shows up as a sharp spike in the
accelerometer.

1. Spikes: accel minus its 70 ms running median (a high-pass, so the swing's own smooth
   pull and gravity drop out), then peaks above median + K * MAD of that signal.
2. Taps: the first two spikes 0.1 to 1.5 s apart, with the arm still.
3. Impacts: spikes after the taps that happen MID-SWING (forearm turning faster than
   MIN_SWING_DPS within 100 ms). Spikes within 1 s of each other are one swing (the
   biggest wins). A spike with the arm still (a footstep, a knock) is rejected and listed.
4. Alignment: video time + offset = sensor time. The offset comes from the FIRST TAP
   (sensor tap time - the video time you read off for that tap). Impacts are paired with
   the video's contact times IN ORDER (each contact takes the nearest unused impact after
   the previous pair, so one missed swing doesn't shift the rest), and each pair's
   alignment error is impact - (contact + offset). Pairs beyond TOLERANCE_MS are not
   trusted, and metrics.py skips them. Without a video tap time, the offset is fitted to
   the impacts (median) and the k-th impact pairs with the k-th contact, so the errors
   are only residuals of that fit, a weaker check; the report says so.

Metrics use the sensor's own impact time as contact, so a small sync error moves no
number; sync only decides WHICH swing each impact belongs to.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

from wrist.load import Recording

SPIKE_WINDOW_S = 0.07     # high-pass = accel minus its running median over this window
SPIKE_K = 8.0             # spike = high-pass above median + K * MAD
SPIKE_MIN_GAP_S = 0.08    # two spikes closer than this are one
TAP_GAP_S = (0.1, 1.5)    # the two taps are this far apart
TAP_SEARCH_S = 60.0       # and both within the first minute
IMPACT_GUARD_S = 0.5      # impacts start this long after the second tap
SWING_GAP_S = 1.0         # spikes closer than this belong to the same swing
MIN_SWING_DPS = 360.0     # an impact happens mid-swing: forearm turning at least this fast...
SWING_SPEED_WINDOW_S = 0.1  # ...within this long of the spike
TOLERANCE_MS = 100.0      # pairs with a bigger alignment error are not trusted

CONTACT_COLUMNS = ("contact_s", "contact_video_s", "contact_playback_s")


class SyncError(ValueError):
    """Couldn't line the sensor up with the video."""


@dataclass
class Spike:
    t: float          # sensor seconds
    height: float     # high-pass accel magnitude, m/s^2
    gyro_dps: float   # fastest forearm turn within SWING_SPEED_WINDOW_S, deg/s


def spike_signal(rec: Recording) -> np.ndarray:
    """|accel - running median|: sharp knocks stay, the smooth swing and gravity go."""
    w = max(3, int(round(SPIKE_WINDOW_S * rec.rate_hz)) | 1)
    return np.linalg.norm(rec.acc - median_filter(rec.acc, size=(w, 1), mode="nearest"), axis=1)


def find_spikes(rec: Recording, k: float = SPIKE_K) -> list[Spike]:
    hp = spike_signal(rec)
    med = float(np.median(hp))
    mad = float(np.median(np.abs(hp - med))) * 1.4826
    thr = med + k * max(mad, 1e-6)
    peaks, props = find_peaks(hp, height=thr, distance=max(1, int(round(SPIKE_MIN_GAP_S * rec.rate_hz))))
    speed = np.degrees(np.linalg.norm(rec.gyro, axis=1))
    half = int(round(SWING_SPEED_WINDOW_S * rec.rate_hz))
    return [Spike(t=float(rec.t[i]), height=float(h),
                  gyro_dps=float(speed[max(0, i - half): i + half + 1].max()))
            for i, h in zip(peaks, props["peak_heights"])]


def find_taps(spikes: list[Spike], start_t: float = 0.0) -> Optional[tuple[Spike, Spike]]:
    """The first two spikes TAP_GAP_S apart with the arm still, or None."""
    still = [s for s in spikes if s.gyro_dps < MIN_SWING_DPS and s.t <= start_t + TAP_SEARCH_S]
    for a, b in zip(still, still[1:]):
        if TAP_GAP_S[0] <= b.t - a.t <= TAP_GAP_S[1]:
            return a, b
    return None


def find_impacts(spikes: list[Spike], after_t: float) -> tuple[list[Spike], list[dict[str, Any]]]:
    """(impacts in time order, rejected spikes with why). See the module doc."""
    rejected: list[dict[str, Any]] = []
    mid_swing: list[Spike] = []
    for s in spikes:
        if s.t <= after_t:
            continue
        if s.gyro_dps < MIN_SWING_DPS:
            rejected.append({**_r(s), "why": f"arm still ({s.gyro_dps:.0f} deg/s < {MIN_SWING_DPS:.0f})"})
        else:
            mid_swing.append(s)
    groups: list[list[Spike]] = []
    for s in mid_swing:
        if groups and s.t - groups[-1][-1].t < SWING_GAP_S:
            groups[-1].append(s)
        else:
            groups.append([s])
    return [max(g, key=lambda s: s.height) for g in groups], rejected


def _r(s: Spike) -> dict[str, Any]:
    return {k: round(v, 3) for k, v in asdict(s).items()}


def align(impacts_s: list[float], contacts: list[tuple[str, float]], tap_s: Optional[float] = None,
          video_tap_s: Optional[float] = None, video_scale: float = 1.0,
          tolerance_ms: float = TOLERANCE_MS) -> dict[str, Any]:
    """Pair impacts with video contacts in order and report each pair's alignment error.

    contacts: [(swing id, video seconds)]. video_scale: real seconds per video second
    (1.0 unless contact times were read off a slowed-down playback).

    With the first-tap offset, each contact (in time order) takes the nearest impact
    after the last one used, and only uses it up if it's within tolerance: an extra or
    missing swing then spoils only its own pair. Without it, the k-th impact pairs with
    the k-th contact, so one missing swing shifts every pair after it (the errors show it).
    """
    impacts = sorted(impacts_s)
    contacts = sorted(contacts, key=lambda c: c[1])
    n = min(len(impacts), len(contacts))
    from_tap = tap_s is not None and video_tap_s is not None
    if from_tap:
        offset = tap_s - video_tap_s * video_scale
        offset_from = "first tap"
    elif n:
        offset = float(np.median([impacts[k] - contacts[k][1] * video_scale for k in range(n)]))
        offset_from = ("fitted to the impacts (no tap pair to use): errors are residuals of "
                       "that fit, a weaker check than a tap")
    else:
        raise SyncError("no impacts or no video contacts to align")

    def pair(swing: str, video_t: float, impact: float) -> dict[str, Any]:
        err = (impact - (video_t * video_scale + offset)) * 1000
        return {"swing": swing, "impact_s": round(impact, 3), "contact_video_s": round(video_t, 3),
                "error_ms": round(err, 1), "ok": bool(abs(err) <= tolerance_ms)}

    pairs: list[dict[str, Any]] = []
    unpaired_swings: list[str] = []
    if from_tap:
        j = 0  # impacts before j are used up
        for swing, video_t in contacts:
            if j >= len(impacts):
                unpaired_swings.append(swing)
                continue
            k = j + int(np.argmin([abs(t - (video_t * video_scale + offset)) for t in impacts[j:]]))
            pairs.append(pair(swing, video_t, impacts[k]))
            if pairs[-1]["ok"]:
                j = k + 1
    else:
        pairs = [pair(*contacts[k], impacts[k]) for k in range(n)]
        unpaired_swings = [c[0] for c in contacts[n:]]
    used = {p["impact_s"] for p in pairs if p["ok"]}
    errs = np.abs([p["error_ms"] for p in pairs]) if pairs else np.array([])
    return {
        "offset_s": round(offset, 4), "offset_from": offset_from, "video_scale": video_scale,
        "tolerance_ms": tolerance_ms,
        "paired_by": "order, nearest impact to the tap-predicted time" if from_tap else "order (k-th with k-th)",
        "n_impacts": len(impacts), "n_contacts": len(contacts),
        "count_mismatch": len(impacts) != len(contacts),
        "unpaired_swings": unpaired_swings,
        "unpaired_impacts_s": [round(t, 3) for t in impacts if round(t, 3) not in used],
        "error_ms": {"mean_abs": round(float(errs.mean()), 1) if errs.size else None,
                     "max_abs": round(float(errs.max()), 1) if errs.size else None,
                     "n_ok": sum(p["ok"] for p in pairs), "n_pairs": len(pairs)},
        "pairs": pairs,
    }


def synchronise(rec: Recording, contacts: list[tuple[str, float]], video_tap_s: Optional[float] = None,
                video_scale: float = 1.0, k: float = SPIKE_K, tolerance_ms: float = TOLERANCE_MS
                ) -> dict[str, Any]:
    """Taps, impacts and alignment in one report. report["impacts"] = {swing: sensor s} (ok pairs only)."""
    spikes = find_spikes(rec, k)
    taps = find_taps(spikes, float(rec.t[0]))
    after = taps[1].t + IMPACT_GUARD_S if taps else float(rec.t[0])
    impacts, rejected = find_impacts(spikes, after)
    warnings = []
    if taps is None:
        warnings.append("couldn't find the two start taps; offset fitted to the impacts instead")
    elif video_tap_s is None:
        warnings.append("no video tap time given (--video-tap); offset fitted to the impacts instead")
    alignment = align([s.t for s in impacts], contacts, taps[0].t if taps else None,
                      video_tap_s, video_scale, tolerance_ms)
    if alignment["count_mismatch"]:
        how = ("each contact took the nearest impact in order; unmatched ones are listed"
               if alignment["offset_from"] == "first tap" else
               "without a tap, k-th-with-k-th pairing is unreliable after the first missing or extra one")
        warnings.append(f"{alignment['n_impacts']} impacts but {alignment['n_contacts']} video contacts: {how}")
    bad = alignment["error_ms"]["n_pairs"] - alignment["error_ms"]["n_ok"]
    if bad:
        warnings.append(f"{bad} pair(s) off by more than {tolerance_ms:.0f} ms: their wrist metrics are skipped")
    return {
        "taps_s": [round(s.t, 3) for s in taps] if taps else None,
        "video_tap_s": video_tap_s,
        "spike_threshold_k": k,
        "impacts": {p["swing"]: p["impact_s"] for p in alignment["pairs"] if p["ok"]},
        "rejected_spikes": rejected,
        "alignment": alignment,
        "warnings": warnings,
    }


def strip_run(swing: str, run: Optional[str]) -> str:
    return swing[: -len(run) - 1] if run and swing.endswith(f"@{run}") else swing


def read_contacts(path: str | Path, run: Optional[str] = None) -> list[tuple[str, float]]:
    """Video contact times: [(swing id, seconds)], in time order.

    - a CSV with `swing` and one of contact_s / contact_video_s / contact_playback_s
      (data/labels/labels.csv works); with `run`, only rows whose pipeline_run matches,
      and a trailing "@<run>" is dropped from the id so it matches the swing JSON's id.
    - a folder of pipeline swing JSONs: id + metadata.sourceContactSeconds.
    """
    path = Path(path)
    out: list[tuple[str, float]] = []
    if path.is_dir():
        for p in sorted(path.rglob("*.json")):
            try:
                data = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            items = data if isinstance(data, list) else data.get("swings", [data]) if isinstance(data, dict) else []
            for s in items:
                t = (s.get("metadata") or {}).get("sourceContactSeconds") if isinstance(s, dict) else None
                if isinstance(t, (int, float)) and "id" in s:
                    out.append((str(s["id"]), float(t)))
    else:
        with path.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        col = next((c for c in CONTACT_COLUMNS if rows and c in rows[0]), None)
        if col is None or "swing" not in (rows[0] if rows else {}):
            raise SyncError(f"{path}: needs a 'swing' column and one of {CONTACT_COLUMNS}")
        for r in rows:
            if run and r.get("pipeline_run", run) != run:
                continue
            try:
                t = float(r[col])
            except (TypeError, ValueError):
                continue
            out.append((strip_run(r["swing"], run), t))
    if not out:
        raise SyncError(f"{path}: no contact times found")
    return sorted(out, key=lambda c: c[1])
