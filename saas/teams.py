"""Team access. Call under the sponsoring Account lock for mutations."""
from django.db.models import Q
from django.utils import timezone
from local_app.service import Conflict
from .models import Account,Analysis,Workspace,TeamMember
from .access import entitlement
from .catalog import rights,LTD_PLANS
from .retention import visible

def team_seats(account):
    allowed,_,plan=entitlement(account)
    if not allowed:return 0
    if account.ltd_active and account.ltd_plan in LTD_PLANS and plan==LTD_PLANS[account.ltd_plan]['name']:return LTD_PLANS[account.ltd_plan]['seats']
    if plan=='Essai 14 jours':return 5
    if plan=='Bêta privée':return 3
    return rights(account)['seats'] if account.subscription_status in ['active','trialing'] else 1

def can_manage(account):
    if team_seats(account)<2:raise Conflict('Activez un essai de 14 jours ou une offre équipe pour gérer vos espaces clients.')

def shared_accounts(user):
    return Account.objects.filter(Q(user=user)|Q(teammember__user=user)).distinct()

def workspaces(user):
    return Workspace.objects.filter(account__in=shared_accounts(user))

def role_for(account,user):
    if account.user_id==user.pk:return 'owner'
    return TeamMember.objects.filter(account=account,user=user).values_list('role',flat=True).first()

def authorized_analyses(user):
    # Personal analyses NEVER become visible simply by joining a team.
    return Analysis.objects.filter(Q(owner=user,workspace__isnull=True)|Q(workspace__in=workspaces(user))).distinct()

def analysis_access(user):
    return visible(authorized_analyses(user),user)

def sponsor(user,workspace_id=None):
    if workspace_id:
        space=workspaces(user).get(pk=workspace_id)
        account=Account.objects.select_for_update().get(pk=space.account_id)
        # Re-check after locking: revocation uses the same account lock.
        role=role_for(account,user)
        if not role:raise Analysis.DoesNotExist
        return account,space,role
    return Account.objects.select_for_update().get(user=user),None,'owner'

def can_write(account,role,operation='edit'):
    if role not in ['owner','editor']:raise Conflict('Votre rôle autorise uniquement la consultation et l’export.')
    if operation=='delete' and role!='owner':raise Conflict('Seul le propriétaire de l’équipe peut supprimer une analyse partagée.')
    if role!='owner' and team_seats(account)<2:raise Conflict('L’accès équipe est expiré. Les analyses restent consultables.')
