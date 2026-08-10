"""
draft.py
Semi-automated flow that needs NO Reddit API access/approval:

  1. Generates a unique post via AWS Bedrock (Nova).
  2. Records it in history.json so nothing repeats (works alongside main.py).
  3. Sends you a Telegram notification with the title + a ready-to-post link.
  4. Opens the prefilled Reddit submit page in your browser — you review
     and click "Post". No API credentials, no approval, no ban-risk pattern.

Run it any time you want a draft; schedule it 5x/day if you want cadence.
Requires: same AWS/Reddit env vars as the rest of the project + your
browser session logged into the bot account.

Usage:
    python draft.py            # generate 1 draft + open browser tab
    python draft.py --count 5  # generate 5 unique drafts
    python draft.py --no-open  # generate + notify only, no browser
"""

import argparse
import webbrowser
from urllib.parse import quote_plus

import dotenv

dotenv.load_dotenv()

import storage
import content_generator
import telegram_client
from reddit_client import pick_subreddit


def build_submit_url(subreddit_name: str, title: str, body: str) -> str:
    params = f"title={quote_plus(title)}&text={quote_plus(body)}&selftext=true"
    return f"https://www.reddit.com/r/{subreddit_name}/submit?{params}"


def main():
    parser = argparse.ArgumentParser(description="Generate a unique Reddit draft.")
    parser.add_argument("--count", type=int, default=1, help="number of drafts to generate")
    parser.add_argument("--no-open", action="store_true", help="don't open the browser tab(s)")
    args = parser.parse_args()

    for i in range(args.count):
        recent_posts = storage.get_recent_posts(limit=30)
        title, body, angle = content_generator.generate_unique_post(recent_posts)
        subreddit_name = pick_subreddit(recent_posts)

        submit_url = build_submit_url(subreddit_name, title, body)
        storage.add_post(
            title, body, subreddit_name, angle=angle, url=submit_url, status="drafted"
        )

        message = (
            f"\U0001F4E2 Reddit draft {i + 1}/{args.count}\n"
            f"r/{subreddit_name}\n"
            f"{title}\n\n"
            f"Review and post here:\n{submit_url}"
        )
        telegram_client.send_message(message)
        print(f"Draft {i + 1}/{args.count} for r/{subreddit_name}: {title}")
        if not args.no_open:
            webbrowser.open(submit_url)


if __name__ == "__main__":
    main()