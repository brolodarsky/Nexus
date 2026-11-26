"""
secret_scrubber.py — Pre-hash credential scrubbing and token estimation helpers.

Why this exists:
  1. Content-addressed trace storage (`trace_blobs`) deduplicates payloads by SHA-256 hash.
     Running `scrub_secrets()` *before* hashing guarantees that leaked API keys, Bearer headers,
     or OAuth credentials never enter SQLite blobs, run logs, or SSE trace streams.
  2. Token approximation (`approx_token_count`) provides a fast, zero-dependency, provider-agnostic
     `~tokens` estimate (`ceil(chars / 4)`) alongside exact character counts across UI and logs.
"""

from __future__ import annotations

import re
from typing import Any

# Compiled regular expressions matching common API tokens, bearer headers, and JSON secret fields
_GOOGLE_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z\-_]{35}")
_ANTHROPIC_API_KEY_RE = re.compile(r"sk-ant-[0-9A-Za-z\-_]{20,}")
_OPENAI_API_KEY_RE = re.compile(r"sk-(?:proj-|svcacct-)?[0-9A-Za-z\-_]{20,}")
_TAVILY_API_KEY_RE = re.compile(r"tvly-[0-9A-Za-z\-_]{16,}")
_TELEGRAM_BOT_TOKEN_RE = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
_BEARER_HEADER_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9\-._~+/]+=*"
)
_JSON_SECRET_FIELD_RE = re.compile(
    r'(?i)("(?:access_token|refresh_token|client_secret|api_key|private_key)"\s*:\s*")([^"]{8,})(")'
)


# `char_count: int` is the raw UTF-8 character length of a prompt, tool payload, or message.
# `-> int` returns ceiling division `(char_count + 3) // 4` (or 0 for empty/non-positive counts).
def approx_token_count(char_count: int) -> int:
    """Estimate token count deterministically from character length using ceil(chars / 4)."""
    if not isinstance(char_count, int) or char_count <= 0:
        return 0
    return (char_count + 3) // 4


# `text: str` is raw text destined for SHA-256 blob storage or trace event serialization.
# `-> str` returns a sanitized copy with recognized secrets replaced by safe redaction markers.
def scrub_secrets(text: str) -> str:
    """Redact recognized API keys, OAuth tokens, and Bearer authorization headers from `text`."""
    if not isinstance(text, str) or not text:
        return text if isinstance(text, str) else ""

    # Apply specific provider prefixes before generic `sk-` OpenAI patterns
    cleaned = _ANTHROPIC_API_KEY_RE.sub("sk-ant-...[REDACTED]", text)
    cleaned = _GOOGLE_API_KEY_RE.sub("AIza...[REDACTED]", cleaned)
    cleaned = _TAVILY_API_KEY_RE.sub("tvly-...[REDACTED]", cleaned)
    cleaned = _OPENAI_API_KEY_RE.sub("sk-...[REDACTED]", cleaned)
    cleaned = _TELEGRAM_BOT_TOKEN_RE.sub("[TELEGRAM_TOKEN_REDACTED]", cleaned)
    cleaned = _BEARER_HEADER_RE.sub(r"\1[REDACTED]", cleaned)
    cleaned = _JSON_SECRET_FIELD_RE.sub(r"\1[REDACTED]\3", cleaned)
    return cleaned


# `value: Any` is an arbitrary JSON-serializable trace payload (str, dict, list, tuple, or scalar).
# `-> Any` returns a recursively scrubbed copy leaving numbers, booleans, and None untouched.
def scrub_structure(value: Any) -> Any:
    """Recursively scrub secrets across nested dicts, lists, tuples, and string values."""
    if isinstance(value, str):
        return scrub_secrets(value)
    if isinstance(value, dict):
        return {k: scrub_structure(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_structure(item) for item in value)
    return value
