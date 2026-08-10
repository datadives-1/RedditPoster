"""
main.py
Single-run script, triggered by a GitHub Actions scheduled workflow (see
.github/workflows/post.yml). Each invocation:
  1. Sleeps a random jitter (so two runs triggered at fixed cron times don't
     post at exactly predictable minutes).
  2. Generates a unique post via AWS Bedrock (Nova).
  3. Picks a subreddit, posts directly.
  4. Updates history.json (the workflow commits this back to the repo).
"""

import os
import random
import time
from datetime import datetime

import dotenv

dotenv.load_dotenv()

import storage
import content_generator
import telegram_client
from reddit_client import get_reddit_client, pick_subreddit, submit_post

# Keep this small: GitHub Actions bills by wall-clock job time, so every
# minute slept here is a billable minute. Default cap = ~15 min/run
# (avg 7.5 min x 3 runs/day x 30 days ~= 680 min/month, comfortably under
# the 2,000 free private-repo minutes).
MAX_JITTER_MINUTES = int(os.environ.get("MAX_JITTER_MINUTES", "15"))
MAX_JITTER_SECONDS = random.randint(0, MAX_JITTER_MINUTES * 60)


def main():
    print(f"[{datetime.now()}] Sleeping {MAX_JITTER_SECONDS}s of random jitter before posting...")
    time.sleep(MAX_JITTER_SECONDS)

    recent_posts = storage.get_recent_posts(limit=30)
    title, body, angle = content_generator.generate_unique_post(recent_posts)

    reddit = get_reddit_client()
    subreddit_name = pick_subreddit(recent_posts)

    url = submit_post(reddit, subreddit_name, title, body)
    storage.add_post(
        title, body, subreddit_name, angle=angle, url=url, status="posted"
    )

    print(f"[{datetime.now()}] Posted to r/{subreddit_name}: {title}  ({url})")
    telegram_client.send_message(
        f"\U0001F916 Posted to r/{subreddit_name}\n{title}\n{url}"
    )


if __name__ == "__main__":
    main()