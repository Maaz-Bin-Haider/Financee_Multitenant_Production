"""Observe after a successful view and before TenantSchemaMiddleware resets scope."""
import json
import logging
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from . import work

logger = logging.getLogger(__name__)


class ActivityMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not settings.TEAM_ACTIVITY_RECORDING_ENABLED: return
        if request.method == 'POST' and request.resolver_match.view_name in work.DOCUMENTS:
            try:
                payload = json.loads(request.body or '{}') if request.content_type == 'application/json' else request.POST.dict()
                request.activity_payload = payload if isinstance(payload,dict) else {}
            except Exception:
                request.activity_payload = {}

    def process_response(self, request, response):
        if not settings.TEAM_ACTIVITY_RECORDING_ENABLED or not getattr(request, 'tenant_is_active',False): return response
        if response.status_code != 200 or not response.get('Content-Type','').startswith('application/json'): return response
        try:
            data = json.loads(response.content)
            work.observe(request,getattr(request,'activity_payload',{}),data)
        except Exception as exc:
            logger.warning('Activity observation failed (%s)',type(exc).__name__)
        return response
