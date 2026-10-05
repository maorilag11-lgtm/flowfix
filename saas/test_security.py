"""Security regressions use an isolated Django test database and synthetic data."""
import copy
import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from .models import Account, Analysis, Throttle
from .security_config import validate_production
from verification.test_root_cause_trace import fixture


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False)
class SecurityTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('secure@example.test',email='secure@example.test',password='Strong-test-password-827!')
        Account.objects.create(user=self.user,beta_until=timezone.now()+timedelta(days=1))
        self.client.force_login(self.user)

    def post(self, url, body, **extra):
        return self.client.post(url,json.dumps(body),content_type='application/json',**extra)

    def test_sliced_secrets_masked_before_storage_and_edit_history(self):
        f=fixture()
        for path in [['headers','Authorization'],['access_token'],['client-secret','nested'],['Cookie',0]]:
            with self.subTest(path=path):
                context=copy.deepcopy(f['context']['root_cause_context'])
                context['observations'][0].update(data_path=path,observed_value='SYNTHETIC_PRIVATE_VALUE')
                body={'error':f['error'],'blueprint':f['blueprint'],'module':'3','root_cause_context':context}
                r=self.post('/api/sessions',body)
                self.assertEqual(r.status_code,201)
                data=r.json();url='/api/sessions/'+data['id']
                self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',r.content.decode())
                self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',json.dumps(Analysis.objects.get(pk=data['id']).data))
                r=self.post(url+'/edit',dict(body,revision=1,error='HTTP 500'))
                self.assertEqual(r.status_code,200)
                self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',r.content.decode())
                self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',self.client.get(url+'/export').content.decode())

    def test_delete_password_attempts_limited_across_ips_before_hashing(self):
        for n in range(5):
            self.assertEqual(self.post('/api/account/delete',{'password':'wrong'},REMOTE_ADDR=f'192.0.2.{n+1}').status_code,403)
        with patch.object(User,'check_password') as check:
            self.assertEqual(self.post('/api/account/delete',{'password':'wrong'},REMOTE_ADDR='192.0.2.50').status_code,429)
            check.assert_not_called()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        Throttle.objects.update(started=timezone.now()-timedelta(minutes=16))
        self.assertEqual(self.post('/api/account/delete',{'password':'wrong'}).status_code,403)

    def test_login_identity_limit_survives_ip_rotation_and_case_changes(self):
        self.client.logout()
        # Mock the expensive form only; exercise real limits and database counters.
        from django.http import HttpResponse
        with patch('django.contrib.auth.views.LoginView.post',return_value=HttpResponse('form')) as authenticate:
            for n in range(30):
                self.assertEqual(self.client.post('/login/',{'username':'Secure@example.test','password':'wrong'},REMOTE_ADDR=f'192.0.2.{n+1}').status_code,200)
            self.assertEqual(self.client.post('/login/',{'username':'secure@example.test','password':'wrong'},REMOTE_ADDR='192.0.2.99').status_code,429)
            self.assertEqual(authenticate.call_count,30)
            Throttle.objects.update(started=timezone.now()-timedelta(minutes=16))
            self.assertEqual(self.client.post('/login/',{'username':'secure@example.test','password':'wrong'}).status_code,200)

    @override_settings(TRUST_CLIENT_IP=False)
    def test_untrusted_forwarding_headers_cannot_bypass_ip_limit(self):
        self.client.logout()
        from django.http import HttpResponse
        with patch('django.contrib.auth.views.LoginView.post',return_value=HttpResponse('form')):
            for n in range(10):
                self.assertEqual(self.client.post('/login/',{'username':f'{n}@example.test'},HTTP_X_FLOWFIX_CLIENT_IP=f'192.0.2.{n+1}',HTTP_X_FORWARDED_FOR=f'192.0.2.{n+1}').status_code,200)
            self.assertEqual(self.client.post('/login/',{'username':'other@example.test'},HTTP_X_FLOWFIX_CLIENT_IP='192.0.2.99').status_code,429)

    @override_settings(BILLING_ENABLED=True,STRIPE_PRICE_ID='price_test')
    def test_billing_calls_share_per_user_limit(self):
        Account.objects.filter(user=self.user).update(customer='cus_test')
        api=MagicMock();api.v1.billing_portal.sessions.create.return_value.url='https://billing.stripe.com/test'
        api.v1.checkout.sessions.create.return_value.url='https://checkout.stripe.com/test'
        with patch('saas.billing.client',return_value=api),patch('saas.billing.sync'):
            for n in range(30):
                self.assertEqual(self.post('/api/billing/portal',{},REMOTE_ADDR=f'192.0.2.{n+1}').status_code,200)
            self.assertEqual(self.post('/api/billing/checkout',{}).status_code,429)
            api.v1.checkout.sessions.create.assert_not_called()

    def test_security_headers_on_private_responses(self):
        r=self.client.get('/api/settings')
        self.assertEqual(r['Cache-Control'],'no-store')
        self.assertEqual(r['X-Content-Type-Options'],'nosniff')
        self.assertEqual(r['X-Frame-Options'],'DENY')
        self.assertIn("frame-ancestors 'none'",r['Content-Security-Policy'])


class ProductionConfigTests(SimpleTestCase):
    def test_managed_postgres_url_uses_tls_and_decodes_credentials(self):
        from .security_config import postgres_url_config
        config=postgres_url_config('postgresql://user:p%40ss%2Fword@internal.test:5433/flowfix')
        self.assertEqual(config['HOST'],'internal.test')
        self.assertEqual(config['PASSWORD'],'p@ss/word')
        self.assertEqual(config['PORT'],'5433')
        self.assertEqual(config['OPTIONS'],{'sslmode':'require'})

    def test_invalid_managed_database_url_never_reflects_credentials(self):
        from .security_config import postgres_url_config
        for value in ['https://user:PRIVATE_SENTINEL@host/db','postgres://user:PRIVATE_SENTINEL@host:bad/db',
                      'postgres://user:PRIVATE_SENTINEL@host/db?sslmode=disable',
                      'postgres://user:PRIVATE_SENTINEL@host/db?options=bad',
                      'postgres://user:PRIVATE_SENTINEL@host/db?sslmode=require&sslmode=disable',
                      'postgres://user:PRIVATE_SENTINEL@host/']:
            with self.subTest(value=value),self.assertRaises(RuntimeError) as error:
                postgres_url_config(value)
            self.assertNotIn('PRIVATE_SENTINEL',str(error.exception))

    def test_valid_explicit_https_origin(self):
        validate_production('TEST-ONLY-secret-with-diverse-characters-0123456789-abcdef',['app.example.test'],'https://app.example.test')

    def test_unsafe_configurations_refused(self):
        strong='TEST-ONLY-secret-with-diverse-characters-0123456789-abcdef'
        cases=[('short',['app.example.test'],'https://app.example.test'),
               ('x'*60,['app.example.test'],'https://app.example.test'),
               ('django-insecure-'+strong,['app.example.test'],'https://app.example.test'),
               (strong,['*'],'https://app.example.test'),
               (strong,['.example.test'],'https://app.example.test')]
        cases += [(strong,['app.example.test'],url) for url in ['https://other.test','http://app.example.test','https://user:pass@app.example.test','https://app.example.test/path','https://app.example.test?x=1','https://app.example.test#x','https://app.example.test:bad']]
        for args in cases:
            with self.subTest(args=args),self.assertRaises(RuntimeError):validate_production(*args)

@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False,
                   EMAIL_HOST='smtp.example.test',DEFAULT_FROM_EMAIL='support@example.test',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   PUBLIC_URL='https://app.example.test')
class SecurityAuditRegressionTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('audit@example.test',email='audit@example.test',password='Audit-only-password-839!')
        Account.objects.create(user=self.user,beta_until=timezone.now()+timedelta(days=30))

    def test_reset_identity_limit_across_ips_without_account_enumeration(self):
        from django.core import mail
        for n in range(5):
            r=self.client.post('/reset/',{'email':'AUDIT@example.test'},REMOTE_ADDR=f'192.0.2.{n+1}')
            self.assertEqual(r.status_code,302)
        self.assertEqual(len(mail.outbox),5)
        r=self.client.post('/reset/',{'email':'audit@example.test'},REMOTE_ADDR='192.0.2.99')
        self.assertEqual(r.status_code,429)
        self.assertEqual(len(mail.outbox),5)
        for n in range(5):
            self.assertEqual(self.client.post('/reset/',{'email':'absent@example.test'},REMOTE_ADDR=f'198.51.100.{n+1}').status_code,302)
        self.assertEqual(self.client.post('/reset/',{'email':'absent@example.test'},REMOTE_ADDR='198.51.100.99').status_code,429)

    def test_reset_link_uses_canonical_origin_not_request_host(self):
        from django.core import mail
        self.client.post('/reset/',{'email':'audit@example.test'})
        self.assertIn('https://app.example.test/reset/',mail.outbox[0].body)
        self.assertNotIn('testserver/reset/',mail.outbox[0].body)

    def test_diagnostic_limit_shared_by_account_across_ips_and_operations(self):
        self.client.force_login(self.user)
        from saas.views import limited
        from django.test import RequestFactory
        req=RequestFactory().post('/');req.user=self.user
        for _ in range(120):limited(req,'diagnostic-user',120,identity=self.user.pk)
        with patch('saas.views.analyze') as analyze:
            r=self.client.post('/api/sessions',json.dumps({'error':'HTTP 422'}),content_type='application/json',REMOTE_ADDR='192.0.2.99')
            self.assertEqual(r.status_code,429);analyze.assert_not_called()
        record=Analysis.objects.create(owner=self.user,data={'revision':1})
        for operation in ['edit','answer']:
            with patch('saas.views.mutate') as mutate:
                r=self.client.post(f'/api/sessions/{record.pk}/{operation}',json.dumps({'revision':1}),content_type='application/json',REMOTE_ADDR='198.51.100.99')
                self.assertEqual(r.status_code,429);mutate.assert_not_called()

    def test_archived_analyses_still_count_towards_storage_limit(self):
        from uuid import uuid4
        Account.objects.filter(user=self.user).update(subscription_plan='solo')
        Analysis.objects.bulk_create([Analysis(id=uuid4(),owner=self.user,data={}) for _ in range(500)])
        Analysis.objects.update(created_at=timezone.now()-timedelta(days=60))
        self.client.force_login(self.user)
        with patch('saas.views.analyze') as analyze:
            r=self.client.post('/api/sessions',json.dumps({'error':'HTTP 422'}),content_type='application/json')
            self.assertEqual(r.status_code,409);analyze.assert_not_called()
