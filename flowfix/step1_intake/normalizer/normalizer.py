"""
FlowFix — Step 1 Intake — Normalizer

Transforms raw user input into a NormalizedProblem.

v1.1 corrections applied:
- CORRECTION 2: raw_blueprint stores redacted text only (no secrets in pipeline).
- CORRECTION 3: logs, expected_behavior, actual_behavior, recent_changes are redacted.
- CORRECTION 4: headers redacted via redact_headers(); nested structures via redact_dict().
- CORRECTION 7: HTTP status code detection now requires contextual markers to reduce
  false positives (plain numbers like "Module ID 403" are ignored).
- CORRECTION 8: missing_information tracks informational gaps only; does not affect
  ready_for_step2 validity.
- CORRECTION 9: context.http.status coerced defensively (str, int, None, unknown).

STEP 1 does NOT:
  - Search the Knowledge Base.
  - Generate diagnoses or causes.
  - Classify errors into KB categories.
  - Score relevance.
  - Recommend solutions.
"""

from __future__ import annotations
import re
from typing import Optional

from ..intake.models import (
    NormalizedProblem,
    ErrorInfo,
    ExecutionContext,
    HttpContext,
    IntakeMetadata,
)
from ..blueprint_parser.parser import parse_blueprint, BlueprintInfo
from ..redaction.redactor import redact, redact_headers, redact_dict


# ---------------------------------------------------------------------------
# CORRECTION 7 — Contextual HTTP status code detection
#
# Priority: patterns that explicitly name an HTTP status first.
# Fallback: bare known codes only when surrounded by unambiguous delimiters.
# ---------------------------------------------------------------------------

# Pattern 1 — Explicit HTTP context (highest confidence):
#   "HTTP 403", "status code 403", "status: 403", "status=403",
#   "403 Forbidden", "429 Too Many Requests", etc.
_HTTP_EXPLICIT_RE = re.compile(
    r"""
    (?:
        # "HTTP 403" / "HTTP/1.1 403"
        \bHTTP(?:/[\d.]+)?\s+(?P<c1>1[0-9]{2}|[2-5][0-9]{2})\b
        |
        # "status code 403" / "status: 403" / "status=403"
        \bstatus(?:\s+code)?\s*[:=]\s*(?P<c2>1[0-9]{2}|[2-5][0-9]{2})\b
        |
        # "403 Forbidden" / "404 Not Found" / "429 Too Many Requests" / "500 Internal Server Error"
        # Requires the word after the code to be a known HTTP reason phrase fragment.
        \b(?P<c3>1[0-9]{2}|[2-5][0-9]{2})\s+
        (?:OK|Created|Accepted|No\s+Content|
           Moved|Found|Not\s+Modified|
           Bad\s+Request|Unauthorized|
           Payment\s+Required|Forbidden|Not\s+Found|
           Method\s+Not\s+Allowed|Not\s+Acceptable|
           Request\s+Timeout|Conflict|Gone|
           Unprocessable|Too\s+Many\s+Requests|
           Internal\s+Server\s+Error|Bad\s+Gateway|
           Service\s+Unavailable|Gateway\s+Timeout)
        |
        # "with status 403" / "returned 403" / "got 403" / "error 403" / "code 403"
        \b(?:with\s+status|returned?|got|error|code)\s+(?P<c4>1[0-9]{2}|[2-5][0-9]{2})\b
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_KNOWN_HTTP_STATUSES = {
    100, 101,
    200, 201, 202, 204,
    301, 302, 304,
    400, 401, 403, 404, 405, 408, 409, 410, 422, 429,
    500, 502, 503, 504,
}


def _extract_http_status_codes(text: str) -> list[int]:
    """
    Extract HTTP status codes from text using contextual patterns only.
    Reduces false positives from IDs, module numbers, etc.
    """
    codes: list[int] = []
    for m in _HTTP_EXPLICIT_RE.finditer(text):
        raw = m.group("c1") or m.group("c2") or m.group("c3") or m.group("c4")
        if raw:
            code = int(raw)
            if code in _KNOWN_HTTP_STATUSES and code not in codes:
                codes.append(code)
    return codes


# ---------------------------------------------------------------------------
# Generic error code extraction (Make-specific non-HTTP codes)
# ---------------------------------------------------------------------------

_ERROR_CODE_RE = re.compile(
    r"\b(ECONNREFUSED|ETIMEDOUT|ENOTFOUND|ERR_[A-Z_]+|[A-Z][A-Z0-9_]{3,}(?:_ERROR|_FAILED|_INVALID))\b"
)


def _extract_error_codes(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _ERROR_CODE_RE.finditer(text)))


# ---------------------------------------------------------------------------
# CORRECTION 9 — Defensive HTTP status coercion
# ---------------------------------------------------------------------------

def _coerce_http_status(raw) -> Optional[int]:
    """
    Safely coerce a context-supplied HTTP status to int.
    Accepts: int, str of an int, None.
    Rejects: non-numeric strings, values outside the HTTP range 100-599.
    """
    if raw is None:
        return None
    value: Optional[int] = None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        try:
            value = int(raw.strip())
        except (ValueError, AttributeError):
            return None
    if value is not None and 100 <= value <= 599:
        return value
    return None


# ---------------------------------------------------------------------------
# CORRECTION 8 — Missing information (informational only, non-blocking)
# ---------------------------------------------------------------------------

def _detect_missing(
    error_text: Optional[str],
    blueprint_text: Optional[str],
    context: Optional[dict],
    bp_info: BlueprintInfo,
) -> list[str]:
    """
    Record what information is absent.
    These gaps are informational for Step 2 — they do NOT affect validity.
    """
    missing = []

    if not error_text:
        missing.append("exact_error_message")

    if not blueprint_text:
        missing.append("blueprint")

    if blueprint_text and bp_info.valid_json and bp_info.recognized_as_make_blueprint:
        if not bp_info.modules:
            missing.append("blueprint_modules")

    if context:
        if not context.get("failing_module_id") and not context.get("failing_module_name"):
            missing.append("failing_module_id")
    else:
        missing.append("execution_context")

    return missing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize(
    error_text: Optional[str] = None,
    blueprint_text: Optional[str] = None,
    context: Optional[dict] = None,
    user_description: Optional[str] = None,
) -> NormalizedProblem:
    """
    Entry point for Step 1.

    Parameters
    ----------
    error_text:         Raw error string from the user.
    blueprint_text:     Raw Make.com blueprint JSON string.
    context:            Dict with optional execution context keys.
    user_description:   Free-text problem description.

    Returns
    -------
    NormalizedProblem
        Fully populated internal contract for Step 2.
        All secrets are redacted before storage.
    """
    problem = NormalizedProblem()
    meta: IntakeMetadata = problem.metadata

    # -----------------------------------------------------------------------
    # 1. User description — redact before storing
    # -----------------------------------------------------------------------
    if user_description:
        res = redact(user_description)
        problem.user_description = res.redacted_text
        meta.redactions_applied.extend(res.redactions)
        meta.received_sources.append("user_description")

    # -----------------------------------------------------------------------
    # 2. Error text — redact, then extract signals
    # -----------------------------------------------------------------------
    error_info = ErrorInfo()

    if error_text:
        res = redact(error_text)
        clean_error = res.redacted_text
        meta.redactions_applied.extend(res.redactions)
        meta.received_sources.append("error_text")

        error_info.exact_error_messages = [clean_error]
        error_info.http_status_codes = _extract_http_status_codes(clean_error)
        error_info.error_codes = _extract_error_codes(clean_error)

    problem.errors = error_info

    # -----------------------------------------------------------------------
    # 3. Blueprint — CORRECTION 2: redact first, parse redacted version only.
    #    raw_blueprint stores the redacted text so no secrets enter the pipeline.
    # -----------------------------------------------------------------------
    bp_info = BlueprintInfo(provided=False)

    if blueprint_text:
        # Redact before any parsing or storage
        import json
        try:
            if len(blueprint_text) > 1_000_000:
                raise ValueError("size limit")
            dr = redact_dict(json.loads(blueprint_text))
            from ..redaction.redactor import RedactionResult
            res = RedactionResult(json.dumps(dr.redacted_data), dr.redactions)
        except (ValueError, TypeError, RecursionError):
            from ..redaction.redactor import RedactionResult
            res = RedactionResult("[REDACTED:INVALID_OR_LIMIT]", ["Blueprint invalid or over limit: masked"])
        clean_bp = res.redacted_text          # only this version is used further
        meta.redactions_applied.extend(res.redactions)
        meta.received_sources.append("blueprint")

        bp_info = parse_blueprint(clean_bp)
        # raw_blueprint in bp_info already holds clean_bp (set inside parser)

        if not bp_info.valid_json:
            meta.warnings.append("Blueprint provided but not valid JSON.")
        elif not bp_info.recognized_as_make_blueprint:
            meta.warnings.append(
                "Blueprint is valid JSON but not recognised as a Make.com scenario blueprint."
            )

    problem.blueprint = bp_info

    # -----------------------------------------------------------------------
    # 4. Execution context — CORRECTIONS 3, 4, 9
    # -----------------------------------------------------------------------
    exec_ctx = ExecutionContext()

    if context and isinstance(context, dict):
        meta.received_sources.append("execution_context")
        sanitized = redact_dict(context)
        meta.redactions_applied.extend(sanitized.redactions)
        context = sanitized.redacted_data
        if not isinstance(context, dict):
            context = {}

        if "json_field_observation" in context:
            from ..intake.field_contracts import parse_observation
            exec_ctx.json_field_observation = parse_observation(context["json_field_observation"])
            if exec_ctx.json_field_observation is None:
                meta.warnings.append("JSON field observation malformed, sensitive or incomplete; precise correction withheld.")
        exec_ctx.failing_module_id = context.get("failing_module_id")
        exec_ctx.failing_module_name = context.get("failing_module_name")
        exec_ctx.timestamp = context.get("timestamp")
        exec_ctx.bundle_count = context.get("bundle_count")
        exec_ctx.frequency = context.get("frequency")

        # CORRECTION 3 — Redact free-text fields that may contain secrets
        for field_name in ("logs", "expected_behavior", "actual_behavior", "recent_changes"):
            raw_val = context.get(field_name)
            if raw_val is not None:
                res = redact(str(raw_val))
                setattr(exec_ctx, field_name, res.redacted_text)
                meta.redactions_applied.extend(res.redactions)

        # CORRECTION 4 — Redact nested input/output structures
        if context.get("input_data") is not None:
            raw_input = context["input_data"]
            if isinstance(raw_input, (dict, list)):
                dr = redact_dict(raw_input)
                exec_ctx.input_data = str(dr.redacted_data)
                meta.redactions_applied.extend(dr.redactions)
            else:
                res = redact(str(raw_input))
                exec_ctx.input_data = res.redacted_text
                meta.redactions_applied.extend(res.redactions)

        if context.get("output_data") is not None:
            raw_output = context["output_data"]
            if isinstance(raw_output, (dict, list)):
                dr = redact_dict(raw_output)
                exec_ctx.output_data = str(dr.redacted_data)
                meta.redactions_applied.extend(dr.redactions)
            else:
                res = redact(str(raw_output))
                exec_ctx.output_data = res.redacted_text
                meta.redactions_applied.extend(res.redactions)

        # HTTP sub-context
        http_raw = context.get("http", {}) or {}
        if isinstance(http_raw, dict):
            # Response body
            body = http_raw.get("response_body")
            if body is not None:
                res = redact(str(body))
                body = res.redacted_text
                meta.redactions_applied.extend(res.redactions)

            # CORRECTION 3 & 4 — Headers: redact sensitive values
            headers_raw = http_raw.get("headers")
            redacted_headers = None
            if isinstance(headers_raw, dict):
                hr = redact_headers(headers_raw)
                redacted_headers = hr.redacted_data
                meta.redactions_applied.extend(hr.redactions)
            elif headers_raw is not None:
                # Non-dict headers: treat as string and redact
                res = redact(str(headers_raw))
                redacted_headers = res.redacted_text
                meta.redactions_applied.extend(res.redactions)

            # CORRECTION 9 — Defensive status coercion
            exec_ctx.http = HttpContext(
                status=_coerce_http_status(http_raw.get("status")),
                response_body=body,
                headers=redacted_headers,
            )

    if isinstance(context,dict) and context.get('root_cause_context') is not None:
        from ..intake.trace_contract import parse_context
        try:exec_ctx.root_cause_context = parse_context(context['root_cause_context'])
        except (ValueError,TypeError,RecursionError):
            exec_ctx.root_cause_context = {'error':'Malformed, sensitive or inconsistent trace context.'}
            meta.warnings.append('Root cause context rejected; no causal conclusion permitted.')
    problem.execution_context = exec_ctx

    # -----------------------------------------------------------------------
    # 5. Missing information (informational, non-blocking)
    # -----------------------------------------------------------------------
    meta.missing_information = _detect_missing(
        error_text, blueprint_text, context, bp_info
    )

    # Deduplicate redactions list
    meta.redactions_applied = list(dict.fromkeys(meta.redactions_applied))

    return problem
