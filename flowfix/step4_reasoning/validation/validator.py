"""
FlowFix — Step 4 Reasoning — Validation
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step4_reasoning.models_internal.models import ReasoningResult


@dataclass
class ReasoningValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate(result: ReasoningResult) -> ReasoningValidation:
    warnings = list(result.warnings)

    if not result.analysis_id:
        return ReasoningValidation(
            valid=False,
            reason="analysis_id missing — traceability broken.",
            warnings=warnings,
        )

    from ..models_internal.corrections import validate_proposals
    error = validate_proposals(result.correction_proposals, result.analysis_id)
    if error:
        return ReasoningValidation(False, error, warnings)
    if result.correction_proposals and (result.reasoning_status != 'DIAGNOSIS_CANDIDATE' or result.leading_hypothesis is None or result.leading_hypothesis.hypothesis_id != result.correction_proposals[0].hypothesis_id):
        return ReasoningValidation(False, 'Correction does not belong to the leading diagnostic candidate.', warnings)

    if result.hypotheses is None:
        return ReasoningValidation(
            valid=False,
            reason="hypotheses list is None — internal error.",
            warnings=warnings,
        )

    if not result.hypotheses and result.reasoning_status != "INSUFFICIENT_EVIDENCE":
        warnings.append("No hypotheses but status is not INSUFFICIENT_EVIDENCE.")

    if result.leading_hypothesis is None and result.reasoning_status == "DIAGNOSIS_CANDIDATE":
        warnings.append("reasoning_status=DIAGNOSIS_CANDIDATE but leading_hypothesis is None.")

    return ReasoningValidation(
        valid=True,
        reason="Ready for Step 5.",
        warnings=warnings,
    )
