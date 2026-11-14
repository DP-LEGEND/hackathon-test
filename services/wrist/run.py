"""Sensor Logger export in, per-swing wrist metrics and roll series out. Owner: Henoch.

Run (from inside services/):

    python -m wrist.run ../data/raw/wrist/<export>.zip \
        --contacts ../data/labels/labels.csv --run <pipeline_run> --video-tap 3.21

--contacts: labels.csv (contact_playback_s), any CSV with swing + contact_s, or a folder
of pipeline swing JSONs (metadata.sourceContactSeconds). --video-tap: the video time of
the FIRST tap, on the same clock as the contact times. Without it the offset is fitted
to the impacts and the report says the error check is weaker.

Outputs go to data/raw/wrist/ (git-ignored) unless --out / --series-out say otherwise.
Then coach a swing with its wrist data:

    python -m coach.agent swing.json --wrist ../data/raw/wrist/wrist_metrics.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wrist.load import load_recording
from wrist.metrics import wrist_metrics
from wrist.sync import SPIKE_K, TOLERANCE_MS, read_contacts, synchronise

# Real-data outputs stay out of git by default (data/raw/ is git-ignored).
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "wrist"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-swing forearm roll from a Sensor Logger export.")
    parser.add_argument("export", type=Path, help="Sensor Logger export folder or .zip")
    parser.add_argument("--contacts", type=Path, required=True, help="video contact times (CSV or swing JSON folder)")
    parser.add_argument("--run", help="only contacts from this pipeline_run (labels.csv)")
    parser.add_argument("--video-tap", type=float, help="video seconds of the first tap")
    parser.add_argument("--video-scale", type=float, default=1.0,
                        help="real seconds per video second (1 unless times came from slowed playback)")
    parser.add_argument("--axis", default="y", help="phone axis along the forearm: x, y or z (default y)")
    parser.add_argument("--spike-k", type=float, default=SPIKE_K, help="spike threshold in MADs (default 8)")
    parser.add_argument("--tolerance-ms", type=float, default=TOLERANCE_MS, help="max alignment error (default 100)")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "wrist_metrics.json")
    parser.add_argument("--series-out", type=Path, default=OUT_DIR / "wrist_series.json")
    args = parser.parse_args(argv)

    rec = load_recording(args.export)
    contacts = read_contacts(args.contacts, args.run)
    sync = synchronise(rec, contacts, args.video_tap, args.video_scale, args.spike_k, args.tolerance_ms)
    metrics, series = wrist_metrics(rec, sync, args.axis)
    for path in (args.out, args.series_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2, allow_nan=False))
    args.series_out.write_text(json.dumps(series, separators=(",", ":"), allow_nan=False))

    a = sync["alignment"]
    usable = sum(1 for s in metrics["swings"].values() if s["usable"])
    print(("MOCK DATA. " if rec.mock else "") + f"{rec.rate_hz:.0f} Hz, {rec.t[-1] - rec.t[0]:.0f} s recorded.")
    print(f"Taps at {sync['taps_s']} s; {a['n_impacts']} impacts vs {a['n_contacts']} video contacts; "
          f"offset {a['offset_s']} s from the {a['offset_from']}.")
    e = a["error_ms"]
    print(f"Alignment error: mean {e['mean_abs']} ms, max {e['max_abs']} ms; "
          f"{e['n_ok']}/{e['n_pairs']} pairs within {a['tolerance_ms']:.0f} ms.")
    q = metrics["sensor"]["quaternion"]
    print(f"Quaternions are {q['convention']} (gyro mismatch {q['mismatch']:.2f}).")
    for w in metrics["warnings"]:
        print(f"WARNING: {w}")
    print(f"{usable}/{len(metrics['swings'])} swings usable.")
    for swing, s in metrics["swings"].items():
        if s["usable"]:
            print(f"  {swing}: roll {s['roll_change_deg']:+.1f} deg, roll rate {s['peak_roll_rate_dps']:+d} deg/s, "
                  f"speed {s['peak_angular_speed_dps']} deg/s (sync {s['align_error_ms']:+.0f} ms)")
        else:
            print(f"  {swing}: skipped, {s['skip_reason']}")
    print(f"Wrote {args.out} and {args.series_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
