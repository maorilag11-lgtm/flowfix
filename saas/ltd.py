"""Operator-initiated delivery of a paid presale; no charge is created here.
Only Stripe data is authoritative. User/browser fields cannot grant LTD access.
"""
import stripe
from django.conf import settings
from local_app.service import Invalid,Conflict
from .catalog import LTD_PLANS

VERSION='founders-2026-09-v1'
def client():
    if not settings.STRIPE_SECRET_KEY:raise RuntimeError('Stripe is not configured')
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY,max_network_retries=2)

def sync_payment(account,api):
    payment=api.v1.payment_intents.retrieve(account.ltd_payment_intent,{'expand':['latest_charge']})
    charge=payment.get('latest_charge') or {}
    if not isinstance(charge,dict) and not isinstance(charge,stripe.StripeObject):raise Invalid('Charge non développée.')
    if payment.get('status')!='succeeded' or payment.get('currency')!='eur':raise Invalid('Paiement non confirmé.')
    # Partial refunds do not automatically remove the entire purchased access.
    account.ltd_active=not (charge.get('refunded') is True and charge.get('amount_refunded',0)>=charge.get('amount',1))
    account.save(update_fields=['ltd_active'])
    return account.ltd_active

def fulfill(account,checkout_id,api):
    from .email_verification import require_verified
    require_verified(account)
    if account.ltd_checkout and account.ltd_checkout!=checkout_id:raise Conflict('Un autre achat LTD est déjà rattaché à ce compte.')
    session=api.v1.checkout.sessions.retrieve(checkout_id,{'expand':['line_items.data.price.product']})
    metadata=session.get('metadata') or {}
    if session.get('mode')!='payment' or session.get('status')!='complete' or session.get('payment_status')!='paid':raise Invalid('Prévente non payée.')
    if not metadata.get('flowfix_order') or metadata.get('flowfix_order')!=session.get('client_reference_id') or metadata.get('offer_version')!=VERSION:raise Invalid('Contrat de prévente non reconnu.')
    email=(session.get('customer_details') or {}).get('email') or session.get('customer_email','')
    if not email or email.lower()!=account.user.email.lower():raise Invalid('Le compte ne correspond pas à l’adresse de l’achat.')
    lines=session.get('line_items') or {};items=lines.get('data') or []
    if lines.get('has_more') or len(items)!=1 or items[0].get('quantity')!=1:raise Invalid('Lignes de prévente ambiguës.')
    product=(items[0].get('price') or {}).get('product') or {}
    if not hasattr(product,'get'):raise Invalid('Produit non développé.')
    names={'solo':'Solo','pro':'Pro','agence':'Agence'}
    tier=next((k for k,v in LTD_PLANS.items() if session.get('currency')=='eur' and session.get('amount_total')==v['price'] and product.get('name')=='Prévente FixScenario LTD '+names[k]),None)
    if not tier:raise Invalid('Offre ou montant non reconnu.')
    intent=session.get('payment_intent')
    if not isinstance(intent,str) or not intent.startswith('pi_'):raise Invalid('Référence de paiement absente.')
    account.ltd_plan=tier;account.ltd_checkout=checkout_id;account.ltd_payment_intent=intent
    account.save(update_fields=['ltd_plan','ltd_checkout','ltd_payment_intent'])
    if not sync_payment(account,api):raise Conflict('Cet achat a été intégralement remboursé.')
    return LTD_PLANS[tier]
