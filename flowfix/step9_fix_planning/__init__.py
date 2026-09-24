"""
FlowFix — Step 9 Fix Planning V1.1

Public interface.

Usage
-----
from flowfix.step9_fix_planning import run_fix_planning

result = run_fix_planning(
    problem=intake.normalized_problem,
    analysis=analysis.analysis,
    reasoning=reasoning_result.result,
    response=response_result.result,  # Optional
    decision=orchestrator_result.result,  # Optional per V1.1
)

result.result.status          # "READY" | "PARTIALLY_READY" | "BLOCKED" | "NOT_APPLICABLE"
result.result.actions         # list[FixAction]
result.result.validation_criteria  # list[ValidationCriterion]
result.ready                  # bool

V1.1: Step 8 (PipelineDecision) is OPTIONAL.
Minimum inputs: NormalizedProblem + WorkflowAnalysis + ReasoningResult.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step9_fix_planning.models.models import FixPlanResult
from flowfix.step9_fix_planning.planner.planner import plan
from flowfix.step9_fix_planning.validation.validator import validate, FixPlanValidation


@dataclass
class FixPlanOutput:
    result: FixPlanResult
    validation: FixPlanValidation

    @property
    def ready(self) -> bool:
        """Legacy structural-validity alias; use explicit properties below."""
        return self.validation.valid

    @property
    def structurally_valid(self) -> bool:
        return self.validation.valid

    @property
    def available_for_review(self) -> bool:
        return self.structurally_valid and self.result.status in ("READY", "PARTIALLY_READY")

    @property
    def correction_applicable(self) -> bool:
        return self.available_for_review and any(a.proposed_change is not None for a in self.result.actions)

    @property
    def problem_resolved(self) -> bool:
        # A plan is not an execution result or technical confirmation.
        return False


def run_fix_planning(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    reasoning: ReasoningResult,
    response: Optional[object] = None,   # ResponseResult — optional
    decision: Optional[object] = None,   # PipelineDecision — optional per V1.1
) -> FixPlanOutput:
    """
    Run Step 9 Fix Planning.

    Deterministic. No KB access. No LLM. No network. No Blueprint modification.
    Step 8 (decision) is OPTIONAL per V1.1 contract.
    """
    result = plan(problem, analysis, reasoning, response, decision)
    validation = validate(result)
    return FixPlanOutput(result=result, validation=validation)
