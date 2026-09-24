"""
FlowFix — Step 8 Orchestrator — Models

Step 8 is the pipeline orchestrator. It makes the final routing decision
after receiving all prior step outputs.

Routing decisions:
  DELIVER            — Response is sufficient. Deliver ResponseResult to the user.
  ASK_CLARIFICATION  — More information needed. Present the clarification question.
  ESCALATE           — Max clarification cycles reached or unresolvable. Escalate.
  RERUN              — User answered a clarification question. Re-run from Step 1.
  RECORD_FEEDBACK    — Feedback received and recorded. Acknowledge to the user.
  DONE               — Terminal state. No further action needed.

Design principles:
  - Step 8 reads all prior step outputs but modifies none of them.
  - Step 8 does not access the KB directly.
  - Step 8 does not score, rank, or reason.
  - Step 8 does not generate user-facing text (that is Step 5's job).
  - Deterministic: same inputs → same PipelineDecision.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


ALLOWED_ACTIONS = frozenset({
    "DELIVER",
    "ASK_CLARIFICATION",
    "ESCALATE",
    "RERUN",
    "RECORD_FEEDBACK",
    "DONE",
})


@dataclass
class PipelineDecision:
    """
    The routing decision produced by Step 8.

    Fields
    ------
    action : str
        One of ALLOWED_ACTIONS. What the orchestrator should do next.
    analysis_id : str
        Propagated for traceability.
    reason : str
        Human-readable explanation of why this action was chosen.
    next_cycle : int
        If action == RERUN, the cycle number for the next clarification round.
        Zero otherwise.
    clarification_question_type : Optional[str]
        If action == ASK_CLARIFICATION, the question type from Step 6.
    escalation_reason : Optional[str]
        If action == ESCALATE, why escalation was triggered.
    feedback_validation_state : Optional[str]
        Propagated from Step 7 when feedback was received.
    warnings : list[str]
        Propagated from prior steps.
    """
    action: str = "DONE"
    analysis_id: str = ""
    reason: str = ""
    next_cycle: int = 0
    clarification_question_type: Optional[str] = None
    escalation_reason: Optional[str] = None
    feedback_validation_state: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"Invalid action: {self.action!r}. Allowed: {sorted(ALLOWED_ACTIONS)}"
            )

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
