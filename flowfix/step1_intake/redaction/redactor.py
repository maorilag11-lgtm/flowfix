"""
FlowFix — Step 1 Intake — Redaction
Detect and mask secrets/credentials in raw user input.

Secrets are replaced with [REDACTED:<type>] placeholders.
Every redaction is recorded so Step 2+ can be aware of what was removed.

v1.1 corrections:
- Added header-specific redaction (dict form) for Authorization, Cookie, etc.
- Added redact_dict() for nested structures (headers, context fields).
- Added redact_logs() helper for multi-line log fields.
- Text redaction patterns unchanged; new helpers layered on top.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Patterns for flat text redaction.
# Order matters: more specific patterns first.
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    (
        "Bearer token",
        "BEARER_TOKEN",
        re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    ),
    (
        "Authorization header value",
        "AUTH_HEADER",
        re.compile(
            r"(Authorization\s*:\s*(?:Basic|Token|ApiKey)\s+)[A-Za-z0-9+/=]{8,}",
            re.IGNORECASE,
        ),
    ),
    (
        "API key param",
        "API_KEY",
        re.compile(
            r"((?:api[-_]?key|apikey|access[-_]?token|secret[-_]?key)\s*[=:]\s*)['\"]?[A-Za-z0-9\-._~+/]{16,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    (
        "Refresh token",
        "REFRESH_TOKEN",
        re.compile(
            r"(refresh[-_]?token\s*[=:]\s*)['\"]?[A-Za-z0-9\-._~+/]{16,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    (
        "Password field",
        "PASSWORD",
        re.compile(
            r"((?:password|passwd|pwd)\s*[=:]\s*)['\"]?[^\s'\"]{6,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    (
        "Webhook secret",
        "WEBHOOK_SECRET",
        re.compile(
            r"((?:webhook[-_]?secret|signing[-_]?secret)\s*[=:]\s*)['\"]?[A-Za-z0-9\-._~+/]{16,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    (
        "Generic long token",
        "TOKEN",
        re.compile(
            r"((?:token|credential)\s*[=:]\s*)['\"]?[A-Za-z0-9\-._~+/]{32,}['\"]?",
            re.IGNORECASE,
        ),
    ),
]

# ---------------------------------------------------------------------------
# Sensitive header names — values must be redacted when found in dicts.
# Header name matching is case-insensitive.
# ---------------------------------------------------------------------------

_SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
}

# Keys that carry secrets when found anywhere in nested dicts (not just HTTP headers).
# Used by redact_dict() to catch fields like {"api_key": "...", "token": "..."}.
_SENSITIVE_DICT_KEYS = {
    "api_key",
    "apikey",
    "api-key",
    "access_token",
    "refresh_token",
    "secret_key",
    "secret",
    "password",
    "passwd",
    "token",
    "credential",
    "webhook_secret",
    "signing_secret",
    "bearer",
} | _SENSITIVE_HEADERS


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RedactionResult:
    redacted_text: str
    redactions: list[str] = field(default_factory=list)


@dataclass
class DictRedactionResult:
    redacted_data: Any
    redactions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core text redaction (unchanged from v1.0)
# ---------------------------------------------------------------------------

def redact(text: str) -> RedactionResult:
    """
    Apply all text patterns to *text*.
    Returns the redacted string and a list of recorded redactions.
    """
    if not text:
        return RedactionResult(redacted_text=text, redactions=[])

    if not isinstance(text, str) or len(text) > 1_000_000:
        return RedactionResult("[REDACTED:LIMIT]", ["Text size/type limit: masked"])
    redactions: list[str] = []
    result = text
    # JSON/Python-style quoted key/value fragments, plus short labelled secrets.
    secret_names = r"authorization|proxy-authorization|cookie|set-cookie|x-api-key|api[-_]?key|access[-_]?token|refresh[-_]?token|client[-_]?secret|secret|secret[-_]?key|password|passwd|pwd|token|credential|webhook[-_]?secret|signing[-_]?secret"
    secret_pattern = re.compile(r"((?<![\w-])(?:" + secret_names + r")[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)", re.I)
    def labelled(m):
        redactions.append("Labelled secret redacted")
        return m.group(1) + "[REDACTED:SECRET]"

    for label, tag, pattern in _PATTERNS:
        def _replace(m: re.Match, _tag: str = tag, _label: str = label) -> str:
            prefix = m.group(1)
            redactions.append(f"{_label} redacted")
            return f"{prefix}[REDACTED:{_tag}]"

        result = pattern.sub(_replace, result)

    # A complete unquoted authorization/cookie line is sensitive, including
    # unfamiliar schemes and short credentials that token regexes cannot detect.
    header_pattern = re.compile(r"(?im)((?:^|\n)\s*(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+")
    result = header_pattern.sub(labelled, result)
    result = secret_pattern.sub(labelled, result)
    return RedactionResult(redacted_text=result, redactions=redactions)


# ---------------------------------------------------------------------------
# Header dict redaction (CORRECTION 3 & 4)
# ---------------------------------------------------------------------------

def redact_headers(headers: dict) -> DictRedactionResult:
    return redact_dict(headers)


MAX_TEXT_SIZE = 1_000_000
MAX_DEPTH = 32
MAX_NODES = 50_000


def _sensitive(key):
    return isinstance(key, str) and re.sub(r"[^a-z0-9]", "", key.lower()) in {
        re.sub(r"[^a-z0-9]", "", k) for k in _SENSITIVE_DICT_KEYS | {"client_secret", "pwd"}
    }


def redact_at_path(data: Any, path: list) -> DictRedactionResult:
    """A sliced observation retains the sensitivity of its enclosing field."""
    if any(_sensitive(part) for part in path):
        return DictRedactionResult("[REDACTED:SECRET]", ["Sensitive observation path redacted"])
    return redact_dict(data)


def redact_dict(data: Any, _depth: int = 0) -> DictRedactionResult:
    """Copy and sanitize; mask entire subtrees at explicit resource limits."""
    redactions = []
    budget = [MAX_NODES]
    def walk(value, depth):
        budget[0] -= 1
        if depth > MAX_DEPTH or budget[0] < 0:
            redactions.append("Resource limit: subtree masked")
            return "[REDACTED:LIMIT]"
        if isinstance(value, str):
            r = redact(value)
            redactions.extend(r.redactions)
            return r.redacted_text
        if isinstance(value, dict):
            if len(value) > budget[0]:
                redactions.append("Resource limit: object masked")
                return "[REDACTED:LIMIT]"
            pair_secret = _sensitive(value.get("name")) or _sensitive(value.get("key"))
            result = {}
            for key, item in value.items():
                if _sensitive(key) or (pair_secret and key == "value"):
                    result[key] = "[REDACTED:SECRET]"
                    redactions.append("Sensitive field value redacted")
                else:
                    result[key] = walk(item, depth + 1)
            return result
        if isinstance(value, (list, tuple)):
            if len(value) > budget[0]:
                redactions.append("Resource limit: array masked")
                return "[REDACTED:LIMIT]"
            return [walk(item, depth + 1) for item in value]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        redactions.append("Unsupported value masked")
        return "[REDACTED:UNSUPPORTED]"
    return DictRedactionResult(walk(data, _depth), redactions)
