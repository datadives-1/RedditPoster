"""
storage.py
Post history lives in history.json, committed back to the repo by the
workflow after every run. No external database needed — the repo IS the
database, which is why this can run entirely inside GitHub Actions.
"""

import json
import os
import time

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "history.json")
MAX_HISTORY = 200


def get_recent_posts(limit: int = 30):
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        # Corrupt/partial file (e.g. a run died mid-write). Back it up so the
        # bot can recover and keep posting instead of failing forever.
        try:
            os.replace(HISTORY_FILE, HISTORY_FILE + ".corrupt")
        except OSError:
            pass
        print(
            f"[storage] Warning: {os.path.basename(HISTORY_FILE)} unreadable "
            f"({exc}). Backed it up and starting fresh."
        )
        return []
    return data[:limit]  # stored newest-first


def add_post(
    title: str,
    body: str,
    subreddit: str,
    angle: str = None,
    url: str = None,
    status: str = "drafted",
):
    data = get_recent_posts(limit=MAX_HISTORY)
    entry = {
        "title": title,
        "body": body,
        "subreddit": subreddit,
        "angle": angle,
        "url": url,
        "status": status,
        "timestamp": int(time.time()),
    }
    data.insert(0, entry)
    data = data[:MAX_HISTORY]

    # Atomic write: write to a temp file then rename, so a crash mid-write
    # can never leave history.json half-written/corrupt.
    tmp_file = HISTORY_FILE + ".tmp"
    try:
        with open(tmp_file, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_file, HISTORY_FILE)
    finally:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass
    return entry