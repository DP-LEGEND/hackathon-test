"""Adaption status script tests (fake API responses only; no network, no keys)."""

import io
import json
import urllib.error

import pytest

from physics import adaption_status as st

RUN = {"id": "run_1", "status": "running", "model": "Qwen/Qwen3.5-2B", "training_method": "instruction",
       "iterations_completed": 1, "max_iterations": 3, "target_win_rate": 0.7, "best_win_rate": 0.58,
       "created_at": "2026-11-15T04:00:00Z", "completed_at": None, "download_available": False, "error": None}


def fake(responses):
    calls = []

    def fetch(path, what):
        calls.append(path)
        return responses[path]
    fetch.calls = calls
    return fetch


def run_main(capsys, argv, fetch):
    st.main(argv, fetch=fetch)
    return capsys.readouterr().out


def test_running_run_shows_progress_and_no_paste_line(capsys, tmp_path):
    out = run_main(capsys, ["run_1", "--state", str(tmp_path / "none.json")], fake({"/api/v1/autoscientist/run_1": RUN}))
    assert "status: running" in out and "iterations: 1 of 3" in out and "58%" in out and "SIMULATED" in out
    assert "not done yet" in out and "--adaption-win-rate" not in out


def test_succeeded_run_prints_the_win_rate_line_for_the_report(capsys, tmp_path):
    done = dict(RUN, status="succeeded", iterations_completed=2, best_win_rate=0.64,
                completed_at="2026-11-15T05:10:00Z", download_available=True)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"dataset_id": "ds_1", "run_id": "run_1"}))
    out = run_main(capsys, ["--state", str(state)], fake({"/api/v1/autoscientist/run_1": done}))
    assert ('--adaption-win-rate "64% vs base Qwen/Qwen3.5-2B (Adaption AutoScientist, best of 2 iterations; '
            "Adaption's own eval, not our test rows)\"") in out


def test_failed_run_shows_the_error(capsys, tmp_path):
    out = run_main(capsys, ["run_1", "--state", str(tmp_path / "x.json")],
                   fake({"/api/v1/autoscientist/run_1": dict(RUN, status="failed", error="out of credits")}))
    assert "error: out of credits" in out


def test_dataset_only_state_says_no_run_started(capsys, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"dataset_id": "ds_1", "dataset_name": "train", "run_id": None}))
    out = run_main(capsys, ["--state", str(state)],
                   fake({"/api/v1/datasets/ds_1/status": {"status": "succeeded", "row_count": 1373}}))
    assert "No AutoScientist run started yet" in out and "1373 rows" in out


def test_missing_key_exits_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "REPO_ROOT", tmp_path)  # no .env.local here
    monkeypatch.delenv("ADAPTION_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="ADAPTION_API_KEY is not set"):
        st.main(["run_1", "--state", str(tmp_path / "x.json")])


def test_rejected_key_message_never_contains_the_key(monkeypatch):
    def deny(req, timeout, context):
        assert req.get_header("Authorization") == "Bearer pt_live_SECRET"
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(st.urllib.request, "urlopen", deny)
    with pytest.raises(st.AdaptionError) as exc:
        st.make_fetch("pt_live_SECRET")("/api/v1/autoscientist/run_1", "run run_1")
    assert "rejected" in str(exc.value) and "SECRET" not in str(exc.value)
