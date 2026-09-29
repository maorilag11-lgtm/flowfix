from local_app.diagnostic_contract import module_choices
import copy,hashlib,json,uuid,logging
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib.auth import login,logout,views as auth_views
from django.contrib.auth.forms import UserCreationForm,AuthenticationForm,PasswordResetForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError,RequestDataTooBig
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse,HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render,redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods,require_POST
from local_app.service import Sessions,Invalid,Conflict,analyze,mutate,now,intake,text
from .models import Account,Analysis,Invitation,Throttle,Workspace,TeamMember,TeamInvitation
from .email_verification import verified,require_verified
from .localization import text as translate,html_source,javascript_source
log=logging.getLogger(__name__)
def error(message,status=400):return JsonResponse({'error':translate(message)},status=status)
def csrf_failure(request,reason=''):return error('Session expirée ou origine refusée. Rechargez la page.',403)
def limited(request,scope,limit=10,identity=None):
    # Never trust client-supplied forwarding headers. Proxy rate limiting supplements this.
    ident=request.META.get('REMOTE_ADDR','')
    if settings.TRUST_CLIENT_IP:
        import ipaddress
        try:ident=str(ipaddress.ip_address(request.META.get('HTTP_X_FLOWFIX_CLIENT_IP','')))
        except ValueError:pass
    if identity is not None:ident='identity:'+str(identity)
    key=hashlib.sha256((scope+'|'+ident+'|'+settings.SECRET_KEY).encode()).hexdigest()
    with transaction.atomic():
        obj,_=Throttle.objects.get_or_create(key=key,defaults={'started':timezone.now()})
        obj=Throttle.objects.select_for_update().get(pk=key)
        if timezone.now()-obj.started>timedelta(minutes=15):obj.started=timezone.now();obj.count=0
        obj.count+=1;obj.save()
        return obj.count>limit
def diagnostic_limited(request):
    # Keep the IP budget and add an account budget shared by create/edit/answer.
    return limited(request,'diagnostic',120) or limited(request,'diagnostic-user',120,identity=request.user.pk)

class Login(auth_views.LoginView):
    template_name='registration/login.html'
    def get_context_data(self,**kwargs):
        context=super().get_context_data(**kwargs)
        context.update(marketing_url=settings.MARKETING_URL,auth_mode='login',login_form=context['form'],signup_form=UserCreationForm())
        return context
    def post(self,request,*args,**kwargs):
        if limited(request,'login'):return error('Trop de tentatives. Réessayez dans 15 minutes.',429)
        # A rotating IP must not bypass the limit for a single login identity.
        identity=request.POST.get('username','').strip().casefold()
        if limited(request,'login-identity',30,identity=identity):return error('Trop de tentatives. Réessayez dans 15 minutes.',429)
        return super().post(request,*args,**kwargs)
class LocalizedPasswordResetForm(PasswordResetForm):
    def save(self,**kwargs):
        from urllib.parse import urlsplit
        origin=urlsplit(settings.PUBLIC_URL)
        # Links use the configured application origin, not a request Host alias.
        kwargs['domain_override']=origin.netloc
        kwargs['use_https']=origin.scheme=='https'
        return super().save(**kwargs)

    def send_mail(self,subject_template_name,email_template_name,context,from_email,to_email,html_email_template_name=None):
        from django.utils import translation
        lang=Account.objects.filter(user=context['user']).values_list('language',flat=True).first() or 'en'
        with translation.override(lang):
            return super().send_mail(subject_template_name,email_template_name,context,from_email,to_email,html_email_template_name)

class PasswordReset(auth_views.PasswordResetView):
    form_class=LocalizedPasswordResetForm
    def post(self,request,*args,**kwargs):
        if limited(request,'reset',5):return error('Trop de demandes. Réessayez plus tard.',429)
        identity=request.POST.get('email','').strip().casefold()
        if limited(request,'reset-identity',5,identity=identity):return error('Trop de demandes. Réessayez plus tard.',429)
        if not settings.EMAIL_HOST:return error('La récupération par email est indisponible. Contactez votre interlocuteur bêta.',503)
        return super().post(request,*args,**kwargs)
@require_http_methods(['GET','POST'])
def signup(request,invitation_required=False):
    if invitation_required and request.user.is_authenticated:return activate_beta(request)
    beta_mode=invitation_required or (request.method=='POST' and 'invitation' in request.POST)
    form=UserCreationForm(request.POST or None)
    msg=''
    if request.method=='POST':
        if limited(request,'signup'):return error('Trop de tentatives. Réessayez dans 15 minutes.',429)
        email=request.POST.get('username','').strip().lower()
        try:validate_email(email)
        except ValidationError:msg='Utilisez votre adresse email comme identifiant.'
        if not msg and form.is_valid():
            digest=hashlib.sha256(request.POST.get('invitation','').encode()).hexdigest()
            with transaction.atomic():
                invite=Invitation.objects.select_for_update().filter(digest=digest,email=email,used=False,expires__gt=timezone.now()).first()
                if beta_mode and not invite:msg='Invitation invalide, expirée ou destinée à une autre adresse.'
                elif User.objects.filter(username__iexact=email).exists():msg='Ce compte existe déjà. Connectez-vous.'
                elif request.POST.get('acknowledge')!='yes':msg='Confirmez avoir lu les informations sur vos données et les limites de FlowFix.'
                else:
                    user=form.save(commit=False);user.username=email;user.email=email;user.save()
                    Account.objects.create(user=user,beta_until=timezone.now()+timedelta(days=30) if beta_mode else None)
                    if beta_mode:invite.used=True;invite.save()
                    login(request,user);return redirect('/app/')
    return render(request,'registration/signup.html',{'marketing_url':settings.MARKETING_URL,'form':form,'error':translate(msg),'auth_mode':'signup','beta_mode':beta_mode,'signup_form':form,'login_form':AuthenticationForm(request)})
@require_http_methods(['GET','POST'])
def activate_beta(request):
    if not request.user.is_authenticated:return redirect('/beta/')
    msg=''
    if request.method=='POST':
        if limited(request,'signup'):return error('Trop de tentatives. Réessayez dans 15 minutes.',429)
        digest=hashlib.sha256(request.POST.get('invitation','').encode()).hexdigest()
        with transaction.atomic():
            invite=Invitation.objects.select_for_update().filter(digest=digest,email=request.user.email.lower(),used=False,expires__gt=timezone.now()).first()
            if not invite:msg='Invitation invalide, expirée ou destinée à une autre adresse.'
            elif request.POST.get('acknowledge')!='yes':msg='Confirmez avoir lu les informations de la bêta.'
            else:
                account=Account.objects.select_for_update().get(user=request.user)
                until=timezone.now()+timedelta(days=30)
                account.beta_until=max(account.beta_until,until) if account.beta_until else until
                account.save(update_fields=['beta_until']);invite.used=True;invite.save()
                return redirect('/app/')
    return render(request,'registration/activate_beta.html',{'error':translate(msg)})

def welcome(request):
    if not request.user.is_authenticated:return redirect('/login/?next=/welcome/')
    account=Account.objects.get(user=request.user)
    if entitlement(account)[0]:return redirect('/app/')
    return render(request,'registration/welcome.html')

@require_POST
def signout(request):logout(request);return redirect('/login/')
def landing(request):return render(request,'landing.html',{'support':settings.SUPPORT_EMAIL})
def privacy(request):return render(request,'privacy.html',{'support':settings.SUPPORT_EMAIL})
def panel(request):
    if not request.user.is_authenticated:return redirect('/login/?next=/app/')
    account=Account.objects.get(user=request.user)
    return HttpResponse(html_source((settings.BASE_DIR/'local_app/static/index.html').read_text().replace('Local Plan','Bêta privée').replace('Local user','Utilisateur').replace('Stored on this device','Analyses privées')))
def asset(request,name):
    if name not in ['app.js','trace-examples.json','root-trace.js','style.css','auth.js','auth.css','team.js','billing.css','billing.js','ui-text.js']:return error('Introuvable',404)
    source=(settings.BASE_DIR/'local_app/static'/name).read_text()
    if name=='ui-text.js':
        from .localization import catalog,language
        source='window.flowfixLanguage='+json.dumps(language())+';window.flowfixCatalog='+json.dumps(catalog(),ensure_ascii=True)+';'+source
    elif name.endswith('.js'):source=javascript_source(source)
    return HttpResponse(source,content_type='application/json' if name.endswith('.json') else 'text/javascript' if name.endswith('.js') else 'text/css')
def endpoint(fn):
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_authenticated:return error('Connectez-vous pour continuer.',401)
        try:
            body={}
            if request.method=='POST':
                if request.content_type!='application/json':return error('Format JSON requis.',415)
                from flowfix.step1_intake.intake.trace_contract import decode_request
                body=decode_request(request.body)
                if not isinstance(body,dict):raise Invalid('Requête invalide.')
            return fn(request,body,*args,**kwargs)
        except Conflict as exc:return error(str(exc),409)
        except (Analysis.DoesNotExist,Account.DoesNotExist,Workspace.DoesNotExist,TeamMember.DoesNotExist,TeamInvitation.DoesNotExist):return error('Ressource introuvable.',404)
        except (Invalid,ValueError,TypeError,ValidationError,RecursionError):return error('Données invalides. Vérifiez les champs et le Blueprint.')
        except RequestDataTooBig:return error('La requête dépasse 1,5 Mo.',413)
        except Exception:
            # Do not log traceback locals, raw payloads or third-party exception contents.
            log.error('FlowFix request failed: %s',fn.__name__)
            return error('Service momentanément indisponible. Réessayez.',503)
    return wrapped

from .access import entitlement,check_access,record_usage,start_trial
from .catalog import PLANS,price_catalog
from .retention import history_days
from .teams import workspaces,analysis_access,authorized_analyses,sponsor,can_write,team_seats,can_manage,role_for

@require_POST
@endpoint
def trial(request,body):
    with transaction.atomic():
        account=Account.objects.select_for_update().get(user=request.user)
        until=start_trial(account)
    return JsonResponse({'trial_until':until,'message':'Essai activé pour 14 jours, sans paiement automatique.'})

@require_http_methods(['GET'])
@endpoint
def config(request,body):return JsonResponse({'csrf':get_token(request),'mode':'saas'})
@require_http_methods(['GET','POST'])
@endpoint
def profile(request,body):
    account=Account.objects.get(user=request.user)
    if request.method=='POST':
        fields=[]
        if 'display_name' in body:
            name=text(body['display_name'],60)
            if not name:raise Invalid('Nom requis.')
            account.display_name=intake({'description':name},'profile').user_description;fields.append('display_name')
        if 'language' in body:
            if body['language'] not in ('en','fr'):raise Invalid('Unsupported language.')
            account.language=body['language'];fields.append('language')
        if not fields:raise Invalid('No settings supplied.')
        account.save(update_fields=fields)
        if 'language' in fields:request.session['flowfix_language']=account.language
    _,limit,plan=entitlement(account)
    active_workspace=None
    if request.GET.get('workspace'):
        selected=workspaces(request.user).select_related('account').filter(pk=request.GET['workspace']).first()
        if selected:
            allowed,shared_limit,shared_plan=entitlement(selected.account)
            active_workspace={'name':selected.name,'plan':translate(shared_plan),'limit':shared_limit,'can_analyze':allowed,'trial_until':selected.account.agency_trial_until,'role':role_for(selected.account,request.user)}
        else:active_workspace={'plan':'Espace inaccessible','can_analyze':False,'role':None}
    return JsonResponse({'email_verified':verified(account),'display_name':account.display_name,'mode':'saas','active_workspace':active_workspace,'plan':translate(plan),'language':account.language,'usage':account.usage if account.usage_month==timezone.now().strftime('%Y-%m') else 0,'limit':limit,'billing_enabled':settings.BILLING_ENABLED,'beta_until':account.beta_until,'email':request.user.email,'free_remaining':account.free_remaining,'trial_until':account.agency_trial_until,'can_start_trial':getattr(settings,'AGENCY_TRIAL_ENABLED',False) and not account.agency_trial_started and not account.subscription and not account.ltd_active,'can_analyze':entitlement(account)[0],'workspaces':[{'id':str(w.pk),'name':w.name,'role':role_for(w.account,request.user),'team':w.account.display_name} for w in workspaces(request.user).select_related('account')],'history_days':history_days(account),'seats':team_seats(account),'offers':[{'plan':r['plan'],'interval':r['interval'],'name':PLANS.get(r['plan'],{'name':'Abonnement'})['name']} for r in price_catalog().values()]})
@require_POST
@endpoint
def preview(request,body):
    if limited(request,'preview',120):return error('Trop de requêtes.',429)
    p=intake({'blueprint':text(body.get('blueprint',''),1000000)},'preview')
    return JsonResponse({'modules':module_choices(p)})
def stored_analysis_count(account):
    from django.db.models import Q
    # Archive visibility is not physical deletion. Count all storage sponsored by
    # this account, excluding unrelated teams the owner happens to belong to.
    return Analysis.objects.filter(Q(owner=account.user,workspace__isnull=True)|Q(workspace__account=account)).count()

@require_http_methods(['GET','POST'])
@endpoint
def sessions(request,body):
    if request.method=='GET':
        keys=['id','title','created','updated','revision','resolution']
        query=analysis_access(request.user)
        if request.GET.get('archived')=='1':query=authorized_analyses(request.user).exclude(pk__in=query.values('pk'))
        space=request.GET.get('workspace')
        query=query.filter(workspace_id=space) if space else query.filter(workspace__isnull=True,owner=request.user)
        rows=query.values(*['data__'+k for k in keys])
        return JsonResponse(sorted([{k:d['data__'+k] for k in keys} for d in rows],key=lambda d:d['updated'],reverse=True),safe=False)
    if diagnostic_limited(request):return error('Trop de calculs rapprochés. Réessayez plus tard.',429)
    with transaction.atomic():
        account,space,role=sponsor(request.user,body.get('workspace'));can_write(account,role);check_access(account)
        if space and team_seats(account)<2:raise Conflict('L’offre actuelle ne permet pas de nouvelles analyses partagées.')
        if entitlement(account)[1] is not None and stored_analysis_count(account)>=500:raise Conflict('Limite de 500 analyses stockées. Exportez puis supprimez les anciennes analyses.')
        sid=str(uuid.uuid4());clean,output=analyze(Sessions.parse_inputs(None,body),sid)
        d=dict(id=sid,workspace_id=str(space.pk) if space else None,title=(clean['description'] or clean['error'] or 'Analyse de Blueprint')[:90],created=now(),updated=now(),revision=1,resolution='unknown',inputs=clean,output=output,cycle=0,answered=[],history=[])
        if len(json.dumps(d).encode())>3000000:raise Invalid('Analyse trop volumineuse.')
        record=Analysis.objects.create(id=sid,owner=request.user,workspace=space,data=d)
        d['accounting']=record_usage(account,record,output)
        record.data=d;record.save(update_fields=['data'])
    return JsonResponse(d,status=201)
@require_http_methods(['GET','POST'])
@endpoint
def session(request,body,sid,operation=None):
    if request.method=='GET':
        d=copy.deepcopy(analysis_access(request.user).get(id=sid).data)
        from local_app.service import enrich_first_reading
        enrich_first_reading(d)
        if operation=='export':
            class Export:
                def get(self,_):return d
            return JsonResponse(Sessions.export_report(Export(),str(sid)))
        if operation:return error('Action invalide.',405)
        return JsonResponse(d)
    if operation not in ['answer','feedback','edit','delete']:return error('Action invalide.',405)
    if operation in ['answer','edit'] and diagnostic_limited(request):return error('Trop de calculs rapprochés. Réessayez plus tard.',429)
    with transaction.atomic():
        query=authorized_analyses(request.user) if operation=='delete' else analysis_access(request.user)
        visible=query.get(id=sid)
        account,space,role=sponsor(request.user,visible.workspace_id)
        can_write(account,role,operation)
        record=(authorized_analyses(request.user) if operation=='delete' else analysis_access(request.user)).select_for_update().get(id=sid);d=copy.deepcopy(record.data)
        if body.get('revision')!=d['revision']:raise Conflict('Cette analyse a changé. Rechargez-la.')
        if operation=='delete':record.delete();return JsonResponse({'deleted':True})
        if operation in ['answer','edit']:check_access(account)
        if len(d['history'])>=200:raise Conflict('Historique maximal atteint. Exportez cette analyse et créez-en une nouvelle.')
        d=mutate(d,body,operation)
        if len(json.dumps(d).encode())>3000000:raise Invalid('Historique trop volumineux. Exportez puis créez une nouvelle analyse.')
        record.data=d
        if operation in ['answer','edit']:d['accounting']=record_usage(account,record,d['output'])
        record.data=d;record.save(update_fields=['data'])
    return JsonResponse(d)
@require_POST
@endpoint
def delete_account(request,body):
    if limited(request,'delete-account',5,identity=request.user.pk):return error('Trop de tentatives. Réessayez dans 15 minutes.',429)
    if not request.user.check_password(body.get('password','')):return error('Mot de passe incorrect.',403)
    with transaction.atomic():
        account=Account.objects.select_for_update().get(user=request.user)
        if TeamMember.objects.filter(account=account).exists():return error('Révoquez les membres et supprimez vos analyses et espaces partagés avant de supprimer ce compte.',409)
        if Workspace.objects.filter(account=account,analysis__isnull=False).exists():return error('Supprimez les analyses partagées avant de supprimer ce compte.',409)
        if Analysis.objects.filter(owner=request.user,workspace__isnull=False).exclude(workspace__account=account).exists():return error('Des analyses appartiennent à une équipe. Demandez au propriétaire de les supprimer avant de supprimer votre compte.',409)
        if account.subscription:return error('Résiliez votre abonnement dans le portail puis contactez le support pour supprimer le compte après sa clôture.',409)
        request.user.delete()
    logout(request);return JsonResponse({'deleted':True})
def health(request):
    from django.db import connection
    try:
        with connection.cursor() as c:c.execute('SELECT 1')
    except Exception:return error('unavailable',503)
    return JsonResponse({'status':'ok'})


def team_page(request):
    if not request.user.is_authenticated:return redirect('/login/?next=/team/')
    return render(request,'team.html')

@require_http_methods(['GET','POST'])
@endpoint
def team(request,body):
    if request.method=='GET':
        a=Account.objects.get(user=request.user)
        return JsonResponse({'seats':team_seats(a),'members':[{'id':m.pk,'email':m.user.email,'role':m.role} for m in TeamMember.objects.filter(account=a).select_related('user')],
            'invitations':[{'id':str(i.pk),'email':i.email,'role':i.role,'expires':i.expires} for i in TeamInvitation.objects.filter(account=a,used=False,expires__gt=timezone.now())],
            'spaces':[{'id':str(w.pk),'name':w.name,'role':role_for(w.account,request.user),'team':w.account.display_name} for w in workspaces(request.user).select_related('account')]})
    if limited(request,'team',60):return error('Trop de demandes rapprochées.',429)
    op=body.get('operation')
    with transaction.atomic():
        if op=='accept':
            require_verified(Account.objects.select_related('user').get(user=request.user))
            digest=hashlib.sha256(text(body.get('code',''),200).encode()).hexdigest()
            invite=TeamInvitation.objects.filter(digest=digest,email__iexact=request.user.email,used=False,expires__gt=timezone.now()).first()
            if not invite:raise Invalid('Invitation invalide.')
            a=Account.objects.select_for_update().get(pk=invite.account_id)
            invite=TeamInvitation.objects.select_for_update().get(pk=invite.pk)
            if invite.used or invite.expires<=timezone.now():raise Conflict('Invitation expirée ou déjà utilisée.')
            can_manage(a)
            if TeamMember.objects.filter(account=a).count()+1>=team_seats(a):raise Conflict('Tous les sièges de cette équipe sont occupés.')
            if a.user_id==request.user.pk:raise Invalid('Le propriétaire fait déjà partie de cette équipe.')
            member,created=TeamMember.objects.get_or_create(account=a,user=request.user,defaults={'role':invite.role})
            if not created:raise Conflict('Vous faites déjà partie de cette équipe.')
            invite.used=True;invite.save(update_fields=['used'])
            return JsonResponse({'message':'Invitation acceptée. Vos espaces clients sont disponibles dans le panneau.'})
        a=Account.objects.select_for_update().get(user=request.user)
        if op=='revoke':
            TeamMember.objects.get(pk=body.get('id'),account=a).delete()
        elif op=='cancel_invite':
            i=TeamInvitation.objects.get(pk=body.get('id'),account=a);i.used=True;i.save(update_fields=['used'])
        elif op=='delete_space':
            w=Workspace.objects.get(pk=body.get('id'),account=a)
            if Analysis.objects.filter(workspace=w).exists():raise Conflict('Exportez puis supprimez les analyses de cet espace avant de le supprimer.')
            w.delete()
        elif op=='create_space':
            can_manage(a)
            name=text(body.get('name',''),80)
            if not name:raise Invalid('Nom requis.')
            if Workspace.objects.filter(account=a).count()>=100:raise Conflict('Limite de 100 espaces atteinte. Contactez le support.')
            Workspace.objects.create(account=a,name=intake({'description':name},'workspace').user_description)
        elif op=='invite':
            import secrets
            can_manage(a)
            email=text(body.get('email',''),254).lower();validate_email(email)
            role=body.get('role')
            if role not in ['editor','viewer'] or email==request.user.email.lower():raise Invalid('Invitation invalide.')
            if TeamMember.objects.filter(account=a,user__email__iexact=email).exists():raise Conflict('Cette personne fait déjà partie de votre équipe.')
            pending=TeamInvitation.objects.filter(account=a,used=False,expires__gt=timezone.now())
            if pending.filter(email=email).exists():raise Conflict('Une invitation est déjà en cours pour cette adresse.')
            if TeamMember.objects.filter(account=a).count()+pending.count()+1>=team_seats(a):raise Conflict('Tous les sièges sont occupés ou réservés par une invitation.')
            code=secrets.token_urlsafe(32)
            TeamInvitation.objects.create(account=a,email=email,role=role,digest=hashlib.sha256(code.encode()).hexdigest(),expires=timezone.now()+timedelta(days=7))
            return JsonResponse({'code':code,'message':'Transmettez ce code au destinataire par un canal privé. Il expire dans 7 jours. Aucun email automatique envoyé.'},status=201)
        else:raise Invalid('Action inconnue.')
    return JsonResponse({'message':'Modification enregistrée.'})
