#!/usr/bin/env python3
"""Phase 12 domestic quantity sales, FIFO COGS, and concurrency."""

import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django  # noqa: E402
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import DatabaseError, close_old_connections, connection, transaction  # noqa: E402
from django.test import Client  # noqa: E402
from tenancy.models import Company, Currency, Membership, INVENTORY_MODE_QUANTITY  # noqa: E402
from tenancy.schema_families import schema_family  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402
from tests.suite.test_quantity_purchases import setup_scope  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))


def q(schema, sql, params=None):
    quoted = connection.ops.quote_name(schema)
    with connection.cursor() as cur:
        cur.execute(f"SET search_path TO {quoted}, public")
        try:
            cur.execute(sql, params or [])
            return cur.fetchall() if cur.description else []
        finally:
            cur.execute("SET search_path TO public")


def as_json(value):
    return json.loads(value) if isinstance(value, str) else value


def rejected(schema, sql, params=None):
    try:
        with transaction.atomic():
            q(schema, sql, params)
        return False
    except DatabaseError:
        return True


def purchase(schema, key, variant, warehouse, quantity, cost, when="2026-07-01"):
    return as_json(q(schema, "SELECT quantity_create_purchase(%s::jsonb)", [
        json.dumps({
            "idempotency_key": key, "invoice_date": when,
            "vendor_name": "Phase 12 Vendor", "purchase_type": "credit",
            "created_by_id": 1, "items": [{
                "variant_id": variant, "warehouse_id": warehouse,
                "quantity": str(quantity), "unit_cost_base": str(cost),
            }],
        })
    ])[0][0])


def payload(key, lines, **overrides):
    data = {
        "idempotency_key": key, "invoice_date": "2026-07-10",
        "customer_name": "Phase 12 Customer", "sale_type": "credit",
        "description": "Domestic quantity sale", "created_by_id": 1,
        "items": lines,
    }
    data.update(overrides)
    return data


def create(schema, data):
    return as_json(q(schema, "SELECT quantity_create_sale(%s::jsonb)",
                     [json.dumps(data)])[0][0])


def account(schema, code):
    return q(schema, """
        SELECT COALESCE(sum(jl.debit-jl.credit),0)
          FROM journal_lines jl JOIN chart_of_accounts c
            ON c.account_id=jl.account_id WHERE c.account_code=%s
    """, [code])[0][0]


def concurrent_attempt(schema, data):
    close_old_connections()
    try:
        return ("ok", create(schema, data))
    except DatabaseError as exc:
        return ("rejected", str(exc))
    finally:
        close_old_connections()


def drop_company(company):
    if not company:
        return
    with connection.cursor() as cur:
        cur.execute(
            f"DROP SCHEMA IF EXISTS "
            f"{connection.ops.quote_name(company.schema_name)} CASCADE"
        )
        cur.execute("SET search_path TO public")
    Company.objects.filter(pk=company.pk).delete()


def main():
    company = company_b = user = None
    try:
        currency = Currency.objects.get(pk="PKR")
        company = Company.objects.create(
            name=f"PHASE12 SALES {TAG} A", inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency, tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE12 SALES {TAG} B", inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency, tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        definition = schema_family(INVENTORY_MODE_QUANTITY)
        chk("fresh schema includes sales lifecycle",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0] >= 8)
        chk("fresh sales schema verifies",
            verify_company_schema(company, use_cache=False).ok)

        pcs, wh_a = setup_scope(schema, "SALA", "PCS")
        kg, wh_b = setup_scope(schema, "SALB", "KG")
        purchase(schema, "stock-a1", pcs, wh_a, 3, 100)
        purchase(schema, "stock-a2", pcs, wh_a, 5, 120, "2026-07-02")
        purchase(schema, "stock-b", kg, wh_b, "4.500", 80)
        before_inventory = account(schema, "1400")

        credit_data = payload("credit-main", [
            {"variant_id": pcs, "warehouse_id": wh_a,
             "quantity": "5", "unit_price_base": "200"},
            {"variant_id": kg, "warehouse_id": wh_b,
             "quantity": "1.500", "unit_price_base": "150"},
        ])
        credit = create(schema, credit_data)
        sale_id = credit["sale_invoice_id"]
        chk("multi-line multi-warehouse credit sale posts",
            credit["status"] == "success"
            and Decimal(str(credit["total_base"])) == Decimal("1225"))
        chk("sale uses SAL sequence", credit["document_number"] == "SAL-000001")
        chk("FIFO consumes oldest layers exactly",
            q(schema, """
                SELECT fa.unit_cost_base,fa.quantity
                  FROM fifo_allocations fa JOIN stock_movements sm
                    ON sm.movement_id=fa.outbound_movement_id
                 WHERE sm.source_type='sale' AND sm.source_id=%s
                   AND sm.variant_id=%s ORDER BY allocation_id
            """, [sale_id, pcs]) == [
                (Decimal("100.000000"), Decimal("3")),
                (Decimal("120.000000"), Decimal("2")),
            ])
        chk("sale lines retain FIFO COGS",
            q(schema, "SELECT sum(cogs_base) FROM sale_lines WHERE sale_invoice_id=%s",
              [sale_id])[0][0] == Decimal("660"))
        chk("credit sale posts AR and Revenue",
            account(schema, "1200") == Decimal("1225")
            and account(schema, "4000") == Decimal("-1225"))
        chk("credit sale posts COGS and reduces Inventory",
            account(schema, "5000") == Decimal("660")
            and account(schema, "1400") == before_inventory - Decimal("660"))
        chk("credit sale journal remains balanced",
            q(schema, "SELECT sum(debit),sum(credit) FROM journal_lines")[0][0]
            == q(schema, "SELECT sum(debit),sum(credit) FROM journal_lines")[0][1])

        same = create(schema, credit_data)
        chk("identical retry is idempotent",
            same["idempotent"] is True
            and same["sale_invoice_id"] == sale_id)
        changed = dict(credit_data)
        changed["customer_name"] = "Changed Customer"
        chk("changed idempotency payload is rejected",
            rejected(schema, "SELECT quantity_create_sale(%s::jsonb)",
                     [json.dumps(changed)]))

        cash = create(schema, payload("cash-main", [{
            "variant_id": kg, "warehouse_id": wh_b,
            "quantity": "1", "unit_price_base": "175",
        }], customer_name="", sale_type="cash", payment_account_code="1000"))
        chk("cash sale debits Cash without AR",
            cash["status"] == "success"
            and account(schema, "1000") == Decimal("175")
            and account(schema, "1200") == Decimal("1225"))

        invalid = [
            ("zero quantity", {"variant_id": pcs, "warehouse_id": wh_a,
                               "quantity": "0", "unit_price_base": "1"}),
            ("fractional Piece", {"variant_id": pcs, "warehouse_id": wh_a,
                                  "quantity": "1.5", "unit_price_base": "1"}),
            ("excessive stock", {"variant_id": pcs, "warehouse_id": wh_a,
                                 "quantity": "99", "unit_price_base": "1"}),
            ("zero price", {"variant_id": pcs, "warehouse_id": wh_a,
                            "quantity": "1", "unit_price_base": "0"}),
        ]
        for index, (label, line) in enumerate(invalid):
            chk(f"{label} sale is rejected", rejected(
                schema, "SELECT quantity_create_sale(%s::jsonb)",
                [json.dumps(payload(f"bad-{index}", [line]))],
            ))

        edit_variant, edit_wh = setup_scope(schema, "EDITSALE", "PCS")
        purchase(schema, "edit-stock", edit_variant, edit_wh, 10, 25)
        editable = create(schema, payload("editable", [{
            "variant_id": edit_variant, "warehouse_id": edit_wh,
            "quantity": "4", "unit_price_base": "50",
        }]))
        edited = as_json(q(schema, "SELECT quantity_update_sale(%s,%s::jsonb)", [
            editable["sale_invoice_id"], json.dumps(payload("ignored", [{
                "variant_id": edit_variant, "warehouse_id": edit_wh,
                "quantity": "6", "unit_price_base": "55",
            }], invoice_date="2026-07-11", customer_name="Edited Customer")),
        ])[0][0])
        chk("sale edit preserves number and creates revision",
            edited["document_number"] == editable["document_number"]
            and edited["revision_number"] == 2
            and q(schema, "SELECT count(*) FROM sale_revisions WHERE sale_invoice_id=%s",
                  [editable["sale_invoice_id"]])[0][0] == 1)
        chk("sale edit rebuilds FIFO stock and accounting",
            q(schema, "SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",
              [edit_variant, edit_wh])[0][0] == Decimal("4")
            and q(schema, "SELECT cogs_base,line_total_base FROM sale_lines WHERE sale_invoice_id=%s",
                  [editable["sale_invoice_id"]])[0] == (
                      Decimal("150"), Decimal("330")))
        chk("unsafe sale edit rolls back atomically", rejected(
            schema, "SELECT quantity_update_sale(%s,%s::jsonb)", [
                editable["sale_invoice_id"], json.dumps(payload("ignored", [{
                    "variant_id": edit_variant, "warehouse_id": edit_wh,
                    "quantity": "11", "unit_price_base": "55",
                }]))
            ]))

        reverse = as_json(q(schema, "SELECT quantity_reverse_sale(%s,%s,1)", [
            editable["sale_invoice_id"], date(2026, 7, 12),
        ])[0][0])
        chk("sale reversal restores FIFO stock",
            reverse["status"] == "success"
            and q(schema, "SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",
                  [edit_variant, edit_wh])[0][0] == Decimal("10"))
        chk("sale reversal cannot repeat", rejected(
            schema, "SELECT quantity_reverse_sale(%s,%s,1)",
            [editable["sale_invoice_id"], date(2026, 7, 13)]))

        con_variant, con_wh = setup_scope(schema, "FINAL", "PCS")
        purchase(schema, "final-stock", con_variant, con_wh, 1, 10)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(
                lambda data: concurrent_attempt(schema, data),
                [
                    payload("final-a", [{"variant_id": con_variant,
                                         "warehouse_id": con_wh,
                                         "quantity": "1", "unit_price_base": "20"}]),
                    payload("final-b", [{"variant_id": con_variant,
                                         "warehouse_id": con_wh,
                                         "quantity": "1", "unit_price_base": "20"}]),
                ],
            ))
        chk("concurrent final-stock sale permits exactly one",
            sorted(x[0] for x in outcomes) == ["ok", "rejected"])
        chk("concurrent sale cannot oversell",
            q(schema, "SELECT on_hand_quantity FROM stock_balances WHERE variant_id=%s AND warehouse_id=%s",
              [con_variant, con_wh])[0][0] == 0)

        details = as_json(q(schema, "SELECT quantity_sale_details(%s)",
                            [sale_id])[0][0])
        summary = as_json(q(schema, "SELECT quantity_sale_summary(%s,%s)",
                            [date(2026, 7, 1), date(2026, 7, 31)])[0][0])
        chk("sale details expose price cost SKU and warehouse",
            details["customer_name"] == "Phase 12 Customer"
            and len(details["lines"]) == 2
            and "cogs_base" in details["lines"][0])
        chk("sale summary separates credit and cash",
            Decimal(str(summary["credit_total_base"])) > 0
            and Decimal(str(summary["cash_total_base"])) == Decimal("175"))

        b_variant, b_wh = setup_scope(schema_b, "ISOLATED", "PCS")
        purchase(schema_b, "isolated-stock", b_variant, b_wh, 1, 30)
        isolated = create(schema_b, payload("credit-main", [{
            "variant_id": b_variant, "warehouse_id": b_wh,
            "quantity": "1", "unit_price_base": "45",
        }]))
        chk("sale numbering and idempotency are tenant-isolated",
            isolated["document_number"] == "SAL-000001")
        chk("sale stock AR and Revenue are tenant-isolated",
            account(schema_b, "1200") == Decimal("45")
            and account(schema_b, "4000") == Decimal("-45"))

        call_command("apply_sql_all_tenants", str(definition.hardening_path),
                     family=INVENTORY_MODE_QUANTITY, stdout=io.StringIO())
        chk("sale hardening is idempotent",
            q(schema, "SELECT count(*) FROM quantity_seed_registry WHERE seed_key='quantity.sales'")[0][0] == 1)

        user = get_user_model().objects.create_superuser(
            username=f"phase12_admin_{TAG}",
            email=f"phase12_admin_{TAG}@example.com", password="phase12-pass",
        )
        Membership.objects.create(user=user, company=company_b)
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)
        page = client.get("/sale/sales/")
        chk("quantity sale page has manual quantities and no serial UI",
            page.status_code == 200 and b"Quantity Sales" in page.content
            and b"Serial Numbers" not in page.content)
        http_create = client.post("/sale/sales/", data=json.dumps({
            "action": "submit", "idempotency_key": "http-sale",
            "invoice_date": "2026-07-15", "customer_name": "HTTP Customer",
            "sale_type": "credit", "items": [{
                "variant_id": b_variant, "warehouse_id": b_wh,
                "quantity": "0", "unit_price_base": "50",
            }],
        }), content_type="application/json")
        chk("quantity sale validation uses guarded shared route",
            http_create.status_code == 400 and http_create.json()["success"] is False)
        chk("quantity sale HTTP navigation works",
            client.get("/sale/get-sale/", {
                "action": "current",
                "current_id": isolated["sale_invoice_id"],
            }).status_code == 200)
        chk("quantity sale HTTP summary works",
            client.get("/sale/get-sale-summary/").status_code == 200)
        chk("quantity serial endpoints are denied",
            client.post("/sale/bulk-lookup/", data="{}",
                        content_type="application/json").status_code == 404)
        chk("request search path resets to public",
            q("public", "SELECT current_schema()")[0][0] == "public")
    finally:
        if user:
            user.delete()
        drop_company(company_b)
        drop_company(company)

    passed = sum(ok for _name, ok, _detail in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}"
              f"{' — ' + detail if detail and not ok else ''}")
    print(f"\nQuantity sales: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
