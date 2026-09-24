"""
FlowFix — Step 4 Reasoning — Hypothesis Builder

Constructs ReasonedHypothesis objects from:
  - Step 2 WorkflowAnalysis (structural hypotheses)
  - Step 3 RetrievalResult (KB-grounded hypotheses)

Rules:
  - Never invent a hypothesis not grounded in observed signals.
  - KB hypotheses are only created from strong/candidate matches.
  - Step 2 hypotheses are carried forward with their original confidence.
  - No solution generation, no auto-fix, no KB modification.
"""

from __future__ import annotations
import re
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step3_retrieval.retriever.retriever import KBMatch
from flowfix.step4_reasoning.models_internal.models import (
    ReasonedHypothesis,
    Evidence,
    Confidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conf_from_str(s: str) -> Confidence:
    mapping = {"high": "high", "medium": "medium", "low": "low"}
    return mapping.get((s or "").lower(), "unknown")  # type: ignore


def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


# ---------------------------------------------------------------------------
# Step 2 hypotheses → ReasonedHypothesis
# ---------------------------------------------------------------------------

def from_step2_hypotheses(analysis: WorkflowAnalysis) -> list[ReasonedHypothesis]:
    """
    Lift Step 2 Hypothesis objects into ReasonedHypothesis.
    These are structural hypotheses — they don't have KB backing yet.
    """
    result = []
    for i, h in enumerate(analysis.hypotheses):
        hyp = ReasonedHypothesis(
            hypothesis_id=f"H_S2_{i+1}",
            statement=h.hypothesis,
            source="step2_analysis",
            supporting_signals=[h.basis] if h.basis else [],
            confidence=_conf_from_str(h.confidence),
        )
        # Add evidence from failure location if available
        fl = analysis.failure_location
        if fl and fl.module_id:
            hyp.supporting_evidence.append(Evidence(
                source="workflow_analysis",
                evidence_type="structural",
                description=f"Failure location identified: module {fl.module_id} "
                            f"(confidence: {fl.confidence})",
                reference=fl.module_id,
            ))
        result.append(hyp)
    return result


# ---------------------------------------------------------------------------
# KB match → ReasonedHypothesis
# ---------------------------------------------------------------------------

def from_kb_match(match: KBMatch, seq: int) -> list[ReasonedHypothesis]:
    """
    Build one ReasonedHypothesis per likely_cause from a KB match.
    Each likely_cause is a separate hypothesis candidate.

    Returns a list because one KB entry may suggest several root causes.
    """
    entry = match.entry
    if not entry:
        return []

    results = []
    likely_causes = list(entry.likely_causes or [])

    if not likely_causes:
        # Create a single hypothesis from the entry problem description
        hyp = _single_hyp_from_entry(match, seq, 0, entry.problem or entry.title)
        results.append(hyp)
        return results

    for j, cause_obj in enumerate(likely_causes):
        if isinstance(cause_obj, dict):
            cause_text = cause_obj.get("cause", "")
            cause_conf = float(cause_obj.get("confidence", 0.5))
        elif isinstance(cause_obj, str):
            cause_text = cause_obj
            cause_conf = 0.5
        else:
            continue

        if not cause_text:
            continue

        hyp = _single_hyp_from_entry(match, seq, j, cause_text)

        # Adjust confidence from KB entry's cause confidence
        if cause_conf >= 0.85:
            hyp.confidence = "high"
        elif cause_conf >= 0.70:
            hyp.confidence = "medium"
        else:
            hyp.confidence = "low"

        results.append(hyp)

    return results


def _single_hyp_from_entry(match: KBMatch, seq: int, j: int, statement: str) -> ReasonedHypothesis:
    entry = match.entry
    hyp = ReasonedHypothesis(
        hypothesis_id=f"H_KB_{seq}_{j+1}",
        statement=statement,
        source=f"kb_entry:{match.entry_id}",
        supporting_kb_entries=[match.entry_id],
        supporting_signals=list(dict.fromkeys(match.match_reasons)),
        documented_error_codes=list(entry.error_codes),
        documented_checks=[str(s) for s in entry.diagnosis_steps],
    )
    # Add KB match as supporting evidence
    hyp.supporting_evidence.append(Evidence(
        source="kb_entry",
        evidence_type="kb_match",
        description=f"KB entry '{match.entry_id}' matched with score {match.score:.3f}: {match.title}",
        reference=match.entry_id,
    ))
    # Add diagnostic signals from the entry
    if entry:
        for sig in list(entry.diagnostic_signals or [])[:3]:
            hyp.supporting_evidence.append(Evidence(source="kb_entry", evidence_type="documented_signal",
                description=str(sig), reference=match.entry_id, provenance_kind="knowledge"))
    return hyp
