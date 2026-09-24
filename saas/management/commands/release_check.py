from django.core.management.base import BaseCommand,CommandError
from django.conf import settings
from flowfix.step3_retrieval.kb.loader import load_kb
from saas.catalog import price_catalog
class Command(BaseCommand):
    help='Fail closed when required deployment configuration is missing.'
    def handle(self,*a,**kw):
        problems=[]
        if settings.DEBUG:problems.append('Development mode enabled')
        if len(settings.SECRET_KEY)<50:problems.append('Secret key must contain at least 50 random characters')
        for field in ['PUBLIC_URL','SUPPORT_EMAIL','DEFAULT_FROM_EMAIL','EMAIL_HOST']:
            if not getattr(settings,field,''):problems.append(field+' missing')
        if not settings.ALLOWED_HOSTS or '*' in settings.ALLOWED_HOSTS:problems.append('Explicit allowed hosts required')
        if settings.DATABASES['default']['ENGINE']!='django.db.backends.postgresql':problems.append('PostgreSQL required')
        if settings.BILLING_ENABLED:
            for name in ['STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET']:
                if not getattr(settings,name):problems.append(name+' missing')
            if not price_catalog():problems.append('At least one Stripe price must be configured')
        if len(load_kb())!=67:problems.append('Unexpected knowledge base count')
        if problems:raise CommandError('; '.join(problems))
        self.stdout.write('Configuration checks passed. This does not certify live services, restoration, legal notices or diagnosis accuracy.')
