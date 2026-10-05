import json
from datetime import timedelta
from django.utils import timezone
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from .models import Account,Analysis
from verification.test_root_cause_trace import fixture

@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False)
class TraceApiTests(TestCase):
    def setUp(self):
        u=User.objects.create_user('trace@example.test');Account.objects.create(user=u,beta_until=timezone.now()+timedelta(days=1));self.client.force_login(u)
        f=fixture();self.body={'error':f['error'],'blueprint':f['blueprint'],'module':'3','root_cause_context':f['context']['root_cause_context']}
    def test_create_export_and_no_quota_promotion(self):
        r=self.client.post('/api/sessions',json.dumps(self.body),content_type='application/json');self.assertEqual(r.status_code,201)
        d=r.json();self.assertEqual(d['output']['root_cause_trace']['status'],'INVALID_BOUNDARY_OBSERVED');self.assertFalse(d['accounting']['counted']);self.assertEqual(Account.objects.get().free_remaining,3)
        export=self.client.get('/api/sessions/'+d['id']+'/export').json();self.assertEqual(export['root_cause_trace'],d['output']['root_cause_trace'])
    def test_duplicate_key_rejected_without_saving(self):
        raw=json.dumps(self.body).replace('"name": "John"','"email": "present", "email": null')
        r=self.client.post('/api/sessions',raw,content_type='application/json');self.assertEqual(r.status_code,400);self.assertFalse(Analysis.objects.exists())
    def test_malformed_context_rejected_without_saving(self):
        self.body['root_cause_context']['correlations'][0]['observation_id']='missing'
        r=self.client.post('/api/sessions',json.dumps(self.body),content_type='application/json');self.assertEqual(r.status_code,400);self.assertFalse(Analysis.objects.exists())

    def test_panel_script_and_mapping_preview(self):
        self.assertEqual(self.client.get('/root-trace.js').status_code,200)
        r=self.client.post('/api/blueprint',json.dumps({'blueprint':self.body['blueprint']}),content_type='application/json')
        self.assertEqual(r.status_code,200)
        target=next(m for m in r.json()['modules'] if m['id']=='3')
        self.assertEqual(target['trace_mappings'][0]['source_module_id'],'1')
        self.assertEqual(target['trace_mappings'][0]['target_field_path'],['email'])
        self.assertNotIn('observed_value',json.dumps(target))

    def test_comparison_saved_exported_and_preserved_on_edit(self):
        from verification.test_trace_comparison import case
        for value,expected,code in [(12,{'expected_type':'string'},'TYPE_MISMATCH'),(None,{'nullable':False},'NULL_NOT_ALLOWED'),([],{'expected_type':'array','min_items':1},'EMPTY_ARRAY_NOT_ALLOWED')]:
            with self.subTest(code=code):
                self.body['root_cause_context']=case(value,**expected)['context']['root_cause_context']
                r=self.client.post('/api/sessions',json.dumps(self.body),content_type='application/json');self.assertEqual(r.status_code,201)
                d=r.json();t=d['output']['root_cause_trace'];self.assertEqual(t['invalid_boundary_observed'][0]['mismatch_codes'],[code]);self.assertFalse(d['accounting']['counted'])
                self.assertEqual(self.client.get('/api/sessions/'+d['id']+'/export').json()['root_cause_trace'],t)
                body=dict(self.body,revision=d['revision'])
                r=self.client.post('/api/sessions/'+d['id']+'/edit',json.dumps(body),content_type='application/json');self.assertEqual(r.status_code,200)
                self.assertEqual(r.json()['output']['root_cause_trace'],t)

    def test_execution_provenance_and_historical_export(self):
        import copy
        from verification.test_trace_evidence import evidence_fixture
        self.body['root_cause_context']=evidence_fixture()['context']['root_cause_context']
        r=self.client.post('/api/sessions',json.dumps(self.body),content_type='application/json');self.assertEqual(r.status_code,201);old=r.json()
        bad=copy.deepcopy(self.body);bad['root_cause_context']['correlations'][0]['target_execution_id']='another-run'
        r=self.client.post('/api/sessions',json.dumps(bad),content_type='application/json');self.assertEqual(r.status_code,400);self.assertEqual(Analysis.objects.count(),1)
        body=copy.deepcopy(self.body);c=body['root_cause_context'];c['execution_id']='run-2';c['observations'][0].update(execution_id='run-2',evidence_origin='REPRODUCTION',observed_at='2026-09-24T15:00:00Z',observed_value={'email':'a@example.test'});c['correlations'][0]['target_execution_id']='run-2';body['revision']=old['revision']
        r=self.client.post('/api/sessions/'+old['id']+'/edit',json.dumps(body),content_type='application/json');self.assertEqual(r.status_code,200)
        export=self.client.get('/api/sessions/'+old['id']+'/export').json()
        self.assertEqual(export['root_cause_trace']['execution_id'],'run-2');self.assertEqual(export['historical_root_cause_traces'][0]['trace'],old['output']['root_cause_trace'])

    def test_multihop_and_operator_examples_create_export_edit(self):
        from pathlib import Path
        from django.conf import settings
        samples=json.loads((settings.BASE_DIR/'local_app/static/trace-examples.json').read_text())
        self.assertEqual(self.client.get('/trace-examples.json')['Content-Type'],'application/json')
        for name,body in samples.items():
            with self.subTest(name=name):
                r=self.client.post('/api/sessions',json.dumps(body),content_type='application/json');self.assertEqual(r.status_code,201);d=r.json();trace=d['output']['root_cause_trace']
                if name=='chain':self.assertEqual(trace['observed_data_paths'][0]['module_ids'],['1','2','3'])
                else:self.assertEqual(trace['operator_findings'][0]['status'],'INVALID_CONTRACT_OBSERVED')
                self.assertEqual(self.client.get('/api/sessions/'+d['id']+'/export').json()['root_cause_trace'],trace)
                r=self.client.post('/api/sessions/'+d['id']+'/edit',json.dumps(dict(body,revision=d['revision'])),content_type='application/json');self.assertEqual(r.status_code,200);self.assertEqual(r.json()['output']['root_cause_trace'],trace)
