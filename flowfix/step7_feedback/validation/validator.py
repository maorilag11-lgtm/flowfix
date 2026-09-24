"""
FlowFix — Step 7 Feedback — Validation
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step7_feedback.models_internal.models import (
    FeedbackResult,
    ALLOWED_DIAGNOSIS_ACCURACY,
    ALLOWED_RESOLUTION_STATUS,
    ALLOWED_VALIDATION_STATES,
)


@dataclass
class FeedbackValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate(result: FeedbackResult) -> FeedbackValidation:
    warnings = list(result.warnings)

    # analysis_id required
    if not result.analysis_id:
        return FeedbackValidation(
            valid=False,
            reason="analysis_id missing — traceability broken.",
            warnings=warnings,
        )

    # feedback_id required
    if not result.feedback_id:
        return FeedbackValidation(
            valid=False,
            reason="feedback_id missing — generated ID should always be present.",
            warnings=warnings,
        )

    # Enum checks (only when feedback received)
    if result.feedback_received:
        if result.diagnosis_accuracy is not None:
            if result.diagnosis_accuracy not in ALLOWED_DIAGNOSIS_ACCURACY:
                return FeedbackValidation(
                    valid=False,
                    reason=f"Invalid diagnosis_accuracy: {result.diagnosis_accuracy!r}. "
                           f"Allowed: {sorted(ALLOWED_DIAGNOSIS_ACCURACY)}",
                    warnings=warnings,
                )

        if result.resolution_status not in ALLOWED_RESOLUTION_STATUS:
            return FeedbackValidation(
                valid=False,
                reason=f"Invalid resolution_status: {result.resolution_status!r}. "
                       f"Allowed: {sorted(ALLOWED_RESOLUTION_STATUS)}",
                warnings=warnings,
            )

    # validation_state must be a known value
    if result.validation_state not in ALLOWED_VALIDATION_STATES:
        return FeedbackValidation(
            valid=False,
            reason=f"Unknown validation_state: {result.validation_state!r}.",
            warnings=warnings,
        )

    # Coherence: if feedback_received=False, validation_state should be NO_FEEDBACK
    if not result.feedback_received and result.validation_state != "NO_FEEDBACK":
        warnings.append(
            f"feedback_received=False but validation_state={result.validation_state!r}."
        )

    # Coherence: if feedback_received=True, validation_state should not be NO_FEEDBACK
    if result.feedback_received and result.validation_state == "NO_FEEDBACK":
        warnings.append(
            "feedback_received=True but validation_state=NO_FEEDBACK — "
            "processor may not have detected any feedback fields."
        )

    return FeedbackValidation(
        valid=True,
        reason="Ready.",
        warnings=warnings,
    )
