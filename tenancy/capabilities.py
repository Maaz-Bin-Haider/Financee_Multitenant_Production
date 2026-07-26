"""Trusted inventory-mode capability and request dispatch helpers."""

from __future__ import annotations

import json
from functools import wraps

from django.http import JsonResponse

from .models import INVENTORY_MODE_QUANTITY, INVENTORY_MODE_SERIAL

CAPABILITY_CATALOG = {
    INVENTORY_MODE_SERIAL: frozenset({
        "serial_inventory", "serial_lookup", "serial_documents",
        "shared_financials", "attachments", "subscriptions",
    }),
    INVENTORY_MODE_QUANTITY: frozenset({
        "quantity_inventory", "quantity_documents", "warehouses", "fifo",
        "transfers", "physical_counts", "adjustments", "tax", "currency",
        "quantity_reports", "quantity_dashboards", "shared_financials",
        "attachments", "audit", "subscriptions",
    }),
}

SERIAL_PAYLOAD_KEYS = frozenset({
    "serial", "serials", "serial_number", "serial_numbers", "imei", "imeis",
})
QUANTITY_ONLY_PAYLOAD_KEYS = frozenset({
    "variant_id", "warehouse_id", "source_warehouse_id",
    "destination_warehouse_id", "source_sale_line_id",
    "source_purchase_line_id", "counted_quantity",
})


def inventory_mode(request):
    company = getattr(request, "tenant_company", None)
    return getattr(company, "inventory_mode", None)


def supports(request, capability):
    return capability in CAPABILITY_CATALOG.get(inventory_mode(request), ())


def dispatch_inventory_view(request, serial_view, quantity_view, *args, **kwargs):
    """Select a view only from the trusted public Company inventory mode."""
    mode = inventory_mode(request)
    if mode == INVENTORY_MODE_QUANTITY:
        return quantity_view(request, *args, **kwargs)
    if mode == INVENTORY_MODE_SERIAL:
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                payload = _request_payload(request)
                reject_quantity_payload(payload)
            except ValueError as exc:
                return JsonResponse(
                    {"status": "error", "message": str(exc)}, status=400
                )
        return serial_view(request, *args, **kwargs)
    return JsonResponse(
        {"status": "denied", "message": "No supported company type is active."},
        status=403,
    )


def require_capability(capability):
    """Backend guard for routes that exist for only one schema family."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not supports(request, capability):
                return JsonResponse(
                    {"status": "error", "message": "This operation is unavailable "
                     "for your company type."},
                    status=404,
                )
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def reject_serial_payload(payload):
    """Reject serial-shaped data recursively before quantity SQL is called."""
    if not isinstance(payload, dict):
        raise ValueError("A valid JSON object is required.")

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in SERIAL_PAYLOAD_KEYS:
                    raise ValueError(
                        "Serial-number fields are unavailable for quantity companies."
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return payload


def reject_quantity_payload(payload):
    """Reject quantity-schema identifiers on serial document routes."""
    if not isinstance(payload, dict):
        raise ValueError("A valid JSON object is required.")

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in QUANTITY_ONLY_PAYLOAD_KEYS:
                    raise ValueError(
                        "Quantity-inventory fields are unavailable for serial companies."
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return payload


def _request_payload(request):
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        raw = request.POST.get("payload") or "{}"
    else:
        raw = request.body or b"{}"
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("A valid JSON object is required.") from exc
    return value


def parse_quantity_payload(request, *, actor_key="created_by_id"):
    """Parse JSON or attachment multipart and stamp the trusted actor."""
    payload = _request_payload(request)
    reject_serial_payload(payload)
    payload[actor_key] = request.user.pk
    return payload
