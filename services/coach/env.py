"""Load API keys from the repo-root env file. Owners: aryan and Dev.

Keys live only in `.env.local` (or `.env`) at the repo root, never in code.
This module only loads them into the process environment; it never prints them.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load `.env.local`, then `.env`, without overriding variables already set."""
    for name in (".env.local", ".env"):
        path = REPO_ROOT / name
        if path.is_file():
            load_dotenv(path, override=False)


def require_env(name: str) -> str:
    """Return an env var, or raise a clear error that names the variable (not its value)."""
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to .env.local at the repo root.")
    return value
