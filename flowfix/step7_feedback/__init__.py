"""
FlowFix — Step 7 Feedback

Public interface.

Usage
-----
from flowfix.step7_feedback import process_feedback
from flowfix.step7_feedback.models_internal.models import UserFeedback

fb = UserFeedback(
    analysis_id=response.analysis_id,
    helpful=True,
    diagnosis_accuracy="correct",
    solution_worked=True,
    resolution_status="resolved",
)

result = process_feedback(
    problem=intake.normalized_problem,
    analysis=analysis.analysis,
    retrieval=retrieval_result,
    reasoning=reasoning_result.result,
    response=response_result.result,
    clarification=clarification_result.result,
    user_feedback=fb,   # or None
)

result.result.validation_state   # "USER_CONFIRMED" | "USER_CORRECTED" | ...
result.result.feedback_received  # bool
result.ready_for_record          # bool
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step6_clarification.models_internal.models import ClarificationResult
from flowfix.step7_feedback.models_internal.models import UserFeedback, FeedbackResult
from flowfix.step7_feedback.processor.processor import process_feedback as _process
from flowfix.step7_feedback.validation.validator import validate, FeedbackValidation


@dataclass
class FeedbackOutput:
    result: FeedbackResult
    validation: FeedbackValidation

    @property
    def ready_for_record(self) -> bool:
        return self.validation.valid


def process_feedback(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
    reasoning: ReasoningResult,
    response: ResponseResult,
    clarification: ClarificationResult,
    user_feedback: Optional[UserFeedback] = None,
) -> FeedbackOutput:
    """
    Run Step 7 feedback processing.
    All prior step objects are read-only.
    No KB write. No LLM. No network. Fully deterministic.
    """
    result = _process(
        problem=problem, analysis=analysis, retrieval=retrieval,
        reasoning=reasoning, response=response, clarification=clarification,
        user_feedback=user_feedback,
    )
    validation = validate(result)
    return FeedbackOutput(result=result, validation=validation)
