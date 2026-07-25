"""Quantity-family product, variant, SKU, and unit JSON endpoints."""

import json

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from tenancy.models import INVENTORY_MODE_QUANTITY


def _error(message, status=400):
    return JsonResponse({"status": "error", "message": message}, status=status)


def _quantity_company(request):
    company = getattr(request, "tenant_company", None)
    return company if company and company.inventory_mode == INVENTORY_MODE_QUANTITY else None


def _payload(request):
    try:
        value = json.loads(request.body or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("A valid JSON object is required.")
    if not isinstance(value, dict):
        raise ValueError("A valid JSON object is required.")
    value["user_id"] = request.user.pk
    return value


def _can_change(request, permission):
    return (
        request.user.is_superuser
        or (
            not request.user.groups.filter(name="view_only_users").exists()
            and request.user.has_perm(permission)
        )
    )


@login_required
@require_GET
def units(request):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    with connection.cursor() as cur:
        cur.execute("""
            SELECT unit_id, code, unit_name, quantity_scale
              FROM units_of_measure WHERE is_active ORDER BY unit_id
        """)
        rows = cur.fetchall()
    return JsonResponse({
        "status": "success",
        "units": [
            {"unit_id": row[0], "code": row[1], "name": row[2],
             "quantity_scale": row[3]}
            for row in rows
        ],
    })


@login_required
@require_POST
def create_product(request):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    if not _can_change(request, "auth.create_item"):
        return _error("You do not have permission to create items.", 403)
    try:
        payload = _payload(request)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_create_product(%s::jsonb)",
                [json.dumps(payload)],
            )
            product_id = cur.fetchone()[0]
    except ValueError as exc:
        return _error(str(exc))
    except (DatabaseError, TypeError):
        return _error("Product data is invalid or already exists.")
    return JsonResponse({"status": "success", "product_id": product_id}, status=201)


@login_required
@require_POST
def update_product(request, product_id):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    if not _can_change(request, "auth.update_item"):
        return _error("You do not have permission to update items.", 403)
    try:
        payload = _payload(request)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_update_product(%s, %s::jsonb)",
                [product_id, json.dumps(payload)],
            )
    except ValueError as exc:
        return _error(str(exc))
    except (DatabaseError, TypeError):
        return _error("Product update is invalid.")
    return JsonResponse({"status": "success", "product_id": product_id})


@login_required
@require_POST
def create_variant(request):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    if not _can_change(request, "auth.create_item"):
        return _error("You do not have permission to create items.", 403)
    try:
        payload = _payload(request)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_create_variant(%s::jsonb)",
                [json.dumps(payload)],
            )
            variant_id = cur.fetchone()[0]
            cur.execute(
                "SELECT sku FROM product_variants WHERE variant_id = %s",
                [variant_id],
            )
            sku = cur.fetchone()[0]
    except ValueError as exc:
        return _error(str(exc))
    except (DatabaseError, TypeError, ValueError):
        return _error("Variant data, SKU, combination, or unit is invalid.")
    return JsonResponse(
        {"status": "success", "variant_id": variant_id, "sku": sku},
        status=201,
    )


@login_required
@require_POST
def update_variant(request, variant_id):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    if not _can_change(request, "auth.update_item"):
        return _error("You do not have permission to update items.", 403)
    try:
        payload = _payload(request)
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_update_variant(%s, %s::jsonb)",
                [variant_id, json.dumps(payload)],
            )
    except ValueError as exc:
        return _error(str(exc))
    except (DatabaseError, TypeError):
        return _error("Variant update is invalid or locked.")
    return JsonResponse({"status": "success", "variant_id": variant_id})


@login_required
@require_GET
def catalog(request):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    search = (request.GET.get("term") or "").strip()
    active_only = request.GET.get("active", "true").lower() != "false"
    with connection.cursor() as cur:
        cur.execute(
            "SELECT * FROM quantity_item_catalog(%s, %s)",
            [search, active_only],
        )
        columns = [column[0] for column in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    for row in rows:
        row["reorder_level"] = str(row["reorder_level"])
    return JsonResponse({"status": "success", "count": len(rows), "items": rows})


@login_required
@require_GET
def suggest_sku(request):
    if not _quantity_company(request):
        return _error("Quantity item API is unavailable.", 404)
    values = [
        request.GET.get(name)
        for name in (
            "product_name", "brand", "model", "color", "storage", "ram",
            "region", "condition",
        )
    ]
    if any(not value or not value.strip() for value in values):
        return _error("Product name and all seven variant dimensions are required.")
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT quantity_suggest_sku(%s,%s,%s,%s,%s,%s,%s,%s)",
                values,
            )
            sku = cur.fetchone()[0]
    except DatabaseError:
        return _error("SKU suggestion could not be generated.")
    return JsonResponse({"status": "success", "sku": sku})
