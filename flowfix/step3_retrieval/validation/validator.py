"""
FlowFix — Step 3 Retrieval — Validation

Validates a RetrievalResult before it is passed to Step 4.
Validation is tolerant: no matches is a valid outcome.
"""

from __future__ import annotations
from flowfix.step3_retrieval.models import RetrievalResult, RetrievalValidation


def validate(result: RetrievalResult) -> RetrievalValidation:
    warnings: list[str] = []

    if not result.analysis_id:
        return RetrievalValidation(
            valid=False,
            reason="analysis_id missing — traceability broken.",
        )

    if result.matches is None:
        return RetrievalValidation(
            valid=False,
            reason="matches list is None — internal error.",
        )

    if result.stats.entries_evaluated == 0:
        warnings.append("KB was empty or could not be loaded.")

    if not result.matches:
        warnings.append("No KB entries matched the problem signals — Step 4 will handle the no-match case.")

    # Warn about needs_reverification entries in results
    rev_entries = [m.entry_id for m in result.matches if m.needs_reverification]
    if rev_entries:
        warnings.append(f"Matched entries with needs_reverification=true: {rev_entries}")

    return RetrievalValidation(
        valid=True,
        reason="Ready for Step 4.",
        warnings=warnings,
    )
