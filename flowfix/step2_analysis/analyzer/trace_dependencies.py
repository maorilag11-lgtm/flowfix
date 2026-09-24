"""Exact literal mapping references and bounded explicit execution ancestry."""
import re
from dataclasses import dataclass,asdict

@dataclass
class DependencyEvidence:
    dependency_id: str
    analysis_id: str
    source_module_id: str
    target_module_id: str
    dependency_type: str
    blueprint_path: str | None
    mapping_expression: str
    source_field_path: list
    target_field_path: list
    resolution: str

@dataclass
class BoundaryObservation:
    boundary_id: str
    dependency_ref: str
    upstream_output_observation_ref: str
    expectation_ref: str
    correlation_ref: str


def collect(problem,graph):
    result=[];counts={}
    for m in problem.blueprint.modules:counts[m.id]=counts.get(m.id,0)+1
    # Deliberately narrow grammar: no arrays, functions, interpolations or eval.
    literal=re.compile(r'\{\{([0-9]+)\.([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\}\}')
    def walk(value,segments,mid):
        if len(segments)>24 or len(result)>=1000:return
        if isinstance(value,dict):
            for k in sorted(value):walk(value[k],segments+[k],mid)
        elif isinstance(value,str):
            match=literal.fullmatch(value)
            if match:
                source,field=match.groups();ref='mapping:'+str(mid)+':'+repr(segments)
                result.append(asdict(DependencyEvidence(ref,problem.analysis_id,source,str(mid),'DATA_DEPENDENCY',next((m.blueprint_path for m in problem.blueprint.modules if m.id==mid),None),value,field.split('.'),segments,'RESOLVED' if counts.get(source,0)==1 and counts.get(mid,0)==1 else 'UNRESOLVED')))
    for m in problem.blueprint.modules:
        if isinstance(m.metadata.get('mapper'),dict):walk(m.metadata['mapper'],[],m.id)
    return sorted(result,key=lambda d:d['dependency_id'])


def upstream_paths(graph,target):
    parents={n.module_id:sorted(n.predecessors) for n in graph.nodes}
    paths=[];issues=[];stack=[(target,)];visited_count=0
    while stack and len(paths)<256:
        visited_count+=1
        if visited_count>10000:issues.append('TRAVERSAL_LIMIT');break
        route=stack.pop();p=parents.get(route[-1],[])
        if len(route)>=64:issues.append('DEPTH_LIMIT');continue
        if not p:paths.append(list(reversed(route)))
        for source in reversed(p):
            if source in route:issues.append('CYCLE');continue
            stack.append(route+(source,))
    if stack:issues.append('PATH_LIMIT')
    return sorted(paths),sorted(set(issues))
