"""
FlowFix — Step 5 Response — Models

Output contract for Step 5, the final layer before the user.

Design principles:
  - Step 5 is a PRESENTATION layer, not a reasoning layer.
  - Step 4 produced the analysis; Step 5 structures it for the user.
  - Confidence and status come from ReasoningResult — never recalculated here.
  - Hypotheses are presented as hypotheses, never upgraded to confirmed facts.
  - Secrets remain redacted.
  - No KB access, no LLM, no network calls.
  - Deterministic: same input → same output.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from flowfix.step4_reasoning.models_internal.corrections import ManualCorrectionProposal
from flowfix.step5_response.models_internal.guidance import (
    DiagnosticCheck, DocumentedSolution, DocumentationReference,
)


# ---------------------------------------------------------------------------
# Response status — mirrors reasoning status for external consumers
# ---------------------------------------------------------------------------

ResponseStatus = str  # one of the ReasoningStatus values, carried through


# ---------------------------------------------------------------------------
# Action item — a concrete step the user can take
# ---------------------------------------------------------------------------

@dataclass
class ActionItem:
    """A concrete, verifiable step the user can take."""
    step: int
    description: str
    source: str   # "kb_entry:<id>", "structural_signal", "execution_context"
    purpose: str = "verification"  # or documented_solution; never permission to apply


# ---------------------------------------------------------------------------
# Evidence summary — human-readable, no internal IDs exposed to user
# ---------------------------------------------------------------------------

@dataclass
class EvidenceSummary:
    """A piece of evidence presented to the user."""
    description: str
    evidence_type: str    # "structural", "error_signal", "kb_match", "execution_context"
    source_label: str     # human-readable label, no raw internal IDs


# ---------------------------------------------------------------------------
# Hypothesis summary — for alternatives section
# ---------------------------------------------------------------------------

@dataclass
class HypothesisSummary:
    """Summary of an alternative hypothesis for the user."""
    statement: str
    confidence: str      # high / medium / low / unknown
    distinguishing_check: str   # what would confirm or rule this out


# ---------------------------------------------------------------------------
# Root output — ResponseResult
# ---------------------------------------------------------------------------

@dataclass
class ResponseResult:
    """
    Step 5 output — the structured user-facing response.

    This is consumed by Step 6 (Unknown Cases) or directly rendered by a UI.
    It does NOT contain raw internal scores, hypothesis IDs, or KB entry IDs
    in the user-facing fields — those belong to the structured metadata only.
    """
    # Traceability
    analysis_id: str = ""

    # Overall status (carried from ReasoningResult)
    status: ResponseStatus = "INSUFFICIENT_EVIDENCE"

    # Confidence (carried from ReasoningResult — never recalculated)
    confidence: str = "unknown"

    # -----------------------------------------------------------------------
    # User-facing sections
    # -----------------------------------------------------------------------

    # One-sentence summary of the situation
    summary: str = ""

    # What was observed (from facts)
    observed: list[str] = field(default_factory=list)

    # Diagnosis section — only populated when status allows a candidate
    diagnosis: Optional[str] = None       # the leading hypothesis statement
    diagnosis_confidence: str = "unknown"  # same as confidence
    diagnosis_is_candidate: bool = False   # True = candidate, False = hypothesis only

    # Evidence supporting the diagnosis
    evidence: list[EvidenceSummary] = field(default_factory=list)

    # Concrete recommended actions (from KB diagnosis_steps + solutions)
    recommended_actions: list[ActionItem] = field(default_factory=list)

    # What is unknown or missing — user needs to provide this
    missing_information: list[str] = field(default_factory=list)

    # Alternative hypotheses (only when MULTIPLE_CANDIDATES or CONTRADICTED)
    alternative_hypotheses: list[HypothesisSummary] = field(default_factory=list)

    # Warnings inherited from prior steps
    warnings: list[str] = field(default_factory=list)

    # -----------------------------------------------------------------------
    # Metadata (not for direct display to end users)
    # -----------------------------------------------------------------------

    # Whether a leading hypothesis exists
    has_leading_hypothesis: bool = False

    # Signals that informed the analysis (for debugging)
    diagnostic_signals: list[str] = field(default_factory=list)

    candidate_checks: list[dict] = field(default_factory=list)

    diagnostic_checks: list[DiagnosticCheck] = field(default_factory=list)
    documented_solutions: list[DocumentedSolution] = field(default_factory=list)
    documentation: list[DocumentationReference] = field(default_factory=list)
    guidance_markdown: str = ''

    correction_proposals: list[ManualCorrectionProposal] = field(default_factory=list)
    correction_gaps: list[str] = field(default_factory=list)
    correction_markdown: str = ''

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
