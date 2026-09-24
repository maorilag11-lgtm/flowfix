"""
FlowFix — Step 3 Retrieval — Models

Output contract for Step 3, consumed by Step 4 (Reasoning).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from flowfix.step3_retrieval.retriever.retriever import KBMatch, RetrievalStats
from flowfix.step3_retrieval.retriever.scorer import SignalBag


@dataclass
class RetrievalValidation:
    valid: bool
    reason: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """
    Output of Step 3 — passed to Step 4 (Reasoning).

    Attributes
    ----------
    analysis_id : str
        Inherited from Step 1 for end-to-end traceability.
    matches : list[KBMatch]
        KB entries that scored above the weak threshold, sorted by score desc.
    stats : RetrievalStats
        Aggregated retrieval statistics (counts, not the entries themselves).
    signals : SignalBag
        The signal bag used for scoring — allows Step 4 to understand
        what signals were extracted and why entries were matched.
    validation : RetrievalValidation
    """
    analysis_id: str = ""
    matches: list[KBMatch] = field(default_factory=list)
    stats: RetrievalStats = field(default_factory=RetrievalStats)
    signals: Optional[SignalBag] = None
    validation: RetrievalValidation = field(
        default_factory=lambda: RetrievalValidation(valid=True, reason="")
    )

    integrity_status: str = "OK"

    @property
    def ready_for_step4(self) -> bool:
        return self.validation.valid

    @property
    def strong_matches(self) -> list[KBMatch]:
        return [m for m in self.matches if m.match_strength == "strong"]

    @property
    def candidates(self) -> list[KBMatch]:
        return [m for m in self.matches if m.match_strength == "candidate"]

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
