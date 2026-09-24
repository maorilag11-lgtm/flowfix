from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from saas.models import Account
from saas.ltd import client,sync_payment
class Command(BaseCommand):
    help='Refresh delivered LTD payments from Stripe, including full refunds.'
    def handle(self,*args,**options):
        api=client();failures=0;count=0
        for pk in Account.objects.exclude(ltd_payment_intent=None).values_list('pk',flat=True):
            try:
                with transaction.atomic():sync_payment(Account.objects.select_for_update().get(pk=pk),api)
                count+=1
            except Exception:failures+=1
        if failures:raise CommandError(f'{failures} payments need a retry; existing rights preserved until verification.')
        self.stdout.write(f'{count} payments verified; no charge created.')
