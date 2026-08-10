#!/usr/bin/env python
"""
get_refresh_token.py
Run this ONCE, locally, on your own machine (not in GitHub Actions).

It opens a Reddit authorization URL in your terminal -> you open it in a
browser -> click "Allow" -> this script catches the redirect and prints a
permanent refresh_token. Save that token as the REDDIT_REFRESH_TOKEN GitHub
Secret. Your Reddit password is never used or stored anywhere after this.

Prerequisites:
  - Reddit app must be type "web app" (not "script"), with redirect uri
    set to exactly: http://localhost:8080
  - pip install praw
  - Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET as env vars before running,
    e.g.:
      export REDDIT_CLIENT_ID=xxxx
      export REDDIT_CLIENT_SECRET=xxxx
      python get_refresh_token.py
"""

import os
import random
import socket
import sys
from urllib.parse import unquote

import praw


def receive_connection():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", 8080))
    server.listen(1)
    client = server.accept()[0]
    server.close()
    return client


def send_message(client, message):
    print(message)
    client.send(f"HTTP/1.1 200 OK\r\n\r\n{message}".encode("utf-8"))
    client.close()


def parse_query_params(data: str):
    """Parse the query string from a raw HTTP request line, tolerantly."""
    parts = data.split(" ", 2)
    if len(parts) < 2:
        return {}
    path_and_query = parts[1]
    if "?" not in path_and_query:
        return {}
    query = path_and_query.split("?", 1)[1]
    params = {}
    for token in query.split("&"):
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        params[unquote(key)] = unquote(value)
    return params


def main():
    client_id = os.environ["REDDIT_CLIENT_ID"]
    client_secret = os.environ["REDDIT_CLIENT_SECRET"]

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://localhost:8080",
        user_agent="get_refresh_token/1.0",
    )

    state = str(random.randint(0, 65000))
    # "submit" scope lets it post; "identity" lets it confirm which account.
    # duration="permanent" is what makes the refresh_token non-expiring.
    url = reddit.auth.url(["identity", "submit"], state, "permanent")
    print("Go to this URL in your browser and click Allow:\n")
    print(url)
    print("\nWaiting for you to authorize...")

    client = receive_connection()
    data = client.recv(1024).decode("utf-8")
    params = parse_query_params(data)

    if not params.get("state"):
        send_message(client, "No state parameter in the callback URL. Aborting.")
        return 1
    if state != params["state"]:
        send_message(
            client, f"State mismatch. Expected {state}, got {params['state']}. Aborting."
        )
        return 1
    if "error" in params:
        send_message(client, f"Reddit returned an error: {params['error']}")
        return 1
    if "code" not in params:
        send_message(client, "No authorization code in the callback URL. Aborting.")
        return 1

    refresh_token = reddit.auth.authorize(params["code"])
    send_message(client, "Success! Refresh token printed in your terminal — check there.")
    print("\n=== SAVE THIS AS THE 'REDDIT_REFRESH_TOKEN' GITHUB SECRET ===")
    print(refresh_token)
    print("===============================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())