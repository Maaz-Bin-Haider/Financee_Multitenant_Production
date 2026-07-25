import json

from django.shortcuts import render, redirect
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from tenancy.models import INVENTORY_MODE_QUANTITY

VIEW_PERM      = "auth.view_opening_stock"
CREATE_PERM    = "auth.create_opening_stock"
DELETE_PERM    = "auth.delete_opening_stock"
RECLASS_PERM   = "auth.reclassify_opening_balance"


def _as_dict(row):
    data = row[0] if row and row[0] is not None else {}
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _is_quantity(request):
    company = getattr(request, "tenant_company", None)
    return bool(company and company.inventory_mode == INVENTORY_MODE_QUANTITY)


@login_required
def opening_stock_page(request):
    """Render the Opening Stock onboarding section."""
    if not request.user.has_perm(VIEW_PERM):
        messages.error(request, "Access Denied!")
        return redirect("home:home")
    quantity_mode = _is_quantity(request)
    return render(
        request,
        (
            "opening_stock_templates/quantity_opening_stock_template.html"
            if quantity_mode
            else "opening_stock_templates/opening_stock_template.html"
        ),
        {
            "can_create":  request.user.has_perm(CREATE_PERM),
            "can_delete":  request.user.has_perm(DELETE_PERM),
            "can_reclass": request.user.has_perm(RECLASS_PERM),
            "quantity_mode": quantity_mode,
            "base_currency": getattr(
                getattr(request, "tenant_company", None), "base_currency", None
            ),
        },
    )


@login_required
def create_opening_stock(request):
    """Create one opening-stock load (Debit Inventory / Credit Opening Balance)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    if not request.user.has_perm(CREATE_PERM):
        return JsonResponse({"status": "error", "message": "You do not have permission to add opening stock."}, status=403)

    try:
        body = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        return JsonResponse({"status": "error", "message": "Invalid request data."}, status=400)

    items = body.get("items") or []
    if not items:
        message = (
            "Add at least one SKU and warehouse quantity."
            if _is_quantity(request)
            else "Add at least one item with serials."
        )
        return JsonResponse({"status": "error", "message": message}, status=400)

    payload_data = {
        "as_of_date":    body.get("as_of_date") or None,
        "vendor_name":   body.get("vendor_name") or None,
        "notes":         body.get("notes") or None,
        "created_by_id": request.user.id,
        "items":         items,
    }
    if _is_quantity(request):
        payload_data["description"] = body.get("description") or body.get("notes")
    payload = json.dumps(payload_data)
    try:
        with connection.cursor() as cursor:
            function = (
                "quantity_create_opening_stock"
                if _is_quantity(request)
                else "create_opening_stock"
            )
            cursor.execute(f"SELECT {function}(%s::jsonb);", [payload])
            data = _as_dict(cursor.fetchone())
    except (DatabaseError, TypeError, ValueError):
        return JsonResponse(
            {"status": "error", "message": "Opening-stock data is invalid."},
            status=400,
        )

    status = 200 if data.get("status") == "success" else 400
    return JsonResponse(data, status=status)


@login_required
def list_opening_stock(request):
    """Return all opening-stock loads."""
    if not request.user.has_perm(VIEW_PERM):
        return JsonResponse([], safe=False, status=403)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT quantity_opening_stock_list();"
                if _is_quantity(request)
                else "SELECT get_opening_stock_loads_json();"
            )
            row = cursor.fetchone()
        data = row[0] if row and row[0] is not None else []
        if isinstance(data, str):
            data = json.loads(data)
    except Exception as exc:  # pragma: no cover
        return JsonResponse({"error": str(exc)}, status=500)
    return JsonResponse(data, safe=False)


@login_required
def opening_stock_details(request):
    """Return one opening-stock load with its items + serials."""
    if not request.user.has_perm(VIEW_PERM):
        return JsonResponse({"error": "Access denied."}, status=403)
    try:
        load_id = int(request.GET.get("id"))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid id."}, status=400)
    with connection.cursor() as cursor:
        cursor.execute(
            (
                "SELECT quantity_opening_stock_details(%s);"
                if _is_quantity(request)
                else "SELECT get_opening_stock_load_details(%s);"
            ),
            [load_id],
        )
        data = _as_dict(cursor.fetchone())
    if not data:
        return JsonResponse({"error": "Opening stock entry not found."}, status=404)
    return JsonResponse(data, safe=False)


@login_required
def delete_opening_stock(request):
    """Delete an opening-stock load (blocked if any unit was already sold)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    if not request.user.has_perm(DELETE_PERM):
        return JsonResponse({"status": "error", "message": "You do not have permission to delete opening stock."}, status=403)
    try:
        load_id = int(json.loads(request.body or "{}").get("id"))
    except (TypeError, ValueError):
        return JsonResponse({"status": "error", "message": "Invalid id."}, status=400)
    try:
        with connection.cursor() as cursor:
            if _is_quantity(request):
                cursor.execute(
                    "SELECT quantity_reverse_opening_stock(%s,CURRENT_DATE,%s);",
                    [load_id, request.user.id],
                )
            else:
                cursor.execute("SELECT delete_opening_stock(%s);", [load_id])
            data = _as_dict(cursor.fetchone())
    except DatabaseError:
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Opening stock cannot be reversed after its quantity "
                    "has been consumed."
                ),
            },
            status=400,
        )
    status = 200 if data.get("status") == "success" else 400
    return JsonResponse(data, status=status)


@login_required
def check_serials(request):
    """Live serial validation for the entry form (mirrors purchase check).

    Returns {success, results:{serial:{status:'ok'|'in_stock'|'ever_existed'}}}.
    """
    if _is_quantity(request):
        return JsonResponse(
            {"success": False, "message": "Serial validation is unavailable."},
            status=404,
        )
    if not request.user.has_perm(VIEW_PERM):
        return JsonResponse({"success": False, "message": "Permission denied."})
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "POST required."})
    try:
        payload = json.loads(request.body or "{}")
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "message": "Invalid JSON."})
    serials = payload.get("serials", [])
    if not isinstance(serials, list):
        return JsonResponse({"success": False, "message": "'serials' must be a list."})
    cleaned = [str(s).strip() for s in serials if str(s).strip()]
    results = {}
    if cleaned:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT serial_number, in_stock FROM purchaseunits WHERE serial_number = ANY(%s)",
                [cleaned],
            )
            found = {r[0]: r[1] for r in cursor.fetchall()}
        for s in cleaned:
            if s in found:
                results[s] = {"status": "in_stock" if found[s] else "ever_existed", "label": ""}
            else:
                results[s] = {"status": "ok", "label": ""}
    return JsonResponse({"success": True, "results": results})


@login_required
def opening_balance_status(request):
    """Return the Opening Balance Equity status (balance + needs_reclass)."""
    if not request.user.has_perm(VIEW_PERM):
        return JsonResponse({"error": "Access denied."}, status=403)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_opening_balance_status();"
            if _is_quantity(request)
            else "SELECT get_opening_balance_status_json();"
        )
        data = _as_dict(cursor.fetchone())
    return JsonResponse(data, safe=False)


@login_required
def reclassify_opening_balance(request):
    """Sweep the Opening Balance Equity into Owner's Capital (one journal entry)."""
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "POST required"}, status=405)
    if not request.user.has_perm(RECLASS_PERM):
        return JsonResponse({"status": "error", "message": "You do not have permission to reclassify."}, status=403)
    payload = json.dumps({"created_by_id": request.user.id})
    with connection.cursor() as cursor:
        cursor.execute(
            (
                "SELECT quantity_reclassify_opening_balance(%s::jsonb);"
                if _is_quantity(request)
                else "SELECT reclassify_opening_balance_to_capital(%s::jsonb);"
            ),
            [payload],
        )
        data = _as_dict(cursor.fetchone())
    status = 200 if data.get("status") in ("success", "noop") else 400
    return JsonResponse(data, status=status)
