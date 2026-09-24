"""
FlowFix — Step 1 Intake — Validation

Checks that a NormalizedProblem has enough information to be passed to Step 2.

Rules:
- Validation is TOLERANT — the user must not be blocked for missing context.
- A problem with only a user description is valid.
- A problem with only a blueprint is valid.
- A problem with only an error message is valid.
- The validator only fails when there is truly NOTHING to work with.
"""

from __future__ import annotations
from dataclasses import dataclass

from ..intake.models import NormalizedProblem


@dataclass
class ValidationResult:
    valid: bool
    reason: str                         # human-readable verdict
    errors: list[str]                   # blocking issues (empty when valid)
    warnings: list[str]                 # non-blocking notices


def validate(problem: NormalizedProblem) -> ValidationResult:
    """
    Validate a NormalizedProblem before it is handed to Step 2.

    Returns a ValidationResult.
    Does NOT query the Knowledge Base.
    Does NOT generate diagnoses.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Minimum content check — at least one source of information must exist
    # -----------------------------------------------------------------------
    has_error_text = bool(problem.errors.exact_error_messages)
    has_blueprint = (
        problem.blueprint.provided
        and problem.blueprint.valid_json
        and problem.blueprint.recognized_as_make_blueprint
    )
    has_description = bool(problem.user_description)
    has_http = bool(problem.errors.http_status_codes)

    if not any([has_error_text, has_blueprint, has_description, has_http]):
        errors.append(
            "No usable input: provide at least an error message, a blueprint, "
            "or a description of the problem."
        )

    # -----------------------------------------------------------------------
    # Blueprint-specific warnings (non-blocking)
    # -----------------------------------------------------------------------
    if problem.blueprint.provided:
        if problem.blueprint.valid_json is False:
            warnings.append("Blueprint was provided but is not valid JSON.")
        elif problem.blueprint.recognized_as_make_blueprint is False:
            warnings.append(
                "Blueprint JSON does not appear to be a Make.com scenario."
            )
        elif has_blueprint and not problem.blueprint.modules:
            warnings.append("Blueprint recognised but no modules could be extracted.")

    # -----------------------------------------------------------------------
    # Context warnings
    # -----------------------------------------------------------------------
    if problem.blueprint.provided and not problem.errors.exact_error_messages:
        warnings.append(
            "Blueprint provided without error message — analysis will cover "
            "structural issues only."
        )

    if problem.errors.exact_error_messages and not problem.blueprint.provided:
        warnings.append(
            "Error message provided without blueprint — diagnosis may be less precise."
        )

    # -----------------------------------------------------------------------
    # analysis_id must always be set
    # -----------------------------------------------------------------------
    if not problem.analysis_id:
        errors.append("analysis_id is missing — this is a normalizer bug.")

    # -----------------------------------------------------------------------
    # Result
    # -----------------------------------------------------------------------
    valid = len(errors) == 0
    reason = (
        "Ready for Step 2."
        if valid
        else f"Intake failed: {'; '.join(errors)}"
    )

    return ValidationResult(
        valid=valid,
        reason=reason,
        errors=errors,
        warnings=warnings,
    )
