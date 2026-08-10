"""
reddit_client.py
Thin wrapper around PRAW for authenticating and submitting text posts.

Uses a permanent OAuth refresh token instead of username/password — get one
by running get_refresh_token.py locally, once. Your Reddit password is never
stored or used by this script.
"""

import os
import random

import praw
from praw.exceptions import RedditAPIException

REDDIT_TITLE_MAX = 300

SUBREDDITS = [s.strip() for s in os.environ["SUBREDDITS"].split(",") if s.strip()]
if not SUBREDDITS:
    raise ValueError("SUBREDDITS must be a non-empty comma-separated list of subreddits")


def get_reddit_client():
    user_agent = os.environ.get("REDDIT_USER_AGENT")
    if not user_agent:
        raise ValueError(
            "REDDIT_USER_AGENT must be set (e.g. 'my-bot/1.0 by u/username') — "
            "Reddit requires a descriptive user agent"
        )
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        refresh_token=os.environ["REDDIT_REFRESH_TOKEN"],
        user_agent=user_agent,
    )


def pick_subreddit(recent_posts, avoid_last_n: int = 3):
    """Avoid posting to the same subreddit twice in a row (or last N times)."""
    recently_used = {p["subreddit"] for p in recent_posts[:avoid_last_n]}
    choices = [s for s in SUBREDDITS if s not in recently_used] or SUBREDDITS
    return random.choice(choices)


def _configured_flair(subreddit_name: str):
    """Flair text for a subreddit from SUBREDDIT_FLAIRS='webdev:Question,css:Review'."""
    raw = os.environ.get("SUBREDDIT_FLAIRS", "")
    for pair in raw.split(","):
        if ":" not in pair:
            continue
        sub, flair_text = pair.split(":", 1)
        if sub.strip().lower() == subreddit_name.lower():
            return flair_text.strip() or None
    return None


def _auto_flair(subreddit):
    """Pick the first available link-flair template (for subs that require flair)."""
    try:
        for template in subreddit.flair.link_templates:
            flair_id = template.get("flair_template_id") or template.get("id")
            if flair_id:
                return flair_id, template.get("flair_text")
    except Exception:
        pass
    return None, None


def _requires_flair(exc: RedditAPIException) -> bool:
    for item in exc.items:
        if item.error_type in ("REQUIRED_FLAIR", "INVALID_FLAIR"):
            return True
    return "flair" in str(exc).lower()


def _submit(subreddit, title: str, body: str, **kwargs):
    title = title.strip()
    if len(title) > REDDIT_TITLE_MAX:
        title = title[: REDDIT_TITLE_MAX - 1].rstrip() + "\u2026"
    return subreddit.submit(title=title, selftext=body, **kwargs).url


def submit_post(reddit, subreddit_name: str, title: str, body: str):
    subreddit = reddit.subreddit(subreddit_name)

    flair_text = _configured_flair(subreddit_name)
    if flair_text:
        try:
            return _submit(subreddit, title, body, flair_text=flair_text)
        except RedditAPIException:
            pass  # configured flair rejected -> fall through to auto-detection

    try:
        return _submit(subreddit, title, body)
    except RedditAPIException as exc:
        if not _requires_flair(exc):
            raise
        flair_id, fallback_text = _auto_flair(subreddit)
        if flair_id:
            return _submit(subreddit, title, body, flair_id=flair_id)
        if fallback_text:
            return _submit(subreddit, title, body, flair_text=fallback_text)
        raise