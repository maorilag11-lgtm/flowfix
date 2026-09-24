"""
FlowFix — Step 3 Retrieval — Scorer

Deterministic, explainable scoring of KB entries against problem signals.

Scoring philosophy:
  - Exact matches on structured fields (error_codes, apps, modules) score highest.
  - Keyword/text overlap scores lower.
  - No LLM involved. No opaque scoring.
  - Every point contribution is recorded in match_reasons.
  - Identical inputs always produce identical scores.

Score scale: 0.0 – 1.0 (capped).

Weight table (sum of all max weights = 1.0):
  error_code exact match        : 0.35
  error_message substring match : 0.20
  app exact match               : 0.15
  module exact match            : 0.10
  category match                : 0.06
  layer match                   : 0.04
  surface match                 : 0.03
  diagnostic_signal keyword hit : 0.04
  search_keyword hit            : 0.03
                                  -----
  max total                     : 1.00
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from flowfix.step3_retrieval.kb.loader import KBEntry


# ---------------------------------------------------------------------------
# Signal bag — normalised signals extracted from Step 1 + Step 2
# ---------------------------------------------------------------------------

@dataclass
class SignalBag:
    """
    Flat collection of normalised signals for scoring.
    All string values are lower-case stripped for comparison.
    """
    http_status_codes: list[int] = field(default_factory=list)    # e.g. [422, 429]
    error_codes: list[str] = field(default_factory=list)           # e.g. ["422", "ECONNREFUSED"]
    error_messages: list[str] = field(default_factory=list)        # redacted, lower
    apps: list[str] = field(default_factory=list)                  # e.g. ["gmail", "hubspot"]
    modules: list[str] = field(default_factory=list)               # e.g. ["http", "gmail.sendemail"]
    categories: list[str] = field(default_factory=list)            # e.g. ["http", "validation"]
    layers: list[str] = field(default_factory=list)                # e.g. ["external_api"]
    surfaces: list[str] = field(default_factory=list)              # e.g. ["module"]
    diagnostic_signals: list[str] = field(default_factory=list)    # from Step 2
    user_description: Optional[str] = None                         # lower, redacted


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

W_ERROR_CODE      = 0.35
W_ERROR_MESSAGE   = 0.20
W_APP             = 0.15
W_MODULE          = 0.10
W_CATEGORY        = 0.06
W_LAYER           = 0.04
W_SURFACE         = 0.03
W_DIAG_SIGNAL     = 0.04
W_KEYWORD         = 0.03


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScoredEntry:
    entry: KBEntry
    score: float
    match_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return s.strip().lower()


def _tokens(s: str) -> set[str]:
    """Split a string into lowercase word tokens (min 3 chars)."""
    import re
    return {w for w in re.split(r"\W+", s.lower()) if len(w) >= 3}


def _overlap(a: str, b: str) -> bool:
    """True if any token from a appears in b."""
    tok_a = _tokens(a)
    tok_b = _tokens(b)
    return bool(tok_a & tok_b)


# ---------------------------------------------------------------------------
# Core scoring function
# ---------------------------------------------------------------------------

def score_entry(entry: KBEntry, signals: SignalBag) -> ScoredEntry:
    """
    Compute a deterministic score for one KB entry against the signal bag.
    Returns a ScoredEntry with the score and a list of reasons.
    """
    score = 0.0
    reasons: list[str] = []

    # --- 1. Error code exact match (highest weight) ---
    kb_codes = {_norm(c) for c in entry.error_codes}
    sig_codes = {str(c) for c in signals.http_status_codes} | {_norm(c) for c in signals.error_codes}
    matched_codes = kb_codes & sig_codes
    if matched_codes:
        score += W_ERROR_CODE
        reasons.append(f"error_code exact match: {matched_codes}")

    # --- 2. Error message substring match ---
    if entry.error_messages and signals.error_messages:
        for kb_msg in entry.error_messages:
            kb_msg_norm = _norm(kb_msg)
            for sig_msg in signals.error_messages:
                sig_msg_norm = _norm(sig_msg)
                # Substring in either direction, or significant token overlap
                if (kb_msg_norm in sig_msg_norm or
                        sig_msg_norm in kb_msg_norm or
                        _overlap(kb_msg_norm, sig_msg_norm)):
                    score += W_ERROR_MESSAGE
                    reasons.append(f"error_message match: '{kb_msg[:60]}'")
                    break
            else:
                continue
            break

    # --- 3. App exact match ---
    kb_apps = {_norm(a) for a in (entry.make_context.get("apps") or [])}
    # Supplement from search_keywords that mention app names
    kb_apps_kw = {_norm(kw.split()[0]) for kw in entry.search_keywords if kw}
    sig_apps = {_norm(a) for a in signals.apps}
    matched_apps = kb_apps & sig_apps
    if matched_apps:
        score += W_APP
        reasons.append(f"app match: {matched_apps}")

    # --- 4. Module exact match ---
    kb_modules = {_norm(m) for m in (entry.make_context.get("modules") or [])}
    sig_modules = {_norm(m) for m in signals.modules}
    # Partial: "HTTP" in "http.actionsenddataadvanced"
    module_hit = False
    for kb_mod in kb_modules:
        for sig_mod in sig_modules:
            if kb_mod in sig_mod or sig_mod in kb_mod:
                module_hit = True
                score += W_MODULE
                reasons.append(f"module match: KB='{kb_mod}' / signal='{sig_mod}'")
                break
        if module_hit:
            break

    # --- 5. Category match ---
    sig_cats = {_norm(c) for c in signals.categories}
    if entry.category and _norm(entry.category) in sig_cats:
        score += W_CATEGORY
        reasons.append(f"category match: '{entry.category}'")

    # --- 6. Layer match ---
    sig_layers = {_norm(l) for l in signals.layers}
    if entry.layer and _norm(entry.layer) in sig_layers:
        score += W_LAYER
        reasons.append(f"layer match: '{entry.layer}'")

    # --- 7. Surface match ---
    sig_surfaces = {_norm(s) for s in signals.surfaces}
    if entry.surface and _norm(entry.surface) in sig_surfaces:
        score += W_SURFACE
        reasons.append(f"surface match: '{entry.surface}'")

    # --- 8. Diagnostic signal keyword overlap ---
    if signals.diagnostic_signals:
        all_sig_diag_text = " ".join(signals.diagnostic_signals).lower()
        for kb_sig in entry.diagnostic_signals:
            if _overlap(_norm(kb_sig), all_sig_diag_text):
                score += W_DIAG_SIGNAL
                reasons.append(f"diagnostic_signal overlap: '{kb_sig[:60]}'")
                break  # one hit is enough for this weight bucket

    # --- 9. Search keyword overlap ---
    if not reasons or score < W_ERROR_CODE:
        # Only apply keyword matching when stronger signals are weak/absent
        all_sig_text = " ".join(
            signals.error_messages
            + signals.apps
            + signals.modules
            + signals.categories
            + (([signals.user_description] if signals.user_description else []))
        ).lower()
        if all_sig_text:
            for kw in entry.search_keywords:
                kw_norm = _norm(kw)
                if kw_norm and kw_norm in all_sig_text:
                    score += W_KEYWORD
                    reasons.append(f"search_keyword match: '{kw}'")
                    break

    # Optional curated multi-concept match. A text hint alone remains below
    # the strong threshold; it supplies no evidence or diagnosis confidence.
    from .symptoms import match_pattern
    texts = [('user_description', signals.user_description)] + [
        (f'error_messages[{i}]', text) for i, text in enumerate(signals.error_messages)]
    pattern_reason = match_pattern(entry._raw, texts)
    if pattern_reason and score < 0.30:
        score = 0.30
        reasons.append(pattern_reason)

    # Cap at 1.0 (rounding artefacts)
    score = min(round(score, 6), 1.0)

    return ScoredEntry(entry=entry, score=score, match_reasons=reasons)
