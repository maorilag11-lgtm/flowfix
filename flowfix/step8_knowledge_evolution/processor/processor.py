"""
FlowFix — Step 8 Knowledge Evolution — Processor

Transforms feedback observations into Knowledge Candidates.

Rules (hard):
  - Never access the KB directly.
  - Never invent evidence not present in input data.
  - Never automatically APPROVE a candidate.
  - Never infer technical truth from user declarations.
  - Never duplicate Step 4 reasoning.
  - No LLM, no network, no ML.
  - Deterministic: same inputs → same KnowledgeEvolutionResult.
  - Secrets ([REDACTED:*]) must never appear in candidate fields.

Decision table:
  feedback_received=False           → NO_EVOLUTION
  validation_state=USER_CONFIRMED   → NO_EVOLUTION (confirmed = no gap needed)
  validation_state=USER_CORRECTED   → POSSIBLE_CORRECTION (REVIEW_REQUIRED)
  validation_state=USER_REJECTED    → KNOWLEDGE_GAP if enough context, else NO_EVOLUTION
  validation_state=UNRESOLVED
    + solution_worked=False
    + enough context               → KNOWLEDGE_GAP (REVIEW_REQUIRED)
    else                           → NO_EVOLUTION
  validation_state=FEEDBACK_RECEIVED
    + solution_worked=False        → KNOWLEDGE_GAP if enough context
    else                           → NO_EVOLUTION
  else                             → NO_EVOLUTION
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step5_response.models_internal.models import ResponseResult
from flowfix.step7_feedback.models_internal.models import FeedbackResult

from flowfix.step8_knowledge_evolution.models.models import (
    KnowledgeCandidate,
    KnowledgeEvolutionResult,
    ALLOWED_CANDIDATE_TYPES,
)
import hashlib as _hashlib


def _make_candidate_id(analysis_id: str, feedback_id: str, candidate_type: str) -> str:
    """Derive a stable, deterministic candidate_id. No randomness."""
    key = f"{analysis_id}|{feedback_id}|{candidate_type}"
    return _hashlib.sha256(key.encode()).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Secret guard
# ---------------------------------------------------------------------------

def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


def _safe(v: Optional[str], fallback: str = "") -> str:
    """Return value only if non-empty and not redacted."""
    if not v or _is_redacted(v):
        return fallback
    return v.strip()


# ---------------------------------------------------------------------------
# Evidence extraction — never invent, only report observable facts
# ---------------------------------------------------------------------------

def _build_evidence(
    feedback: FeedbackResult,
    response: ResponseResult,
    retrieval: RetrievalResult,
) -> list[str]:
    """
    Build supporting evidence from real, observable pipeline data.
    Every item is traceable to an actual input field.
    """
    ev = []

    # From feedback
    if feedback.diagnosis_accuracy:
        ev.append(f"diagnosis_accuracy={feedback.diagnosis_accuracy} (reported by user)")
    if feedback.solution_worked is not None:
        ev.append(f"solution_worked={feedback.solution_worked} (reported by user)")
    if feedback.resolution_status and feedback.resolution_status != "unknown":
        ev.append(f"resolution_status={feedback.resolution_status} (reported by user)")
    if _safe(feedback.corrected_diagnosis):
        ev.append("corrected_diagnosis provided by user (not technically validated)")
    if _safe(feedback.actual_resolution):
        ev.append("actual_resolution provided by user (not technically validated)")

    # From response (already produced by Step 5 — read-only)
    if response.status:
        ev.append(f"pipeline_status={response.status}")
    if response.confidence and response.confidence != "unknown":
        ev.append(f"pipeline_confidence={response.confidence}")

    # From retrieval — KB IDs are real identifiers, not invented
    if retrieval.strong_matches:
        ev.append(
            f"{len(retrieval.strong_matches)} strong KB match(es) in Step 3 retrieval"
        )

    return ev


def _extract_kb_ids(retrieval: RetrievalResult) -> list[str]:
    """
    Return real KB entry IDs from Step 3 retrieval.
    Never invent an ID.
    """
    return [m.entry_id for m in retrieval.strong_matches[:3] if m.entry_id]


# ---------------------------------------------------------------------------
# Observed problem — derive from available facts, never invent
# ---------------------------------------------------------------------------

def _build_observed_problem(
    feedback: FeedbackResult,
    response: ResponseResult,
) -> str:
    parts = []
    if response.status:
        parts.append(f"Reasoning status: {response.status}.")
    if feedback.diagnosis_accuracy:
        parts.append(
            f"User reported diagnosis_accuracy={feedback.diagnosis_accuracy}."
        )
    if feedback.solution_worked is not None:
        parts.append(
            f"User reported solution_worked={feedback.solution_worked}."
        )
    if feedback.resolution_status and feedback.resolution_status != "unknown":
        parts.append(f"Resolution status: {feedback.resolution_status}.")
    return " ".join(parts) if parts else "Observed from pipeline data (details above)."


# ---------------------------------------------------------------------------
# Confidence derivation — signal strength only
# ---------------------------------------------------------------------------

def _derive_confidence(feedback: FeedbackResult, retrieval: RetrievalResult) -> str:
    """
    Derive signal strength from available evidence.
    HIGH = multiple strong signals. LOW = sparse data.
    """
    signals = 0
    if feedback.diagnosis_accuracy in ("incorrect", "partially_correct"):
        signals += 1
    if feedback.solution_worked is False:
        signals += 1
    if _safe(feedback.corrected_diagnosis):
        signals += 1
    if retrieval.strong_matches:
        signals += 1
    if feedback.validation_state in ("USER_CORRECTED", "USER_REJECTED"):
        signals += 1

    if signals >= 4:
        return "HIGH"
    if signals >= 2:
        return "MEDIUM"
    if signals >= 1:
        return "LOW"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Context sufficiency — does the data justify creating a candidate?
# ---------------------------------------------------------------------------

def _has_sufficient_context(
    feedback: FeedbackResult,
    response: ResponseResult,
) -> bool:
    """
    True when there are enough real signals to warrant a candidate.
    Prevents creating candidates from pure absence-of-information.
    """
    # At minimum, we need either an error context or a diagnosis state
    has_response_context = response.status not in (None, "")
    has_retrieval_signal = bool(response.observed or response.evidence)
    has_feedback_signal = (
        feedback.diagnosis_accuracy is not None
        or feedback.solution_worked is not None
        or bool(feedback.corrected_diagnosis)
    )
    return has_response_context and (has_retrieval_signal or has_feedback_signal)


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------

def _make_possible_correction(
    feedback: FeedbackResult,
    response: ResponseResult,
    retrieval: RetrievalResult,
    analysis_id: str,
) -> KnowledgeCandidate:
    """
    CAS C: USER_CORRECTED — user provided a corrected diagnosis.
    The correction is stored verbatim, never treated as validated truth.
    """
    correction = _safe(feedback.corrected_diagnosis) or _safe(feedback.actual_resolution)

    # Title: deterministic, descriptive, no creativity
    status_label = response.status.lower().replace("_", " ") if response.status else "unknown"
    title = f"Possible correction for {status_label} diagnosis"

    description = (
        "The previous diagnosis was marked incorrect or partially correct by the user. "
        "The user provided a correction (see reported_correction). "
        "This correction has NOT been technically validated — it is user-declared information only."
    )

    return KnowledgeCandidate(
        candidate_id=_make_candidate_id(analysis_id, feedback.feedback_id, "POSSIBLE_CORRECTION"),
        analysis_id=analysis_id,
        feedback_id=feedback.feedback_id,
        candidate_type="POSSIBLE_CORRECTION",
        source="USER_FEEDBACK",
        status="REVIEW_REQUIRED",
        title=title,
        description=description,
        observed_problem=_build_observed_problem(feedback, response),
        reported_correction=correction if correction else None,
        supporting_evidence=_build_evidence(feedback, response, retrieval),
        related_kb_ids=_extract_kb_ids(retrieval),
        confidence=_derive_confidence(feedback, retrieval),
        occurrence_count=1,
    )


def _make_knowledge_gap(
    feedback: FeedbackResult,
    response: ResponseResult,
    retrieval: RetrievalResult,
    analysis_id: str,
) -> KnowledgeCandidate:
    """
    CAS D/E: USER_REJECTED or UNRESOLVED with failed solution.
    A gap is suspected but not confirmed.
    """
    status_label = response.status.lower().replace("_", " ") if response.status else "unknown"
    title = f"Knowledge gap for {status_label} case"

    description = (
        "The diagnosis was marked incorrect or the solution failed to resolve the issue. "
        "No user correction was provided. "
        "Available data suggests a possible gap in current KB coverage for this case. "
        "This is a candidate for review — not a confirmed gap."
    )

    return KnowledgeCandidate(
        candidate_id=_make_candidate_id(analysis_id, feedback.feedback_id, "KNOWLEDGE_GAP"),
        analysis_id=analysis_id,
        feedback_id=feedback.feedback_id,
        candidate_type="KNOWLEDGE_GAP",
        source="USER_FEEDBACK",
        status="REVIEW_REQUIRED",
        title=title,
        description=description,
        observed_problem=_build_observed_problem(feedback, response),
        reported_correction=None,
        supporting_evidence=_build_evidence(feedback, response, retrieval),
        related_kb_ids=_extract_kb_ids(retrieval),
        confidence=_derive_confidence(feedback, retrieval),
        occurrence_count=1,
    )


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

def evolve(
    feedback: FeedbackResult,
    response: ResponseResult,
    retrieval: RetrievalResult,
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    reasoning: ReasoningResult,
) -> KnowledgeEvolutionResult:
    """
    Determine whether a Knowledge Candidate should be created from
    the available feedback and pipeline observations.

    Parameters
    ----------
    feedback  : FeedbackResult       — Step 7 output (primary input)
    response  : ResponseResult       — Step 5 output (read-only context)
    retrieval : RetrievalResult      — Step 3 output (read-only, for KB IDs)
    problem   : NormalizedProblem    — Step 1 output (read-only context)
    analysis  : WorkflowAnalysis     — Step 2 output (read-only context)
    reasoning : ReasoningResult      — Step 4 output (read-only context)

    Returns
    -------
    KnowledgeEvolutionResult — candidate or NO_EVOLUTION.
    Never modifies the KB. Never modifies input objects.
    """
    analysis_id = feedback.analysis_id or response.analysis_id
    result = KnowledgeEvolutionResult(
        analysis_id=analysis_id,
        feedback_id=feedback.feedback_id,
        warnings=list(feedback.warnings or []),
    )

    # Rule 1: No exploitable feedback → NO_EVOLUTION
    if not feedback.feedback_received or feedback.validation_state == "NO_FEEDBACK":
        result.evolution_state = "NO_EVOLUTION"
        return result

    state = feedback.validation_state

    # Rule 2: USER_CONFIRMED → NO_EVOLUTION (confirmed case, no gap)
    if state == "USER_CONFIRMED":
        result.evolution_state = "NO_EVOLUTION"
        return result

    # Rule 3: USER_CORRECTED → POSSIBLE_CORRECTION
    if state == "USER_CORRECTED":
        candidate = _make_possible_correction(feedback, response, retrieval, analysis_id)
        result.candidate = candidate
        result.candidate_created = True
        result.evolution_state = "REVIEW_REQUIRED"
        return result

    # Rule 4: USER_REJECTED → KNOWLEDGE_GAP if sufficient context
    if state == "USER_REJECTED":
        if _has_sufficient_context(feedback, response):
            candidate = _make_knowledge_gap(feedback, response, retrieval, analysis_id)
            result.candidate = candidate
            result.candidate_created = True
            result.evolution_state = "REVIEW_REQUIRED"
            return result
        result.evolution_state = "NO_EVOLUTION"
        return result

    # Rule 5: UNRESOLVED → KNOWLEDGE_GAP if solution failed AND sufficient context
    if state == "UNRESOLVED":
        if feedback.solution_worked is False and _has_sufficient_context(feedback, response):
            candidate = _make_knowledge_gap(feedback, response, retrieval, analysis_id)
            result.candidate = candidate
            result.candidate_created = True
            result.evolution_state = "REVIEW_REQUIRED"
            return result
        result.evolution_state = "NO_EVOLUTION"
        return result

    # Rule 6: FEEDBACK_RECEIVED (partial) → KNOWLEDGE_GAP only if solution failed + context
    if state == "FEEDBACK_RECEIVED":
        if feedback.solution_worked is False and _has_sufficient_context(feedback, response):
            candidate = _make_knowledge_gap(feedback, response, retrieval, analysis_id)
            result.candidate = candidate
            result.candidate_created = True
            result.evolution_state = "REVIEW_REQUIRED"
            return result
        result.evolution_state = "NO_EVOLUTION"
        return result

    # Fallback
    result.evolution_state = "NO_EVOLUTION"
    return result
