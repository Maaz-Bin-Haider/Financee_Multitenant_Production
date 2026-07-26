"""Phase 15 quantity warehouse-transfer HTTP adapter."""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render

from .models import INVENTORY_MODE_QUANTITY
from .capabilities import reject_serial_payload


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
def transfers(request):
    if not _available(request):
        return _error("Quantity transfers are unavailable.", 404)
    if request.method == "GET":
        return render(request, "tenancy_templates/quantity_transfers.html", {
            "can_create": _can(request, "auth.create_warehouse_transfer"),
            "can_update": _can(request, "auth.update_warehouse_transfer"),
            "can_delete": _can(request, "auth.delete_warehouse_transfer"),
        })
    try:
        data = json.loads(request.body or "{}")
        if not isinstance(data, dict):
            raise ValueError
        reject_serial_payload(data)
        data["created_by_id"] = request.user.pk
        action = (data.get("action") or "submit").lower()
        transfer_id = data.get("transfer_id")
        if action == "submit":
            permission = ("auth.update_warehouse_transfer" if transfer_id
                          else "auth.create_warehouse_transfer")
            if not _can(request, permission):
                return _error("You do not have permission for this transfer.", 403)
            data.setdefault("idempotency_key", str(uuid.uuid4()))
            with connection.cursor() as cur:
                if transfer_id:
                    cur.execute("SELECT quantity_update_transfer(%s,%s::jsonb)",
                                [int(transfer_id), json.dumps(data)])
                else:
                    cur.execute("SELECT quantity_create_transfer(%s::jsonb)",
                                [json.dumps(data)])
                result = _json(cur.fetchone()[0])
            return JsonResponse({"success": True, **result})
        if action in ("delete", "reverse"):
            if not _can(request, "auth.delete_warehouse_transfer"):
                return _error("You do not have permission to reverse transfers.", 403)
            with connection.cursor() as cur:
                cur.execute("SELECT quantity_reverse_transfer(%s,CURRENT_DATE,%s)",
                            [int(transfer_id), request.user.pk])
                result = _json(cur.fetchone()[0])
            return JsonResponse({"success": True, **result})
        return _error("Unknown transfer action.")
    except (TypeError, ValueError):
        return _error("Transfer request is invalid.")
    except DatabaseError:
        return _error("Transfer is invalid or its stock dependencies prevent it.")


@login_required
def navigate(request):
    try:
        current = request.GET.get("current_id")
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_transfer_navigate(%s,%s)", [
                request.GET.get("action") or "last",
                int(current) if current else None,
            ])
            result = _json(cur.fetchone()[0])
        return JsonResponse(result) if result else _error("No transfer found.", 404)
    except (DatabaseError, TypeError, ValueError):
        return _error("Unable to navigate transfers.")


@login_required
def summary(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_transfer_summary(%s::date,%s::date)", [
                request.GET.get("from") or None, request.GET.get("to") or None,
            ])
            return JsonResponse(_json(cur.fetchone()[0]))
    except DatabaseError:
        return _error("Transfer date range is invalid.")
