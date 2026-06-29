"""
tenancy.middleware
==================
Request-scoped tenant activation — the heart of the isolation guarantee.

For every request this middleware:

1. Resolves the schema for the authenticated user (via their Membership).
2. Issues ``SET search_path TO "<schema>", public`` on *this request's*
   database connection, at the very start of the request.
3. Always resets the path to ``public`` in a ``finally`` block, so a connection
   returned to the pool / reused by the worker never carries a previous
   request's tenant context.

Why this is thread-/request-safe
--------------------------------
* No module-level, global, or singleton tenant variable is ever written.
  The schema lives only on the local ``request`` object and on the connection
  for the duration of the request.
* Under Gunicorn sync workers each worker processes one request at a time on
  its own connection, so two tenants can never observe each other's
  ``search_path``. Even with persistent connections (CONN_MAX_AGE), the
  start-of-request SET overwrites any stale value before a single query runs.

Resolution rules
----------------
* Unauthenticated request                -> ``public`` (login pages, static).
* Authenticated, active membership+company -> the tenant schema.
* Authenticated, no membership (e.g. a fresh superuser) -> ``public``.

Superusers still land in ``public`` by default but ``public`` is always on the
path, so the custom admin keeps working; if a superuser is also given a
Membership they additionally get that tenant's business data in the UI.
"""
import json

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from financee.security import (
    TENANT_GUARD_EXEMPT_PREFIXES,
    deny_response,
    has_required_permissions,
    rate_limit_response,
    required_permissions_for_path,
    tenant_required_response,
)
from .utils import (
    PUBLIC_SCHEMA,
    reset_search_path,
    set_search_path,
    tenant_schema_version_ok,
)


class TenantSchemaMiddleware(MiddlewareMixin):
    """Activate the current user's schema for the duration of the request."""

    def process_request(self, request):
        schema, tenant_ok = self._resolve_schema(request)
        request.tenant_schema = schema
        request.tenant_is_active = tenant_ok
        set_search_path(schema)
        if tenant_ok and schema != PUBLIC_SCHEMA:
            request.tenant_is_active = tenant_schema_version_ok(schema)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        if not getattr(request, "tenant_is_active", False):
            if request.path.startswith(TENANT_GUARD_EXEMPT_PREFIXES):
                return None
            return tenant_required_response(request)

        perms, mode = required_permissions_for_path(request.path)
        if perms and not has_required_permissions(user, perms, mode):
            return deny_response(request)

        limited = self._rate_limit_request(request)
        if limited is not None:
            return limited

        return None

    @staticmethod
    def _rate_limit_request(request):
        path = request.path
        if path.startswith("/home/api/"):
            return rate_limit_response(request, "dashboard_api", limit=180, window=60)
        if path.startswith(("/accountsReports/", "/sales-reports/api/")):
            return rate_limit_response(request, "reports", limit=90, window=60)
        if "autocomplete" in path or "lookup" in path:
            return rate_limit_response(request, "lookup", limit=240, window=60)
        return None

    def process_response(self, request, response):
        response = self._scrub_error_response(response)
        reset_search_path()
        return response

    def process_exception(self, request, exception):
        # Make sure a failed request never leaves tenant context on the
        # connection. process_response also resets, but exceptions may bypass it.
        reset_search_path()
        if request.path.startswith("/admin/"):
            return None
        return JsonResponse(
            {"status": "error", "message": "An unexpected error occurred."},
            status=500,
        )

    @staticmethod
    def _scrub_error_response(response):
        content_type = response.get("Content-Type", "")
        if "application/json" not in content_type or response.status_code < 400:
            return response
        try:
            payload = json.loads(response.content or "{}")
        except Exception:
            return response
        if not isinstance(payload, dict):
            return response
        payload.pop("details", None)
        if response.status_code >= 500:
            payload = {"status": "error", "message": "An unexpected error occurred."}
        return JsonResponse(payload, status=response.status_code)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_schema(request) -> tuple[str, bool]:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return PUBLIC_SCHEMA, True

        # Membership is a reverse OneToOne: when the user has none, accessing
        # ``user.membership`` raises Membership.DoesNotExist (NOT None), so the
        # lookup must be guarded with try/except rather than getattr default.
        from .models import Membership

        try:
            membership = user.membership
        except Membership.DoesNotExist:
            return PUBLIC_SCHEMA, False

        company = membership.company
        if company is None or not company.is_active or not company.schema_name:
            return PUBLIC_SCHEMA, False

        return company.schema_name, True
