"""Optional, fail-soft tap-synced wrist data for the multi-upload endpoint.

Flat CSV contract: seconds_elapsed (seconds) or time (Unix nanoseconds),
accel_x/y/z in m/s² and gyro_x/y/z in rad/s. ax/ay/az and gx/gy/gz are accepted
aliases. Optional qx/qy/qz/qw and mock retain Sensor Logger provenance. The
phone's long edge (y) must lie along the hitting forearm, as in wrist/README.md.
No clocks are fitted to ball impacts: an unambiguous audible double tap is
required, otherwise the optional sensor data is ignored. Sensor Logger ZIPs use
the same native reader as scripts/make_sensor_sample.py.
"""
from __future__ import annotations

import copy
import csv
import io
import math
from pathlib import Path
import shutil
import tempfile
import zipfile

import numpy as np

from pipeline.live import playback_hits_to_real
from pipeline.segment import audio_hits
from pipeline.video import VideoInfo, probe_video, run_tool, tool
from wrist.fuse import attach_wrist_entries
from wrist.load import Recording, load_recording
from wrist.metrics import wrist_report
from wrist.shadow import find_shadow_swings, find_tap_events
from wrist.sync import (IMPACT_GUARD_S, MIN_SWING_DPS, TOLERANCE_MS, align,
                        find_impacts, find_spikes)

MAX_SENSOR_BYTES = 25 * 1024 * 1024
MAX_SENSOR_ROWS = 500_000
TAP_GAP_TOLERANCE_S = 0.04
GYRO_PEAK_SEARCH_S = 0.3


def is_sensor_zip(path: Path) -> bool:
    """Recognize ZIP exports independently of their multipart filename/MIME type."""
    if path.suffix.lower() == ".zip":
        return True
    with path.open("rb") as stream:
        return stream.read(4) in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _zip_recording(path: Path, work: Path) -> Recording:
    """Bound archive expansion and the native reader's resampling allocation."""
    if path.stat().st_size > MAX_SENSOR_BYTES:
        raise ValueError("sensor ZIP exceeds 25 MB")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 128 or sum(member.file_size for member in members) > MAX_SENSOR_BYTES:
            raise ValueError("sensor ZIP expands beyond the sensor data limit")
        tables = {Path(member.filename).stem.lower(): member for member in members
                  if member.filename.lower().endswith(".csv")}
        accel = tables.get("accelerometer") or tables.get("totalacceleration")
        if accel is None:
            raise ValueError("sensor ZIP needs Accelerometer.csv or TotalAcceleration.csv")
        # Acceleration determines the native reader's rate; overlap with other
        # streams can only shorten its grid. Check before numpy allocates it.
        with archive.open(accel) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            reader.fieldnames = [name.strip().lower() for name in (reader.fieldnames or [])]
            time = next((name for name in ("seconds_elapsed", "time") if name in reader.fieldnames), None)
            if time is None:
                raise ValueError("sensor ZIP accelerometer needs seconds_elapsed or time")
            samples = []
            for row in reader:
                if len(samples) >= MAX_SENSOR_ROWS:
                    raise ValueError("sensor ZIP has too many samples")
                samples.append(float(row[time]))
        times = np.sort(np.asarray(samples) / (1e9 if time == "time" else 1))
        if len(times) < 3 or not np.isfinite(times).all():
            raise ValueError("sensor ZIP needs finite accelerometer timestamps")
        interval = float(np.median(np.diff(times)))
        span = times[-1] - times[0]
        if not 0.001 <= interval <= 0.1 or not 1 <= span <= 3600:
            raise ValueError("sensor ZIP needs 10–1000 Hz samples over 1–3600 seconds")
        if span * round(1 / interval) + 1 > MAX_SENSOR_ROWS:
            raise ValueError("sensor ZIP time grid is too large")
    # The existing reader dispatches by suffix. Keep magic-detected uploads on
    # that exact ZIP path too, without extracting or flattening the export.
    if path.suffix.lower() != ".zip":
        destination = work / "sensor.zip"
        shutil.copyfile(path, destination)
        path = destination
    return load_recording(path)


def _flat_recording(path: Path, work: Path) -> Recording:
    """Adapt the uploaded combined CSV to the existing Sensor Logger reader."""
    if path.stat().st_size > MAX_SENSOR_BYTES:
        raise ValueError("sensor CSV exceeds 25 MB")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [name.strip().lower() for name in (reader.fieldnames or [])]
        if len(fields) != len(set(fields)):
            raise ValueError("sensor CSV has duplicate column names")
        reader.fieldnames = fields
        time = next((name for name in ("seconds_elapsed", "time") if name in fields), None)
        if time is None:
            raise ValueError("sensor CSV needs seconds_elapsed or time")
        axes = []
        for prefix, short in (("accel", "a"), ("gyro", "g")):
            for axis in "xyz":
                name = next((key for key in (f"{prefix}_{axis}", f"{short}{axis}") if key in fields), None)
                if name is None:
                    raise ValueError("sensor CSV needs accel_x/y/z (m/s²) and gyro_x/y/z (rad/s)")
                axes.append(name)
        quat = [key for key in ("qx", "qy", "qz", "qw") if key in fields]
        if quat and len(quat) != 4:
            raise ValueError("sensor CSV needs all four quaternion columns or none")
        rows, mock_values = [], set()
        for row in reader:
            if len(rows) >= MAX_SENSOR_ROWS:
                raise ValueError("sensor CSV has too many samples")
            try:
                values = [float(row[name]) for name in [time, *axes, *quat]]
            except (ValueError, TypeError, KeyError):
                raise ValueError("sensor CSV contains an incomplete or non-numeric sample") from None
            if not all(math.isfinite(value) for value in values):
                raise ValueError("sensor CSV contains non-finite values")
            if rows and values[0] <= rows[-1][0]:
                raise ValueError("sensor CSV timestamps must increase")
            rows.append(values)
            marker = (row.get("mock") or "false").strip().lower()
            if marker not in ("0", "false", "no", "1", "true", "yes"):
                raise ValueError("sensor CSV mock must be true or false")
            mock_values.add(marker in ("1", "true", "yes"))
    if len(rows) < 3 or len(mock_values) != 1:
        raise ValueError("sensor CSV needs consistent provenance and at least three samples")
    times = np.asarray([row[0] for row in rows]) / (1e9 if time == "time" else 1)
    interval = float(np.median(np.diff(times)))
    # Bound resampling before the existing loader allocates a uniform grid.
    if not 0.001 <= interval <= 0.1 or not 1 <= times[-1] - times[0] <= 3600:
        raise ValueError("sensor CSV needs 10–1000 Hz samples over 1–3600 seconds")
    if (times[-1] - times[0]) / interval > MAX_SENSOR_ROWS:
        raise ValueError("sensor CSV time grid is too large")
    for name, start in (("Accelerometer", 1), ("Gyroscope", 4)):
        with (work / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([time, "x", "y", "z"])
            writer.writerows([row[0], *row[start:start + 3]] for row in rows)
    if quat:
        if any(np.linalg.norm(row[7:]) < 1e-8 for row in rows):
            raise ValueError("sensor CSV contains a zero quaternion")
        with (work / "Orientation.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([time, *quat])
            writer.writerows([row[0], *row[7:]] for row in rows)
    (work / "Metadata.csv").write_text(f"mock\n{str(mock_values.pop()).lower()}\n", encoding="utf-8")
    return load_recording(work)


def _video_taps(clip: Path, work: Path, info: VideoInfo) -> np.ndarray:
    wav = work / "tap-audio.wav"
    run_tool([tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
              "-format_whitelist", "mov,avi", "-i", str(clip.resolve()), "-map", "0:a:0", "-vn",
              "-ac", "1", "-ar", "16000", "-t", "300", str(wav)], timeout=30)
    hits = audio_hits(str(wav), min_gap_s=0.04, rise_db=20)
    return playback_hits_to_real(info, hits)


def _tap_sync(rec: Recording, contacts: list[tuple[str, float]], hits: np.ndarray) -> dict:
    spikes = find_spikes(rec)
    events = [event for event in find_tap_events(rec, spikes)
              if event["taps_s"][-1] <= float(rec.t[0]) + 60]
    if not events:
        raise ValueError("no still-arm double tap found in the sensor data")
    taps = events[0]["taps_s"]
    impacts, rejected = find_impacts(spikes, taps[-1] + IMPACT_GUARD_S)
    speed = np.degrees(np.linalg.norm(rec.gyro, axis=1))

    def swinging(t: float) -> bool:
        near = np.abs(rec.t - t) <= TOLERANCE_MS / 1000
        return bool(near.any() and rec.t[0] <= t <= rec.t[-1] and speed[near].max() >= MIN_SWING_DPS)

    # The taps precede the first video swing. Require both the tap interval and
    # subsequent contact alignment to agree; never infer a clock from hits alone.
    hits = np.sort(np.asarray(hits, dtype=float))
    hits = hits[np.isfinite(hits) & (hits >= 0) & (hits < min(t for _, t in contacts) - IMPACT_GUARD_S)]
    candidates = []
    for start in range(len(hits) - len(taps) + 1):
        sequence = hits[start:start + len(taps)]
        if np.any(np.abs(np.diff(sequence) - np.diff(taps)) > TAP_GAP_TOLERANCE_S):
            continue
        a = float(sequence[0])
        alignment = align([s.t for s in impacts], contacts, taps[0], a, swinging=swinging)
        if alignment["error_ms"]["n_ok"] or alignment["tap_only"]:
            candidates.append((float(a), alignment))
    if len(candidates) != 1:
        reason = "ambiguous" if candidates else "no matching"
        raise ValueError(f"{reason} audio double tap in video A; wrist sync was not trusted")
    tap, alignment = candidates[0]
    return {"taps_s": taps, "video_tap_s": tap, "alignment": alignment,
            "impacts": {p["swing"]: p["impact_s"] for p in alignment["pairs"] if p["ok"]},
            "tap_only": {p["swing"]: p["contact_s"] for p in alignment["tap_only"]},
            "rejected_spikes": rejected, "warnings": [], "tap_method": "audio double tap matched to sensor taps"}


def _at_gyro_peak(rec: Recording, sync: dict, metrics: dict) -> tuple[dict, list[str]]:
    """Match make_sensor_sample: wrist window at gyro peak, camera/racket at impact."""
    entries = {sid: entry for sid, entry in metrics["swings"].items() if entry.get("usable")}
    peaks, warnings = [], []
    for sid, entry in entries.items():
        contact = entry["contact_s"]
        found = find_shadow_swings(rec, contact - GYRO_PEAK_SEARCH_S, contact + GYRO_PEAK_SEARCH_S)
        if found:
            peaks.append({"swing": sid, "contact_s": min(found, key=lambda t: abs(t - contact))})
        else:
            warnings.append(f"Wrist data skipped for {sid}: no gyro peak near its synced contact.")
    gp_sync = {**sync, "impacts": {}, "tap_only": {}, "alignment": {
        **sync["alignment"], "pairs": [], "unpaired_swings": [], "tap_only": [], "gyro_peak": peaks}}
    gp_metrics, _, _ = wrist_report(rec, gp_sync)
    accepted = {}
    for sid, gp in gp_metrics["swings"].items():
        if not gp.get("usable"):
            continue
        before = entries[sid]
        info = {"contact_source": "gyro peak", "gyro_peak_s": gp["contact_s"],
                "found_from": before["contact_source"], "found_from_s": before["contact_s"],
                "gyro_peak_minus_found_from_ms": round((gp["contact_s"] - before["contact_s"]) * 1000, 1),
                "search_ms": GYRO_PEAK_SEARCH_S * 1000}
        accepted[sid] = {**gp, "occlusion_fill": before["occlusion_fill"],
                         "racket_speed_sensor": {**before["racket_speed_sensor"],
                                                 "contact_source": before["contact_source"]},
                         "align_error_ms": before.get("align_error_ms"), "timing": info}
    return {**gp_metrics, "swings": accepted}, [*metrics["warnings"], *gp_metrics["warnings"], *warnings]


def attach_sensor(swings: list[dict], clip_a: Path, csv_path: Path, *, slowdown: float | None,
                  work: Path, info: VideoInfo | None = None) -> tuple[list[dict], list[str]]:
    """Return wrist-enriched swings, or originals with a warning on any sensor/sync failure.

    Swings must already have final unique IDs and metadata.sourceContactSeconds in
    video A's real-time clock. Pass info when slowdown was inferred/retried.
    Optional sensor work never mutates a caller's swings or publishes raw uploads.
    """
    try:
        contacts = [(s["id"], float(s["metadata"]["sourceContactSeconds"])) for s in swings]
        if not contacts or not all(math.isfinite(t) for _, t in contacts):
            raise ValueError("video contact times are unavailable")
        info = info or probe_video(clip_a, slowdown)
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".wrist-", dir=work) as temporary:
            folder = Path(temporary)
            rec = (_zip_recording(csv_path, folder) if is_sensor_zip(csv_path)
                   else _flat_recording(csv_path, folder))
            sync = _tap_sync(rec, contacts, _video_taps(clip_a, folder, info))
            originals = {s["id"]: copy.deepcopy(s) for s in swings}
            metrics, _, filled = wrist_report(rec, sync, swings=originals)
            metrics, warnings = _at_gyro_peak(rec, sync, metrics)
            accepted = metrics["swings"]
            if not accepted:
                raise ValueError("no usable wrist samples aligned with the video swings")
            attached = attach_wrist_entries({sid: originals[sid] for sid in accepted}, metrics, filled)
            for sid, swing in attached.items():
                swing.setdefault("metadata", {})["wristSync"] = {
                    "method": sync["tap_method"], "offsetSeconds": sync["alignment"]["offset_s"],
                    "videoTapSeconds": sync["video_tap_s"], "sensorTapSeconds": sync["taps_s"][0],
                    "forearmAxis": "y", "mock": rec.mock}
                swing["metadata"]["wristTiming"] = accepted[sid]["timing"]
            if len(attached) != len(swings):
                warnings.append("Sensor data was ignored for swings without trusted tap/contact alignment or usable wrist data.")
            warnings.append("Sensor forearm axis assumed y: strap the phone's long edge along the hitting forearm.")
            return [attached.get(s["id"], s) for s in swings], list(dict.fromkeys(warnings))
    except Exception as exc:
        # Optional input must not fail a successfully reconstructed video. Limit
        # diagnostics to our validation messages; tool/library errors may contain paths.
        reason = str(exc) if type(exc) is ValueError else "invalid sensor data or tap sync failed"
        return swings, [f"Sensor data ignored: {reason}."]
