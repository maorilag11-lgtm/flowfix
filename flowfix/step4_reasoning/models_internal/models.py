"""
FlowFix — Step 4 Reasoning — Models

Output contract for Step 4, consumed by Step 5 (Response).

Key design principles:
  - FACT ≠ SIGNAL ≠ HYPOTHESIS ≠ DIAGNOSIS
  - Every hypothesis is scored deterministically from observable signals.
  - Every piece of evidence points to a traceable source.
  - Contradictions are tracked explicitly.
  - "Unknown" is a valid and important output state.
  - No invention: if data is absent, the field is None or empty.
  - Step 4 never generates the user-facing response — that is Step 5's job.
  - No auto-fix, no blueprint modification, no workflow change.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal
from .corrections import ManualCorrectionProposal

# Confidence levels — same convention as Step 2
Confidence = Literal["high", "medium", "low", "unknown"]

# Reasoning status
ReasoningStatus = Literal[
    "DIAGNOSIS_CANDIDATE",     # Leading hypothesis with sufficient evidence
    "MULTIPLE_CANDIDATES",     # Several hypotheses compete; no clear winner
    "WEAK_EVIDENCE",           # Some signals present but none strongly supported
    "INSUFFICIENT_EVIDENCE",   # Not enough information to form a hypothesis
    "CONTRADICTED",            # Best candidate actively contradicted by context
]


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """
    A piece of evidence supporting or contradicting a hypothesis.
    Always traceable to a specific source.
    """
    source: str         # e.g. "workflow_analysis", "error_text", "kb_entry", "execution_context"
    evidence_type: str  # e.g. "structural", "error_signal", "kb_match", "user_reported"
    description: str    # Human-readable explanation of what this evidence shows
    reference: Optional[str] = None  # e.g. module_id, entry_id, field name
    provenance_kind: str = "unspecified"  # observation / knowledge / declaration / hypothesis
    evidence_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------

@dataclass
class ReasonedHypothesis:
    """
    A candidate explanation for the observed problem.

    Important: a hypothesis is never promoted to a confirmed fact within Step 4.
    The leading_hypothesis in ReasoningResult is the BEST CANDIDATE, not the truth.
    """
    hypothesis_id: str                          # e.g. "H1", "H2"
    statement: str                              # The hypothesis in plain language
    source: str                                 # Where this hypothesis originated
                                                # ("step2_analysis", "kb_entry", "derived")
    supporting_signals: list[str] = field(default_factory=list)
    supporting_kb_entries: list[str] = field(default_factory=list)   # KB entry IDs
    contradicting_signals: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    supporting_evidence: list[Evidence] = field(default_factory=list)
    contradicting_evidence: list[Evidence] = field(default_factory=list)
    score: float = 0.0                          # 0.0 – 1.0, deterministically computed
    confidence: Confidence = "unknown"
    status: str = "candidate"                   # "candidate" | "leading" | "penalized" | "rejected"
    documented_error_codes: list[str] = field(default_factory=list)
    documented_checks: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Root output — ReasoningResult
# ---------------------------------------------------------------------------

@dataclass
class ReasoningResult:
    """
    Step 4 output — passed to Step 5 (Response).

    Contains the full reasoning chain:
    facts → signals → hypotheses → ranking → leading candidate → confidence.

    Step 5 uses this to generate the user-facing response.
    Step 4 never generates that response directly.
    """
    # Traceability
    analysis_id: str = ""
    root_cause_trace: Optional[dict] = None

    # What we know (from Step 1 + Step 2)
    facts: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    # All generated hypotheses (unranked)
    hypotheses: list[ReasonedHypothesis] = field(default_factory=list)

    # Ranked — best first
    ranked_hypotheses: list[ReasonedHypothesis] = field(default_factory=list)

    # The single best candidate (None if INSUFFICIENT_EVIDENCE)
    leading_hypothesis: Optional[ReasonedHypothesis] = None

    # Global evidence lists
    supporting_evidence: list[Evidence] = field(default_factory=list)
    contradicting_evidence: list[Evidence] = field(default_factory=list)

    # What we cannot determine from available data
    unknowns: list[str] = field(default_factory=list)

    # Overall confidence in the leading hypothesis
    confidence: Confidence = "unknown"
    confidence_reasons: list[str] = field(default_factory=list)

    # Overall reasoning status
    reasoning_status: ReasoningStatus = "INSUFFICIENT_EVIDENCE"

    # Validation and warnings
    warnings: list[str] = field(default_factory=list)

    correction_proposals: list[ManualCorrectionProposal] = field(default_factory=list)
    correction_gaps: list[str] = field(default_factory=list)

    @property
    def ready_for_step5(self) -> bool:
        """Step 5 can always proceed — even with INSUFFICIENT_EVIDENCE."""
        return bool(self.analysis_id)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
