"""
FlowFix — Step 2 Analysis — Graph Builder

Constructs a WorkflowGraph from the BlueprintInfo produced by Step 1.

Rules:
- NEVER create an edge between two modules based solely on their order
  in the 'flow' array.  Order ≠ execution relationship.
- Edges are created ONLY from explicit, structural data present in the
  Blueprint:
    * Router route structures (router node → first-of-route; sequential
      order within a route).
    * Any other explicit connection data already parsed by Step 1.
- A module with no known connections stays as an isolated node.
- Absence of a connection is never treated as proof that no connection
  exists — it is simply unknown.
- Never access the Knowledge Base.
- Never produce diagnoses.

v1.1 change: removed implicit sequential-order edges.
"""

from __future__ import annotations
from typing import Optional

from flowfix.step1_intake.intake.models import (
    BlueprintInfo,
    BlueprintModule,
    BlueprintRoute,
    BlueprintFilter,
    BlueprintErrorHandler,
)
from flowfix.step2_analysis.models import (
    WorkflowGraph,
    GraphNode,
    GraphRoute,
    GraphFilter,
    GraphErrorHandler,
)


# ---------------------------------------------------------------------------
# Module type classification helpers
# ---------------------------------------------------------------------------

_ROUTER_APPS = {"gateway"}
_ROUTER_ACTIONS = {"router"}
_ITERATOR_KEYWORDS = {"iterator", "arrayelement"}
_AGGREGATOR_KEYWORDS = {"aggregator", "array-aggregator", "arrayaggregator", "textaggregator"}
_WEBHOOK_APPS = {"gateway", "webhook"}
_WEBHOOK_ACTIONS = {"trigger", "customwebhook", "respondtoaclient", "customwebhooktrigger"}
_HTTP_APPS = {"http", "util"}
_HTTP_ACTIONS = {"actionsenddataadvanced", "actionsenddata", "make_an_api_key_auth_request",
                 "make_an_oauth2_request", "make_a_basic_auth_request", "make_a_request"}


def _classify(module: BlueprintModule) -> dict[str, bool]:
    """Return classification flags for a blueprint module."""
    mtype = (module.module_type or "").lower()
    app = (module.app or "").lower()
    action = ""
    if "." in mtype:
        action = mtype.split(".", 1)[1].lower()

    return {
        "is_router": (
            app in _ROUTER_APPS and any(k in action for k in _ROUTER_ACTIONS)
            or any(k in mtype for k in _ROUTER_ACTIONS)
        ),
        "is_iterator": any(k in action for k in _ITERATOR_KEYWORDS),
        "is_aggregator": any(k in action for k in _AGGREGATOR_KEYWORDS),
        "is_webhook": (
            app in _WEBHOOK_APPS and any(k in action for k in _WEBHOOK_ACTIONS)
        ),
        "is_http": app in _HTTP_APPS and any(k in action for k in _HTTP_ACTIONS),
        "is_error_handler": "error" in action and "handler" in action,
    }


def _extract_action(module_type: Optional[str]) -> Optional[str]:
    if not module_type or "." not in module_type:
        return None
    return module_type.split(".", 1)[1]


# ---------------------------------------------------------------------------
# Edge resolution — explicit sources ONLY
#
# v1.1: The flat 'flow' order is NOT a valid source of edges.
#
# Accepted explicit sources:
#   A. BlueprintInfo.connections — explicit connection list when present in
#      the Blueprint (e.g. [{"source": "1", "target": "2"}, ...]).
#      Multiple field-name conventions are normalised (source/target,
#      from/to).  Integer IDs are coerced to strings.
#   B. Sequential order WITHIN a named route (routes[].flow[]).
#      A route encodes an explicit execution sequence.
#   C. Router → first-of-route edges (derived from route structure).
#
# NOT accepted:
#   - Position of a module in the top-level 'flow' array.
#   - Proximity in any list.
#   - metadata fields.
#   - Any inference not supported by explicit structural data.
# ---------------------------------------------------------------------------

def _extract_connection_pair(conn: dict) -> tuple[str, str] | None:
    """
    Normalise a single connection dict to (source_id, target_id) strings.
    Supports: {source/target}, {from/to}.
    Returns None if the dict does not encode a recognisable directed edge.
    """
    def _str(v) -> str:
        return str(v).strip() if v is not None else ""

    src = _str(conn.get("source") or conn.get("from"))
    dst = _str(conn.get("target") or conn.get("to"))

    if src and dst and src != dst:
        return src, dst
    return None


def _build_edge_map(
    modules: list[BlueprintModule],
    routes: list[BlueprintRoute],
    connections: list[dict] | None = None,
) -> dict[str, dict[str, list[str]]]:
    """
    Return {module_id: {"predecessors": [...], "successors": [...]}}

    Edges are built ONLY from explicitly structural data:
      A. BlueprintInfo.connections list (highest priority — direct edges).
      B. Sequential order within route.flow lists.
      C. Router → first-of-route relationships.

    Modules with no explicit connection data remain as isolated nodes.
    """
    # Initialise every module with empty adjacency
    all_ids = {m.id for m in modules if m.id}
    result: dict[str, dict[str, list[str]]] = {
        mid: {"predecessors": [], "successors": []}
        for mid in all_ids
    }

    # Helper to add a directed edge safely (dedup)
    def _add_edge(src: str, dst: str) -> None:
        if src in result and dst in result:
            if dst not in result[src]["successors"]:
                result[src]["successors"].append(dst)
            if src not in result[dst]["predecessors"]:
                result[dst]["predecessors"].append(src)

    # A. Explicit connections from BlueprintInfo.connections (highest priority)
    #    These are direct edges declared in the Blueprint's connections array.
    #    Multiple field-name conventions are supported (source/target, from/to).
    for conn in (connections or []):
        if not isinstance(conn, dict):
            continue
        pair = _extract_connection_pair(conn)
        if pair:
            _add_edge(pair[0], pair[1])

    # B. Edges within each route: the modules in route.flow are explicitly
    #    ordered by Make — each one is succeeded by the next within the route.
    for route in routes:
        route_ids = list(route.flow)
        for i in range(len(route_ids) - 1):
            _add_edge(route_ids[i], route_ids[i + 1])

    # C. Parent → first-of-route: only the explicit parent preserved by S1.
    # A sole router is not evidence of ownership. Legacy routes without
    # parent_module_id remain unresolved; their internal route edges survive.
    for route in routes:
        parent = getattr(route, "parent_module_id", None)
        route_ids = list(route.flow)
        if parent in all_ids and route_ids:
            _add_edge(parent, route_ids[0])

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_graph(bp: BlueprintInfo) -> tuple[WorkflowGraph, list[str]]:
    """
    Build a WorkflowGraph from a BlueprintInfo.

    Returns (graph, warnings).
    Never raises — issues are captured as warnings.
    Never creates edges from list order alone.
    """
    warnings: list[str] = []
    graph = WorkflowGraph()

    if not bp.provided:
        warnings.append("No blueprint provided — workflow graph is empty.")
        return graph, warnings

    if not bp.valid_json:
        warnings.append("Blueprint is not valid JSON — workflow graph is empty.")
        return graph, warnings

    if not bp.recognized_as_make_blueprint:
        warnings.append("Blueprint not recognised as Make.com scenario — workflow graph is empty.")
        return graph, warnings

    # Scenario-level
    graph.scenario_name = bp.scenario_name
    graph.module_count = len(bp.modules)

    if graph.module_count == 0:
        warnings.append("Blueprint contains no modules.")
        return graph, warnings

    # Build explicit-only edge map
    edge_map = _build_edge_map(bp.modules, bp.routes, bp.connections)
    for index, route in enumerate(bp.routes):
        if getattr(route, "parent_module_id", None) is None:
            warnings.append(
                f"Route {index}: explicit parent is missing; parent relationship remains unresolved."
            )


    known_ids = {m.id for m in bp.modules if m.id}
    for index, route in enumerate(bp.routes):
        if any(mid not in known_ids for mid in route.flow):
            warnings.append(f"Route {index}: unknown module reference; no edge is created across the gap.")

    # Warn when no connections could be established at all (structural info absent)
    total_edges = sum(len(v["successors"]) for v in edge_map.values())
    if total_edges == 0 and len(bp.modules) > 1:
        warnings.append(
            "No explicit connections found in blueprint — "
            "modules are represented as isolated nodes. "
            "Execution order between modules is unknown."
        )

    # Build nodes
    for i, bpm in enumerate(bp.modules):
        flags = _classify(bpm)
        node = GraphNode(
            module_id=bpm.id,
            module_name=bpm.name,
            app=bpm.app,
            action=_extract_action(bpm.module_type),
            module_type=bpm.module_type,
            position=i,
            predecessors=edge_map.get(bpm.id or "", {}).get("predecessors", []),
            successors=edge_map.get(bpm.id or "", {}).get("successors", []),
            **flags,
        )
        graph.nodes.append(node)

        # Update graph-level flags
        if flags["is_router"]:
            graph.has_router = True
        if flags["is_iterator"]:
            graph.has_iterator = True
        if flags["is_aggregator"]:
            graph.has_aggregator = True
        if flags["is_webhook"]:
            graph.has_webhook = True
        if flags["is_http"]:
            graph.has_http = True
        if flags["is_error_handler"]:
            graph.has_error_handler = True

    # Error handlers from blueprint
    for bpeh in bp.error_handlers:
        graph.has_error_handler = True
        graph.error_handlers.append(
            GraphErrorHandler(
                module_id=bpeh.module_id,
                handler_type=bpeh.handler_type,
            )
        )

    # Routes
    for bpr in bp.routes:
        graph.routes.append(
            GraphRoute(
                label=bpr.label,
                module_ids=list(bpr.flow),
            )
        )

    # Filters
    for bpf in bp.filters:
        graph.filters.append(
            GraphFilter(
                module_id=bpf.module_id,
                conditions=list(bpf.conditions),
            )
        )

    return graph, warnings
