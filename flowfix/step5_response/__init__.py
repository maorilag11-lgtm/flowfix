"""
FlowFix — Step 5 Response

Public interface.

Usage
-----
from flowfix.step1_intake import run_intake
from flowfix.step2_analysis import run_analysis
from flowfix.step3_retrieval import run_retrieval
from flowfix.step4_reasoning import run_reasoning
from flowfix.step5_response import run_response

intake    = run_intake(error_text="...", blueprint_text=...)
analysis  = run_analysis(intake.normalized_problem)
retrieval = run_retrieval(intake.normalized_problem, analysis.analysis)
reasoning = run_reasoning(intake.normalized_problem, analysis.analysis, retrieval)
response  = run_response(
    intake.normalized_problem,
    analysis.analysis,
    retrieval,
    reasoning.result,
)

response.result.summary            # str — one-sentence summary
response.result.diagnosis          # str | None — leading candidate with qualifier
response.result.recommended_actions  # list[ActionItem]
response.result.missing_information  # list[str]
response.result.alternative_hypotheses  # list[HypothesisSummary]
response.ready_for_step6           # bool
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step5_response.formatter.formatter import format_response
from flowfix.step5_response.validation.validator import validate, ResponseValidation


@dataclass
class ResponseOutput:
    result: ResponseResult
    validation: ResponseValidation

    @property
    def ready_for_step6(self) -> bool:
        return self.validation.valid


def run_response(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
    reasoning: ReasoningResult,
) -> ResponseOutput:
    """
    Run Step 5 response formatting.

    Parameters
    ----------
    problem   : NormalizedProblem — from run_intake()
    analysis  : WorkflowAnalysis  — from run_analysis().analysis
    retrieval : RetrievalResult   — from run_retrieval()
    reasoning : ReasoningResult   — from run_reasoning().result

    Returns
    -------
    ResponseOutput
    """
    result = format_response(problem, analysis, retrieval, reasoning)
    validation = validate(result)
    return ResponseOutput(result=result, validation=validation)
