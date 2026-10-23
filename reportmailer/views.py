"""Company-only Report Email endpoints, gated independently of navigation."""
import json
from datetime import date
from functools import wraps
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from financee.db_errors import user_db_error
from financee.security import rate_limit_response
from . import service


def guarded(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        company = getattr(request, 'tenant_company', None)
        if not company or not getattr(request, 'tenant_is_active', False):
            return JsonResponse({'message':'An active company membership is required.'}, status=403)
        if not service.company_allowed(company):
            return JsonResponse({'message':'Company report delivery is unavailable.'}, status=403)
        if not service.user_allowed(request.user.pk, company.pk):
            return JsonResponse({'message':'Report Email and Sale-wise Profit permissions are required.'}, status=403)
        limited = rate_limit_response(request, 'report_email', limit=60, window=60)
        if limited is not None: return limited
        try:
            return view(request, *args, **kwargs)
        except (service.ReportEmailError, ValueError, TypeError, ValidationError) as exc:
            return JsonResponse({'message':str(exc)}, status=400)
        except Exception as exc:
            return JsonResponse({'message':user_db_error(exc, 'The report email operation could not be completed.')}, status=400)
    return wrapped


def payload(request):
    if len(request.body)>16384: raise ValueError('Request is too large.')
    try: data=json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError): raise ValueError('Malformed JSON request.')
    if not isinstance(data,dict): raise ValueError('A JSON object is required.')
    return data


def email(value):
    if not isinstance(value,str) or len(value)>254: raise ValueError('Enter a valid email address.')
    value=value.strip()
    validate_email(value)
    if not value.isascii(): raise ValueError('Use an ASCII mailbox address.')
    return value


def text(data,key,default='',limit=150):
    value=data.get(key,default)
    if not isinstance(value,str) or len(value)>limit or '\r' in value or '\n' in value:
        raise ValueError(f'Invalid {key.replace("_"," ")}.')
    return value.strip()


def boolean(data,key,default=True):
    value=data.get(key,default)
    if not isinstance(value,bool): raise ValueError(f'{key} must be true or false.')
    return value


def read_settings(company):
    raw=service.query('SELECT report_email_settings_get()') or {}
    raw['password_from_env']=False
    raw['authorization_valid']=service.user_allowed(raw.get('authorized_user_id'),company.pk)
    raw['currency_code']=company.base_currency_id
    raw['capture_only']=service.review_transport()
    return raw


@guarded
@require_GET
def report_email_module(request):
    return render(request,'report_email_templates/report_email.html',{'capture_only':service.review_transport()})


@guarded
@require_GET
def settings_get(request):
    raw=read_settings(request.tenant_company)
    return JsonResponse({'status':'ok','settings':raw,'schedule':service.schedule_state(raw)})


@guarded
@require_POST
def settings_save(request):
    data=payload(request)
    args={key:text(data,key,default) for key,default in (
        ('sender_name','Financee Reports'),('smtp_host','smtp.gmail.com'),('timezone','Asia/Karachi'))}
    args['sender_email']=email(data.get('sender_email'))
    args['smtp_host']=args['smtp_host'].lower()
    if args['smtp_host'] not in settings.REPORT_EMAIL_SMTP_HOSTS:
        raise ValueError('This SMTP provider is not enabled by the service operator.')
    try: ZoneInfo(args['timezone'])
    except (ZoneInfoNotFoundError,ValueError): raise ValueError('Use a valid business time zone, such as Asia/Karachi.')
    for key,default,lo,hi in (('smtp_port',587,1,65535),('send_hour',0,0,23),('send_minute',0,0,59)):
        value=data.get(key,default)
        if isinstance(value,bool) or str(value).strip().isdigit() is False: raise ValueError(f'Invalid {key}.')
        args[key]=int(value)
        if not lo<=args[key]<=hi: raise ValueError(f'Invalid {key}.')
    args['use_tls']=boolean(data,'use_tls')
    args['is_enabled']=boolean(data,'is_enabled',False)
    if (args['smtp_port'],args['use_tls']) not in ((587,True),(465,False)):
        raise ValueError('Use port 587 with TLS, or port 465 with implicit TLS.')
    if 'app_password' in data:
        value=data['app_password']
        if not isinstance(value,str) or len(value)>1024: raise ValueError('Invalid app password.')
        args['app_password']=value
    args.update(actor=request.user.get_username(),authorized_user_id=request.user.pk)
    service.query('SELECT save_report_email_settings_from_json(%s::jsonb)',[json.dumps(args)])
    return JsonResponse({'status':'ok','settings':read_settings(request.tenant_company),'message':'Sending mailbox saved.'})


@guarded
@require_GET
def recipients_list(request):
    return JsonResponse({'status':'ok','recipients':service.query('SELECT report_email_recipients_list()') or []})


@guarded
@require_POST
def recipient_write(request, action):
    data=payload(request)
    args={'actor':request.user.get_username()}
    if action in ('update','delete'):
        args['recipient_id']=int(data.get('recipient_id',0))
    if action in ('add','update'):
        args.update(email=email(data.get('email')),label=text(data,'label'),is_active=boolean(data,'is_active'))
    if action=='delete':
        result=service.query('SELECT delete_report_recipient(%s)',[args['recipient_id']])
    else:
        fn='add_report_recipient_from_json' if action=='add' else 'update_report_recipient_from_json'
        result=service.query(f'SELECT {fn}(%s::jsonb)',[json.dumps(args)])
    return JsonResponse({'status':'ok','recipients':result,'message':'Recipient list updated.'})


@guarded
@require_GET
def log_list(request):
    limit=min(100,max(1,int(request.GET.get('limit',50))))
    offset=min(100000,max(0,int(request.GET.get('offset',0))))
    return JsonResponse({'status':'ok','log':service.query('SELECT report_email_log_list(%s,%s)',[limit,offset])})


def report_day(data,default=None):
    raw=data.get('report_date','')
    if not raw: return default
    if not isinstance(raw,str) or len(raw)!=10: raise ValueError('Use YYYY-MM-DD for the business day.')
    return date.fromisoformat(raw)


@guarded
@require_POST
def send(request,trigger):
    limited=rate_limit_response(request,'report_email_send',limit=5,window=60)
    if limited is not None: return limited
    result=service.send_report(request.tenant_company.pk,report_day(payload(request)),
                               trigger=trigger,actor_id=request.user.pk)
    return JsonResponse(result,status=200 if result['status']=='sent' else 400)


@guarded
@require_POST
def rearm_day(request):
    raw=service.query('SELECT report_email_settings_get()') or {}
    state=service.schedule_state(raw)
    day=report_day(payload(request),date.fromisoformat(state['report_date']))
    # Only yesterday can be scheduled. Older days can be sent explicitly by hand.
    if str(day)!=state['report_date']: raise ValueError('Only the current scheduled business day can be re-armed. Use Send now for older reports.')
    with service.delivery_lock(request.tenant_company):
        service.query('SELECT report_email_recover()')
        result=service.query('SELECT rearm_report_email_day(%s,%s)',[day,request.user.get_username()])
    return JsonResponse({'status':'ok','result':result,'message':'Day re-armed; delivery waits for the configured time and authorization.'})
