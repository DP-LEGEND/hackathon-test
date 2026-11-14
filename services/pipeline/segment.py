"""Find individual swings in a long clip. Owner: Dev.

A swing = a peak in hip-relative wrist speed (image space, smoothed, scaled by
torso length so it works at any distance). Optionally confirmed by a ball-hit
transient in the audio (1.5-7 kHz band) within `confirm_s` seconds.

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


def wrist_speed(raw: dict, wrist: int = R_WRIST, slowdown: float = 1.0, win: int = 15) -> np.ndarray:
    """Hip-relative wrist speed in torso-lengths per REAL second, one value per frame."""
    img = raw["img"]
    hip = (img[:, L_HIP, :2] + img[:, R_HIP, :2]) / 2
    x = smooth(img[:, wrist, :2] - hip, win)
    fps_real = float(raw["fps"]) * slowdown
    sp = np.linalg.norm(np.diff(x, axis=0), axis=1) / torso_px(img) * fps_real
    return np.concatenate([[0.0], sp])


def audio_hits(wav_path: str, min_gap_s: float = 0.4, rise_db: float = 20.0) -> np.ndarray:
    """Times (clip seconds) of sharp transients (ball hits, claps) in a 16 kHz mono wav."""
    w = wave.open(wav_path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    x = sosfiltfilt(butter(4, [1500, 7000], btype="band", fs=sr, output="sos"), x)
    hop = sr // 200
    n = len(x) // hop * hop
    db = 20 * np.log10(np.sqrt((x[:n] ** 2).reshape(-1, hop).mean(1)) + 1e-6)
    pk, _ = find_peaks(db, height=np.median(db) + rise_db, distance=int(min_gap_s * 200), prominence=15)
    return pk / 200.0


def find_swings(
    raw: dict,
    slowdown: float = 1.0,
    min_speed: float = 6.0,
    min_gap_real_s: float = 0.5,
    hits: np.ndarray | None = None,
    confirm_s: float = 0.6,
) -> list[dict]:
    """Return [{"peak": frame, "start": frame, "end": frame, "speed": .., "hit": t|None}]."""
    sp = wrist_speed(raw, slowdown=slowdown)
    fps = float(raw["fps"])
    gap = int(min_gap_real_s * fps * slowdown)
    pk, _ = find_peaks(np.nan_to_num(sp), height=min_speed, distance=gap)
    t = raw["t"]
    out = []
    pre, post = int(0.45 * fps * slowdown), int(0.35 * fps * slowdown)
    for p in pk:
        hit = None
        if hits is not None and len(hits):
            j = np.argmin(np.abs(hits - t[p]))
            if abs(hits[j] - t[p]) <= confirm_s * slowdown / 4 + 0.15:
                hit = float(hits[j])
        out.append({
            "peak": int(p),
            "start": int(max(0, p - pre)),
            "end": int(min(len(t) - 1, p + post)),
            "speed": float(sp[p]),
            "hit": hit,
        })
    return out
