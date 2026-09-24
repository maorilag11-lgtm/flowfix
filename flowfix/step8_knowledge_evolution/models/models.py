"""
FlowFix — Step 8 Knowledge Evolution — Models

Strict data contracts for the Knowledge Evolution layer.

Key rules:
  - KnowledgeCandidate is NEVER automatically APPROVED.
  - confidence represents signal strength, NOT technical truth.
  - reported_correction is user-declared, NOT a validated fact.
  - No KB access from this module.
  - Deterministic: same inputs → same candidate structure.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Strict enum sets
# ---------------------------------------------------------------------------

ALLOWED_CANDIDATE_TYPES = frozenset({
    "KNOWLEDGE_GAP",
    "POSSIBLE_CORRECTION",
    "NEW_PATTERN",
    "RECURRING_CASE",
    "INSUFFICIENT_KB_COVERAGE",
})

ALLOWED_SOURCES = frozenset({
    "USER_FEEDBACK",
    "SYSTEM_OBSERVATION",
    "RECURRING_CASE",
})

ALLOWED_STATUSES = frozenset({
    "CANDIDATE",
    "REVIEW_REQUIRED",
    "REJECTED",
    "APPROVED",
})

ALLOWED_CONFIDENCES = frozenset({
    "LOW",
    "MEDIUM",
    "HIGH",
    "UNKNOWN",
})

ALLOWED_EVOLUTION_STATES = frozenset({
    "NO_EVOLUTION",
    "CANDIDATE_CREATED",
    "REVIEW_REQUIRED",
})


# ---------------------------------------------------------------------------
# KnowledgeCandidate
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeCandidate:
    """
    A structured candidate for future KB evolution.

    This is an observation record — never a validated truth.
    It must be reviewed by a human or external validation process
    before any KB modification can occur.

    Fields
    ------
    candidate_id : str
        Unique identifier for this candidate. Generated at creation.
    analysis_id : str
        From the pipeline that produced the feedback.
    feedback_id : str
        From the FeedbackResult that triggered this candidate.
    candidate_type : str
        One of ALLOWED_CANDIDATE_TYPES.
    source : str
        One of ALLOWED_SOURCES.
    status : str
        One of ALLOWED_STATUSES. Never automatically APPROVED.
    title : str
        Short, deterministic, descriptive title.
    description : str
        Factual description distinguishing observed facts from user-reported info.
    observed_problem : str
        What was observed — derived from pipeline data only, never invented.
    reported_correction : Optional[str]
        User-declared correction. Stored verbatim, never interpreted as truth.
    supporting_evidence : list[str]
        Evidence traceable to real pipeline data. Never invented.
    related_kb_ids : list[str]
        KB entry IDs from Step 3 retrieval. Never invented.
    confidence : str
        Signal strength (LOW/MEDIUM/HIGH/UNKNOWN). NOT technical validation.
    occurrence_count : Optional[int]
        Number of real observations. 1 for single-case. None if unknown.
    warnings : list[str]
        Propagated from prior steps.
    """
    # candidate_id is set deterministically by the processor (not by default_factory).
    candidate_id: str = ""
    analysis_id: str = ""
    feedback_id: str = ""
    candidate_type: str = "KNOWLEDGE_GAP"
    source: str = "USER_FEEDBACK"
    status: str = "CANDIDATE"
    title: str = ""
    description: str = ""
    observed_problem: str = ""
    reported_correction: Optional[str] = None
    supporting_evidence: list[str] = field(default_factory=list)
    related_kb_ids: list[str] = field(default_factory=list)
    confidence: str = "UNKNOWN"
    occurrence_count: Optional[int] = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.candidate_type not in ALLOWED_CANDIDATE_TYPES:
            raise ValueError(
                f"Invalid candidate_type: {self.candidate_type!r}. "
                f"Allowed: {sorted(ALLOWED_CANDIDATE_TYPES)}"
            )
        if self.source not in ALLOWED_SOURCES:
            raise ValueError(
                f"Invalid source: {self.source!r}. "
                f"Allowed: {sorted(ALLOWED_SOURCES)}"
            )
        if self.status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Invalid status: {self.status!r}. "
                f"Allowed: {sorted(ALLOWED_STATUSES)}"
            )
        if self.confidence not in ALLOWED_CONFIDENCES:
            raise ValueError(
                f"Invalid confidence: {self.confidence!r}. "
                f"Allowed: {sorted(ALLOWED_CONFIDENCES)}"
            )

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# KnowledgeEvolutionResult
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEvolutionResult:
    """
    Output of the Knowledge Evolution processor.

    Fields
    ------
    analysis_id : str
        Propagated for traceability.
    feedback_id : str
        Propagated for traceability.
    candidate_created : bool
        Whether a KnowledgeCandidate was produced.
    candidate : Optional[KnowledgeCandidate]
        The candidate, or None if no evolution was warranted.
    evolution_state : str
        One of ALLOWED_EVOLUTION_STATES.
    warnings : list[str]
        Propagated warnings.
    """
    analysis_id: str = ""
    feedback_id: str = ""
    candidate_created: bool = False
    candidate: Optional[KnowledgeCandidate] = None
    evolution_state: str = "NO_EVOLUTION"
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.evolution_state not in ALLOWED_EVOLUTION_STATES:
            raise ValueError(
                f"Invalid evolution_state: {self.evolution_state!r}. "
                f"Allowed: {sorted(ALLOWED_EVOLUTION_STATES)}"
            )

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
