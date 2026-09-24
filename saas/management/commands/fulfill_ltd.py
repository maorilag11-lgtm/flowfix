from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from saas.models import Account
from saas.ltd import client,fulfill
class Command(BaseCommand):
    help='Deliver an existing paid LTD purchase to its buyer. Requires a real Stripe verification; does not charge.'
    def add_arguments(self,parser):
        parser.add_argument('account_id',type=int)
        parser.add_argument('checkout_id')
    def handle(self,*args,**options):
        try:
            with transaction.atomic():
                account=Account.objects.select_for_update().select_related('user').get(pk=options['account_id'])
                plan=fulfill(account,options['checkout_id'],client())
        except Exception:raise CommandError('Delivery rejected. Check the account, paid session, contract and Stripe configuration. No partial grant retained.')
        self.stdout.write(f"Delivered {plan['name']}: {plan['quota']} diagnostics/month, {plan['seats']} seats. No payment created.")
