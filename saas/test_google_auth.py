from unittest.mock import patch,MagicMock
from urllib.parse import urlparse,parse_qs
from django.test import TestCase,override_settings,Client
from django.contrib.auth.models import User
from .models import Account
from . import google_auth

@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False,GOOGLE_CLIENT_ID='client.apps.googleusercontent.com',GOOGLE_CLIENT_SECRET='test-only',PUBLIC_URL='https://example.test')
class GoogleAuthTests(TestCase):
    def test_google_form_redirect_is_allowed_only_on_start_page(self):
        for response in (self.client.get('/auth/google/'), self.client.post('/auth/google/', {'acknowledge':'yes'})):
            self.assertIn("form-action 'self' https://accounts.google.com", response['Content-Security-Policy'])
        self.assertNotIn('accounts.google.com', self.client.get('/login/')['Content-Security-Policy'])
    def begin(self):
        response=self.client.post('/auth/google/',{'acknowledge':'yes'})
        self.assertEqual(response.status_code,302)
        return self.client.session['google_oauth']
    def finish(self,flow,**changes):
        claims={'sub':'subject-1','email':'new@gmail.com','email_verified':True,'nonce':flow['nonce']}
        claims.update(changes)
        with patch('saas.google_auth.exchange',return_value=claims):
            return self.client.get('/auth/google/callback/',{'state':flow['state'],'code':'code'})
    def test_start_has_state_nonce_pkce_and_minimal_scope(self):
        response=self.client.post('/auth/google/',{'acknowledge':'yes'})
        params=parse_qs(urlparse(response.url).query)
        self.assertEqual(params['scope'],['openid email profile'])
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertEqual(params['redirect_uri'],['https://example.test/auth/google/callback/'])
        self.assertNotIn('test-only',response.url)
        self.assertTrue(params['state']);self.assertTrue(params['nonce'])
    def test_new_account_has_three_credits_and_verified_google_email(self):
        self.assertEqual(self.finish(self.begin()).url,'/app/')
        account=Account.objects.get(google_subject='subject-1')
        self.assertEqual(account.free_remaining,3);self.assertIsNotNone(account.email_verified_at)
        self.assertFalse(account.user.has_usable_password())
    def test_repeat_login_does_not_reset_credits(self):
        self.finish(self.begin());account=Account.objects.get();account.free_remaining=1;account.save()
        self.client.logout();self.finish(self.begin());account.refresh_from_db()
        self.assertEqual(account.free_remaining,1);self.assertEqual(Account.objects.count(),1)
    def test_existing_email_is_not_automatically_linked(self):
        user=User.objects.create_user('new@gmail.com',email='new@gmail.com');Account.objects.create(user=user)
        self.assertEqual(self.finish(self.begin()).status_code,409)
        self.assertNotIn('_auth_user_id',self.client.session)
    def test_authenticated_account_can_link_matching_email(self):
        user=User.objects.create_user('new@gmail.com',email='new@gmail.com');account=Account.objects.create(user=user,free_remaining=1)
        self.client.force_login(user);self.assertEqual(self.finish(self.begin()).status_code,302)
        account.refresh_from_db();self.assertEqual(account.google_subject,'subject-1');self.assertEqual(account.free_remaining,1)
    def test_mismatched_link_denied(self):
        user=User.objects.create_user('other@gmail.com',email='other@gmail.com');Account.objects.create(user=user)
        self.client.force_login(user);self.assertEqual(self.finish(self.begin()).status_code,409)
    def test_state_replay_and_nonce_fail_closed(self):
        flow=self.begin()
        self.assertEqual(self.client.get('/auth/google/callback/',{'state':'wrong','code':'code'}).status_code,400)
        self.assertEqual(self.finish(flow).status_code,400)
        flow=self.begin();self.assertEqual(self.finish(flow,nonce='wrong').status_code,400)
        self.assertEqual(User.objects.count(),0)
    def test_expired_flow_does_not_exchange_code(self):
        flow=self.begin();session=self.client.session;flow['created']=0;session['google_oauth']=flow;session.save()
        with patch('saas.google_auth.exchange') as exchange:
            self.assertEqual(self.finish(flow).status_code,400)
            exchange.assert_not_called()
    def test_unverified_and_third_party_email(self):
        self.assertEqual(self.finish(self.begin(),email_verified=False).status_code,400)
        self.finish(self.begin(),email='new@example.test')
        self.assertIsNone(Account.objects.get().email_verified_at)
    def test_inactive_user_denied(self):
        user=User.objects.create_user('new@gmail.com',email='new@gmail.com',is_active=False)
        Account.objects.create(user=user,google_subject='subject-1')
        self.assertEqual(self.finish(self.begin()).status_code,403)
        self.assertNotIn('_auth_user_id',self.client.session)
    def test_start_requires_csrf_and_acknowledgement(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/auth/google/',{'acknowledge':'yes'}).status_code,403)
        self.assertEqual(self.client.post('/auth/google/',{}).status_code,400)
    @override_settings(GOOGLE_CLIENT_SECRET='')
    def test_unconfigured_is_safe(self):
        self.assertEqual(self.client.get('/auth/google/').status_code,503)
    def test_exchange_verifies_token_with_expected_audience(self):
        response=MagicMock();response.json.return_value={'id_token':'signed-token'}
        with patch('saas.google_auth.requests.post',return_value=response) as post,patch('saas.google_auth.id_token.verify_oauth2_token',return_value={'sub':'verified'}) as verify:
            self.assertEqual(google_auth.exchange('one-time-code',{'verifier':'pkce'})['sub'],'verified')
            self.assertEqual(verify.call_args.args[0],'signed-token')
            self.assertEqual(verify.call_args.args[2],'client.apps.googleusercontent.com')
            self.assertEqual(post.call_args.kwargs['timeout'],15)
    def test_google_cancel_does_not_create_user(self):
        flow=self.begin();result=self.client.get('/auth/google/callback/',{'state':flow['state'],'error':'access_denied'})
        self.assertEqual(result.status_code,400);self.assertEqual(User.objects.count(),0)
