import dataclasses
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .diagnostic_contract import assessment
from .first_reading import first_reading
from flowfix.step1_intake import run_intake
from flowfix.step1_intake.redaction.redactor import redact_dict
from flowfix.step2_analysis import run_analysis
from flowfix.step3_retrieval import run_retrieval
from flowfix.step4_reasoning import run_reasoning
from flowfix.step5_response import run_response
from flowfix.step6_clarification import run_clarification
from flowfix.step7_feedback import process_feedback
from flowfix.step7_feedback.models_internal.models import UserFeedback
from flowfix.step8_orchestrator import run_orchestration
from flowfix.step9_fix_planning import run_fix_planning

class Invalid(ValueError): pass
class Conflict(Invalid): pass

def now(): return datetime.now(timezone.utc).isoformat()
def text(value, limit=20000):
    if not isinstance(value, str) or len(value)>limit: raise Invalid('Texte absent ou trop volumineux.')
    return value.strip()

def intake(inputs, sid):
    p=run_intake(user_description=inputs.get('description'),error_text=inputs.get('error'),blueprint_text=inputs.get('blueprint'),context=inputs.get('context',{}))
    if not p.ready_for_step2: raise Invalid('Les informations fournies ne peuvent pas être analysées.')
    p=p.normalized_problem
    if inputs.get('blueprint') and (not p.blueprint.valid_json or not p.blueprint.recognized_as_make_blueprint):
        raise Invalid('Le fichier doit être un Blueprint de scénario Make au format JSON.')
    module=p.execution_context.failing_module_id
    if module and p.blueprint.provided and str(module) not in {str(m.id) for m in p.blueprint.modules}:
        raise Invalid('Ce module ne figure pas dans le Blueprint. Sélectionnez un module existant.')
    p.analysis_id=sid
    return p

def sanitized_inputs(p):
    return dict(description=p.user_description or '',error='\n'.join(p.errors.exact_error_messages),blueprint=p.blueprint.raw_blueprint or '',context=dataclasses.asdict(p.execution_context))

def checked(output):
    if not output.validation.valid:raise Invalid('Le moteur a refusé un résultat invalide ; aucune modification enregistrée.')
    return output

def analyze(inputs,sid,cycle=0,answered=None,feedback=None):
    p=intake(inputs,sid);a=checked(run_analysis(p)).analysis;r=checked(run_retrieval(p,a))
    if r.integrity_status!='OK': raise Invalid('La base de connaissances est indisponible ou invalide.')
    h=checked(run_reasoning(p,a,r)).result;s=checked(run_response(p,a,r,h)).result
    c=checked(run_clarification(s,p,cycle=cycle,answered_gaps=answered or [])).result
    u=UserFeedback(analysis_id=sid,**feedback) if feedback else None
    fb=checked(process_feedback(p,a,r,h,s,c,u)).result
    decision=checked(run_orchestration(s,c,fb,current_cycle=cycle)).result
    f=checked(run_fix_planning(p,a,h,s,decision))
    verdict=assessment(h,f,decision)
    return sanitized_inputs(p),dict(root_cause_trace=h.root_cause_trace,first_reading=first_reading(p,r),assessment=verdict,response=s.to_dict(),clarification=c.to_dict(),feedback=dataclasses.asdict(fb),decision=dataclasses.asdict(decision),plan=dataclasses.asdict(f.result),correction_applicable=f.correction_applicable,problem_resolved=f.problem_resolved,redactions=p.metadata.redactions_applied)

class Sessions:
    def __init__(self, directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.directory/'sessions.sqlite3'
        with self.connect() as db: db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)')
        self.path.chmod(0o600)
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=15)
        db.execute('PRAGMA secure_delete=ON')
        return db
    def list(self):
        with self.connect() as db: rows=db.execute('SELECT data FROM sessions').fetchall()
        result=[]
        for row in rows:
            d=json.loads(row[0]);result.append({k:d[k] for k in ['id','title','created','updated','revision','resolution']})
        return sorted(result,key=lambda d:d['updated'],reverse=True)
    def get(self,sid):
        with self.connect() as db: row=db.execute('SELECT data FROM sessions WHERE id=?',(sid,)).fetchone()
        if not row: raise KeyError(sid)
        return json.loads(row[0])
    def parse_inputs(self,body):
        if not isinstance(body,dict):raise Invalid('Requête invalide.')
        inputs={k:text(body.get(k,''),1000000 if k=='blueprint' else 20000) for k in ['description','error','blueprint']}
        module=text(body.get('module',''),100)
        ctx={'failing_module_id':module} if module else {}
        for key in ['logs','input_data','expected_behavior']:
            value=text(body.get(key,''))
            if value:ctx[key]=value
        response=text(body.get('http_response_body',''))
        if response:ctx['http']={'response_body':response}
        if not any(inputs.values()) and not ctx:raise Invalid('Ajoutez une description, une erreur, un Blueprint ou des données d’exécution.')
        if body.get('root_cause_context') is not None:
            from flowfix.step1_intake.intake.trace_contract import parse_context
            try:ctx['root_cause_context']=parse_context(body['root_cause_context'])
            except (ValueError,TypeError,RecursionError):raise Invalid('Contexte de traçage invalide.')
        observation=body.get('json_field_observation')
        if observation is not None:
            from flowfix.step1_intake.intake.field_contracts import parse_observation
            parsed=parse_observation(observation)
            if parsed is None:raise Invalid('Observation de champ JSON invalide ou incomplète.')
            if parsed.module_id!=module:raise Invalid('Le champ observé doit appartenir au module sélectionné.')
            ctx['json_field_observation']=dataclasses.asdict(parsed)
        inputs['context']=ctx
        return inputs
    def create(self,body):
        inputs=self.parse_inputs(body)
        sid=str(uuid.uuid4());clean,output=analyze(inputs,sid)
        d=dict(id=sid,title=(clean['description'] or clean['error'] or 'Analyse de Blueprint')[:90],created=now(),updated=now(),revision=1,resolution='unknown',inputs=clean,output=output,cycle=0,answered=[],history=[])
        with self.connect() as db:db.execute('INSERT INTO sessions VALUES (?,?,?)',(sid,1,json.dumps(d,ensure_ascii=False)))
        return d
    def change(self,sid,body,kind):
        if not isinstance(body,dict):raise Invalid('Requête invalide.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT data FROM sessions WHERE id=?',(sid,)).fetchone()
            if not row:raise KeyError(sid)
            d=json.loads(row[0])
            if body.get('revision')!=d['revision']:raise Conflict('Cette session a changé. Rechargez-la avant de poursuivre.')
            if kind=='delete':
                db.execute('DELETE FROM sessions WHERE id=?',(sid,));return {'deleted':True}
            d=mutate(d,body,kind)
            db.execute('UPDATE sessions SET revision=?,data=? WHERE id=?',(d['revision'],json.dumps(d,ensure_ascii=False),sid))
            return d

    def settings(self,body=None):
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, data TEXT NOT NULL)')
            if body is not None:
                if not isinstance(body,dict):raise Invalid('Invalid settings.')
                name=text(body.get('display_name',''),60)
                if not name:raise Invalid('Choose a display name.')
                safe=run_intake(user_description=name).normalized_problem.user_description
                db.execute('INSERT OR REPLACE INTO settings VALUES (1,?)',(json.dumps({'display_name':safe}),))
            row=db.execute('SELECT data FROM settings WHERE id=1').fetchone()
            return json.loads(row[0]) if row else {'display_name':'Local user'}

    def export_report(self,sid):
        d=self.get(sid);r=d['output']['response']
        return dict(historical_root_cause_traces=[{'archived_at':e['at'],'trace':e['previous_root_cause_trace']} for e in d['history'] if e.get('previous_root_cause_trace')],root_cause_trace=d['output'].get('root_cause_trace'),first_reading=d['output'].get('first_reading'),assessment=d['output'].get('assessment'),manual_corrections=d['output']['plan'].get('correction_proposals',[]),correction_gaps=d['output']['plan'].get('correction_gaps',[]),format_version='1.1',application='FlowFix',release='0.3.0-rc1',exported_at=now(),analysis_id=sid,revision=d['revision'],title=d['title'],resolution_declared_by_user=d['resolution'],status=r['status'],confidence=r['confidence'],summary=r['summary'],observed=r['observed'],candidate=r['diagnosis'],alternatives=r['alternative_hypotheses'],missing_information=r['missing_information'],checks=r['diagnostic_checks'],conditional_solutions=r['documented_solutions'],sources=r['documentation'],decision=d['output']['decision'],feedback=[e for e in d['history'] if e['kind']=='feedback'],limitations=['No Make execution or modification performed.','No independently verified real-world resolution.','Source entries may be partially verified.','Export excludes the full Blueprint and execution payloads; proposed corrections include the specific field text. Review before sharing.'])


def mutate(d,body,kind):
    sid=d['id']
    if kind=='edit':
        clean,output=analyze(Sessions.parse_inputs(None,body),sid)
        d['history'].append(dict(at=now(),kind='edit',previous_inputs=d['inputs'],previous_root_cause_trace=d['output'].get('root_cause_trace')))
        d.update(inputs=clean,output=output,cycle=0,answered=[],resolution='unknown',title=(clean['description'] or clean['error'] or 'Analyse de Blueprint')[:90])
    elif kind=='answer':
        q=d['output']['clarification'].get('question')
        if not q:raise Invalid('Aucune question en attente.')
        answer=text(body.get('answer',''),1000000 if q['question_type']=='blueprint' else 20000)
        if not answer:raise Invalid('Ajoutez une réponse.')
        if answer.casefold() in {'unknown','i don’t know',"i don't know",'je ne sais pas','inconnu','n/a'}:
            raise Invalid('Information inconnue : vous pouvez conserver le diagnostic provisoire ou modifier les données de la session.')
        inputs=d['inputs'];qt=q['question_type'];ctx=inputs['context']
        if qt=='blueprint':inputs['blueprint']=answer
        elif qt=='error_message':inputs['error']=answer
        elif qt=='failing_module':ctx['failing_module_id']=text(answer,100)
        elif qt=='http_response_body':ctx['http']['response_body']=answer
        elif qt=='input_data':ctx['input_data']=answer
        else:ctx['logs']=answer
        # Re-normalize before retaining even the clarification answer.
        clean,output=analyze(inputs,sid,d['cycle']+1,d['answered']+[q['targets_gap']])
        safe_answer=clean['blueprint'] if qt=='blueprint' else clean['error'] if qt=='error_message' else clean['context'].get({'failing_module':'failing_module_id','input_data':'input_data','execution_context':'logs'}.get(qt,'logs'))
        if qt=='http_response_body':safe_answer=clean['context']['http']['response_body']
        d['history'].append(dict(at=now(),kind='answer',question_type=qt,answer=safe_answer))
        d.update(inputs=clean,output=output,cycle=d['cycle']+1,answered=d['answered']+[q['targets_gap']],resolution='unknown')
    elif kind=='feedback':
        status=body.get('status')
        if status not in ['resolved','unresolved','partially_resolved']:raise Invalid('Statut de résolution invalide.')
        note=text(body.get('actual_resolution',''))
        comment=text(body.get('user_comment',''))
        safe=redact_dict({'resolution_status':status,'actual_resolution':note,'user_comment':comment}).redacted_data
        clean,output=analyze(d['inputs'],sid,d['cycle'],d['answered'],safe)
        d.update(inputs=clean,output=output,resolution=status)
        d['history'].append(dict(at=now(),kind='feedback',status=status,actual_resolution=safe['actual_resolution'],user_comment=safe['user_comment']))
    else:raise Invalid('Action inconnue.')
    d['revision']+=1;d['updated']=now()
    return d


def enrich_first_reading(d):
    """Add the current triage to a legacy response without rewriting its verdict/history."""
    if 'first_reading' not in d['output']:
        p=intake(d['inputs'],d['id'])
        a=checked(run_analysis(p)).analysis
        r=checked(run_retrieval(p,a))
        if r.integrity_status=='OK':d['output']['first_reading']=first_reading(p,r)
    return d
