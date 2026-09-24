"""
FlowFix — Step 7 Feedback — Processor

Processes UserFeedback and derives a deterministic FeedbackResult.

Validation state derivation rules (priority: resolution truth > solution > diagnosis > helpfulness):

  NO_FEEDBACK          — no UserFeedback provided
  FEEDBACK_RECEIVED    — feedback provided but insufficient to classify further
  USER_CONFIRMED       — diagnosis correct + solution worked + resolved
  USER_CORRECTED       — incorrect/partially incorrect diagnosis with a user correction
  USER_REJECTED        — diagnosis incorrect without user correction
  UNRESOLVED           — resolution_status is unresolved or contradictory signals

Conflict resolution:
  If resolution_status = unresolved → UNRESOLVED (regardless of other fields)
  If diagnosis = correct AND solution_worked = false → UNRESOLVED (not USER_CONFIRMED)
  helpful = true does NOT imply diagnosis = correct

Rules:
  - Never modify any prior step object.
  - Never access the KB.
  - Never call LLM or network.
  - Never invent missing field values.
  - feedback_id is the only UUID generated here — it does not influence logic.
  - Deterministic: same inputs → same validation_state.
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step6_clarification.models_internal.models import ClarificationResult
from flowfix.step7_feedback.models_internal.models import (
    UserFeedback,
    FeedbackResult,
)


# ---------------------------------------------------------------------------
# Validation state derivation — deterministic
# ---------------------------------------------------------------------------

def _derive_validation_state(fb: UserFeedback) -> str:
    """
    Derive the validation_state from UserFeedback fields.

    Priority order (highest first):
      1. resolution_status = unresolved → UNRESOLVED
      2. diagnosis_accuracy = incorrect → USER_REJECTED or USER_CORRECTED
      3. diagnosis_accuracy = correct + solution_worked = false → UNRESOLVED
      4. diagnosis_accuracy = correct + solution_worked = true + resolved → USER_CONFIRMED
      5. Any feedback with partial information → FEEDBACK_RECEIVED
    """
    acc = fb.diagnosis_accuracy       # correct | partially_correct | incorrect | unknown | None
    worked = fb.solution_worked       # True | False | None
    status = fb.resolution_status     # resolved | partially_resolved | unresolved | unknown
    has_correction = bool(fb.corrected_diagnosis or fb.actual_resolution)

    # Rule 1 — Explicit unresolved truth overrides everything
    if status == "unresolved":
        return "UNRESOLVED"

    # Rule 2 — Incorrect diagnosis
    if acc == "incorrect":
        if has_correction:
            return "USER_CORRECTED"
        return "USER_REJECTED"

    # Rule 3 — Partially incorrect diagnosis
    if acc == "partially_correct":
        if has_correction:
            return "USER_CORRECTED"
        return "FEEDBACK_RECEIVED"  # acknowledged but not enough info to classify

    # Rule 4 — Diagnosis correct + solution failed (contradictory)
    if acc == "correct" and worked is False:
        return "UNRESOLVED"

    # Rule 5 — Full confirmation
    if acc == "correct" and worked is True and status == "resolved":
        return "USER_CONFIRMED"

    # Rule 6 — Partial resolution
    if status == "partially_resolved":
        return "UNRESOLVED"

    # Rule 7 — Any feedback received but insufficient to classify clearly
    any_feedback = (
        fb.helpful is not None
        or acc is not None
        or worked is not None
        or status != "unknown"
        or fb.user_comment
        or has_correction
    )
    if any_feedback:
        return "FEEDBACK_RECEIVED"

    return "NO_FEEDBACK"


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

def process_feedback(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
    reasoning: ReasoningResult,
    response: ResponseResult,
    clarification: ClarificationResult,
    user_feedback: Optional[UserFeedback] = None,
) -> FeedbackResult:
    """
    Process user feedback and produce a FeedbackResult.

    Parameters
    ----------
    problem, analysis, retrieval, reasoning, response, clarification :
        Prior step outputs — read-only; never modified by Step 7.
    user_feedback : Optional[UserFeedback]
        Feedback from the user. None means no feedback received.

    Returns
    -------
    FeedbackResult — deterministic; does not modify any prior output.
    No KB write. No LLM. No network.
    """
    result = FeedbackResult(
        analysis_id=response.analysis_id,
    )

    if user_feedback is None:
        # No feedback provided
        result.feedback_received = False
        result.validation_state = "NO_FEEDBACK"
        return result

    from dataclasses import asdict
    from flowfix.step1_intake.redaction.redactor import redact_dict
    user_feedback = UserFeedback(**redact_dict(asdict(user_feedback)).redacted_data)

    # Validate analysis_id consistency
    if user_feedback.analysis_id != response.analysis_id:
        result.warnings.append("analysis_id mismatch: feedback isolated and not integrated")
        result.feedback_received = False
        result.validation_state = "NO_FEEDBACK"
        return result

    # Populate feedback fields
    result.feedback_received = True
    result.helpful = user_feedback.helpful
    result.diagnosis_accuracy = user_feedback.diagnosis_accuracy
    result.solution_worked = user_feedback.solution_worked
    result.resolution_status = user_feedback.resolution_status
    result.user_comment = user_feedback.user_comment
    result.corrected_diagnosis = user_feedback.corrected_diagnosis
    result.actual_resolution = user_feedback.actual_resolution

    # Derive validation state
    result.validation_state = _derive_validation_state(user_feedback)

    # Propagate warnings from prior steps (non-intrusive observation only)
    if response.warnings:
        result.warnings.extend(response.warnings)

    return result
