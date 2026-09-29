"""Email ownership proof: account-bound, expiring, one-use, no automatic login."""
import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import render,redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from local_app.service import Conflict
from .models import Account,EmailVerification
from .localization import text as translate


def verified(account):
    email=account.user.email.strip().lower()
    return bool(email and account.email_verified_at and account.verified_email==email)


def require_verified(account):
    if not verified(account):
        raise Conflict('Confirmez votre adresse email depuis Mon accès avant de continuer.')


@login_required
@require_http_methods(['GET','POST'])
def verification(request,token=None):
    # Lazy import avoids the views -> email_verification circular dependency.
    from .views import limited
    account=Account.objects.select_related('user').get(user=request.user)
    message='';status=200
    if request.method=='POST':
        if limited(request,'email-confirm' if token else 'email-send',10 if token else 3,identity=request.user.pk):
            message='Trop de demandes. Réessayez dans 15 minutes.';status=429
        elif token:
            with transaction.atomic():
                account=Account.objects.select_for_update().select_related('user').get(pk=account.pk)
                proof=EmailVerification.objects.filter(account=account,digest=hashlib.sha256(token.encode()).hexdigest(),expires__gt=timezone.now(),email=account.user.email.strip().lower()).first()
                if proof:
                    account.verified_email=proof.email;account.email_verified_at=timezone.now()
                    account.save(update_fields=['verified_email','email_verified_at'])
                    proof.delete()
                    return redirect('/verify-email/')
                message='Ce lien est invalide, expiré ou déjà utilisé. Demandez un nouvel email.';status=400
        elif verified(account):
            return redirect('/verify-email/')
        elif not settings.EMAIL_HOST or not settings.DEFAULT_FROM_EMAIL:
            message='L’envoi des emails n’est pas encore disponible. Votre compte reste accessible.';status=503
        else:
            try:
                with transaction.atomic():
                    account=Account.objects.select_for_update().select_related('user').get(pk=account.pk)
                    email=account.user.email.strip().lower();validate_email(email)
                    secret=secrets.token_urlsafe(32)
                    EmailVerification.objects.update_or_create(account=account,defaults={'email':email,'digest':hashlib.sha256(secret.encode()).hexdigest(),'expires':timezone.now()+timedelta(hours=24)})
                    url=settings.PUBLIC_URL+'/verify-email/'+secret+'/'
                    sent=send_mail(translate('Confirmez votre adresse email — FlowFix'),
                        translate('Confirmez cette adresse pour votre compte FlowFix :')+'\n\n'+url+'\n\n'+translate('Connectez-vous au compte concerné, puis confirmez. Ce lien expire dans 24 heures. Un nouvel envoi remplace le précédent.')+'\n'+translate('Si vous n’avez pas demandé cet email, ignorez-le.'),
                        settings.DEFAULT_FROM_EMAIL,[email],fail_silently=False)
                    if sent!=1:raise RuntimeError('Email not sent')
                message='Email envoyé. Ouvrez le lien reçu et confirmez votre adresse. Pensez aux indésirables.'
            except Exception:
                # Never reflect SMTP errors or log a token/recipient.
                message='L’email n’a pas pu être envoyé. Réessayez plus tard.';status=503
    return render(request,'registration/verify_email.html',{'verified':verified(account),'confirm_link':bool(token),'message':translate(message)},status=status)
