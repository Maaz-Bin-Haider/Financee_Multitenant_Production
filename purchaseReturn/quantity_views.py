"""Guarded HTTP adapter for Phase 14 quantity purchase returns."""
import json
import uuid

from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.core.exceptions import ValidationError
from attachments.utils import (
    delete_document_attachments, parse_json_or_multipart_payload,
    save_document_attachments, validate_request_attachments,
)

from tenancy.models import INVENTORY_MODE_QUANTITY
from tenancy.quantity_tax import (
    finalize_return, prepare_return_revision, reverse_return,
)


def is_quantity(request):
    company = getattr(request, "tenant_company", None)
    return bool(company and company.inventory_mode == INVENTORY_MODE_QUANTITY)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _error(message, status=400):
    return JsonResponse({"success": False, "status": "error", "message": message},
                        status=status)


def _can(request, permission):
    return request.user.is_superuser or (
        not request.user.groups.filter(name="view_only_users").exists()
        and request.user.has_perm(permission)
    )


def purchase_returns(request):
    if request.method == "GET":
        return render(request,
            "purchase_return_templates/quantity_purchase_return_template.html",
            {"can_create": _can(request, "auth.create_purchase_return"),
             "can_update": _can(request, "auth.update_purchase_return"),
             "can_delete": _can(request, "auth.delete_purchase_return"),
             "can_manage_attachments": (
                 request.user.is_superuser
                 or request.user.has_perm("auth.manage_quantity_attachments")
             ),
             "base_currency": getattr(request.tenant_company, "base_currency", None)})
    try:
        validate_request_attachments(request)
        data = parse_json_or_multipart_payload(request)
        if not isinstance(data, dict):
            raise ValueError
        data["created_by_id"] = request.user.pk
        action = (data.get("action") or "submit").lower()
        return_id = data.get("purchase_return_id") or data.get("return_id")
        if action == "submit":
            permission = ("auth.update_purchase_return" if return_id
                          else "auth.create_purchase_return")
            if not _can(request, permission):
                return _error("You do not have permission for this purchase return.", 403)
            data.setdefault("idempotency_key", str(uuid.uuid4()))
            function = ("quantity_update_purchase_return" if return_id
                        else "quantity_create_purchase_return")
            args = [int(return_id), json.dumps(data)] if return_id else [json.dumps(data)]
            placeholders = "%s,%s::jsonb" if return_id else "%s::jsonb"
            with transaction.atomic():
                if return_id:
                    prepare_return_revision(
                        "purchase_return", int(return_id),
                        data.get("return_date"), request.user.pk,
                    )
                with connection.cursor() as cur:
                    cur.execute(f"SELECT {function}({placeholders})", args)
                    result = _json(cur.fetchone()[0])
                if not result.get("idempotent"):
                    result.update(finalize_return(
                        "purchase_return",
                        int(return_id) if return_id
                        else result["purchase_return_id"],
                        request.user.pk,
                    ))
            attachment_id = int(return_id) if return_id else result["purchase_return_id"]
            save_document_attachments(request, "purchase_return", attachment_id)
            return JsonResponse({"success": True, **result})
        if action in ("delete", "reverse"):
            if not _can(request, "auth.delete_purchase_return"):
                return _error("You do not have permission to reverse purchase returns.", 403)
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute("SELECT quantity_reverse_purchase_return(%s,CURRENT_DATE,%s)",
                                [int(return_id), request.user.pk])
                    result = _json(cur.fetchone()[0])
                result["reversal_tax_journal_id"] = reverse_return(
                    "purchase_return", int(return_id), None, request.user.pk
                )
            delete_document_attachments("purchase_return", int(return_id))
            return JsonResponse({"success": True, **result})
        return _error("Unknown purchase-return action.")
    except (ValueError, TypeError, ValidationError) as exc:
        return _error(str(exc) if isinstance(exc, ValidationError)
                      else "Purchase return request is invalid.")
    except DatabaseError:
        return _error("Purchase return is invalid or its source stock is unavailable.")


def navigate(request):
    try:
        current = request.GET.get("current_id")
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_purchase_return_navigate(%s,%s)",
                        [request.GET.get("action") or "last",
                         int(current) if current else None])
            result = _json(cur.fetchone()[0])
        return JsonResponse(result) if result else _error("No purchase return found.", 404)
    except (DatabaseError, TypeError, ValueError):
        return _error("Unable to navigate purchase returns.")


def summary(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_purchase_return_summary(%s::date,%s::date)",
                        [request.GET.get("from") or None,
                         request.GET.get("to") or None])
            return JsonResponse(_json(cur.fetchone()[0]))
    except DatabaseError:
        return _error("Purchase-return date range is invalid.")


def sources(request):
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT quantity_purchase_return_sources(%s)",
                        [request.GET.get("vendor") or None])
            result = _json(cur.fetchone()[0])
        return JsonResponse({"sources": result})
    except DatabaseError:
        return _error("Unable to load returnable purchase lines.")


def serial_check(_request, _serial=None):
    return _error("Serial validation is unavailable for quantity purchase returns.", 404)
