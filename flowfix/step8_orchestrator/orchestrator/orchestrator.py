"""
FlowFix — Step 8 Orchestrator — Routing Engine

Reads all prior step outputs and produces a PipelineDecision.

Routing priority (highest first):
  1. Feedback received → RECORD_FEEDBACK (terminal acknowledgement)
  2. Max clarification cycles reached → ESCALATE
  3. Clarification needed → ASK_CLARIFICATION
  4. Re-run requested (clarification already answered) → RERUN
  5. Pass-through (Step 5 response is sufficient) → DELIVER
  6. Fallback → DELIVER (best effort)

Rules:
  - Never access the KB.
  - Never generate user-facing content.
  - Never modify any prior step object.
  - Never call LLM or network.
  - Deterministic: same inputs → same PipelineDecision.
  - analysis_id is propagated from the response; never regenerated.
"""

from __future__ import annotations

from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step6_clarification.models_internal.models import ClarificationResult
from flowfix.step7_feedback.models_internal.models import FeedbackResult
from flowfix.step8_orchestrator.models_internal.models import PipelineDecision


def decide(
    response: ResponseResult,
    clarification: ClarificationResult,
    feedback: FeedbackResult,
    current_cycle: int = 0,
) -> PipelineDecision:
    """
    Produce a routing decision.

    Parameters
    ----------
    response      : ResponseResult      — Step 5 output
    clarification : ClarificationResult — Step 6 output
    feedback      : FeedbackResult      — Step 7 output
    current_cycle : int                 — number of clarification cycles completed

    Returns
    -------
    PipelineDecision — deterministic; no prior object is modified.
    """
    analysis_id = response.analysis_id
    warnings = list(response.warnings or [])

    # --- Priority 1: Feedback received and processed → RECORD_FEEDBACK ---
    # Terminal: acknowledge the feedback to the user and stop.
    if feedback.feedback_received:
        return PipelineDecision(
            action="RECORD_FEEDBACK",
            analysis_id=analysis_id,
            reason=(
                f"User feedback received and recorded. "
                f"Validation state: {feedback.validation_state}."
            ),
            feedback_validation_state=feedback.validation_state,
            warnings=warnings,
        )

    # --- Priority 2: Max clarification cycles reached → ESCALATE ---
    # Too many rounds without convergence — human intervention needed.
    if clarification.max_questions_reached:
        return PipelineDecision(
            action="ESCALATE",
            analysis_id=analysis_id,
            reason=(
                f"Maximum clarification cycles ({current_cycle}) reached "
                "without sufficient information to diagnose the problem."
            ),
            escalation_reason="max_clarification_cycles",
            warnings=warnings,
        )

    # --- Priority 3: Clarification question available → ASK_CLARIFICATION ---
    if clarification.needs_clarification and clarification.question is not None:
        return PipelineDecision(
            action="ASK_CLARIFICATION",
            analysis_id=analysis_id,
            reason=(
                f"Additional information needed before a diagnosis can be made. "
                f"Asking: {clarification.question.question_type}."
            ),
            clarification_question_type=clarification.question.question_type,
            warnings=warnings,
        )

    # --- Priority 4: RERUN stub ---
    # RERUN is reserved for the external orchestration loop: after the user
    # answers a clarification question, the caller re-invokes the full pipeline
    # (Steps 1-8) with the enriched input and an incremented cycle counter.
    # Step 8 itself never emits RERUN — it is the caller's responsibility.
    # This branch documents the contract without producing dead returns.
    # (re_run_after_answer is consumed by the external caller, not here.)

    # --- Priority 5: Pass-through — response is sufficient → DELIVER ---
    if clarification.pass_through:
        return PipelineDecision(
            action="DELIVER",
            analysis_id=analysis_id,
            reason=(
                f"Response is sufficient for delivery. "
                f"Status: {response.status}, confidence: {response.confidence}."
            ),
            warnings=warnings,
        )

    # --- Priority 6: Fallback → DELIVER (best effort) ---
    # No clarification possible, not a pass-through — deliver what we have.
    return PipelineDecision(
        action="DELIVER",
        analysis_id=analysis_id,
        reason=(
            f"Delivering best-effort response. "
            f"Status: {response.status}, confidence: {response.confidence}."
        ),
        warnings=warnings,
    )
