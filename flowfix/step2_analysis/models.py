"""
FlowFix — Step 2 Analysis
Output models — WorkflowAnalysis contract.

This is the internal contract produced by Step 2 and consumed by Step 3 (KB Search).
It is completely separate from both:
  - The Step 1 NormalizedProblem contract
  - The Knowledge Base schema (make_workflow_doctor_kb_v1.3.1)

Confidence levels:
  high    — information explicitly provided in input
  medium  — deduction supported by multiple signals
  low     — plausible hypothesis, insufficient evidence
  unknown — cannot be determined from available data
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal

Confidence = Literal["high", "medium", "low", "unknown"]


# ---------------------------------------------------------------------------
# Workflow graph
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """A single module represented as a node in the workflow graph."""
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    app: Optional[str] = None
    action: Optional[str] = None          # e.g. "sendEmail" from "gmail.sendEmail"
    module_type: Optional[str] = None     # full type string e.g. "gmail.sendEmail"
    position: Optional[int] = None        # order in the flat flow (0-indexed)
    predecessors: list[str] = field(default_factory=list)  # module_ids
    successors: list[str] = field(default_factory=list)    # module_ids
    is_router: bool = False
    is_iterator: bool = False
    is_aggregator: bool = False
    is_webhook: bool = False
    is_http: bool = False
    is_error_handler: bool = False


@dataclass
class GraphRoute:
    """A router route in the workflow graph."""
    label: Optional[str] = None
    module_ids: list[str] = field(default_factory=list)


@dataclass
class GraphFilter:
    """A filter extracted from the workflow graph."""
    module_id: Optional[str] = None       # ID of the module with the filter
    conditions: list[dict] = field(default_factory=list)
    filter_mismatch_detected: bool = False  # True if context contradicts filter


@dataclass
class GraphErrorHandler:
    """An error handler in the workflow graph."""
    module_id: Optional[str] = None
    handler_type: Optional[str] = None


@dataclass
class WorkflowGraph:
    """Structural representation of the Make.com scenario."""
    scenario_name: Optional[str] = None
    module_count: int = 0
    nodes: list[GraphNode] = field(default_factory=list)
    routes: list[GraphRoute] = field(default_factory=list)
    filters: list[GraphFilter] = field(default_factory=list)
    error_handlers: list[GraphErrorHandler] = field(default_factory=list)
    has_router: bool = False
    has_iterator: bool = False
    has_aggregator: bool = False
    has_webhook: bool = False
    has_http: bool = False
    has_error_handler: bool = False


# ---------------------------------------------------------------------------
# Failure location
# ---------------------------------------------------------------------------

@dataclass
class FailureLocation:
    """Where the failure appears to have occurred."""
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    app: Optional[str] = None
    confidence: Optional[Confidence] = None
    source: Optional[str] = None   # e.g. "explicit_context", "error_signal", "deduced"


# ---------------------------------------------------------------------------
# Observations — facts / signals / hypotheses
# ---------------------------------------------------------------------------

@dataclass
class ObservedFact:
    """
    A fact directly present in the input.
    Never invented. Confidence is always high by definition.
    """
    fact: str = ""
    source: str = ""     # e.g. "execution_context", "error_text", "blueprint"


@dataclass
class DiagnosticSignal:
    """
    A technical indicator that may be relevant to diagnosis.
    Derived from input data — not a confirmed cause.
    """
    signal: str = ""
    confidence: Confidence = "medium"
    source: str = ""


@dataclass
class Hypothesis:
    """
    A non-confirmed deduction.
    Must never be presented as a confirmed cause.
    Must always be marked as a hypothesis.
    """
    hypothesis: str = ""
    confidence: Confidence = "low"
    basis: str = ""   # what this is based on


# ---------------------------------------------------------------------------
# Dependency analysis
# ---------------------------------------------------------------------------

@dataclass
class DependencyChain:
    """
    Relevant module dependency chain around the failure area.
    """
    upstream_module_ids: list[str] = field(default_factory=list)
    target_module_id: Optional[str] = None
    downstream_module_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Root output contract — passed to Step 3
# ---------------------------------------------------------------------------

@dataclass
class WorkflowAnalysis:
    """
    The internal contract produced by Step 2 and passed to Step 3 (KB Search).

    Contains:
    - Structural representation of the workflow
    - Localisation of the potential failure point
    - Observed facts (from input)
    - Diagnostic signals (derived)
    - Hypotheses (non-confirmed deductions)
    - Dependency chain around the failure
    - Warnings and missing information
    """
    analysis_version: str = "1.0"
    dependency_evidence: list[dict] = field(default_factory=list)

    # Inherited from Step 1 for traceability
    analysis_id: str = ""

    # Workflow structure
    workflow: WorkflowGraph = field(default_factory=WorkflowGraph)

    # Failure location
    failure_location: Optional[FailureLocation] = None

    # Observations
    observed_facts: list[ObservedFact] = field(default_factory=list)
    diagnostic_signals: list[DiagnosticSignal] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)

    # Dependencies around failure
    dependencies: Optional[DependencyChain] = None

    # Bookkeeping
    warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
