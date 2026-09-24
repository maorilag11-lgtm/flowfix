"""
FlowFix — Step 8 Orchestrator

Public interface.

Usage
-----
from flowfix.step8_orchestrator import run_orchestration

decision = run_orchestration(
    response=response_output.result,
    clarification=clarification_output.result,
    feedback=feedback_output.result,
    current_cycle=0,
)

decision.result.action   # "DELIVER" | "ASK_CLARIFICATION" | "ESCALATE" | ...
decision.result.reason   # str — why this action was chosen
decision.ready           # bool
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step6_clarification.models_internal.models import ClarificationResult
from flowfix.step7_feedback.models_internal.models import FeedbackResult
from flowfix.step8_orchestrator.models_internal.models import PipelineDecision
from flowfix.step8_orchestrator.orchestrator.orchestrator import decide
from flowfix.step8_orchestrator.validation.validator import validate, OrchestratorValidation


@dataclass
class OrchestratorOutput:
    result: PipelineDecision
    validation: OrchestratorValidation

    @property
    def ready(self) -> bool:
        return self.validation.valid


def run_orchestration(
    response: ResponseResult,
    clarification: ClarificationResult,
    feedback: FeedbackResult,
    current_cycle: int = 0,
) -> OrchestratorOutput:
    """
    Run Step 8 orchestration.

    Parameters
    ----------
    response      : ResponseResult      — from run_response() (Step 5)
    clarification : ClarificationResult — from run_clarification() (Step 6)
    feedback      : FeedbackResult      — from process_feedback() (Step 7)
    current_cycle : int                 — number of clarification cycles completed

    Returns
    -------
    OrchestratorOutput — call .result.action to route the pipeline.
    """
    decision = decide(response, clarification, feedback, current_cycle)
    validation = validate(decision)
    return OrchestratorOutput(result=decision, validation=validation)
