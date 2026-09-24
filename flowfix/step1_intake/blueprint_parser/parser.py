"""
FlowFix — Step 1 Intake — Blueprint Parser

Defensively parses a Make.com scenario blueprint (JSON).

Rules:
- Never invent data that is absent in the input.
- Mark missing fields as None, not as guesses.
- Handle invalid / partial JSON gracefully — never raise unhandled exceptions.
- Recognise a blueprint as Make-specific only when clear structural markers
  are present (e.g. "flow" array with typed module objects).
"""

from __future__ import annotations
import json
import re
from typing import Optional

from ..intake.models import (
    BlueprintInfo,
    BlueprintModule,
    BlueprintRoute,
    BlueprintFilter,
    BlueprintErrorHandler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_str(value) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _extract_app(module_type: Optional[str]) -> Optional[str]:
    """
    Make module types follow the pattern "<app>.<ActionName>".
    Extract the app prefix when present.
    """
    if not module_type or "." not in module_type:
        return None
    return module_type.split(".")[0].lower()


def _walk(flow, warnings, path="flow", depth=0, budget=None):
    if budget is None:
        budget = [10000]
    if depth > 24:
        warnings.append(path + ": traversal depth limit")
        return
    if not isinstance(flow, list):
        warnings.append(path + ": expected array")
        return
    for i, item in enumerate(flow):
        budget[0] -= 1
        if budget[0] < 0:
            warnings.append("Module traversal size limit")
            return
        loc = f"{path}[{i}]"
        if not isinstance(item, dict):
            warnings.append(loc + ": expected object")
            continue
        yield item, loc
        routes = item.get("routes", [])
        if not isinstance(routes, list):
            warnings.append(loc + ".routes: expected array")
            continue
        for j, route in enumerate(routes):
            if not isinstance(route, dict):
                warnings.append(loc + ".routes: expected object")
                continue
            yield from _walk(route.get("flow", []), warnings, f"{loc}.routes[{j}].flow", depth+1, budget)


def _parse_structure(flow, info):
    for item, path in _walk(flow, info.parse_warnings):
        mid = _safe_str(item.get("id"))
        module_type = _safe_str(item.get("module"))
        info.modules.append(BlueprintModule(id=mid, blueprint_path=path,
            name=_safe_str(item.get("name") or item.get("label")),
            module_type=module_type, app=_extract_app(module_type),
            metadata={k:v for k,v in item.items() if k not in {"id","name","label","module","routes","filter"}}))
        routes = item.get("routes", [])
        if isinstance(routes, list):
            for j, route in enumerate(routes):
                if not isinstance(route, dict):
                    continue
                sub = route.get("flow", [])
                info.routes.append(BlueprintRoute(label=_safe_str(route.get("label")),
                    flow=[str(m['id']) for m in sub if isinstance(m, dict) and m.get('id') is not None] if isinstance(sub,list) else [],
                    parent_module_id=mid, provenance=f"{path}.routes[{j}]"))
        f = item.get("filter")
        if isinstance(f, dict):
            conditions = f.get("conditions", [])
            if not isinstance(conditions, list):
                info.parse_warnings.append(path + ".filter.conditions: expected array")
                conditions = []
            info.filters.append(BlueprintFilter(module_id=mid, conditions=conditions, provenance=path + ".filter"))
        eh = item.get("errorHandler") or item.get("error_handler")
        if isinstance(eh, dict):
            info.error_handlers.append(BlueprintErrorHandler(module_id=mid,
                handler_type=_safe_str(eh.get("type") or eh.get("directive")), provenance=path + (".errorHandler" if "errorHandler" in item else ".error_handler")))
        elif eh is not None:
            info.parse_warnings.append(path + ": unsupported error handler variant")


_MAKE_MODULE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*\.[a-zA-Z][a-zA-Z0-9_-]*$")


def _is_make_blueprint(data: dict) -> bool:
    """
    Heuristic: is this dict likely a Make.com scenario blueprint?

    Requirements (all must hold):
    1. Top-level 'flow' key must be a non-empty list.
    2. At least one element of 'flow' must be a dict containing a 'module'
       key whose value matches the Make pattern "<app>.<ActionName>"
       (e.g. "gmail.sendEmail", "hubspot.watchContacts").

    Rationale: a JSON with only {"flow": [{"id": "123"}]} is NOT enough —
    'id' alone could belong to any system.  The 'module' key with the
    dot-notation pattern is the reliable Make-specific marker.
    """
    if not isinstance(data, dict):
        return False

    flow = data.get("flow")
    if not isinstance(flow, list) or len(flow) == 0:
        return False

    for item in flow:
        if not isinstance(item, dict):
            continue
        module_val = item.get("module")
        if isinstance(module_val, str) and _MAKE_MODULE_RE.match(module_val):
            return True

    # No item had a recognisable Make module string
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_blueprint(raw: str) -> BlueprintInfo:
    """
    Parse a raw string as a Make.com blueprint.

    Returns a BlueprintInfo regardless of input quality.
    Never raises — errors are captured in the returned object.
    """
    from ..redaction.redactor import redact_dict
    info = BlueprintInfo(provided=True)
    if not isinstance(raw, str) or len(raw) > 1_000_000:
        info.parse_warnings.append("Blueprint size/type limit")
        return info

    # --- JSON validity ---
    try:
        data = json.loads(raw)
        cleaned = redact_dict(data)
        data = cleaned.redacted_data
        info.raw_blueprint = json.dumps(data)
        info.parse_warnings.extend(cleaned.redactions)
        info.valid_json = True
    except (json.JSONDecodeError, ValueError, TypeError, RecursionError):
        info.valid_json = False
        info.recognized_as_make_blueprint = False
        return info  # Can't go further without valid JSON

    # --- Make recognition ---
    info.recognized_as_make_blueprint = _is_make_blueprint(data)

    if not info.recognized_as_make_blueprint:
        # Valid JSON but not a Make blueprint — return what we have
        return info

    # --- Scenario-level extraction ---
    info.scenario_name = _safe_str(
        data.get("name") or data.get("scenario", {}).get("name")
        if isinstance(data.get("scenario"), dict)
        else data.get("name")
    )

    # --- Structural extraction ---
    flow: list = data.get("flow", []) or []

    _parse_structure(flow, info)

    # Connections: only populated when 'connections' key is explicitly present.
    # 'metadata' is a different concept and must NOT be treated as connections.
    raw_connections = data.get("connections")
    if isinstance(raw_connections, list):
        info.connections = raw_connections
    # Any other type or absent key → leave connections as []

    return info
