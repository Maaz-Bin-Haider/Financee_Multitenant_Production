"""Tenant boundaries, durable attempts and SMTP. No process-wide mailbox state."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import logging
import os
import re
import smtplib
import time
from decimal import Decimal
from email.utils import formataddr
from email.policy import SMTP
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection
from tenancy.models import Company, Membership, BLOCKED_STATES, PROVISIONING_READY
from tenancy.schema_verification import verify_company_schema
from tenancy.utils import set_search_path, reset_search_path
from . import reports

logger = logging.getLogger(__name__)
PERMISSIONS = ('auth.send_reports', 'auth.can_view_sale_wise_profit')


class ReportEmailError(Exception):
    pass


class PartialDelivery(Exception):
    pass


def query(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        row = cursor.fetchone()
        if not row: return None
        value = row[0]
        # Django deliberately registers jsonb as text for ORM JSONField decoding.
        # Raw cursors must decode JSON OIDs explicitly; ordinary text stays text.
        if cursor.description[0].type_code in (114, 3802) and isinstance(value, str):
            return json.loads(value, parse_float=Decimal)
        return value


def review_transport():
    project = os.environ.get('FINANCEE_REVIEW_PROJECT', '')
    if not project:
        return False
    if not re.fullmatch(r'financee_review_(darkmode|email|spotlight|activity|regression)(_[a-z0-9]{1,16})?', project):
        raise ReportEmailError('Invalid local review configuration.')
    db = settings.DATABASES['default']
    if (db['NAME'], db['USER'], db['HOST']) != ('financee_review', 'review', 'db'):
        raise ReportEmailError('Local mail capture requires the isolated review database.')
    return True


def company_allowed(company):
    return (getattr(settings, 'REPORT_EMAIL_ENABLED', True) and company.is_active
        and company.provisioning_state == PROVISIONING_READY
        and company.subscription_state() not in BLOCKED_STATES
        and company.feature_enabled('report_email')
        and company.feature_enabled('sales_reports.sale_wise'))


def user_allowed(user_id, company_id):
    user = get_user_model().objects.filter(pk=user_id, is_active=True,
        membership__company_id=company_id).first()
    return user is not None and all(user.has_perm(p) for p in PERMISSIONS)


@contextmanager
def tenant(company):
    if not re.fullmatch(r'tenant_company_[1-9][0-9]*', company.schema_name):
        raise ReportEmailError('Company schema is unavailable.')
    previous = query('SHOW search_path')
    try:
        set_search_path(company.schema_name)
        if not verify_company_schema(company, use_cache=False).ok:
            raise ReportEmailError('Company schema is unavailable.')
        # Fail closed if an upgraded tenant has not received this feature yet.
        if not query('SELECT to_regprocedure(%s)', [f'{company.schema_name}.report_email_settings_get()']):
            raise ReportEmailError('Company report email is not installed.')
        yield
    finally:
        if connection.connection is not None:
            query("SELECT set_config('search_path',%s,false)", [previous])


@contextmanager
def delivery_lock(company):
    key = company.schema_name + ':report_email'
    locked = query('SELECT pg_try_advisory_lock(hashtextextended(%s,0))', [key])
    try:
        if not locked:
            raise ReportEmailError('A report email operation is already in progress. Refresh shortly.')
        yield
    finally:
        if locked and connection.connection is not None:
            query('SELECT pg_advisory_unlock(hashtextextended(%s,0))', [key])


def schedule_state(raw, now=None):
    zone = ZoneInfo(raw.get('timezone') or 'Asia/Karachi')
    now = (now or datetime.now(tz=zone)).astimezone(zone)
    day = now.date() - timedelta(days=1)
    state = query("""SELECT jsonb_build_object('report_date',%s::date,'due',report_email_due(%s),
        'last_sent_at',max(finished_at) FILTER(WHERE status='sent' AND NOT superseded),
        'attempts',count(*) FILTER(WHERE status IN ('failed','skipped') AND NOT superseded),
        'unknown',bool_or(status='unknown' AND NOT superseded),
        'in_progress',bool_or(status IN ('pending','sending') AND NOT superseded))
        FROM report_email_log WHERE report_date=%s AND trigger_source='schedule'""", [day]*3)
    state['time_reached'] = (now.hour, now.minute) >= (raw.get('send_hour', 0), raw.get('send_minute', 0))
    return state


def deliver(message, raw):
    if review_transport():
        smtp = get_connection('django.core.mail.backends.smtp.EmailBackend', host='mailpit', port=1025,
                              username='', password='', use_tls=False, use_ssl=False, timeout=30)
    else:
        host = (raw.get('smtp_host') or '').lower()
        if host not in settings.REPORT_EMAIL_SMTP_HOSTS:
            raise ReportEmailError('This SMTP provider is not enabled by the service operator.')
        smtp = get_connection('django.core.mail.backends.smtp.EmailBackend', host=host,
            port=raw['smtp_port'], username=raw['sender_email'], password=raw['password'],
            use_tls=raw['use_tls'], use_ssl=not raw['use_tls'] and raw['smtp_port'] == 465, timeout=30)
    with smtp:
        # Inspect partial refusal explicitly: an SMTP server may accept some
        # recipients and refuse others. Retrying all would duplicate delivery.
        refused = smtp.connection.sendmail(raw['sender_email'], message.to,
            message.message(policy=SMTP).as_bytes())
        if refused:
            raise PartialDelivery()


def send_report(company_id, day=None, *, trigger='manual', actor_id=None, now=None):
    started = time.monotonic()
    company = Company.objects.select_related('base_currency').get(pk=company_id)
    if not company_allowed(company):
        raise ReportEmailError('Company report delivery is unavailable.')
    with tenant(company), delivery_lock(company):
        query('SELECT report_email_recover()')
        raw = query('SELECT report_email_settings_get()') or {}
        if not user_allowed(raw.get('authorized_user_id'), company.pk):
            raise ReportEmailError('An authorized company member must save the mailbox again.')
        if trigger != 'schedule' and not user_allowed(actor_id, company.pk):
            raise ReportEmailError('You do not have permission to send this report.')
        if trigger == 'schedule':
            state = schedule_state(raw, now)
            if not state['time_reached'] or not state['due']:
                return {'status': 'skipped', 'message': 'No scheduled delivery is due.'}
            day = datetime.fromisoformat(state['report_date']).date()
        if day is None:
            zone = ZoneInfo(raw.get('timezone') or 'Asia/Karachi')
            day = datetime.now(tz=zone).date() - timedelta(days=1)
        if trigger not in ('manual', 'schedule', 'test'):
            raise ReportEmailError('Invalid delivery source.')
        actor = 'scheduler' if trigger == 'schedule' else str(actor_id)
        attempt = query('SELECT report_email_claim(%s,%s,%s)', [day, trigger, actor])
        if attempt is None:
            return {'status': 'skipped', 'message': 'No scheduled delivery is due.'}
        data = {'status': 'failed', 'currency_code': company.base_currency_id}
        def record(status, message=''):
            data.update(status=status, error_message=message,
                        duration_ms=int((time.monotonic()-started)*1000))
            query('SELECT report_email_finish(%s,%s::jsonb)', [attempt, json.dumps(data, default=str)])
        sending = False
        try:
            raw['password'] = query('SELECT app_password FROM report_email_settings WHERE id=1')
            targets = query('SELECT report_email_recipients_list()') or []
            data['recipients'] = [r['email'] for r in targets if r['is_active']]
            if not raw['password'] or not data['recipients']:
                record('skipped', 'Save an app password and at least one active recipient.')
                return {'status': 'skipped', 'message': data['error_message']}
            if not review_transport() and raw['smtp_host'].lower() not in settings.REPORT_EMAIL_SMTP_HOSTS:
                raise ReportEmailError('This SMTP provider is not enabled by the service operator.')
            report = reports.fetch_report(day)
            totals = report['totals']
            data.update(subject=reports.subject(report, day, company), unit_count=totals['units'],
                        total_sales=totals['revenue'], total_profit=totals['profit'])
            if not company_allowed(Company.objects.get(pk=company.pk)) or not user_allowed(raw['authorized_user_id'], company.pk):
                raise ReportEmailError('Company delivery authorization changed; save the mailbox again.')
            message = EmailMultiAlternatives(
                subject=('[TEST] ' if trigger == 'test' else '') + data['subject'],
                body=reports.build_text(report, day, company),
                from_email=formataddr((raw['sender_name'], raw['sender_email'])), to=data['recipients'])
            message.attach_alternative(reports.build_html(report, day, company, raw['timezone']), 'text/html')
            message.attach(f'sale-wise-profit-{day.isoformat()}.csv', reports.build_csv(report, day, company), 'text/csv')
            record('sending')  # committed evidence before the network boundary
            sending = True
            deliver(message, raw)
            record('sent')
        except ReportEmailError as exc:
            record('failed', str(exc))
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused,
                smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            record('failed', 'SMTP server refused delivery. Check the mailbox and recipients.')
        except Exception:
            # Exception strings may contain SMTP credentials or remote content.
            # Unknown delivery is held for reconciliation, never auto-retried.
            record('unknown' if sending else 'failed',
                'Delivery outcome is uncertain; check the inbox before re-arming.' if sending
                else 'Report preparation failed. Check configuration and try again.')
        return {'status': data['status'], 'message': 'Sent to the configured recipients.'
                if data['status']=='sent' else data['error_message'], 'log_id': attempt,
                'report_date': str(day)}


def tick(now=None, heartbeat=lambda: None):
    reset_search_path()
    ids = list(Company.objects.filter(is_active=True, provisioning_state=PROVISIONING_READY).values_list('pk', flat=True))
    for company_id in ids:
        heartbeat()
        try:
            send_report(company_id, trigger='schedule', now=now)
        except Exception as exc:
            # Isolate each company and never print mailbox passwords or SQL.
            logger.info('Report email company %s: %s', company_id, type(exc).__name__)
        finally:
            reset_search_path()
