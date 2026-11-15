"""Optional, fail-soft sequence-synced wrist data for the multi-upload endpoint.

Flat CSV contract: seconds_elapsed (seconds) or time (Unix nanoseconds),
accel_x/y/z in m/s² and gyro_x/y/z in rad/s. ax/ay/az and gx/gy/gz are accepted
aliases. Optional qx/qy/qz/qw and mock retain Sensor Logger provenance. The
phone's long edge (y) must lie along the hitting forearm, as in wrist/README.md.
Only dominant swing sequences establish the clock; small feed taps and isolated
peaks cannot establish sync. Sensor Logger ZIPs use
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
from scipy.signal import find_peaks

from pipeline.multi_audio import _extract_hits
from pipeline.multi_sync import match_sequence, select_swing_peaks
from pipeline.video import VideoInfo, probe_video
from wrist.fuse import attach_wrist_entries
from wrist.load import Recording, load_recording
from wrist.metrics import wrist_report
from wrist.tempo import speed_dps

MAX_SENSOR_BYTES = 25 * 1024 * 1024
MAX_SENSOR_ROWS = 500_000
CONTACT_MATCH_S = 0.3
SEQUENCE_TOLERANCE_S = 0.12


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


def _video_swing_times(clip: Path, work: Path, info: VideoInfo) -> np.ndarray:
    """The same dominant audio swings used by the two-camera sync path."""
    return _extract_hits(clip, info, work / "sensor-sync-audio.wav")[0]


def _gyro_swings(rec: Recording) -> tuple[np.ndarray, np.ndarray]:
    """Session-sized gyro peaks; each is the strongest event in its 2 s window."""
    speed = speed_dps(rec)
    if not np.isfinite(speed).all():
        raise ValueError("sensor gyro contains non-finite values")
    peaks, _ = find_peaks(speed, distance=max(1, int(round(.04 * rec.rate_hz))))
    return select_swing_peaks(rec.t[peaks], speed[peaks])


def _sequence_sync(rec: Recording, contacts: list[tuple[str, float]], hits: np.ndarray,
                   debug: dict, gyro_peaks: tuple[np.ndarray, np.ndarray] | None = None) -> dict:
    gyro, strength = gyro_peaks if gyro_peaks is not None else _gyro_swings(rec)
    video = np.asarray(hits, dtype=float)
    if video.ndim != 1 or not np.isfinite(video).all():
        raise ValueError("video swing times must be finite and one-dimensional")
    debug.update(chosenGyroTimesSeconds=gyro.tolist(), chosenGyroStrengthDps=strength.tolist(),
                 chosenVideoTimesSeconds=video.tolist())
    try:
        match = match_sequence(video, gyro, tolerance_s=SEQUENCE_TOLERANCE_S, min_matches=3)
    except ValueError as exc:
        # offset_b_s only overrides camera B, not the sensor's independent clock.
        raise ValueError(str(exc).replace('; provide offset_b_s', '')) from None
    offset = match["offsetSeconds"]
    debug.update(offsetSeconds=offset, matchedCount=match["matchedCount"],
                 residualMs=match["residualMs"], sequencePairs=match["pairs"])
    matched = {int(i): int(j) for i, j in match["pairs"]}
    used = set()
    paired, unpaired = [], []
    for sid, contact in sorted(contacts, key=lambda item: item[1]):
        candidates = [i for i in matched if i not in used and abs(float(video[i]) - contact) <= CONTACT_MATCH_S]
        if not candidates:
            unpaired.append(sid)
            continue
        i = min(candidates, key=lambda index: abs(float(video[index]) - contact))
        used.add(i)
        sensor_time = float(gyro[matched[i]])
        paired.append({"swing": sid, "contact_s": sensor_time,
                       "contact_video_s": contact, "video_swing_s": float(video[i]),
                       "error_ms": (sensor_time - float(video[i]) - offset) * 1000})
    if not paired:
        raise ValueError("no video swing contact matches the synchronized gyro sequence")
    debug.update(status="matched", reason=None, matchedSwingIds=[row["swing"] for row in paired],
                 unmatchedSwingIds=unpaired)
    return {"taps_s": None, "video_tap_s": None, "impacts": {}, "tap_only": {},
            "rejected_spikes": [], "warnings": [], "method": "dominant swing sequence",
            "alignment": {"pairs": [], "tap_only": [], "gyro_peak": paired,
                          "unpaired_swings": unpaired, "offset_s": offset,
                          "offset_from": "dominant swing sequence", "tolerance_ms": SEQUENCE_TOLERANCE_S * 1000}}


def attach_sensor(swings: list[dict], clip_a: Path, csv_path: Path, *, slowdown: float | None,
                  work: Path, info: VideoInfo | None = None, debug: dict | None = None,
                  video_swing_times: list[float] | None = None) -> tuple[list[dict], list[str]]:
    """Return wrist-enriched swings, or originals with a warning on any sensor/sync failure.

    Swings must already have final unique IDs and metadata.sourceContactSeconds in
    video A's real-time clock. Pass info when slowdown was inferred/retried.
    Optional sensor work never mutates a caller's swings or publishes raw uploads.
    """
    debug = debug if debug is not None else {}
    debug.update(status="pending", reason=None, chosenGyroTimesSeconds=[],
                 chosenVideoTimesSeconds=[], offsetSeconds=None, matchedCount=0, residualMs=None)
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
            gyro_peaks = _gyro_swings(rec)
            debug.update(chosenGyroTimesSeconds=gyro_peaks[0].tolist(),
                         chosenGyroStrengthDps=gyro_peaks[1].tolist())
            hits = (np.asarray(video_swing_times, dtype=float) if video_swing_times is not None
                    else _video_swing_times(clip_a, folder, info))
            sync = _sequence_sync(rec, contacts, hits, debug, gyro_peaks)
            originals = {s["id"]: copy.deepcopy(s) for s in swings}
            metrics, _, filled = wrist_report(rec, sync, swings=originals)
            warnings = list(metrics["warnings"])
            accepted = {sid: entry for sid, entry in metrics["swings"].items() if entry.get("usable")}
            if not accepted:
                raise ValueError("no usable wrist samples aligned with the video swings")
            paired = {row["swing"]: row for row in sync["alignment"]["gyro_peak"]}
            for sid, entry in accepted.items():
                event = paired[sid]
                entry["timing"] = {"contact_source": "gyro peak", "gyro_peak_s": event["contact_s"],
                                   "found_from": "dominant swing sequence", "found_from_s": event["contact_s"],
                                   "gyro_peak_minus_found_from_ms": 0.0, "sequence_error_ms": event["error_ms"]}
                entry["racket_speed_sensor"]["contact_source"] = "gyro peak"
            metrics = {**metrics, "swings": accepted}
            attached = attach_wrist_entries({sid: originals[sid] for sid in accepted}, metrics, filled)
            for sid, swing in attached.items():
                swing.setdefault("metadata", {})["wristSync"] = {
                    "method": sync["method"], "offsetSeconds": sync["alignment"]["offset_s"],
                    "matchedCount": debug["matchedCount"], "residualMs": debug["residualMs"],
                    "forearmAxis": "y", "mock": rec.mock}
                swing["metadata"]["wristTiming"] = accepted[sid]["timing"]
            if len(attached) != len(swings):
                warnings.append("Sensor data was ignored for swings without trusted sequence alignment or usable wrist data.")
            warnings.append("Sensor forearm axis assumed y: strap the phone's long edge along the hitting forearm.")
            debug.update(status="attached", attachedSwingIds=list(attached))
            return [attached.get(s["id"], s) for s in swings], list(dict.fromkeys(warnings))
    except Exception as exc:
        # Optional input must not fail a successfully reconstructed video. Limit
        # diagnostics to our validation messages; tool/library errors may contain paths.
        reason = str(exc) if type(exc) is ValueError else "invalid sensor data or swing sequence sync failed"
        debug.update(status="ignored", reason=reason)
        return swings, [f"Sensor data ignored: {reason}."]
