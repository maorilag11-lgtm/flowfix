"""
FlowFix — Step 6 Clarification — Validation
"""

from __future__ import annotations
from dataclasses import dataclass
from flowfix.step6_clarification.models_internal.models import ClarificationResult


@dataclass
class ClarificationValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate(result: ClarificationResult) -> ClarificationValidation:
    warnings = list(result.warnings)

    if not result.analysis_id:
        return ClarificationValidation(
            valid=False,
            reason="analysis_id missing — traceability broken.",
            warnings=warnings,
        )

    # Invariant: needs_clarification True → question must be set
    if result.needs_clarification and result.question is None:
        return ClarificationValidation(
            valid=False,
            reason="needs_clarification=True but no question generated.",
            warnings=warnings,
        )

    # Invariant: pass_through and needs_clarification are mutually exclusive
    if result.pass_through and result.needs_clarification:
        warnings.append(
            "Both pass_through and needs_clarification are True — "
            "pass_through takes precedence."
        )

    # Invariant: max_questions_reached → needs_clarification must be False
    if result.max_questions_reached and result.needs_clarification:
        warnings.append(
            "max_questions_reached=True but needs_clarification=True — "
            "max_questions_reached takes precedence."
        )

    return ClarificationValidation(
        valid=True,
        reason="Ready for orchestrator.",
        warnings=warnings,
    )
