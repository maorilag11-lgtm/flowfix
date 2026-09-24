"""
FlowFix — Step 4 Reasoning

Public interface.

Usage
-----
from flowfix.step1_intake import run_intake
from flowfix.step2_analysis import run_analysis
from flowfix.step3_retrieval import run_retrieval
from flowfix.step4_reasoning import run_reasoning

intake    = run_intake(error_text="...", blueprint_text=...)
analysis  = run_analysis(intake.normalized_problem)
retrieval = run_retrieval(intake.normalized_problem, analysis.analysis)
reasoning = run_reasoning(
    intake.normalized_problem,
    analysis.analysis,
    retrieval,
)

reasoning.result.leading_hypothesis   # ReasonedHypothesis | None
reasoning.result.reasoning_status     # ReasoningStatus
reasoning.result.confidence           # Confidence
reasoning.result.ready_for_step5      # bool
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step4_reasoning.reasoner.reasoner import reason
from flowfix.step4_reasoning.validation.validator import validate, ReasoningValidation


@dataclass
class ReasoningOutput:
    result: ReasoningResult
    validation: ReasoningValidation

    @property
    def ready_for_step5(self) -> bool:
        return self.result.ready_for_step5


def run_reasoning(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
) -> ReasoningOutput:
    """
    Run Step 4 reasoning pipeline.

    Parameters
    ----------
    problem   : NormalizedProblem — from run_intake()
    analysis  : WorkflowAnalysis  — from run_analysis().analysis
    retrieval : RetrievalResult   — from run_retrieval()

    Returns
    -------
    ReasoningOutput
    """
    result = reason(problem, analysis, retrieval)
    validation = validate(result)
    return ReasoningOutput(result=result, validation=validation)
