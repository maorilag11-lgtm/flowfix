"""
FlowFix — Step 8 Knowledge Evolution

Public interface.

Usage:
    from flowfix.step8_knowledge_evolution import run_knowledge_evolution
    result = run_knowledge_evolution(feedback, response, retrieval, problem, analysis, reasoning)
    result.result.candidate_created  # bool
    result.result.candidate          # KnowledgeCandidate | None
    result.result.evolution_state    # "NO_EVOLUTION" | "REVIEW_REQUIRED" | ...
    result.valid                     # bool
"""

from __future__ import annotations
from dataclasses import dataclass

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step7_feedback.models_internal.models import FeedbackResult
from flowfix.step8_knowledge_evolution.models.models import (
    KnowledgeEvolutionResult, KnowledgeCandidate
)
from flowfix.step8_knowledge_evolution.processor.processor import evolve
from flowfix.step8_knowledge_evolution.validation.validator import (
    validate, KnowledgeEvolutionValidation
)


@dataclass
class KnowledgeEvolutionOutput:
    result: KnowledgeEvolutionResult
    validation: KnowledgeEvolutionValidation

    @property
    def valid(self) -> bool:
        return self.validation.valid


def run_knowledge_evolution(
    feedback: FeedbackResult,
    response: ResponseResult,
    retrieval: RetrievalResult,
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    reasoning: ReasoningResult,
) -> KnowledgeEvolutionOutput:
    """Run Step 8 Knowledge Evolution. No KB write. No LLM. Deterministic."""
    result = evolve(feedback, response, retrieval, problem, analysis, reasoning)
    validation = validate(result)
    return KnowledgeEvolutionOutput(result=result, validation=validation)
