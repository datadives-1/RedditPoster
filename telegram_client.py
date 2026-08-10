"""
telegram_client.py
Sends Telegram notifications via the Bot API using only the stdlib
(no new dependencies). Every notification is optional: if the Telegram
env vars are missing, send_message() prints a warning and returns False
instead of crashing the script.
"""

import os
import urllib.parse
import urllib.request


def send_message(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(
            "[telegram] skipped: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "(see .env.example) to receive notifications"
        )
        return False
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=payload, timeout=15) as response:
            if response.status == 200:
                return True
    except Exception as exc:
        print(f"[telegram] send failed: {exc}")
    return False