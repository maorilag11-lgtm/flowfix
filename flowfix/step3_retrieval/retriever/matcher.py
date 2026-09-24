"""
FlowFix — Step 3 Retrieval — Matcher

Extracts a SignalBag from the Step 1 NormalizedProblem and Step 2 WorkflowAnalysis.

Rules:
- Never invent signals absent from the input.
- Never re-introduce redacted values (anything containing [REDACTED:]).
- Keep signal extraction deterministic and side-effect free.
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis
from flowfix.step3_retrieval.retriever.scorer import SignalBag


_CATEGORY_FROM_HTTP = {
    400: "http",
    401: "authentication",
    403: "authorization",
    404: "http",
    405: "http",
    408: "timeout",
    409: "http",
    410: "http",
    422: "validation",
    429: "rate_limit",
    500: "external_service",
    502: "external_service",
    503: "external_service",
    504: "timeout",
}

_LAYER_FROM_HTTP = {
    400: "external_api",
    401: "external_api",
    403: "external_api",
    404: "external_api",
    422: "external_api",
    429: "external_api",
    500: "external_api",
    502: "external_api",
    503: "external_api",
}


def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


def _safe(v: Optional[str]) -> Optional[str]:
    if not v or _is_redacted(v):
        return None
    return v.strip().lower() if v else None


def build_signal_bag(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
) -> SignalBag:
    """
    Build a SignalBag from Step 1 + Step 2 outputs.
    All strings are normalised to lower-case.
    Redacted values are excluded.
    """
    bag = SignalBag()

    # --- Error codes + HTTP codes ---
    bag.http_status_codes = list(problem.errors.http_status_codes)
    bag.error_codes = [str(c) for c in problem.errors.http_status_codes]
    bag.error_codes += [c for c in problem.errors.error_codes if c]

    # Add HTTP status from execution context
    ctx_status = problem.execution_context.http.status
    if ctx_status and ctx_status not in bag.http_status_codes:
        bag.http_status_codes.append(ctx_status)
        if str(ctx_status) not in bag.error_codes:
            bag.error_codes.append(str(ctx_status))

    # Deduplicate
    bag.http_status_codes = list(dict.fromkeys(bag.http_status_codes))
    bag.error_codes = list(dict.fromkeys(bag.error_codes))

    # --- Error messages (redacted values excluded) ---
    bag.error_messages = [
        _safe(msg) for msg in problem.errors.exact_error_messages
        if _safe(msg) is not None
    ]

    # --- Apps and modules from Step 2 workflow graph ---
    for node in analysis.workflow.nodes:
        if node.app:
            app_norm = node.app.lower().strip()
            if app_norm and app_norm not in bag.apps:
                bag.apps.append(app_norm)
        if node.module_type:
            mod_norm = node.module_type.lower().strip()
            if mod_norm and mod_norm not in bag.modules:
                bag.modules.append(mod_norm)
        if node.app and node.action:
            mod_full = f"{node.app}.{node.action}".lower()
            if mod_full not in bag.modules:
                bag.modules.append(mod_full)

    # From failure location (more specific)
    fl = analysis.failure_location
    if fl:
        if fl.app:
            app_norm = fl.app.lower().strip()
            if app_norm and app_norm not in bag.apps:
                bag.apps.insert(0, app_norm)  # prioritise failure app

    # --- Categories inferred from HTTP codes ---
    for code in bag.http_status_codes:
        cat = _CATEGORY_FROM_HTTP.get(code)
        if cat and cat not in bag.categories:
            bag.categories.append(cat)

    # Always add "http" if http module present and http codes
    if analysis.workflow.has_http and bag.http_status_codes:
        if "http" not in bag.categories:
            bag.categories.append("http")

    # Structural categories from graph
    if analysis.workflow.has_iterator and "iterator" not in bag.categories:
        bag.categories.append("iterator")
    if analysis.workflow.has_aggregator and "aggregator" not in bag.categories:
        bag.categories.append("aggregator")
    if analysis.workflow.has_router and "router" not in bag.categories:
        bag.categories.append("router")
    if analysis.workflow.has_webhook and "webhook" not in bag.categories:
        bag.categories.append("webhook")

    # From Step 2 hypotheses — extract category hints
    for hyp in analysis.hypotheses:
        h = hyp.hypothesis.lower()
        if "auth" in h or "credential" in h:
            for cat in ("authentication", "authorization"):
                if cat not in bag.categories:
                    bag.categories.append(cat)
        if "mapping" in h or "field" in h:
            if "mapping" not in bag.categories:
                bag.categories.append("mapping")
        if "rate limit" in h:
            if "rate_limit" not in bag.categories:
                bag.categories.append("rate_limit")

    # --- Layers inferred from HTTP codes ---
    for code in bag.http_status_codes:
        lyr = _LAYER_FROM_HTTP.get(code)
        if lyr and lyr not in bag.layers:
            bag.layers.append(lyr)

    # --- Surfaces inferred from graph ---
    if analysis.workflow.has_http:
        if "module" not in bag.surfaces:
            bag.surfaces.append("module")
    if analysis.workflow.has_webhook:
        if "webhook" not in bag.surfaces:
            bag.surfaces.append("webhook")
    if analysis.workflow.has_iterator:
        if "iterator" not in bag.surfaces:
            bag.surfaces.append("iterator")
    if analysis.workflow.has_aggregator:
        if "aggregator" not in bag.surfaces:
            bag.surfaces.append("aggregator")
    if analysis.workflow.has_router:
        if "router" not in bag.surfaces:
            bag.surfaces.append("router")
    if analysis.workflow.filters:
        if "filter" not in bag.surfaces:
            bag.surfaces.append("filter")

    # Failure location surface
    if fl and fl.module_id:
        if "module" not in bag.surfaces:
            bag.surfaces.append("module")

    # --- Diagnostic signals from Step 2 ---
    bag.diagnostic_signals = [
        s.signal.lower() for s in analysis.diagnostic_signals
        if s.signal and not _is_redacted(s.signal)
    ]

    # --- User description (safe) ---
    desc = _safe(problem.user_description)
    if desc:
        bag.user_description = desc

    return bag
