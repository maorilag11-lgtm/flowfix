"""One local rule: remove one trailing comma from explicitly static JSON.

No guess about Make field names, schemas or mappings. The supplied requirement
and link to execution remain declarations. The syntax defect is checked locally.
No new value, key, mapping expression or endpoint is generated.
"""
from __future__ import annotations
import json
import hashlib
from flowfix.step1_intake.intake.field_contracts import observed_value, observation_digest, pointer
from flowfix.step4_reasoning.models_internal.models import Evidence, ReasonedHypothesis
from flowfix.step4_reasoning.models_internal.corrections import ManualCorrectionProposal

RULE = 'static_json_single_trailing_comma_v1'


def _strict_loads(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('Duplicate object keys are outside this rule.')
            result[key] = item
        return result
    def constant(_):
        raise ValueError('Nonstandard JSON constant.')
    return json.loads(value, object_pairs_hook=pairs, parse_constant=constant, parse_float=lambda token:token)


def _bounded_depth(value, maximum=100):
    """Reject deep containers before parsing, independently of Python's recursion limit."""
    depth = 0
    inside = escaped = False
    for char in value:
        if inside:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                inside = False
        elif char == '"':
            inside = True
        elif char in '[{':
            depth += 1
            if depth > maximum:
                return False
        elif char in ']}':
            depth -= 1
    return True


def corrected_json(value):
    """Return (corrected text, removed offset) or None. Never alter string data."""
    if not isinstance(value, str) or len(value) > 10000 or '{{' in value or '[REDACTED:' in value or not _bounded_depth(value):
        return None
    try:
        _strict_loads(value)
        return None  # Already valid: no edit.
    except json.JSONDecodeError:
        pass
    except (ValueError, RecursionError):
        return None
    inside = False
    escaped = False
    positions = []
    for i, char in enumerate(value):
        if inside:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                inside = False
            continue
        if char == '"':
            inside = True
        elif char == ',':
            right = value[i+1:].lstrip(' \t\r\n')
            left = value[:i].rstrip(' \t\r\n')
            if right and right[0] in ']}' and left and left[-1] not in '[{,:':
                positions.append(i)
    if inside or len(positions) != 1:
        return None
    pos = positions[0]
    fixed = value[:pos] + value[pos+1:]
    try:
        _strict_loads(fixed)
    except (ValueError, RecursionError):
        return None
    return fixed, pos


def add_json_correction(result, problem, analysis, retrieval):
    """Integrate a locally proven syntax defect inside S4's diagnostic decision."""
    obs = problem.execution_context.json_field_observation
    if obs is None:
        return
    def abstain(message):
        result.correction_gaps.append(message)
    if not retrieval.ready_for_step4:
        return abstain('Retrieval integrity must be valid before proposing a correction.')
    if len({problem.analysis_id, analysis.analysis_id, retrieval.analysis_id, result.analysis_id}) != 1:
        return abstain('Inputs belong to different analysis sessions.')
    fl = analysis.failure_location
    if not fl or fl.module_id != obs.module_id or fl.confidence != 'high':
        return abstain('The failing module must be explicit and consistent with the field observation.')
    if obs.expected_format != 'json' or obs.value_origin != 'static' or obs.error_kind != 'JSON_SYNTAX':
        return abstain('This rule requires an explicit static JSON requirement and a declared JSON syntax error.')
    if result.reasoning_status == 'CONTRADICTED' or result.contradicting_evidence or problem.errors.http_status_codes or problem.execution_context.http.status:
        return abstain('Contradictory or HTTP evidence is outside the local JSON syntax case.')
    if problem.blueprint.parse_warnings:
        return abstain('Resolve incomplete, redacted or malformed blueprint data first.')
    value = observed_value(problem, obs)
    if value != obs.execution_value:
        return abstain('The static blueprint value and the supplied execution value must match exactly.')
    change = corrected_json(value)
    if change is None:
        return abstain('No unique single trailing-comma correction is demonstrated.')
    fixed, offset = change
    digest = observation_digest(problem, obs)
    if digest is None:
        return abstain('The normalized inputs cannot be bound to a stable strict JSON snapshot.')
    ident = hashlib.sha256((RULE + digest).encode()).hexdigest()[:20]
    hid = 'H_LOCAL_JSON_' + ident
    declarations = [
        Evidence('execution_context', 'user_reported',
            'The caller declares this exact field to require static JSON. Source: ' + obs.format_source,
            pointer(obs.field_path), 'declaration', 'E_FORMAT_' + ident),
        Evidence('execution_context', 'user_reported',
            'The supplied failed execution value equals the static blueprint value. Error source: ' + obs.error_source,
            obs.module_id, 'declaration', 'E_EXECUTION_' + ident),
        Evidence('local_json_validation', 'syntax_check',
            'Strict local parsing fails before the edit and succeeds after deleting exactly one trailing comma outside strings. Duplicate keys and nonstandard constants are refused.',
            pointer(obs.field_path), 'observation', 'E_SYNTAX_' + ident),
    ]
    limitation = 'The syntax correction is locally verified against the supplied field contract. The contract and execution provenance are caller declarations; no real Make execution or API schema has been independently verified.'
    hyp = ReasonedHypothesis(hid,
        'A trailing comma makes the explicitly identified static JSON field syntactically invalid.',
        'derived:local_json_validation', supporting_evidence=declarations,
        score=1.0, confidence='medium', status='leading')
    # Direct local syntax evidence is the priority here, not a KB relevance score.
    if result.leading_hypothesis:
        result.leading_hypothesis.status = 'candidate'
    result.hypotheses.append(hyp)
    result.ranked_hypotheses.insert(0, hyp)
    result.leading_hypothesis = hyp
    result.reasoning_status = 'DIAGNOSIS_CANDIDATE'
    result.confidence = 'medium'
    result.confidence_reasons = ['Direct local syntax evidence takes priority over documentary relevance. The score is not a calibrated probability.', 'Local syntax failure reproduced and a unique minimal edit validated.', limitation]
    result.supporting_evidence.extend(declarations)
    result.correction_proposals.append(ManualCorrectionProposal(
        proposal_id='CORRECTION_' + ident, analysis_id=problem.analysis_id,
        hypothesis_id=hid, rule_id=RULE, module_id=obs.module_id,
        field_path=list(obs.field_path), observed_value=value, proposed_value=fixed,
        removed_character_index=offset, observation_digest=digest,
        preconditions=['Explicit failing module matches the unique blueprint module.',
            'The caller-supplied contract identifies this exact field as static JSON.',
            'The supplied execution value equals the current static field.',
            'One comma deletion outside strings makes strict JSON parsing succeed.'],
        evidence_ids=[e.evidence_id for e in declarations], limitation=limitation,
        validation_instruction='After the manual edit, compare this field with the proposed text and validate its JSON syntax locally. This establishes syntax only; schema compliance and scenario resolution remain unverified. No scenario rerun is required.',
    ))
