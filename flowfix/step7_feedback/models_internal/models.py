"""
FlowFix — Step 7 Feedback — Models

Input and output contracts for Step 7.

Design principles:
  - UserFeedback is user-provided data — never treated as confirmed ground truth.
  - FeedbackResult is the structured output of Step 7.
  - All enums are strict — invalid values raise at construction time.
  - No automatic KB write, no diagnosis change, no scoring change.
  - feedback_id is generated for identification; it does not influence logic.
  - analysis_id is propagated from prior steps — never regenerated.
  - Deterministic: same inputs → same FeedbackResult.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid

# ---------------------------------------------------------------------------
# Enum-like constants — strict set of allowed values
# ---------------------------------------------------------------------------

ALLOWED_DIAGNOSIS_ACCURACY = frozenset({"correct", "partially_correct", "incorrect", "unknown"})
ALLOWED_SOLUTION_WORKED = frozenset({True, False, None})     # tri-valued boolean
ALLOWED_RESOLUTION_STATUS = frozenset({"resolved", "partially_resolved", "unresolved", "unknown"})

ALLOWED_VALIDATION_STATES = frozenset({
    "NO_FEEDBACK",
    "FEEDBACK_RECEIVED",
    "USER_CONFIRMED",
    "USER_CORRECTED",
    "USER_REJECTED",
    "UNRESOLVED",
})


# ---------------------------------------------------------------------------
# UserFeedback — input provided by the user after receiving the FlowFix response
# ---------------------------------------------------------------------------

@dataclass
class UserFeedback:
    """
    Structured feedback provided by the user after FlowFix delivered a response.

    All fields are optional except analysis_id (which must match the pipeline).

    Fields
    ------
    analysis_id : str
        Must match the analysis_id from prior steps. Required.
    helpful : Optional[bool]
        Was the FlowFix response useful overall?
    diagnosis_accuracy : Optional[str]
        Was the diagnosis correct? One of: correct, partially_correct, incorrect, unknown.
    solution_worked : Optional[bool]
        Did the recommended solution resolve the issue?
    resolution_status : str
        Final status of the problem. One of: resolved, partially_resolved, unresolved, unknown.
    user_comment : Optional[str]
        Free-text comment from the user. Not interpreted as ground truth.
    corrected_diagnosis : Optional[str]
        If the diagnosis was wrong, what was the actual cause? User-declared only.
    actual_resolution : Optional[str]
        What actually resolved the problem? User-declared only.
    """
    analysis_id: str
    helpful: Optional[bool] = None
    diagnosis_accuracy: Optional[str] = None       # or "correct" | "partially_correct" | "incorrect" | "unknown"
    solution_worked: Optional[bool] = None
    resolution_status: str = "unknown"             # "resolved" | "partially_resolved" | "unresolved" | "unknown"
    user_comment: Optional[str] = None
    corrected_diagnosis: Optional[str] = None
    actual_resolution: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate enum fields at construction time."""
        if self.diagnosis_accuracy is not None:
            if self.diagnosis_accuracy not in ALLOWED_DIAGNOSIS_ACCURACY:
                raise ValueError(
                    f"Invalid diagnosis_accuracy: {self.diagnosis_accuracy!r}. "
                    f"Allowed: {sorted(ALLOWED_DIAGNOSIS_ACCURACY)}"
                )
        if self.resolution_status not in ALLOWED_RESOLUTION_STATUS:
            raise ValueError(
                f"Invalid resolution_status: {self.resolution_status!r}. "
                f"Allowed: {sorted(ALLOWED_RESOLUTION_STATUS)}"
            )


# ---------------------------------------------------------------------------
# FeedbackResult — Step 7 output
# ---------------------------------------------------------------------------

@dataclass
class FeedbackResult:
    """
    Step 7 output — structured record of user feedback.

    This is a terminal observation layer. It does not modify the diagnosis,
    the KB, or any prior step output. It records what the user reported and
    derives a deterministic validation_state from the feedback fields.
    """
    # Traceability
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    analysis_id: str = ""

    # Whether feedback was actually provided
    feedback_received: bool = False

    # Feedback fields (copied from UserFeedback when present)
    helpful: Optional[bool] = None
    diagnosis_accuracy: Optional[str] = None
    solution_worked: Optional[bool] = None
    resolution_status: str = "unknown"
    user_comment: Optional[str] = None
    corrected_diagnosis: Optional[str] = None
    actual_resolution: Optional[str] = None

    # Derived state (deterministic from feedback fields)
    validation_state: str = "NO_FEEDBACK"

    # Validation and warnings
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
