from django.core.management.base import BaseCommand
from saas.models import Account
from saas.retention import expired_for
class Command(BaseCommand):
    help='Read-only retention report. Does not delete any data or log diagnostic contents.'
    def handle(self,*args,**options):
        total=0
        for account in Account.objects.iterator():total+=expired_for(account).count()
        self.stdout.write(f'{total} analyses outside the current history window. No data deleted. Physical retention and backup deletion must be scheduled under the operator policy.')
