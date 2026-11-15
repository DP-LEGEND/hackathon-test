"""Sensor Logger export in, per-swing wrist metrics and roll series out. Owner: Henoch.

Run (from inside services/):

    python -m wrist.run ../data/raw/wrist/<export>.zip \
        --contacts ../data/labels/labels.csv --run <pipeline_run> --video-tap 3.21

--contacts: labels.csv (contact_playback_s), any CSV with swing + contact_s, or a folder
of pipeline swing JSONs (metadata.sourceContactSeconds). --video-tap: the video time of
the FIRST tap, on the same clock as the contact times. Without it the offset is fitted
to the impacts and the report says the error check is weaker.

--swings: the pipeline swing JSONs (default: --contacts when it's a folder). With them you
also get the camera fusion ESTIMATES: racket speed (camera wrist velocity + gyro x --lever)
and the occlusion fill. Every camera swing is then written to --swings-out with its wrist
entry attached as swing["wrist"] (and the fill applied where it was), ready for the coach
and for physics' compare(), which prefers the sensor's racket speed.

Outputs go to data/raw/wrist/ (git-ignored) unless --out / --series-out / --swings-out say
otherwise. Then coach or compare a swing with its wrist data:

    python -m coach.agent ../data/raw/wrist/swings/<id>.json
    python -m physics.compare ../data/raw/wrist/swings/<id>.json turn_shoulders_less 15 --no-swings
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from wrist.fuse import LEVER_M, attach_wrist_entries, read_swings
from wrist.load import load_recording
from wrist.metrics import wrist_report
from wrist.sync import SPIKE_K, TOLERANCE_MS, read_contacts, synchronise

# Real-data outputs stay out of git by default (data/raw/ is git-ignored).
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "wrist"


def _ms(v: object) -> str:
    return "?" if v is None else f"{v:+.0f}"


def _estimates(s: dict) -> list[str]:
    """One swing's ESTIMATES as short phrases for the terminal."""
    r, im, tp, fill = s["racket_speed_sensor"], s["impact"], s["tempo"], s["occlusion_fill"]
    racket = (f"racket {r['value']} m/s {r['label']} ({'vectors' if 'vectors' in r['method'] else 'parallel'})"
              if r["value"] is not None else f"racket rotation part {r['rotationMs']} m/s (no camera)")
    impact = (f"impact {im['peak_g']} g, ring-down {im['ring_down_ms']:.0f} ms"
              f"{'+' if im['ring_down_capped'] else ''} (not judged)" if im else "no impact (shadow swing)")
    tempo = (f"tempo {_ms(tp['backswing_start_ms'])} / {_ms(tp['forward_start_ms'])} / 0 / "
             f"{_ms(tp['follow_through_end_ms'])} ms, backswing to contact {_ms(tp['backswing_to_contact_ms'])} ms")
    if fill["applied"]:
        hold = fill["holdout_deg"]
        filled = (f"filled {fill['joints'][0]} on {len(fill['frames'])} frames, agreement "
                  f"{fill['agreement_deg']['median']} deg" + (f", holdout {hold['median']} deg" if hold else ""))
    else:
        filled = f"no fill: {fill['reason']}"
    return [racket, impact, tempo, filled]


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
    parser.add_argument("--swings", type=Path,
                        help="pipeline swing JSON folder for the camera fusion (default: --contacts if a folder)")
    parser.add_argument("--lever", type=float, default=LEVER_M,
                        help=f"ESTIMATE: wrist joint to the racket's sweet spot, m (default {LEVER_M:g})")
    parser.add_argument("--out", type=Path, default=OUT_DIR / "wrist_metrics.json")
    parser.add_argument("--series-out", type=Path, default=OUT_DIR / "wrist_series.json")
    parser.add_argument("--swings-out", "--filled-out", dest="swings_out", type=Path, default=OUT_DIR / "swings",
                        help="folder for every camera swing with swing['wrist'] attached and the fill applied")
    args = parser.parse_args(argv)

    rec = load_recording(args.export)
    contacts = read_contacts(args.contacts, args.run)
    sync = synchronise(rec, contacts, args.video_tap, args.video_scale, args.spike_k, args.tolerance_ms)
    swings_path = args.swings or (args.contacts if args.contacts.is_dir() else None)
    swings = read_swings(swings_path) if swings_path else None
    metrics, series, filled = wrist_report(rec, sync, args.axis, swings, args.lever)
    for path in (args.out, args.series_out):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(metrics, indent=2, allow_nan=False))
    args.series_out.write_text(json.dumps(series, separators=(",", ":"), allow_nan=False))
    attached = attach_wrist_entries(swings, metrics, filled) if swings else {}
    if attached:
        args.swings_out.mkdir(parents=True, exist_ok=True)
        for sid, swing in attached.items():
            (args.swings_out / f"{sid}.json").write_text(json.dumps(swing, separators=(",", ":"), allow_nan=False))

    a = sync["alignment"]
    usable = sum(1 for s in metrics["swings"].values() if s["usable"])
    print(("MOCK DATA. " if rec.mock else "") + f"{rec.rate_hz:.0f} Hz, {rec.t[-1] - rec.t[0]:.0f} s recorded.")
    print(f"Taps at {sync['taps_s']} s; {a['n_impacts']} impacts vs {a['n_contacts']} video contacts; "
          f"offset {a['offset_s']} s from the {a['offset_from']}.")
    e = a["error_ms"]
    print(f"Alignment error: mean {e['mean_abs']} ms, max {e['max_abs']} ms; "
          f"{e['n_ok']}/{e['n_pairs']} pairs within {a['tolerance_ms']:.0f} ms.")
    if a.get("tap_only"):
        print(f"{len(a['tap_only'])} swing(s) with no impact, timed from the double tap.")
    o = metrics["sensor"]["orientation_used"]
    if o["source"] == "phone":
        q = metrics["sensor"]["quaternion"]
        b = o["gyro_bias"]
        print(f"Orientation: the phone's, quaternions {q['convention']} (gyro mismatch {q['mismatch']:.2f}); "
              + (f"gyro bias {b['bias_dps']} deg/s removed from the roll (against the phone's orientation)."
                 if b["bias_dps"] is not None else "gyro bias not removed (too few samples)."))
    else:
        print(f"Orientation: integrated gyro, bias {o['bias_dps']} deg/s removed {o['bias_from']}.")
    for w in metrics["warnings"]:
        print(f"WARNING: {w}")
    print(f"{usable}/{len(metrics['swings'])} swings usable.")
    for swing, s in metrics["swings"].items():
        if s["usable"]:
            sync_note = (f"sync {s['align_error_ms']:+.0f} ms" if s["align_error_ms"] is not None
                         else "no impact: contact from the double tap")
            print(f"  {swing}: roll {s['roll_change_deg']:+.1f} deg, roll rate {s['peak_roll_rate_dps']:+d} deg/s, "
                  f"speed {s['peak_angular_speed_dps']} deg/s ({sync_note})")
        else:
            print(f"  {swing}: skipped, {s['skip_reason']}")
        if "tempo" in s:
            print("      ESTIMATES: " + "; ".join(_estimates(s)))
    if swings is not None:
        print(f"{len(swings)} camera swings read from {swings_path}.")
    print(f"Wrote {args.out} and {args.series_out}")
    if attached:
        print(f"Wrote {len(attached)} swings with swing['wrist'] to {args.swings_out} "
              f"({len(filled)} with the forearm filled from the sensor)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
