"""Evidence-bound comparisons over S1 observations and S2 literal dependencies. No KB."""
from dataclasses import dataclass,field,asdict
from flowfix.step2_analysis.analyzer.trace_dependencies import BoundaryObservation,upstream_paths

@dataclass
class RootCauseTrace:
    analysis_id: str
    schema_version: str = 'root-cause-trace/1'
    status: str = 'NOT_ESTABLISHED'
    execution_id: str | None = None
    scenario_version: str | None = None
    symptom_location: dict | None = None
    invalid_boundary_observed: list = field(default_factory=list)
    earliest_invalid_boundary_within_observed_scope: list = field(default_factory=list)
    upstream_candidates: list = field(default_factory=list)
    unobserved_upstream_scope: list = field(default_factory=list)
    supporting_evidence: list = field(default_factory=list)
    contradictory_evidence: list = field(default_factory=list)
    missing_information: list = field(default_factory=list)
    confidence: str = 'unknown'
    confidence_reasons: list = field(default_factory=list)
    scope_limitations: list = field(default_factory=lambda:['Origin before the observed boundary is not established.','Runtime evidence and expectations are supplied declarations, not independently verified Make executions.'])
    evidence_registry: list = field(default_factory=list)
    field_observations: list = field(default_factory=list)
    evidence_warnings: list = field(default_factory=list)
    execution_paths: list = field(default_factory=list)
    observed_data_paths: list = field(default_factory=list)
    operator_findings: list = field(default_factory=list)


def field_value(obs,path):
    if obs['redaction_state']!='NONE':return 'REDACTED',None
    prefix=obs['data_path']
    if path[:len(prefix)]!=prefix:return 'NOT_PROVIDED',None
    value=obs['observed_value']
    for segment in path[len(prefix):]:
        if isinstance(value,list) and type(segment) is int:
            if segment>=len(value):return ('ABSENT' if obs['completeness']=='COMPLETE' else 'PARTIAL_OBSERVATION'),None
            value=value[segment]
        elif isinstance(value,dict) and isinstance(segment,str):
            if segment not in value:return ('ABSENT' if obs['completeness']=='COMPLETE' else 'PARTIAL_OBSERVATION'),None
            value=value[segment]
        else:return 'NOT_PROVIDED',None
    if value is None:return 'NULL',value
    if value=='':return 'EMPTY_STRING',value
    if value==[]:return 'EMPTY_ARRAY',value
    return 'PRESENT',value


def field_state(obs,path):
    return field_value(obs,path)[0]


def json_type(value):
    return ('null' if value is None else 'boolean' if type(value) is bool else
            'number' if type(value) in (int,float) else 'string' if isinstance(value,str) else
            'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'UNKNOWN')


def mismatches(obs,path,expectation):
    # No judgement from partial or redacted snapshots, including an empty array excerpt.
    state,value=field_value(obs,path)
    if obs['completeness']!='COMPLETE' or state in ('REDACTED','NOT_PROVIDED','PARTIAL_OBSERVATION'):return []
    if state=='ABSENT':return ['REQUIRED_FIELD_ABSENT'] if expectation['required'] is True else []
    if state=='NULL':return ['NULL_NOT_ALLOWED'] if expectation.get('nullable') is False else []
    result=[]
    if expectation['expected_type']!='UNKNOWN' and json_type(value)!=expectation['expected_type']:result.append('TYPE_MISMATCH')
    if state=='EMPTY_ARRAY' and expectation.get('min_items')==1:result.append('EMPTY_ARRAY_NOT_ALLOWED')
    return result


def expectations_conflict(items):
    for key,unknown in [('required',None),('nullable',None),('expected_type','UNKNOWN'),('min_items',None)]:
        if len({e.get(key) for e in items if e.get(key)!=unknown})>1:return True
    return any(e['expected_type']=='null' for e in items) and any(e.get('nullable') is False for e in items)


def observation_conflicts(obs,peer,path,peer_path):
    state,value=field_value(obs,path);other,other_value=field_value(peer,peer_path)
    known={'ABSENT','NULL','EMPTY_STRING','EMPTY_ARRAY','PRESENT'}
    if state not in known or other not in known:return False
    # A present value in an excerpt can contradict an alleged absence. An empty
    # excerpt cannot contradict a complete array; require full peers otherwise.
    if state=='ABSENT':return other!='ABSENT'
    if peer['completeness']!='COMPLETE':return False
    return state!=other or json_type(value)!=json_type(other_value) or value!=other_value


def evaluate(problem,analysis):
    ctx=problem.execution_context.root_cause_context
    out=RootCauseTrace(problem.analysis_id)
    if not ctx:return asdict(out)
    if 'error' in ctx:
        out.missing_information.append({'code':'INVALID_CONTEXT','explanation':ctx['error']});return asdict(out)
    out.execution_id=ctx['execution_id'];out.scenario_version=ctx['scenario_version']
    failure=analysis.failure_location
    if not failure or failure.source!='explicit_context' or not failure.module_id:
        out.missing_information.append({'code':'EXPLICIT_SYMPTOM_REQUIRED'});return asdict(out)
    out.symptom_location={'module_id':failure.module_id,'source':'execution_context.failing_module_id'}
    out.execution_paths,issues=upstream_paths(analysis.workflow,failure.module_id)
    out.scope_limitations.extend(issues)
    deps=analysis.dependency_evidence
    observations=ctx['observations'];expectations=ctx['expectations'];correlations=ctx['correlations']
    if not ctx['scenario_version']:out.scope_limitations.append('Scenario version not supplied; correspondence to the executed Blueprint is declared only.')
    out.evidence_registry=[dict(d,provenance_kind='STRUCTURAL') for d in deps]
    for kind,items in [('observation',observations),('expectation',expectations),('correlation',correlations)]:
        for item in items:
            out.evidence_registry.append(dict({k:v for k,v in item.items() if k!='observed_value'},analysis_id=problem.analysis_id,execution_id=ctx['execution_id'],scenario_version=ctx['scenario_version'],provenance_kind='DECLARATION',record_type=kind))
    for obs in observations:
        for key,code in [('observed_at','OBSERVATION_DATE_UNKNOWN'),('execution_id','OBSERVATION_RUN_INHERITED')]:
            if not obs.get(key):out.evidence_warnings.append({'code':code,'subject_ref':obs['observation_id']})
        if obs.get('evidence_origin','UNKNOWN')=='UNKNOWN':out.evidence_warnings.append({'code':'OBSERVATION_ORIGIN_UNKNOWN','subject_ref':obs['observation_id']})
    for correlation in correlations:
        if not correlation.get('method'):out.evidence_warnings.append({'code':'LEGACY_BUNDLE_DECLARATION','subject_ref':correlation['correlation_id']})
    from .trace_extensions import trace_paths,operator_findings
    out.observed_data_paths,allowed,path_issues=trace_paths(ctx,deps,failure.module_id)
    out.scope_limitations.extend(path_issues)
    out.operator_findings=operator_findings(problem,analysis,ctx)
    for kind,items in [('transition',ctx.get('transitions',[])),('operator_check',ctx.get('operator_checks',[]))]:
        for item in items:out.evidence_registry.append(dict(item,record_type=kind,provenance_kind='DECLARATION'))
    comparisons=0
    if len(deps)>=1000:
        out.missing_information.append({'code':'DEPENDENCY_LIMIT'});return asdict(out)
    for dep in deps:
        if dep['target_module_id']!=failure.module_id and not any(d==dep['dependency_id'] for d,c in allowed):continue
        if dep['resolution']!='RESOLVED':
            out.missing_information.append({'code':'UNRESOLVED_DEPENDENCY','subject_ref':dep['dependency_id']});continue
        targets=[e for e in expectations if e['target_module_id']==dep['target_module_id'] and e['target_field_path']==dep['target_field_path'] and e.get('direction','INPUT')=='INPUT']
        sources=[o for o in observations if o['module_id']==dep['source_module_id'] and o['direction']=='OUTPUT']
        if not targets:out.missing_information.append({'code':'EXACT_EXPECTATION_REQUIRED','subject_ref':dep['dependency_id']})
        if not sources:out.missing_information.append({'code':'OUTPUT_OBSERVATION_REQUIRED','subject_ref':dep['dependency_id']})
        if expectations_conflict(targets):
            out.contradictory_evidence.extend(e['expectation_id'] for e in targets);continue
        for expectation in targets:
            for obs in sources:
                comparisons+=1
                if comparisons>10000:
                    out.status='NOT_ESTABLISHED';out.confidence='unknown';out.invalid_boundary_observed=[];out.earliest_invalid_boundary_within_observed_scope=[];out.missing_information.append({'code':'COMPARISON_LIMIT'});return asdict(out)
                state=field_state(obs,dep['source_field_path'])
                out.field_observations.append({'observation_ref':obs['observation_id'],'dependency_ref':dep['dependency_id'],'state':state})
                violations=mismatches(obs,dep['source_field_path'],expectation)
                paired=[c for c in correlations if c['observation_id']==obs['observation_id'] and c['target_module_id']==dep['target_module_id'] and (dep['target_module_id']==failure.module_id or (dep['dependency_id'],c['correlation_id']) in allowed)]
                if not paired:
                    out.missing_information.append({'code':'BUNDLE_CORRELATION_REQUIRED','subject_ref':obs['observation_id']})
                    if violations:out.upstream_candidates.append({'dependency_ref':dep['dependency_id'],'observation_ref':obs['observation_id'],'expectation_ref':expectation['expectation_id'],'mismatch_codes':violations})
                    continue
                if not violations:
                    out.missing_information.append({'code':'MISMATCH_NOT_ESTABLISHED','subject_ref':obs['observation_id'],'state':state});continue
                for correlation in paired:
                    if len(out.invalid_boundary_observed)>=256:
                        out.status='NOT_ESTABLISHED';out.invalid_boundary_observed=[];out.missing_information.append({'code':'BOUNDARY_LIMIT'});return asdict(out)
                    peers=[o for o in observations if (o['module_id']==obs['module_id'] and o['direction']=='OUTPUT' and o['bundle_id']==obs['bundle_id']) or (o['module_id']==dep['target_module_id'] and o['direction']=='INPUT' and o['bundle_id']==correlation['target_bundle_id'])]
                    conflicts=[o for o in peers if observation_conflicts(obs,o,dep['source_field_path'],dep['source_field_path'] if o['direction']=='OUTPUT' else dep['target_field_path'])]
                    if conflicts:
                        out.contradictory_evidence.extend([obs['observation_id']]+[o['observation_id'] for o in conflicts]);continue
                    ref='boundary:'+dep['dependency_id']+':'+obs['observation_id']+':'+expectation['expectation_id']+':'+correlation['correlation_id']
                    boundary=asdict(BoundaryObservation(ref,dep['dependency_id'],obs['observation_id'],expectation['expectation_id'],correlation['correlation_id']))
                    refs=[dep['dependency_id'],obs['observation_id'],expectation['expectation_id'],correlation['correlation_id']]
                    boundary.update(rule_id=violations[0]+'_AT_EXPLICIT_BOUNDARY_V1',mismatch_codes=violations,source_module_id=dep['source_module_id'],target_module_id=dep['target_module_id'],source_field_path=dep['source_field_path'],target_field_path=dep['target_field_path'],observed_state=state,observed_type=json_type(field_value(obs,dep['source_field_path'])[1]) if state!='ABSENT' else 'UNKNOWN',expected_type=expectation['expected_type'],nullable=expectation.get('nullable'),min_items=expectation.get('min_items'),evidence_refs=refs)
                    if state=='ABSENT':boundary['missing_source_path']=dep['source_field_path']
                    out.invalid_boundary_observed.append(boundary);out.supporting_evidence.extend(refs)
                    out.unobserved_upstream_scope.append({'before_module_id':dep['source_module_id'],'reason':'Earlier origin not evaluated by this rule.'})
    if 'CONTRADICTORY_PATH_LINK' in path_issues:out.contradictory_evidence.append('CONTRADICTORY_PATH_LINK')
    if out.contradictory_evidence:
        out.status='CONTRADICTED'
    elif out.invalid_boundary_observed:
        out.status='INVALID_BOUNDARY_OBSERVED';out.confidence='medium'
        if not issues and not path_issues:
            out.earliest_invalid_boundary_within_observed_scope=[{'boundary_ref':b['boundary_id'],'scope_start':b['source_module_id'],'scope_end':b['target_module_id'],'coverage_evidence_refs':b['evidence_refs']} for b in out.invalid_boundary_observed]
            if ctx.get('transitions'):
                earliest=[]
                for path in out.observed_data_paths:
                    if path['stop_reason']!='OBSERVED_SCOPE_START':continue
                    for dep_ref,corr_ref in zip(path['dependency_refs'],path['correlation_refs']):
                        found=[b for b in out.invalid_boundary_observed if b['dependency_ref']==dep_ref and b['correlation_ref']==corr_ref]
                        if found:
                            earliest.extend({'boundary_ref':b['boundary_id'],'path_ref':path['path_id'],'scope_start':path['module_ids'][0],'scope_end':path['module_ids'][-1],'coverage_evidence_refs':path['dependency_refs']+path['correlation_refs']+path['transition_refs'],'limitation':'Earliest observed mismatch in this supplied path, not the first origin or a proven propagated cause.'} for b in found);break
                out.earliest_invalid_boundary_within_observed_scope=earliest
    elif out.upstream_candidates:out.status='CANDIDATES';out.confidence='low'
    if out.status=='NOT_ESTABLISHED' and not out.missing_information:out.missing_information.append({'code':'NO_SUPPORTED_EXPLICIT_MAPPING'})
    out.supporting_evidence=sorted(set(out.supporting_evidence));out.contradictory_evidence=sorted(set(out.contradictory_evidence))
    out.confidence_reasons=['Conclusion limited to the supplied observations and direct literal mappings; no root-cause probability.']
    return asdict(out)
