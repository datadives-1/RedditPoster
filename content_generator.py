"""
content_generator.py
Generates a unique, engaging Reddit post (title + body) using an Amazon Nova
model via AWS Bedrock's Converse API. Uses recent post history as negative
examples so topics/angles don't repeat, plus a similarity check as a
second safety net.
"""

import os
import random
import re
import time
import difflib
from collections import Counter

import boto3
from botocore.exceptions import BotoCoreError, ClientError

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# amazon.nova-micro-v1:0 (cheapest/fastest) | amazon.nova-lite-v1:0 (default) | amazon.nova-pro-v1:0 (best quality)
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

DOMAIN_DESCRIPTION = os.environ.get(
    "DOMAIN_DESCRIPTION",
    "designing and building AI-powered products — product designer and frontend "
    "developer shipping AI tools, automations, and SaaS; sharing lessons from "
    "building products, automating workflows, and startup life",
)

POST_ANGLES = [
    "ask a genuine question to the subreddit about a challenge in this field",
    "share a specific lesson learned from a real project, written like a short story",
    "share a mildly controversial or contrarian opinion about a common practice, and invite debate",
    "share a before/after or small win, framed as 'here's what changed my approach'",
    "ask the community to critique or roast something specific",
    "share a mistake or failure and what you'd do differently, self-deprecating tone",
    "post a 'hot take vs common advice' comparison and ask which side people are on",
    "ask for recommendations/resources on a specific sub-topic you're genuinely stuck on",
    "share a small, weirdly specific tip that most people don't know, framed as 'PSA'",
    "describe an anonymized real client project's hardest problem and ask how others would have solved or priced it",
    "offer a free mini-critique of anyone's portfolio, site, or design in the comments — they reply, you critique",
    "ask how people scope, pitch, and price a specific type of client work you are quoting right now, with concrete numbers",
    "share one concrete thing you changed that measurably lifted engagement or conversions and invite others' before/after evidence",
]

# Angles used in the last N posts are excluded entirely; the rest are picked
# weighted toward the least-used ones so styles don't cluster.
AVOID_LAST_ANGLES = 3
ANGLE_WEIGHT_WINDOW = 10

# Throttling/service hiccups are worth retrying with backoff; anything else
# (bad creds, content policy, missing model access) should fail fast.
_RETRYABLE_CODES = {
    "ThrottlingException",
    "Throttling",
    "TooManyRequestsException",
    "InternalServerException",
    "ServiceUnavailable",
    "ModelTimeoutException",
    "ModelStreamErrorException",
}
_RETRYABLE_STATUS = {429, 500, 503}

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
TITLE_BODY_RE = re.compile(
    r"#{0,6}\s*title\s*:\s*(.*?)\s*#{0,6}\s*body\s*:", re.IGNORECASE | re.DOTALL
)


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _build_prompt(recent_titles, angle):
    history_block = "\n".join(f"- {t}" for t in recent_titles) or "(none yet)"
    return f"""You are ghostwriting a Reddit post for a real person whose domain is: {DOMAIN_DESCRIPTION}

Write ONE Reddit post using this angle: {angle}

Rules:
- Sound like a real person casually posting, not a marketer or a bot.
- Do NOT include any links or mention any website/portfolio URL in the body.
- Do NOT use marketing language, hashtags, or emoji spam.
- Never say "hire me", "DM me for work", or advertise services. If the angle
  offers help (e.g. a critique), frame it as genuine community value.
- The title must make someone want to click: specific, concrete, mildly curious.
- The body should read like a real thread people will reply to — one concrete
  situation, a real-sounding detail, and a natural ending that begs for a comment.
- Keep it specific and concrete (a real-sounding detail, number, or anecdote beats generic advice).
- End with something that invites replies (a question, an ask for opinions, etc.) where the angle calls for it.
- Grammar and spelling should be normal, correct English, written in a natural conversational voice.
- Must be meaningfully different in topic and wording from these recent posts:
{history_block}

Respond in exactly this format, nothing else:
TITLE: <post title>
BODY: <post body, 2-5 short paragraphs>
"""


def _is_retryable(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = error.get("Code", "")
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in _RETRYABLE_CODES or status in _RETRYABLE_STATUS


def _call_nova(prompt: str, max_attempts: int = 4) -> str:
    """Call Bedrock with retry + exponential backoff on throttling/5xx."""
    last_error = None
    for attempt in range(max_attempts):
        try:
            response = bedrock.converse(
                modelId=BEDROCK_MODEL_ID,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 1024, "temperature": 1.0},
            )
            return response["output"]["message"]["content"][0]["text"].strip()
        except ClientError as exc:
            if not _is_retryable(exc) or attempt == max_attempts - 1:
                raise
            last_error = exc
        except BotoCoreError:
            if attempt == max_attempts - 1:
                raise
            last_error = None
        time.sleep(2 ** (attempt + 1))
    raise last_error  # pragma: no cover - only reached if max_attempts == 0


def generate_unique_post(recent_posts, max_attempts: int = 5):
    """
    Returns (title, body, angle). Retries generation if too similar to
    recent history. recent_posts: list of dicts from storage.get_recent_posts()
    """
    recent_titles = [p["title"] for p in recent_posts]
    recent_bodies = [p["body"] for p in recent_posts]
    # Angles from the last few posts are excluded, and other angles are
    # weighted toward the least-used ones — this stops "every post is a
    # question" or "every post is a hot take" from becoming a pattern, on
    # top of the content-similarity check below.
    recent_angles = {p.get("angle") for p in recent_posts[:AVOID_LAST_ANGLES] if p.get("angle")}
    angle_pool = [a for a in POST_ANGLES if a not in recent_angles] or POST_ANGLES
    angle_counts = Counter(
        p.get("angle") for p in recent_posts[:ANGLE_WEIGHT_WINDOW] if p.get("angle")
    )
    weights = [1.0 / (1.0 + angle_counts[a]) for a in angle_pool]

    for _ in range(max_attempts):
        angle = random.choices(angle_pool, weights=weights, k=1)[0]
        prompt = _build_prompt(recent_titles[:15], angle)

        text = _call_nova(prompt)
        title, body = _parse_post(text)
        if not title or not body:
            continue

        too_similar = any(
            _similarity(title, rt) > 0.5 or _similarity(body, rb) > 0.45
            for rt, rb in zip(recent_titles, recent_bodies)
        )
        if not too_similar:
            return title, body, angle

    raise RuntimeError(
        "Could not generate a sufficiently unique post after several attempts. "
        "Consider widening POST_ANGLES or the DOMAIN_DESCRIPTION."
    )


def _parse_post(text: str):
    """Extract TITLE:/BODY: case-insensitively; tolerates markdown fences."""
    match = TITLE_BODY_RE.search(text)
    if not match:
        return None, None
    title = match.group(1).strip()
    body = text[match.end():].strip()
    if body.startswith("```"):
        body = re.sub(r"^```[a-z]*\n|\n```\s*$", "", body).strip()
    return (title or None), (body or None)