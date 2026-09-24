"""
FlowFix — Step 9 Fix Planning — Validation V1.1
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step9_fix_planning.models.models import (
    FixPlanResult,
    FixAction,
    ValidationCriterion,
    ALLOWED_PLAN_STATUSES,
    ALLOWED_ACTION_TYPES,
    ALLOWED_TARGET_TYPES,
    ALLOWED_VALIDATION_CRITERION_TYPES,
    ALLOWED_CONFIDENCE_LEVELS,
)


@dataclass
class FixPlanValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate(result: FixPlanResult) -> FixPlanValidation:
    warnings = list(result.warnings)

    if not result.plan_id:
        return FixPlanValidation(False, "plan_id is empty.", warnings)

    if not result.analysis_id:
        return FixPlanValidation(False, "analysis_id is empty.", warnings)

    if result.status not in ALLOWED_PLAN_STATUSES:
        return FixPlanValidation(False, f"Invalid status: {result.status!r}.", warnings)

    from flowfix.step5_response.formatter.guidance import validate_guidance
    error = validate_guidance(result.diagnostic_checks, result.documented_solutions, result.documentation)
    if error:
        return FixPlanValidation(False, error, warnings)

    from flowfix.step4_reasoning.models_internal.corrections import validate_proposals
    error = validate_proposals(result.correction_proposals, result.analysis_id)
    if error:
        return FixPlanValidation(False, error, warnings)
    if result.correction_proposals:
        p = result.correction_proposals[0]
        if len(result.actions) != 1 or result.actions[0].proposed_change != p.proposed_value or result.actions[0].current_state != p.observed_value:
            return FixPlanValidation(False, 'Action does not match the correction proposal.', warnings)

    # Secrets must not appear in plan text fields
    text_fields = [result.plan_id, result.analysis_id]
    if result.diagnosis_reference:
        text_fields.extend(result.diagnosis_reference.supporting_evidence or [])
        text_fields.extend(result.diagnosis_reference.supporting_signals or [])

    if result.target:
        text_fields.extend([
            result.target.module_name or "",
            result.target.app or "",
            result.target.action or "",
            result.target.field_path or "",
            result.target.evidence_reference or "",
        ])
    for action in result.actions:
        text_fields.extend([
            action.description,
            action.rationale,
            action.current_state or "",
            action.proposed_change or "",
        ])
    if result.expected_outcome:
        text_fields.extend([
            result.expected_outcome.description,
            result.expected_outcome.expected_behavior,
            result.expected_outcome.downstream_expectation or "",
        ])
    for crit in result.validation_criteria:
        text_fields.extend([
            crit.description,
            crit.expected_value or "",
        ])

    for text in text_fields:
        if text and "[REDACTED:" in text:
            return FixPlanValidation(
                False,
                "A plan field contains a [REDACTED:] placeholder — "
                "secrets must not appear in fix plans.",
                warnings,
            )

    # Invariant: READY → at least one action
    if result.status == "READY" and not result.actions:
        return FixPlanValidation(
            False,
            "status=READY but no actions present.",
            warnings,
        )

    # Invariant: action steps must be unique and sequential (starting from 1)
    if result.actions:
        steps = [a.step for a in result.actions]
        sorted_unique = sorted(set(steps))
        expected = list(range(sorted_unique[0], sorted_unique[0] + len(sorted_unique)))
        if steps != sorted_unique or sorted_unique != expected:
            return FixPlanValidation(
                False,
                f"Action steps are not sequential, unique, or consecutive: {steps}",
                warnings,
            )
        for action in result.actions:
            if action.action_type not in ALLOWED_ACTION_TYPES:
                return FixPlanValidation(
                    False,
                    f"Invalid action_type: {action.action_type!r} in step {action.step}.",
                    warnings,
                )

    # target_type must be valid
    if result.target and result.target.target_type not in ALLOWED_TARGET_TYPES:
        return FixPlanValidation(
            False,
            f"Invalid target_type: {result.target.target_type!r}.",
            warnings,
        )

    # validation criterion types must be valid
    for crit in result.validation_criteria:
        if crit.criterion_type not in ALLOWED_VALIDATION_CRITERION_TYPES:
            return FixPlanValidation(
                False,
                f"Invalid criterion_type: {crit.criterion_type!r}.",
                warnings,
            )

    return FixPlanValidation(True, "Ready.", warnings)
