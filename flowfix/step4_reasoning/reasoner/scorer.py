"""
FlowFix — Step 4 Reasoning — Hypothesis Scorer  v1.1

Deterministic, explicable scoring of ReasonedHypothesis objects.

Scoring philosophy:
  - Scores derive from observable signals, never from opaque heuristics.
  - Every point contribution is documented in reasons[].
  - No LLM involved.
  - Contradictions reduce the score with graduated severity.
  - Context always beats generic KB knowledge.
  - Token overlap is NEVER used as sole evidence — it is secondary to
    direct error-code and structural evidence.

Score scale: 0.0 – 1.0 (clamped, rounded to 6 decimals for determinism).

Weight table (v1.1):
  Explicit failure location (high)      : +0.25
  Explicit failure location (medium)    : +0.15
  Exact structured documented error code : +0.20   (source beats text match)
  HTTP status in supporting signals     : +0.10
  Structural diagnostic-signal match    : +0.08   (per signal, max 2 = 0.16)
                                                   — requires SPECIFIC match
  KB match score carry-over             : +0.12 max
  Structural evidence present           : +0.05
  Strong contradiction penalty          : -0.25
  Moderate contradiction penalty        : -0.12
  Weak contradiction penalty            : -0.05
  Missing-information penalty           : -0.04 per gap (max 3 = -0.12)

Priority invariant:
  structural_evidence > direct_error_evidence > failure_location >
  contextual_signal > kb_support > generic_text_similarity
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step4_reasoning.models_internal.models import (
    ReasonedHypothesis,
    Evidence,
    Confidence,
)


# ---------------------------------------------------------------------------
# Weight constants
# ---------------------------------------------------------------------------

W_FAILURE_LOCATION_HIGH   = 0.25
W_FAILURE_LOCATION_MEDIUM = 0.15
W_ERROR_CODE_SOURCE       = 0.20   # structured KB error_codes matches observed code
W_HTTP_STATUS_SIGNAL      = 0.10   # http status in supporting_signals
W_SIGNAL_MATCH            = 0.08   # per specific diagnostic signal hit (max 2)
W_KB_CARRY_MAX            = 0.12
W_STRUCTURAL_EVIDENCE     = 0.05

W_PENALTY_STRONG          = -0.25
W_PENALTY_MODERATE        = -0.12
W_PENALTY_WEAK            = -0.05
W_MISSING_INFO_PENALTY    = -0.04  # per gap, max 3


# ---------------------------------------------------------------------------
# Contradiction model — graduated severity
# ---------------------------------------------------------------------------

@dataclass
class ContradictionResult:
    evidence: Evidence
    severity: str   # "strong" | "moderate" | "weak"

    def penalty(self) -> float:
        return {
            "strong": W_PENALTY_STRONG,
            "moderate": W_PENALTY_MODERATE,
            "weak": W_PENALTY_WEAK,
        }[self.severity]


def _detect_contradictions(
    hyp: ReasonedHypothesis,
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
) -> list[ContradictionResult]:
    """
    Check whether the workflow context contradicts this hypothesis.

    Rules (v1.1):
    - 422 without any 401/403 REDUCES plausibility of "authentication failure"
      hypotheses — but does NOT prove absence of auth issues (moderate penalty).
    - actual_behavior explicitly reporting success contradicts a failure
      hypothesis for the same module (strong penalty, only if very specific).
    - Hypotheses are never fully invalidated by a single contradiction;
      scoring and the leading-hypothesis logic handle rejection.
    - Absence of data is UNKNOWN, not NEGATIVE evidence.
    """
    results: list[ContradictionResult] = []

    hyp_text = hyp.statement.lower()
    ctx = problem.execution_context
    all_codes = set(problem.errors.http_status_codes)
    if ctx.http.status:
        all_codes.add(ctx.http.status)

    # --- Contradiction 1: auth hypothesis vs pure 422 context ---
    # Only applies when the hypothesis explicitly names authentication failure
    # AND there is no 401/403 anywhere in the signal set.
    AUTH_KEYWORDS = {"authentication failure", "invalid credentials",
                     "token expired", "oauth2 access token"}
    if any(kw in hyp_text for kw in AUTH_KEYWORDS):
        if 422 in all_codes and not (401 in all_codes or 403 in all_codes):
            results.append(ContradictionResult(
                evidence=Evidence(
                    source="execution_context",
                    evidence_type="contradiction",
                    description=(
                        "Hypothesis explicitly names authentication failure, but the "
                        "observed HTTP status is 422 (validation error) with no 401/403 "
                        "present — reduces auth hypothesis plausibility."
                    ),
                    reference="http_status:422",
                ),
                severity="moderate",  # NOT strong — 422 can coexist with auth issues
            ))

    # --- Contradiction 2: actual_behavior reports success for same module ---
    actual = (ctx.actual_behavior or "").lower()
    fl = analysis.failure_location
    FAILURE_KEYWORDS = {"authentication", "token expired", "credentials invalid"}
    if (actual and any(kw in hyp_text for kw in FAILURE_KEYWORDS)
            and "success" in actual
            and fl and fl.module_id
            and (fl.module_id in hyp_text or (fl.module_name or "").lower() in hyp_text)):
        results.append(ContradictionResult(
            evidence=Evidence(
                source="execution_context",
                evidence_type="contradiction",
                description=(
                    f"Hypothesis implies failure for module {fl.module_id}, but "
                    "actual_behavior reports success for the same module."
                ),
                reference=f"module:{fl.module_id}",
            ),
            severity="strong",
        ))

    return results


# ---------------------------------------------------------------------------
# Diagnostic signal specific match — avoids token-overlap false positives
# ---------------------------------------------------------------------------

# Specific signal topics paired with hypothesis keywords.
# Only these explicit associations are allowed to contribute W_SIGNAL_MATCH.
# Generic token overlap is NOT used.
_SIGNAL_HYPOTHESIS_PAIRS = [
    # (signal_keyword_set, hypothesis_keyword_set) — all lowercase
    ({"http 4", "client-side", "rejected the request"},   {"field", "mapping", "required", "validation", "format"}),
    ({"http 4", "client-side", "rejected the request"},   {"authentication", "authorization", "token", "credential"}),
    ({"rate limit", "429"},                               {"rate limit", "too many requests", "quota"}),
    ({"http 5", "server-side", "external service"},       {"external service", "server error", "unavailable"}),
    ({"response body", "error details"},                  {"field", "required", "validation"}),
    ({"bundle count", "iterator"},                        {"iterator", "array", "bundle", "aggregat"}),
    ({"no error handler"},                                {"error handler", "stop", "rollback"}),
    ({"webhook"},                                         {"webhook", "payload", "trigger"}),
    ({"filter"},                                          {"filter", "condition", "route"}),
]


def _specific_signal_match(hyp_text: str, sig_text: str) -> bool:
    """
    Returns True only when the signal and hypothesis share a SPECIFIC topic
    from the known pairing table — not generic token overlap.
    """
    for sig_keywords, hyp_keywords in _SIGNAL_HYPOTHESIS_PAIRS:
        if (any(k in sig_text for k in sig_keywords)
                and any(k in hyp_text for k in hyp_keywords)):
            return True
    return False


# ---------------------------------------------------------------------------
# Confidence with contradiction awareness
# ---------------------------------------------------------------------------

def _derive_confidence(
    score: float,
    contradictions: list[ContradictionResult],
) -> Confidence:
    """
    Confidence considers score AND active contradictions.
    A high score with a strong contradiction cannot be "high" confidence.
    """
    strong = sum(1 for c in contradictions if c.severity == "strong")
    moderate = sum(1 for c in contradictions if c.severity == "moderate")

    if strong >= 1:
        # Active strong contradiction: cap at low
        if score >= 0.55:
            return "medium"  # score is high but contradicted
        return "low"

    if moderate >= 2:
        # Two moderate contradictions: cap at medium
        if score >= 0.55:
            return "medium"
        return "low"

    # Normal derivation
    if score >= 0.55:
        return "high"
    if score >= 0.35:
        return "medium"
    if score >= 0.10:
        return "low"
    return "unknown"


# ---------------------------------------------------------------------------
# Core scorer
# ---------------------------------------------------------------------------

def score_hypothesis(
    hyp: ReasonedHypothesis,
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    kb_match_score: float = 0.0,
) -> float:
    """
    Compute a deterministic score for one hypothesis.
    Returns a float 0.0 – 1.0, rounded to 6 decimals.

    Side effects:
      - Appends contradictions to hyp.contradicting_evidence.
      - Sets hyp.confidence.
    """
    score = 0.0
    reasons: list[str] = []

    # All HTTP codes observed (error text + execution context)
    all_codes = {str(c) for c in problem.errors.http_status_codes}
    if problem.execution_context.http.status:
        all_codes.add(str(problem.execution_context.http.status))

    hyp_text = hyp.statement.lower()


    # --- 1. Failure location (applies to step2_analysis hypotheses only) ---
    fl = analysis.failure_location
    if fl and hyp.source == "step2_analysis":
        if fl.confidence == "high":
            score += W_FAILURE_LOCATION_HIGH
            reasons.append(f"failure_location(high):module={fl.module_id}")
        elif fl.confidence == "medium":
            score += W_FAILURE_LOCATION_MEDIUM
            reasons.append(f"failure_location(medium):module={fl.module_id}")

    # An opaque document ID never contributes evidence. One HTTP observation
    # family contributes once, regardless of repeated text or context copies.
    for code in sorted(all_codes.intersection(hyp.documented_error_codes)):
        score += W_ERROR_CODE_SOURCE
        reasons.append(f"documented_error_code:{code}")
        break

    # --- 4. Specific diagnostic signal match (up to 2) ---
    signal_hits = 0
    seen_signal_text = set()
    for sig in analysis.diagnostic_signals:
        normalized = " ".join(sig.signal.lower().split())
        if normalized in seen_signal_text:
            continue
        seen_signal_text.add(normalized)
        if signal_hits >= 2:
            break
        if _specific_signal_match(hyp_text, sig.signal.lower()):
            score += W_SIGNAL_MATCH
            signal_hits += 1
            reasons.append(f"specific_signal_match:'{sig.signal[:50]}'")

    # --- 5. KB carry-over (capped, normalized against typical KB max score 0.62) ---
    if kb_match_score > 0:
        # Normalize: 0.62 → W_KB_CARRY_MAX, proportional below
        carry = round(min(kb_match_score / 0.62 * W_KB_CARRY_MAX, W_KB_CARRY_MAX), 6)
        score += carry
        reasons.append(f"kb_carry:{kb_match_score:.3f}→+{carry:.3f}")

    # --- 6. Structural evidence already attached to the hypothesis ---
    if any(e.evidence_type == "structural" for e in hyp.supporting_evidence):
        score += W_STRUCTURAL_EVIDENCE
        reasons.append("structural_evidence_present")

    # --- 7. Contradiction detection (graduated penalties) ---
    contradiction_results = _detect_contradictions(hyp, problem, analysis)
    for cr in contradiction_results:
        penalty = cr.penalty()
        score += penalty
        reasons.append(
            f"CONTRADICTION({cr.severity}):{cr.evidence.description[:60]}"
        )
        hyp.contradicting_evidence.append(cr.evidence)

    # --- 8. Missing-information penalty ---
    gaps = min(len(hyp.missing_information), 3)
    if gaps:
        score += gaps * W_MISSING_INFO_PENALTY
        reasons.append(f"missing_info_penalty:{gaps}_gap(s)")

    # Clamp and round
    score = max(0.0, min(round(score, 6), 1.0))

    # Set confidence with contradiction awareness
    hyp.confidence = _derive_confidence(score, contradiction_results)

    # Append scoring trace to supporting_signals (excludes CONTRADICTION lines)
    non_contradiction_reasons = [r for r in reasons if not r.startswith("CONTRADICTION")]
    hyp.supporting_signals.extend(non_contradiction_reasons)

    return score
