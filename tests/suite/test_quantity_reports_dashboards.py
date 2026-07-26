#!/usr/bin/env python3
"""Phase 22 report catalogue, SQL, filters, exports, and dashboard gates."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.db import connection  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.http import Http404  # noqa: E402

from tenancy.models import (  # noqa: E402
    Company, Currency, INVENTORY_MODE_QUANTITY, INVENTORY_MODE_SERIAL,
    PROVISIONING_READY,
)
from tenancy.report_catalog import (  # noqa: E402
    QUANTITY_REPORTS, QUANTITY_REPORT_MAP, SERIAL_ONLY_REPORTS,
    available_reports, report_available,
)
from tenancy.schema_families import schema_family  # noqa: E402
from tenancy import report_views  # noqa: E402

RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def static_checks():
    family = schema_family(INVENTORY_MODE_QUANTITY)
    keys = {report.key for report in QUANTITY_REPORTS}
    chk("Phase 22 schema registered", family.required_version == 22)
    chk("report rollout is final bootstrap",
        family.bootstrap_paths[-1].name == "quantity_reports_dashboards.sql")
    chk("report functions fingerprinted",
        {"quantity_report_filters", "quantity_run_report", "quantity_dashboard"}
        .issubset(family.required_functions))
    chk("all required report families catalogued",
        {report.group for report in QUANTITY_REPORTS}
        == {"Accounts", "Stock", "Sales", "Purchases"})
    chk("complete report catalogue", len(keys) >= 40, len(keys))
    chk("serial reports excluded from quantity catalogue",
        not keys.intersection(SERIAL_ONLY_REPORTS))
    quantity = Company(name="q", inventory_mode=INVENTORY_MODE_QUANTITY)
    quantity.feature_enabled = lambda _key: True
    serial = Company(name="s", inventory_mode=INVENTORY_MODE_SERIAL)
    serial.feature_enabled = lambda _key: True
    chk("quantity catalogue available only in quantity mode",
        len(available_reports(quantity)) == len(keys) and not available_reports(serial))
    chk("serial-only report backend unavailable to quantity mode",
        all(not report_available(quantity, key) for key in SERIAL_ONLY_REPORTS))
    template = (ROOT / "templates/reports/quantity_reports.html").read_text()
    js = (ROOT / "static/js/quantity_reports.js").read_text()
    chk("all SRS filters exposed",
        all(f'name="{key}"' in template for key in (
            "from", "to", "warehouse_id", "sku", "variant_id", "customer",
            "vendor", "tax_code", "currency")))
    chk("accessible asynchronous report status",
        'role="status"' in template and 'aria-live="polite"' in template)
    chk("safe DOM report rendering", "textContent" in js and "item[column.key]" in js)
    chk("CSV export and API routes exist",
        "quantity_reports:csv" in template and "quantity_reports:excel" in template
        and "quantity_reports:api" in template)
    chk("every report has backend permission metadata",
        all(report.permission.startswith("auth.") for report in QUANTITY_REPORTS))
    home = (ROOT / "home/views.py").read_text()
    chk("quantity dashboards dispatch independently",
        home.count("_quantity_dashboard(request") >= 10
        and "fn_dash_sales_today_kpi" in home)

    sample = {
        "label": "Trial Balance",
        "columns": [{"key": "account", "label": "Account"}],
        "rows": [{"account": "Cash"}],
        "totals": {},
    }
    factory = RequestFactory()
    user = SimpleNamespace(
        is_authenticated=True, pk=1, has_perm=lambda _permission: True
    )
    tenant = SimpleNamespace(
        inventory_mode=INVENTORY_MODE_QUANTITY,
        feature_enabled=lambda _feature: True,
    )
    with patch.object(report_views, "_report", return_value=sample):
        csv_request = factory.get("/quantity-reports/export/trial_balance.csv")
        csv_request.user, csv_request.tenant_company = user, tenant
        csv_response = report_views.report_csv(csv_request, "trial_balance")
        excel_request = factory.get("/quantity-reports/export/trial_balance.xls")
        excel_request.user, excel_request.tenant_company = user, tenant
        excel_response = report_views.report_excel(excel_request, "trial_balance")
    chk("CSV endpoint emits spreadsheet rows",
        csv_response.status_code == 200 and b"Cash" in csv_response.content)
    chk("Excel endpoint emits SpreadsheetML",
        excel_response.status_code == 200
        and b"urn:schemas-microsoft-com:office:spreadsheet"
        in excel_response.content)
    denied_request = factory.get("/quantity-reports/api/trial_balance/")
    denied_request.user = SimpleNamespace(has_perm=lambda _permission: False)
    denied_request.tenant_company = tenant
    try:
        report_views._report(denied_request, "trial_balance")
        denied = False
    except Http404:
        denied = True
    chk("per-report permission is backend-enforced", denied)
    serial_request = factory.get("/quantity-reports/")
    serial_request.user = user
    serial_request.tenant_company = SimpleNamespace(
        inventory_mode=INVENTORY_MODE_SERIAL
    )
    chk("quantity report endpoint rejects serial tenant",
        report_views.reports_page(serial_request).status_code == 404)


def database_checks():
    family = schema_family(INVENTORY_MODE_QUANTITY)
    company = Company.objects.create(
        name=f"PHASE22 REPORTS {time.time_ns()}",
        inventory_mode=INVENTORY_MODE_QUANTITY,
        base_currency=Currency.objects.get(pk="PKR"),
        tax_environment="non_tax",
    )
    company.refresh_from_db()
    quoted = connection.ops.quote_name(company.schema_name)
    try:
        chk("temporary quantity tenant provisioned",
            company.provisioning_state == PROVISIONING_READY,
            company.provisioning_error_code)
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {quoted}, public")
            cursor.execute("SELECT version FROM tenant_schema_metadata WHERE id")
            chk("deployed version current", cursor.fetchone()[0] == family.required_version)
            failed = []
            for report in QUANTITY_REPORTS:
                try:
                    cursor.execute(
                        "SELECT quantity_run_report(%s,'{}'::jsonb)", [report.key]
                    )
                    payload = decoded(cursor.fetchone()[0])
                    if not {"columns", "rows", "totals", "filters"}.issubset(payload):
                        failed.append(report.key)
                except Exception as exc:
                    connection.rollback()
                    cursor.execute(f"SET search_path TO {quoted}, public")
                    failed.append(f"{report.key}: {exc}")
            chk("every catalogued report executes", not failed, failed)
            filters = {
                "from": "2026-01-01", "to": "2026-12-31",
                "warehouse_id": "1", "sku": "SKU", "variant_id": "1",
                "customer": "C", "vendor": "V", "tax_code": "GST",
                "currency": "PKR", "limit": "20",
            }
            cursor.execute(
                "SELECT quantity_run_report('sales_summary',%s::jsonb)",
                [json.dumps(filters)],
            )
            chk("complete filter matrix accepted",
                decoded(cursor.fetchone()[0])["filters"]["currency"] == "PKR")
            cursor.execute(
                "SELECT quantity_run_report('inventory_reconciliation','{}')"
            )
            rec = decoded(cursor.fetchone()[0])
            chk("empty source reconciliation is exact",
                rec["totals"]["quantity_variance"] == 0)
            dashboard_keys = (
                "sales_today", "sales_chart", "stock_kpi", "low_stock",
                "fast_moving", "stale_stock", "top_customers", "top_vendors",
                "receivables_aging", "recent_transactions", "expense_kpi",
                "expense_categories", "expense_descriptions", "alerts",
            )
            failed_dash = []
            for key in dashboard_keys:
                try:
                    cursor.execute("SELECT quantity_dashboard(%s,'{}')", [key])
                    cursor.fetchone()
                except Exception as exc:
                    connection.rollback()
                    cursor.execute(f"SET search_path TO {quoted}, public")
                    failed_dash.append(f"{key}: {exc}")
            chk("every quantity dashboard executes", not failed_dash, failed_dash)
            try:
                cursor.execute("SELECT quantity_run_report('serial_ledger','{}')")
                blocked = False
            except Exception:
                connection.rollback()
                cursor.execute(f"SET search_path TO {quoted}, public")
                blocked = True
            chk("serial-only SQL report is backend-blocked", blocked)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
        Company.objects.filter(pk=company.pk).delete()


def main():
    static_checks()
    database_checks()
    failed = [result for result in RESULTS if not result[1]]
    for name, ok, detail in RESULTS:
        print(("PASS" if ok else "FAIL") + ":", name,
              "" if ok or not detail else f"— {detail}")
    print(f"{len(RESULTS)-len(failed)}/{len(RESULTS)} Phase 22 checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
