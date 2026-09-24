"""
FlowFix — Step 8 Orchestrator — Validation
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step8_orchestrator.models_internal.models import (
    PipelineDecision,
    ALLOWED_ACTIONS,
)


@dataclass
class OrchestratorValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate(decision: PipelineDecision) -> OrchestratorValidation:
    warnings = list(decision.warnings)

    # action must be valid
    if decision.action not in ALLOWED_ACTIONS:
        return OrchestratorValidation(
            valid=False,
            reason=f"Invalid action: {decision.action!r}.",
            warnings=warnings,
        )

    # analysis_id required
    if not decision.analysis_id:
        return OrchestratorValidation(
            valid=False,
            reason="analysis_id missing — traceability broken.",
            warnings=warnings,
        )

    # reason required
    if not decision.reason:
        return OrchestratorValidation(
            valid=False,
            reason="reason is empty — every decision must be explainable.",
            warnings=warnings,
        )

    # Invariant: ASK_CLARIFICATION → clarification_question_type must be set
    if decision.action == "ASK_CLARIFICATION" and not decision.clarification_question_type:
        return OrchestratorValidation(
            valid=False,
            reason="action=ASK_CLARIFICATION but clarification_question_type is not set.",
            warnings=warnings,
        )

    # Invariant: ESCALATE → escalation_reason must be set
    if decision.action == "ESCALATE" and not decision.escalation_reason:
        warnings.append("action=ESCALATE but escalation_reason is not set.")

    # Invariant: RECORD_FEEDBACK → feedback_validation_state must be set
    if decision.action == "RECORD_FEEDBACK" and not decision.feedback_validation_state:
        warnings.append("action=RECORD_FEEDBACK but feedback_validation_state is not set.")

    # Invariant: RERUN → next_cycle must be positive
    if decision.action == "RERUN" and decision.next_cycle <= 0:
        warnings.append("action=RERUN but next_cycle is not positive.")

    return OrchestratorValidation(
        valid=True,
        reason="Ready.",
        warnings=warnings,
    )
