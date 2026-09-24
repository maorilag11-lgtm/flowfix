"""A bounded proposal from S4, distinct from a documentary option."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ManualCorrectionProposal:
    proposal_id: str = ''
    analysis_id: str = ''
    hypothesis_id: str = ''
    rule_id: str = ''
    module_id: str = ''
    field_path: list[str] = field(default_factory=list)
    observed_value: str = ''
    proposed_value: str = ''
    removed_character_index: int = -1
    observation_digest: str = ''
    preconditions: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    limitation: str = ''
    validation_instruction: str = ''
    action_type: str = 'UPDATE'


def validate_proposals(proposals, analysis_id):
    """Check the additive proposal contract; no JSON diagnostic is run here."""
    from flowfix.step1_intake.redaction.redactor import redact
    if not isinstance(proposals, list) or len(proposals) > 1:
        return 'At most one local JSON correction is supported.'
    for p in proposals:
        if not isinstance(p, ManualCorrectionProposal):
            return 'Unsupported correction proposal.'
        if p.analysis_id != analysis_id or p.action_type != 'UPDATE' or p.rule_id != 'static_json_single_trailing_comma_v1':
            return 'Correction identity or operation mismatch.'
        groups = [p.field_path, p.preconditions, p.evidence_ids]
        if any(not isinstance(group, list) or not group for group in groups):
            return 'Correction references and preconditions are required.'
        if not 2 <= len(p.field_path) <= 6 or p.field_path[0] not in ('mapper', 'parameters') or len(p.evidence_ids) != 3:
            return 'Unsupported correction target or evidence contract.'
        text = [p.proposal_id, p.analysis_id, p.hypothesis_id, p.module_id,
                p.observed_value, p.proposed_value, p.observation_digest,
                p.validation_instruction, p.limitation] + p.field_path + p.preconditions + p.evidence_ids
        if any(not isinstance(v,str) or not v or len(v)>10000 or '[REDACTED:' in v or redact(v).redactions for v in text):
            return 'Incomplete or sensitive correction content.'
        i = p.removed_character_index
        if type(i) is not int or not 0 <= i < len(p.observed_value) or p.observed_value[i] != ',' or p.proposed_value != p.observed_value[:i]+p.observed_value[i+1:]:
            return 'Correction must be exactly the declared comma deletion.'
    return None
