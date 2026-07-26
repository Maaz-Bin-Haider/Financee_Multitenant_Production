"""Guarded HTTP adapter for Phase 13 quantity sale returns."""

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


def _payload(request):
    try:
        data = parse_json_or_multipart_payload(request)
    except (TypeError, ValueError):
        raise ValueError("A valid JSON object is required.")
    if not isinstance(data, dict):
        raise ValueError("A valid JSON object is required.")
    data["created_by_id"] = request.user.pk
    return data


def _can(request, permission):
    return (
        request.user.is_superuser
        or (
            not request.user.groups.filter(name="view_only_users").exists()
            and request.user.has_perm(permission)
        )
    )


def _error(message, status=400):
    return JsonResponse({"success": False, "status": "error", "message": message},
                        status=status)


def sale_returns(request):
    if request.method == "GET":
        return render(
            request,
            "sale_return_templates/quantity_sale_return_template.html",
            {
                "can_create": _can(request, "auth.create_sale_return"),
                "can_update": _can(request, "auth.update_sale_return"),
                "can_delete": _can(request, "auth.delete_sale_return"),
                "base_currency": getattr(
                    getattr(request, "tenant_company", None),
                    "base_currency", None,
                ),
                "can_manage_attachments": (
                    request.user.is_superuser
                    or request.user.has_perm("auth.manage_quantity_attachments")
                ),
            },
        )
    try:
        validate_request_attachments(request)
        data = _payload(request)
        action = (data.get("action") or "submit").lower()
        sale_return_id = data.get("sale_return_id")
        if action == "submit" and sale_return_id:
            if not _can(request, "auth.update_sale_return"):
                return _error("You do not have permission to update sale returns.",
                              403)
            with transaction.atomic():
                prepare_return_revision(
                    "sale_return", int(sale_return_id),
                    data.get("return_date"), request.user.pk,
                )
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT quantity_update_sale_return(%s,%s::jsonb)",
                        [int(sale_return_id), json.dumps(data)],
                    )
                    result = _json(cur.fetchone()[0])
                result.update(finalize_return(
                    "sale_return", int(sale_return_id), request.user.pk
                ))
            save_document_attachments(
                request, "sale_return", int(sale_return_id)
            )
            return JsonResponse({"success": True, **result})
        if action == "submit":
            if not _can(request, "auth.create_sale_return"):
                return _error("You do not have permission to create sale returns.",
                              403)
            data.setdefault("idempotency_key", str(uuid.uuid4()))
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT quantity_create_sale_return(%s::jsonb)",
                        [json.dumps(data)],
                    )
                    result = _json(cur.fetchone()[0])
                if not result.get("idempotent"):
                    result.update(finalize_return(
                        "sale_return", result["sale_return_id"],
                        request.user.pk,
                    ))
            save_document_attachments(
                request, "sale_return", result["sale_return_id"]
            )
            return JsonResponse({"success": True, **result})
        if action in ("delete", "reverse"):
            if not _can(request, "auth.delete_sale_return"):
                return _error("You do not have permission to reverse sale returns.",
                              403)
            if not sale_return_id:
                return _error("Select a sale return first.")
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT quantity_reverse_sale_return(%s,CURRENT_DATE,%s)",
                        [int(sale_return_id), request.user.pk],
                    )
                    result = _json(cur.fetchone()[0])
                result["reversal_tax_journal_id"] = reverse_return(
                    "sale_return", int(sale_return_id), None, request.user.pk
                )
            delete_document_attachments("sale_return", int(sale_return_id))
            return JsonResponse({"success": True, **result})
        return _error("Unknown sale-return action.")
    except (ValueError, TypeError, ValidationError) as exc:
        return _error(str(exc) if isinstance(exc, ValidationError)
                      else "Sale return request is invalid.")
    except DatabaseError:
        return _error(
            "Sale return data is invalid or its stock dependencies prevent this "
            "change."
        )


def get_sale_return(request):
    action = (request.GET.get("action") or "last").lower()
    current_id = request.GET.get("current_id")
    try:
        current_id = int(current_id) if current_id else None
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_sale_return_navigate(%s,%s)",
                [action, current_id],
            )
            result = _json(cur.fetchone()[0])
    except (DatabaseError, TypeError, ValueError):
        return _error("Unable to navigate sale returns.")
    if not result:
        return _error("No sale return found.", 404)
    return JsonResponse(result)


def get_sale_return_summary(request):
    from_date = request.GET.get("from") or None
    to_date = request.GET.get("to") or None
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_sale_return_summary(%s::date,%s::date)",
                [from_date, to_date],
            )
            result = _json(cur.fetchone()[0])
    except DatabaseError:
        return _error("Sale return date range is invalid.")
    return JsonResponse(result)

def sources(request):
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_sale_return_sources(%s)",
                [request.GET.get("customer") or None],
            )
            result = _json(cur.fetchone()[0])
    except DatabaseError:
        return _error("Unable to load returnable sale lines.")
    return JsonResponse({"sources": result})


def serial_check(_request):
    return _error("Serial validation is unavailable for quantity sale returns.",
                  404)
