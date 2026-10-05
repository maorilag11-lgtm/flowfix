import copy
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Account,Analysis,DiagnosticUsage
from local_app.service import analyze


@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False,
                   SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False)
class AccessContractTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('access@example.test',email='access@example.test',password='Access-test-938!')
        self.account=Account.objects.create(user=self.user,verified_email=self.user.email,email_verified_at=timezone.now())
        self.client.force_login(self.user)
        self.clean,self.output=analyze({'error':'HTTP 422'},'fixture')

    def post(self,url,data=None):
        return self.client.post(url,data=data or {'error':'HTTP 422'},content_type='application/json')

    def calculated(self,status='DIAGNOSIS_CANDIDATE',confidence='medium'):
        output=copy.deepcopy(self.output)
        output['response'].update(status=status,confidence=confidence,diagnosis='Test candidate')
        return patch('saas.views.analyze',return_value=(self.clean,output))

    def test_three_free_analyses_then_solo_without_monthly_reset(self):
        for remaining in [2,1,0]:
            with self.calculated():result=self.post('/api/sessions')
            self.assertEqual(result.status_code,201)
            self.account.refresh_from_db();self.assertEqual(self.account.free_remaining,remaining)
            self.assertEqual(result.json()['accounting']['reason'],'free_diagnosis')
        self.assertEqual(DiagnosticUsage.objects.count(),3)
        denied=self.post('/api/sessions');self.assertEqual(denied.status_code,409)
        self.assertIn('Solo',denied.json()['error'])
        self.account.usage_month='2000-01';self.account.save()
        self.assertEqual(self.post('/api/sessions').status_code,409)
        sid=result.json()['id']
        self.assertEqual(self.client.get('/api/sessions/'+sid).status_code,200)
        self.assertEqual(self.post('/api/sessions/'+sid+'/delete',{'revision':1}).status_code,200)
        self.account.refresh_from_db();self.assertEqual(self.account.free_remaining,0)
        self.assertEqual(DiagnosticUsage.objects.filter(analysis_id=None).count(),1)
        self.assertFalse(self.client.get('/api/settings').json()['can_start_trial'])
        self.assertEqual(self.post('/api/access/trial',{}).status_code,409)

    def test_all_inconclusive_outcomes_preserve_credit(self):
        for status in ['MULTIPLE_CANDIDATES','INSUFFICIENT_EVIDENCE','WEAK_EVIDENCE','CONTRADICTED','UNKNOWN']:
            with self.subTest(status=status),self.calculated(status):result=self.post('/api/sessions')
            self.assertEqual(result.status_code,201)
            self.assertFalse(result.json()['accounting']['counted'])
        self.account.refresh_from_db()
        self.assertEqual(self.account.free_remaining,3)
        self.assertEqual(self.account.usage,0)

    def test_real_engine_three_debits_then_structured_paywall(self):
        import json
        value='{"amount":12,}'
        body={'error':'JSON syntax error','module':'5',
              'blueprint':json.dumps({'flow':[{'id':'5','module':'json.parse','parameters':{'json_text':value}}]}),
              'json_field_observation':{'module_id':'5','field_path':['parameters','json_text'],
                  'execution_value':value,'expected_format':'json','value_origin':'static',
                  'format_source':'Synthetic field contract requiring JSON text',
                  'error_kind':'JSON_SYNTAX','error_source':'Synthetic failed-execution fixture'}}
        self.assertEqual(self.client.get('/api/settings').json()['free_remaining'],3)
        for remaining in [2,1,0]:
            result=self.post('/api/sessions',body)
            self.assertEqual(result.status_code,201,result.content)
            self.assertTrue(result.json()['accounting']['counted'])
            self.assertEqual(self.client.get('/api/settings').json()['free_remaining'],remaining)
        sid=result.json()['id']
        with patch('saas.views.analyze') as engine:
            for _ in range(2):
                denied=self.post('/api/sessions',body)
                self.assertEqual(denied.status_code,409)
                self.assertEqual(denied.json()['code'],'free_analyses_exhausted')
                self.assertEqual(denied.json()['upgrade_url'],'/?upgrade=1#pricing')
            engine.assert_not_called()
        self.assertEqual(Analysis.objects.count(),3)
        self.assertEqual(DiagnosticUsage.objects.count(),3)
        self.assertEqual(self.client.get('/api/settings').json()['free_remaining'],0)
        self.assertEqual(self.client.get('/api/sessions/'+sid).status_code,200)

    def test_monthly_credit_counts_only_conclusive_result(self):
        self.account.beta_until=timezone.now()+timedelta(days=1);self.account.save()
        with self.calculated('MULTIPLE_CANDIDATES'):self.post('/api/sessions')
        with self.calculated():result=self.post('/api/sessions')
        self.account.refresh_from_db()
        self.assertEqual(self.account.usage,1)
        self.assertEqual(result.json()['accounting']['reason'],'monthly_quota')

    def test_low_confidence_candidate_is_not_counted(self):
        with self.calculated(confidence='low'):result=self.post('/api/sessions')
        self.assertEqual(result.json()['accounting']['reason'],'inconclusive')
        self.account.refresh_from_db();self.assertEqual(self.account.free_remaining,3)

    @override_settings(AGENCY_TRIAL_ENABLED=True)
    def test_trial_starts_once_and_expires_without_payment(self):
        start=timezone.now()
        self.assertEqual(self.post('/api/access/trial',{}).status_code,200)
        self.account.refresh_from_db()
        self.assertGreater(self.account.agency_trial_until,start+timedelta(days=13,hours=23))
        self.assertLess(self.account.agency_trial_until,timezone.now()+timedelta(days=14,seconds=1))
        self.assertEqual(self.post('/api/access/trial',{}).status_code,409)
        with self.calculated():
            self.assertEqual(self.post('/api/sessions').json()['accounting']['reason'],'included_in_trial')
            self.assertEqual(self.post('/api/sessions').status_code,201)
        self.account.refresh_from_db();self.assertEqual(self.account.usage,0)
        self.assertIsNone(self.account.customer)
        self.account.agency_trial_until=timezone.now()-timedelta(seconds=1);self.account.save()
        self.assertEqual(self.post('/api/sessions').status_code,409)
        self.assertEqual(self.post('/api/access/trial',{}).status_code,409)

    def test_stale_revision_never_consumes_another_credit(self):
        self.account.beta_until=timezone.now()+timedelta(days=1);self.account.save()
        with self.calculated():created=self.post('/api/sessions').json()
        self.assertEqual(self.post('/api/sessions/'+created['id']+'/edit',{'revision':0,'error':'HTTP 429'}).status_code,409)
        self.account.refresh_from_db();self.assertEqual(self.account.usage,1)
        self.assertEqual(DiagnosticUsage.objects.count(),1)

    def test_result_and_debit_roll_back_together(self):
        with self.calculated(),patch('saas.access.DiagnosticUsage.objects.create',side_effect=RuntimeError('test failure')):
            self.assertEqual(self.post('/api/sessions').status_code,503)
        self.assertFalse(Analysis.objects.exists())
        self.account.refresh_from_db();self.assertEqual(self.account.free_remaining,3)
