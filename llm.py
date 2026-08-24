"""
llm.py
Provider-agnostic LLM calls with retry + exponential backoff. Pick the
provider with LLM_PROVIDER (default: bedrock). No new dependencies —
all providers are called with the stdlib.

Providers:
  bedrock   - AWS Bedrock (uses AWS_* env vars + BEDROCK_MODEL_ID)
  openai    - any OpenAI-compatible REST endpoint (OpenAI, Groq, OpenRouter,
              DeepSeek, etc.): LLM_API_KEY + optional LLM_API_URL + LLM_MODEL
  gemini    - Google AI Studio: LLM_API_KEY + optional LLM_MODEL (default gemini-2.0-flash)
"""

import json
import os
import time
import urllib.request
import urllib.error

import boto3
from botocore.exceptions import BotoCoreError, ClientError

AWS_REGION = os.environ.get("AWS_REGION") or "us-east-1"
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

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


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return error.get("Code", "") in _RETRYABLE_CODES or status in _RETRYABLE_STATUS
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _RETRYABLE_STATUS
    return isinstance(exc, (BotoCoreError, urllib.error.URLError))


def _call_bedrock(prompt: str) -> str:
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1024, "temperature": 0.7},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def _call_openai_compatible(prompt: str) -> str:
    url = os.environ.get("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 1.0,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['LLM_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def _call_gemini(prompt: str) -> str:
    model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={os.environ['LLM_API_KEY']}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def generate(prompt: str, max_attempts: int = 4) -> str:
    """Call the configured LLM provider with retry + exponential backoff."""
    provider = os.environ.get("LLM_PROVIDER", "bedrock").lower()
    if provider == "bedrock":
        call = _call_bedrock
    elif provider == "openai":
        if not os.environ.get("LLM_API_KEY"):
            raise ValueError("LLM_PROVIDER=openai requires LLM_API_KEY (and LLM_MODEL)")
        call = _call_openai_compatible
    elif provider == "gemini":
        if not os.environ.get("LLM_API_KEY"):
            raise ValueError("LLM_PROVIDER=gemini requires LLM_API_KEY from Google AI Studio")
        call = _call_gemini
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider} (use bedrock, openai, or gemini)"
        )

    last_error = None
    for attempt in range(max_attempts):
        try:
            return call(prompt)
        except (ClientError, BotoCoreError, urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            if isinstance(exc, ValueError) or not _is_retryable_error(exc) or attempt == max_attempts - 1:
                raise
            last_error = exc
        except Exception:
            raise
        time.sleep(2 ** (attempt + 1))
    raise last_error  # pragma: no cover - only reached if max_attempts == 0