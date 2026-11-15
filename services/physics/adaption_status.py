"""Status of the Adaption AutoScientist run, and its win rate when done. Owner: aryan.

    # from services/
    python -m physics.adaption_status                 # run id from ../data/raw/adaption/autoscientist_run.json
    python -m physics.adaption_status <run id>

Read only: it never starts, changes or cancels anything. AutoScientist trains a LoRA on the
SIMULATED training split (data/raw/adaption/autoscientist_train.jsonl; the test split was never
uploaded) and scores it as a win rate against its own base model on evaluations Adaption derives
from the uploaded data. That win rate is Adaption's measure, not accuracy on our held-out test
rows, so it isn't comparable with the eval tables. ADAPTION_API_KEY is loaded from .env.local
(repo root, or --env-dir) into this process only and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

DEFAULT_BASE_URL = "https://api.prod.adaptionlabs.ai"
DEFAULT_STATE = "../data/raw/adaption/autoscientist_run.json"
REPO_ROOT = Path(__file__).resolve().parents[2]

Fetch = Callable[[str, str], dict]


class AdaptionError(RuntimeError):
    pass


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def make_fetch(api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> Fetch:
    """GET helper for the Adaption API. Errors never include the key."""
    def fetch(path: str, what: str) -> dict:
        req = urllib.request.Request(base_url.rstrip("/") + path,
                                     headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AdaptionError("Adaption rejected ADAPTION_API_KEY") from None
            if exc.code == 404:
                raise AdaptionError(f"{what} not found on Adaption") from None
            raise AdaptionError(f"Adaption returned HTTP {exc.code} for {what}") from None
        except urllib.error.URLError as exc:
            raise AdaptionError(f"couldn't reach Adaption ({exc.reason})") from None
    return fetch


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def describe_run(run: dict) -> list[str]:
    """Plain lines for one AutoScientist run (the API's run object)."""
    lines = [
        f"AutoScientist run {run.get('id')} (SIMULATED training data)",
        f"  status: {run.get('status')}   base model: {run.get('model')}   method: {run.get('training_method')}",
        f"  iterations: {run.get('iterations_completed', 0):.0f} of {run.get('max_iterations', 0):.0f}   "
        f"target win rate: {_pct(run.get('target_win_rate'))}",
        f"  best win rate vs base model so far: {_pct(run.get('best_win_rate'))}",
        f"  started {run.get('created_at')}" + (f", finished {run['completed_at']}" if run.get("completed_at") else ""),
    ]
    status = run.get("status")
    if status == "failed":
        lines.append(f"  error: {run.get('error')}")
    elif status == "succeeded":
        win = run.get("best_win_rate")
        lines.append(f"  download available: {bool(run.get('download_available'))}")
        if win is not None:
            note = (f"{_pct(win)} vs base {run.get('model')} (Adaption AutoScientist, best of "
                    f"{run.get('iterations_completed', 0):.0f} iterations; Adaption's own eval, not our test rows)")
            lines += ["", "Put it in the eval report:",
                      f'  python -m physics.adaption_eval --data ../data/raw/adaption --adaption-win-rate "{note}"']
    elif status in ("pending", "running"):
        lines.append("  not done yet; run this again later")
    return lines


def status_lines(fetch: Fetch, run_id: Optional[str], state: dict) -> list[str]:
    if run_id:
        return describe_run(fetch(f"/api/v1/autoscientist/{run_id}", f"run {run_id}"))
    if state.get("run_id"):
        return describe_run(fetch(f"/api/v1/autoscientist/{state['run_id']}", f"run {state['run_id']}"))
    if state.get("dataset_id"):
        ds = fetch(f"/api/v1/datasets/{state['dataset_id']}/status", f"dataset {state['dataset_id']}")
        return [f"No AutoScientist run started yet. Uploaded training dataset {state['dataset_id']} "
                f"({state.get('dataset_name')}): status {ds.get('status')}, {ds.get('row_count')} rows (SIMULATED)."]
    raise AdaptionError("no run id given and no dataset or run in the state file")


def load_env(env_dir: Optional[str]) -> None:
    from dotenv import load_dotenv
    for base in [REPO_ROOT] + ([Path(env_dir).expanduser()] if env_dir else []):
        for name in (".env.local", ".env"):
            if (base / name).is_file():
                load_dotenv(base / name, override=False)


def main(argv: list[str] | None = None, fetch: Optional[Fetch] = None) -> None:
    p = argparse.ArgumentParser(description="Status and win rate of the Adaption AutoScientist run (read only).")
    p.add_argument("run_id", nargs="?", help="AutoScientist run id (default: from the state file)")
    p.add_argument("--state", default=DEFAULT_STATE, help="JSON written when the run was launched (git-ignored)")
    p.add_argument("--env-dir", default=None, help="extra folder whose .env.local holds ADAPTION_API_KEY")
    a = p.parse_args(argv)
    state_path = Path(a.state)
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    if not a.run_id and not state:
        sys.exit(f"no run id given and no state file at {state_path}")
    try:
        if fetch is None:
            load_env(a.env_dir)
            key = os.environ.get("ADAPTION_API_KEY", "").strip()
            if not key:
                sys.exit("ADAPTION_API_KEY is not set (put it in .env.local; it is never printed)")
            fetch = make_fetch(key, os.environ.get("ADAPTION_BASE_URL") or DEFAULT_BASE_URL)
        print("\n".join(status_lines(fetch, a.run_id, state)))
    except AdaptionError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
