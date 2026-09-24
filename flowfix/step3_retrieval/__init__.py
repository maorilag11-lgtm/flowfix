"""
FlowFix — Step 3 Retrieval

Public interface.

Usage
-----
from flowfix.step1_intake import run_intake
from flowfix.step2_analysis import run_analysis
from flowfix.step3_retrieval import run_retrieval

intake   = run_intake(error_text="429 Too Many Requests", blueprint_text=...)
analysis = run_analysis(intake.normalized_problem)
retrieval = run_retrieval(
    problem=intake.normalized_problem,
    analysis=analysis.analysis,
)

retrieval.matches         # list[KBMatch] — sorted by score desc
retrieval.strong_matches  # list[KBMatch] — score >= STRONG_THRESHOLD
retrieval.candidates      # list[KBMatch] — score < STRONG_THRESHOLD
retrieval.ready_for_step4 # bool
"""

from __future__ import annotations

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step3_retrieval.retriever.retriever import retrieve, DEFAULT_TOP_K
from flowfix.step3_retrieval.validation.validator import validate


def run_retrieval(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    top_k: int = DEFAULT_TOP_K,
) -> RetrievalResult:
    """
    Run Step 3 KB retrieval.

    Parameters
    ----------
    problem  : NormalizedProblem — from run_intake()
    analysis : WorkflowAnalysis  — from run_analysis()
    top_k    : int — maximum KB matches to return (default 5)

    Returns
    -------
    RetrievalResult — call .ready_for_step4 to check before proceeding.
    """
    from .kb.loader import KBIntegrityError
    from .models import RetrievalValidation
    try:
        matches, stats, signals = retrieve(problem, analysis, top_k=top_k)
    except KBIntegrityError as exc:
        return RetrievalResult(analysis_id=problem.analysis_id, integrity_status="UNAVAILABLE_OR_INVALID",
            validation=RetrievalValidation(valid=False, reason=str(exc), warnings=["KB integrity failure"]))

    result = RetrievalResult(
        analysis_id=problem.analysis_id,
        matches=matches,
        stats=stats,
        signals=signals,
    )
    result.validation = validate(result)
    return result
