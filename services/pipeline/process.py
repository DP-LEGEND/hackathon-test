"""Synced stereo clips -> individual replay-compatible Swing objects."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import cv2

from pipeline.cache import extract_pair
from pipeline.pose import DEFAULT_MODEL, extract_raw, to_swing
from pipeline.segment import find_swings
from pipeline.stereo import calibrate, clean, normalise, triangulate


@dataclass(frozen=True)
class Options:
    # B clip seconds = A clip seconds * slowdown_b / slowdown_a + offset_b.
    slowdown_a: float = 1.0
    slowdown_b: float = 1.0
    offset_b: float = 0.0
    hand: str = "R"
    side: str = "auto"
    torso_m: float = 0.5
    focal_a: float | None = None
    focal_b: float | None = None
    min_speed: float = 8.0
    max_gap_s: float = 0.25
    model_path: str = DEFAULT_MODEL
    no_cache: bool = False
    cache_dir: str | None = None

    def validate(self) -> None:
        for key in ("slowdown_a", "slowdown_b", "torso_m", "min_speed"):
            value = getattr(self, key)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if not np.isfinite(self.offset_b) or not np.isfinite(self.max_gap_s) or self.max_gap_s < 0:
            raise ValueError("offset_b must be finite; max_gap_s must be finite and nonnegative")
        for value in (self.focal_a, self.focal_b):
            if value is not None and (not np.isfinite(value) or value <= 0):
                raise ValueError("Focal lengths must be finite and positive")
        if self.hand not in ("R", "L") or self.side not in ("auto", "forehand", "backhand"):
            raise ValueError("Invalid hand or side")


def classify_side(world: np.ndarray, contact: int, hand: str) -> str:
    """Approximate stroke side from the wrist's lateral position before contact.

    A body-only heuristic, not a racket/ball measurement. Ambiguous poses remain
    unknown; --side provides the known label for a single-side session.
    """
    pose = np.median(world[max(0, contact - 3):contact + 1], axis=0)
    lateral = pose[12] - pose[11]
    lateral[1] = 0
    length = np.linalg.norm(lateral)
    if length < 1e-6:
        return "unknown"
    wrist = pose[16 if hand == "R" else 15]
    hips = (pose[23] + pose[24]) / 2
    signed = float(np.dot(wrist - hips, lateral / length)) * (1 if hand == "R" else -1)
    if abs(signed) < 0.05:
        return "unknown"
    return "forehand" if signed > 0 else "backhand"


CORE_JOINTS = (11, 12, 13, 14, 15, 16, 23, 24)


def complete_optional_joints(world: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Keep 33 finite replay points; missing optional points repeat their parent.

    These are explicitly recorded as approximations, never used for the core gate,
    orientation or scale. A missing knee/ankle must not discard a valid arm swing.
    """
    world = world.copy()
    parents = {0: 11, **{j: 0 for j in range(1, 11)},
               17: 15, 19: 15, 21: 15, 18: 16, 20: 16, 22: 16,
               25: 23, 26: 24, 27: 25, 28: 26, 29: 27, 30: 28, 31: 27, 32: 28}
    filled = []
    for joint, parent in parents.items():
        missing = ~np.isfinite(world[:, joint]).all(axis=1)
        if missing.any():
            world[missing, joint] = world[missing, parent]
            filled.append(joint)
    return world, filled


def swings_from_raw(a: dict, b: dict, options: Options = Options()) -> tuple[list[dict], dict]:
    """Pure-array entry point for extraction caches and deterministic validation."""
    options.validate()
    for name, raw in (("A", a), ("B", b)):
        t = np.asarray(raw["t"])
        if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
            raise ValueError(f"Camera {name} needs at least two increasing finite timestamps")
        if not np.isfinite(raw["fps"]) or raw["fps"] <= 0:
            raise ValueError(f"Camera {name} has invalid FPS")
        if raw["img"].shape != (len(t), 33, 3) or raw["vis"].shape != (len(t), 33):
            raise ValueError(f"Camera {name} has invalid landmark arrays")
    if np.asarray(a["world"]).shape != (len(a["t"]), 33, 3):
        raise ValueError("Camera A has invalid world landmarks")
    scale = options.slowdown_b / options.slowdown_a
    focal_a = options.focal_a or 1400 * a["size"][0] / 1920
    focal_b = options.focal_b or 1400 * b["size"][0] / 1920
    fps_real = float(a["fps"]) * options.slowdown_a
    max_gap = max(0, int(options.max_gap_s * fps_real))
    # The iPhone gate is independent of the iPad and of stereo reconstruction.
    mono = np.asarray(a["world"], dtype=float).copy()
    # Visibility estimates occlusion, not whether MediaPipe detected a position.
    # Keep finite mono joints above .1 visibility; expose confidence in metadata.
    observed = np.isfinite(a["img"][:, :, :2]).all(axis=2) & (a["vis"] > .1)
    mono[~observed] = np.nan
    mono = clean(mono, max_gap=max_gap)
    cal, calibration_error = None, None
    stereo = np.full_like(mono, np.nan)
    try:
        cal = calibrate(a, b, scale, options.offset_b, f_a=focal_a, f_b=focal_b)
        stereo = clean(triangulate(a, b, cal, 0, len(a["t"])), max_gap=max_gap)
    except (ValueError, cv2.error) as exc:
        # A cropped/unusable second view must not prevent usable iPhone swings.
        cal = None
        calibration_error = str(exc)
    detections = find_swings(a, slowdown=options.slowdown_a,
                             min_speed=options.min_speed, wrist=16 if options.hand == "R" else 15)
    swings, rejected = [], []
    for number, event in enumerate(detections, 1):
        start, end = event["start"], event["end"] + 1  # finder uses inclusive end
        contact = event["peak"] - start
        try:
            if not np.isfinite(mono[start:end, CORE_JOINTS]).all():
                raise ValueError("iPhone view contains missing key joints (shoulders, elbows, wrists, hips)")
            source = "stereo" if np.isfinite(stereo[start:end, CORE_JOINTS]).all() else "mono"
            fallback_reason = (calibration_error or "Stereo key joints unavailable after quality gates") if source == "mono" else None
            selected = stereo[start:end] if source == "stereo" else mono[start:end]
            try:
                normalised = normalise(selected, options.torso_m)
            except ValueError as exc:
                if source != "stereo":
                    raise
                source = "mono"
                fallback_reason = f"Stereo normalisation failed: {exc}"
                normalised = normalise(mono[start:end], options.torso_m)
            world, filled = complete_optional_joints(normalised)
            raw = {"world": world, "t": np.asarray(a["t"])[start:end] / options.slowdown_a,
                   "fps": fps_real}
            swing = to_swing(raw, smooth_win=1, swing_id=f"swing-{number:04d}", contact_frame=contact)
        except ValueError as exc:
            rejected.append({"index": number, "startFrame": start, "reason": str(exc)})
            continue
        swing["source"] = source
        swing["fpsReal"] = fps_real
        swing["side"] = (classify_side(world, contact, options.hand)
                         if options.side == "auto" else options.side)
        visibility = np.nan_to_num(a["vis"][start:end, CORE_JOINTS],
                                   nan=0., posinf=0., neginf=0.)
        # Stable reporting at the .3 boundary despite floating-point summation.
        core_visibility = round(float(np.clip(visibility, 0, 1).mean()), 6)
        swing["metadata"] = {
            "hand": options.hand,
            "contactMethod": "wrist-speed-peak-estimate",
            "sideMethod": "wrist-lateral-position-estimate" if options.side == "auto" else "provided",
            "sourceStartFrame": start, "sourceContactFrame": event["peak"],
            "sourceStartSeconds": float(a["t"][start]),
            "coordinateSystem": "hip-centred-y-up-metres",
            "scaleMethod": "assumed-torso-length", "torsoMetres": options.torso_m,
            "reconstruction": source, "approximatedJoints": filled,
            "fallbackReason": fallback_reason,
            "coreVisibility": core_visibility, "lowConfidence": core_visibility < .3,
            "optionalJointPolicy": "missing optional joints repeat their parent; not measured",
        }
        swings.append(swing)
    report = {"detected": len(detections), "written": len(swings), "rejected": rejected,
              "sync": {"scale": scale, "offset": options.offset_b},
              "calibration": ({k: cal[k] for k in ("inliers", "n", "reprojectionErrorPx")}
                              if cal is not None else {"error": calibration_error})}
    return swings, report


def process_clips(clip_a: str, clip_b: str, out_dir: str,
                  options: Options = Options()) -> dict:
    """Extract both clips, write one strict JSON file per accepted swing + manifest.

    Use a fresh output folder to prevent stale swing files being replayed. Never
    overwrite existing output or put model weights/video in the repository.
    """
    options.validate()
    for clip in (clip_a, clip_b):
        if not Path(clip).is_file():
            raise ValueError(f"Clip does not exist: {clip}")
    output = Path(out_dir)
    retry_manifest = None
    if output.exists():
        if not output.is_dir() or {p.name for p in output.iterdir()} - {"raw_cache.npz", "manifest.json"}:
            raise ValueError("Output directory must be empty or contain only a pose cache and failed manifest")
        if (output / "manifest.json").exists():
            retry_manifest = (output / "manifest.json").read_text(encoding="utf-8")
            previous = json.loads(retry_manifest)
            if (not isinstance(previous, dict) or previous.get("written") != 0
                    or previous.get("files") != [] or previous.get("status") not in ("failed", "partial")):
                raise ValueError("Existing swing output is preserved; use a fresh directory")
    if not Path(options.model_path).is_file():
        raise ValueError("Pose model not found; supply --model-path or set GHOST_POSE_MODEL (see pipeline/README.md)")
    cache_dir = Path(options.cache_dir) if options.cache_dir else output
    a, b = extract_pair(str(clip_a), str(clip_b), options.model_path, cache_dir,
                        extract_raw, no_cache=options.no_cache)
    swings, report = swings_from_raw(a, b, options)
    if report["detected"] == 0:
        raise ValueError("No swings detected; check visibility, slowdown and --min-speed")
    # Stable, session-specific IDs distinguish repeated imports of different clips.
    digest = hashlib.sha256()
    for clip in (clip_a, clip_b):
        digest.update(Path(clip).stat().st_size.to_bytes(8, "big"))
        with Path(clip).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    session = digest.hexdigest()[:12]
    files = []
    payloads = []
    for swing in swings:
        swing["id"] = f"{session}-{swing['id']}"
        name = f"{swing['id']}.json"
        files.append(name)
        payloads.append((name, json.dumps(swing, allow_nan=False, separators=(",", ":"))))
    report.update({"session": session, "files": files,
                   "status": "failed" if not swings else "partial" if report["rejected"] else "complete"})
    payloads.append(("manifest.json", json.dumps(report, allow_nan=False, indent=2)))
    output.mkdir(parents=True, exist_ok=True)
    if retry_manifest is not None and (output / "manifest.json").read_text(encoding="utf-8") != retry_manifest:
        raise ValueError("Output manifest changed during processing; existing output is preserved")
    for name, payload in payloads:
        path = output / name
        mode = "w" if name == "manifest.json" and retry_manifest is not None else "x"
        with path.open(mode, encoding="utf-8") as stream:
            stream.write(payload + "\n")
    return report
