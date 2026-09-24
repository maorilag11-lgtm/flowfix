"""
FlowFix — Step 6 Clarification

Public interface.

Usage
-----
from flowfix.step6_clarification import run_clarification

clarification = run_clarification(
    response=response_output.result,      # ResponseResult from Step 5
    problem=intake.normalized_problem,    # NormalizedProblem from Step 1
    cycle=0,                              # number of prior clarification cycles
)

clarification.result.needs_clarification  # bool
clarification.result.question             # ClarificationQuestion | None
clarification.result.pass_through         # bool — deliver Step 5 result as-is
clarification.result.max_questions_reached # bool — escalate

Pipeline decision:
  - pass_through = True   → deliver ResponseResult to the user, done
  - needs_clarification   → ask question.question_text, re-run pipeline with answer
  - max_questions_reached → deliver a "please contact support" fallback
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step6_clarification.models_internal.models import ClarificationResult
from flowfix.step6_clarification.engine.engine import decide_clarification
from flowfix.step6_clarification.validation.validator import validate, ClarificationValidation


@dataclass
class ClarificationOutput:
    result: ClarificationResult
    validation: ClarificationValidation

    @property
    def ready_for_orchestrator(self) -> bool:
        return self.validation.valid


def run_clarification(
    response: ResponseResult,
    problem: NormalizedProblem,
    cycle: int = 0,
    *, answered_gaps: Optional[list[str]] = None,
) -> ClarificationOutput:
    """
    Run Step 6 clarification decision.

    Parameters
    ----------
    response : ResponseResult    — from run_response() (Step 5)
    problem  : NormalizedProblem — from run_intake() (Step 1)
    cycle    : int               — number of clarification cycles already run

    Returns
    -------
    ClarificationOutput
    """
    result = decide_clarification(response, problem, cycle, answered_gaps=answered_gaps)
    validation = validate(result)
    return ClarificationOutput(result=result, validation=validation)
