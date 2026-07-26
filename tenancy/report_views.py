"""Quantity report page, JSON endpoint, and spreadsheet-compatible CSV export."""

from __future__ import annotations

import csv
import json
from xml.etree import ElementTree

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .capabilities import require_capability
from .report_catalog import QUANTITY_REPORT_MAP, available_reports

FILTER_KEYS = (
    "from", "to", "warehouse_id", "sku", "variant_id", "customer", "vendor",
    "tax_code", "currency", "threshold", "days", "limit",
)


def _filters(request):
    return {
        key: request.GET[key].strip()
        for key in FILTER_KEYS if request.GET.get(key, "").strip()
    }


def _report(request, key):
    definition = QUANTITY_REPORT_MAP.get(key)
    company = getattr(request, "tenant_company", None)
    if (
        not definition or not company
        or not company.feature_enabled(definition.feature)
        or not request.user.has_perm(definition.permission)
    ):
        raise Http404("Report is unavailable.")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT quantity_run_report(%s, %s::jsonb)",
            [key, json.dumps(_filters(request))],
        )
        row = cursor.fetchone()
    result = row[0] if row and row[0] else {"columns": [], "rows": [], "totals": {}}
    result["key"] = key
    result["label"] = definition.label
    return result


@login_required
@require_capability("quantity_reports")
@require_GET
def reports_page(request):
    grouped = {}
    for report in available_reports(request.tenant_company):
        if not request.user.has_perm(report.permission):
            continue
        grouped.setdefault(report.group, []).append(report)
    return render(request, "reports/quantity_reports.html", {"report_groups": grouped})


@login_required
@require_capability("quantity_reports")
@require_GET
def report_api(request, key):
    return JsonResponse({"status": "ok", "data": _report(request, key)})


@login_required
@require_capability("quantity_reports")
@require_GET
def report_csv(request, key):
    company = request.tenant_company
    if not company.feature_enabled("excel_export"):
        return JsonResponse(
            {"status": "denied", "message": "Export is not enabled."}, status=403
        )
    report = _report(request, key)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{key}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    columns = report.get("columns", [])
    writer.writerow([column.get("label", column["key"]) for column in columns])
    for row in report.get("rows", []):
        writer.writerow([row.get(column["key"], "") for column in columns])
    return response


@login_required
@require_capability("quantity_reports")
@require_GET
def report_excel(request, key):
    """Dependency-free SpreadsheetML export understood natively by Excel."""
    if not request.tenant_company.feature_enabled("excel_export"):
        return JsonResponse(
            {"status": "denied", "message": "Export is not enabled."}, status=403
        )
    report = _report(request, key)
    ns = "urn:schemas-microsoft-com:office:spreadsheet"
    ElementTree.register_namespace("", ns)
    workbook = ElementTree.Element(f"{{{ns}}}Workbook")
    worksheet = ElementTree.SubElement(
        workbook, f"{{{ns}}}Worksheet", {f"{{{ns}}}Name": report["label"][:31]}
    )
    table = ElementTree.SubElement(worksheet, f"{{{ns}}}Table")
    columns = report.get("columns", [])
    values = [[column.get("label", column["key"]) for column in columns]]
    values.extend(
        [row.get(column["key"], "") for column in columns]
        for row in report.get("rows", [])
    )
    for values_row in values:
        xml_row = ElementTree.SubElement(table, f"{{{ns}}}Row")
        for value in values_row:
            cell = ElementTree.SubElement(xml_row, f"{{{ns}}}Cell")
            data = ElementTree.SubElement(
                cell, f"{{{ns}}}Data", {f"{{{ns}}}Type": "String"}
            )
            data.text = "" if value is None else str(value)
    response = HttpResponse(
        ElementTree.tostring(workbook, encoding="utf-8", xml_declaration=True),
        content_type="application/vnd.ms-excel",
    )
    response["Content-Disposition"] = f'attachment; filename="{key}.xls"'
    return response
