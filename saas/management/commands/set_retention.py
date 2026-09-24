from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from saas.models import Account
class Command(BaseCommand):
    help='Set the Enterprise history window. Does not physically delete data.'
    def add_arguments(self,parser):
        parser.add_argument('account_id',type=int)
        parser.add_argument('days',help='7 to 3650, or unlimited')
    def handle(self,*args,**options):
        try:days=None if options['days']=='unlimited' else int(options['days'])
        except ValueError:raise CommandError('Use a number of days or unlimited')
        if days is not None and not 7<=days<=3650:raise CommandError('Days must be between 7 and 3650')
        with transaction.atomic():
            try:a=Account.objects.select_for_update().get(pk=options['account_id'],subscription_plan='enterprise')
            except Account.DoesNotExist:raise CommandError('Enterprise account not found')
            a.retention_days=days;a.save(update_fields=['retention_days'])
        self.stdout.write('History window updated. No data deleted. Apply the separate operator retention and backup policy.')
