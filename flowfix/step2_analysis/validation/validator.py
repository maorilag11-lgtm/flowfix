"""
FlowFix — Step 2 Analysis — Validation

Validates that a WorkflowAnalysis is ready to be passed to Step 3 (KB Search).

Validation is tolerant:
  - A valid analysis does not require a blueprint (can work from error text only).
  - A valid analysis does not require a failure location (may be undetermined).
  - An analysis with only warnings is still valid.

Only fails when the output is structurally broken.
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step2_analysis.models import WorkflowAnalysis


@dataclass
class Step2ValidationResult:
    valid: bool
    reason: str
    errors: list[str]
    warnings: list[str]


def validate(analysis: WorkflowAnalysis) -> Step2ValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(analysis.warnings)

    # analysis_id must be carried through
    if not analysis.analysis_id:
        errors.append("analysis_id is missing — traceability broken.")

    # Must have at least one form of content:
    # observed facts, signals, a graph, a failure location, warnings, or missing_information.
    # user_description alone is enough — Step 3 can still search on it.
    has_content = (
        analysis.observed_facts
        or analysis.diagnostic_signals
        or analysis.workflow.module_count > 0
        or analysis.failure_location is not None
        or analysis.warnings
        or analysis.missing_information
    )
    if not has_content:
        errors.append(
            "Analysis produced no useful content — no facts, signals, graph, failure location, "
            "warnings, or missing information."
        )

    valid = len(errors) == 0
    reason = "Ready for Step 3." if valid else f"Analysis incomplete: {'; '.join(errors)}"

    return Step2ValidationResult(
        valid=valid,
        reason=reason,
        errors=errors,
        warnings=warnings,
    )
