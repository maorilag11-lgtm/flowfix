import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
class Account(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    verified_email=models.EmailField(blank=True,default='')
    email_verified_at=models.DateTimeField(null=True,blank=True)
    language=models.CharField(max_length=2,choices=[("en","English"),("fr","Français")],default="en")
    display_name=models.CharField(max_length=60,default='User')
    beta_until=models.DateTimeField(null=True)
    customer=models.CharField(max_length=100,null=True,unique=True)
    subscription=models.CharField(max_length=100,blank=True)
    ltd_plan=models.CharField(max_length=10,blank=True)
    ltd_checkout=models.CharField(max_length=100,null=True,unique=True)
    ltd_payment_intent=models.CharField(max_length=100,null=True,unique=True)
    ltd_active=models.BooleanField(default=False)
    subscription_plan=models.CharField(max_length=20,default='legacy')
    subscription_status=models.CharField(max_length=30,blank=True)
    paid_until=models.DateTimeField(null=True)
    usage_month=models.CharField(max_length=7,blank=True)
    usage=models.PositiveIntegerField(default=0)
    retention_days=models.PositiveIntegerField(null=True,blank=True)
    free_remaining=models.PositiveSmallIntegerField(default=3)
    agency_trial_started=models.DateTimeField(null=True,blank=True)
    agency_trial_until=models.DateTimeField(null=True,blank=True)
class Analysis(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    created_at=models.DateTimeField(default=timezone.now,db_index=True)
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    workspace=models.ForeignKey('Workspace',on_delete=models.PROTECT,null=True,blank=True)
    data=models.JSONField()
class Invitation(models.Model):
    digest=models.CharField(max_length=64,unique=True)
    email=models.EmailField()
    expires=models.DateTimeField()
    used=models.BooleanField(default=False)

class EmailVerification(models.Model):
    account=models.OneToOneField(Account,on_delete=models.CASCADE)
    email=models.EmailField()
    digest=models.CharField(max_length=64,unique=True)
    expires=models.DateTimeField()
class Throttle(models.Model):
    key=models.CharField(max_length=64,primary_key=True)
    started=models.DateTimeField()
    count=models.PositiveIntegerField(default=0)
class BillingEvent(models.Model):
    event_id=models.CharField(max_length=100,primary_key=True)
    processed=models.DateTimeField(auto_now_add=True)

class DiagnosticUsage(models.Model):
    account=models.ForeignKey(Account,on_delete=models.CASCADE)
    analysis=models.ForeignKey(Analysis,on_delete=models.SET_NULL,null=True)
    revision=models.PositiveIntegerField()
    created=models.DateTimeField(auto_now_add=True)
    outcome=models.CharField(max_length=40)
    counted=models.BooleanField(default=False)
    reason=models.CharField(max_length=40)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['analysis','revision'],name='usage_once_per_revision')]

class Workspace(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    account=models.ForeignKey(Account,on_delete=models.CASCADE)
    name=models.CharField(max_length=80)
    created=models.DateTimeField(auto_now_add=True)

class TeamMember(models.Model):
    account=models.ForeignKey(Account,on_delete=models.CASCADE)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    role=models.CharField(max_length=10,choices=[('editor','Éditeur'),('viewer','Lecture seule')])
    class Meta:
        constraints=[models.UniqueConstraint(fields=['account','user'],name='one_team_membership')]

class TeamInvitation(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    account=models.ForeignKey(Account,on_delete=models.CASCADE)
    digest=models.CharField(max_length=64,unique=True)
    email=models.EmailField()
    role=models.CharField(max_length=10)
    expires=models.DateTimeField()
    used=models.BooleanField(default=False)
