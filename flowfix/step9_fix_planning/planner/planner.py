"""
FlowFix — Step 9 Fix Planning — Planner V1.1

Transforms reasoning and workflow analysis outputs into a structured fix plan.

V1.1 Rules (hard):
  - No KB access. No LLM. No network. No new retrieval. No new reasoning.
  - No Blueprint modification.
  - No persistence.
  - No uuid.uuid4() or timestamp-based IDs — all IDs are deterministic hashes.
  - Hypotheses are NEVER promoted to confirmed facts.
  - All evidence is traceable to actual pipeline data.
  - Secrets ([REDACTED:*]) never surface in plan output.
  - Deterministic: same inputs → same FixPlanResult.
  - FORBIDDEN: KB ID → target_type mapping
  - FORBIDDEN: keyword analysis on description text → action_type
  - FORBIDDEN: auto-added TEST action
  - FORBIDDEN: invented field_path, current_state, proposed_change values
  - FORBIDDEN: PipelineDecision is OPTIONAL (Step 8 not required)

Plan generation strategy (V1.1):
  1. Build DiagnosisReference from Step 4 ReasoningResult.
  2. Build FixTarget from Step 2 WorkflowAnalysis structural data only
     (failure_location → module_id, module_name, app, action).
     target_type derived from GraphNode structural flags, NOT from KB IDs.
  3. Determine plan status from reasoning_status.
  4. Build FixActions using explicit structural rules, NOT keyword search.
  5. Build ExpectedOutcome without inventing expected_status.
  6. Build ValidationCriteria using V1.1 criterion types.
"""

from __future__ import annotations
import hashlib
from typing import Optional

from flowfix.step1_intake.intake.models import NormalizedProblem
from flowfix.step2_analysis.models import WorkflowAnalysis, GraphNode
from flowfix.step4_reasoning.models_internal.models import ReasoningResult
from flowfix.step5_response.models_internal.models import ResponseResult

from flowfix.step9_fix_planning.models.models import (
    FixPlanResult,
    FixTarget,
    DiagnosisReference,
    FixAction,
    ExpectedOutcome,
    ValidationCriterion,
    ALLOWED_TARGET_TYPES,
    ALLOWED_PLAN_STATUSES,
    ALLOWED_ACTION_TYPES,
    ALLOWED_CONFIDENCE_LEVELS,
)


# ---------------------------------------------------------------------------
# Optional import — PipelineDecision is OPTIONAL per V1.1 contract
# ---------------------------------------------------------------------------

try:
    from flowfix.step8_orchestrator.models_internal.models import PipelineDecision
    _HAS_PIPELINE_DECISION = True
except ImportError:
    PipelineDecision = None  # type: ignore[misc,assignment]
    _HAS_PIPELINE_DECISION = False


# ---------------------------------------------------------------------------
# Deterministic ID generation — no randomness, no uuid.uuid4()
# ---------------------------------------------------------------------------

def _plan_id(analysis_id: str) -> str:
    return hashlib.sha256(f"fixplan:{analysis_id}".encode()).hexdigest()[:24]


def _action_id(plan_id: str, step: int) -> str:
    return hashlib.sha256(f"{plan_id}:action:{step}".encode()).hexdigest()[:16]


def _criterion_id(plan_id: str, index: int) -> str:
    return hashlib.sha256(f"{plan_id}:criterion:{index}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Secret guard
# ---------------------------------------------------------------------------

def _is_redacted(v: Optional[str]) -> bool:
    return isinstance(v, str) and "[REDACTED:" in v


def _safe(v: Optional[str], fallback: str = "") -> str:
    if not v or _is_redacted(v):
        return fallback
    return v.strip()


# ---------------------------------------------------------------------------
# Target type derivation — STRUCTURAL ONLY, NEVER from KB IDs
#
# RULE: KB ID → target_type is ABSOLUTELY FORBIDDEN.
# The target_type is derived EXCLUSIVELY from structural data in WorkflowAnalysis
# (GraphNode flags, FailureLocation data, observed facts).
# ---------------------------------------------------------------------------

def _derive_target_type_from_structure(
    analysis: WorkflowAnalysis,
    failing_module_id: Optional[str],
) -> str:
    """
    Derive target_type from WorkflowAnalysis structural data only.

    Uses GraphNode flags (is_router, is_iterator, is_aggregator, is_webhook,
    is_http, is_error_handler) and FailureLocation data.
    NEVER uses KB entry IDs or hypothesis source strings.
    """
    if not failing_module_id:
        return "UNKNOWN"

    # Find the failing node in the workflow graph
    failing_node: Optional[GraphNode] = None
    for node in analysis.workflow.nodes:
        if node.module_id and str(node.module_id) == str(failing_module_id):
            failing_node = node
            break

    if failing_node is None:
        return "UNKNOWN"

    # Derive from structural flags — explicit structural classification
    if failing_node.is_router:
        return "ROUTER"
    if failing_node.is_iterator:
        return "ITERATOR"
    if failing_node.is_aggregator:
        return "AGGREGATOR"
    if failing_node.is_webhook:
        return "WEBHOOK"
    if failing_node.is_error_handler:
        return "ERROR_HANDLER"
    if failing_node.is_http:
        return "HTTP_CONFIGURATION"

    # Non-special module: classify as MODULE
    return "MODULE"


# ---------------------------------------------------------------------------
# DiagnosisReference — V1.1 contract
# ---------------------------------------------------------------------------

def _build_diagnosis_reference(
    reasoning: ReasoningResult,
) -> DiagnosisReference:
    """
    Build DiagnosisReference from ReasoningResult.
    V1.1 fields: reasoning_status, diagnosis_status, hypothesis_id,
                 confidence, supporting_evidence, supporting_signals,
                 supporting_kb_entries
    Does NOT re-diagnose. Does NOT re-score.
    """
    lh = reasoning.leading_hypothesis

    if not lh:
        return DiagnosisReference(
            reasoning_status=reasoning.reasoning_status,
            diagnosis_status="NO_HYPOTHESIS",
            hypothesis_id="",
            confidence="UNKNOWN",
            supporting_evidence=[],
            supporting_signals=list(reasoning.signals or []),
            supporting_kb_entries=[],
        )

    # Extract supporting evidence descriptions (plain strings, no secrets)
    evidence_descriptions = []
    for ev in (lh.supporting_evidence or []):
        desc = _safe(getattr(ev, "description", ""), "")
        if desc:
            evidence_descriptions.append(desc)

    return DiagnosisReference(
        reasoning_status=reasoning.reasoning_status,
        diagnosis_status=lh.status if lh.status else "candidate",
        hypothesis_id=_safe(lh.hypothesis_id, ""),
        confidence=(lh.confidence.upper() if lh.confidence else "UNKNOWN"),
        supporting_evidence=evidence_descriptions,
        supporting_signals=list(lh.supporting_signals or []),
        supporting_kb_entries=list(lh.supporting_kb_entries or []),
    )


# ---------------------------------------------------------------------------
# FixTarget — V1.1 contract
# RULE: target_type NEVER derived from KB IDs
# RULE: field_path NEVER invented
# ---------------------------------------------------------------------------

def _build_fix_target(
    reasoning: ReasoningResult,
    analysis: WorkflowAnalysis,
    problem: NormalizedProblem,
) -> Optional[FixTarget]:
    """
    Build FixTarget from structural data only.
    No KB ID → target_type mapping.
    No invented field_path.
    """
    # Module from Step 2 failure_location (primary structural source)
    fl = analysis.failure_location
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    app: Optional[str] = None
    action: Optional[str] = None

    if fl:
        module_id = _safe(fl.module_id) or None
        module_name = _safe(fl.module_name) or None
        app = _safe(fl.app) if hasattr(fl, "app") else None

    # Also check execution context if failure_location is sparse
    if not module_id and problem.execution_context.failing_module_id:
        module_id = _safe(problem.execution_context.failing_module_id)
    if not module_name and problem.execution_context.failing_module_name:
        module_name = _safe(problem.execution_context.failing_module_name)

    # Try to find app/action from GraphNode if available
    if module_id:
        for node in analysis.workflow.nodes:
            if node.module_id and str(node.module_id) == str(module_id):
                if not app and node.app:
                    app = _safe(node.app) or None
                if node.action:
                    action = _safe(node.action) or None
                break

    # Derive target_type from structural data ONLY (never from KB IDs)
    target_type = _derive_target_type_from_structure(analysis, module_id)

    # evidence_reference: traceable reference to what we used
    evidence_ref = None
    if fl and fl.source:
        evidence_ref = f"failure_location:{fl.source}"
    elif module_id:
        evidence_ref = "execution_context"

    # field_path: NEVER invented — only set if structurally present
    # No field path is known from structural data at this level
    field_path = None

    return FixTarget(
        module_id=module_id,
        module_name=module_name,
        app=app,
        action=action,
        target_type=target_type,
        field_path=field_path,   # always None — never invented
        evidence_reference=evidence_ref,
    )


# ---------------------------------------------------------------------------
# Plan status derivation — V1.1 statuses ONLY
# ---------------------------------------------------------------------------

def _derive_plan_status(
    reasoning: ReasoningResult,
    is_escalated: bool,
    actions: list[FixAction],
) -> str:
    """
    Derive plan status from reasoning_status.
    V1.1 statuses: READY, PARTIALLY_READY, BLOCKED, NOT_APPLICABLE

    Mapping:
      INSUFFICIENT_EVIDENCE → BLOCKED
      CONTRADICTED          → BLOCKED (may be PARTIALLY_READY for safe verifications)
      MULTIPLE_CANDIDATES   → PARTIALLY_READY
      WEAK_EVIDENCE         → PARTIALLY_READY
      DIAGNOSIS_CANDIDATE   → READY (if sufficient actions) or PARTIALLY_READY
      ESCALATE signal       → BLOCKED
    """
    if is_escalated:
        return "BLOCKED"

    rs = reasoning.reasoning_status

    if rs == "INSUFFICIENT_EVIDENCE":
        return "BLOCKED"

    if rs == "CONTRADICTED":
        # Only PARTIALLY_READY if all actions are safe verifications (INSPECT/VERIFY)
        if actions and all(a.action_type in ("INSPECT", "VERIFY") for a in actions):
            return "PARTIALLY_READY"
        return "BLOCKED"

    if rs == "MULTIPLE_CANDIDATES":
        return "PARTIALLY_READY"

    if rs == "WEAK_EVIDENCE":
        return "PARTIALLY_READY"

    if rs == "DIAGNOSIS_CANDIDATE":
        if actions:
            return "READY"
        return "PARTIALLY_READY"

    # Unknown reasoning status
    if not actions:
        return "BLOCKED"
    return "PARTIALLY_READY"


# ---------------------------------------------------------------------------
# FixActions — V1.1 contract
#
# RULES:
#   - action_type NEVER derived from keywords in description text
#   - current_state: only observed facts from inputs
#   - proposed_change: only justified concrete changes; None otherwise
#   - No automatic TEST action added
#   - Modification actions (UPDATE, REPLACE, REMOVE, ADD, RECONNECT, RECONFIGURE)
#     only when sufficiently supported by structural data
#   - Default to INSPECT/VERIFY when evidence is insufficient
# ---------------------------------------------------------------------------

def _action_type_from_reasoning_status(reasoning_status: str) -> str:
    """
    Determine base action type from reasoning_status (structural rule, not keyword).
    DIAGNOSIS_CANDIDATE → VERIFY (verify before modifying)
    MULTIPLE_CANDIDATES → VERIFY (verify to distinguish candidates)
    WEAK_EVIDENCE       → INSPECT (inspect before any action)
    INSUFFICIENT_EVIDENCE → INSPECT (inspect to gather evidence)
    CONTRADICTED        → INSPECT (inspect to resolve contradiction)
    """
    if reasoning_status == "DIAGNOSIS_CANDIDATE":
        return "VERIFY"
    if reasoning_status == "MULTIPLE_CANDIDATES":
        return "VERIFY"
    return "INSPECT"


def _current_state_from_signals(reasoning: ReasoningResult) -> Optional[str]:
    """
    Build current_state from observed facts only.
    Never invents values.
    """
    observed = []
    # HTTP error codes are observable facts
    if reasoning.facts:
        observed.extend(f for f in reasoning.facts if f)
    if observed:
        return "; ".join(observed[:3])  # limit to first 3 facts
    return None


def _build_actions_from_response(
    plan_id: str,
    response: ResponseResult,
    reasoning: ReasoningResult,
) -> list[FixAction]:
    """
    Build actions from Step 5 ResponseResult (primary source).
    action_type is determined by STRUCTURAL RULE based on reasoning_status,
    NOT by keyword search in description text.
    """
    actions: list[FixAction] = []
    step_num = 1

    # Base action type from reasoning status (structural rule)
    base_action_type = _action_type_from_reasoning_status(reasoning.reasoning_status)

    # current_state from observed facts only (never invented)
    current_state = _current_state_from_signals(reasoning)

    lh = reasoning.leading_hypothesis
    lh_id = lh.hypothesis_id if lh else ""

    for ra in sorted(response.recommended_actions or [], key=lambda a: a.step):
        if getattr(ra, 'purpose', '') == 'manual_correction':
            continue  # Only the dedicated proposal gate may emit this action.
        desc = _safe(ra.description)
        if getattr(ra, "purpose", "verification") == "documented_solution":
            desc = "Assess the preconditions of this documented option before any manual change: " + desc
        else:
            desc = "Collect evidence for this documented check; do not apply changes based on this text alone: " + desc
        if not desc:
            continue

        # action_type from structural rule ONLY — never from keyword in desc
        atype = base_action_type

        # source traceable to pipeline data
        source = _safe(ra.source, "")
        if not source:
            source = "step5_response"

        # proposed_change: only set when action is a modification type
        # For VERIFY/INSPECT: proposed_change is None (we don't know yet)
        proposed_change = None

        # rationale: from hypothesis id (traceable reference)
        rationale = ""
        if lh_id:
            rationale = f"Based on hypothesis candidate {lh_id} from Step 4 reasoning."
        elif lh:
            rationale = "Based on leading hypothesis from Step 4 reasoning."

        actions.append(FixAction(
            order=step_num,
            step=step_num,
            action_type=atype,
            description=desc,
            target=None,       # target described at FixTarget level
            current_state=current_state,
            proposed_change=proposed_change,
            rationale=rationale,
            source=source,
            confidence=reasoning.confidence.upper() if reasoning.confidence else "UNKNOWN",
            validation_required=True,
        ))
        step_num += 1

    return actions


def _build_actions_for_multiple_candidates(
    plan_id: str,
    reasoning: ReasoningResult,
) -> list[FixAction]:
    """
    For MULTIPLE_CANDIDATES: generate VERIFY actions for each candidate.
    Never choose a candidate automatically.
    Never generate destructive/irreversible actions.
    """
    actions: list[FixAction] = []
    step_num = 1

    lh = reasoning.leading_hypothesis
    current_state = _current_state_from_signals(reasoning)

    for hyp in reasoning.ranked_hypotheses[:3]:  # top 3 candidates max
        hyp_id = _safe(hyp.hypothesis_id, f"H{step_num}")
        stmt = _safe(hyp.statement, "Unknown candidate")[:80]
        # Truncate for description
        check = next((c for c in hyp.documented_checks if c and not _is_redacted(c)), None)
        gap = next((g for g in hyp.missing_information if g and not _is_redacted(g)), None)
        desc = f"Verify whether candidate {hyp_id} applies: {stmt}. "
        if gap:
            desc += "Missing observation: " + gap + ". "
        if check:
            desc += "Documented check to assess, without applying changes: " + check + ". "
        desc += "Use the existing failed execution details; share the anonymized relevant input and error excerpt. Record whether it supports, contradicts, or leaves this candidate unresolved."

        actions.append(FixAction(
            order=step_num,
            step=step_num,
            action_type="VERIFY",   # structural rule: MULTIPLE_CANDIDATES → VERIFY
            description=desc,
            target=None,
            current_state=current_state,
            proposed_change=None,   # never choose automatically
            rationale=(
                f"Multiple diagnosis candidates present. Candidate {hyp_id} must be "
                "verified before any corrective action is taken."
            ),
            source="reasoning_result",
            confidence=hyp.confidence.upper() if hyp.confidence else "UNKNOWN",
            validation_required=True,
        ))
        step_num += 1

    # If no ranked hypotheses, generate a generic INSPECT action
    if not actions:
        if lh:
            stmt = _safe(lh.statement, "")[:80]
            desc = f"Inspect the workflow to verify the applicable diagnosis: {stmt}"
        else:
            desc = "Inspect the workflow to identify which diagnostic candidate applies."
        actions.append(FixAction(
            order=1,
            step=1,
            action_type="INSPECT",
            description=desc,
            target=None,
            current_state=current_state,
            proposed_change=None,
            rationale="Multiple candidates present. Inspection required before any fix.",
            source="reasoning_result",
            confidence="UNKNOWN",
            validation_required=True,
        ))

    return actions


def _build_actions_for_blocked(
    plan_id: str,
    reasoning: ReasoningResult,
    problem: NormalizedProblem,
) -> list[FixAction]:
    """
    For BLOCKED status (INSUFFICIENT_EVIDENCE or CONTRADICTED):
    Generate only safe, non-destructive INSPECT actions.
    """
    current_state = _current_state_from_signals(reasoning)

    missing = list(reasoning.unknowns or [])
    if not missing:
        missing = list(problem.missing_information if hasattr(problem, "missing_information") else [])

    if missing:
        desc = f"Inspect the workflow to gather missing information: {'; '.join(missing[:2])}"
    else:
        desc = "Inspect the workflow to gather sufficient evidence for diagnosis."

    return [FixAction(
        order=1,
        step=1,
        action_type="INSPECT",
        description=desc,
        target=None,
        current_state=current_state,
        proposed_change=None,
        rationale=(
            f"Evidence is insufficient for corrective action "
            f"(reasoning_status={reasoning.reasoning_status}). "
            "Inspection required to gather additional information."
        ),
        source="reasoning_result",
        confidence="UNKNOWN",
        validation_required=True,
    )]


def _build_actions(
    plan_id: str,
    response: Optional[ResponseResult],
    reasoning: ReasoningResult,
    problem: NormalizedProblem,
    plan_status: str,
) -> list[FixAction]:
    """
    Main action builder. Routes to appropriate strategy based on plan_status.
    """
    if plan_status == "BLOCKED":
        return _build_actions_for_blocked(plan_id, reasoning, problem)

    if reasoning.reasoning_status == "MULTIPLE_CANDIDATES":
        # For multiple candidates: use VERIFY per candidate
        # But also supplement with step5 actions if available and non-modification
        actions = _build_actions_for_multiple_candidates(plan_id, reasoning)
        return actions

    # READY or PARTIALLY_READY with response available
    if response and response.recommended_actions:
        actions = _build_actions_from_response(plan_id, response, reasoning)
        if actions:
            return actions

    # Fallback: generate INSPECT based on available context
    current_state = _current_state_from_signals(reasoning)
    lh = reasoning.leading_hypothesis

    if lh:
        stmt = _safe(lh.statement, "")[:80]
        desc = f"Inspect the workflow for evidence related to: {stmt}"
    else:
        desc = "Inspect the workflow to determine the root cause."

    return [FixAction(
        order=1,
        step=1,
        action_type="INSPECT",
        description=desc,
        target=None,
        current_state=current_state,
        proposed_change=None,
        rationale="Inspection required to verify the diagnosis candidate before any fix.",
        source="reasoning_result",
        confidence=reasoning.confidence.upper() if reasoning.confidence else "UNKNOWN",
        validation_required=True,
    )]


# ---------------------------------------------------------------------------
# ExpectedOutcome — V1.1 contract
# RULE: expected_status must NOT be invented
# ---------------------------------------------------------------------------

def _build_expected_outcome(
    reasoning: ReasoningResult,
    problem: NormalizedProblem,
) -> ExpectedOutcome:
    """
    Build ExpectedOutcome without inventing expected_status.
    expected_status is only set if directly observable from the input data
    (e.g. HTTP status codes present in execution context).
    """
    return ExpectedOutcome(
        description="Evidence collected for the current diagnosis candidate; resolution remains unverified.",
        expected_status=None,
        expected_behavior="Record the observed result of each inspection and any remaining uncertainty.",
        downstream_expectation=None,
    )


# ---------------------------------------------------------------------------
# ValidationCriteria — V1.1 contract
# ---------------------------------------------------------------------------

def _build_validation_criteria(
    plan_id: str,
    reasoning: ReasoningResult,
    problem: NormalizedProblem,
    plan_status: str,
) -> list[ValidationCriterion]:
    """
    Build validation criteria using V1.1 criterion types.
    """
    return [ValidationCriterion(criterion_type="MANUAL_CONFIRMATION",
        description="Record the requested anonymized evidence and whether it supports or contradicts the candidate. No scenario run is required for inspection.",
        expected_value=None, required=True)]


# ---------------------------------------------------------------------------
# Warnings — V1.1 categories
# ---------------------------------------------------------------------------

def _build_warnings(
    reasoning: ReasoningResult,
    response: Optional[ResponseResult],
    plan_status: str,
) -> list[str]:
    """
    Build warnings using V1.1 categories.
    """
    warnings = []

    if reasoning.reasoning_status in ("WEAK_EVIDENCE", "INSUFFICIENT_EVIDENCE"):
        warnings.append("LOW_CONFIDENCE")

    if reasoning.reasoning_status in ("WEAK_EVIDENCE",):
        warnings.append("PARTIAL_EVIDENCE")

    if reasoning.reasoning_status == "MULTIPLE_CANDIDATES":
        warnings.append("AMBIGUOUS_FIX")

    lh = reasoning.leading_hypothesis
    if lh is None:
        warnings.append("MISSING_TARGET")

    if plan_status in ("READY", "PARTIALLY_READY"):
        warnings.append("MANUAL_VALIDATION_REQUIRED")

    if response and response.missing_information:
        warnings.append("PARTIAL_EVIDENCE")

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            deduped.append(w)

    return deduped


# ---------------------------------------------------------------------------
# Missing information
# ---------------------------------------------------------------------------

def _build_missing_information(
    reasoning: ReasoningResult,
    response: Optional[ResponseResult],
) -> list[str]:
    """
    Collect missing information from Step 4 and Step 5 outputs.
    Never invents items.
    """
    missing = []

    lh = reasoning.leading_hypothesis
    if lh and lh.missing_information:
        missing.extend(lh.missing_information)

    if reasoning.unknowns:
        missing.extend(reasoning.unknowns)

    if response and response.missing_information:
        missing.extend(response.missing_information)

    # Deduplicate
    seen = set()
    deduped = []
    for m in missing:
        if m and m not in seen:
            seen.add(m)
            deduped.append(m)

    return deduped


# ---------------------------------------------------------------------------
# Risk assessment
# ---------------------------------------------------------------------------

def _build_risks(
    reasoning: ReasoningResult,
    plan_status: str,
) -> list[str]:
    """
    Build risk assessment. Never minimizes risk artificially.
    """
    risks = []

    if reasoning.reasoning_status == "CONTRADICTED":
        risks.append("HIGH")
    elif reasoning.reasoning_status in ("WEAK_EVIDENCE", "INSUFFICIENT_EVIDENCE"):
        risks.append("MEDIUM")
    elif reasoning.reasoning_status == "MULTIPLE_CANDIDATES":
        risks.append("MEDIUM")
    elif plan_status == "READY":
        risks.append("UNKNOWN")
    else:
        risks.append("UNKNOWN")

    return risks


# ---------------------------------------------------------------------------
# Main planner — V1.1
# ---------------------------------------------------------------------------

def plan(
    problem: NormalizedProblem,
    analysis: WorkflowAnalysis,
    reasoning: ReasoningResult,
    response: Optional[ResponseResult] = None,
    decision: Optional[object] = None,  # PipelineDecision — OPTIONAL per V1.1
) -> FixPlanResult:
    """
    Generate a FixPlanResult from prior step outputs.

    Parameters
    ----------
    problem   : NormalizedProblem   — Step 1 output (read-only)
    analysis  : WorkflowAnalysis    — Step 2 output (read-only)
    reasoning : ReasoningResult     — Step 4 output (read-only)
    response  : ResponseResult      — Step 5 output (read-only, OPTIONAL)
    decision  : PipelineDecision    — Step 8 output (OPTIONAL per V1.1)

    Returns
    -------
    FixPlanResult — deterministic, no KB access, no Blueprint modification.
    """
    pid = _plan_id(reasoning.analysis_id)

    # Detect escalation from decision (optional)
    is_escalated = False
    if decision is not None:
        decision_action = getattr(decision, "action", None)
        is_escalated = (decision_action == "ESCALATE")

    # Confidence from hypothesis (uppercase for consistency)
    lh = reasoning.leading_hypothesis
    if lh and lh.confidence:
        confidence = lh.confidence.upper()
    else:
        confidence = "UNKNOWN"

    # Build diagnosis reference (never re-diagnoses)
    diagnosis_reference = _build_diagnosis_reference(reasoning)

    # Build fix target (structural data only, no KB ID mapping)
    fix_target = _build_fix_target(reasoning, analysis, problem)

    # Derive plan status BEFORE building actions
    # (actions for BLOCKED status are INSPECT only)
    # We do a preliminary status determination to guide action building
    preliminary_actions: list[FixAction] = []
    plan_status = _derive_plan_status(reasoning, is_escalated, preliminary_actions)

    # Build actions based on plan status
    actions = _build_actions(pid, response, reasoning, problem, plan_status)

    # Attach only observed module identity; no invented field selection.
    if analysis.failure_location and analysis.failure_location.module_id:
        for action in actions:
            action.target = "module:" + analysis.failure_location.module_id

    # Re-derive plan status now that we have actions
    plan_status = _derive_plan_status(reasoning, is_escalated, actions)

    # Build expected outcome (no invented expected_status)
    expected_outcome = _build_expected_outcome(reasoning, problem)

    # Build validation criteria (V1.1 types)
    validation_criteria = _build_validation_criteria(pid, reasoning, problem, plan_status)

    validation_criteria = [ValidationCriterion(criterion_type="MANUAL_CONFIRMATION",
        description=f"Action {a.step}: record the requested observation, its source, and whether the candidate is supported, contradicted or unresolved.",
        expected_value=None, required=True, action_step=a.step) for a in actions]

    # Build warnings (V1.1 categories)
    warnings = _build_warnings(reasoning, response, plan_status)

    # Collect missing information
    missing_information = _build_missing_information(reasoning, response)

    missing_information.append("No structured case-specific correction was supplied: the exact observed field, justified target value and verified preconditions are required before proposing a change.")

    # Risk assessment
    risks = _build_risks(reasoning, plan_status)

    from .guidance import transfer_guidance
    checks, options, documents, guidance_text, omissions = transfer_guidance(response, reasoning, plan_status, fix_target)
    warnings.extend(omissions)

    from .corrections import prepare_correction
    from flowfix.step1_intake.intake.field_contracts import pointer
    prepared, correction_gaps = prepare_correction(problem, analysis, reasoning, is_escalated)
    correction_proposals = []
    correction_markdown = ''
    if prepared:
        proposal, action, criterion, correction_markdown = prepared
        correction_proposals = [proposal]
        actions = [action]
        validation_criteria = [criterion]
        fix_target.module_id = proposal.module_id
        fix_target.field_path = pointer(proposal.field_path)
        fix_target.target_type = 'FIELD'
        fix_target.evidence_reference = proposal.proposal_id
        plan_status = 'READY'
        risks = ['UNKNOWN']
        missing_information = [m for m in missing_information if not m.startswith('No structured case-specific correction')]
        expected_outcome = ExpectedOutcome(description='The specified field should contain syntactically valid JSON after the manual edit.',
            expected_behavior='Only local JSON syntax is covered; schema compliance and scenario resolution remain unverified.')
    else:
        missing_information.extend(correction_gaps)

    return FixPlanResult(
        correction_proposals=correction_proposals,
        correction_gaps=correction_gaps,
        correction_markdown=correction_markdown,
        diagnostic_checks=checks,
        documented_solutions=options,
        documentation=documents,
        guidance_markdown=guidance_text,
        plan_id=pid,
        analysis_id=reasoning.analysis_id,
        status=plan_status,
        confidence=confidence,
        diagnosis_reference=diagnosis_reference,
        target=fix_target,
        actions=actions,
        expected_outcome=expected_outcome,
        validation_criteria=validation_criteria,
        missing_information=missing_information,
        risks=risks,
        warnings=warnings,
    )
