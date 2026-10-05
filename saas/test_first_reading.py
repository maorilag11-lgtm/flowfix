"""Synthetic error-only acceptance cases. Not an accuracy benchmark."""
import copy
import json
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from .models import Account, Analysis
from local_app.service import analyze, enrich_first_reading

@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False)
class FirstReadingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('triage@example.test')
        Account.objects.create(user=self.user)
        self.client.force_login(self.user)
    def test_error_only_produces_useful_nonconclusive_answer_and_export(self):
        response=self.client.post('/api/sessions',json.dumps({'error':'HTTP 422 Unprocessable Entity'}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        d=response.json();first=d['output']['first_reading']
        self.assertEqual(first['title'],'Données refusées par le service')
        self.assertTrue(first['checks']);self.assertTrue(first['possibilities'])
        self.assertFalse(first['conclusive']);self.assertFalse(d['output']['correction_applicable'])
        self.assertTrue(d['output']['clarification']['question'])
        self.assertTrue(d['accounting']['counted'])
        self.assertEqual(Account.objects.get(user=self.user).free_remaining,2)
        exported=self.client.get('/api/sessions/'+d['id']+'/export').json()
        self.assertEqual(exported['first_reading'],first)
    def test_common_families_without_blueprint(self):
        for error,title in [('HTTP 401 Unauthorized','Authentification'),('HTTP 403 Forbidden','Accès'),('HTTP 429 Too Many Requests','Limite'),('BundleValidationError: Missing value of required parameter email','Entrée'),('ModuleTimeoutError','Délai'),('ConnectionError','Connexion'),('HTTP 503 Service Unavailable','Erreur côté'),('HTTP 404 Not Found','Ressource'),('HTTP 400 Bad Request','Requête'),('Invalid JSON syntax','Syntaxe')]:
            with self.subTest(error=error):
                _,out=analyze({'error':error},'triage')
                self.assertTrue(out['first_reading']['title'].startswith(title))
                self.assertTrue(out['first_reading']['checks'])
                self.assertFalse(out['first_reading']['execution_verified'])
    def test_unknown_symptom_gets_checks_without_invented_cause(self):
        _,out=analyze({'error':'ça ne fonctionne pas'},'unknown')
        self.assertEqual(out['first_reading']['possibilities'],[])
        self.assertGreater(len(out['first_reading']['checks']),0)
        self.assertFalse(out['correction_applicable'])
    def test_module_number_does_not_become_status_code(self):
        _,out=analyze({'error':'Erreur dans le module ID: 401'},'module-id')
        self.assertEqual(out['first_reading']['possibilities'],[])
    def test_multiple_errors_remain_separate_possibilities(self):
        _,out=analyze({'error':'HTTP 401 Unauthorized\nHTTP 429 Too Many Requests'},'multi')
        self.assertEqual(len(out['first_reading']['possibilities']),2)
    def test_no_arbitrary_secret_in_first_reading(self):
        _,out=analyze({'error':'HTTP 422 api_key=NEVER_SHARE_THIS_SECRET'},'secret')
        self.assertNotIn('NEVER_SHARE_THIS_SECRET',json.dumps(out))
    def test_legacy_get_adds_reading_without_changing_stored_analysis(self):
        inputs,out=analyze({'error':'HTTP 422 Unprocessable Entity'},'legacy')
        out.pop('first_reading')
        d={'id':'e48b411e-53b9-476a-8003-7e013f0f2771','inputs':inputs,'output':out,'revision':1}
        record=Analysis.objects.create(id=d['id'],owner=self.user,data=d)
        before=copy.deepcopy(d)
        res=self.client.get('/api/sessions/'+d['id'])
        self.assertEqual(res.status_code,200);self.assertTrue(res.json()['output']['first_reading']['checks'])
        record.refresh_from_db();self.assertEqual(record.data,before)

    def test_named_field_is_used_without_inventing_a_replacement(self):
        _,out=analyze({'error':'HTTP 422 product_id must be a valid integer'},'named')
        first=out['first_reading']
        self.assertIn('product_id',first['checks'][0])
        self.assertIn('un entier',first['checks'][0])
        self.assertFalse(out['correction_applicable'])

    def test_error_body_names_empty_field_without_blueprint(self):
        _,out=analyze({'error':'HTTP 422 {"suberrors":[{"field":"to","message":"Value is empty or null","provided":null}]}'},'empty-field')
        self.assertIn('« to »',out['first_reading']['explanation'])
        self.assertIn('mapping',out['first_reading']['checks'][0])
        self.assertFalse(out['correction_applicable'])
