"""
FlowFix — Step 6 Clarification — Engine

Decides whether clarification is needed and what to ask.

Decision logic:
  1. If ResponseResult.status == INSUFFICIENT_EVIDENCE and no blueprint provided:
       → ask for the blueprint (highest value gap for Make problems)
  2. If no error message and no HTTP status:
       → ask for the exact error message
  3. If blueprint is present but failing module is unknown:
       → ask to identify the failing module
  4. If HTTP module present and no response body:
       → ask for the HTTP response body
  5. If status is DIAGNOSIS_CANDIDATE with high confidence:
       → no clarification needed, pass_through = True
  6. If max_cycles reached:
       → max_questions_reached = True, no question generated

Rules:
  - At most ONE question per invocation.
  - Questions are prioritised by diagnostic value.
  - No KB access, no scoring, no hypothesis generation.
  - Deterministic: same inputs → same output.
  - Never ask for secrets, credentials, or API keys.
  - Never ask for information already present in ResponseResult.
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step6_clarification.models_internal.models import (
    ClarificationResult,
    ClarificationQuestion,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CLARIFICATION_CYCLES = 3   # after this many questions, escalate


# ---------------------------------------------------------------------------
# Gap detectors — read from ResponseResult only
# ---------------------------------------------------------------------------

def _has_blueprint(response: ResponseResult, problem: NormalizedProblem) -> bool:
    """Blueprint provided and recognised by Step 1."""
    return (
        problem.blueprint.provided
        and problem.blueprint.valid_json is True
        and problem.blueprint.recognized_as_make_blueprint is True
    )


def _has_error_signal(problem: NormalizedProblem) -> bool:
    """At least one error code or error message available."""
    return bool(
        problem.errors.http_status_codes
        or problem.errors.exact_error_messages
        or problem.errors.error_codes
        or problem.execution_context.http.status
    )


def _has_failing_module(problem: NormalizedProblem) -> bool:
    """Failing module was explicitly provided."""
    return bool(
        problem.execution_context.failing_module_id
        or problem.execution_context.failing_module_name
    )


def _has_http_response_body(problem: NormalizedProblem) -> bool:
    """HTTP response body was provided."""
    return bool(problem.execution_context.http.response_body)


def _has_http_module(response: ResponseResult) -> bool:
    """HTTP module present in the workflow (from ResponseResult signals)."""
    signals_text = " ".join(response.diagnostic_signals or []).lower()
    # Step 2 emits "HTTP module present" or "has_http" style signals
    return "http" in signals_text or any(
        "http" in s.lower() for s in (response.observed or [])
    )


def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


# ---------------------------------------------------------------------------
# Question builders — returns a ClarificationQuestion or None
# ---------------------------------------------------------------------------

def _q_blueprint() -> ClarificationQuestion:
    return ClarificationQuestion(
        question_type="blueprint",
        question_text=(
            "To analyse your workflow structure, please paste the blueprint JSON "
            "from Make.com. You can export it via the three-dot menu on your scenario "
            "→ Export Blueprint. Paste the full JSON content here."
        ),
        why_needed=(
            "The blueprint lets FlowFix see your module sequence, connections, filters, "
            "and router branches — essential for pinpointing where the failure occurs."
        ),
        targets_gap="blueprint",
        expected_format="Paste the complete JSON content of the blueprint.",
    )


def _q_error_message() -> ClarificationQuestion:
    return ClarificationQuestion(
        question_type="error_message",
        question_text=(
            "What is the exact error message shown by Make.com? "
            "Please copy the full error text from the execution log — "
            "including any error code, HTTP status, or response body shown."
        ),
        why_needed=(
            "The exact error message is the primary signal for identifying the root cause. "
            "Without it, FlowFix can only provide generic guidance."
        ),
        targets_gap="exact_error_message",
        expected_format="Paste the error text exactly as it appears in Make.",
    )


def _q_failing_module() -> ClarificationQuestion:
    return ClarificationQuestion(
        question_type="failing_module",
        question_text=(
            "Which module is shown as failing in the Make.com execution log? "
            "Please tell me the module name and its position in the scenario "
            "(e.g. 'Module 3 — Gmail: Send an Email')."
        ),
        why_needed=(
            "Knowing which specific module fails narrows the diagnosis from the whole "
            "scenario to a single point — significantly reducing the candidate causes."
        ),
        targets_gap="failing_module_id",
        expected_format="Module number and name from the execution error panel.",
    )


def _q_http_response_body() -> ClarificationQuestion:
    return ClarificationQuestion(
        question_type="http_response_body",
        question_text=(
            "What does the HTTP response body say? "
            "In Make.com, click on the failing HTTP module in the execution log "
            "and copy the 'Output' or 'Response body' content shown there."
        ),
        why_needed=(
            "The response body typically contains the exact validation error from the "
            "external API — it identifies which field failed and why, "
            "which is necessary to distinguish between the current candidates."
        ),
        targets_gap="http_response_body",
        expected_format="Paste the JSON or text from the response body.",
    )


# ---------------------------------------------------------------------------
# Priority decision
# ---------------------------------------------------------------------------

def _select_question(
    response: ResponseResult,
    problem: NormalizedProblem,
    cycle: int,
    answered_gaps: Optional[list[str]] = None,
) -> Optional[ClarificationQuestion]:
    """
    Select the highest-priority clarification question.
    Returns None when no clarification is needed.

    Priority (highest first):
    1. No error signal → ask for error message
    2. No blueprint → ask for blueprint
    3. Blueprint present but failing module unknown → ask for failing module
    4. HTTP scenario + no response body → ask for response body
    """
    answered = set(answered_gaps or [])
    # Priority 1: error signal is the most fundamental input
    if not _has_error_signal(problem) and "exact_error_message" not in answered:
        return _q_error_message()

    # Priority 2: blueprint provides structural context
    if not _has_blueprint(response, problem) and "blueprint" not in answered:
        return _q_blueprint()

    # Priority 3: if we have blueprint + error but no failing module
    if _has_blueprint(response, problem) and not _has_failing_module(problem) and "failing_module_id" not in answered:
        return _q_failing_module()

    # Priority 4: HTTP scenario, no response body, still multiple candidates
    if (
        response.status in ("MULTIPLE_CANDIDATES", "WEAK_EVIDENCE")
        and any(m.app == "http" for m in problem.blueprint.modules)
        and not _has_http_response_body(problem)
        and "http_response_body" not in answered
    ):
        return _q_http_response_body()

    return None


# ---------------------------------------------------------------------------
# Pass-through decision
# ---------------------------------------------------------------------------

def _can_pass_through(response: ResponseResult) -> bool:
    """
    True when Step 5 output is already sufficient for the user.
    Criteria: strong diagnosis candidate OR actions available with high confidence.
    """
    if response.status == "DIAGNOSIS_CANDIDATE" and response.confidence == "high":
        return True
    if (
        response.status == "DIAGNOSIS_CANDIDATE"
        and response.confidence in ("high", "medium")
        and len(response.recommended_actions) >= 2
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def decide_clarification(
    response: ResponseResult,
    problem: NormalizedProblem,
    cycle: int = 0,
    *, answered_gaps: Optional[list[str]] = None,
) -> ClarificationResult:
    """
    Decide whether clarification is needed and which question to ask.

    Parameters
    ----------
    response : ResponseResult — Step 5 output (primary signal)
    problem  : NormalizedProblem — Step 1 output (to check what data is present)
    cycle    : int — number of clarification cycles already completed

    Returns
    -------
    ClarificationResult — with a question, a pass_through signal, or
                          a max_questions_reached flag.
    """
    result = ClarificationResult(
        analysis_id=response.analysis_id,
        warnings=list(response.warnings or []),
    )

    # Max cycles guard — avoid infinite loops
    if cycle >= MAX_CLARIFICATION_CYCLES:
        result.max_questions_reached = True
        result.needs_clarification = False
        result.re_run_after_answer = False
        return result

    # Pass-through: diagnosis is already good enough
    if _can_pass_through(response):
        result.pass_through = True
        result.needs_clarification = False
        result.re_run_after_answer = False
        return result

    # INSUFFICIENT_EVIDENCE always triggers clarification (if under max)
    # Other statuses may or may not depending on what is missing
    question = _select_question(response, problem, cycle, answered_gaps)

    if question is None:
        # Nothing useful to ask — pass through whatever we have
        result.pass_through = True
        result.needs_clarification = False
        result.re_run_after_answer = False
        return result

    result.needs_clarification = True
    question.question_text += " Remove all authentication material and personal data before sharing. Use existing execution details; do not run the scenario just to answer."
    question.expected_format += " Anonymized excerpt only, preserving field names and error codes."
    question.hypothesis_ids = [c["hypothesis_id"] for c in response.candidate_checks]
    if question.hypothesis_ids:
        question.why_needed += " This observation will help distinguish the current candidates; an inconclusive answer leaves them unresolved."
    result.question = question
    result.re_run_after_answer = True
    return result
