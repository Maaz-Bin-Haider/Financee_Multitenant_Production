import json

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from .models import INVENTORY_MODE_QUANTITY


def _allowed(request):
    company = getattr(request, "tenant_company", None)
    return (
        company
        and company.inventory_mode == INVENTORY_MODE_QUANTITY
        and (request.user.is_superuser
             or request.user.has_perm("auth.view_quantity_audit"))
    )


@login_required
def audit_log(request):
    if not _allowed(request):
        return JsonResponse(
            {"success": False, "message": "Access denied."}, status=403
        )
    entity_type = request.GET.get("entity_type") or None
    entity_id = request.GET.get("entity_id") or None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_audit_log(%s,%s,%s)",
            [entity_type, entity_id, request.GET.get("limit") or 200],
        )
        events = cursor.fetchone()[0]
    if isinstance(events, str):
        events = json.loads(events)
    if request.headers.get("Accept") == "application/json" or request.GET.get("format") == "json":
        return JsonResponse({"success": True, "events": events})
    return render(request, "tenancy_templates/quantity_audit.html",
                  {"audit_events": events})
