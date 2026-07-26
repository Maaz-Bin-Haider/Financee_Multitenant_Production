"""Phase 16 physical-count and inventory-adjustment HTTP adapter."""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render

from .models import INVENTORY_MODE_QUANTITY


def _error(message, status=400):
    return JsonResponse({"success": False, "status": "error", "message": message},
                        status=status)


def _can(request, permission):
    return request.user.is_superuser or (
        not request.user.groups.filter(name="view_only_users").exists()
        and request.user.has_perm(permission)
    )


def _available(request):
    company = getattr(request, "tenant_company", None)
    return bool(company and company.inventory_mode == INVENTORY_MODE_QUANTITY)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


@login_required
def counts(request):
    if not _available(request):
        return _error("Quantity physical counts are unavailable.", 404)
    if request.method == "GET":
        return render(request, "tenancy_templates/quantity_counts.html", {
            "can_create": _can(request, "auth.create_physical_count"),
            "can_approve": _can(request, "auth.approve_inventory_adjustment"),
            "can_reverse": _can(request, "auth.reverse_inventory_adjustment"),
        })
    try:
        data = json.loads(request.body or "{}")
        if not isinstance(data, dict):
            raise ValueError
        data["created_by_id"] = request.user.pk
        action = (data.get("action") or "create").lower()
        count_id = int(data.get("count_id")) if data.get("count_id") else None
        if action in ("create", "submit"):
            if not _can(request, "auth.create_physical_count"):
                return _error("You do not have permission to create counts.", 403)
            data.setdefault("idempotency_key", str(uuid.uuid4()))
            sql, params = "SELECT quantity_create_physical_count(%s::jsonb)", [
                json.dumps(data)
            ]
        elif action in ("approve", "post"):
            if not _can(request, "auth.approve_inventory_adjustment"):
                return _error("You do not have permission to approve adjustments.", 403)
            sql, params = "SELECT quantity_approve_physical_count(%s,%s)", [
                count_id, request.user.pk
            ]
        elif action == "reverse":
            if not _can(request, "auth.reverse_inventory_adjustment"):
                return _error("You do not have permission to reverse adjustments.", 403)
            sql, params = "SELECT quantity_reverse_physical_count(%s,CURRENT_DATE,%s)", [
                count_id, request.user.pk
            ]
        else:
            return _error("Unknown physical-count action.")
        with connection.cursor() as cur:
            cur.execute(sql, params)
            result = _json(cur.fetchone()[0])
        return JsonResponse({"success": True, **result})
    except (TypeError, ValueError):
        return _error("Physical-count request is invalid.")
    except DatabaseError:
        return _error("Count or adjustment is invalid or conflicts with stock.")


@login_required
def navigate(request):
    try:
        current = request.GET.get("current_id")
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_physical_count_navigate(%s,%s)", [
                request.GET.get("action") or "last",
                int(current) if current else None,
            ])
            result = _json(cur.fetchone()[0])
        return JsonResponse(result) if result else _error("No count found.", 404)
    except (DatabaseError, TypeError, ValueError):
        return _error("Unable to navigate physical counts.")


@login_required
def summary(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_physical_count_summary(%s::date,%s::date)", [
                request.GET.get("from") or None, request.GET.get("to") or None,
            ])
            return JsonResponse(_json(cur.fetchone()[0]))
    except DatabaseError:
        return _error("Physical-count date range is invalid.")
