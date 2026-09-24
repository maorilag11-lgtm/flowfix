"""Expose diagnostic limits and provenance without upgrading a hypothesis to a fact."""
import dataclasses
from flowfix.step1_intake.redaction.redactor import redact_dict


def assessment(reasoning, planning, decision):
    applicable=planning.correction_applicable
    status=reasoning.reasoning_status
    if applicable:
        kind='local_syntax_verified'
        title='Défaut de syntaxe reproduit localement'
        detail='La modification proposée corrige la syntaxe du texte fourni. Le contrat du champ et sa provenance sont déclarés par vous ; la résolution dans Make reste à vérifier.'
    elif status=='DIAGNOSIS_CANDIDATE' and reasoning.confidence in ('medium','high'):
        kind='hypothesis'
        title='Cause probable à vérifier'
        detail='Les éléments disponibles soutiennent une hypothèse principale. Ils ne prouvent pas encore la cause réelle ni une valeur de remplacement exacte.'
    else:
        kind='inconclusive'
        title='Diagnostic non concluant'
        detail='Plusieurs explications restent possibles, ou les preuves sont insuffisantes ou contradictoires. Complétez le contexte avant de modifier le scénario.'
    if decision.action=='ESCALATE':
        kind='human_review';title='Vérification humaine nécessaire'
        detail='Le parcours automatique ne permet pas de conclure. Aucune correction précise n’est présentée comme applicable.'
    trace=[]
    for relation,items in [('support',reasoning.supporting_evidence),('contradiction',reasoning.contradicting_evidence)]:
        for e in items:
            row=dataclasses.asdict(e);row['relation']=relation
            if row not in trace:trace.append(row)
    return redact_dict({'kind':kind,'title':title,'detail':detail,'execution_verified':False,'exact_change_available':applicable,'evidence':trace}).redacted_data


def module_choices(problem):
    """Exact paths from the redacted Blueprint; no guessing of Make UI labels."""
    from flowfix.step2_analysis.analyzer.trace_dependencies import collect
    dependencies=collect(problem,None)
    modules=[]
    for m in problem.blueprint.modules:
        paths=[]
        def visit(value,path):
            if len(paths)>=100 or len(path)>6:return
            if isinstance(value,str) and 0<len(value)<=10000 and '[REDACTED:' not in value:
                paths.append(path)
            elif isinstance(value,dict):
                for key,child in value.items():
                    if isinstance(key,str):visit(child,path+[key])
        for root in ['mapper','parameters']:
            value=m.metadata.get(root)
            if isinstance(value,dict):
                for key,child in value.items():visit(child,[root,key])
        modules.append({'id':str(m.id),'name':m.name or m.module_type,'fields':paths,'trace_mappings':[{k:d[k] for k in ['source_module_id','target_module_id','source_field_path','target_field_path','mapping_expression']} for d in dependencies if d['target_module_id']==str(m.id) and d['resolution']=='RESOLVED']})
    return modules
