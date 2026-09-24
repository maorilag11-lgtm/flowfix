"""Server-side trial access and outcome-based diagnostic accounting.

The commercial decision consumes S4/S5's verdict; it never alters the verdict.
Call check_access and record_usage with the Account row locked in a transaction.
"""
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from local_app.service import Conflict
from .models import DiagnosticUsage
from .catalog import rights,LTD_PLANS


def entitlement(account):
    now=timezone.now()
    if account.subscription_status in ['active','trialing'] and account.paid_until and account.paid_until>now:
        r=rights(account)
        return True,r['quota'],r['name']
    if account.ltd_active and account.ltd_plan in LTD_PLANS:
        r=LTD_PLANS[account.ltd_plan]
        return True,r['quota'],r['name']
    if account.agency_trial_until and account.agency_trial_until>now:
        return True,None,'Essai 14 jours'
    if account.beta_until and account.beta_until>now:
        return True,settings.BETA_QUOTA,'Bêta privée'
    # An expired paid/beta/trial access must not silently turn into a second trial.
    if account.paid_until or account.beta_until or account.agency_trial_started or account.ltd_checkout:
        return False,0,'Accès expiré'
    if account.free_remaining:
        return True,1,'Premier diagnostic gratuit'
    return False,0,'Diagnostic gratuit utilisé'


def check_access(account):
    allowed,limit,plan=entitlement(account)
    if not allowed:raise Conflict('Votre accès est terminé. Consultez Mon accès pour continuer.')
    month=timezone.now().strftime('%Y-%m')
    used=account.usage if account.usage_month==month else 0
    if limit is not None and plan!='Premier diagnostic gratuit' and used>=limit:
        raise Conflict('Quota mensuel atteint. Vos analyses restent consultables.')


def record_usage(account,analysis,output):
    response=output.get('response',{})
    outcome=response.get('status','INSUFFICIENT_EVIDENCE')
    # A leading candidate is not a confirmed resolution. Ambiguity never counts.
    conclusive=(outcome=='DIAGNOSIS_CANDIDATE' and response.get('confidence') in ['medium','high']
                and bool(response.get('diagnosis')) and output.get('decision',{}).get('action')!='ESCALATE')
    _,limit,plan=entitlement(account)
    reason='inconclusive'
    counted=False
    if conclusive:
        if plan=='Premier diagnostic gratuit':
            account.free_remaining-=1
            reason='free_diagnosis'
            counted=True
        elif limit is None:
            reason='included_in_trial' if plan=='Essai 14 jours' else 'included_in_plan'
        else:
            month=timezone.now().strftime('%Y-%m')
            if account.usage_month!=month:account.usage_month=month;account.usage=0
            account.usage+=1
            reason='monthly_quota'
            counted=True
        account.save(update_fields=['free_remaining','usage_month','usage'])
    DiagnosticUsage.objects.create(account=account,analysis=analysis,revision=analysis.data['revision'],
                                    outcome=outcome,counted=counted,reason=reason)
    messages={
        'inconclusive':'Diagnostic non concluant : aucun crédit décompté.',
        'free_diagnosis':'Votre premier diagnostic est offert. Aucun paiement effectué.',
        'included_in_trial':'Diagnostic inclus dans votre essai. Aucun paiement effectué.',
        'included_in_plan':'Diagnostic inclus dans votre abonnement sans quota mensuel.',
        'monthly_quota':'Un diagnostic décompté de votre quota mensuel.',
    }
    return {'counted':counted,'reason':reason,'message':messages[reason]}


def start_trial(account):
    from .email_verification import require_verified
    require_verified(account)
    if account.ltd_active:raise Conflict('Votre accès LTD est déjà actif.')
    if account.agency_trial_started:raise Conflict('Cet essai a déjà été activé.')
    if account.subscription_status in ['active','trialing'] and account.paid_until and account.paid_until>timezone.now():
        raise Conflict('Votre abonnement est déjà actif.')
    now=timezone.now()
    account.agency_trial_started=now
    account.agency_trial_until=now+timedelta(days=14)
    # Starting the time-limited trial replaces the one-diagnosis entry offer.
    account.free_remaining=0
    account.save(update_fields=['agency_trial_started','agency_trial_until','free_remaining'])
    return account.agency_trial_until
