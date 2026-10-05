from html.parser import HTMLParser
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import hashlib
from .models import Account, Invitation, Analysis


class Forms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = attrs.get('action')
            self.forms[self.current] = {}
        if tag == 'input' and self.current and 'name' in attrs:
            self.forms[self.current][attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


@override_settings(ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False,
                   SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class AuthScreenTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        User.objects.create_user('ui@example.test', password='Test-only-strong-492!')

    def test_rendered_login_form_authenticates_and_preserves_next(self):
        page = self.client.get('/login/?next=/app/?view=history')
        fields = Forms(page.content.decode()).forms['/login/']
        fields.update(username='ui@example.test', password='Test-only-strong-492!')
        result = self.client.post('/login/', fields)
        self.assertRedirects(result, '/app/?view=history', fetch_redirect_response=False)
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_from_invitation_page_rejects_external_redirect(self):
        page = self.client.get('/signup/')
        fields = Forms(page.content.decode()).forms['/login/']
        fields.update(username='ui@example.test', password='Test-only-strong-492!',
                      next='https://example.org/')
        result = self.client.post('/login/', fields)
        self.assertRedirects(result, '/app/', fetch_redirect_response=False)

    def test_errors_retain_email_without_reflecting_password(self):
        page = self.client.get('/login/')
        fields = Forms(page.content.decode()).forms['/login/']
        fields.update(username='ui@example.test', password='wrong-secret-sentinel')
        result = self.client.post('/login/', fields)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'role="alert"')
        self.assertContains(result, 'ui@example.test')
        self.assertNotContains(result, 'wrong-secret-sentinel')
        self.assertNotIn('_auth_user_id', self.client.session)

    def create_public_account(self):
        page = self.client.get('/signup/')
        fields = Forms(page.content.decode()).forms['/signup/']
        self.assertNotIn('invitation', fields)
        fields.update(username='new@example.test', password1='Signup-test-only-348!',
                      password2='Signup-test-only-348!', acknowledge='yes')
        result = self.client.post('/signup/', fields)
        self.assertRedirects(result, '/app/', fetch_redirect_response=False)
        return User.objects.get(username='new@example.test')

    def test_public_account_gets_first_diagnosis_without_beta_access(self):
        user = self.create_public_account()
        self.assertIsNone(Account.objects.get(user=user).beta_until)
        self.assertEqual(Account.objects.get(user=user).free_remaining, 3)
        self.assertEqual(self.client.get('/app/').status_code, 200)
        result = self.client.post('/api/sessions', {'error': 'HTTP 422'}, content_type='application/json',
                                  HTTP_X_FLOWFIX_TOKEN=self.client.cookies['csrftoken'].value)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()['accounting']['reason'], 'free_diagnosis')
        self.assertEqual(Account.objects.get(user=user).free_remaining, 2)

    def test_existing_account_can_activate_matching_invitation_once(self):
        user = self.create_public_account()
        invite = Invitation.objects.create(email=user.email, digest=hashlib.sha256(b'BETA-CODE').hexdigest(),
                                           expires=timezone.now()+timedelta(days=1))
        fields = Forms(self.client.get('/beta/').content.decode()).forms['/beta/']
        fields.update(invitation='BETA-CODE', acknowledge='yes')
        result = self.client.post('/beta/', fields)
        self.assertRedirects(result, '/app/', fetch_redirect_response=False)
        invite.refresh_from_db()
        self.assertTrue(invite.used)
        until = Account.objects.get(user=user).beta_until
        self.assertGreater(until, timezone.now())
        self.assertContains(self.client.post('/beta/', fields), 'invitation is invalid')
        self.assertEqual(Account.objects.get(user=user).beta_until, until)

    def test_beta_route_requires_valid_invitation(self):
        fields = Forms(self.client.get('/beta/').content.decode()).forms['/beta/']
        fields.update(username='beta@example.test', password1='Signup-test-only-348!',
                      password2='Signup-test-only-348!', acknowledge='yes', invitation='')
        self.assertContains(self.client.post('/beta/', fields), 'invitation is invalid')
        self.assertFalse(User.objects.filter(username='beta@example.test').exists())
