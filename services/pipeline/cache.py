"""Versioned, non-pickle pose cache. Reconstruction options do not invalidate it."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
import tempfile
from zipfile import BadZipFile

import numpy as np


def file_digest(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate(raw: dict) -> None:
    n = len(raw["t"])
    if (np.asarray(raw["t"]).shape != (n,) or n < 2
            or np.asarray(raw["fps"]).shape != () or not np.isfinite(raw["fps"])
            or raw["fps"] <= 0 or np.asarray(raw["size"]).shape != (2,)
            or not np.isfinite(raw["size"]).all() or min(raw["size"]) <= 0
            or not np.isfinite(raw["t"]).all() or np.any(np.diff(raw["t"]) <= 0)
            or raw["img"].shape != (n, 33, 3) or raw["world"].shape != (n, 33, 3)
            or raw["vis"].shape != (n, 33)):
        raise ValueError("Invalid cached pose arrays")


def extract_pair(clip_a: str, clip_b: str, model_path: str, output: Path,
                 extractor: Callable[..., dict], *, no_cache: bool = False) -> tuple[dict, dict]:
    """Cache both cameras before calibration, so failed reconstruction can be retried.

    Content hashes include camera order, weights and extraction settings. No pickle
    is loaded; corrupt/stale caches are recomputed. Atomic replacement prevents a
    killed cache write from destroying the last complete extraction.
    """
    identity = json.dumps({"version": 1, "max_width": 1280,
                           "clips": [file_digest(clip_a), file_digest(clip_b)],
                           "model": file_digest(model_path)}, sort_keys=True)
    cache = output / "raw_cache.npz"
    if (output.exists() and not output.is_dir()) or (cache.exists() and not cache.is_file()):
        raise ValueError("Pose cache needs a directory and a regular raw_cache.npz file")
    fields = ("fps", "size", "t", "img", "world", "vis")
    if cache.is_file() and not no_cache:
        try:
            with np.load(cache, allow_pickle=False) as saved:
                if saved["identity"].item() == identity:
                    pair = tuple({key: saved[f"{camera}_{key}"] for key in fields}
                                 for camera in ("a", "b"))
                    for raw in pair:
                        _validate(raw)
                    return pair
        except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile):
            # The original videos/model remain the authority, never a bad cache.
            pass
    pair = tuple(extractor(clip, model_path=model_path, max_width=1280)
                 for clip in (clip_a, clip_b))
    for raw in pair:
        _validate(raw)
    output.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output, prefix=".raw-cache-", suffix=".npz",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            arrays = {f"{camera}_{key}": np.asarray(raw[key])
                      for camera, raw in zip(("a", "b"), pair) for key in fields}
            np.savez_compressed(stream, identity=np.asarray(identity), **arrays)
        os.replace(temporary, cache)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return pair
