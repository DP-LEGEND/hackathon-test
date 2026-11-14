"""Find individual swings in a long clip. Owner: Dev.

A swing = a fast hip-relative wrist sweep with a preceding pullback and a
follow-through (image space, scaled by torso length). A nearby audio transient
(1.5-7 kHz band) can be attached as an annotation; it is not required.

`slowdown` is how much the clip is slowed: iPhone 240fps slo-mo AirDropped as a
30fps render plays 4x slow (measured against the real-time iPad audio), so its
real frame rate is 120. Real time = clip time / slowdown.
"""

from __future__ import annotations

import wave

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

from pipeline.pose import smooth

L_WRIST, R_WRIST, L_HIP, R_HIP, L_SH, R_SH = 15, 16, 23, 24, 11, 12


def torso_px(img: np.ndarray) -> float:
    sh = (img[:, L_SH, :2] + img[:, R_SH, :2]) / 2
    hp = (img[:, L_HIP, :2] + img[:, R_HIP, :2]) / 2
    return float(np.nanmedian(np.linalg.norm(sh - hp, axis=1)))


def _wrist_track(raw: dict, wrist: int, slowdown: float, win: int | None = None) -> np.ndarray:
    """Hip-relative image trajectory in torso lengths, smoothed in real seconds."""
    if win is None:
        win = max(3, int(round(.06 * float(raw["fps"]) * slowdown)) | 1)
    img = raw["img"]
    hip = (img[:, L_HIP, :2] + img[:, R_HIP, :2]) / 2
    return smooth(img[:, wrist, :2] - hip, win) / torso_px(img)


def wrist_speed(raw: dict, wrist: int = R_WRIST, slowdown: float = 1.0, win: int | None = None) -> np.ndarray:
    """Hip-relative wrist speed in torso-lengths per REAL second, one value per frame."""
    x = _wrist_track(raw, wrist, slowdown, win)
    fps_real = float(raw["fps"]) * slowdown
    sp = np.linalg.norm(np.diff(x, axis=0), axis=1) * fps_real
    return np.concatenate([[0.0], sp])


def _swing_pattern(track: np.ndarray, peak: int, fps_real: float) -> bool:
    """Conservative 2D pullback/sweep/follow-through heuristic, not a ball-hit detector.

    Project onto the local impact-motion direction so mirroring, hand choice and
    image rotation do not hard-code forehand/backhand movement. Distances are in
    torso lengths; durations are real seconds, including slow-motion exports.
    """
    start = max(0, peak - int(.45 * fps_real))
    end = min(len(track) - 1, peak + int(.25 * fps_real))
    radius = max(1, int(round(.025 * fps_real)))
    if peak - start < .15 * fps_real or end - peak < .08 * fps_real:
        return False  # a cropped windup/follow-through is insufficient evidence
    points = track[start:end + 1]
    if not np.isfinite(points).all():
        return False
    direction = track[min(end, peak + radius)] - track[max(start, peak - radius)]
    length = np.linalg.norm(direction)
    if not np.isfinite(length) or length < 1e-6:
        return False
    projected = points @ (direction / length)
    p = peak - start
    first = max(0, p - int(.35 * fps_real))
    last = p - max(1, int(np.ceil(.05 * fps_real)))
    follow_start = p + max(1, int(np.ceil(.08 * fps_real)))
    follow = follow_start + int(np.argmax(projected[follow_start:]))
    # A preceding feed may start below the real backswing's turning point.
    # Consider local turns instead of letting an unrelated global minimum win.
    turns, _ = find_peaks(-projected, prominence=.10)
    for turn in turns:
        if not first <= turn <= last:
            continue
        back_end = turn - max(1, int(np.ceil(.05 * fps_real)))
        if back_end < 0:
            continue
        pullback = projected[max(0, turn - int(.25 * fps_real)):back_end + 1].max() - projected[turn]
        sweep = projected[follow] - projected[turn]
        path_length = np.linalg.norm(np.diff(points[turn:follow + 1], axis=0), axis=1).sum()
        coherence = np.linalg.norm(points[follow] - points[turn]) / max(path_length, 1e-9)
        if (pullback >= .12 and projected[p] - projected[turn] >= .25
                and projected[follow] - projected[p] >= .10 and sweep >= .50 and coherence >= .60):
            return True
    return False


def audio_hits(wav_path: str, min_gap_s: float = 0.4, rise_db: float = 20.0) -> np.ndarray:
    """Times (clip seconds) of sharp transients (ball hits, claps) in a 16 kHz mono wav."""
    try:
        stream = wave.open(wav_path)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Invalid hits WAV; supply 16 kHz mono PCM16") from exc
    with stream as w:
        sr = w.getframerate()
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or sr != 16000:
            raise ValueError("hits WAV must be 16 kHz mono PCM16 in camera A playback time")
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    if len(x) < sr // 10:
        return np.array([], dtype=float)
    x = sosfiltfilt(butter(4, [1500, 7000], btype="band", fs=sr, output="sos"), x)
    hop = sr // 200
    n = len(x) // hop * hop
    db = 20 * np.log10(np.sqrt((x[:n] ** 2).reshape(-1, hop).mean(1)) + 1e-6)
    pk, _ = find_peaks(db, height=np.median(db) + rise_db, distance=int(min_gap_s * 200), prominence=15)
    return pk / 200.0


def find_swings(
    raw: dict,
    slowdown: float = 1.0,
    min_speed: float = 8.0,
    min_gap_real_s: float = 0.5,
    hits: np.ndarray | None = None,
    confirm_s: float = 0.6,
    wrist: int = R_WRIST,
    speed_fallback: bool = False,
    require_audio: bool = False,
) -> list[dict]:
    """Return [{"peak": frame, "start": frame, "end": frame, "speed": .., "hit": t|None}]."""
    if len(raw["t"]) < 2:
        return []
    fps = float(raw["fps"])
    track = _wrist_track(raw, wrist, slowdown)
    sp = np.concatenate([[0.0], np.linalg.norm(np.diff(track, axis=0), axis=1) * fps * slowdown])
    gap = max(1, int(min_gap_real_s * fps * slowdown))
    pk, _ = find_peaks(np.nan_to_num(sp, nan=0., posinf=0., neginf=0.),
                       height=min_speed, prominence=min_speed * .25)
    # Filter before enforcing spacing: an unrelated fast feed must not suppress
    # the nearby real swing merely because its peak happens to be larger.
    patterns = {int(p): _swing_pattern(track, int(p), fps * slowdown) for p in pk}
    candidates = [int(p) for p in pk if patterns[int(p)] or speed_fallback]
    # Confirm before spacing, so an unconfirmed feed cannot suppress a hit.
    matched = {}
    for p in candidates:
        if hits is not None and len(hits):
            nearest = float(hits[np.argmin(np.abs(hits - raw["t"][p]))])
            if abs(nearest - raw["t"][p]) / slowdown <= confirm_s:
                matched[p] = nearest
    if require_audio:
        candidates = [p for p in candidates if p in matched]
    selected = []
    for p in sorted(candidates, key=lambda p: sp[p], reverse=True):
        if all(abs(p - other) >= gap for other in selected):
            selected.append(p)
    t = raw["t"]
    out = []
    pre, post = max(1, int(0.45 * fps * slowdown)), max(1, int(0.35 * fps * slowdown))
    for p in sorted(selected):
        hit = matched.get(p)
        out.append({
            "peak": int(p),
            "start": int(max(0, p - pre)),
            "end": int(min(len(t) - 1, p + post)),
            "speed": float(sp[p]),
            "hit": hit,
            "detection": "pattern" if patterns[p] else "speed_peak",
        })
    return out
