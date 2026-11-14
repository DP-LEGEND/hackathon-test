"""POST /compare refuses a fix that would edit a guessed measurement, with the reason (422)."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

import pipeline.server as server

SAMPLE = Path(__file__).resolve().parents[3] / "public" / "swings" / "swing_2116_bh_stereo.json"


def _wrist_guessed() -> dict:
    s = json.loads(SAMPLE.read_text())
    for f in s["frames"]:
        f.pop("filled", None)
        f.pop("visibility", None)
    for k in range(56, 63):
        s["frames"][k]["filled"] = [False] * 33
        s["frames"][k]["filled"][16] = True
    s.setdefault("metadata", {})["hand"] = "R"
    s["side"] = "backhand"
    return s


def test_guessed_fix_returns_the_unchanged_comparison(monkeypatch):
    monkeypatch.setattr(server, "load_swing", lambda identifier: _wrist_guessed())
    client = TestClient(server.app)
    r = client.post("/compare/x", json={"fix": "straighten_elbow", "amount": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["noCorrection"] is True and body["fix"]["id"] == "straighten_elbow" and body["fix"]["amount"] == 0.0
    assert "couldn't see the right elbow around contact" in body["ghostNote"]
    assert client.post("/compare/x", json={"fix": "no_such_fix", "amount": 1}).status_code == 422
    ok = client.post("/compare/x", json={"fix": "turn_shoulders_more", "amount": 15})
    assert ok.status_code == 200 and list(ok.json()["delta"]["metrics"]) == ["shoulder_turn_deg"]
