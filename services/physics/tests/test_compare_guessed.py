"""compare() never shows a number read from a guessed joint."""

import copy
import json
from pathlib import Path

from physics.compare import compare

SWINGS = Path(__file__).resolve().parents[3] / "public" / "swings"


def _unflagged(path: str) -> dict:
    s = json.loads((SWINGS / path).read_text())
    for f in s["frames"]:
        f.pop("filled", None)
        f.pop("visibility", None)
    return s


def test_unflagged_swing_keeps_every_metric():
    r = compare(_unflagged("swing_fh_over_rotation.json"), "turn_shoulders_less", 20, fps_real=120, hand="R",
                side="forehand")
    assert r["notMeasured"] == {}
    assert all(v is not None for v in r["you"]["metrics"].values())
    assert r["delta"]["metrics"]["shoulder_turn_deg"]["change"] is not None


def test_guessed_wrist_blanks_wrist_elbow_and_stance_rows():
    s = _unflagged("swing_2116_bh_stereo.json")
    c = 59
    for k in range(c - 3, c + 4):
        s["frames"][k]["filled"] = [False] * 33
        s["frames"][k]["filled"][16] = True  # right wrist guessed around contact
    r = compare(s, "turn_shoulders_more", 15, fps_real=120, hand="R", side="backhand")
    for k in ("wrist_at_contact_deg", "wrist_release_ms", "stance_open_deg", "elbow_at_contact_deg"):
        assert k in r["notMeasured"], k
        row = r["delta"]["metrics"][k]
        assert row["you"] is None and row["ghost"] is None and row["change"] is None
        assert "notMeasured" in row
        assert r["you"]["metrics"][k] is None and r["ghost"]["metrics"][k] is None
    # the shoulder turn doesn't read the wrist, so it's still a measurement
    assert r["delta"]["metrics"]["shoulder_turn_deg"]["change"] is not None
    assert not any("wrist" in line or "stance" in line for line in r["delta"]["summary"])


def test_saved_backhand_sample_has_no_guessed_numbers():
    s = json.loads((SWINGS / "swing_2116_bh_stereo.json").read_text())
    r = compare(copy.deepcopy(s), "turn_shoulders_more", 15, fps_real=120, hand="R", side="backhand")
    for k in r["notMeasured"]:
        assert r["delta"]["metrics"][k]["you"] is None
