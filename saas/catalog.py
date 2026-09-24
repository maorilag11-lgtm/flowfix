"""Commercial rights, independent from transport/security limits.
Prices live in Stripe; this catalog grants no rights from client-supplied data.
"""
from django.conf import settings
PLANS={
    'solo':{'name':'Solo','quota':100,'seats':1,'history_days':30},
    'agency':{'name':'Agence','quota':None,'seats':5,'history_days':None},
    'enterprise':{'name':'Entreprise','quota':None,'seats':20,'history_days':None},
}
def rights(account):
    return PLANS.get(account.subscription_plan,{'name':'Abonnement','quota':settings.PAID_QUOTA,'seats':1,'history_days':None})

def price_catalog():
    result={}
    for plan in PLANS:
        for interval in ['monthly','annual']:
            price=getattr(settings,'STRIPE_'+plan.upper()+'_'+interval.upper()+'_PRICE','')
            if price:result[price]={'plan':plan,'interval':interval}
    if settings.STRIPE_PRICE_ID:result.setdefault(settings.STRIPE_PRICE_ID,{'plan':'legacy','interval':'monthly'})
    return result

# Snapshot of the public founders-2026-09-v1 presale contract.
LTD_PLANS={
    'solo':{'name':'Solo LTD','price':7900,'quota':100,'seats':1},
    'pro':{'name':'Pro LTD','price':14900,'quota':300,'seats':1},
    'agence':{'name':'Agence LTD','price':29900,'quota':1000,'seats':3},
}
