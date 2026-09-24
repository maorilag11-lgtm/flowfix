import json
from collections import Counter
from django.core.management.base import BaseCommand
from saas.models import Analysis,Account
class Command(BaseCommand):
    help='Aggregate beta declarations; does not measure independently verified accuracy.'
    def handle(self,*args,**options):
        rows=Analysis.objects.values_list('data',flat=True);status=Counter();diagnostic=Counter();notes=0
        for d in rows:
            status[d['resolution']]+=1;diagnostic[d['output']['response']['status']]+=1
            notes+=sum(bool(e.get('actual_resolution')) for e in d['history'] if e['kind']=='feedback')
        self.stdout.write(json.dumps({'accounts':Account.objects.count(),'analyses':sum(status.values()),'user_declared_outcomes':dict(status),'diagnostic_states':dict(diagnostic),'feedback_with_resolution_notes':notes,'independently_validated_accuracy':None},indent=2))
