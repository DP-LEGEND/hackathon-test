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
from pipeline.segment import (BACKSWING_LOOKBACK_S, CONTACT_MATCH_S, REVERSAL_SUPPORT_S, PEAK_MATCH_S,
                              audio_hits, find_swings, wrist_speed, swing_evidence)
from pipeline.kinematics import gap_limit, runs
from pipeline.timing import Timeline
from pipeline.stereo import calibrate, clean, normalise, triangulate


@dataclass(frozen=True)
class Options:
    # B clip seconds = A clip seconds * slowdown_b / slowdown_a + offset_b.
    slowdown_a: float = 1.0
    slowdown_b: float = 1.0
    offset_b: float = 0.0
    hand: str = "auto"
    side: str = "auto"
    torso_m: float = 0.5
    focal_a: float | None = None
    focal_b: float | None = None
    min_speed: float = 8.0
    max_gap_s: float = 0.25
    model_path: str = DEFAULT_MODEL
    no_cache: bool = False
    cache_dir: str | None = None
    a_realtime_before: float = 0.0
    a_realtime_after: float | None = None
    b_realtime_before: float = 0.0
    b_realtime_after: float | None = None
    hits_wav: str | None = None
    tap_filter: bool = False

    def validate(self) -> None:
        Timeline(self.slowdown_a, self.a_realtime_before, self.a_realtime_after)
        Timeline(self.slowdown_b, self.b_realtime_before, self.b_realtime_after)
        for key in ("slowdown_a", "slowdown_b", "torso_m", "min_speed"):
            value = getattr(self, key)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if not np.isfinite(self.offset_b) or not np.isfinite(self.max_gap_s) or self.max_gap_s < 0:
            raise ValueError("offset_b must be finite; max_gap_s must be finite and nonnegative")
        for value in (self.focal_a, self.focal_b):
            if value is not None and (not np.isfinite(value) or value <= 0):
                raise ValueError("Focal lengths must be finite and positive")
        if self.hand not in ("auto", "R", "L") or self.side not in ("auto", "forehand", "backhand"):
            raise ValueError("Invalid hand or side")


def classify_side(world: np.ndarray, contact: int, hand: str) -> str:
    """Approximate stroke side from the wrist's lateral position before contact.

    A body-only heuristic, not a racket/ball measurement. Ambiguous poses remain
    unknown; --side provides the known label for a single-side session.
    """
    pose = world[contact]
    lateral = pose[12] - pose[11]
    up = (pose[11] + pose[12] - pose[23] - pose[24]) / 2
    up_length = np.linalg.norm(up)
    up = up / up_length if up_length >= 1e-6 else np.array([0., 1., 0.])
    lateral = lateral - np.dot(lateral, up) * up
    length = np.linalg.norm(lateral)
    if length < 1e-6:
        return "unknown"
    wrist = pose[16 if hand == "R" else 15]
    hips = (pose[23] + pose[24]) / 2
    signed = float(np.dot(wrist - hips, lateral / length)) * (1 if hand == "R" else -1)
    if abs(signed) < 1e-6:
        return "unknown"
    return "forehand" if signed > 0 else "backhand"


CORE_JOINTS = (11, 12, 13, 14, 15, 16, 23, 24)


def carry_offhand_wrist(points: np.ndarray, hand: str) -> tuple[np.ndarray, np.ndarray]:
    """Carry a hidden NON-hitting wrist rigidly with its tracked elbow.

    With hidden landmarks excluded from stereo, the off-hand wrist is often
    behind the body for longer than the repair limit during a forehand. It is
    not swing evidence, so keep the window: hold the forearm offset seen at the
    nearest tracked frames (blended across the gap, bone length kept). Every
    carried frame is returned as filled, i.e. guessed, never measured.
    """
    elbow, wrist = (13, 15) if hand == 'R' else (14, 16)
    points = points.copy()
    carried = np.zeros(len(points), dtype=bool)
    seen = np.isfinite(points[:, wrist]).all(axis=1) & np.isfinite(points[:, elbow]).all(axis=1)
    if not seen.any():
        return points, carried
    for start, end in runs(~np.isfinite(points[:, wrist]).all(axis=1)):
        if not np.isfinite(points[start:end, elbow]).all():
            continue
        before = points[start - 1, wrist] - points[start - 1, elbow] if start > 0 else None
        after = points[end, wrist] - points[end, elbow] if end < len(points) else None
        before = after if before is None else before
        after = before if after is None else after
        weight = (np.arange(1, end - start + 1) / (end - start + 1))[:, None]
        offset = (1 - weight) * before + weight * after
        length = (1 - weight) * np.linalg.norm(before) + weight * np.linalg.norm(after)
        offset *= length / np.maximum(np.linalg.norm(offset, axis=1, keepdims=True), 1e-9)
        points[start:end, wrist] = points[start:end, elbow] + offset
        carried[start:end] = True
    return points, carried


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


def swings_from_raw(a: dict, b: dict | None = None, options: Options = Options()) -> tuple[list[dict], dict]:
    """Pure-array entry point for extraction caches and deterministic validation."""
    options.validate()
    for name, raw in ([("A", a)] + ([("B", b)] if b is not None else [])):
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
    focal_b = options.focal_b or (1400 * b["size"][0] / 1920 if b is not None else 1400)
    fps_real = float(a["fps"]) * options.slowdown_a
    timeline_a = Timeline(options.slowdown_a, options.a_realtime_before, options.a_realtime_after)
    timeline_b = Timeline(options.slowdown_b, options.b_realtime_before, options.b_realtime_after)
    real_a = timeline_a.real(a["t"])
    real_b = timeline_b.real(b["t"]) if b is not None else None
    # offset_b remains B playback seconds at A playback zero, including negative
    # extrapolation using B's initial rate. Re-measure sync when changing ramps.
    real_offset = float(timeline_b.real(options.offset_b))
    synced_a = {**a, "t": real_a}
    synced_b = {**b, 't': real_b,
                # Preserve encoded-frame adjacency before the piecewise clock
                # changes intervals. Resampling must not bridge dropped frames.
                'frame_contiguous': np.diff(b['t']) <= 1.5 / b['fps']} if b is not None else None
    sections = timeline_a.sections(a["t"])

    def clean_sections(points, filled, win=5):
        out = points.copy()
        repaired = filled.copy()
        for lo, hi, factor in sections:
            real_fps = a['fps'] * factor
            limit = gap_limit(real_fps, options.max_gap_s)
            section_win = min(win, max(1, int(round(.04 * real_fps)) | 1))
            out[lo:hi], repaired[lo:hi] = clean(points[lo:hi], win=section_win, max_gap=limit,
                                                filled=filled[lo:hi], provenance=True)
        return out, repaired
    mono = np.asarray(a["world"], dtype=float).copy()
    observed = np.isfinite(a["img"][:, :, :2]).all(axis=2) & (a["vis"] > .1)
    mono_visibility = np.clip(np.nan_to_num(a['vis'], nan=0., posinf=0., neginf=0.), 0, 1)
    mono_visibility[~np.isfinite(a['img'][:, :, :2]).all(axis=2)] = 0
    mono[~observed] = np.nan
    mono_filled = ~np.isfinite(mono).all(axis=2) | (mono_visibility < .5)
    mono, mono_filled = clean_sections(mono, mono_filled)
    cal, calibration_error = None, None
    stereo = np.full_like(mono, np.nan)
    stereo_filled = np.ones(mono.shape[:2], dtype=bool)
    stereo_visibility = np.zeros(mono.shape[:2])
    try:
        if b is None:
            raise ValueError("Single camera: depth is estimated from MediaPipe")
        cal = calibrate(synced_a, synced_b, 1.0, real_offset, f_a=focal_a, f_b=focal_b)
        reconstructed, stereo_filled, stereo_visibility = triangulate(
            synced_a, synced_b, cal, 0, len(a['t']), provenance=True)
        # A stereo sample between B frames uses a temporally interpolated view.
        # Use the same fractional-frame exact-match tolerance as sample_b_at_a.
        target = real_a + real_offset
        index = np.clip(np.searchsorted(real_b, target, side="right") - 1, 0, len(real_b) - 2)
        weight = (target - real_b[index]) / (real_b[index + 1] - real_b[index])
        exact_b = np.isclose(weight, 0, rtol=0, atol=1e-9) | np.isclose(weight, 1, rtol=0, atol=1e-9)
        stereo_filled |= ~exact_b[:, None]
        stereo, stereo_filled = clean_sections(reconstructed, stereo_filled)
    except (ValueError, cv2.error) as exc:
        # A cropped/unusable second view must not prevent usable iPhone swings.
        cal = None
        calibration_error = str(exc)
    # A hidden A wrist must not defeat B's recovered 3D trajectory or inject
    # low-confidence pixel spikes into detection/automatic hand selection.
    detection = {**a, 'img': a['img'].copy(), 'vis': mono_visibility.copy()}
    detection['img'][~observed] = np.nan
    # Detection may use a bounded repair, while exported visibility remains the
    # original camera evidence. The final metric gate uses the repaired 3D pose.
    repaired_pixels, _ = clean_sections(detection['img'], ~observed, win=1)
    usable = (~observed & np.isfinite(repaired_pixels).all(axis=2)
              & np.isfinite(mono).all(axis=2))
    detection['img'][usable] = repaired_pixels[usable]
    detection['vis'][usable] = 1.
    if cal is not None:
        projected = stereo @ cal['Ka'].T
        with np.errstate(invalid='ignore', divide='ignore'):
            pixels = projected[:, :, :2] / projected[:, :, 2:]
        recovered = ~observed & np.isfinite(pixels).all(axis=2)
        detection['img'][recovered, :2] = pixels[recovered]
        detection['vis'][recovered] = 1.
    if "audio_hits" in a:
        hits = np.asarray(a["audio_hits"])
    else:
        hits = timeline_a.real(audio_hits(options.hits_wav, rise_db=25)) if options.hits_wav else None
    detections, contact_references = [], []
    for lo, hi, factor in sections:
        if hi - lo < 2:
            continue
        part = {**detection, 'img': detection['img'][lo:hi], 'vis': detection['vis'][lo:hi],
                't': real_a[lo:hi], 'fps': a['fps'] * factor}
        section_events = []
        hands = ("R", "L") if options.hand == "auto" else (options.hand,)
        for hand in hands:
            settings = dict(min_speed=7.0 if options.tap_filter else options.min_speed,
                            min_gap_real_s=2.5 if options.tap_filter else .5,
                            hits=hits, confirm_s=.5, require_audio=False,
                            speed_fallback=True, wrist=16 if hand == "R" else 15)
            if hits is not None and len(hits):
                original = {**a, 'img': a['img'][lo:hi], 't': real_a[lo:hi], 'fps': a['fps'] * factor}
                for reference in find_swings(original, **settings, contact_reference=True):
                    contact_references.append({**reference, 'peak': reference['peak'] + lo,
                                               'section': (lo, hi)})
            for event in find_swings(part, **settings):
                event["hand"] = hand
                for key in ("start", "end", "peak"):
                    event[key] += lo
                event["fpsReal"] = float(a["fps"]) * factor
                event['section'] = (lo, hi)
                event["realtime"] = factor == 1
                section_events.append(event)
        detections.extend(section_events)
    # Match main's candidate spacing, including across hands/rate sections.
    selected = []
    for event in sorted(detections, key=lambda e: e['speed'], reverse=True):
        if all(abs(real_a[event['peak']] - real_a[other['peak']]) >= (2.5 if options.tap_filter else .5)
               for other in selected):
            selected.append(event)
    detections = sorted(selected, key=lambda e: e['peak'])
    # Apply main's cross-hand/rate spacing to its original candidates, too.
    # Recovery may move the admission peak, but must not choose a new transient.
    anchors = []
    for reference in sorted(contact_references, key=lambda e: e['speed'], reverse=True):
        if all(abs(real_a[reference['peak']] - real_a[other['peak']]) >= (2.5 if options.tap_filter else .5)
               for other in anchors):
            anchors.append(reference)
    for event in detections:
        lo, hi = event['section']
        if anchors:
            reference = min(anchors, key=lambda e: abs(real_a[e['peak']] - real_a[event['peak']]))
            # Real seconds, not slow-mo playback: the reprojected track can move
            # the speed peak ~0.2 s from main's, but the contact stays main's:
            # its sound match, or its speed peak when neither has a sound.
            if (reference['section'] == event['section']
                    and abs(real_a[reference['peak']] - real_a[event['peak']]) <= CONTACT_MATCH_S + 1e-9):
                if reference.get('hit') is not None:
                    hit_frame = int(np.argmin(abs(real_a - reference['hit'])))
                    if lo <= hit_frame < hi:
                        event['hit'] = reference['hit']
                if (event.get('hit') is None and lo <= reference['peak'] < hi
                        and abs(real_a[reference['peak']] - real_a[event['peak']]) <= PEAK_MATCH_S + 1e-9):
                    event['contactPeak'] = reference['peak']
        if event.get('hit') is not None:
            hit_frame = int(np.argmin(abs(real_a - event['hit'])))
            if lo <= hit_frame < hi:
                event['start'] = min(event['start'], hit_frame)
                event['end'] = max(event['end'], hit_frame)
    swings, rejected = [], []
    for number, event in enumerate(detections, 1):
        start, end = event["start"], event["end"] + 1  # finder uses inclusive end
        hand = event.get("hand", options.hand)
        if hand == "auto":
            hand = "R"
        if options.hand == "auto":
            local = {**detection, 'img': detection['img'][start:end], 'vis': detection['vis'][start:end]}
            peaks = {}
            speeds = {}
            for side, joint in (("R", 16), ("L", 15)):
                speed = wrist_speed(local, wrist=joint, slowdown=event.get("fpsReal", fps_real) / a["fps"])
                speeds[side] = speed
                finite = speed[np.isfinite(speed)]
                peaks[side] = float(finite.max()) if len(finite) else -1.0
            hand = "L" if peaks["L"] > peaks["R"] else "R"
            if hand != event.get("hand", "R") and np.isfinite(speeds[hand]).any():
                event["peak"] = start + int(np.nanargmax(speeds[hand]))
        fps_real = event.get("fpsReal", fps_real)
        measured_contact = event.get("hit") is not None
        estimate = event.get('contactPeak', event['peak'])
        if not start <= estimate < end:
            estimate = event['peak']
        contact_source = estimate if not measured_contact else int(np.argmin(abs(real_a - event["hit"])))
        if not start <= contact_source < end:
            # A matching audio hit can lie outside the standard peak window.
            # Keep the rate-consistent window; do not fabricate a contact frame.
            contact_source = estimate
            measured_contact = False
        lo, hi = event['section']
        start = max(lo, int(np.searchsorted(real_a, real_a[contact_source] - .6 - 1e-9)))
        end = min(hi, max(end, contact_source + int(round(.35 * fps_real)) + 1))
        stereo_core = np.isfinite(stereo[:, CORE_JOINTS]).all(axis=(1, 2))
        mono_core = np.isfinite(mono[:, CORE_JOINTS]).all(axis=(1, 2))
        source = ('stereo' if stereo_core[start:end].all() else 'mono'
                  if mono_core[start:end].all() else 'stereo' if stereo_core[contact_source] else 'mono')
        valid_core = stereo_core if source == 'stereo' else mono_core
        original_window = (start, end)
        # An occluded windup edge need not discard a tracked contact and follow-
        # through. Crop only to a contiguous observed/repaired core run; never
        # bridge long gaps or lower the core visibility gate.
        if valid_core[contact_source] and not valid_core[start:end].all():
            left = contact_source
            right = contact_source + 1
            while left > start and valid_core[left - 1]:
                left -= 1
            while right < end and valid_core[right]:
                right += 1
            if (real_a[contact_source] - real_a[left] >= .15
                    and real_a[right - 1] - real_a[contact_source] >= .08):
                start, end = left, right
        contact = contact_source - start
        try:
            selected = stereo[start:end] if source == 'stereo' else mono[start:end]
            selected, offhand_carried = carry_offhand_wrist(selected, hand)
            if not np.isfinite(selected[:, CORE_JOINTS]).all():
                missing = [j for j in CORE_JOINTS if not np.isfinite(selected[:, j]).all()]
                raise ValueError(f'Reconstruction contains missing key joints {missing}; hidden gap exceeds the repair limit')
            fallback_reason = (calibration_error or "Stereo key joints unavailable after quality gates") if source == "mono" else None
            try:
                normalised = normalise(selected, options.torso_m)
            except ValueError as exc:
                if source != "stereo":
                    raise
                source = "mono"
                fallback_reason = f"Stereo normalisation failed: {exc}"
                selected, offhand_carried = carry_offhand_wrist(mono[start:end], hand)
                if not np.isfinite(selected[:, CORE_JOINTS]).all():
                    raise
                normalised = normalise(selected, options.torso_m)
            # Sound can be offset from the speed peak. Keep its requested .6 s
            # replay trim without throwing away earlier backswing evidence.
            # Metric and image peaks may differ by PEAK_MATCH_S. Read enough
            # source history for the entire reversal search at either peak;
            # this does not change the replay window or contact selection.
            history_s = BACKSWING_LOOKBACK_S + REVERSAL_SUPPORT_S + PEAK_MATCH_S
            evidence_start = max(0, min(start, int(np.searchsorted(
                real_a, real_a[event['peak']] - history_s - 1e-9))))
            trajectory = (stereo if source == 'stereo' else mono)
            wrist = 15 if hand == 'L' else 16
            # Keep the candidate's source index even when history contains gaps.
            # The gate bridges bounded gaps and stops at longer missing runs.
            evidence_world = (normalised if evidence_start == start else
                              normalise(trajectory[evidence_start:end], options.torso_m))
            try:
                evidence = swing_evidence(evidence_world, real_a[evidence_start:end], wrist,
                                          event['peak'] - evidence_start, options.torso_m, options.max_gap_s)
            except ValueError:
                # Auto hand can pick an off-hand wrist whose reappearance from
                # behind the body looks like a speed peak. Then test the other
                # wrist with the same, unrelaxed 3D gate before rejecting.
                if options.hand != 'auto' or offhand_carried.any():
                    raise  # never test a guessed off-hand wrist as swing evidence
                other = 31 - wrist
                evidence = swing_evidence(evidence_world, real_a[evidence_start:end], other,
                                          event['peak'] - evidence_start, options.torso_m, options.max_gap_s)
                wrist, hand = other, 'L' if other == 15 else 'R'
            joint_filled = (stereo_filled if source == "stereo" else mono_filled)[start:end].copy()
            joint_filled |= ~np.isfinite(normalised).all(axis=2)
            joint_filled[offhand_carried, 15 if hand == 'R' else 16] = True
            world, filled = complete_optional_joints(normalised)
            confidence = (stereo_visibility if source == 'stereo' else mono_visibility)[start:end]
            raw = {"world": world, "filled": joint_filled, 'vis': confidence, "t": real_a[start:end],
                   "fps": fps_real}
            swing = to_swing(raw, smooth_win=1, swing_id=f"swing-{number:04d}", contact_frame=contact)
        except ValueError as exc:
            rejected.append({"index": number, "startFrame": start, "sourcePeakSeconds": float(a["t"][event["peak"]]), "detection": event.get("detection", "pattern"), "reason": str(exc)})
            continue
        swing["source"] = source
        swing["fpsReal"] = fps_real
        swing["side"] = (classify_side(world, contact, hand)
                         if options.side == "auto" else options.side)
        visibility = confidence[:, CORE_JOINTS]
        # Stable reporting at the .3 boundary despite floating-point summation.
        core_visibility = round(float(np.clip(visibility, 0, 1).mean()), 6)
        swing["metadata"] = {
            "hand": hand,
            "handSource": "auto" if options.hand == "auto" else "manual",
            "depth": "estimated" if source == "mono" else "stereo",
            "contactMethod": "audio-transient" if measured_contact else "wrist-speed-peak-estimate",
            "detection": event.get("detection", "pattern"), "realtime": event.get("realtime", False),
            "croppedForCoreVisibility": (start, end) != original_window,
            "sideMethod": "wrist-lateral-position-estimate" if options.side == "auto" else "provided",
            "stroke": swing["side"], "strokeSource": "auto" if options.side == "auto" else "manual",
            "sourceStartFrame": start, "sourceContactFrame": contact_source,
            "sourceStartSeconds": float(a["t"][start]),
            "sourcePeakSeconds": float(a["t"][event["peak"]]),
            "sourceContactSeconds": float(a["t"][contact_source]),
            "realStartSeconds": float(real_a[start]),
            "coordinateSystem": "hip-centred-y-up-metres",
            "scaleMethod": "assumed-torso-length", "torsoMetres": options.torso_m,
            "reconstruction": source, "approximatedJoints": filled,
            "fallbackReason": fallback_reason,
            "coreVisibility": core_visibility, "lowConfidence": core_visibility < .3,
            'hittingArmFilledPercent': 100 * float(joint_filled[:, (11, 13, 15) if hand == 'L' else (12, 14, 16)].any(axis=1).mean()),
            **evidence,
            "optionalJointPolicy": "missing optional joints repeat their parent; not measured",
        }
        swings.append(swing)
    report = {"detected": len(detections), "written": len(swings), "rejected": rejected,
              "sync": {"scale": scale, "offset": options.offset_b, "realOffset": real_offset, "timeline": "piecewise"},
              "calibration": ({k: cal[k] for k in ("inliers", "n", "reprojectionErrorPx")}
                              if cal is not None else {"error": calibration_error})}
    return swings, report


def process_clips(clip_a: str, clip_b: str | None, out_dir: str,
                  options: Options = Options()) -> dict:
    """Extract both clips, write one strict JSON file per accepted swing + manifest.

    Use a fresh output folder to prevent stale swing files being replayed. Never
    overwrite existing output or put model weights/video in the repository.
    """
    options.validate()
    if clip_b is None:
        from pipeline.live import process_live_clip, LiveOptions
        return process_live_clip(Path(clip_a), Path(out_dir), LiveOptions(
            slowdown=None if options.slowdown_a == 1 else options.slowdown_a, hand=None if options.hand == "auto" else options.hand,
            stroke=None if options.side == "auto" else options.side, model_path=options.model_path,
            min_speed=options.min_speed))
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
