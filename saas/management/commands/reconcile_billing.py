from django.core.management.base import BaseCommand
from django.db import transaction
from saas.models import Account
from saas.billing import client,sync
class Command(BaseCommand):
    help='Reconcile billing with Stripe hourly; alert on nonzero exit.'
    def handle(self,*a,**kw):
        api=client()
        for pk in Account.objects.exclude(customer=None).values_list('pk',flat=True):
            with transaction.atomic():sync(Account.objects.select_for_update().get(pk=pk),api)
        self.stdout.write('Billing reconciled')
