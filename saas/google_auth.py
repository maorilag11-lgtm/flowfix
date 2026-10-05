"""Server-side Google OIDC; no Google access or refresh tokens are retained."""
import base64, hashlib, secrets, time
from urllib.parse import urlencode
import requests
from google.oauth2 import id_token
from google.auth.transport.requests import Request
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.validators import validate_email
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_GET
from .localization import text as translate
from .models import Account
from .views import limited


def configured():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def screen(request, error='', status=200):
    return render(request,'registration/google_connect.html',{'enabled':configured(),'error':translate(error),'marketing_url':settings.MARKETING_URL},status=status)


@require_http_methods(['GET','POST'])
def start(request):
    if not configured():return screen(request,'La connexion Google n’est pas encore configurée.',503)
    if request.method=='GET':return redirect('/login/')
    if limited(request,'google-login'):return screen(request,'Trop de tentatives. Réessayez plus tard.',429)
    state,nonce,verifier=(secrets.token_urlsafe(32) for _ in range(3))
    request.session['google_oauth']={'state':state,'nonce':nonce,'verifier':verifier,'created':time.time(),'user':request.user.pk if request.user.is_authenticated else None}
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
        'client_id':settings.GOOGLE_CLIENT_ID,'redirect_uri':settings.PUBLIC_URL+'/auth/google/callback/',
        'response_type':'code','scope':'openid email profile','state':state,'nonce':nonce,
        'code_challenge':challenge,'code_challenge_method':'S256','prompt':'select_account'}))


def exchange(code,flow):
    response=requests.post('https://oauth2.googleapis.com/token',data={
        'code':code,'client_id':settings.GOOGLE_CLIENT_ID,'client_secret':settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri':settings.PUBLIC_URL+'/auth/google/callback/','grant_type':'authorization_code',
        'code_verifier':flow['verifier']},timeout=15)
    response.raise_for_status()
    # Google library checks signature, issuer, audience and expiry. Never use tokeninfo in production.
    class TimedRequest(Request):
        def __call__(self,*args,**kwargs):
            kwargs['timeout']=15
            return super().__call__(*args,**kwargs)
    return id_token.verify_oauth2_token(response.json()['id_token'],TimedRequest(),settings.GOOGLE_CLIENT_ID)


@require_GET
def callback(request):
    flow=request.session.pop('google_oauth',None)
    if not configured() or not flow or not secrets.compare_digest(request.GET.get('state',''),flow['state']) or not 0<=time.time()-flow['created']<600:
        return screen(request,'Cette tentative de connexion a expiré. Recommencez.',400)
    if (request.user.pk if request.user.is_authenticated else None)!=flow['user']:
        return screen(request,'Votre session a changé. Recommencez.',400)
    if request.GET.get('error'):return screen(request,'La connexion Google a été annulée. Votre compte n’a pas changé.',400)
    code=request.GET.get('code','')
    if not code or len(code)>4096:return screen(request,'Réponse Google invalide. Recommencez.',400)
    try:
        claims=exchange(code,flow)
        if not secrets.compare_digest(str(claims.get('nonce','')),flow['nonce']):raise ValueError()
        subject=claims.get('sub');email=claims.get('email','').strip().lower()
        if not isinstance(subject,str) or not subject or len(subject)>255 or claims.get('email_verified') is not True or len(email)>150:raise ValueError()
        validate_email(email)
    except Exception:
        return screen(request,'La connexion Google n’a pas pu être vérifiée. Réessayez.',400)
    try:
        with transaction.atomic():
            account=Account.objects.select_for_update().select_related('user').filter(google_subject=subject).first()
            if account:
                if flow['user'] and account.user_id!=flow['user']:return screen(request,'Cette identité Google est déjà associée à un autre compte.',409)
            elif flow['user']:
                account=Account.objects.select_for_update().select_related('user').get(user_id=flow['user'])
                if account.google_subject or account.user.email.lower()!=email:return screen(request,'Choisissez l’identité Google avec la même adresse email que votre compte.',409)
                account.google_subject=subject;account.save(update_fields=['google_subject'])
            else:
                # Email equality alone is never enough to link an existing local account.
                if User.objects.filter(Q(username__iexact=email)|Q(email__iexact=email)).exists():
                    return screen(request,'Un compte utilise déjà cette adresse. Connectez-vous avec votre mot de passe, puis revenez ici pour associer Google.',409)
                user=User.objects.create_user(username=email,email=email,password=None)
                authoritative=email.endswith('@gmail.com') or bool(claims.get('hd'))
                account=Account.objects.create(user=user,google_subject=subject,language=request.LANGUAGE_CODE,
                    verified_email=email if authoritative else '',email_verified_at=timezone.now() if authoritative else None)
            if not account.user.is_active:return screen(request,'Ce compte est indisponible.',403)
            login(request,account.user,backend='django.contrib.auth.backends.ModelBackend')
    except IntegrityError:
        return screen(request,'Un compte a été modifié pendant la connexion. Recommencez.',409)
    return redirect('/app/')
