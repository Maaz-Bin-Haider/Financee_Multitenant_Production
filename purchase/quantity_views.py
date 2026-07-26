"""Guarded HTTP adapter for Phase 11 quantity purchases."""

import json
import logging
import uuid

from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from tenancy.models import INVENTORY_MODE_QUANTITY
from tenancy.models import Currency
from tenancy.quantity_tax import (
    calculate_and_transform, catalog, finalize, finalize_currency,
    prepare_revision, reverse,
)

logger = logging.getLogger(__name__)


def is_quantity(request):
    company = getattr(request, "tenant_company", None)
    return bool(company and company.inventory_mode == INVENTORY_MODE_QUANTITY)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _payload(request):
    try:
        data = json.loads(request.body or "{}")
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


def purchasing(request):
    if request.method == "GET":
        return render(
            request,
            "purchase_templates/quantity_purchasing_template.html",
            {
                "can_create": _can(request, "auth.create_purchase"),
                "can_update": _can(request, "auth.update_purchase"),
                "can_delete": _can(request, "auth.delete_purchase"),
                "base_currency": getattr(
                    getattr(request, "tenant_company", None),
                    "base_currency", None,
                ),
                "tax_environment": request.tenant_company.tax_environment,
                "tax_codes": catalog(),
                "can_manage_tax": request.user.is_superuser,
                "currencies": list(Currency.objects.filter(is_active=True)
                                   .values("code", "name", "minor_units")),
            },
        )
    try:
        data = _payload(request)
        action = (data.get("action") or "submit").lower()
        purchase_id = data.get("purchase_id")
        if action == "settle":
            if not _can(request, "auth.update_purchase"):
                return _error("You do not have permission to settle purchases.", 403)
            data.setdefault("idempotency_key", str(uuid.uuid4()))
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute("SELECT quantity_settle_foreign_purchase(%s::jsonb)",
                            [json.dumps(data)])
                result = _json(cur.fetchone()[0])
            return JsonResponse({"success": True, **result})
        if action == "submit" and purchase_id:
            if not _can(request, "auth.update_purchase"):
                return _error("You do not have permission to update purchases.",
                              403)
            with transaction.atomic():
                calculation, transformed, foreign, currency, rate = (
                    calculate_and_transform(
                    data, price_key="unit_cost_base",
                    company=request.tenant_company,
                )
                )
                prepare_revision(
                    "purchase", int(purchase_id), data.get("invoice_date"),
                    request.user.pk,
                )
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT quantity_update_purchase(%s,%s::jsonb)",
                        [int(purchase_id), json.dumps(transformed)],
                    )
                    result = _json(cur.fetchone()[0])
                result.update(finalize(
                    "purchase", int(purchase_id), data, calculation,
                    request.user.pk,
                ))
                result.update(finalize_currency(
                    "purchase", int(purchase_id), foreign, currency, rate,
                    request.user.pk,
                ))
            return JsonResponse({"success": True, **result})
        if action == "submit":
            if not _can(request, "auth.create_purchase"):
                return _error("You do not have permission to create purchases.",
                              403)
            data.setdefault("idempotency_key", str(uuid.uuid4()))
            with transaction.atomic():
                calculation, transformed, foreign, currency, rate = (
                    calculate_and_transform(
                    data, price_key="unit_cost_base",
                    company=request.tenant_company,
                )
                )
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT quantity_create_purchase(%s::jsonb)",
                        [json.dumps(transformed)],
                    )
                    result = _json(cur.fetchone()[0])
                if not result.get("idempotent"):
                    result.update(finalize(
                        "purchase", result["purchase_invoice_id"], data,
                        calculation, request.user.pk,
                    ))
                    result.update(finalize_currency(
                        "purchase", result["purchase_invoice_id"], foreign,
                        currency, rate, request.user.pk,
                    ))
            return JsonResponse({"success": True, **result})
        if action in ("delete", "reverse"):
            if not _can(request, "auth.delete_purchase"):
                return _error("You do not have permission to reverse purchases.",
                              403)
            if not purchase_id:
                return _error("Select a purchase first.")
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        "SELECT quantity_reverse_purchase(%s,CURRENT_DATE,%s)",
                        [int(purchase_id), request.user.pk],
                    )
                    result = _json(cur.fetchone()[0])
                result["reversal_tax_journal_id"] = reverse(
                    "purchase", int(purchase_id), None, request.user.pk
                )
            return JsonResponse({"success": True, **result})
        return _error("Unknown purchase action.")
    except (ValueError, TypeError):
        return _error("Purchase request is invalid.")
    except DatabaseError:
        logger.exception("Quantity purchase posting failed")
        return _error(
            "Purchase data, tax, or discounts are invalid, or stock "
            "dependencies prevent this change."
        )


def get_purchase(request):
    action = (request.GET.get("action") or "last").lower()
    current_id = request.GET.get("current_id")
    try:
        current_id = int(current_id) if current_id else None
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_purchase_navigate(%s,%s)",
                [action, current_id],
            )
            result = _json(cur.fetchone()[0])
    except (DatabaseError, TypeError, ValueError):
        return _error("Unable to navigate purchases.")
    if not result:
        return _error("No purchase found.", 404)
    return JsonResponse(result)


def get_purchase_summary(request):
    from_date = request.GET.get("from") or None
    to_date = request.GET.get("to") or None
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_purchase_summary(%s::date,%s::date)",
                [from_date, to_date],
            )
            result = _json(cur.fetchone()[0])
    except DatabaseError:
        return _error("Purchase date range is invalid.")
    return JsonResponse(result)


def serial_check(_request):
    return _error("Serial validation is unavailable for quantity purchases.",
                  404)


@login_required
def tax_codes(request):
    if not is_quantity(request):
        return _error("Tax codes are only available to quantity companies.", 404)
    if request.method == "GET":
        return JsonResponse({"tax_codes": catalog()})
    if not request.user.is_superuser:
        return _error("Only tenant administrators may manage tax codes.", 403)
    try:
        data = _payload(request)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT quantity_upsert_tax_code(%s::jsonb)",
                [json.dumps(data)],
            )
            result = _json(cursor.fetchone()[0])
        return JsonResponse({"success": True, **result})
    except (DatabaseError, TypeError, ValueError):
        return _error("Tax code configuration is invalid.")
