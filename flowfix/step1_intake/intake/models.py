"""
FlowFix — Step 1 Intake
Internal data models (normalized_problem contract).

This is FlowFix's internal contract. It is completely separate from the
Knowledge Base schema (make_workflow_doctor_kb_v1.3.1).
Do NOT modify the KB schema to accommodate these models.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import uuid
from .field_contracts import JsonFieldObservation


# ---------------------------------------------------------------------------
# Sub-objects
# ---------------------------------------------------------------------------

@dataclass
class ErrorInfo:
    """Extracted error signals from raw user input."""
    exact_error_messages: list[str] = field(default_factory=list)
    error_codes: list[str] = field(default_factory=list)
    http_status_codes: list[int] = field(default_factory=list)


@dataclass
class BlueprintModule:
    """A single module extracted from a Make blueprint."""
    id: Optional[str] = None
    name: Optional[str] = None
    module_type: Optional[str] = None   # e.g. "gateway.BasicResponder"
    app: Optional[str] = None           # e.g. "gmail", "hubspot"
    metadata: dict = field(default_factory=dict)
    blueprint_path: Optional[str] = None


@dataclass
class BlueprintRoute:
    """A router route extracted from a Make blueprint."""
    label: Optional[str] = None
    flow: list[str] = field(default_factory=list)   # module IDs in order
    parent_module_id: Optional[str] = None
    provenance: Optional[str] = None


@dataclass
class BlueprintFilter:
    """A filter condition extracted from a Make blueprint."""
    module_id: Optional[str] = None
    conditions: list[dict] = field(default_factory=list)
    provenance: Optional[str] = None


@dataclass
class BlueprintErrorHandler:
    """An error handler extracted from a Make blueprint."""
    module_id: Optional[str] = None
    handler_type: Optional[str] = None   # e.g. "rollback", "commit", "ignore"
    provenance: Optional[str] = None


@dataclass
class BlueprintInfo:
    """Parsed representation of a Make.com scenario blueprint."""
    provided: bool = False
    valid_json: Optional[bool] = None
    recognized_as_make_blueprint: Optional[bool] = None
    raw_blueprint: Optional[str] = None   # original text, post-redaction

    # Scenario-level
    scenario_name: Optional[str] = None

    # Structural elements
    modules: list[BlueprintModule] = field(default_factory=list)
    connections: list[dict] = field(default_factory=list)
    routes: list[BlueprintRoute] = field(default_factory=list)
    filters: list[BlueprintFilter] = field(default_factory=list)
    error_handlers: list[BlueprintErrorHandler] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class HttpContext:
    """HTTP-specific execution details."""
    status: Optional[int] = None
    response_body: Optional[str] = None
    headers: Optional[dict] = None


@dataclass
class ExecutionContext:
    """Runtime context provided by the user."""
    failing_module_id: Optional[str] = None
    failing_module_name: Optional[str] = None
    timestamp: Optional[str] = None

    input_data: Optional[str] = None
    output_data: Optional[str] = None
    bundle_count: Optional[int] = None

    http: HttpContext = field(default_factory=HttpContext)

    logs: Optional[str] = None
    frequency: Optional[str] = None

    expected_behavior: Optional[str] = None
    actual_behavior: Optional[str] = None
    recent_changes: Optional[str] = None
    json_field_observation: Optional[JsonFieldObservation] = None
    root_cause_context: Optional[dict] = None


@dataclass
class IntakeMetadata:
    """Bookkeeping information about this intake pass."""
    received_sources: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    redactions_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Root normalized problem — output of Step 1
# ---------------------------------------------------------------------------

@dataclass
class NormalizedProblem:
    """
    The internal contract passed from Step 1 (Intake) to Step 2 (Analysis).

    Step 2 must be able to consume this object directly without re-parsing
    raw user input.
    """
    input_version: str = "1.0"
    analysis_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # What the user described in free text
    user_description: Optional[str] = None

    # Structured error information
    errors: ErrorInfo = field(default_factory=ErrorInfo)

    # Blueprint
    blueprint: BlueprintInfo = field(default_factory=BlueprintInfo)

    # Runtime context
    execution_context: ExecutionContext = field(default_factory=ExecutionContext)

    # Bookkeeping
    metadata: IntakeMetadata = field(default_factory=IntakeMetadata)

    def to_dict(self) -> dict:
        """Serialise to a plain dict for logging / transmission."""
        import dataclasses
        return dataclasses.asdict(self)
