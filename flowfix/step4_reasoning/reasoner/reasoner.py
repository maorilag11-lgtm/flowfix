"""
FlowFix — Step 4 Reasoning — Reasoner

Orchestrates the full Step 4 reasoning pipeline.

Pipeline:
  1. Extract facts and signals from Step 1 + Step 2 inputs.
  2. Build hypotheses from Step 2 structural analysis + Step 3 KB matches.
  3. Score each hypothesis deterministically.
  4. Detect contradictions.
  5. Rank hypotheses by score (desc), tie-break by hypothesis_id.
  6. Select leading hypothesis (or declare INSUFFICIENT_EVIDENCE).
  7. Compute overall confidence and reasoning_status.
  8. Return ReasoningResult.

Rules:
  - No LLM involved in scoring or ranking.
  - No invention: only use data present in the inputs.
  - No solution generation.
  - No KB modification.
  - Secrets remain redacted.
  - Deterministic: same inputs → same output.
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step2_analysis import AnalysisResult
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import (
    ReasoningResult,
    ReasonedHypothesis,
    Evidence,
    Confidence,
    ReasoningStatus,
)
from flowfix.step4_reasoning.reasoner.hypothesis_builder import (
    from_step2_hypotheses,
    from_kb_match,
)
from flowfix.step4_reasoning.reasoner.scorer import score_hypothesis


# Thresholds for reasoning status
LEADING_MIN_SCORE   = 0.30   # minimum score to declare a leading hypothesis
STRONG_SCORE        = 0.55   # score above which confidence is "high"
COMPETING_GAP       = 0.10   # if top-2 scores differ by less than this → MULTIPLE_CANDIDATES


def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


def _safe_str(v: Optional[str]) -> Optional[str]:
    if not v or _is_redacted(v):
        return None
    return v.strip()


# ---------------------------------------------------------------------------
# Facts extraction
# ---------------------------------------------------------------------------

def _extract_facts(problem: NormalizedProblem, analysis: WorkflowAnalysis) -> list[str]:
    facts = []
    for f in analysis.observed_facts:
        text = f.fact
        if text and not _is_redacted(text):
            facts.append(text)
    return facts


# ---------------------------------------------------------------------------
# Signals extraction
# ---------------------------------------------------------------------------

def _extract_signals(problem: NormalizedProblem, analysis: WorkflowAnalysis) -> list[str]:
    """
    Preserve source, confidence and signal text for Step 5 traceability.
    Format: "[{confidence}|{source}] {signal}"
    Redacted values are excluded.
    """
    signals = []
    for s in analysis.diagnostic_signals:
        if s.signal and not _is_redacted(s.signal):
            signals.append(f"[{s.confidence}|{s.source}] {s.signal}")
    return signals


# ---------------------------------------------------------------------------
# Global evidence
# ---------------------------------------------------------------------------

def _collect_global_evidence(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
) -> tuple[list[Evidence], list[Evidence]]:
    supporting: list[Evidence] = []
    contradicting: list[Evidence] = []

    # Failure location
    fl = analysis.failure_location
    if fl and fl.module_id:
        supporting.append(Evidence(
            source="workflow_analysis",
            evidence_type="structural",
            description=f"Failing module identified: {fl.module_id} "
                        f"('{fl.module_name}') with {fl.confidence} confidence.",
            reference=fl.module_id,
        ))

    # Error codes
    for code in problem.errors.http_status_codes:
        supporting.append(Evidence(
            source="error_text",
            evidence_type="error_signal",
            description=f"HTTP {code} observed in error message.",
            reference=str(code),
        ))

    if problem.execution_context.http.status:
        code = problem.execution_context.http.status
        if code not in problem.errors.http_status_codes:
            supporting.append(Evidence(
                source="execution_context",
                evidence_type="error_signal",
                description=f"HTTP {code} present in execution context.",
                reference=str(code),
            ))

    # KB strong matches
    for m in retrieval.strong_matches[:3]:
        supporting.append(Evidence(
            source="kb_entry",
            evidence_type="kb_match",
            description=f"KB entry '{m.entry_id}' matches strongly (score={m.score:.3f}): {m.title}",
            reference=m.entry_id,
        ))

    return supporting, contradicting


# ---------------------------------------------------------------------------
# Unknowns
# ---------------------------------------------------------------------------

def _collect_unknowns(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
) -> list[str]:
    """
    Collect things we genuinely do NOT know.

    Rule: absence of data is UNKNOWN — it is never NEGATIVE evidence.
    We do not infer "X is incorrect" from "X is absent".
    Each unknown is phrased as an information gap, not a conclusion.
    """
    unknowns = []

    # Structural unknowns
    if not problem.blueprint.provided:
        unknowns.append(
            "[UNKNOWN] Workflow blueprint not provided — module sequence and "
            "connections cannot be analysed."
        )

    # Error signal unknowns
    if not problem.errors.exact_error_messages and not problem.errors.http_status_codes:
        unknowns.append(
            "[UNKNOWN] No error code or exact error message available — "
            "specific root cause cannot be narrowed down from error signals alone."
        )

    # Failure location unknowns
    if analysis.failure_location is None:
        unknowns.append(
            "[UNKNOWN] Failing module not identified — "
            "problem location within the workflow is unknown."
        )
    elif analysis.failure_location.confidence in ("low", "unknown"):
        unknowns.append(
            "[UNCERTAIN] Failing module identification has low confidence — "
            "additional context may change the diagnosis."
        )

    # Execution context unknowns
    ctx = problem.execution_context
    if ctx.input_data is None:
        unknowns.append(
            "[UNKNOWN] Module input data not provided — "
            "cannot verify field mapping or data structure."
        )
    if ctx.http.response_body is None and analysis.workflow.has_http:
        unknowns.append(
            "[UNKNOWN] HTTP response body not provided — "
            "specific API rejection reason is unknown."
        )

    # Propagate explicit gaps from Step 2 (excluding already-covered ones)
    already_covered = {
        "exact_error_message", "blueprint", "blueprint_modules",
        "failing_module_id", "execution_context",
    }
    for gap in analysis.missing_information:
        if gap not in already_covered:
            unknowns.append(f"[UNKNOWN] Missing information reported by Step 2: {gap}")

    return list(dict.fromkeys(unknowns))


# ---------------------------------------------------------------------------
# Ranking and status
# ---------------------------------------------------------------------------

def _rank_hypotheses(hypotheses: list[ReasonedHypothesis]) -> list[ReasonedHypothesis]:
    """Sort by score desc, then hypothesis_id asc for determinism."""
    return sorted(hypotheses, key=lambda h: (-h.score, h.hypothesis_id))


def _compute_status(
    ranked: list[ReasonedHypothesis],
) -> tuple[Optional[ReasonedHypothesis], ReasoningStatus, Confidence, list[str]]:
    """
    Determine reasoning_status, leading_hypothesis, overall confidence, and reasons.

    Invariants enforced (v1.1):
    - leading_hypothesis is None   ↔   status in (INSUFFICIENT_EVIDENCE,)
      when score < LEADING_MIN_SCORE
    - status == CONTRADICTED       → leading_hypothesis is set (best candidate
      even if contradicted) and confidence is capped
    - status == MULTIPLE_CANDIDATES → leading is the highest-scoring candidate
    - confidence is derived from the hypothesis's own _derive_confidence()
      (which already accounts for contradictions), not from score alone
    """
    if not ranked:
        return None, "INSUFFICIENT_EVIDENCE", "unknown", [
            "No hypotheses generated from available signals."
        ]

    top = ranked[0]

    # Hard floor: below LEADING_MIN_SCORE, we cannot name a leading hypothesis
    if top.score < LEADING_MIN_SCORE:
        return None, "INSUFFICIENT_EVIDENCE", "unknown", [
            f"Best hypothesis score {top.score:.3f} is below the minimum "
            f"threshold {LEADING_MIN_SCORE} — no sufficiently supported candidate."
        ]

    # CONTRADICTED: top candidate has active contradictions AND score < STRONG_SCORE
    # (high-score contradicted hypotheses become MULTIPLE_CANDIDATES or DIAGNOSIS_CANDIDATE
    #  with reduced confidence, not CONTRADICTED — they are still the best we have)
    if top.contradicting_evidence and top.score < STRONG_SCORE:
        top.status = "penalized"
        return top, "CONTRADICTED", top.confidence, [
            "Leading hypothesis has contradicting evidence and score below strong threshold.",
            f"Contradictions: {len(top.contradicting_evidence)}.",
            "Consider this hypothesis with caution.",
        ]

    # MULTIPLE_CANDIDATES: top-2 scores are close
    if len(ranked) >= 2:
        second = ranked[1]
        if second.score >= LEADING_MIN_SCORE and (top.score - second.score) < COMPETING_GAP:
            top.status = "leading"
            return top, "MULTIPLE_CANDIDATES", top.confidence, [
                f"Top hypothesis score {top.score:.3f} vs second {second.score:.3f} "
                f"— gap ({top.score - second.score:.3f}) < threshold {COMPETING_GAP}.",
                "Multiple hypotheses are plausible; additional context is needed.",
            ]

    top.status = "leading"

    if top.score >= STRONG_SCORE:
        status: ReasoningStatus = "DIAGNOSIS_CANDIDATE"
        reasons = [
            f"Leading hypothesis score {top.score:.3f} ≥ {STRONG_SCORE} (strong threshold).",
            f"Confidence: {top.confidence}.",
            f"Supporting signals: {len(top.supporting_signals)}.",
        ]
    else:
        status = "WEAK_EVIDENCE"
        reasons = [
            f"Leading hypothesis score {top.score:.3f} is above minimum threshold "
            f"but below strong threshold {STRONG_SCORE}.",
            "Additional context may strengthen or contradict this candidate.",
        ]

    return top, status, top.confidence, reasons


# ---------------------------------------------------------------------------
# Main reasoning function
# ---------------------------------------------------------------------------

def reason(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
) -> ReasoningResult:
    """
    Run full Step 4 reasoning.

    Parameters
    ----------
    problem   : NormalizedProblem — Step 1 output
    analysis  : WorkflowAnalysis  — Step 2 output
    retrieval : RetrievalResult   — Step 3 output

    Returns
    -------
    ReasoningResult — passed to Step 5.
    Never raises; errors are captured in warnings.
    No LLM, no invention, no KB modification.
    """
    result = ReasoningResult(analysis_id=problem.analysis_id)

    # 1. Facts and signals
    result.facts = _extract_facts(problem, analysis)
    result.signals = _extract_signals(problem, analysis)

    # 2. Build hypotheses
    all_hypotheses: list[ReasonedHypothesis] = []

    # 2a. From Step 2 structural analysis
    all_hypotheses.extend(from_step2_hypotheses(analysis))

    # 2b. From Step 3 KB matches — build one or more hypotheses per match
    for seq, match in enumerate(retrieval.matches[:5]):  # limit to top 5 KB matches
        kb_hyps = from_kb_match(match, seq + 1)
        all_hypotheses.extend(kb_hyps)

    # 3. Score each hypothesis
    for hyp in all_hypotheses:
        # Find KB match score for carry-over
        kb_score = 0.0
        for ref in hyp.supporting_kb_entries:
            for m in retrieval.matches:
                if m.entry_id == ref:
                    kb_score = m.score
                    break

        hyp.score = score_hypothesis(hyp, problem, analysis, kb_score)

    # 4. Deduplicate very similar hypotheses (same statement, different IDs)
    seen_statements: dict[str, ReasonedHypothesis] = {}
    unique_hypotheses: list[ReasonedHypothesis] = []
    for hyp in all_hypotheses:
        key = hyp.statement.lower().strip()[:100]
        if key not in seen_statements:
            seen_statements[key] = hyp
            unique_hypotheses.append(hyp)
        else:
            # Keep the higher-scoring one
            existing = seen_statements[key]
            if hyp.score > existing.score:
                unique_hypotheses.remove(existing)
                seen_statements[key] = hyp
                unique_hypotheses.append(hyp)

    result.hypotheses = unique_hypotheses

    # 5. Rank
    result.ranked_hypotheses = _rank_hypotheses(unique_hypotheses)

    # 6. Determine leading hypothesis, status, confidence
    leading, status, conf, conf_reasons = _compute_status(result.ranked_hypotheses)
    result.leading_hypothesis = leading
    result.reasoning_status = status
    result.confidence = conf
    result.confidence_reasons = conf_reasons

    if status == "MULTIPLE_CANDIDATES":
        for hyp in result.ranked_hypotheses:
            if hyp.confidence == "high":
                hyp.confidence = "medium"
        result.confidence = leading.confidence if leading else "unknown"
        result.confidence_reasons.append("Competing causes remain unconfirmed; score is not a calibrated probability.")

    # 7. Global evidence
    result.supporting_evidence, result.contradicting_evidence = _collect_global_evidence(
        problem, analysis, retrieval
    )
    # Also aggregate from leading hypothesis
    if leading:
        for ev in leading.contradicting_evidence:
            if ev not in result.contradicting_evidence:
                result.contradicting_evidence.append(ev)

    import hashlib
    evidence = result.supporting_evidence + result.contradicting_evidence
    for hyp in result.hypotheses:
        evidence += hyp.supporting_evidence + hyp.contradicting_evidence
    for ev in evidence:
        if ev.provenance_kind == "unspecified":
            ev.provenance_kind = ("knowledge" if ev.source == "kb_entry" else
                "declaration" if ev.evidence_type == "user_reported" else
                "hypothesis" if ev.source == "workflow_analysis" else "observation")
        ev.evidence_id = hashlib.sha256((ev.source + "|" + (ev.reference or "") + "|" + ev.description).encode()).hexdigest()[:16]

    # 8. Unknowns
    result.unknowns = _collect_unknowns(problem, analysis)

    # 9. Warnings (inherited from prior steps)
    result.warnings.extend(analysis.warnings or [])
    result.warnings.extend(retrieval.validation.warnings or [])

    from .json_correction import add_json_correction
    add_json_correction(result, problem, analysis, retrieval)
    if problem.execution_context.root_cause_context is not None:
        from .root_cause import evaluate
        result.root_cause_trace = evaluate(problem, analysis)
    return result
