"""Bounded, explicit runtime links and operator contracts. No Blueprint inference."""

def parse_extensions(raw,observations,expectations,ids,ident,provenance,path):
    by_id={o['observation_id']:o for o in observations}
    exps={e['expectation_id']:e for e in expectations}
    def records(name):
        items=raw.get(name,[])
        if not isinstance(items,list) or len(items)>128:raise ValueError('Too many '+name)
        return items
    def base(item,key,fields):
        if not isinstance(item,dict) or set(item)!=fields:raise ValueError('Invalid '+key+' fields')
        if not ident(item[key]) or item[key] in ids or not ident(item['module_id']) or item['execution_id']!=raw['execution_id'] or not provenance(item['provenance']):raise ValueError('Invalid extension identity or provenance')
        ids.add(item[key])
    def observation(ref,module,direction):
        o=by_id.get(ref) if isinstance(ref,str) else None
        if not o or o['module_id']!=module or o['direction']!=direction or o['execution_id']!=raw['execution_id']:raise ValueError('Explicit same-run observation required')
        return o
    transitions=[]
    for t in records('transitions'):
        base(t,'transition_id',{'transition_id','module_id','execution_id','input_observation_id','output_observation_id','input_field_path','output_field_path','provenance'})
        observation(t['input_observation_id'],t['module_id'],'INPUT');observation(t['output_observation_id'],t['module_id'],'OUTPUT')
        if not path(t['input_field_path']) or not path(t['output_field_path']):raise ValueError('Invalid transition path')
        transitions.append(dict(t))
    checks=[]
    common={'check_id','module_id','execution_id','kind','input_observation_ids','output_observation_ids','complete_bundle_set','provenance','expectation_source','output_expectation_ids'}
    extras={'FILTER':{'outcome','expected_outcome','event_bundle_id'},'ITERATOR':{'array_path','rule'},'AGGREGATOR':{'array_path','rule','group_id'}}
    for c in records('operator_checks'):
        if not isinstance(c,dict) or not isinstance(c.get('kind'),str) or c['kind'] not in extras:raise ValueError('Invalid operator kind')
        base(c,'check_id',common|extras[c['kind']])
        if type(c['complete_bundle_set']) is not bool or not provenance(c['expectation_source']):raise ValueError('Invalid operator scope')
        for field in ['input_observation_ids','output_observation_ids','output_expectation_ids']:
            refs=c[field]
            if not isinstance(refs,list) or len(refs)>256 or not all(isinstance(r,str) for r in refs) or len(set(refs))!=len(refs):raise ValueError('Invalid operator references')
        for ref in c['output_expectation_ids']:
            e=exps.get(ref)
            if not e or e['target_module_id']!=c['module_id'] or e['direction']!='OUTPUT':raise ValueError('Expected an explicit output constraint')
        if c['kind']=='FILTER':
            if len(c['input_observation_ids'])!=1 or c['output_observation_ids'] or c['output_expectation_ids'] or not ident(c['event_bundle_id']):raise ValueError('Invalid filter event')
            ref=c['input_observation_ids'][0];o=by_id.get(ref)
            if not o or o['direction']!='OUTPUT' or o['execution_id']!=raw['execution_id']:raise ValueError('Filter needs incoming source output')
            if c['outcome'] not in ['PASSED','BLOCKED','UNKNOWN'] or c['expected_outcome'] not in ['PASSED','BLOCKED','UNKNOWN']:raise ValueError('Invalid filter outcome')
        else:
            for ref in c['input_observation_ids']:observation(ref,c['module_id'],'INPUT')
            for ref in c['output_observation_ids']:observation(ref,c['module_id'],'OUTPUT')
            if not path(c['array_path']):raise ValueError('Invalid array path')
            if c['kind']=='ITERATOR' and (len(c['input_observation_ids'])!=1 or c['rule']!='ONE_BUNDLE_PER_ITEM'):raise ValueError('Invalid iterator contract')
            if c['kind']=='AGGREGATOR' and (len(c['output_observation_ids'])!=1 or c['rule']!='ONE_ITEM_PER_INPUT_IN_GROUP' or not ident(c['group_id'])):raise ValueError('Invalid aggregator contract')
            for refs in [c['input_observation_ids'],c['output_observation_ids']]:
                bundles=[by_id[r]['bundle_id'] for r in refs]
                if len(set(bundles))!=len(bundles):raise ValueError('A bundle must not be counted twice')
        canonical=dict(c)
        for key in ['input_observation_ids','output_observation_ids','output_expectation_ids']:canonical[key]=sorted(c[key])
        checks.append(canonical)
    cost=sum((len(c['input_observation_ids'])+len(c['output_observation_ids']))*(len(observations)+len(checks))+len(c['output_expectation_ids'])*(len(c['output_expectation_ids'])+len(c['output_observation_ids'])) for c in checks)
    if cost>200000:raise ValueError('Operator comparison limit exceeded')
    return sorted(transitions,key=lambda t:t['transition_id']),sorted(checks,key=lambda c:c['check_id'])
