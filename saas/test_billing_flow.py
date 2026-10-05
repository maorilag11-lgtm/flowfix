"""Payment lifecycle tests; Stripe is mocked, never charged."""
import json,time
from unittest.mock import MagicMock,patch
import stripe
from django.test import TestCase,override_settings,Client
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Account
from . import billing

def obj(data):return stripe.StripeObject.construct_from(data,None)

@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False,SESSION_COOKIE_SECURE=False,CSRF_COOKIE_SECURE=False,BILLING_ENABLED=True,STRIPE_SOLO_MONTHLY_PRICE='price_solo',STRIPE_AGENCY_MONTHLY_PRICE='price_agency',STRIPE_PRICE_ID='')
class BillingFlowTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user('billing@example.test',email='billing@example.test',password='test-password')
        self.account=Account.objects.create(user=self.user,customer='cus_owner',verified_email=self.user.email,email_verified_at=timezone.now())
        self.client.force_login(self.user)
        self.api=MagicMock()
        self.api.v1.subscriptions.list.return_value.data=[]
        self.api.v1.checkout.sessions.list.return_value.data=[]
        self.api.v1.checkout.sessions.create.return_value=obj({'url':'https://checkout.stripe.com/example'})
        self.api.v1.prices.retrieve.return_value=obj({'active':True,'currency':'eur','unit_amount':4900,'tax_behavior':'exclusive','recurring':{'interval':'month','interval_count':1,'usage_type':'licensed'}})
        self.patch=patch('saas.billing.client',return_value=self.api);self.patch.start();self.addCleanup(self.patch.stop)
    def post(self,url,data):return self.client.post(url,json.dumps(data),content_type='application/json')
    def subscription(self,status='active',paid=True,plan='price_solo'):
        return obj({'id':'sub_owner','status':status,'latest_invoice':{'status':'paid' if paid else 'open'},'items':{'data':[{'price':{'id':plan},'current_period_end':int(time.time())+86400}]}})
    def test_public_cannot_read_or_confirm(self):
        self.client.logout()
        self.assertEqual(self.client.get('/billing/').status_code,302)
        self.assertEqual(self.client.get('/api/billing/status').status_code,401)
        self.assertEqual(self.post('/api/billing/confirm',{'session_id':'cs_test'}).status_code,401)
    def test_checkout_requires_csrf(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/api/billing/checkout','{}',content_type='application/json').status_code,403)
    def test_monthly_price_and_tax_configuration(self):
        response=self.post('/api/billing/checkout',{'plan':'solo','price':'attacker'})
        self.assertEqual(response.status_code,200)
        data=self.api.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(data['line_items'],[{'price':'price_solo','quantity':1}])
        self.assertTrue(data['automatic_tax']['enabled'])
        self.assertIn('{CHECKOUT_SESSION_ID}',data['success_url'])
        self.account.refresh_from_db();self.assertIsNone(self.account.paid_until)
    def test_wrong_price_fails_closed(self):
        self.api.v1.prices.retrieve.return_value['unit_amount']=100
        self.assertEqual(self.post('/api/billing/checkout',{'plan':'solo'}).status_code,503)
        self.api.v1.checkout.sessions.create.assert_not_called()
    @override_settings(STRIPE_AUTOMATIC_TAX=False)
    def test_confirmed_no_vat_regime_is_server_controlled(self):
        response=self.post('/api/billing/checkout',{'plan':'solo','automatic_tax':True})
        self.assertEqual(response.status_code,200)
        data=self.api.v1.checkout.sessions.create.call_args.args[0]
        self.assertFalse(data['automatic_tax']['enabled'])
        self.assertEqual(data['line_items'],[{'price':'price_solo','quantity':1}])
    def test_unverified_cannot_pay(self):
        self.account.email_verified_at=None;self.account.save()
        self.assertNotEqual(self.post('/api/billing/checkout',{'plan':'solo'}).status_code,200)
        self.api.v1.checkout.sessions.create.assert_not_called()
    def test_existing_session_reused(self):
        self.api.v1.checkout.sessions.list.return_value.data=[obj({'id':'cs_existing','mode':'subscription','url':'https://checkout.stripe.com/existing','metadata':{'flowfix_price':'price_solo'}})]
        self.assertEqual(self.post('/api/billing/checkout',{'plan':'solo'}).json()['url'],'https://checkout.stripe.com/existing')
        self.api.v1.checkout.sessions.create.assert_not_called()
    def test_paid_subscriber_cannot_buy_twice(self):
        self.api.v1.subscriptions.list.return_value.data=[self.subscription()]
        self.assertEqual(self.post('/api/billing/checkout',{'plan':'solo'}).status_code,409)
        self.api.v1.checkout.sessions.create.assert_not_called()
    def test_return_for_other_customer_denied(self):
        self.api.v1.checkout.sessions.retrieve.return_value=obj({'customer':'cus_other','mode':'subscription','client_reference_id':str(self.user.pk),'status':'complete','payment_status':'paid'})
        self.assertEqual(self.post('/api/billing/confirm',{'session_id':'cs_stolen'}).status_code,404)
        self.api.v1.subscriptions.list.assert_not_called()
    def test_unpaid_return_does_not_activate(self):
        self.api.v1.checkout.sessions.retrieve.return_value=obj({'customer':'cus_owner','mode':'subscription','client_reference_id':str(self.user.pk),'status':'complete','payment_status':'unpaid'})
        self.assertFalse(self.post('/api/billing/confirm',{'session_id':'cs_pending'}).json()['active'])
        self.api.v1.subscriptions.list.assert_not_called()
    def test_paid_return_activates_actual_server_plan(self):
        self.api.v1.checkout.sessions.retrieve.return_value=obj({'customer':'cus_owner','mode':'subscription','client_reference_id':str(self.user.pk),'status':'complete','payment_status':'paid'})
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(plan='price_agency')]
        result=self.post('/api/billing/confirm',{'session_id':'cs_paid','plan':'enterprise'}).json()
        self.assertTrue(result['active']);self.assertEqual(result['plan'],'Agency')
        self.account.refresh_from_db();self.assertEqual(self.account.subscription_plan,'agency')
    def test_unpaid_invoice_never_grants_access(self):
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(paid=False)]
        billing.sync(self.account,self.api);self.assertIsNone(self.account.paid_until)
    def test_renewal_failure_and_cancellation_remove_paid_access(self):
        self.api.v1.subscriptions.list.return_value.data=[self.subscription()]
        billing.sync(self.account,self.api);self.assertIsNotNone(self.account.paid_until)
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(status='past_due',paid=False)]
        billing.sync(self.account,self.api);self.assertIsNone(self.account.paid_until)
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(status='canceled')]
        billing.sync(self.account,self.api);self.assertEqual(self.account.subscription,'')
    def test_status_pricing_matches_approved_offers(self):
        result=self.client.get('/api/billing/status').json()
        self.assertEqual([(o['plan'],o['amount']) for o in result['offers']],[('solo',4900),('agency',14900),('enterprise',39900)])
    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_billing_test')
    def test_signed_invoice_webhook_grants_once_without_browser(self):
        import hmac,hashlib
        from .models import BillingEvent
        self.api.v1.subscriptions.list.return_value.data=[self.subscription()]
        raw=json.dumps({'id':'evt_invoice_paid','object':'event','type':'invoice.paid','data':{'object':{'customer':'cus_owner'}}})
        stamp=str(int(time.time()))
        signature=hmac.new(b'whsec_billing_test',(stamp+'.'+raw).encode(),hashlib.sha256).hexdigest()
        for _ in range(2):
            response=self.client.post('/api/billing/webhook',raw,content_type='application/json',HTTP_STRIPE_SIGNATURE='t='+stamp+',v1='+signature)
            self.assertEqual(response.status_code,200)
        self.account.refresh_from_db()
        self.assertEqual(self.account.subscription_plan,'solo');self.assertIsNotNone(self.account.paid_until)
        self.assertEqual(BillingEvent.objects.filter(event_id='evt_invoice_paid').count(),1)
        self.assertEqual(self.api.v1.subscriptions.list.call_count,1)

    @override_settings(STRIPE_ENTERPRISE_MONTHLY_PRICE='price_enterprise')
    def test_enterprise_monthly_checkout_and_entitlement(self):
        self.api.v1.prices.retrieve.return_value['unit_amount']=39900
        response=self.post('/api/billing/checkout',{'plan':'enterprise','interval':'monthly'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.api.v1.checkout.sessions.create.call_args.args[0]['line_items'],[{'price':'price_enterprise','quantity':1}])
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(plan='price_enterprise')]
        billing.sync(self.account,self.api)
        from .catalog import rights
        self.assertEqual(self.account.subscription_plan,'enterprise')
        self.assertEqual(rights(self.account)['seats'],20)

    def test_scheduled_cancellation_keeps_access_until_period_end(self):
        sub=self.subscription();sub['cancel_at_period_end']=True
        self.api.v1.subscriptions.list.return_value.data=[sub]
        billing.sync(self.account,self.api)
        state=billing.summary(self.account)
        self.assertTrue(state['active']);self.assertTrue(state['cancel_at_period_end'])
        self.assertEqual(state['cancel_at'],state['paid_until'])
        from datetime import timedelta
        with patch('saas.billing.timezone.now',return_value=self.account.paid_until+timedelta(seconds=1)):
            self.assertFalse(billing.summary(self.account)['active'])
            from .access import entitlement
            self.assertFalse(entitlement(self.account)[0])

    def test_custom_cancel_date_limits_access_and_can_be_reversed(self):
        sub=self.subscription();sub['cancel_at']=int(time.time())+3600
        self.api.v1.subscriptions.list.return_value.data=[sub]
        billing.sync(self.account,self.api)
        self.assertEqual(int(self.account.paid_until.timestamp()),sub['cancel_at'])
        self.api.v1.subscriptions.list.return_value.data=[self.subscription()]
        billing.sync(self.account,self.api)
        self.assertFalse(self.account.cancel_at_period_end);self.assertIsNone(self.account.cancel_at)

    def test_renewal_and_payment_recovery_preserve_usage(self):
        self.account.usage=42;self.account.save()
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(status='past_due',paid=False)]
        billing.sync(self.account,self.api);self.assertFalse(billing.summary(self.account)['active'])
        sub=self.subscription();sub['items']['data'][0]['current_period_end']+=86400*30
        self.api.v1.subscriptions.list.return_value.data=[sub]
        billing.sync(self.account,self.api);self.account.refresh_from_db()
        self.assertTrue(billing.summary(self.account)['active'])
        self.assertEqual(self.account.usage,42);self.assertEqual(self.account.free_remaining,0)

    def test_refresh_uses_authenticated_customer_not_request_body(self):
        self.api.v1.subscriptions.list.return_value.data=[self.subscription()]
        result=self.post('/api/billing/refresh',{'customer':'cus_other'}).json()
        self.assertTrue(result['active'])
        self.assertEqual(self.api.v1.subscriptions.list.call_args.args[0]['customer'],'cus_owner')
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/api/billing/refresh','{}',content_type='application/json').status_code,403)
        self.client.logout();self.assertEqual(self.post('/api/billing/refresh',{}).status_code,401)

    @override_settings(BILLING_ENABLED=False)
    def test_disabled_refresh_never_calls_stripe(self):
        self.assertEqual(self.post('/api/billing/refresh',{}).status_code,503)
        self.api.v1.subscriptions.list.assert_not_called()

    def test_partial_subscription_list_does_not_revoke_access(self):
        self.api.v1.subscriptions.list.return_value=obj({'data':[],'has_more':True})
        with self.assertRaises(RuntimeError):billing.sync(self.account,self.api)

    def test_billing_page_and_script_are_english_by_default(self):
        self.assertContains(self.client.get('/billing/'),'YOUR MEMBERSHIP')
        self.assertContains(self.client.get('/billing.js'),'Cancellation scheduled')

    def test_checkout_keeps_dynamic_payment_methods_for_subscriptions(self):
        self.assertEqual(self.post('/api/billing/checkout',{'plan':'solo','payment_method_types':['attacker']}).status_code,200)
        data=self.api.v1.checkout.sessions.create.call_args.args[0]
        self.assertEqual(data['mode'],'subscription')
        # Stripe selects eligible enabled methods, including wallets and PayPal.
        self.assertNotIn('payment_method_types',data)
        self.assertNotIn('payment_intent_data',data)

    @override_settings(STRIPE_WEBHOOK_SECRET='whsec_billing_test')
    def test_delayed_payment_waits_for_paid_invoice_and_handles_failure(self):
        import hmac,hashlib
        def send(kind,event_id):
            raw=json.dumps({'id':event_id,'object':'event','type':kind,'data':{'object':{'customer':'cus_owner'}}})
            stamp=str(int(time.time()))
            signature=hmac.new(b'whsec_billing_test',(stamp+'.'+raw).encode(),hashlib.sha256).hexdigest()
            return self.client.post('/api/billing/webhook',raw,content_type='application/json',HTTP_STRIPE_SIGNATURE='t='+stamp+',v1='+signature)
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(paid=False)]
        self.assertEqual(send('checkout.session.completed','evt_pending').status_code,200)
        self.account.refresh_from_db();self.assertFalse(billing.summary(self.account)['active'])
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(paid=True)]
        self.assertEqual(send('checkout.session.async_payment_succeeded','evt_settled').status_code,200)
        self.account.refresh_from_db();self.assertTrue(billing.summary(self.account)['active'])
        self.api.v1.subscriptions.list.return_value.data=[self.subscription(status='unpaid',paid=False)]
        self.assertEqual(send('checkout.session.async_payment_failed','evt_failed').status_code,200)
        self.account.refresh_from_db();self.assertFalse(billing.summary(self.account)['active'])
