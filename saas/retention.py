"""Visibility window separate from operator-controlled physical deletion.
No purge runs from an HTTP request or migration. Existing data is not destroyed.
"""
from datetime import timedelta
from django.db.models import Q
from django.utils import timezone
from .models import Account,Analysis

def history_days(account):
    if account.ltd_active and not account.subscription:return None
    if account.subscription_plan=='solo':return 30
    if account.subscription_plan=='enterprise':return account.retention_days
    return None

def expired_for(account):
    days=history_days(account)
    if days is None:return Analysis.objects.none()
    return Analysis.objects.filter(Q(owner_id=account.user_id,workspace__isnull=True)|Q(workspace__account=account),created_at__lt=timezone.now()-timedelta(days=days))

def visible(query,user):
    accounts=Account.objects.filter(Q(user=user)|Q(teammember__user=user)).distinct()
    for a in accounts:query=query.exclude(pk__in=expired_for(a).values('pk'))
    return query
