"""
FlowFix — Step 6 Clarification — Models

Output contract for Step 6.

Step 6 decides:
  - Whether clarification is needed (based on ResponseResult)
  - What to ask (one clear, prioritised question)
  - What information it targets (for traceability)
  - Whether the pipeline should be re-run after the answer

Design principles:
  - Step 6 never generates a diagnosis.
  - Step 6 never scores hypotheses.
  - Step 6 never accesses the KB.
  - Questions are derived from missing_information in ResponseResult.
  - At most ONE question per cycle (avoid overwhelming the user).
  - Deterministic: same ResponseResult → same ClarificationResult.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Question type — what kind of information is targeted
# ---------------------------------------------------------------------------

QUESTION_TYPES = {
    "blueprint":            "Request for the Make.com blueprint JSON",
    "error_message":        "Request for the exact error message",
    "failing_module":       "Request to identify the failing module",
    "http_response_body":   "Request for the HTTP response body",
    "execution_context":    "Request for additional execution context",
    "input_data":           "Request for module input data",
    "none_needed":          "No clarification needed",
}


# ---------------------------------------------------------------------------
# ClarificationQuestion — the question to ask
# ---------------------------------------------------------------------------

@dataclass
class ClarificationQuestion:
    """
    A single clarification question for the user.

    Priority: highest-value gap to fill given the current analysis state.
    Only ONE question per Step 6 invocation.
    """
    question_type: str            # one of QUESTION_TYPES keys
    question_text: str            # exact text to show the user
    why_needed: str               # one sentence explaining why this helps
    targets_gap: str              # which missing_information item this resolves
    expected_format: str = ""     # hint to the user ("paste JSON", "describe in plain text", etc.)
    hypothesis_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ClarificationResult — Step 6 output
# ---------------------------------------------------------------------------

@dataclass
class ClarificationResult:
    """
    Step 6 output — consumed by the orchestrator.

    Attributes
    ----------
    analysis_id :       Propagated for traceability.
    needs_clarification : True when a question was generated.
    question :          The question to ask (None when no clarification needed).
    max_questions_reached : True when the pipeline has asked too many questions
                            without convergence — signals the orchestrator to
                            escalate to a generic "provide more details" response
                            rather than looping indefinitely.
    re_run_after_answer : Whether the pipeline should re-run when the user answers.
    pass_through :      Signals that the ResponseResult from Step 5 is sufficient
                        and should be delivered as-is.
    warnings :          Propagated from prior steps.
    """
    analysis_id: str = ""
    needs_clarification: bool = False
    question: Optional[ClarificationQuestion] = None
    max_questions_reached: bool = False
    re_run_after_answer: bool = True
    pass_through: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
