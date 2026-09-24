"""Validate proposal identity/current state; never recompute the S4 diagnosis."""
from __future__ import annotations
from copy import deepcopy
from flowfix.step1_intake.intake.field_contracts import observed_value, observation_digest, pointer
from flowfix.step4_reasoning.models_internal.corrections import ManualCorrectionProposal, validate_proposals
from flowfix.step9_fix_planning.models.models import FixAction, ValidationCriterion
from flowfix.step5_response.formatter.corrections import render_corrections


def prepare_correction(problem, analysis, reasoning, is_escalated):
    proposals = reasoning.correction_proposals
    if not proposals:
        return None, list(reasoning.correction_gaps)
    def reject(message):
        return None, ['Precise correction withheld: ' + message]
    if len(proposals) != 1 or not isinstance(proposals[0], ManualCorrectionProposal):
        return reject('exactly one supported proposal is required.')
    error = validate_proposals(proposals, problem.analysis_id)
    if error:
        return reject(error)
    p = proposals[0]
    obs = problem.execution_context.json_field_observation
    h = reasoning.leading_hypothesis
    if is_escalated or reasoning.reasoning_status != 'DIAGNOSIS_CANDIDATE' or h is None or h.contradicting_evidence:
        return reject('the current diagnostic status does not permit this modification.')
    if not obs or len({p.analysis_id, problem.analysis_id, reasoning.analysis_id, analysis.analysis_id}) != 1 or p.hypothesis_id != h.hypothesis_id:
        return reject('case or hypothesis identity does not match.')
    if not analysis.failure_location or analysis.failure_location.module_id != p.module_id or analysis.failure_location.confidence != 'high':
        return reject('the target module is no longer explicitly localized.')
    if p.module_id != obs.module_id or p.field_path != obs.field_path or p.observation_digest != observation_digest(problem, obs):
        return reject('the observed inputs have changed since S4.')
    if observed_value(problem, obs) != p.observed_value or obs.execution_value != p.observed_value:
        return reject('the observed field value has changed.')
    if p.action_type != 'UPDATE' or p.rule_id != 'static_json_single_trailing_comma_v1':
        return reject('unsupported proposal contract.')
    # Mechanical edit integrity, not a new diagnosis or JSON analysis.
    i = p.removed_character_index
    if type(i) is not int or not 0 <= i < len(p.observed_value) or p.observed_value[i] != ',' or p.proposed_value != p.observed_value[:i] + p.observed_value[i+1:]:
        return reject('the proposed edit is not the declared single-character deletion.')
    refs = {e.evidence_id for e in h.supporting_evidence if e.evidence_id}
    if len(p.evidence_ids) != 3 or not set(p.evidence_ids) <= refs or not p.preconditions or not p.validation_instruction or not p.limitation:
        return reject('proposal evidence or validation is incomplete.')
    p = deepcopy(p)
    action = FixAction(order=1, step=1, action_type=p.action_type,
        description='Manually remove the identified trailing comma from the static JSON field, after confirming the supplied field contract.',
        target='module:' + p.module_id + pointer(p.field_path), current_state=p.observed_value,
        proposed_change=p.proposed_value, rationale=p.limitation, source=p.proposal_id,
        confidence=reasoning.confidence.upper(), validation_required=True)
    criterion = ValidationCriterion('FIELD_VALUE', p.validation_instruction, p.proposed_value, True, 1)
    return (p, action, criterion, render_corrections([p])), []
