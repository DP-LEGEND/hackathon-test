"""Shared MOCK sessions for the wrist tests (built once per test run, in a temp folder)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pytest

from wrist.fuse import read_swings
from wrist.load import Recording, load_recording
from wrist.metrics import wrist_report
from wrist.sync import read_contacts, synchronise
from wrist.synth import make_session


class Session:
    def __init__(self, folder: Path, drop_orientation: bool = False,
                 gyro_bias_dps: Optional[Sequence[float]] = None, **kwargs: Any):
        self.truth = make_session(folder, **kwargs)
        self.folder = folder
        if drop_orientation:
            (Path(self.truth["export"]) / "Orientation.csv").unlink()
        self.rec: Recording = load_recording(self.truth["export"])
        if gyro_bias_dps is not None:
            self.rec.gyro = self.rec.gyro + np.radians(gyro_bias_dps)
        self.contacts = read_contacts(self.truth["contacts"])
        self.sync = synchronise(self.rec, self.contacts, video_tap_s=self.truth["video_tap_s"])
        self.swings = read_swings(self.truth["swings_dir"]) if self.truth["swings_dir"] else None
        self.metrics, self.series, self.filled = wrist_report(self.rec, self.sync, swings=self.swings)


@pytest.fixture(scope="session")
def session(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """Default mock: 5 normal then 5 rolled swings, phone-to-world quaternions."""
    return Session(tmp_path_factory.mktemp("wrist-default"))


@pytest.fixture(scope="session")
def session_inverse(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """Same swings, but the quaternions point world-to-phone."""
    return Session(tmp_path_factory.mktemp("wrist-inverse"), quat_convention="world_to_body", seed=1)


@pytest.fixture(scope="session")
def fused(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """Default swings plus MOCK camera swings (occluded wrist or elbow near contact); swing 4 is a mishit."""
    return Session(tmp_path_factory.mktemp("wrist-fused"), camera=True, mishit=(3,))


GYRO_BIAS_DPS = (0.5, -1.0, 1.5)  # an uncalibrated phone gyro's offset, for the fallback


@pytest.fixture(scope="session")
def shadow(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """`fused` again, except swing 5 (synth-05) is a shadow swing: the same motion, no ball, no spike."""
    return Session(tmp_path_factory.mktemp("wrist-shadow"), camera=True, mishit=(3,), shadow=(4,))


@pytest.fixture(scope="session")
def no_orientation(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """`fused` swings with no Orientation.csv and a biased gyro: the integrated-gyro fallback."""
    return Session(tmp_path_factory.mktemp("wrist-gyro-only"), drop_orientation=True,
                   gyro_bias_dps=GYRO_BIAS_DPS, camera=True, mishit=(3,))
