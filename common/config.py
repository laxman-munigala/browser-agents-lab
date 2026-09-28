"""Environment loading for the lab.

Order: real environment variables win, then the lab's .env (gitignored), then,
for the three API keys only, `export KEY=...` lines in ~/.bashrc. The last step
lets scripts run from shells that never sourced ~/.bashrc (cron, IDE runners,
non-interactive tools) without copying keys into another file.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

LAB_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = LAB_ROOT / "runs"

API_KEYS = ("BROWSER_USE_API_KEY", "TINYFISH_API_KEY", "OPENROUTER_API_KEY")

_loaded = False


def load_env() -> None:
    """Load .env and fill missing API keys from ~/.bashrc. Safe to call repeatedly."""
    global _loaded
    if _loaded:
        return
    load_dotenv(LAB_ROOT / ".env", override=False)
    missing = [k for k in API_KEYS if not os.environ.get(k)]
    if missing:
        bashrc = Path.home() / ".bashrc"
        try:
            text = bashrc.read_text()
        except OSError:
            text = ""
        for key in missing:
            m = re.search(rf"^\s*export\s+{key}=(['\"]?)(.+?)\1\s*$", text, re.M)
            if m:
                os.environ[key] = m.group(2)
    _loaded = True


def env(name: str, default: str | None = None) -> str | None:
    load_env()
    return os.environ.get(name, default)


def require(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f"{name} is not set. Add it to ~/.bashrc or browser-agents-lab/.env.")
    return value


def mock_app_url() -> str:
    return (env("MOCK_APP_URL") or "http://localhost:8787").rstrip("/")
