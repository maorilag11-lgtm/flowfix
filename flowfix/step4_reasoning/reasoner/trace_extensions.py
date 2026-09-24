"""Observed multi-hop paths and local operator checks. Never execute Make expressions."""
from .root_cause import field_value,json_type,mismatches,expectations_conflict,observation_conflicts


def usable(o):
    return o['completeness']=='COMPLETE' and o['redaction_state']=='NONE'


def trace_paths(ctx,deps,symptom):
    observations={o['observation_id']:o for o in ctx['observations']}
    correlations=ctx['correlations'];transitions=ctx.get('transitions',[])
    paths=[];allowed=set();issues=[];queue=[]
    for d in deps:
        if d['resolution']!='RESOLVED' or d['target_module_id']!=symptom:continue
        for c in correlations:
            o=observations[c['observation_id']]
            if c['target_module_id']==symptom and o['module_id']==d['source_module_id']:
                queue.append(([(d,c)],[]))
                if len(queue)>2048:return [],set(),['MULTIHOP_LIMIT']
    iterations=0;comparisons=0
    while queue:
        iterations+=1
        if iterations>2048 or len(paths)>=128:issues.append('MULTIHOP_LIMIT');break
        chain,links=queue.pop();d,c=chain[-1];o=observations[c['observation_id']]
        allowed.add((d['dependency_id'],c['correlation_id']))
        stop='OBSERVED_SCOPE_START';next_steps=[]
        if len(chain)>=16:stop='MULTIHOP_DEPTH_LIMIT';issues.append(stop)
        elif not usable(o):stop='INCOMPLETE_PATH_OBSERVATION'
        else:
            bridges=[t for t in transitions if t['output_observation_id']==o['observation_id'] and t['output_field_path']==d['source_field_path']]
            if bridges:stop='UNRESOLVED_PATH_LINK'
            for t in bridges:
                source_input=observations[t['input_observation_id']]
                if not usable(source_input):continue
                if field_value(o,t['output_field_path'])[0] in ['NOT_PROVIDED','PARTIAL_OBSERVATION','REDACTED'] or field_value(source_input,t['input_field_path'])[0] in ['NOT_PROVIDED','PARTIAL_OBSERVATION','REDACTED']:continue
                for previous in deps:
                    comparisons+=1
                    if comparisons>10000:return [],set(),['MULTIHOP_LIMIT']
                    if previous['resolution']!='RESOLVED' or previous['target_module_id']!=t['module_id'] or previous['target_field_path']!=t['input_field_path']:continue
                    for incoming in correlations:
                        comparisons+=1
                        if comparisons>10000:return [],set(),['MULTIHOP_LIMIT']
                        if incoming.get('target_observation_id')!=source_input['observation_id'] or incoming['target_module_id']!=t['module_id']:continue
                        prior=observations[incoming['observation_id']]
                        if prior['module_id']!=previous['source_module_id'] or not usable(prior):continue
                        if observation_conflicts(prior,source_input,previous['source_field_path'],previous['target_field_path']):
                            issues.append('CONTRADICTORY_PATH_LINK');continue
                        key=(previous['dependency_id'],incoming['correlation_id'])
                        if key in [(x['dependency_id'],y['correlation_id']) for x,y in chain]:issues.append('MULTIHOP_CYCLE');continue
                        next_steps.append((chain+[(previous,incoming)],links+[t]))
                        if len(next_steps)>128:issues.append('MULTIHOP_LIMIT');break
                    if len(next_steps)>128:break
                if len(next_steps)>128:break
        if next_steps and len(chain)<16:
            queue.extend(next_steps[:128]);continue
        ordered=list(reversed(chain))
        paths.append({'path_id':'observed-path-'+str(len(paths)+1),'dependency_refs':[a['dependency_id'] for a,b in ordered],
                      'correlation_refs':[b['correlation_id'] for a,b in ordered],
                      'transition_refs':[t['transition_id'] for t in reversed(links)],
                      'source_observation_refs':[b['observation_id'] for a,b in ordered],
                      'module_ids':[ordered[0][0]['source_module_id']]+[a['target_module_id'] for a,b in ordered],
                      'stop_reason':stop,'complete_scenario_trace':False})
    if any(i in issues for i in ['MULTIHOP_LIMIT','MULTIHOP_CYCLE','CONTRADICTORY_PATH_LINK']):
        # Do not let a truncated or contradictory exploration authorize new upstream findings.
        allowed=set();paths=[]
    return paths,allowed,sorted(set(issues))


def operator_findings(problem,analysis,ctx):
    observations={o['observation_id']:o for o in ctx['observations']}
    expectations={e['expectation_id']:e for e in ctx['expectations']}
    modules={}
    for m in problem.blueprint.modules:modules.setdefault(m.id,[]).append(m)
    filters={f.module_id for f in problem.blueprint.filters}
    results=[]
    checks=ctx.get('operator_checks',[])
    for c in checks:
        row={'check_id':c['check_id'],'module_id':c['module_id'],'kind':c['kind'],'status':'NOT_ESTABLISHED','mismatch_codes':[],
             'evidence_refs':[c['check_id']]+c['input_observation_ids']+c['output_observation_ids']+c['output_expectation_ids'],
             'missing_information':[], 'scope':'Caller-declared single execution; local operator contract, not the root cause.'}
        results.append(row)
        found=modules.get(c['module_id'],[])
        # Use exact supported Make module identifiers, never fuzzy application labels.
        module_type=found[0].module_type if len(found)==1 else None
        known={'ITERATOR':{'builtin:BasicFeeder','builtin.BasicFeeder','builtin:Iterator','builtin.Iterator'},
               'AGGREGATOR':{'builtin:BasicAggregator','builtin.BasicAggregator','builtin:ArrayAggregator','builtin.ArrayAggregator'}}
        if len(found)!=1 or (c['kind']=='FILTER' and c['module_id'] not in filters) or (c['kind']!='FILTER' and module_type not in known[c['kind']]):
            row['reason']='UNSUPPORTED_OPERATOR_STRUCTURE';continue
        refs=c['input_observation_ids']+c['output_observation_ids']
        if not c['complete_bundle_set'] or any(not usable(observations[r]) for r in refs):row['reason']='INCOMPLETE_OPERATOR_SCOPE';continue
        # Conflicting snapshots for any counted bundle invalidate this local check.
        conflict=False
        for ref in refs:
            o=observations[ref]
            for peer in observations.values():
                if peer['module_id']==o['module_id'] and peer['direction']==o['direction'] and peer['bundle_id']==o['bundle_id'] and o['data_path']==peer['data_path'] and usable(peer):
                    if json_type(o['observed_value'])!=json_type(peer['observed_value']) or o['observed_value']!=peer['observed_value']:conflict=True
        for other in checks:
            scope=c.get('event_bundle_id',c.get('group_id',c['input_observation_ids']))
            other_scope=other.get('event_bundle_id',other.get('group_id',other['input_observation_ids']))
            if other['check_id']!=c['check_id'] and other['module_id']==c['module_id'] and other['kind']==c['kind'] and scope==other_scope:
                keys=['outcome','expected_outcome'] if c['kind']=='FILTER' else ['input_observation_ids','output_observation_ids','array_path']
                if any(c.get(k)!=other.get(k) for k in keys):conflict=True
        if conflict:row['status']='CONTRADICTED';row['reason']='CONTRADICTORY_OPERATOR_EVIDENCE';continue
        if c['kind']=='FILTER':
            corr=[x for x in ctx['correlations'] if x['observation_id']==c['input_observation_ids'][0] and x['target_module_id']==c['module_id'] and x['target_bundle_id']==c['event_bundle_id'] and x.get('target_execution_id')==ctx['execution_id']]
            if not corr:row['reason']='FILTER_BUNDLE_CORRELATION_REQUIRED';continue
            row['evidence_refs'].extend(x['correlation_id'] for x in corr)
            row.update(observed_outcome=c['outcome'],expected_outcome=c['expected_outcome'])
            if 'UNKNOWN' in [c['outcome'],c['expected_outcome']]:row['reason']='FILTER_OUTCOME_UNKNOWN';continue
            if c['outcome']!=c['expected_outcome']:row['mismatch_codes'].append('FILTER_OUTCOME_MISMATCH')
        else:
            array_ref=c['input_observation_ids'][0] if c['kind']=='ITERATOR' else c['output_observation_ids'][0]
            state,value=field_value(observations[array_ref],c['array_path'])
            if state in ['NOT_PROVIDED','PARTIAL_OBSERVATION','REDACTED']:row['reason']='ARRAY_OBSERVATION_REQUIRED';continue
            row['observed_array_type']='ABSENT' if state=='ABSENT' else json_type(value)
            if state=='ABSENT' or not isinstance(value,list):row['mismatch_codes'].append('EXPECTED_ARRAY_NOT_OBSERVED')
            else:
                actual=len(c['output_observation_ids']) if c['kind']=='ITERATOR' else len(value)
                expected=len(value) if c['kind']=='ITERATOR' else len(c['input_observation_ids'])
                row.update(observed_count=actual,expected_count=expected)
                if actual!=expected:row['mismatch_codes'].append('BUNDLE_COUNT_MISMATCH')
            output_checks=[]
            for ref in c['output_expectation_ids']:
                e=expectations[ref]
                peers=[expectations[r] for r in c['output_expectation_ids'] if expectations[r]['target_field_path']==e['target_field_path']]
                if expectations_conflict(peers):row['status']='CONTRADICTED';row['reason']='CONTRADICTORY_OUTPUT_EXPECTATIONS';break
                for output_ref in c['output_observation_ids']:
                    if field_value(observations[output_ref],e['target_field_path'])[0] in ['NOT_PROVIDED','PARTIAL_OBSERVATION','REDACTED']:row['missing_information'].append('OUTPUT_FIELD_OBSERVATION_REQUIRED')
                    codes=mismatches(observations[output_ref],e['target_field_path'],e)
                    output_checks.append({'observation_ref':output_ref,'expectation_ref':ref,'field_path':e['target_field_path'],'mismatch_codes':codes})
                    row['mismatch_codes'].extend(codes)
            row['output_field_checks']=output_checks
        if row['status']!='CONTRADICTED':row['status']='INVALID_CONTRACT_OBSERVED' if row['mismatch_codes'] else 'NOT_ESTABLISHED' if row['missing_information'] else 'NO_MISMATCH_OBSERVED'
        row['mismatch_codes']=sorted(set(row['mismatch_codes']))
    return results
