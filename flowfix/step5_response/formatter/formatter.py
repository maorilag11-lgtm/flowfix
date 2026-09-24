"""
FlowFix — Step 5 Response — Formatter

Transforms a ReasoningResult into a ResponseResult.

Rules:
  - NEVER recalculate scores, confidence, or hypotheses.
  - NEVER upgrade a hypothesis to a confirmed fact.
  - NEVER access the KB directly (no load_kb, no kb_dir, no JSON reads).
  - NEVER make network calls or use a LLM.
  - NEVER reveal redacted secrets.
  - Confidence and status are carried from ReasoningResult unchanged.
  - Actions come from KB diagnosis_steps/solutions already present in
    RetrievalResult.matches[*].entry — no new KB access.
  - Deterministic: same inputs → same output.

The formatter maps reasoning status to a presentation strategy:

  DIAGNOSIS_CANDIDATE   → present leading hypothesis as best candidate
  MULTIPLE_CANDIDATES   → present top-2 with a note that verification is needed
  WEAK_EVIDENCE         → present piste with explicit uncertainty
  CONTRADICTED          → present hypothesis with contradiction note
  INSUFFICIENT_EVIDENCE → no diagnosis; focus on what is missing
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.models import RetrievalResult
from flowfix.step4_reasoning.models_internal.models import (
    ReasoningResult,
    ReasonedHypothesis,
)
from flowfix.step5_response.models_internal.models import (
    ResponseResult,
    ActionItem,
    EvidenceSummary,
    HypothesisSummary,
)


# ---------------------------------------------------------------------------
# Secret guard
# ---------------------------------------------------------------------------

def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


def _safe(v: Optional[str]) -> Optional[str]:
    if not v or _is_redacted(v):
        return None
    from flowfix.step1_intake.redaction.redactor import redact
    return None if redact(v).redactions else v.strip()


# ---------------------------------------------------------------------------
# Summary builders — status-specific
# ---------------------------------------------------------------------------

_STATUS_SUMMARIES = {
    "DIAGNOSIS_CANDIDATE": (
        "FlowFix has identified a likely cause for the observed failure."
    ),
    "MULTIPLE_CANDIDATES": (
        "FlowFix has identified several plausible causes. "
        "Additional context is needed to confirm which one applies."
    ),
    "WEAK_EVIDENCE": (
        "FlowFix has a possible lead, but the available evidence is limited. "
        "More context would help narrow down the cause."
    ),
    "CONTRADICTED": (
        "FlowFix identified a candidate explanation, but it has contradicting "
        "signals. Verify the details before acting."
    ),
    "INSUFFICIENT_EVIDENCE": (
        "FlowFix does not have enough information to identify the root cause. "
        "See the missing information section below."
    ),
}


def _build_summary(reasoning: ReasoningResult) -> str:
    return _STATUS_SUMMARIES.get(reasoning.reasoning_status, "Analysis complete.")


# ---------------------------------------------------------------------------
# Observed facts — from facts list, safe only
# ---------------------------------------------------------------------------

def _build_observed(reasoning: ReasoningResult) -> list[str]:
    observed = []
    for fact in reasoning.facts:
        if fact and not _is_redacted(fact):
            observed.append(fact)
    return observed


# ---------------------------------------------------------------------------
# Evidence for the leading hypothesis
# ---------------------------------------------------------------------------

def _build_evidence(reasoning: ReasoningResult) -> list[EvidenceSummary]:
    items: list[EvidenceSummary] = []

    # Global supporting evidence first
    for ev in reasoning.supporting_evidence:
        desc = _safe(ev.description)
        if not desc:
            continue
        items.append(EvidenceSummary(
            description=desc,
            evidence_type=ev.evidence_type,
            source_label=_source_label(ev.source),
        ))

    # Evidence from the leading hypothesis itself
    lh = reasoning.leading_hypothesis
    if lh:
        for ev in lh.supporting_evidence:
            desc = _safe(ev.description)
            if not desc:
                continue
            # Avoid duplicating what's already in global evidence
            if not any(e.description == desc for e in items):
                items.append(EvidenceSummary(
                    description=desc,
                    evidence_type=ev.evidence_type,
                    source_label=_source_label(ev.source),
                ))

    return items


def _source_label(source: str) -> str:
    """Convert internal source identifiers to human-readable labels."""
    mapping = {
        "workflow_analysis": "Workflow structure",
        "error_text": "Error message",
        "execution_context": "Execution context",
        "kb_entry": "FlowFix knowledge base",
        "user_description": "User description",
        "kb_match": "FlowFix knowledge base",
    }
    # Handle prefixed sources like "kb_entry:http-422-validation-error"
    base = source.split(":")[0]
    return mapping.get(base, source)


# ---------------------------------------------------------------------------
# Recommended actions — from KB diagnosis_steps and solutions
# Derived from RetrievalResult (already retrieved by Step 3 — no new KB access)
# ---------------------------------------------------------------------------

def _build_actions(
    reasoning: ReasoningResult,
    retrieval: RetrievalResult,
) -> list[ActionItem]:
    """
    Build concrete action items from:
    1. KB diagnosis_steps of the top strong/candidate match
    2. KB solutions of the same match (conditionally)

    IMPORTANT: We read from retrieval.matches[*].entry — this data was already
    retrieved by Step 3. Step 5 never calls load_kb() or reads KB files.
    """
    actions: list[ActionItem] = []
    step_num = 1

    # Use the leading hypothesis's KB entry if available
    leading_kb_entry_id: Optional[str] = None
    if reasoning.leading_hypothesis:
        kb_refs = reasoning.leading_hypothesis.supporting_kb_entries
        if kb_refs:
            leading_kb_entry_id = kb_refs[0]

    # Find the matching KB entry in retrieval results
    target_entry = None
    if leading_kb_entry_id:
        for match in retrieval.matches:
            if match.entry_id == leading_kb_entry_id and match.entry:
                target_entry = match.entry
                break

    # Fallback: use the top strong match if no leading hypothesis KB entry
    if not target_entry:
        for match in retrieval.strong_matches[:1]:
            if match.entry:
                target_entry = match.entry
                break

    if target_entry:
        source_label = f"kb_entry:{target_entry.id}"

        # Add diagnosis steps (max 5)
        for step_text in list(target_entry.diagnosis_steps)[:5]:
            safe_text = _safe(str(step_text))
            if safe_text:
                actions.append(ActionItem(
                    step=step_num,
                    description=safe_text,
                    source=source_label,
                ))
                step_num += 1

        # Add solutions (max 3, with confidence filter)
        for sol_obj in list(target_entry.solutions)[:3]:
            if isinstance(sol_obj, dict):
                sol_text = sol_obj.get("solution", "")
                sol_conf = float(sol_obj.get("confidence", 0.0))
                conditions = sol_obj.get("conditions", "")
            elif isinstance(sol_obj, str):
                sol_text = sol_obj
                sol_conf = 0.5
                conditions = ""
            else:
                continue

            safe_sol = _safe(str(sol_text))
            if not safe_sol or sol_conf < 0.70:
                continue

            desc = safe_sol
            safe_cond = _safe(str(conditions)) if conditions else None
            if conditions and safe_cond is None:
                continue
            if safe_cond:
                desc = f"{safe_sol} ({safe_cond})"

            actions.append(ActionItem(
                step=step_num,
                description="Documented option — applicability not established: " + desc,
                source=source_label,
                purpose="documented_solution",
            ))
            step_num += 1

    # If no KB entry available but we have structural signals, add a generic step
    if not actions and reasoning.leading_hypothesis:
        actions.append(ActionItem(
            step=1,
            description=(
                "Review the failing module's input mapping and verify that all "
                "required fields receive valid, non-empty values."
            ),
            source="structural_signal",
        ))

    return actions


# ---------------------------------------------------------------------------
# Missing information — from unknowns
# ---------------------------------------------------------------------------

def _build_missing(reasoning: ReasoningResult) -> list[str]:
    missing = []
    for u in reasoning.unknowns:
        # Strip the [UNKNOWN]/[UNCERTAIN] tags for display
        text = u.replace("[UNKNOWN]", "").replace("[UNCERTAIN]", "").strip()
        if text and not _is_redacted(text):
            missing.append(text)
    return missing


# ---------------------------------------------------------------------------
# Alternative hypotheses
# ---------------------------------------------------------------------------

def _build_alternatives(
    reasoning: ReasoningResult,
) -> list[HypothesisSummary]:
    """
    Build alternative hypothesis summaries.
    Only relevant for MULTIPLE_CANDIDATES and CONTRADICTED.
    Shows the top alternatives after the leading hypothesis.
    """
    if reasoning.reasoning_status not in ("MULTIPLE_CANDIDATES", "CONTRADICTED"):
        return []

    alts: list[HypothesisSummary] = []
    leading_id = (
        reasoning.leading_hypothesis.hypothesis_id
        if reasoning.leading_hypothesis
        else None
    )

    for hyp in reasoning.ranked_hypotheses[1:4]:  # up to 3 alternatives
        if hyp.hypothesis_id == leading_id:
            continue
        if hyp.score <= 0:
            continue

        # Build a distinguishing check from missing information or contradictions
        check_parts = []
        if hyp.missing_information:
            check_parts.append(hyp.missing_information[0])
        if hyp.contradicting_evidence:
            check_parts.append(f"resolve: {hyp.contradicting_evidence[0].description[:60]}")
        distinguishing = check_parts[0] if check_parts else "Provide more execution context."

        alts.append(HypothesisSummary(
            statement=hyp.statement,
            confidence=hyp.confidence,
            distinguishing_check=distinguishing,
        ))

    return alts


# ---------------------------------------------------------------------------
# Diagnosis presentation
# ---------------------------------------------------------------------------

def _confidence_qualifier(reasoning_confidence: str, hyp_confidence: str, status: str) -> str:
    """
    Map overall reasoning confidence + status to a qualifier.

    Uses reasoning_confidence (from ReasoningResult.confidence) as the primary signal,
    since that reflects the full analysis including structural evidence.
    Never presents a hypothesis as a confirmed fact.

    Parameters
    ----------
    reasoning_confidence : overall confidence from ReasoningResult
    hyp_confidence       : confidence of the leading hypothesis (secondary)
    status               : reasoning status
    """
    # Use the HIGHER of the two confidence levels (overall vs hypothesis)
    # Overall confidence reflects more signals than just the hypothesis score
    conf = reasoning_confidence if reasoning_confidence in ("high", "medium") else hyp_confidence

    if status == "DIAGNOSIS_CANDIDATE" and conf == "high":
        return "Most likely cause"
    if status in ("DIAGNOSIS_CANDIDATE", "MULTIPLE_CANDIDATES") and conf in ("high", "medium"):
        return "Probable cause"
    if status == "WEAK_EVIDENCE":
        return "Possible cause (low confidence)"
    if status == "MULTIPLE_CANDIDATES" and conf == "low":
        return "Possible cause (low confidence)"
    if status == "CONTRADICTED":
        return "Candidate cause (contradicted — verify before acting)"
    return "Candidate cause"


# ---------------------------------------------------------------------------
# Diagnostic signals
# ---------------------------------------------------------------------------

def _build_signals(reasoning: ReasoningResult) -> list[str]:
    signals = []
    for sig in reasoning.signals:
        # Signals format: "[confidence|source] text" — strip the tag for display
        if "|" in sig and sig.startswith("["):
            # Extract just the signal text
            close = sig.index("]")
            text = sig[close + 1:].strip()
        else:
            text = sig.strip()
        safe_text = _safe(text)
        if safe_text:
            signals.append(safe_text)
    return signals


# ---------------------------------------------------------------------------
# Main formatter
# ---------------------------------------------------------------------------

def format_response(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    retrieval: RetrievalResult,
    reasoning: ReasoningResult,
) -> ResponseResult:
    """
    Format a ReasoningResult into a ResponseResult.

    Parameters
    ----------
    problem   : NormalizedProblem — Step 1 output (for context only, no re-analysis)
    analysis  : WorkflowAnalysis  — Step 2 output (for context only)
    retrieval : RetrievalResult   — Step 3 output (for KB diagnosis_steps/solutions)
    reasoning : ReasoningResult   — Step 4 output (primary source)

    Returns
    -------
    ResponseResult — ready for rendering or Step 6.

    Never raises — errors are captured as warnings.
    """
    response = ResponseResult(
        analysis_id=reasoning.analysis_id,
        status=reasoning.reasoning_status,
        confidence=reasoning.confidence,
    )

    # Summary
    response.summary = _build_summary(reasoning)

    # Observed facts
    response.observed = _build_observed(reasoning)

    # Diagnosis — only when we have a leading hypothesis
    lh = reasoning.leading_hypothesis
    if lh:
        response.has_leading_hypothesis = True
        response.diagnosis = lh.statement
        response.diagnosis_confidence = lh.confidence
        qualifier = _confidence_qualifier(
            reasoning.confidence, lh.confidence, reasoning.reasoning_status
        )
        # Prepend qualifier to diagnosis for clarity
        response.diagnosis = f"[{qualifier}] {lh.statement}"
        response.diagnosis_is_candidate = reasoning.reasoning_status in (
            "DIAGNOSIS_CANDIDATE", "MULTIPLE_CANDIDATES"
        )

    # Evidence
    response.evidence = _build_evidence(reasoning)

    # Actions — from KB via retrieval (no direct KB access)
    response.recommended_actions = _build_actions(reasoning, retrieval)

    # Missing information
    response.missing_information = _build_missing(reasoning)

    # Alternatives
    response.alternative_hypotheses = _build_alternatives(reasoning)

    # Signals (for metadata)
    response.diagnostic_signals = _build_signals(reasoning)

    # Warnings (inherited)
    response.warnings = list(reasoning.warnings or [])

    response.candidate_checks = [
        {"hypothesis_id": h.hypothesis_id, "source": h.source,
         "missing_observations": list(h.missing_information),
         "documented_checks": list(h.documented_checks),
         "conclusion_rule": "Compare the requested observation with the candidate; record support, contradiction or uncertainty."}
        for h in reasoning.ranked_hypotheses[:3]
    ]
    from .guidance import build_guidance, render_guidance
    checks, options, documents, omissions = build_guidance(retrieval, reasoning)
    response.diagnostic_checks = checks
    response.documented_solutions = options
    response.documentation = documents
    response.warnings.extend(omissions)
    response.guidance_markdown = render_guidance(checks, options, documents, response.status)
    from copy import deepcopy
    from .corrections import render_corrections
    from flowfix.step4_reasoning.models_internal.corrections import validate_proposals
    proposal_error = validate_proposals(reasoning.correction_proposals, response.analysis_id)
    if reasoning.correction_proposals and not proposal_error:
        from flowfix.step1_intake.intake.field_contracts import observation_digest
        obs = problem.execution_context.json_field_observation
        p = reasoning.correction_proposals[0]
        if reasoning.reasoning_status != 'DIAGNOSIS_CANDIDATE' or not reasoning.leading_hypothesis or p.hypothesis_id != reasoning.leading_hypothesis.hypothesis_id:
            proposal_error = 'The correction is not attached to the current leading diagnostic candidate.'
        elif obs is None or p.observation_digest != observation_digest(problem, obs):
            proposal_error = 'The correction inputs have changed since S4.'
    response.correction_proposals = [] if proposal_error else deepcopy(reasoning.correction_proposals)
    if proposal_error:
        response.warnings.append(proposal_error)
    response.correction_gaps = list(reasoning.correction_gaps)
    response.missing_information.extend(reasoning.correction_gaps)
    response.correction_markdown = render_corrections(response.correction_proposals)
    if response.correction_proposals:
        response.recommended_actions = [ActionItem(i, 'Review the supplied field contract and apply the locally verified single-comma correction manually if it still matches.',
            'execution_context', purpose='manual_correction') for i, p in enumerate(response.correction_proposals, 1)]
    return response
