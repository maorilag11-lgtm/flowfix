"""
FlowFix — Step 2 Analysis — Analyzer

Consumes a NormalizedProblem (Step 1 output) and produces a WorkflowAnalysis.

Responsibilities:
  1. Build the workflow graph from the blueprint.
  2. Locate the failing module (explicit or deduced).
  3. Collect observed facts from the input.
  4. Derive diagnostic signals.
  5. Form hypotheses (clearly marked as non-confirmed).
  6. Build the dependency chain around the failure.
  7. Record warnings and missing information.

Step 2 does NOT:
  - Access the Knowledge Base.
  - Generate diagnoses or solutions.
  - Invent missing data.
  - Reproduce or recover redacted secrets.
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import (
    WorkflowAnalysis,
    WorkflowGraph,
    GraphNode,
    FailureLocation,
    ObservedFact,
    DiagnosticSignal,
    Hypothesis,
    DependencyChain,
)
from flowfix.step2_analysis.graph.graph_builder import build_graph


# ---------------------------------------------------------------------------
# Secret guard — never re-introduce redacted content
# ---------------------------------------------------------------------------

def _is_redacted(value: Optional[str]) -> bool:
    return value is not None and "[REDACTED:" in value


def _safe_str(value) -> Optional[str]:
    """Return value only if it is not redacted and is a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        return None
    if _is_redacted(value):
        return None  # don't surface redacted content
    return value


# ---------------------------------------------------------------------------
# Failure location helpers
# ---------------------------------------------------------------------------

def _locate_failure(
    problem: NormalizedProblem,
    graph: WorkflowGraph,
) -> tuple[Optional[FailureLocation], list[str]]:
    """
    Determine where the failure occurred.

    Confidence:
      high   — explicitly provided in execution_context
      medium — deduced from error signals cross-referenced with a module
      low    — only hypothesis possible
      None   — cannot determine
    """
    ctx = problem.execution_context
    notes: list[str] = []

    import re
    references = set()
    text_refs = set()
    for msg in problem.errors.exact_error_messages:
        text_refs.update(re.findall(r"\bmodule\s*(?:id\s*)?[#:=]?\s*[\"']?([A-Za-z0-9_-]+)\b", msg, re.I))
        for node in graph.nodes:
            label = node.module_name or ""
            if len(label) >= 5 and len(label.split()) >= 2 and re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", msg, re.I):
                text_refs.add(node.module_id)
    references.update(text_refs)
    if ctx.failing_module_id:
        references.add(str(ctx.failing_module_id))
    if ctx.failing_module_name:
        matches = [n for n in graph.nodes if n.module_name == ctx.failing_module_name]
        if len(matches) == 1:
            references.add(matches[0].module_id)
        elif graph.nodes:
            notes.append("Explicit module name is unknown or ambiguous.")
            return None, notes
    if len(references) > 1:
        notes.append("Contradictory module references: localization withheld.")
        return None, notes
    if references:
        ref = next(iter(references))
        matches = [n for n in graph.nodes if n.module_id == ref]
        if graph.nodes and len(matches) != 1:
            notes.append("Module reference not uniquely present in blueprint.")
            return None, notes
        node = matches[0] if matches else None
        explicit = bool(ctx.failing_module_id or ctx.failing_module_name)
        return FailureLocation(module_id=ref, module_name=node.module_name if node else ctx.failing_module_name,
            app=node.app if node else None, confidence="high" if explicit else "medium",
            source="explicit_context" if explicit else "error_text_reference"), notes
    if ctx.failing_module_name and not graph.nodes:
        return FailureLocation(module_name=ctx.failing_module_name, confidence="high", source="explicit_context"), notes

    # --- Cannot determine ---
    return None, notes


# ---------------------------------------------------------------------------
# Observed facts
# ---------------------------------------------------------------------------

def _collect_facts(problem: NormalizedProblem) -> list[ObservedFact]:
    facts: list[ObservedFact] = []

    # User description — when no structured error is available
    if problem.user_description and not _is_redacted(problem.user_description):
        facts.append(ObservedFact(
            fact=f"User description: {problem.user_description}",
            source="user_description",
        ))

    # Error messages
    for msg in problem.errors.exact_error_messages:
        facts.append(ObservedFact(
            fact=f"Error message received: {msg}",
            source="error_text",
        ))

    # HTTP status codes from error text
    for code in problem.errors.http_status_codes:
        facts.append(ObservedFact(
            fact=f"HTTP status {code} present in error message.",
            source="error_text",
        ))

    # Execution context — only surface non-redacted values
    ctx = problem.execution_context

    if ctx.failing_module_id:
        facts.append(ObservedFact(
            fact=f"Failing module ID provided: {ctx.failing_module_id}",
            source="execution_context",
        ))

    if ctx.failing_module_name:
        facts.append(ObservedFact(
            fact=f"Failing module name provided: {ctx.failing_module_name}",
            source="execution_context",
        ))

    if ctx.http.status:
        facts.append(ObservedFact(
            fact=f"HTTP status in execution context: {ctx.http.status}",
            source="execution_context",
        ))

    if ctx.http.response_body and not _is_redacted(ctx.http.response_body):
        facts.append(ObservedFact(
            fact=f"HTTP response body available (length: {len(ctx.http.response_body)})",
            source="execution_context",
        ))

    if ctx.bundle_count is not None:
        facts.append(ObservedFact(
            fact=f"Bundle count: {ctx.bundle_count}",
            source="execution_context",
        ))

    if ctx.recent_changes and not _is_redacted(ctx.recent_changes):
        facts.append(ObservedFact(
            fact=f"Recent changes reported: {ctx.recent_changes}",
            source="execution_context",
        ))

    # Blueprint
    bp = problem.blueprint
    if bp.provided and bp.recognized_as_make_blueprint:
        facts.append(ObservedFact(
            fact=f"Make.com blueprint provided with {len(bp.modules)} module(s).",
            source="blueprint",
        ))
        if bp.scenario_name:
            facts.append(ObservedFact(
                fact=f"Scenario name: {bp.scenario_name}",
                source="blueprint",
            ))

    # Error codes (non-HTTP)
    for code in problem.errors.error_codes:
        facts.append(ObservedFact(
            fact=f"Error code detected: {code}",
            source="error_text",
        ))

    return facts


# ---------------------------------------------------------------------------
# Diagnostic signals
# ---------------------------------------------------------------------------

def _derive_signals(
    problem: NormalizedProblem,
    graph: WorkflowGraph,
    failure: Optional[FailureLocation],
) -> list[DiagnosticSignal]:
    signals: list[DiagnosticSignal] = []

    ctx = problem.execution_context

    # HTTP status signals
    for code in problem.errors.http_status_codes:
        if 400 <= code < 500:
            signals.append(DiagnosticSignal(
                signal=f"HTTP {code} indicates a client-side error (bad request, auth, or data issue).",
                confidence="high",
                source="http_status",
            ))
        elif 500 <= code < 600:
            signals.append(DiagnosticSignal(
                signal=f"HTTP {code} indicates a server-side error from the external service.",
                confidence="high",
                source="http_status",
            ))

    if ctx.http.status:
        code = ctx.http.status
        if 400 <= code < 500:
            signals.append(DiagnosticSignal(
                signal=f"HTTP {code} in execution context: external service rejected the request.",
                confidence="high",
                source="execution_context",
            ))

    # Filter mismatch detection
    for f in graph.filters:
        if f.conditions and ctx.actual_behavior and not _is_redacted(ctx.actual_behavior):
            # Simple: flag the filter as potentially relevant
            signals.append(DiagnosticSignal(
                signal=f"Filter on module {f.module_id} has conditions that may affect execution flow.",
                confidence="medium",
                source="blueprint_filter",
            ))

    # Error handler absence
    if graph.has_http and not graph.has_error_handler:
        signals.append(DiagnosticSignal(
            signal="HTTP module present but no error handler detected in the workflow.",
            confidence="medium",
            source="blueprint_structure",
        ))

    # Iterator with bundle count
    if graph.has_iterator and ctx.bundle_count is not None:
        signals.append(DiagnosticSignal(
            signal=f"Iterator present; {ctx.bundle_count} bundle(s) processed.",
            confidence="high",
            source="execution_context",
        ))

    # Webhook present — data entry point
    if graph.has_webhook:
        signals.append(DiagnosticSignal(
            signal="Webhook trigger detected — payload structure affects all downstream modules.",
            confidence="medium",
            source="blueprint_structure",
        ))

    # Router with failure — which branch?
    if graph.has_router and failure:
        signals.append(DiagnosticSignal(
            signal="Router present — the failing module may be inside a specific route branch.",
            confidence="low",
            source="blueprint_structure",
        ))

    # Response body available
    if ctx.http.response_body and not _is_redacted(ctx.http.response_body):
        signals.append(DiagnosticSignal(
            signal="HTTP response body is available and may contain specific error details.",
            confidence="high",
            source="execution_context",
        ))

    return signals


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------

def _form_hypotheses(
    problem: NormalizedProblem,
    graph: WorkflowGraph,
    failure: Optional[FailureLocation],
) -> list[Hypothesis]:
    hyps: list[Hypothesis] = []

    ctx = problem.execution_context

    # HTTP 401/403 → auth hypothesis
    all_codes = problem.errors.http_status_codes + (
        [ctx.http.status] if ctx.http.status else []
    )

    if 401 in all_codes or 403 in all_codes:
        hyps.append(Hypothesis(
            hypothesis="The failure may be related to authentication or authorization.",
            confidence="medium",
            basis="HTTP 401/403 status code observed.",
        ))

    if 422 in all_codes:
        hyps.append(Hypothesis(
            hypothesis="A required field may be missing or incorrectly mapped in the failing module.",
            confidence="medium",
            basis="HTTP 422 Unprocessable Entity suggests invalid data sent to the API.",
        ))

    if 429 in all_codes:
        hyps.append(Hypothesis(
            hypothesis="The external API rate limit may have been exceeded.",
            confidence="medium",
            basis="HTTP 429 Too Many Requests.",
        ))

    if any(c >= 500 for c in all_codes):
        hyps.append(Hypothesis(
            hypothesis="The external service may be experiencing issues unrelated to the workflow configuration.",
            confidence="low",
            basis="HTTP 5xx server error observed.",
        ))

    # Filter mismatch
    if graph.filters:
        for f in graph.filters:
            if f.conditions:
                hyps.append(Hypothesis(
                    hypothesis=f"A filter on module {f.module_id} may be blocking execution unexpectedly.",
                    confidence="low",
                    basis="Filter conditions present — context does not confirm whether they pass.",
                ))
                break  # one filter hypothesis is enough at this stage

    # Error handler absence with failure
    if graph.has_http and not graph.has_error_handler and failure:
        hyps.append(Hypothesis(
            hypothesis="Without an error handler, a single failure may stop the entire scenario.",
            confidence="medium",
            basis="No error handler detected in blueprint; HTTP module present.",
        ))

    return hyps


# ---------------------------------------------------------------------------
# Dependency chain
# ---------------------------------------------------------------------------

def _build_dependencies(
    graph: WorkflowGraph,
    failure: Optional[FailureLocation],
) -> Optional[DependencyChain]:
    if not failure or not failure.module_id:
        return None

    # Find the node
    target_node: Optional[GraphNode] = None
    for node in graph.nodes:
        if node.module_id == failure.module_id:
            target_node = node
            break

    if not target_node:
        return None

    chain = DependencyChain(
        upstream_module_ids=list(target_node.predecessors),
        target_module_id=failure.module_id,
        downstream_module_ids=list(target_node.successors),
        notes=[],
    )

    # Add context notes (no invention)
    if target_node.is_http:
        chain.notes.append("Failing module is an HTTP/API module — check request mapping and auth.")
    if target_node.predecessors:
        chain.notes.append(
            f"Data flows from module(s) {target_node.predecessors} — check upstream output mapping."
        )
    if target_node.successors:
        chain.notes.append(
            f"Module(s) {target_node.successors} depend on output from the failing module."
        )

    return chain


# ---------------------------------------------------------------------------
# Missing information
# ---------------------------------------------------------------------------

def _collect_missing(
    problem: NormalizedProblem,
    graph: WorkflowGraph,
    failure: Optional[FailureLocation],
) -> list[str]:
    missing: list[str] = []

    # Propagate from Step 1
    missing.extend(problem.metadata.missing_information)

    if not problem.blueprint.provided:
        missing.append("blueprint (required for structural analysis)")

    if failure is None and graph.module_count > 0:
        missing.append("failing_module_id or failing_module_name (cannot pinpoint failure location)")

    if not problem.errors.exact_error_messages and not problem.errors.http_status_codes:
        missing.append("error_message or http_status_code (no error signal available)")

    if not problem.execution_context.http.response_body and graph.has_http:
        missing.append("http_response_body (would help identify the specific API rejection reason)")

    # Deduplicate
    return list(dict.fromkeys(missing))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze(problem: NormalizedProblem) -> WorkflowAnalysis:
    """
    Run Step 2 analysis on a NormalizedProblem.

    Returns a WorkflowAnalysis ready for Step 3 (KB Search).
    Never raises — issues are captured as warnings.
    Does NOT access the Knowledge Base.
    Does NOT produce diagnoses or solutions.
    """
    analysis = WorkflowAnalysis(analysis_id=problem.analysis_id)
    warnings: list[str] = []

    # 1. Build workflow graph
    graph, graph_warnings = build_graph(problem.blueprint)
    analysis.workflow = graph
    warnings.extend(graph_warnings)

    # 2. Locate failure
    failure, location_notes = _locate_failure(problem, graph)
    analysis.failure_location = failure
    warnings.extend(location_notes)

    # 3. Observed facts
    analysis.observed_facts = _collect_facts(problem)

    # 4. Diagnostic signals
    analysis.diagnostic_signals = _derive_signals(problem, graph, failure)

    # 5. Hypotheses
    analysis.hypotheses = _form_hypotheses(problem, graph, failure)

    # 6. Dependency chain
    analysis.dependencies = _build_dependencies(graph, failure)

    # 7. Missing information
    analysis.missing_information = _collect_missing(problem, graph, failure)

    if problem.execution_context.root_cause_context is not None:
        from .trace_dependencies import collect
        analysis.dependency_evidence = collect(problem, graph)
    analysis.warnings = warnings
    return analysis
