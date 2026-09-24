from datetime import datetime,timezone as tz
import stripe
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Account,BillingEvent
from .catalog import price_catalog
from .views import endpoint,error,limited

def client():
    if not settings.BILLING_ENABLED or not all([settings.STRIPE_SECRET_KEY,settings.STRIPE_WEBHOOK_SECRET,price_catalog()]):raise RuntimeError('Billing unavailable')
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY,max_network_retries=2)
def sync(account,api):
    subscriptions=api.v1.subscriptions.list({'customer':account.customer,'status':'all','limit':100})
    eligible=[]
    for sub in subscriptions.data:
        items=[i for i in sub['items']['data'] if i['price']['id'] in price_catalog()]
        if items and sub.status in ['active','trialing']:
            end=max(i.get('current_period_end',sub.get('current_period_end',0)) for i in items)
            # Mixed commercial tiers are ambiguous: fail closed rather than grant a higher tier.
            plans={price_catalog()[i['price']['id']]['plan'] for i in items}
            if len(plans)!=1:raise RuntimeError('Ambiguous subscription items')
            eligible.append((end,sub,plans.pop()))
    if eligible:
        end,sub,plan=max(eligible,key=lambda row:row[0]);account.free_remaining=0;account.subscription_plan=plan;account.subscription=sub.id;account.subscription_status=sub.status;account.paid_until=datetime.fromtimestamp(end,tz.utc)
    else:
        pending=[s for s in subscriptions.data if s.status not in ['canceled','incomplete_expired']]
        account.subscription=pending[0].id if pending else '';account.subscription_status=pending[0].status if pending else 'inactive';account.paid_until=None
    account.save(update_fields=['subscription','subscription_status','paid_until','subscription_plan','free_remaining'])
@require_POST
@endpoint
def checkout(request,body):
    if not settings.BILLING_ENABLED:return error('Les abonnements ne sont pas encore ouverts.',503)
    plan=body.get('plan','legacy');interval=body.get('interval','monthly')
    price=next((p for p,r in price_catalog().items() if r['plan']==plan and r['interval']==interval),None)
    if not price:return error('Cette offre n’est pas encore ouverte au paiement.',503)
    if limited(request,'billing',30,identity=request.user.pk):return error('Trop de demandes de facturation. Réessayez dans 15 minutes.',429)
    api=client()
    with transaction.atomic():
        account=Account.objects.select_for_update().get(user=request.user)
        from .email_verification import require_verified
        require_verified(account)
        if not account.customer:
            customer=api.v1.customers.create({'email':request.user.email,'metadata':{'flowfix_user':str(request.user.pk)}},options={'idempotency_key':'flowfix-customer-'+str(request.user.pk)})
            account.customer=customer.id;account.save(update_fields=['customer'])
        sync(account,api)
        if account.subscription:return error('Un abonnement existe déjà. Utilisez le portail de facturation.',409)
        from django.utils import timezone
        session=api.v1.checkout.sessions.create({'customer':account.customer,'mode':'subscription','line_items':[{'price':price,'quantity':1}],'success_url':settings.PUBLIC_URL+'/app/#settings','cancel_url':settings.PUBLIC_URL+'/app/#settings','client_reference_id':str(request.user.pk)},options={'idempotency_key':'flowfix-checkout-'+str(request.user.pk)+'-'+plan+'-'+interval+'-'+timezone.now().strftime('%Y-%m-%d')})
    return JsonResponse({'url':session.url})
@require_POST
@endpoint
def portal(request,body):
    account=Account.objects.get(user=request.user)
    if not account.customer:return error('Aucun compte de facturation.',409)
    if limited(request,'billing',30,identity=request.user.pk):return error('Trop de demandes de facturation. Réessayez dans 15 minutes.',429)
    session=client().v1.billing_portal.sessions.create({'customer':account.customer,'return_url':settings.PUBLIC_URL+'/app/#settings'})
    return JsonResponse({'url':session.url})
@csrf_exempt
@require_POST
def webhook(request):
    if not settings.BILLING_ENABLED or not settings.STRIPE_WEBHOOK_SECRET:return error('Billing disabled',503)
    try:event=stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError,stripe.SignatureVerificationError):return error('Invalid signature',400)
    if event.type not in ['checkout.session.completed','customer.subscription.created','customer.subscription.updated','customer.subscription.deleted','invoice.paid','invoice.payment_failed']:return JsonResponse({'received':True})
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
