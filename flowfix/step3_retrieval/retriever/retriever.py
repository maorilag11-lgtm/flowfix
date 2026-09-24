"""
FlowFix — Step 3 Retrieval — Retriever

Orchestrates KB retrieval: loads entries, scores each one, filters and ranks.

Thresholds:
  STRONG_THRESHOLD = 0.35  — strong match (at least error_code level hit)
  WEAK_THRESHOLD   = 0.06  — candidate (at least keyword or structural hit)

Entries below WEAK_THRESHOLD are discarded.

Tie-breaking: entries with equal score are sorted by entry.id (lexicographic)
for full determinism. Two identical inputs always produce identical output.

top_k default: 5 — limits returned results to prevent overwhelming Step 4.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.kb.loader import load_kb, KBEntry
from flowfix.step3_retrieval.retriever.matcher import build_signal_bag
from flowfix.step3_retrieval.retriever.scorer import score_entry, ScoredEntry, SignalBag


# Scoring thresholds — justified by weight table:
#   STRONG: >= error_code level (0.35) — at least one exact structural match
#   WEAK:   >= keyword hit (0.03) but below strong — plausible candidate
STRONG_THRESHOLD: float = 0.35
WEAK_THRESHOLD: float = 0.06

DEFAULT_TOP_K: int = 5


@dataclass
class KBMatch:
    """
    A single KB entry that scored above the weak threshold.
    """
    entry_id: str
    title: str
    score: float
    match_strength: str          # "strong" | "candidate"
    match_reasons: list[str] = field(default_factory=list)
    needs_reverification: bool = False
    verification_status: str = ""
    quality_score: float = 0.0
    confidence: float = 0.0
    # Reference to the full entry for Step 4
    entry: Optional[KBEntry] = field(default=None, repr=False)


@dataclass
class RetrievalStats:
    entries_evaluated: int = 0
    strong_matches: int = 0
    candidates: int = 0
    discarded: int = 0


def retrieve(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[KBMatch], RetrievalStats, SignalBag]:
    """
    Core retrieval function.

    Parameters
    ----------
    problem : NormalizedProblem — Step 1 output
    analysis : WorkflowAnalysis — Step 2 output
    top_k : int — maximum results to return

    Returns
    -------
    matches : list[KBMatch] sorted by score desc, then id asc
    stats : RetrievalStats
    signals : SignalBag used for scoring (for traceability)
    """
    # Build signal bag from Step 1 + Step 2
    signals = build_signal_bag(problem, analysis)

    # Load KB (cached read-only)
    entries = load_kb()

    stats = RetrievalStats(entries_evaluated=len(entries))
    scored: list[ScoredEntry] = []

    for entry in entries:
        se = score_entry(entry, signals)
        if se.score >= WEAK_THRESHOLD:
            scored.append(se)
        else:
            stats.discarded += 1

    # Sort: score desc, then id asc for tie-breaking determinism
    scored.sort(key=lambda s: (-s.score, s.entry.id))

    # Apply top_k
    scored = scored[:top_k]

    matches: list[KBMatch] = []
    for se in scored:
        strength = "strong" if se.score >= STRONG_THRESHOLD else "candidate"
        if strength == "strong":
            stats.strong_matches += 1
        else:
            stats.candidates += 1

        matches.append(KBMatch(
            entry_id=se.entry.id,
            title=se.entry.title,
            score=se.score,
            match_strength=strength,
            match_reasons=se.match_reasons,
            needs_reverification=se.entry.needs_reverification,
            verification_status=se.entry.verification_status,
            quality_score=se.entry.quality_score,
            confidence=se.entry.confidence,
            entry=se.entry,
        ))

    # Entries discarded = those not in scored at all
    stats.discarded = stats.entries_evaluated - len(scored) - (stats.entries_evaluated - stats.entries_evaluated)
    stats.discarded = stats.entries_evaluated - stats.strong_matches - stats.candidates

    return matches, stats, signals
