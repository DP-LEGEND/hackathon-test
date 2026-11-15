"""Shadow-swing sessions: blocks of swings with no ball. Owner: Henoch.

Everything here is an ESTIMATE, labelled "ESTIMATE (sensor)" ("MOCK (sensor)" on synthetic
data). Code measures, Claude explains: quote these numbers with that label, never improve
on them.

Recording routine: start Sensor Logger, then for each block of one stroke (e.g. good
backhand drives, then backhands with a rolled wrist) tap the strapped phone two or more
times, sharply, in view of the camera, then swing. With no ball there's no impact spike to
time contact, and no per-swing video contact marks either, so everything comes from the
sensor:

1. Tap events (find_tap_events): runs of taps. A tap is a spike (sync.find_spikes) at least
   MIN_TAP_G high with the arm still (turning slower than sync.MIN_SWING_DPS); neighbouring
   taps are at most TAP_GAP_S[1] apart; spikes closer than TAP_MERGE_S are one tap (the
   bigger wins). A tap's time is its ONSET, the first sample of the knock (back from the
   peak while the spike signal stays above TAP_ONSET_G, at most TAP_ONSET_S): that's when
   the hand meets the phone, the frame a video shows. The peak is often the phone's rebound
   10-20 ms later (the first real session: the screen-normal push first, then the wobble),
   which is 1-2 frames of a 120 fps clip. Each event's FIRST tap is the one matched to the
   video.
2. Video clock (fit_video_clock): sensor seconds = video seconds x scale + offset, from the
   first tap of each event matched IN ORDER with the video times read off for them. Two or
   more events fit the scale too (a 4x slow-motion render gives about 0.25), and the
   residuals say how well the taps agree. One event needs the scale given.
3. Swings (find_shadow_swings): peaks of the forearm's smoothed turn rate (tempo.speed_dps)
   in a block, at least SWING_GAP_S apart, above sync.MIN_SWING_DPS and at least
   SWING_PEAK_FRACTION of a swing-sized peak: the block's SWING_REFERENCE_PCT percentile.
   The recovery after a swing is a smaller bump; when it comes SWING_GAP_S or more after
   the swing, both reach this filter, and with one recovery per swing the median would sit
   between them and keep every recovery. A swing has at most one recovery, so recoveries
   are at most half the peaks and the 75th percentile is a swing's. CONTACT IS AN ESTIMATE: with no ball, a swing's contact is its fastest
   turn (contact_source "gyro peak"), and the metrics' window (-150..+100 ms) sits on it.
   Where real contact falls relative to that peak is unknown, and for a forehand the roll
   in the window depends on it (the swing part peaks 50-80 ms before the total turn rate
   on the first real session), so compare blocks with each other, not with thresholds
   tuned on hit swings.
4. Numbers (shadow_report): metrics.wrist_report on those contacts, so each swing gets the
   same entry as a real hit (roll, roll rate, angular speed, tempo, racket speed's rotation
   part; impact null), plus "segment". summarise() gives per block the mean, sample SD, min
   and max of each number, and per stroke how each faulty block compares with the good
   one: difference of means, Cohen's d (pooled SD) and AUC, the share of (faulty, good)
   swing pairs where the faulty swing's number is bigger (1.0 or 0.0 = the blocks don't
   overlap at all, 0.5 = no separation).

Racket speed: with no camera swing it has no value (fuse.racket_speed). What the sensor
alone gives is rotationMs, the gyro x lever part (the racket head's speed relative to the
wrist), and the summary reports that, named as such. The camera adds the wrist's own speed.

Segments CSV, one row per block in time order: segment, stroke (forehand/backhand), fault
("none" for a good block, e.g. "rolled_wrist"), and either start_s,end_s (sensor seconds)
or video_start_s,video_end_s (video seconds, mapped with the fitted clock). A blank end
runs to the next block's start (or the end of the recording). Each block needs its own
name (swing ids are <segment>-01, ...), and blocks may not overlap or run out of order:
either would count one swing twice or mislabel it, so both are refused.

Run (from inside services/; outputs default to data/raw/wrist/, git-ignored):

    python -m wrist.shadow ../data/raw/wrist/<export>.zip --segments segments.csv \
        --video-taps 140.333,279.550,377.400,503.967

(--video-taps: the playback second of the frame where the hand first touches the phone,
for each event's first tap.)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
from scipy.signal import find_peaks

from physics.compare import SENSOR_LABEL, SENSOR_MOCK_LABEL
from wrist.fuse import LEVER_M
from wrist.impact import G
from wrist.load import Recording, load_recording
from wrist.metrics import wrist_report
from wrist.sync import (
    MIN_SWING_DPS, SPIKE_K, SWING_GAP_S, TAP_GAP_S, TOLERANCE_MS, Spike, find_spikes, spike_signal,
)
from wrist.tempo import speed_dps

MIN_TAP_G = 0.5            # a tap knocks at least this hard (the first real session's: 0.7-3.4 g)
TAP_MERGE_S = 0.1          # spikes closer than this are one tap (the knock and its ringing)
TAP_ONSET_G = 0.3          # a tap starts at the first sample of its knock above this...
TAP_ONSET_S = 0.05         # ...at most this long before its peak
SWING_PEAK_FRACTION = 0.5  # a swing peaks at least this fraction of a swing-sized peak...
SWING_REFERENCE_PCT = 75   # ...this percentile of the block's peaks (recoveries are at most half)
STROKES = ("forehand", "backhand")

# Summary numbers: entry key -> (unit, what it is). racket_rotation_ms is
# racket_speed_sensor.rotationMs, the only racket-speed part the sensor gives alone.
SUMMARY_KEYS = {
    "roll_change_deg": ("deg", "forearm roll through contact (-150..+100 ms), signed"),
    "roll_change_abs_deg": ("deg", "forearm roll through contact, size"),
    "peak_roll_rate_abs_dps": ("deg/s", "fastest forearm roll rate in the window"),
    "peak_angular_speed_dps": ("deg/s", "fastest forearm turn rate in the window"),
    "racket_rotation_ms": ("m/s", "racket speed, rotation part only: gyro x lever, no camera"),
}
COMPARE_KEYS = ("roll_change_abs_deg", "peak_roll_rate_abs_dps", "peak_angular_speed_dps", "racket_rotation_ms")

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "wrist"


def tap_onset(rec: Recording, peak_t: float, signal: Optional[np.ndarray] = None) -> float:
    """When a knock peaking at peak_t began (module doc, step 1)."""
    hp = spike_signal(rec) if signal is None else signal
    i = int(np.argmin(np.abs(rec.t - peak_t)))
    first = i
    while first > 0 and rec.t[i] - rec.t[first - 1] <= TAP_ONSET_S + 1e-9 and hp[first - 1] >= TAP_ONSET_G * G:
        first -= 1
    return float(rec.t[first])


def find_tap_events(rec: Recording, spikes: Optional[list[Spike]] = None) -> list[dict[str, Any]]:
    """Every run of two or more taps, in time order, timed by onset (module doc, step 1)."""
    spikes = find_spikes(rec) if spikes is None else spikes
    hp = spike_signal(rec)
    taps: list[Spike] = []
    for s in spikes:
        if s.gyro_dps >= MIN_SWING_DPS or s.height < MIN_TAP_G * G:
            continue
        if taps and s.t - taps[-1].t < TAP_MERGE_S:
            if s.height > taps[-1].height:
                taps[-1] = s
            continue
        taps.append(s)
    runs: list[list[Spike]] = []
    for s in taps:
        if runs and s.t - runs[-1][-1].t <= TAP_GAP_S[1]:
            runs[-1].append(s)
        else:
            runs.append([s])
    events = []
    for r in runs:
        if len(r) < 2:
            continue
        onsets = [round(tap_onset(rec, s.t, hp), 3) for s in r]
        events.append({"t_s": onsets[0], "taps_s": onsets, "peaks_s": [round(s.t, 3) for s in r],
                       "heights_g": [round(s.height / G, 2) for s in r], "n_taps": len(r)})
    return events


def fit_video_clock(video_s: Sequence[float], sensor_s: Sequence[float],
                    scale: Optional[float] = None) -> dict[str, Any]:
    """sensor seconds = video seconds x scale + offset, from matched tap times (module doc, step 2)."""
    v, s = np.asarray(video_s, float), np.asarray(sensor_s, float)
    if v.size == 0 or v.size != s.size:
        raise ValueError(f"need matching tap times, got {v.size} video and {s.size} sensor")
    if scale is None:
        if v.size < 2:
            raise ValueError("one tap event can't fit the scale: give it (0.25 for a 4x slow-motion render)")
        scale_f, offset = (float(x) for x in np.polyfit(v, s, 1))
        fitted = "scale and offset fitted to the taps"
    else:
        scale_f = float(scale)
        offset = float(np.mean(s - scale_f * v))
        fitted = "offset fitted to the taps, scale given"
    res = (s - (scale_f * v + offset)) * 1000
    return {"scale": scale_f, "offset_s": offset, "fitted": fitted, "n_taps": int(v.size),
            "video_s": [round(float(x), 3) for x in v], "sensor_s": [round(float(x), 3) for x in s],
            "residuals_ms": [round(float(r), 1) for r in res], "max_abs_residual_ms": round(float(np.abs(res).max()), 1)}


def to_sensor(video_t: float, clock: dict[str, Any]) -> float:
    return float(video_t) * clock["scale"] + clock["offset_s"]


def find_shadow_swings(rec: Recording, start_s: float, end_s: float,
                       speed: Optional[np.ndarray] = None) -> list[float]:
    """Contact ESTIMATES (sensor seconds) of the swings in [start_s, end_s) (module doc, step 3)."""
    s = speed_dps(rec) if speed is None else speed
    idx = np.flatnonzero((rec.t >= start_s) & (rec.t < end_s))
    if idx.size < 3:
        return []
    peaks, _ = find_peaks(s[idx], height=MIN_SWING_DPS, distance=max(1, int(round(SWING_GAP_S * rec.rate_hz))))
    if not peaks.size:
        return []
    heights = s[idx][peaks]
    keep = peaks[heights >= SWING_PEAK_FRACTION * float(np.percentile(heights, SWING_REFERENCE_PCT))]
    return [round(float(rec.t[idx[k]]), 3) for k in keep]


def read_segments(path: str | Path) -> list[dict[str, Any]]:
    """Blocks from the segments CSV (module doc), in file order. Segment names must be unique."""
    with Path(path).open(newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [(reader.line_num, raw) for raw in reader]  # line_num: the CSV line, blank lines counted
    out: list[dict[str, Any]] = []
    line_of: dict[str, int] = {}
    for n, raw in rows:
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not r.get("segment"):
            raise ValueError(f"{path}:{n}: every row needs a segment name")
        if r["segment"] in line_of:  # swing ids are <segment>-NN: a reused name overwrites swings
            raise ValueError(f"{path}: segment {r['segment']!r} is used twice: lines {line_of[r['segment']]} "
                             f"and {n}; give each block a unique name")
        line_of[r["segment"]] = n
        stroke = r.get("stroke") or None
        if stroke is not None and stroke not in STROKES:
            raise ValueError(f"{path}:{n}: stroke must be one of {STROKES}, got {stroke!r}")
        seg: dict[str, Any] = {"segment": r["segment"], "stroke": stroke, "fault": r.get("fault") or "none"}
        for key in ("start_s", "end_s", "video_start_s", "video_end_s"):
            try:
                seg[key] = float(r[key]) if r.get(key) else None
            except ValueError as e:
                raise ValueError(f"{path}:{n}: {key} must be a number, got {r[key]!r}") from e
        if seg["start_s"] is None and seg["video_start_s"] is None:
            raise ValueError(f"{path}:{n}: give start_s (sensor) or video_start_s (video)")
        out.append(seg)
    if not out:
        raise ValueError(f"{path}: no segments")
    return out


def place_segments(segments: list[dict[str, Any]], rec: Recording,
                   clock: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Every block with sensor start_s/end_s: video times mapped with `clock`, blank ends run on.

    Refuses blocks out of time order (start_s not increasing) and overlapping blocks (one's end
    past the next one's start): a swing in both would be found twice under two labels.
    """
    placed = []
    for seg in segments:
        s = dict(seg)
        for k in ("start", "end"):
            if s.get(f"{k}_s") is None and s.get(f"video_{k}_s") is not None:
                if clock is None:
                    raise ValueError(f"segment {s['segment']!r}: video times need the video clock (--video-taps)")
                s[f"{k}_s"] = round(to_sensor(s[f"video_{k}_s"], clock), 3)
        placed.append(s)
    # Order first: a blank end runs to the next start, so an out-of-order pair would otherwise
    # only show up as "ends before it starts".
    for a, b in zip(placed, placed[1:]):
        if b["start_s"] <= a["start_s"]:
            raise ValueError(f"segments {a['segment']!r} (starts {a['start_s']} s) and {b['segment']!r} "
                             f"(starts {b['start_s']} s) are out of order: list the blocks in time order, "
                             "each starting after the one before")
    for a, b in zip(placed, placed[1:] + [None]):
        if a.get("end_s") is None:
            a["end_s"] = b["start_s"] if b is not None else float(rec.t[-1])
        if a["end_s"] <= a["start_s"]:
            raise ValueError(f"segment {a['segment']!r} ends before it starts ({a['start_s']} .. {a['end_s']} s)")
    for a, b in zip(placed, placed[1:]):
        if a["end_s"] > b["start_s"]:
            raise ValueError(f"segments {a['segment']!r} ({a['start_s']} .. {a['end_s']} s) and {b['segment']!r} "
                             f"({b['start_s']} .. {b['end_s']} s) overlap by {a['end_s'] - b['start_s']:.3f} s: "
                             "a swing in both would be counted twice; end each block before the next starts")
    return placed


def shadow_sync(rec: Recording, segments: list[dict[str, Any]],
                taps: Optional[list[dict[str, Any]]] = None) -> tuple[dict[str, Any], dict[str, str]]:
    """(a sync report metrics.wrist_report reads, {swing id: segment}) for placed blocks."""
    speed = speed_dps(rec)
    gyro_peak, seg_of = [], {}
    for seg in segments:
        for k, t in enumerate(find_shadow_swings(rec, seg["start_s"], seg["end_s"], speed), 1):
            sid = f"{seg['segment']}-{k:02d}"
            gyro_peak.append({"swing": sid, "contact_s": t, "segment": seg["segment"]})
            seg_of[sid] = seg["segment"]
    sync = {
        "taps_s": taps[0]["taps_s"] if taps else None,  # a still stretch for the gyro-bias fallback
        "video_tap_s": None, "spike_threshold_k": SPIKE_K, "impacts": {}, "tap_only": {}, "rejected_spikes": [],
        "alignment": {"pairs": [], "unpaired_swings": [], "tap_only": [], "gyro_peak": gyro_peak,
                      "tolerance_ms": TOLERANCE_MS, "offset_from": "none: shadow session, contact = gyro peak"},
        "warnings": ["shadow session: no impacts, so each swing's contact is its fastest forearm turn (ESTIMATE)"],
    }
    return sync, seg_of


def _stats(v: np.ndarray) -> dict[str, Any]:
    if not v.size:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    return {"n": int(v.size), "mean": round(float(v.mean()), 1),
            "sd": round(float(v.std(ddof=1)), 1) if v.size > 1 else None,
            "min": round(float(v.min()), 1), "max": round(float(v.max()), 1)}


def _auc(faulty: np.ndarray, good: np.ndarray) -> float:
    """Share of (faulty, good) pairs where the faulty swing's number is bigger; ties count half."""
    d = faulty[:, None] - good[None, :]
    return float(((d > 0).sum() + 0.5 * (d == 0).sum()) / d.size)


def _value(entry: dict[str, Any], key: str) -> Optional[float]:
    v = (entry.get("racket_speed_sensor") or {}).get("rotationMs") if key == "racket_rotation_ms" else entry.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def summarise(metrics: dict[str, Any], segments: list[dict[str, Any]], seg_of: dict[str, str]) -> dict[str, Any]:
    """Per block statistics and per stroke good-vs-fault comparisons (module doc, step 4)."""
    values = {s["segment"]: {k: [] for k in SUMMARY_KEYS} for s in segments}
    found = {s["segment"]: 0 for s in segments}
    for sid, entry in metrics["swings"].items():
        seg = seg_of.get(sid)
        if seg is None:
            continue
        found[seg] += 1
        if entry.get("usable"):
            for k in SUMMARY_KEYS:
                v = _value(entry, k)
                if v is not None:
                    values[seg][k].append(v)
    blocks = [{"segment": s["segment"], "stroke": s["stroke"], "fault": s["fault"],
               "start_s": s["start_s"], "end_s": s["end_s"], "n_swings": found[s["segment"]],
               "numbers": {k: _stats(np.array(values[s["segment"]][k])) for k in SUMMARY_KEYS}}
              for s in segments]
    comparisons = []
    for stroke in STROKES:
        good = [s for s in segments if s["stroke"] == stroke and s["fault"] == "none"]
        faulty = [s for s in segments if s["stroke"] == stroke and s["fault"] != "none"]
        for g in good:
            for f in faulty:
                for k in COMPARE_KEYS:
                    a, b = np.array(values[f["segment"]][k]), np.array(values[g["segment"]][k])
                    if a.size < 2 or b.size < 2:
                        continue
                    diff = float(a.mean() - b.mean())
                    pooled = math.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1))
                                       / (a.size + b.size - 2))
                    comparisons.append({
                        "stroke": stroke, "fault": f["fault"], "good_segment": g["segment"],
                        "fault_segment": f["segment"], "number": k, "unit": SUMMARY_KEYS[k][0],
                        "difference": round(diff, 1), "cohens_d": round(diff / pooled, 2) if pooled > 0 else None,
                        "auc": round(_auc(a, b), 3),
                        "overlap": bool(a.min() <= b.max() and b.min() <= a.max())})
    return {
        "label": SENSOR_MOCK_LABEL if metrics.get("mock") else SENSOR_LABEL,
        "contact": "gyro peak (ESTIMATE): each swing's fastest forearm turn; there is no ball",
        "numbers": {k: {"unit": u, "what": w} for k, (u, w) in SUMMARY_KEYS.items()},
        "auc": "share of (faulty, good) swing pairs where the faulty swing's number is bigger: "
               "1.0 or 0.0 = no overlap, 0.5 = no separation",
        "blocks": blocks, "comparisons": comparisons,
    }


def shadow_report(rec: Recording, segments: list[dict[str, Any]], axis: str = "y", lever_m: float = LEVER_M,
                  taps: Optional[list[dict[str, Any]]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """(metrics JSON with a "shadow" summary, series JSON) for placed blocks (place_segments)."""
    sync, seg_of = shadow_sync(rec, segments, taps)
    metrics, series, _ = wrist_report(rec, sync, axis, None, lever_m)
    for sid, entry in metrics["swings"].items():
        entry["segment"] = seg_of.get(sid)
    metrics["shadow"] = summarise(metrics, segments, seg_of)
    return metrics, series


def _cell(st: dict[str, Any]) -> str:
    """mean ± sample SD; the SD is n/a for one swing (it can't be computed), never 0."""
    if st["mean"] is None:
        return "n/a"
    return f"{st['mean']:.1f} ± " + ("n/a" if st["sd"] is None else f"{st['sd']:.1f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shadow-swing session: taps, swings and per-block wrist ESTIMATES.")
    parser.add_argument("export", type=Path, help="Sensor Logger export folder or .zip")
    parser.add_argument("--segments", type=Path, required=True,
                        help="CSV: segment, stroke, fault, and start_s/end_s or video_start_s/video_end_s")
    parser.add_argument("--video-taps", help="video seconds of each tap event's FIRST tap, comma-separated, in order")
    parser.add_argument("--video-scale", type=float,
                        help="real seconds per video second, if not fitted from the taps (0.25 for a 4x slow render)")
    parser.add_argument("--axis", default="y", help="phone axis along the forearm (default y)")
    parser.add_argument("--lever", type=float, default=LEVER_M, help=f"ESTIMATE: wrist to sweet spot, m ({LEVER_M:g})")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "shadow_metrics.json")
    parser.add_argument("--series-out", type=Path, default=OUT_DIR / "shadow_series.json")
    args = parser.parse_args(argv)

    rec = load_recording(args.export)
    taps = find_tap_events(rec)
    clock = None
    if args.video_taps:
        video = [float(x) for x in args.video_taps.split(",") if x.strip()]
        if len(video) > len(taps):
            parser.error(f"{len(video)} video taps but only {len(taps)} tap events in the sensor")
        clock = fit_video_clock(video, [e["t_s"] for e in taps[:len(video)]], args.video_scale)
    segments = place_segments(read_segments(args.segments), rec, clock)
    metrics, series = shadow_report(rec, segments, args.axis, args.lever, taps)
    metrics["shadow"]["tap_events"] = taps
    metrics["shadow"]["video_clock"] = clock
    for path in (args.out, args.series_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2, allow_nan=False))
    args.series_out.write_text(json.dumps(series, separators=(",", ":"), allow_nan=False))

    sh = metrics["shadow"]
    print(("MOCK DATA. " if rec.mock else "") + f"Shadow session: {rec.rate_hz:.0f} Hz, {rec.t[-1] - rec.t[0]:.1f} s. "
          f"All numbers {sh['label']}; contact = each swing's fastest forearm turn (no ball).")
    print(f"Tap events: {len(taps)} at " + ", ".join(f"{e['t_s']:.3f} s ({e['n_taps']} taps)" for e in taps))
    if clock:
        print(f"Video clock: sensor = video x {clock['scale']:.5f} {clock['offset_s']:+.3f} s ({clock['fitted']}); "
              f"tap residuals {clock['residuals_ms']} ms")
    for w in metrics["warnings"]:
        print(f"WARNING: {w}")
    print(f"{'block':<14}{'stroke':<10}{'fault':<14}{'swings':>6}  {'roll deg':>14}  {'|roll| deg':>14}  "
          f"{'roll rate dps':>14}  {'turn dps':>14}  {'racket rot. m/s':>15}")
    for b in sh["blocks"]:
        n = b["numbers"]
        print(f"{b['segment']:<14}{b['stroke'] or '-':<10}{b['fault']:<14}{b['n_swings']:>6}  "
              f"{_cell(n['roll_change_deg']):>14}  {_cell(n['roll_change_abs_deg']):>14}  "
              f"{_cell(n['peak_roll_rate_abs_dps']):>14}  {_cell(n['peak_angular_speed_dps']):>14}  "
              f"{_cell(n['racket_rotation_ms']):>15}")
    for c in sh["comparisons"]:
        print(f"  {c['stroke']} {c['fault']} vs good, {c['number']}: {c['difference']:+.1f} {c['unit']}, "
              f"d {c['cohens_d']}, AUC {c['auc']:.2f}, {'overlap' if c['overlap'] else 'no overlap'}")
    print(f"Wrote {args.out} and {args.series_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
