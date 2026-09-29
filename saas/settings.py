import os
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent.parent
DEBUG=os.getenv('FLOWFIX_DEV')=='1'
SECRET_KEY=os.getenv('DJANGO_SECRET_KEY','development-only-do-not-deploy' if DEBUG else '')
if not SECRET_KEY:raise RuntimeError('DJANGO_SECRET_KEY is required')
ALLOWED_HOSTS=[h.strip() for h in os.getenv('DJANGO_ALLOWED_HOSTS','127.0.0.1,localhost' if DEBUG else '').split(',') if h.strip()]
PUBLIC_URL=os.getenv('PUBLIC_URL','http://127.0.0.1:8767' if DEBUG else '').rstrip('/')
# Adresse du site commercial, distincte de PUBLIC_URL (application).
MARKETING_URL=os.getenv('MARKETING_URL','http://127.0.0.1:8770/' if DEBUG else '/').strip() or '/'
from .security_config import postgres_url_config
_postgres_url=postgres_url_config(os.environ['DATABASE_URL']) if os.getenv('DATABASE_URL') else None
if not DEBUG and (not PUBLIC_URL.startswith('https://') or not (_postgres_url or os.getenv('POSTGRES_HOST'))):raise RuntimeError('Production requires HTTPS PUBLIC_URL and PostgreSQL')
if not DEBUG:
    from .security_config import validate_production
    validate_production(SECRET_KEY,ALLOWED_HOSTS,PUBLIC_URL)
INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','saas']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','saas.localization.LanguageMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware','saas.middleware.Headers']
ROOT_URLCONF='saas.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'saas/templates'],'APP_DIRS':False,'OPTIONS':{'loaders':['saas.localization.Loader','django.template.loaders.app_directories.Loader'],'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='saas.wsgi.application'
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'.flowfix-saas.sqlite3','OPTIONS':{'timeout':20}}}
if not _postgres_url and os.getenv('POSTGRES_HOST'):DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','HOST':os.environ['POSTGRES_HOST'],'NAME':os.getenv('POSTGRES_DB','flowfix'),'USER':os.getenv('POSTGRES_USER','flowfix'),'PASSWORD':os.environ['POSTGRES_PASSWORD'],'PORT':os.getenv('POSTGRES_PORT','5432'),'CONN_MAX_AGE':60}}
if _postgres_url:DATABASES={'default':_postgres_url}
AUTH_PASSWORD_VALIDATORS=[{'NAME':'django.contrib.auth.password_validation.'+n} for n in ['UserAttributeSimilarityValidator','MinimumLengthValidator','CommonPasswordValidator','NumericPasswordValidator']]
PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2PasswordHasher']
LANGUAGE_CODE='en'
LANGUAGES=[('en','English'),('fr','Français')]
TIME_ZONE='UTC'
USE_TZ=True
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
LOGIN_URL='/login/'
LOGIN_REDIRECT_URL='/app/'
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=not DEBUG
CSRF_COOKIE_SECURE=not DEBUG
CSRF_HEADER_NAME='HTTP_X_FLOWFIX_TOKEN'
SESSION_COOKIE_AGE=86400*7
SESSION_COOKIE_SAMESITE='Lax'
SECURE_SSL_REDIRECT=not DEBUG
SECURE_HSTS_SECONDS=31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
# Set only behind a proxy which strips incoming X-Forwarded-Proto.
if os.getenv('TRUST_PROXY')=='1':SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO','https')
DATA_UPLOAD_MAX_MEMORY_SIZE=1500000
CSRF_FAILURE_VIEW='saas.views.csrf_failure'
EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST=os.getenv('EMAIL_HOST','')
EMAIL_PORT=int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS=True
EMAIL_TIMEOUT=10
DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL','')
SUPPORT_EMAIL=os.getenv('SUPPORT_EMAIL','')
STRIPE_SECRET_KEY=os.getenv('STRIPE_SECRET_KEY','')
STRIPE_WEBHOOK_SECRET=os.getenv('STRIPE_WEBHOOK_SECRET','')
STRIPE_PRICE_ID=os.getenv('STRIPE_PRICE_ID','')
BILLING_ENABLED=os.getenv('BILLING_ENABLED')=='1'
BETA_QUOTA=int(os.getenv('BETA_QUOTA','100'))
PAID_QUOTA=int(os.getenv('PAID_QUOTA','500'))
LOGGING={'version':1,'disable_existing_loggers':False,'handlers':{'console':{'class':'logging.StreamHandler'}},'loggers':{'django.request':{'handlers':['console'],'level':'ERROR','propagate':False}}}

TRUST_CLIENT_IP=os.getenv('TRUST_CLIENT_IP')=='1'

# Configure server-owned Stripe price IDs before enabling checkout.
for _plan in ['SOLO','AGENCY','ENTERPRISE']:
    for _interval in ['MONTHLY','ANNUAL']:
        _key='STRIPE_'+_plan+'_'+_interval+'_PRICE'
        globals()[_key]=os.getenv(_key,'')

STRIPE_LTD_WEBHOOK_SECRET=os.getenv('STRIPE_LTD_WEBHOOK_SECRET','')

# The public discovery offer is now 3 free analyses; existing trials remain valid.
AGENCY_TRIAL_ENABLED=False
