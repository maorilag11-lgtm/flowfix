import hashlib,secrets
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.validators import validate_email
from django.utils import timezone
from saas.models import Invitation
class Command(BaseCommand):
    help='Create a single-use private beta invitation. Deliver the code to the named recipient securely.'
    def add_arguments(self,p):p.add_argument('email')
    def handle(self,*args,**opts):
        email=opts['email'].strip().lower();validate_email(email)
        token=secrets.token_urlsafe(32)
        Invitation.objects.create(email=email,digest=hashlib.sha256(token.encode()).hexdigest(),expires=timezone.now()+timedelta(days=7))
        self.stdout.write('Invitation code (7 days): '+token)
