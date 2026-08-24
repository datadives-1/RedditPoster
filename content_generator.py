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
import difflib
from collections import Counter

import llm

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
    "share a specific technical problem you solved and how you approached it, focusing on the solution journey",
    "discuss a challenge in AI tooling and crowdsource creative solutions from the community",
    "share a small automation or script you built to solve a recurring problem, without promoting services",
    "present a problem with current AI workflows and ask how others would solve it",
    "share how you built a lightweight AI agent for a specific task — lessons learned",
    "share a technical automation with concrete metrics (time saved, errors reduced, cost avoided) that others can learn from",
]

# Angles used in the last N posts are excluded entirely; the rest are picked
# weighted toward the least-used ones so styles don't cluster.
# Expanded windows for better diversity across 18 angles.
AVOID_LAST_ANGLES = 5
ANGLE_WEIGHT_WINDOW = 15

# Angle groups for rotation strategy — ensures no single style dominates
ANGLE_GROUPS = {
    'question': 0,
    'lesson': 1,
    'controversial': 2,
    'before_after': 3,
    'critique': 4,
    'mistake': 5,
    'hot_take': 6,
    'recommendations': 7,
    'psa': 8,
    'client_project': 9,
    'pricing': 10,
    'engagement_win': 11,
    'technical_problem': 12,
    'ai_tooling_challenge': 13,
    'automation_script': 14,
    'workflow_problem': 15,
    'ai_agent': 16,
    'technical_metrics': 17,
}

TITLE_BODY_RE = re.compile(
    r"#{0,6}\s*title\s*:\s*(.*?)\s*#{0,6}\s*body\s*:", re.IGNORECASE | re.DOTALL
)

# Safety net: reject anything that still looks like a template/placeholder
# even if the model ignored the prompt rule. Matches [insert ...], [your ...],
# YOUR_XXX, TODO, "…something here", etc.
_PLACEHOLDER_RE = re.compile(
    r"\[[^\]]*(?:insert|replace|your|enter|put|placeholder|example|something"
    r"|niche|topic|name)[^\]]*\]"
    r"|\([^)]*(?:insert|placeholder|your (?:name|company|product|tool|app)|"
    r"add .* (?:here|below))[^)]*\)"
    r"|\bYOUR_[A-Z_]+\b|\bREPLACE_ME\b|\bTODO\b|\bXXX\b",
    re.IGNORECASE,
)
_PLACEHOLDER_BRACKET_RE = re.compile(r"\[[A-Za-z]?\]|\b\[X(?:XX)?\]\b")


def _has_placeholder(text: str) -> bool:
    return bool(
        _PLACEHOLDER_RE.search(text) or _PLACEHOLDER_BRACKET_RE.search(text)
    )


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _angle_prompt_guidance(angle: str) -> str:
    """Return angle-specific framing guidance embedded into the prompt."""
    if angle.startswith("share a specific technical problem") or angle.startswith("discuss a challenge") or angle.startswith("share a small automation") or angle.startswith("present a problem") or angle.startswith("share how you built") or angle.startswith("share a technical automation"):
        return """
- Frame this as a genuine challenge you faced, not a service offering.
- Describe the problem concretely: what it was, why it mattered, how you discovered it.
- Share the solution journey: steps you took, what you tried, what finally worked.
- End with a community-focused question that invites others to share similar experiences or alternative solutions.
- Never say "hire me", "DM me for work", or advertise services in the post body.
- DO NOT include any links or mention any website/portfolio URL in the body.
- **Value-first rule**: Provide 3+ sentences of genuine problem/solution content before any service-relevant mentions.
  Frame your approach as "what worked for me" rather than "hire me for this."
- **For Entrepreneur/startup subs**: build reputation through pure problem-solving first.
  Readers who find your approach valuable will naturally check your profile or ask about services.
  This "create demand then supply" pattern works better than direct pitching."""
    return ""

def _build_prompt(recent_titles, angle):
    history_block = "\n".join(f"- {t}" for t in recent_titles) or "(none yet)"
    guidance = _angle_prompt_guidance(angle)
    return f"""You are ghostwriting a Reddit post for a real person whose domain is: {DOMAIN_DESCRIPTION}

Write ONE Reddit post using this angle: {angle}

Rules:
- The post is FINAL and publishable as-is. Never use placeholders, brackets,
  or meta-instructions like [insert niche here], [Your Name], [X], YOUR_COMPANY,
  TODO, or "(add something here)" — write every detail concretely yourself.
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
{guidance}
- Grammar and spelling should be normal, correct English, written in a natural conversational voice.
- Must be meaningfully different in topic and wording from these recent posts:
{history_block}

Respond in exactly this format, nothing else:
TITLE: <post title>
BODY: <post body, 2-5 short paragraphs>
"""


def _call_llm(prompt: str) -> str:
    """Route the prompt to the configured LLM provider (see llm.py)."""
    return llm.generate(prompt)


def _angle_weight(angle: str, angle_counts: Counter, new_angle_marker: str = "NEW_") -> float:
    base = 1.0 / (1.0 + angle_counts.get(angle, 0))
    # Boost new problem/solution angles so they appear >50% of the time
    if angle.startswith("share a specific technical") or angle.startswith("discuss a challenge") or angle.startswith("share a small automation") or angle.startswith("present a problem") or angle.startswith("share how you built") or angle.startswith("share a technical automation"):
        base *= 2.5
    # Additional boost for technical metrics angle - showcases concrete results
    if angle.startswith("share a technical automation"):
        base *= 1.5
    return base


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
    weights = [_angle_weight(a, angle_counts) for a in angle_pool]

    for _ in range(max_attempts):
        angle = random.choices(angle_pool, weights=weights, k=1)[0]
        prompt = _build_prompt(recent_titles[:15], angle)

        text = _call_llm(prompt)
        title, body = _parse_post(text)
        if not title or not body:
            continue
        if _has_placeholder(title) or _has_placeholder(body):
            continue

        too_similar = any(
            _similarity(title, rt) > 0.55 or _similarity(body, rb) > 0.50
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