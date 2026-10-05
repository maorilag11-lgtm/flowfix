from datetime import datetime,timezone as tz
import stripe
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Account,BillingEvent
from .catalog import price_catalog,PLANS
from django.shortcuts import render,redirect
from django.utils import timezone
from django.middleware.csrf import get_token
from django.views.decorators.http import require_GET
from uuid import uuid4

from .views import endpoint,error,limited

MONTHLY_PRICES={'solo':4900,'agency':14900,'enterprise':39900}

def page(request):
    if not request.user.is_authenticated:
        from urllib.parse import urlencode
        plan=request.GET.get('plan')
        destination='/billing/' + ('?plan='+plan if plan in MONTHLY_PRICES else '')
        return redirect('/login/?'+urlencode({'next':destination}))
    return render(request,'billing.html',{'support':settings.SUPPORT_EMAIL or 'FlowFix.contact.support@gmail.com','marketing_url':settings.MARKETING_URL})

def summary(account):
    active=account.subscription_status in ['active','trialing'] and bool(account.paid_until and account.paid_until>timezone.now())
    return {'active':active,'plan':PLANS.get(account.subscription_plan,{'name':'Abonnement'})['name'] if active else None,'status':account.subscription_status,'paid_until':account.paid_until,'plan_id':account.subscription_plan,'cancel_at_period_end':account.cancel_at_period_end,'cancel_at':account.cancel_at,'has_customer':bool(account.customer),'has_subscription':bool(account.subscription)}

@require_GET
@endpoint
def status(request,body):
    account=Account.objects.get(user=request.user)
    from .email_verification import verified
    return JsonResponse({**summary(account),'csrf':get_token(request),'email':request.user.email,'verified':verified(account),'enabled':settings.BILLING_ENABLED,'offers':[{'plan':p,'name':PLANS[p]['name'],'amount':amount,'available':settings.BILLING_ENABLED and any(r=={'plan':p,'interval':'monthly'} for r in price_catalog().values())} for p,amount in MONTHLY_PRICES.items()]})

@require_POST
@endpoint
def confirm(request,body):
    session_id=body.get('session_id','')
    if not isinstance(session_id,str) or not session_id.startswith('cs_') or len(session_id)>255:return error('Session de paiement invalide.',400)
    if limited(request,'billing-confirm',30,identity=request.user.pk):return error('Réessayez dans quelques minutes.',429)
    api=client()
    with transaction.atomic():
        account=Account.objects.select_for_update().get(user=request.user)
        if not account.customer:return error('Session introuvable.',404)
        session=api.v1.checkout.sessions.retrieve(session_id)
        if session.get('customer')!=account.customer or session.get('client_reference_id')!=str(request.user.pk) or session.get('mode')!='subscription':return error('Session introuvable.',404)
        if session.get('status')=='complete' and session.get('payment_status') in ['paid','no_payment_required']:sync(account,api)
        return JsonResponse({**summary(account),'payment_status':session.get('payment_status'),'checkout_status':session.get('status')})


def client():
    if not settings.BILLING_ENABLED or not all([settings.STRIPE_SECRET_KEY,settings.STRIPE_WEBHOOK_SECRET,price_catalog()]):raise RuntimeError('Billing unavailable')
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY,max_network_retries=2)
def sync(account,api):
    subscriptions=api.v1.subscriptions.list({'customer':account.customer,'status':'all','limit':100,'expand':['data.latest_invoice']})
    # Fail closed if the response is incomplete; never revoke based on a partial list.
    if subscriptions.get('has_more',False) is True:raise RuntimeError('Subscription reconciliation requires pagination')
    eligible=[]
    for sub in subscriptions.data:
        items=[i for i in sub['items']['data'] if i['price']['id'] in price_catalog()]
        invoice=sub.get('latest_invoice')
        paid=hasattr(invoice,'get') and invoice.get('status')=='paid'
        if items and (sub.status=='trialing' or (sub.status=='active' and paid)):
            end=max(i.get('current_period_end',sub.get('current_period_end',0)) for i in items)
            # Mixed commercial tiers are ambiguous: fail closed rather than grant a higher tier.
            plans={price_catalog()[i['price']['id']]['plan'] for i in items}
            if len(plans)!=1:raise RuntimeError('Ambiguous subscription items')
            if sub.get('cancel_at'):end=min(end,sub['cancel_at'])
            eligible.append((end,sub,plans.pop()))
    account.cancel_at_period_end=False;account.cancel_at=None
    if eligible:
        end,sub,plan=max(eligible,key=lambda row:row[0]);account.free_remaining=0;account.subscription_plan=plan;account.subscription=sub.id;account.subscription_status=sub.status;account.paid_until=datetime.fromtimestamp(end,tz.utc)
        account.cancel_at_period_end=bool(sub.get('cancel_at_period_end') or sub.get('cancel_at'))
        if account.cancel_at_period_end:account.cancel_at=account.paid_until
    else:
        pending=[s for s in subscriptions.data if s.status not in ['canceled','incomplete_expired']]
        account.subscription=pending[0].id if pending else '';account.subscription_status=pending[0].status if pending else 'inactive';account.paid_until=None
    account.save(update_fields=['subscription','subscription_status','paid_until','subscription_plan','free_remaining','cancel_at_period_end','cancel_at'])
@require_POST
@endpoint
def refresh(request,body):
    if not settings.BILLING_ENABLED:return error('Les abonnements ne sont pas encore ouverts.',503)
    if limited(request,'billing-refresh',10,identity=request.user.pk):return error('Réessayez dans quelques minutes.',429)
    with transaction.atomic():
        account=Account.objects.select_for_update().get(user=request.user)
        if account.customer:sync(account,client())
        return JsonResponse(summary(account))

@require_POST
@endpoint
def checkout(request,body):
    if not settings.BILLING_ENABLED:return error('Les abonnements ne sont pas encore ouverts.',503)
    plan=body.get('plan','legacy');interval=body.get('interval','monthly')
    price=next((p for p,r in price_catalog().items() if r['plan']==plan and r['interval']==interval),None)
    if not price:return error('Cette offre n’est pas encore ouverte au paiement.',503)
    if limited(request,'billing',30,identity=request.user.pk):return error('Trop de demandes de facturation. Réessayez dans 15 minutes.',429)
    api=client()
    if plan in MONTHLY_PRICES:
        if interval!='monthly':return error('Seules les offres mensuelles sont ouvertes.',400)
        actual=api.v1.prices.retrieve(price)
        recurring=actual.get('recurring') or {}
        if not actual.get('active') or actual.get('currency')!='eur' or actual.get('unit_amount')!=MONTHLY_PRICES[plan] or actual.get('tax_behavior')!='exclusive' or recurring.get('interval')!='month' or recurring.get('interval_count')!=1 or recurring.get('usage_type')!='licensed':return error('Le tarif doit être vérifié avant l’ouverture du paiement.',503)
    with transaction.atomic():
        account=Account.objects.select_for_update().get(user=request.user)
        from .email_verification import require_verified
        require_verified(account)
        if not account.customer:
            customer=api.v1.customers.create({'email':request.user.email,'metadata':{'flowfix_user':str(request.user.pk)}},options={'idempotency_key':'flowfix-customer-'+str(request.user.pk)})
            account.customer=customer.id;account.save(update_fields=['customer'])
        sync(account,api)
        if account.subscription:return error('Un abonnement existe déjà. Utilisez le portail de facturation.',409)
        # Reuse an open session, including across tabs, to avoid duplicate purchases.
        sessions=api.v1.checkout.sessions.list({'customer':account.customer,'status':'open','limit':100})
        for existing in sessions.data:
            if existing.get('mode')!='subscription':continue
            if existing.get('metadata',{}).get('flowfix_price')==price:
                return JsonResponse({'url':existing.url})
            api.v1.checkout.sessions.expire(existing.id)
        session=api.v1.checkout.sessions.create({
            'customer':account.customer,'mode':'subscription',
            'line_items':[{'price':price,'quantity':1}],
            'success_url':settings.PUBLIC_URL+'/billing/?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url':settings.PUBLIC_URL+'/billing/?canceled=1',
            'client_reference_id':str(request.user.pk),
            'metadata':{'flowfix_price':price},
            'subscription_data':{'metadata':{'flowfix_user':str(request.user.pk),'flowfix_plan':plan}},
            'billing_address_collection':'required','customer_update':{'address':'auto','name':'auto'},
            'automatic_tax':{'enabled':settings.STRIPE_AUTOMATIC_TAX},'tax_id_collection':{'enabled':True},
            'locale':account.language,
            'branding_settings':{'display_name':'FixScenario','background_color':'#090710','button_color':'#7C4DF5','border_style':'rounded','font_family':'inter'},
        },options={'idempotency_key':'flowfix-checkout-'+str(uuid4())})
    return JsonResponse({'url':session.url})
@require_POST
@endpoint
def portal(request,body):
    account=Account.objects.get(user=request.user)
    if not account.customer:return error('Aucun compte de facturation.',409)
    if limited(request,'billing',30,identity=request.user.pk):return error('Trop de demandes de facturation. Réessayez dans 15 minutes.',429)
    params={'customer':account.customer,'return_url':settings.PUBLIC_URL+'/billing/?portal_return=1','locale':account.language}
    if settings.STRIPE_PORTAL_CONFIGURATION:params['configuration']=settings.STRIPE_PORTAL_CONFIGURATION
    session=client().v1.billing_portal.sessions.create(params)
    return JsonResponse({'url':session.url})
@csrf_exempt
@require_POST
def webhook(request):
    if not settings.BILLING_ENABLED or not settings.STRIPE_WEBHOOK_SECRET:return error('Billing disabled',503)
    try:event=stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError,stripe.SignatureVerificationError):return error('Invalid signature',400)
    if event.type not in ['checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.async_payment_failed','customer.subscription.created','customer.subscription.updated','customer.subscription.deleted','invoice.paid','invoice.payment_failed']:return JsonResponse({'received':True})
    try:
        with transaction.atomic():
            customer=event.data.object.get('customer')
            if not isinstance(customer,str) or not customer.startswith('cus_'):return JsonResponse({'received':True})
            account=Account.objects.select_for_update().filter(customer=customer).first()
            if not account:return JsonResponse({'received':True})
            if BillingEvent.objects.filter(event_id=event.id).exists():return JsonResponse({'received':True})
            sync(account,client());BillingEvent.objects.create(event_id=event.id)
    except Exception:return error('Retry later',503)
    return JsonResponse({'received':True})
