"""
FlowFix — Step 8 Knowledge Evolution — Validation
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from flowfix.step8_knowledge_evolution.models.models import (
    KnowledgeCandidate,
    KnowledgeEvolutionResult,
    ALLOWED_CANDIDATE_TYPES,
    ALLOWED_SOURCES,
    ALLOWED_STATUSES,
    ALLOWED_CONFIDENCES,
    ALLOWED_EVOLUTION_STATES,
)


@dataclass
class KnowledgeEvolutionValidation:
    valid: bool
    reason: str
    warnings: list[str]


def validate_candidate(candidate: KnowledgeCandidate) -> KnowledgeEvolutionValidation:
    """Validate a single KnowledgeCandidate."""
    warnings: list[str] = []

    if not candidate.analysis_id:
        return KnowledgeEvolutionValidation(False, "candidate.analysis_id is empty.", warnings)
    if not candidate.feedback_id:
        return KnowledgeEvolutionValidation(False, "candidate.feedback_id is empty.", warnings)
    if not candidate.title:
        return KnowledgeEvolutionValidation(False, "candidate.title is empty.", warnings)
    if not candidate.description:
        return KnowledgeEvolutionValidation(False, "candidate.description is empty.", warnings)

    if candidate.candidate_type not in ALLOWED_CANDIDATE_TYPES:
        return KnowledgeEvolutionValidation(
            False,
            f"Invalid candidate_type: {candidate.candidate_type!r}.",
            warnings,
        )
    if candidate.source not in ALLOWED_SOURCES:
        return KnowledgeEvolutionValidation(
            False, f"Invalid source: {candidate.source!r}.", warnings
        )
    if candidate.status not in ALLOWED_STATUSES:
        return KnowledgeEvolutionValidation(
            False, f"Invalid status: {candidate.status!r}.", warnings
        )
    if candidate.confidence not in ALLOWED_CONFIDENCES:
        return KnowledgeEvolutionValidation(
            False, f"Invalid confidence: {candidate.confidence!r}.", warnings
        )

    # occurrence_count: must be positive int when set
    if candidate.occurrence_count is not None and candidate.occurrence_count < 1:
        return KnowledgeEvolutionValidation(
            False,
            f"occurrence_count must be >= 1 when set, got {candidate.occurrence_count}.",
            warnings,
        )

    # APPROVED is never valid for an auto-generated candidate
    if candidate.status == "APPROVED":
        return KnowledgeEvolutionValidation(
            False,
            "status=APPROVED is not allowed for auto-generated candidates. "
            "Approval requires explicit external validation.",
            warnings,
        )

    # Secrets must not appear in candidate text fields
    text_fields = [
        candidate.title, candidate.description, candidate.observed_problem,
        candidate.reported_correction or "",
    ] + list(candidate.supporting_evidence)

    for text in text_fields:
        if text and "[REDACTED:" in text:
            return KnowledgeEvolutionValidation(
                False,
                "A candidate field contains a [REDACTED:] placeholder — "
                "secrets must not appear in Knowledge Candidates.",
                warnings,
            )

    return KnowledgeEvolutionValidation(True, "Candidate is valid.", warnings)


def validate(result: KnowledgeEvolutionResult) -> KnowledgeEvolutionValidation:
    """Validate a KnowledgeEvolutionResult."""
    warnings: list[str] = list(result.warnings)

    if not result.analysis_id:
        return KnowledgeEvolutionValidation(False, "analysis_id is empty.", warnings)

    if result.evolution_state not in ALLOWED_EVOLUTION_STATES:
        return KnowledgeEvolutionValidation(
            False,
            f"Invalid evolution_state: {result.evolution_state!r}.",
            warnings,
        )

    # Coherence: candidate_created=True → candidate must be set
    if result.candidate_created and result.candidate is None:
        return KnowledgeEvolutionValidation(
            False,
            "candidate_created=True but candidate is None.",
            warnings,
        )

    # Coherence: candidate_created=False → candidate must be None
    if not result.candidate_created and result.candidate is not None:
        warnings.append(
            "candidate_created=False but candidate is set — "
            "this is inconsistent; candidate will be ignored."
        )

    # Coherence: NO_EVOLUTION → candidate_created must be False
    if result.evolution_state == "NO_EVOLUTION" and result.candidate_created:
        warnings.append(
            "evolution_state=NO_EVOLUTION but candidate_created=True — inconsistent."
        )

    # Validate the candidate itself if present
    if result.candidate is not None:
        candidate_validation = validate_candidate(result.candidate)
        if not candidate_validation.valid:
            return candidate_validation
        warnings.extend(candidate_validation.warnings)

    return KnowledgeEvolutionValidation(True, "Ready for review.", warnings)
