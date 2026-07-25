#!/usr/bin/env python3
"""Phase 11 domestic quantity purchase lifecycle and reconciliation."""

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
from django.db import (  # noqa: E402
    DatabaseError, close_old_connections, connection, transaction,
)
from django.test import Client  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company, Currency, Membership, INVENTORY_MODE_QUANTITY,
)
from tenancy.schema_families import schema_family  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402

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


def rejected(schema, sql, params=None):
    try:
        with transaction.atomic():
            q(schema, sql, params)
        return False
    except DatabaseError:
        return True


def as_json(value):
    return json.loads(value) if isinstance(value, str) else value


def setup_scope(schema, suffix, unit="PCS"):
    product = q(schema, "SELECT quantity_create_product(%s::jsonb)", [
        json.dumps({"product_name": f"Purchase Product {suffix}",
                    "category": "Purchase Test", "user_id": 1})
    ])[0][0]
    unit_id = q(schema, "SELECT unit_id FROM units_of_measure WHERE code=%s",
                [unit])[0][0]
    variant = q(schema, "SELECT quantity_create_variant(%s::jsonb)", [
        json.dumps({
            "product_id": product, "sku": f"PUR-{suffix}", "brand": "Test",
            "model": suffix, "color": "Black", "storage": "256GB",
            "ram": "8GB", "region": "Global", "condition": "New",
            "unit_id": unit_id, "user_id": 1,
        })
    ])[0][0]
    warehouse = q(schema, "SELECT quantity_create_warehouse(%s::jsonb)", [
        json.dumps({"warehouse_code": f"P{suffix}",
                    "warehouse_name": f"Purchase Warehouse {suffix}",
                    "user_id": 1})
    ])[0][0]
    return variant, warehouse


def payload(key, lines, **overrides):
    data = {
        "idempotency_key": key, "invoice_date": "2026-07-01",
        "vendor_name": "Test Vendor", "purchase_type": "credit",
        "description": "Domestic purchase", "created_by_id": 1,
        "items": lines,
    }
    data.update(overrides)
    return data


def create(schema, data):
    return as_json(q(schema, "SELECT quantity_create_purchase(%s::jsonb)",
                     [json.dumps(data)])[0][0])


def account(schema, code):
    return q(schema, """
        SELECT COALESCE(sum(jl.debit-jl.credit),0)
          FROM journal_lines jl JOIN chart_of_accounts c
            ON c.account_id=jl.account_id WHERE c.account_code=%s
    """, [code])[0][0]


def concurrent_create(args):
    schema, data = args
    close_old_connections()
    try:
        return create(schema, data)
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
            name=f"PHASE11 PURCHASE {TAG} A",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency, tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE11 PURCHASE {TAG} B",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency, tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        definition = schema_family(INVENTORY_MODE_QUANTITY)
        chk("fresh schema reaches purchase version",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0] == 7)
        chk("fresh purchase schema verifies",
            verify_company_schema(company, use_cache=False).ok)

        pcs, wh_a = setup_scope(schema, "PCS", "PCS")
        kg, wh_b = setup_scope(schema, "KG", "KG")
        credit_data = payload("credit-main", [
            {"variant_id": pcs, "warehouse_id": wh_a,
             "quantity": "10", "unit_cost_base": "100"},
            {"variant_id": kg, "warehouse_id": wh_b,
             "quantity": "2.500", "unit_cost_base": "80"},
        ])
        credit = create(schema, credit_data)
        credit_id = credit["purchase_invoice_id"]
        chk("multi-line and multi-warehouse credit purchase posts",
            credit["status"] == "success"
            and Decimal(str(credit["total_base"])) == Decimal("1200"))
        chk("purchase uses PUR sequence",
            credit["document_number"] == "PUR-000001")
        chk("whole and decimal purchase quantities are exact",
            q(schema, """
                SELECT variant_id,on_hand_quantity FROM stock_balances
                 ORDER BY variant_id
            """) == [(pcs, Decimal("10")), (kg, Decimal("2.5"))])
        chk("purchase creates separate FIFO costs and source lineage",
            q(schema, """
                SELECT count(*),sum(original_quantity),
                       sum(original_quantity*unit_cost_base)
                  FROM fifo_layers WHERE source_type='purchase' AND source_id=%s
            """, [credit_id])[0] == (2, Decimal("12.5"), Decimal("1200")))
        chk("credit purchase debits Inventory",
            account(schema, "1400") == Decimal("1200"))
        chk("credit purchase credits Accounts Payable",
            account(schema, "2000") == Decimal("-1200"))
        chk("credit purchase does not affect Cash",
            account(schema, "1000") == 0)
        chk("credit purchase journal and trial balance are balanced",
            q(schema, "SELECT sum(debit),sum(credit) FROM journal_lines")[0]
            == (Decimal("1200"), Decimal("1200")))

        same = create(schema, credit_data)
        chk("repeated identical submission is idempotent",
            same["idempotent"] is True
            and same["purchase_invoice_id"] == credit_id
            and q(schema, "SELECT count(*) FROM purchase_invoices")[0][0] == 1)
        changed_key = dict(credit_data)
        changed_key["vendor_name"] = "Changed Vendor"
        chk("idempotency key reuse with changed payload is rejected",
            rejected(schema, "SELECT quantity_create_purchase(%s::jsonb)",
                     [json.dumps(changed_key)]))

        cash_variant, cash_wh = setup_scope(schema, "CASH", "PCS")
        cash = create(schema, payload("cash-one", [{
            "variant_id": cash_variant, "warehouse_id": cash_wh,
            "quantity": "2", "unit_cost_base": "50",
        }], vendor_name="", purchase_type="cash",
           payment_account_code="1000"))
        chk("cash purchase posts without a vendor payable",
            cash["status"] == "success"
            and account(schema, "2000") == Decimal("-1200"))
        chk("cash purchase credits Cash exactly",
            account(schema, "1000") == Decimal("-100"))
        chk("cash purchase increases Inventory exactly",
            account(schema, "1400") == Decimal("1300"))

        invalid_cases = [
            ("fractional Piece", payload("bad-piece", [{
                "variant_id": pcs, "warehouse_id": wh_a,
                "quantity": "1.5", "unit_cost_base": "10",
            }])),
            ("four-decimal KG", payload("bad-kg", [{
                "variant_id": kg, "warehouse_id": wh_b,
                "quantity": "1.0001", "unit_cost_base": "10",
            }])),
            ("zero cost", payload("bad-cost", [{
                "variant_id": pcs, "warehouse_id": wh_a,
                "quantity": "1", "unit_cost_base": "0",
            }])),
            ("duplicate scope", payload("bad-duplicate", [
                {"variant_id": pcs, "warehouse_id": wh_a,
                 "quantity": "1", "unit_cost_base": "10"},
                {"variant_id": pcs, "warehouse_id": wh_a,
                 "quantity": "2", "unit_cost_base": "10"},
            ])),
            ("empty lines", payload("bad-empty", [])),
        ]
        for label, data in invalid_cases:
            chk(f"{label} purchase is rejected",
                rejected(schema, "SELECT quantity_create_purchase(%s::jsonb)",
                         [json.dumps(data)]))
        chk("invalid purchases leave no partial documents",
            q(schema, "SELECT count(*) FROM purchase_invoices")[0][0] == 2)

        edit_variant, edit_wh = setup_scope(schema, "EDIT", "PCS")
        editable = create(schema, payload("editable", [{
            "variant_id": edit_variant, "warehouse_id": edit_wh,
            "quantity": "5", "unit_cost_base": "100",
        }], invoice_date="2026-07-02"))
        editable_id = editable["purchase_invoice_id"]
        sale = as_json(q(schema, """
            SELECT quantity_post_stock_movement(
                'sale',%s,%s,%s,4,NULL,'phase11_sale',1,1,'TEST-SALE',1
            )
        """, [edit_variant, edit_wh, date(2026, 7, 5)])[0][0])
        chk("later consumption initially uses original purchase cost",
            Decimal(str(sale["total_cost_base"])) == Decimal("400"))
        updated_data = payload("ignored-on-update", [{
            "variant_id": edit_variant, "warehouse_id": edit_wh,
            "quantity": "5", "unit_cost_base": "120",
        }], invoice_date="2026-07-03", vendor_name="Edited Vendor")
        updated = as_json(q(schema, """
            SELECT quantity_update_purchase(%s,%s::jsonb)
        """, [editable_id, json.dumps(updated_data)])[0][0])
        chk("purchase edit preserves number and increments revision",
            updated["document_number"] == editable["document_number"]
            and updated["revision_number"] == 2)
        chk("backdated purchase edit deterministically reflows later FIFO cost",
            q(schema, """
                SELECT total_cost_base FROM stock_movements
                 WHERE source_type='phase11_sale' AND source_id=1
            """)[0][0] == Decimal("480"))
        chk("purchase edit keeps correct closing stock and FIFO value",
            q(schema, """
                SELECT b.on_hand_quantity,sum(fl.remaining_quantity*fl.unit_cost_base)
                  FROM stock_balances b JOIN fifo_layers fl
                    ON fl.variant_id=b.variant_id
                   AND fl.warehouse_id=b.warehouse_id
                 WHERE b.variant_id=%s AND b.warehouse_id=%s
                 GROUP BY b.on_hand_quantity
            """, [edit_variant, edit_wh])[0] == (Decimal("1"), Decimal("120")))
        chk("purchase edit retains immutable previous snapshot",
            q(schema, """
                SELECT count(*),previous_document->>'vendor_name'
                  FROM purchase_revisions WHERE purchase_invoice_id=%s
                 GROUP BY previous_document
            """, [editable_id])[0] == (1, "Test Vendor"))
        unsafe_data = payload("unsafe-edit", [{
            "variant_id": edit_variant, "warehouse_id": edit_wh,
            "quantity": "3", "unit_cost_base": "120",
        }], invoice_date="2026-07-03")
        chk("edit causing historical negative stock is rejected",
            rejected(schema, "SELECT quantity_update_purchase(%s,%s::jsonb)",
                     [editable_id, json.dumps(unsafe_data)]))
        chk("rejected edit rolls back document stock cost and journal",
            q(schema, """
                SELECT revision_number,total_base,vendor_name
                  FROM purchase_invoices WHERE purchase_invoice_id=%s
            """, [editable_id])[0] == (2, Decimal("600"), "Edited Vendor")
            and q(schema, """
                SELECT total_cost_base FROM stock_movements
                 WHERE source_type='phase11_sale' AND source_id=1
            """)[0][0] == Decimal("480"))

        reverse_variant, reverse_wh = setup_scope(schema, "REV", "PCS")
        reversible = create(schema, payload("reversible", [{
            "variant_id": reverse_variant, "warehouse_id": reverse_wh,
            "quantity": "3", "unit_cost_base": "40",
        }]))
        reversal = as_json(q(schema, """
            SELECT quantity_reverse_purchase(%s,%s,1)
        """, [reversible["purchase_invoice_id"], date(2026, 7, 8)])[0][0])
        chk("untouched purchase reverses stock and accounting",
            reversal["status"] == "success"
            and q(schema, """
                SELECT on_hand_quantity FROM stock_balances
                 WHERE variant_id=%s AND warehouse_id=%s
            """, [reverse_variant, reverse_wh])[0][0] == 0)
        chk("purchase reversal is retained and cannot repeat",
            q(schema, """
                SELECT status,reversal_journal_id IS NOT NULL
                  FROM purchase_invoices WHERE purchase_invoice_id=%s
            """, [reversible["purchase_invoice_id"]])[0] == ("reversed", True)
            and rejected(schema, """
                SELECT quantity_reverse_purchase(%s,%s,1)
            """, [reversible["purchase_invoice_id"], date(2026, 7, 9)]))
        chk("consumed purchase cannot be reversed",
            rejected(schema, """
                SELECT quantity_reverse_purchase(%s,%s,1)
            """, [editable_id, date(2026, 7, 9)]))

        concurrent_variant, concurrent_wh = setup_scope(schema, "CON", "PCS")
        concurrent_data = payload("concurrent-key", [{
            "variant_id": concurrent_variant, "warehouse_id": concurrent_wh,
            "quantity": "10", "unit_cost_base": "15",
        }])
        with ThreadPoolExecutor(max_workers=2) as pool:
            concurrent_results = list(pool.map(
                concurrent_create,
                [(schema, concurrent_data), (schema, concurrent_data)],
            ))
        chk("concurrent duplicate submission creates one purchase",
            len({r["purchase_invoice_id"] for r in concurrent_results}) == 1
            and sorted(r["idempotent"] for r in concurrent_results)
            == [False, True])
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(
                lambda fn: fn(),
                [
                    lambda: create(schema, payload("interaction-purchase", [{
                        "variant_id": concurrent_variant,
                        "warehouse_id": concurrent_wh,
                        "quantity": "1", "unit_cost_base": "16",
                    }], invoice_date="2026-07-10")),
                    lambda: as_json(q(schema, """
                        SELECT quantity_post_stock_movement(
                            'sale',%s,%s,%s,10,NULL,'phase11_interaction',
                            2,1,'INTERACTION',1
                        )
                    """, [concurrent_variant, concurrent_wh,
                           date(2026, 7, 11)])[0][0]),
                ],
            ))
        chk("concurrent purchase and sale serialize without negative stock",
            len(outcomes) == 2
            and q(schema, """
                SELECT on_hand_quantity>=0 FROM stock_balances
                 WHERE variant_id=%s AND warehouse_id=%s
            """, [concurrent_variant, concurrent_wh])[0][0])
        chk("purchase/sale interaction remains FIFO reconciled",
            q(schema, """
                SELECT is_reconciled FROM quantity_inventory_reconciliation(%s,%s)
            """, [concurrent_variant, concurrent_wh])[0][0])

        details = as_json(q(
            schema, "SELECT quantity_purchase_details(%s)", [credit_id]
        )[0][0])
        previous = as_json(q(
            schema, "SELECT quantity_purchase_navigate('previous',%s)",
            [cash["purchase_invoice_id"]]
        )[0][0])
        summary = as_json(q(
            schema, "SELECT quantity_purchase_summary(%s,%s)",
            [date(2026, 7, 1), date(2026, 7, 31)]
        )[0][0])
        chk("purchase details retain vendor SKU warehouse and costs",
            details["vendor_name"] == "Test Vendor"
            and len(details["lines"]) == 2)
        chk("purchase previous navigation is deterministic",
            previous["purchase_invoice_id"] == credit_id)
        chk("purchase summary separates cash and credit totals",
            Decimal(str(summary["credit_total_base"])) > 0
            and Decimal(str(summary["cash_total_base"])) > 0
            and summary["invoice_count"] >= 5)

        tenant_b_variant, tenant_b_wh = setup_scope(schema_b, "PCS", "PCS")
        tenant_b_purchase = create(schema_b, payload("credit-main", [{
            "variant_id": tenant_b_variant, "warehouse_id": tenant_b_wh,
            "quantity": "1", "unit_cost_base": "25",
        }]))
        chk("purchase number and idempotency key are tenant-isolated",
            tenant_b_purchase["document_number"] == "PUR-000001")
        chk("purchase stock and AP are tenant-isolated",
            q(schema_b, "SELECT count(*) FROM purchase_invoices")[0][0] == 1
            and account(schema_b, "2000") == Decimal("-25"))

        call_command(
            "apply_sql_all_tenants", str(definition.hardening_path),
            family=INVENTORY_MODE_QUANTITY, stdout=io.StringIO(),
        )
        chk("purchase hardening is idempotent",
            q(schema, """
                SELECT count(*) FROM quantity_seed_registry
                 WHERE seed_key='quantity.purchases'
            """)[0][0] == 1)

        user = get_user_model().objects.create_superuser(
            username=f"phase11_admin_{TAG}",
            email=f"phase11_admin_{TAG}@example.com", password="phase11-pass",
        )
        Membership.objects.create(user=user, company=company_b)
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)
        page = client.get("/purchase/purchasing/")
        chk("quantity purchase page contains no serial entry",
            page.status_code == 200 and b"Quantity Purchases" in page.content
            and b"Serial Numbers" not in page.content)
        http_create = client.post(
            "/purchase/purchasing/",
            data=json.dumps({
                "action": "submit", "idempotency_key": "http-purchase",
                "invoice_date": "2026-07-12", "vendor_name": "HTTP Vendor",
                "purchase_type": "credit", "items": [{
                    "variant_id": tenant_b_variant,
                    "warehouse_id": tenant_b_wh,
                    "quantity": "2", "unit_cost_base": "30",
                }],
            }), content_type="application/json",
        )
        chk("quantity purchase posts through guarded shared HTTP route",
            http_create.status_code == 200
            and http_create.json()["success"] is True, http_create.content)
        http_id = http_create.json().get("purchase_invoice_id")
        chk("quantity purchase HTTP navigation works",
            client.get("/purchase/get-purchase/", {
                "action": "current", "current_id": http_id,
            }).status_code == 200)
        chk("quantity purchase HTTP summary works",
            client.get("/purchase/get-purchase-summary/").status_code == 200)
        chk("serial validation endpoint is denied for quantity purchases",
            client.post("/purchase/check-serials/", data="{}",
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
    print(f"\nQuantity purchases: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
