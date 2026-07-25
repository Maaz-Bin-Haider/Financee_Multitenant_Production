#!/usr/bin/env python3
"""Phase 10 quantity opening-stock, accounting, reversal, UI, and isolation."""

import io
import json
import os
import sys
import time
from datetime import date
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402
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


def setup_scope(schema, suffix, unit_code):
    product_id = q(schema, "SELECT quantity_create_product(%s::jsonb)", [
        json.dumps({
            "product_name": f"Opening Product {suffix}",
            "category": "Opening Test", "user_id": 1,
        })
    ])[0][0]
    unit_id = q(schema, "SELECT unit_id FROM units_of_measure WHERE code=%s",
                [unit_code])[0][0]
    variant_id = q(schema, "SELECT quantity_create_variant(%s::jsonb)", [
        json.dumps({
            "product_id": product_id, "sku": f"OPEN-{suffix}",
            "brand": "Test", "model": suffix, "color": "Black",
            "storage": "256GB", "ram": "8GB", "region": "Global",
            "condition": "New", "unit_id": unit_id, "user_id": 1,
        })
    ])[0][0]
    warehouse_id = q(schema, "SELECT quantity_create_warehouse(%s::jsonb)", [
        json.dumps({
            "warehouse_code": f"O{suffix}",
            "warehouse_name": f"Opening Warehouse {suffix}", "user_id": 1,
        })
    ])[0][0]
    return variant_id, warehouse_id


def create_opening(schema, lines, source_date="2026-07-01", description="Opening"):
    result = q(schema, "SELECT quantity_create_opening_stock(%s::jsonb)", [
        json.dumps({
            "as_of_date": source_date, "description": description,
            "created_by_id": 1, "items": lines,
        })
    ])[0][0]
    return as_json(result)


def balance(schema, account_code):
    return q(schema, """
        SELECT COALESCE(sum(jl.debit-jl.credit),0)
          FROM journal_lines jl
          JOIN chart_of_accounts coa ON coa.account_id=jl.account_id
         WHERE coa.account_code=%s
    """, [account_code])[0][0]


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
            name=f"PHASE10 OPENING {TAG} A",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE10 OPENING {TAG} B",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        definition = schema_family(INVENTORY_MODE_QUANTITY)
        chk("fresh schema reaches opening-stock version",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0]
            == definition.required_version)
        chk("fresh opening-stock schema verifies",
            verify_company_schema(company, use_cache=False).ok)
        chk("opening-stock document prefix is configured",
            q(schema, """
                SELECT prefix FROM document_sequences
                 WHERE document_type='opening_stock'
            """)[0][0] == "OPN")

        pcs, wh_a = setup_scope(schema, "PCS", "PCS")
        kg, wh_b = setup_scope(schema, "KG", "KG")
        first = create_opening(schema, [
            {
                "variant_id": pcs, "warehouse_id": wh_a,
                "quantity": "10", "unit_cost_base": "100.250000",
            },
            {
                "variant_id": kg, "warehouse_id": wh_b,
                "quantity": "2.375", "unit_cost_base": "80.400000",
            },
        ], description="Go-live inventory")
        first_id = first["opening_stock_id"]
        expected_value = Decimal("1193.450000")
        chk("whole and decimal opening lines post atomically",
            first["status"] == "success" and first["line_count"] == 2)
        chk("opening document receives its own sequence",
            first["document_number"] == "OPN-000001")
        chk("opening quantities reach their warehouses exactly",
            q(schema, """
                SELECT variant_id, warehouse_id, on_hand_quantity
                  FROM stock_balances ORDER BY variant_id
            """) == [
                (pcs, wh_a, Decimal("10")),
                (kg, wh_b, Decimal("2.375")),
            ])
        chk("opening lines create FIFO layers and movements",
            q(schema, """
                SELECT count(*), sum(fl.remaining_quantity),
                       sum(fl.remaining_quantity*fl.unit_cost_base)
                  FROM fifo_layers fl
                  JOIN stock_movements sm
                    ON sm.movement_id=fl.inbound_movement_id
                 WHERE sm.source_type='opening_stock'
                   AND sm.source_id=%s
            """, [first_id])[0] == (2, Decimal("12.375"), expected_value))
        chk("opening accounting debits Inventory exactly",
            balance(schema, "1400") == Decimal("1193.4500"))
        chk("opening accounting credits Opening Balance exactly",
            balance(schema, "3001") == Decimal("-1193.4500"))
        chk("opening journal is balanced",
            q(schema, """
                SELECT sum(jl.debit), sum(jl.credit)
                  FROM journal_lines jl
                  JOIN opening_stock_documents d ON d.journal_id=jl.journal_id
                 WHERE d.opening_stock_id=%s
            """, [first_id])[0] == (Decimal("1193.4500"), Decimal("1193.4500")))

        listed = as_json(q(schema, "SELECT quantity_opening_stock_list()")[0][0])
        details = as_json(q(
            schema, "SELECT quantity_opening_stock_details(%s)", [first_id]
        )[0][0])
        chk("opening-stock list exposes quantity and value",
            len(listed) == 1
            and Decimal(str(listed[0]["total_cost_base"])) == expected_value)
        chk("opening-stock details retain SKU warehouse and unit",
            len(details["lines"]) == 2
            and {line["unit_code"] for line in details["lines"]} == {"PCS", "KG"}
            and {line["warehouse_id"] for line in details["lines"]} == {wh_a, wh_b})

        chk("duplicate SKU and warehouse line is rejected atomically",
            rejected(schema, "SELECT quantity_create_opening_stock(%s::jsonb)", [
                json.dumps({
                    "as_of_date": "2026-07-02", "items": [
                        {"variant_id": pcs, "warehouse_id": wh_a,
                         "quantity": "1", "unit_cost_base": "10"},
                        {"variant_id": pcs, "warehouse_id": wh_a,
                         "quantity": "2", "unit_cost_base": "10"},
                    ]
                })
            ]))
        chk("fractional Piece opening quantity is rejected",
            rejected(schema, "SELECT quantity_create_opening_stock(%s::jsonb)", [
                json.dumps({"items": [{
                    "variant_id": pcs, "warehouse_id": wh_a,
                    "quantity": "1.5", "unit_cost_base": "10",
                }]})
            ]))
        chk("four-decimal measured quantity is rejected",
            rejected(schema, "SELECT quantity_create_opening_stock(%s::jsonb)", [
                json.dumps({"items": [{
                    "variant_id": kg, "warehouse_id": wh_b,
                    "quantity": "1.0001", "unit_cost_base": "10",
                }]})
            ]))
        chk("negative unit cost is rejected",
            rejected(schema, "SELECT quantity_create_opening_stock(%s::jsonb)", [
                json.dumps({"items": [{
                    "variant_id": pcs, "warehouse_id": wh_a,
                    "quantity": "1", "unit_cost_base": "-1",
                }]})
            ]))
        chk("empty opening document is rejected",
            rejected(schema, "SELECT quantity_create_opening_stock(%s::jsonb)",
                     [json.dumps({"items": []})]))
        chk("failed documents leave no partial stock or journals",
            q(schema, "SELECT count(*) FROM opening_stock_documents")[0][0] == 1
            and q(schema, """
                SELECT count(*) FROM journal_entries
                 WHERE source_document_type='opening_stock'
            """)[0][0] == 1)
        chk("posted opening document cannot be directly changed",
            rejected(schema, """
                UPDATE opening_stock_documents SET description='tampered'
                 WHERE opening_stock_id=%s
            """, [first_id]))
        chk("posted opening lines cannot be directly changed",
            rejected(schema, """
                UPDATE opening_stock_lines SET quantity=99
                 WHERE opening_stock_id=%s
            """, [first_id]))

        reverse_variant, reverse_wh = setup_scope(schema, "REV", "PCS")
        reversible = create_opening(schema, [{
            "variant_id": reverse_variant, "warehouse_id": reverse_wh,
            "quantity": "4", "unit_cost_base": "25",
        }])
        reversal = as_json(q(schema, """
            SELECT quantity_reverse_opening_stock(%s,%s,1)
        """, [reversible["opening_stock_id"], date(2026, 7, 5)])[0][0])
        chk("untouched opening stock reverses through movements and journal",
            reversal["status"] == "success"
            and q(schema, """
                SELECT on_hand_quantity FROM stock_balances
                 WHERE variant_id=%s AND warehouse_id=%s
            """, [reverse_variant, reverse_wh])[0][0] == 0)
        chk("opening reversal nets Inventory and Opening Balance",
            balance(schema, "1400") == Decimal("1193.4500")
            and balance(schema, "3001") == Decimal("-1193.4500"))
        chk("opening stock can be reversed only once",
            rejected(schema, """
                SELECT quantity_reverse_opening_stock(%s,%s,1)
            """, [reversible["opening_stock_id"], date(2026, 7, 6)]))

        consumed_variant, consumed_wh = setup_scope(schema, "USED", "PCS")
        consumed = create_opening(schema, [{
            "variant_id": consumed_variant, "warehouse_id": consumed_wh,
            "quantity": "3", "unit_cost_base": "50",
        }])
        q(schema, """
            SELECT quantity_post_stock_movement(
                'sale',%s,%s,%s,1,NULL,'phase10_consumption',1,1,NULL,1
            )
        """, [consumed_variant, consumed_wh, date(2026, 7, 4)])
        chk("consumed opening FIFO layer cannot be reversed",
            rejected(schema, """
                SELECT quantity_reverse_opening_stock(%s,%s,1)
            """, [consumed["opening_stock_id"], date(2026, 7, 5)]))

        reclass = as_json(q(
            schema, "SELECT quantity_reclassify_opening_balance(%s::jsonb)",
            [json.dumps({"created_by_id": 1})]
        )[0][0])
        chk("Opening Balance reclassifies to Capital",
            reclass["status"] == "success"
            and balance(schema, "3001") == 0)
        chk("Capital receives the exact opening equity",
            balance(schema, "3000") == Decimal("-1343.4500"))
        second_reclass = as_json(q(
            schema, "SELECT quantity_reclassify_opening_balance('{}'::jsonb)"
        )[0][0])
        chk("reclassification is a no-op once Opening Balance is zero",
            second_reclass["status"] == "noop")
        status = as_json(q(
            schema, "SELECT quantity_opening_balance_status()"
        )[0][0])
        chk("opening balance status reflects completed reclassification",
            status["needs_reclass"] is False
            and Decimal(str(status["obe_equity_amount"])) == 0)

        tenant_b_variant, tenant_b_wh = setup_scope(schema_b, "PCS", "PCS")
        tenant_b_doc = create_opening(schema_b, [{
            "variant_id": tenant_b_variant, "warehouse_id": tenant_b_wh,
            "quantity": "7", "unit_cost_base": "30",
        }])
        chk("opening document numbering is tenant-isolated",
            tenant_b_doc["document_number"] == "OPN-000001")
        chk("opening quantities and documents are tenant-isolated",
            q(schema_b, "SELECT count(*) FROM opening_stock_documents")[0][0] == 1
            and q(schema_b, "SELECT count(*) FROM stock_movements")[0][0] == 1)

        call_command(
            "apply_sql_all_tenants", str(definition.hardening_path),
            family=INVENTORY_MODE_QUANTITY, stdout=io.StringIO(),
        )
        chk("opening-stock hardening is idempotent",
            q(schema, """
                SELECT count(*) FROM quantity_seed_registry
                 WHERE seed_key='quantity.opening_stock'
            """)[0][0] == 1
            and q(schema, """
                SELECT count(*) FROM document_sequences
                 WHERE document_type='opening_stock'
            """)[0][0] == 1)

        user = get_user_model().objects.create_superuser(
            username=f"phase10_admin_{TAG}",
            email=f"phase10_admin_{TAG}@example.com",
            password="phase10-password",
        )
        Membership.objects.create(user=user, company=company_b)
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)
        page = client.get("/opening-stock/")
        chk("quantity opening-stock page uses quantity workflow",
            page.status_code == 200
            and b"SKU quantities" in page.content
            and b"Serials + Comments" not in page.content)
        http_create = client.post(
            "/opening-stock/api/create/",
            data=json.dumps({
                "as_of_date": "2026-07-10",
                "description": "HTTP opening",
                "items": [{
                    "variant_id": tenant_b_variant,
                    "warehouse_id": tenant_b_wh,
                    "quantity": "2",
                    "unit_cost_base": "35",
                }],
            }),
            content_type="application/json",
        )
        chk("quantity opening stock posts through shared guarded HTTP route",
            http_create.status_code == 200
            and http_create.json()["document_number"] == "OPN-000002",
            http_create.content)
        http_id = http_create.json().get("opening_stock_id")
        http_list = client.get("/opening-stock/api/list/")
        http_details = client.get("/opening-stock/api/details/", {"id": http_id})
        chk("quantity opening list and details HTTP routes work",
            http_list.status_code == 200 and len(http_list.json()) == 2
            and http_details.status_code == 200
            and len(http_details.json()["lines"]) == 1)
        chk("serial validation endpoint is disabled for quantity tenant",
            client.post(
                "/opening-stock/api/check-serials/",
                data="{}", content_type="application/json",
            ).status_code == 404)
        http_reverse = client.post(
            "/opening-stock/api/delete/",
            data=json.dumps({"id": http_id}), content_type="application/json",
        )
        chk("quantity opening HTTP delete performs guarded reversal",
            http_reverse.status_code == 200
            and http_reverse.json()["status"] == "success")
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
    print(f"\nQuantity opening stock: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
