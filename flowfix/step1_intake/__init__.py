"""
FlowFix — Step 1 Intake

Public interface.

Usage
-----
from flowfix.step1_intake import run_intake

result = run_intake(
    error_text="429 Too Many Requests",
    blueprint_text=None,
    context=None,
    user_description=None,
)

result.normalized_problem  # NormalizedProblem — pass to Step 2
result.validation           # ValidationResult
result.ready_for_step2      # bool
"""

from __future__ import annotations
from dataclasses import dataclass

from .intake.models import NormalizedProblem
from .normalizer.normalizer import normalize
from .validation.validator import validate, ValidationResult


@dataclass
class IntakeResult:
    normalized_problem: NormalizedProblem
    validation: ValidationResult

    @property
    def ready_for_step2(self) -> bool:
        return self.validation.valid


def run_intake(
    error_text: str | None = None,
    blueprint_text: str | None = None,
    context: dict | None = None,
    user_description: str | None = None,
) -> IntakeResult:
    """
    Run the full Step 1 pipeline.

    Parameters
    ----------
    error_text:         Raw error string from the user.
    blueprint_text:     Raw Make.com blueprint JSON string.
    context:            Dict with optional execution context keys.
    user_description:   Free-text problem description.

    Returns
    -------
    IntakeResult
        Contains the NormalizedProblem and ValidationResult.
        Call .ready_for_step2 to check whether Step 2 can proceed.
    """
    problem = normalize(
        error_text=error_text,
        blueprint_text=blueprint_text,
        context=context,
        user_description=user_description,
    )
    validation = validate(problem)

    return IntakeResult(
        normalized_problem=problem,
        validation=validation,
    )
