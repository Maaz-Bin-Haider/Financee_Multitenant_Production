"""Permission-protected quantity warehouse JSON endpoints."""

import json

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import INVENTORY_MODE_QUANTITY
from .capabilities import reject_serial_payload


def _error(message, status=400):
    return JsonResponse({"status": "error", "message": message}, status=status)


def _available(request):
    company = getattr(request, "tenant_company", None)
    return bool(company and company.inventory_mode == INVENTORY_MODE_QUANTITY)


def _can(request, permission):
    return (
        request.user.is_superuser
        or (
            not request.user.groups.filter(name="view_only_users").exists()
            and request.user.has_perm(permission)
        )
    )


def _payload(request):
    try:
        value = json.loads(request.body or "{}")
    except (TypeError, ValueError):
        raise ValueError("A valid JSON object is required.")
    if not isinstance(value, dict):
        raise ValueError("A valid JSON object is required.")
    reject_serial_payload(value)
    value["user_id"] = request.user.pk
    return value


@login_required
@require_GET
def warehouse_page(request):
    if not _available(request):
        return _error("Quantity warehouse management is unavailable.", 404)
    return render(request, "tenancy_templates/quantity_warehouses.html", {
        "can_create": _can(request, "auth.create_warehouse"),
        "can_update": _can(request, "auth.update_warehouse"),
        "can_delete": _can(request, "auth.delete_warehouse"),
    })


@login_required
@require_GET
def warehouse_list(request):
    if not _available(request):
        return _error("Quantity warehouse API is unavailable.", 404)
    term = (request.GET.get("term") or "").strip()
    active_only = request.GET.get("active", "true").lower() != "false"
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM quantity_warehouse_lookup(%s, %s)",
            [term, active_only],
        )
        columns = [column[0] for column in cur.description]
        warehouses = [dict(zip(columns, row)) for row in cur.fetchall()]
    return JsonResponse({
        "status": "success",
        "count": len(warehouses),
        "warehouses": warehouses,
    })


@login_required
@require_GET
def default_warehouse(request):
    if not _available(request):
        return _error("Quantity warehouse API is unavailable.", 404)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT w.warehouse_id, w.warehouse_code, w.warehouse_name
              FROM warehouses w
             WHERE w.warehouse_id = quantity_default_warehouse()
        """)
        row = cur.fetchone()
    return JsonResponse({
        "status": "success",
        "warehouse": None if row is None else {
            "warehouse_id": row[0],
            "warehouse_code": row[1],
            "warehouse_name": row[2],
        },
    })


@login_required
@require_POST
def create_warehouse(request):
    if not _available(request):
        return _error("Quantity warehouse API is unavailable.", 404)
    if not _can(request, "auth.create_warehouse"):
        return _error("You do not have permission to create warehouses.", 403)
    try:
        payload = _payload(request)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_create_warehouse(%s::jsonb)",
                [json.dumps(payload)],
            )
            warehouse_id = cur.fetchone()[0]
    except ValueError as exc:
        return _error(str(exc))
    except (DatabaseError, TypeError):
        return _error("Warehouse data is invalid or already exists.")
    return JsonResponse(
        {"status": "success", "warehouse_id": warehouse_id}, status=201
    )


@login_required
@require_POST
def update_warehouse(request, warehouse_id):
    if not _available(request):
        return _error("Quantity warehouse API is unavailable.", 404)
    if not _can(request, "auth.update_warehouse"):
        return _error("You do not have permission to update warehouses.", 403)
    try:
        payload = _payload(request)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_update_warehouse(%s, %s::jsonb)",
                [warehouse_id, json.dumps(payload)],
            )
    except ValueError as exc:
        return _error(str(exc))
    except (DatabaseError, TypeError):
        return _error("Warehouse update is invalid.")
    return JsonResponse({"status": "success", "warehouse_id": warehouse_id})


@login_required
@require_http_methods(["DELETE"])
def delete_warehouse(request, warehouse_id):
    if not _available(request):
        return _error("Quantity warehouse API is unavailable.", 404)
    if not _can(request, "auth.delete_warehouse"):
        return _error("You do not have permission to delete warehouses.", 403)
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_delete_warehouse(%s)",
                [warehouse_id],
            )
    except DatabaseError:
        return _error("Referenced or unknown warehouses cannot be deleted.")
    return JsonResponse({"status": "success", "warehouse_id": warehouse_id})
