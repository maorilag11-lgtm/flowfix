"""
FlowFix — Step 5 Response — Validation
"""

from __future__ import annotations
from dataclasses import dataclass
from flowfix.step5_response.models_internal.models import ResponseResult


@dataclass
class ResponseValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate(response: ResponseResult) -> ResponseValidation:
    warnings = list(response.warnings)

    if not response.analysis_id:
        return ResponseValidation(
            valid=False,
            reason="analysis_id missing — traceability broken.",
            warnings=warnings,
        )

    from ..formatter.guidance import validate_guidance
    error = validate_guidance(response.diagnostic_checks, response.documented_solutions, response.documentation)
    if error:
        return ResponseValidation(False, error, warnings)

    from flowfix.step4_reasoning.models_internal.corrections import validate_proposals
    error = validate_proposals(response.correction_proposals, response.analysis_id)
    if error:
        return ResponseValidation(False, error, warnings)

    if not response.summary:
        warnings.append("Response summary is empty.")

    # Invariant: if has_leading_hypothesis, diagnosis must be set
    if response.has_leading_hypothesis and not response.diagnosis:
        warnings.append("has_leading_hypothesis=True but diagnosis is empty.")

    # Invariant: INSUFFICIENT_EVIDENCE → no diagnosis
    if response.status == "INSUFFICIENT_EVIDENCE" and response.diagnosis:
        warnings.append(
            "INSUFFICIENT_EVIDENCE status with a diagnosis set — "
            "review formatter logic."
        )

    return ResponseValidation(
        valid=True,
        reason="Ready for Step 6.",
        warnings=warnings,
    )
