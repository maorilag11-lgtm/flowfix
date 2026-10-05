from django.test import SimpleTestCase, override_settings
from django.conf import settings
from django.http import Http404
from .marketing import serve, PUBLIC_FILES

@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False,MARKETING_URL='/')
class MarketingTests(SimpleTestCase):
    def test_pricing_links_to_each_selected_plan(self):
        response=self.client.get('/?upgrade=1')
        for plan in ('solo','agency','enterprise'):
            self.assertContains(response,'data-product-route="/billing/?plan='+plan+'"')
            from urllib.parse import urlencode
            self.assertRedirects(self.client.get('/billing/?plan='+plan),
                '/login/?'+urlencode({'next':'/billing/?plan='+plan}),fetch_redirect_response=False)

    def test_current_home_is_exact_source_and_scripts_are_authorized(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,(settings.BASE_DIR/'marketing/index.html').read_bytes())
        self.assertIn("'sha256-",response['Content-Security-Policy'])
        self.assertNotIn("script-src 'self' 'unsafe-inline'",response['Content-Security-Policy'])

    def test_bridge_and_app_remain_separate(self):
        self.assertRedirects(self.client.get('/login.html'),'/login/',fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/login.html?mode=signup'),'/signup/',fetch_redirect_response=False)
        response=self.client.get('/login/')
        self.assertNotIn('unsafe-inline',response['Content-Security-Policy'])
        self.assertContains(response,'href="/"')

    def test_only_reviewed_public_files_are_available(self):
        for name in PUBLIC_FILES-{'login.html'}:
            response=self.client.get('/'+name)
            self.assertEqual(response.status_code,200,name)
            response.close()
        for name in ['../saas/settings.py','.env','INTEGRATION.md']:
            with self.assertRaises(Http404):serve(None,name)
