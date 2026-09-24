"""Optional, explicitly supplied runtime evidence. No inference or KB access."""
from dataclasses import dataclass, asdict, field
import json
import re
from flowfix.step1_intake.redaction.redactor import redact_at_path

@dataclass
class RuntimeObservation:
    observation_id: str
    module_id: str
    direction: str
    bundle_id: str
    data_path: list
    observed_value: object
    completeness: str
    redaction_state: str
    provenance: dict
    observed_type: str = 'UNKNOWN'
    presence_state: str = 'PRESENT'
    value_state: str = 'VALUE'
    execution_id: str | None = None
    scenario_version: str | None = None
    evidence_origin: str = 'UNKNOWN'
    observed_at: str | None = None

@dataclass
class Expectation:
    expectation_id: str
    target_module_id: str
    target_field_path: list
    required: bool | None
    expected_type: str
    provenance: dict
    nullable: bool | None = None
    min_items: int | None = None
    direction: str = 'INPUT'

@dataclass
class TraceContext:
    execution_id: str
    scenario_version: str | None
    observations: list
    expectations: list
    correlations: list
    transitions: list = field(default_factory=list)
    operator_checks: list = field(default_factory=list)


def path(value):
    return isinstance(value,list) and len(value)<=24 and all((type(x) is int and x>=0) or (isinstance(x,str) and bool(x) and len(x)<=128) for x in value)


def valid_observed_at(value):
    """ISO calendar timestamp with explicit UTC offset; no server-time inference."""
    if value is None:return True
    if not isinstance(value,str):return False
    m=re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})',value)
    if not m:return False
    year,month,day,hour,minute,second=map(int,m.groups()[:6]);zone=m[7]
    if not 1<=year<=9999 or not 1<=month<=12 or hour>23 or minute>59 or second>59:return False
    days=[31,29 if year%4==0 and (year%100!=0 or year%400==0) else 28,31,30,31,30,31,31,30,31,30,31]
    if not 1<=day<=days[month-1]:return False
    return zone=='Z' or (int(zone[1:3])<=14 and int(zone[4:])<=59 and (int(zone[1:3])<14 or int(zone[4:])==0))


def parse_context(raw):
    """Wire IDs belong to this intake; analysis_id is assigned by the pipeline.

    Only complete container snapshots are accepted as evidence of absence.
    Provenance is caller-declared, never independently authenticated.
    """
    required={'execution_id','scenario_version','observations','expectations','correlations'}
    if not isinstance(raw,dict) or not required<=set(raw) or set(raw)-required-{'transitions','operator_checks'}:
        raise ValueError('Invalid root_cause_context fields')
    encoded=json.dumps(raw,allow_nan=False)
    if len(encoded.encode())>1_000_000:raise ValueError('Trace input too large')
    def ident(v):return isinstance(v,str) and 0<len(v)<=200 and '[REDACTED:' not in v
    def provenance(v):return isinstance(v,dict) and set(v)=={'source_ref'} and ident(v['source_ref'])
    if not ident(raw['execution_id']) or (raw['scenario_version'] is not None and not ident(raw['scenario_version'])):raise ValueError('Invalid run/version identity')
    for key in ['observations','expectations','correlations']:
        if not isinstance(raw[key],list) or len(raw[key])>1000:raise ValueError('Invalid trace collection')
    observations=[];expectations=[];ids=set()
    for collection,cls in [('observations',RuntimeObservation),('expectations',Expectation)]:
        for item in raw[collection]:
            if not isinstance(item,dict):raise ValueError('Invalid evidence')
            try:record=cls(**item)
            except TypeError:raise ValueError('Invalid evidence fields')
            key=item['observation_id' if collection=='observations' else 'expectation_id']
            if not ident(key) or key in ids or not provenance(item['provenance']):raise ValueError('Invalid or duplicate evidence identity')
            ids.add(key)
            if collection=='observations':
                if not ident(record.module_id) or not ident(record.bundle_id) or record.direction not in ['INPUT','OUTPUT'] or not path(record.data_path) or record.completeness not in ['COMPLETE','PARTIAL','UNKNOWN'] or record.redaction_state not in ['NONE','VALUE_REDACTED','KEYS_REDACTED','UNKNOWN']:raise ValueError('Invalid observation')
                if record.execution_id is not None and record.execution_id!=raw['execution_id']:raise ValueError('Observation belongs to another execution')
                if record.scenario_version is not None and record.scenario_version!=raw['scenario_version']:raise ValueError('Observation belongs to another scenario version')
                if record.evidence_origin not in ['UNKNOWN','HISTORICAL','REPRODUCTION'] or not valid_observed_at(record.observed_at):raise ValueError('Invalid observation provenance')
                clean=redact_at_path(record.observed_value, record.data_path)
                if clean.redactions or '[REDACTED:' in json.dumps(clean.redacted_data):record.redaction_state='UNKNOWN'
                record.observed_value=clean.redacted_data
                value=record.observed_value
                record.observed_type=('null' if value is None else 'boolean' if type(value) is bool else 'number' if type(value) in (int,float) else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object' if isinstance(value,dict) else 'UNKNOWN')
                record.presence_state='PRESENT'
                record.value_state='NULL' if value is None else 'EMPTY_STRING' if value=='' else 'VALUE'
                if record.redaction_state!='NONE':record.observed_type='UNKNOWN';record.value_state='REDACTED'

                observations.append(asdict(record))
            else:
                if not ident(record.target_module_id) or not path(record.target_field_path) or not record.target_field_path or (record.required is not None and type(record.required) is not bool) or record.expected_type not in ['string','object','array','number','boolean','null','UNKNOWN']:raise ValueError('Invalid expectation')
                if record.direction not in ['INPUT','OUTPUT']:raise ValueError('Invalid expectation direction')
                if record.nullable is not None and type(record.nullable) is not bool:raise ValueError('Invalid nullable constraint')
                if record.min_items is not None and (type(record.min_items) is not int or record.min_items not in (0,1) or record.expected_type!='array'):raise ValueError('min_items requires array and must be 0 or 1')
                if record.expected_type=='null' and record.nullable is False:raise ValueError('Contradictory null expectation')
                expectations.append(asdict(record))
    origins={o['evidence_origin'] for o in observations if o['evidence_origin']!='UNKNOWN'}
    if len(origins)>1:raise ValueError('Historical and reproduction evidence must be kept in separate dossiers')
    by_id={o['observation_id']:o for o in observations}
    for c in raw['correlations']:
        required={'correlation_id','observation_id','target_module_id','target_bundle_id','provenance'}
        extra={'target_execution_id','target_scenario_version','method','target_observation_id','correlation_key'}
        if not isinstance(c,dict) or not required<=set(c) or set(c)-required-extra or not all(ident(c[k]) for k in ['correlation_id','observation_id','target_module_id','target_bundle_id']) or not provenance(c['provenance']):raise ValueError('Invalid correlation')
        if c['correlation_id'] in ids:raise ValueError('Duplicate correlation')
        ids.add(c['correlation_id'])
        source=by_id.get(c['observation_id'])
        if source is None or source['direction']!='OUTPUT':raise ValueError('Correlation requires a source output observation')
        if set(c)&extra:
            if c.get('target_execution_id')!=raw['execution_id']:raise ValueError('Target execution must match the source dossier')
            if c.get('target_scenario_version') is not None and c['target_scenario_version']!=raw['scenario_version']:raise ValueError('Target version mismatch')
            if c.get('method') not in ['HISTORY_LINK','CORRELATION_KEY','MANUAL']:raise ValueError('Explicit correlation method required')
            if 'correlation_key' in c and (c['method']!='CORRELATION_KEY' or not ident(c['correlation_key'])):raise ValueError('Invalid correlation key')
            if c['method']=='CORRELATION_KEY' and not ident(c.get('correlation_key')):raise ValueError('Correlation key required')
            if 'target_observation_id' in c:
                target=by_id.get(c['target_observation_id']) if isinstance(c['target_observation_id'],str) else None
                if target is None or target['direction']!='INPUT' or target['module_id']!=c['target_module_id'] or target['bundle_id']!=c['target_bundle_id']:raise ValueError('Target observation does not match the correlated input')
    from .trace_extensions import parse_extensions
    transitions,checks=parse_extensions(raw,observations,expectations,ids,ident,provenance,path)
    return asdict(TraceContext(raw['execution_id'],raw['scenario_version'],sorted(observations,key=lambda x:x['observation_id']),sorted(expectations,key=lambda x:x['expectation_id']),sorted(raw['correlations'],key=lambda x:x['correlation_id']),transitions,checks))


def decode_request(raw):
    """Keep legacy parsing; require unambiguous JSON when tracing is requested."""
    body=json.loads(raw)
    if isinstance(body,dict) and body.get('root_cause_context') is not None:
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError('Duplicate JSON key')
                result[key]=value
            return result
        def invalid_constant(_):raise ValueError('Non-JSON number')
        body=json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid_constant)
    return body
