"""Shared MOCK sessions for the wrist tests (built once per test run, in a temp folder)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from wrist.load import Recording, load_recording
from wrist.metrics import wrist_metrics
from wrist.sync import read_contacts, synchronise
from wrist.synth import make_session


class Session:
    def __init__(self, folder: Path, **kwargs: Any):
        self.truth = make_session(folder, **kwargs)
        self.folder = folder
        self.rec: Recording = load_recording(self.truth["export"])
        self.contacts = read_contacts(self.truth["contacts"])
        self.sync = synchronise(self.rec, self.contacts, video_tap_s=self.truth["video_tap_s"])
        self.metrics, self.series = wrist_metrics(self.rec, self.sync)


@pytest.fixture(scope="session")
def session(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """Default mock: 5 normal then 5 rolled swings, phone-to-world quaternions."""
    return Session(tmp_path_factory.mktemp("wrist-default"))


@pytest.fixture(scope="session")
def session_inverse(tmp_path_factory: pytest.TempPathFactory) -> Session:
    """Same swings, but the quaternions point world-to-phone."""
    return Session(tmp_path_factory.mktemp("wrist-inverse"), quat_convention="world_to_body", seed=1)
