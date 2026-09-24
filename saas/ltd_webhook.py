import stripe
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import Account,BillingEvent
from .ltd import client,sync_payment
from .views import error
@csrf_exempt
@require_POST
def webhook(request):
    if not settings.STRIPE_LTD_WEBHOOK_SECRET:return error('LTD webhook unavailable',503)
    try:event=stripe.Webhook.construct_event(request.body,request.headers.get('Stripe-Signature',''),settings.STRIPE_LTD_WEBHOOK_SECRET)
    except (ValueError,stripe.SignatureVerificationError):return error('Invalid signature',400)
    if event.type!='charge.refunded':return JsonResponse({'received':True})
    try:
        with transaction.atomic():
            intent=event.data.object.get('payment_intent')
            if not isinstance(intent,str):return JsonResponse({'received':True})
            a=Account.objects.select_for_update().filter(ltd_payment_intent=intent).first()
            if not a:return JsonResponse({'received':True})
            if BillingEvent.objects.filter(event_id=event.id).exists():return JsonResponse({'received':True})
            sync_payment(a,client());BillingEvent.objects.create(event_id=event.id)
    except Exception:return error('Retry later',503)
    return JsonResponse({'received':True})
