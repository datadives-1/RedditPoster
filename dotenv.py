"""
dotenv.py
Tiny .env loader (no third-party dependency). Reads KEY=VALUE pairs from
.env next to this file into os.environ, without overriding variables that
are already set (so CI secrets / real env vars always win).
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def load_dotenv() -> None:
    if not ENV_FILE.exists():
        return
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value