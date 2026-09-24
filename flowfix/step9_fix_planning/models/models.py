"""
FlowFix — Step 9 Fix Planning — Models V1.1

All data models for the Fix Planning layer.

Design principles:
  - Step 9 is a TRANSLATION layer: it takes the reasoning output and
    produces a structured, actionable, human-verifiable fix plan.
  - No new reasoning. No KB access. No LLM. No network. No persistence.
  - No UUID randomness — all IDs are derived deterministically.
  - Secrets never surface. Hypotheses never upgraded to confirmed facts.
  - Deterministic: same inputs → same FixPlanResult.
  - Blueprint never modified.

V1.1 Changes:
  - ALLOWED_PLAN_STATUSES → READY, PARTIALLY_READY, BLOCKED, NOT_APPLICABLE
  - ALLOWED_TARGET_TYPES  → MODULE, FIELD, MAPPING, FILTER, ROUTER, ITERATOR,
                             AGGREGATOR, WEBHOOK, HTTP_CONFIGURATION, ERROR_HANDLER,
                             CONNECTION, UNKNOWN
  - ALLOWED_ACTION_TYPES  → INSPECT, VERIFY, UPDATE, REPLACE, REMOVE, ADD,
                             RECONNECT, RECONFIGURE, RERUN
  - Removed: ACTIONABLE, PARTIAL, INSUFFICIENT, ESCALATE (plan statuses)
  - Removed: MODULE_CONFIG, FIELD_MAPPING, AUTH_SETUP, FILTER_CONDITION,
             HTTP_REQUEST, DATA_TRANSFORM, ROUTE_BRANCH, ITERATOR_SETUP (target types)
  - Removed: CORRECT, TEST (action types)
  - Removed: field_name, observable_signal (old fields)
  - DiagnosisReference updated to V1.1 contract
  - FixTarget updated to V1.1 contract
  - FixAction updated to V1.1 contract
  - ExpectedOutcome updated to V1.1 contract
  - ValidationCriterion updated to V1.1 contract
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from flowfix.step4_reasoning.models_internal.corrections import ManualCorrectionProposal
from flowfix.step5_response.models_internal.guidance import (
    DiagnosticCheck, DocumentedSolution, DocumentationReference,
)


# ---------------------------------------------------------------------------
# Enum-like constants — V1.1 contract exact
# ---------------------------------------------------------------------------

ALLOWED_PLAN_STATUSES = frozenset({
    "READY",            # evidence sufficient, fix is actionable
    "PARTIALLY_READY",  # partial evidence, verification needed first
    "BLOCKED",          # insufficient or contradicted evidence
    "NOT_APPLICABLE",   # no fix plan possible for this context
})

ALLOWED_TARGET_TYPES = frozenset({
    "MODULE",
    "FIELD",
    "MAPPING",
    "FILTER",
    "ROUTER",
    "ITERATOR",
    "AGGREGATOR",
    "WEBHOOK",
    "HTTP_CONFIGURATION",
    "ERROR_HANDLER",
    "CONNECTION",
    "UNKNOWN",
})

ALLOWED_ACTION_TYPES = frozenset({
    "INSPECT",
    "VERIFY",
    "UPDATE",
    "REPLACE",
    "REMOVE",
    "ADD",
    "RECONNECT",
    "RECONFIGURE",
    "RERUN",
})

ALLOWED_CONFIDENCE_LEVELS = frozenset({
    "HIGH",
    "MEDIUM",
    "LOW",
    "UNKNOWN",
})

ALLOWED_RISK_LEVELS = frozenset({
    "LOW",
    "MEDIUM",
    "HIGH",
    "UNKNOWN",
})

ALLOWED_WARNING_CATEGORIES = frozenset({
    "LOW_CONFIDENCE",
    "PARTIAL_EVIDENCE",
    "MISSING_TARGET",
    "MISSING_FIELD",
    "AMBIGUOUS_FIX",
    "MANUAL_VALIDATION_REQUIRED",
})

ALLOWED_VALIDATION_CRITERION_TYPES = frozenset({
    "HTTP_STATUS",
    "MODULE_EXECUTION",
    "ERROR_ABSENCE",
    "OUTPUT_PRESENT",
    "FIELD_VALUE",
    "ROUTE_EXECUTION",
    "FILTER_RESULT",
    "SCENARIO_COMPLETION",
    "MANUAL_CONFIRMATION",
})


# ---------------------------------------------------------------------------
# DiagnosisReference — V1.1 contract exact
# ---------------------------------------------------------------------------

@dataclass
class DiagnosisReference:
    """
    Traceable reference to the diagnosis that drove this fix plan.
    Never states a hypothesis as a confirmed fact.
    Never re-diagnoses. Never recalculates.
    Fields exactly per V1.1 contract.
    """
    reasoning_status: str = ""
    diagnosis_status: str = ""
    hypothesis_id: str = ""
    confidence: str = "UNKNOWN"
    supporting_evidence: list[str] = field(default_factory=list)
    supporting_signals: list[str] = field(default_factory=list)
    supporting_kb_entries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# FixTarget — V1.1 contract exact
# ---------------------------------------------------------------------------

@dataclass
class FixTarget:
    """
    The specific element in the Make.com workflow that needs attention.
    Derived from Step 2 analysis (failure_location) and Step 4 hypothesis.

    V1.1 fields: module_id, module_name, app, action, target_type,
                 field_path, evidence_reference

    RULE: field_path must NEVER be invented.
          If the exact field is not in the structured input data: field_path = None
    RULE: target_type must NEVER be derived from KB ID.
          Must be derived from structural data only.
    """
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    app: Optional[str] = None
    action: Optional[str] = None
    target_type: str = "UNKNOWN"        # one of ALLOWED_TARGET_TYPES
    field_path: Optional[str] = None   # NEVER invented; None if unknown
    evidence_reference: Optional[str] = None  # traceable reference

    def __post_init__(self) -> None:
        if self.target_type not in ALLOWED_TARGET_TYPES:
            raise ValueError(
                f"Invalid target_type: {self.target_type!r}. "
                f"Allowed: {sorted(ALLOWED_TARGET_TYPES)}"
            )

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# FixAction — V1.1 contract exact
# ---------------------------------------------------------------------------

@dataclass
class FixAction:
    """
    One concrete, verifiable action in the fix plan.

    V1.1 fields: order, step, action_type, description, target,
                 current_state, proposed_change, rationale, source,
                 confidence, validation_required

    Rules:
      - action_type NEVER derived from keywords in description text
      - current_state ONLY contains observed facts from inputs
      - proposed_change ONLY contains concrete justified changes; else None
      - source traceable to actual pipeline data
      - No CORRECT, No TEST action types
    """
    order: int = 0                     # alias: same as step
    step: int = 0
    action_type: str = "INSPECT"       # one of ALLOWED_ACTION_TYPES
    description: str = ""
    target: Optional[str] = None       # plain text target description
    current_state: Optional[str] = None   # only observed facts
    proposed_change: Optional[str] = None # only justified changes; None if unknown
    rationale: str = ""
    source: str = ""                   # traceable source
    confidence: str = "UNKNOWN"        # one of ALLOWED_CONFIDENCE_LEVELS
    validation_required: bool = True

    def __post_init__(self) -> None:
        if self.action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(
                f"Invalid action_type: {self.action_type!r}. "
                f"Allowed: {sorted(ALLOWED_ACTION_TYPES)}"
            )
        # Sync order and step
        if self.order == 0 and self.step != 0:
            self.order = self.step
        elif self.step == 0 and self.order != 0:
            self.step = self.order

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# ExpectedOutcome — V1.1 contract exact
# ---------------------------------------------------------------------------

@dataclass
class ExpectedOutcome:
    """
    Observable, verifiable result the user should see after applying the fix.
    Must be phrased in terms of observable Make.com behaviour.

    V1.1 fields: description, expected_status, expected_behavior,
                 downstream_expectation

    RULE: expected_status must NOT be invented if not derivable from diagnosis.
    """
    description: str = ""
    expected_status: Optional[str] = None     # e.g. "200", or None if unknown
    expected_behavior: str = ""               # what to observe in Make.com
    downstream_expectation: Optional[str] = None  # what downstream modules should do

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# ValidationCriterion — V1.1 contract exact
# ---------------------------------------------------------------------------

@dataclass
class ValidationCriterion:
    """
    A concrete check the user can perform to verify the fix succeeded.

    V1.1 fields: criterion_type, description, expected_value, required
    V1.1 types:  HTTP_STATUS, MODULE_EXECUTION, ERROR_ABSENCE, OUTPUT_PRESENT,
                 FIELD_VALUE, ROUTE_EXECUTION, FILTER_RESULT, SCENARIO_COMPLETION,
                 MANUAL_CONFIRMATION
    """
    criterion_type: str = "MANUAL_CONFIRMATION"  # one of ALLOWED_VALIDATION_CRITERION_TYPES
    description: str = ""
    expected_value: Optional[str] = None
    required: bool = True
    action_step: Optional[int] = None

    def __post_init__(self) -> None:
        if self.criterion_type not in ALLOWED_VALIDATION_CRITERION_TYPES:
            raise ValueError(
                f"Invalid criterion_type: {self.criterion_type!r}. "
                f"Allowed: {sorted(ALLOWED_VALIDATION_CRITERION_TYPES)}"
            )

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# FixPlanResult — V1.1 contract exact
# ---------------------------------------------------------------------------

@dataclass
class FixPlanResult:
    """
    The complete fix plan for the user. V1.1 contract.

    V1.1 required fields:
      analysis_id, status, confidence, target, diagnosis_reference,
      actions, expected_outcome, validation_criteria,
      missing_information, risks, warnings

    This is a presentation of structured, traceable correction guidance.
    It does NOT modify the Blueprint, the KB, or any prior step output.
    It does NOT confirm the hypothesis — it presents it as a candidate.
    plan_id is deterministic (sha256-based), never uuid.uuid4().
    """
    # Traceability
    plan_id: str = ""           # deterministic: sha256(analysis_id)[:24]
    analysis_id: str = ""

    # Status — V1.1 values only
    status: str = "BLOCKED"    # one of ALLOWED_PLAN_STATUSES
    confidence: str = "UNKNOWN"  # carried from Step 4 hypothesis confidence

    # What the plan is based on
    diagnosis_reference: Optional[DiagnosisReference] = None

    # What needs to be fixed
    target: Optional[FixTarget] = None

    # The actions (ordered by step)
    actions: list[FixAction] = field(default_factory=list)

    # What success looks like
    expected_outcome: Optional[ExpectedOutcome] = None

    # How to verify the fix
    validation_criteria: list[ValidationCriterion] = field(default_factory=list)

    # Information that would improve the plan
    missing_information: list[str] = field(default_factory=list)

    # Risk assessment
    risks: list[str] = field(default_factory=list)

    # Warnings (categorized per V1.1)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_PLAN_STATUSES:
            raise ValueError(
                f"Invalid status: {self.status!r}. "
                f"Allowed: {sorted(ALLOWED_PLAN_STATUSES)}"
            )

    diagnostic_checks: list[DiagnosticCheck] = field(default_factory=list)
    documented_solutions: list[DocumentedSolution] = field(default_factory=list)
    documentation: list[DocumentationReference] = field(default_factory=list)
    guidance_markdown: str = ''

    correction_proposals: list[ManualCorrectionProposal] = field(default_factory=list)
    correction_gaps: list[str] = field(default_factory=list)
    correction_markdown: str = ''

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
