#!/usr/bin/env python3
"""Phase 9 immutable movements, FIFO, replay, concurrency, and reconciliation."""

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

from django.db import (  # noqa: E402
    DatabaseError, close_old_connections, connection, transaction,
)

from tenancy.models import Company, Currency, INVENTORY_MODE_QUANTITY  # noqa: E402
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


def setup_scope(schema, suffix, unit_code="PCS"):
    product_id = q(schema, """
        SELECT quantity_create_product(%s::jsonb)
    """, [json.dumps({
        "product_name": f"FIFO Product {suffix}",
        "category": "FIFO Test",
        "user_id": 1,
    })])[0][0]
    unit_id = q(
        schema, "SELECT unit_id FROM units_of_measure WHERE code=%s",
        [unit_code],
    )[0][0]
    variant_id = q(schema, """
        SELECT quantity_create_variant(%s::jsonb)
    """, [json.dumps({
        "product_id": product_id,
        "sku": f"FIFO-{suffix}",
        "brand": "Test Brand", "model": f"Model {suffix}",
        "color": "Black", "storage": "256GB", "ram": "8GB",
        "region": "Global", "condition": "New", "unit_id": unit_id,
        "reorder_level": "0", "user_id": 1,
    })])[0][0]
    warehouse_id = q(schema, """
        SELECT quantity_create_warehouse(%s::jsonb)
    """, [json.dumps({
        "warehouse_code": f"W{suffix}",
        "warehouse_name": f"Warehouse {suffix}",
        "user_id": 1,
    })])[0][0]
    return variant_id, warehouse_id


def post(schema, movement_type, variant_id, warehouse_id, movement_date,
         quantity, unit_cost, source_id, source_line=1, effective=None):
    result = q(schema, """
        SELECT quantity_post_stock_movement(
            %s, %s, %s, %s, %s, %s, 'phase9_test', %s, %s,
            %s, 1, 'Phase 9 movement', %s
        )
    """, [
        movement_type, variant_id, warehouse_id, movement_date, quantity,
        unit_cost, source_id, source_line, f"FIFO-{source_id}", effective,
    ])[0][0]
    return json.loads(result) if isinstance(result, str) else result


def concurrent_outbound(args):
    close_old_connections()
    try:
        schema, variant_id, warehouse_id, source_id = args
        try:
            post(
                schema, "sale", variant_id, warehouse_id, date(2026, 7, 20),
                "1", None, source_id,
            )
            return "posted"
        except DatabaseError:
            return "rejected"
    finally:
        close_old_connections()


def lock_pairs(args):
    close_old_connections()
    schema, payload = args
    try:
        with transaction.atomic():
            q(schema, "SELECT quantity_lock_inventory_pairs(%s::jsonb)",
              [json.dumps(payload)])
        return True
    except DatabaseError:
        return False
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
    company = company_b = None
    try:
        currency = Currency.objects.get(pk="PKR")
        company = Company.objects.create(
            name=f"PHASE9 FIFO {TAG} A",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        company_b = Company.objects.create(
            name=f"PHASE9 FIFO {TAG} B",
            inventory_mode=INVENTORY_MODE_QUANTITY,
            base_currency=currency,
            tax_environment="non_tax",
        )
        schema, schema_b = company.schema_name, company_b.schema_name
        definition = schema_family(INVENTORY_MODE_QUANTITY)
        chk("fresh schema reaches FIFO version",
            q(schema, "SELECT version FROM tenant_schema_metadata")[0][0]
            == definition.required_version)
        chk("fresh FIFO schema verifies",
            verify_company_schema(company, use_cache=False).ok)

        variant_id, warehouse_id = setup_scope(schema, "A")
        inbound = post(
            schema, "purchase", variant_id, warehouse_id, date(2026, 7, 1),
            "10", "100", 1,
        )
        chk("single FIFO layer created",
            q(schema, """
                SELECT original_quantity, remaining_quantity, unit_cost_base
                  FROM fifo_layers WHERE variant_id=%s AND warehouse_id=%s
            """, [variant_id, warehouse_id])[0]
            == (q(schema, "SELECT 10::numeric")[0][0],
                q(schema, "SELECT 10::numeric")[0][0],
                q(schema, "SELECT 100::numeric")[0][0]))
        outbound = post(
            schema, "sale", variant_id, warehouse_id, date(2026, 7, 2),
            "4", None, 2,
        )
        outbound_id = outbound["movement_id"]
        chk("partial consumption uses first layer cost",
            Decimal(str(outbound["total_cost_base"])) == Decimal("400"), outbound)
        chk("partial consumption leaves six",
            str(q(schema, """
                SELECT remaining_quantity FROM fifo_layers
                 WHERE variant_id=%s AND warehouse_id=%s
            """, [variant_id, warehouse_id])[0][0]) == "6")

        post(
            schema, "purchase", variant_id, warehouse_id, date(2026, 7, 3),
            "5", "120", 3,
        )
        second_out = post(
            schema, "sale", variant_id, warehouse_id, date(2026, 7, 4),
            "8", None, 4,
        )
        chk("multi-layer FIFO cost is exact",
            Decimal(str(second_out["total_cost_base"])) == Decimal("840"),
            second_out)
        allocations = q(schema, """
            SELECT fa.quantity, fa.unit_cost_base, fa.total_cost_base
              FROM fifo_allocations fa
             WHERE fa.outbound_movement_id=%s ORDER BY allocation_order
        """, [second_out["movement_id"]])
        chk("multi-layer allocation trace is durable",
            [(str(a), str(b), str(c)) for a, b, c in allocations]
            == [
                ("6", "100.000000", "600.000000"),
                ("2", "120.000000", "240.000000"),
            ], allocations)
        chk("full first-layer consumption and partial second are correct",
            [str(row[0]) for row in q(schema, """
                SELECT remaining_quantity FROM fifo_layers
                 WHERE variant_id=%s AND warehouse_id=%s
                 ORDER BY source_date, effective_sequence
            """, [variant_id, warehouse_id])] == ["0", "3"])
        chk("availability equals movement closing quantity",
            str(q(schema, """
                SELECT quantity_stock_availability(%s,%s,NULL)
            """, [variant_id, warehouse_id])[0][0]) == "3")
        chk("historical availability uses business date",
            str(q(schema, """
                SELECT quantity_stock_availability(%s,%s,'2026-07-02')
            """, [variant_id, warehouse_id])[0][0]) == "6")

        other_warehouse = q(schema, """
            SELECT quantity_create_warehouse(%s::jsonb)
        """, [json.dumps({
            "warehouse_code": "WOTHER", "warehouse_name": "Other Warehouse",
        })])[0][0]
        post(
            schema, "purchase", variant_id, other_warehouse, date(2026, 7, 1),
            "7", "90", 5,
        )
        chk("same SKU stock is isolated by warehouse",
            str(q(schema, """
                SELECT quantity_stock_availability(%s,%s,NULL)
            """, [variant_id, other_warehouse])[0][0]) == "7"
            and str(q(schema, """
                SELECT quantity_stock_availability(%s,%s,NULL)
            """, [variant_id, warehouse_id])[0][0]) == "3")

        replay_variant, replay_wh = setup_scope(schema, "REPLAY")
        post(schema, "purchase", replay_variant, replay_wh, date(2026, 7, 2),
             "5", "20", 10)
        replay_sale = post(
            schema, "sale", replay_variant, replay_wh, date(2026, 7, 3),
            "4", None, 11,
        )
        chk("pre-backdate COGS uses original earliest layer",
            Decimal(str(replay_sale["total_cost_base"])) == Decimal("80"))
        backdated = post(
            schema, "purchase", replay_variant, replay_wh, date(2026, 7, 1),
            "4", "10", 12,
        )
        replayed_cost = q(schema, """
            SELECT total_cost_base FROM stock_movements WHERE movement_id=%s
        """, [replay_sale["movement_id"]])[0][0]
        chk("backdated inbound deterministically replays later COGS",
            str(replayed_cost) == "40.000000", replayed_cost)
        chk("backdated replay preserves correct closing stock",
            str(backdated["reconciliation"]["on_hand_quantity"]) == "5")
        chk("historically negative backdated outbound is rejected", rejected(
            schema, """
                SELECT quantity_post_stock_movement(
                    'sale', %s, %s, '2026-06-30', 1, NULL,
                    'phase9_negative', 1, 1
                )
            """, [replay_variant, replay_wh]))
        chk("rejected historical movement rolls back completely",
            q(schema, """
                SELECT count(*) FROM stock_movements
                 WHERE source_type='phase9_negative'
            """)[0][0] == 0)

        decimal_variant, decimal_wh = setup_scope(schema, "KG", "KG")
        post(schema, "purchase", decimal_variant, decimal_wh, date(2026, 7, 1),
             "2.345", "50.123456", 20)
        decimal_out = post(
            schema, "sale", decimal_variant, decimal_wh, date(2026, 7, 2),
            "1.234", None, 21,
        )
        chk("three-decimal quantity and six-decimal cost are exact",
            str(decimal_out["total_cost_base"]) == "61.852345", decimal_out)
        chk("four-decimal stock movement is rejected", rejected(
            schema, """
                SELECT quantity_post_stock_movement(
                    'sale', %s, %s, CURRENT_DATE, 0.0001, NULL,
                    'phase9_precision', 1, 1
                )
            """, [decimal_variant, decimal_wh]))

        idempotent = post(
            schema, "purchase", variant_id, warehouse_id, date(2026, 7, 5),
            "2", "130", 30,
        )
        idempotent_again = post(
            schema, "purchase", variant_id, warehouse_id, date(2026, 7, 5),
            "2", "130", 30,
        )
        chk("same source and payload is idempotent",
            idempotent_again["idempotent"] is True
            and idempotent_again["movement_id"] == idempotent["movement_id"])
        chk("same source with changed payload is rejected", rejected(
            schema, """
                SELECT quantity_post_stock_movement(
                    'purchase', %s, %s, '2026-07-05', 3, 130,
                    'phase9_test', 30, 1
                )
            """, [variant_id, warehouse_id]))

        chk("direct movement insertion is blocked", rejected(
            schema, """
                INSERT INTO stock_movements (
                    variant_id, warehouse_id, movement_date, movement_type,
                    quantity_in, source_type, source_id, source_line_id,
                    unit_cost_base
                ) VALUES (%s,%s,CURRENT_DATE,'purchase',1,'direct_test',1,1,1)
            """, [variant_id, warehouse_id]))
        chk("direct movement update is blocked", rejected(
            schema, "UPDATE stock_movements SET quantity_in=99 WHERE movement_id=%s",
            [inbound["movement_id"]]))
        chk("direct movement deletion is blocked", rejected(
            schema, "DELETE FROM stock_movements WHERE movement_id=%s",
            [inbound["movement_id"]]))
        chk("variant and warehouse references are registered",
            q(schema, """
                SELECT
                    EXISTS(SELECT 1 FROM variant_transaction_registry
                            WHERE variant_id=%s),
                    EXISTS(SELECT 1 FROM warehouse_reference_registry
                            WHERE warehouse_id=%s)
            """, [variant_id, warehouse_id])[0] == (True, True))
        chk("referenced SKU and warehouse master deletion/mutation are protected",
            rejected(schema, """
                SELECT quantity_update_variant(
                    %s, '{"sku":"CHANGED-AFTER-STOCK"}'::jsonb
                )
            """, [variant_id])
            and rejected(schema, "SELECT quantity_delete_warehouse(%s)",
                         [warehouse_id]))

        reversal_variant, reversal_wh = setup_scope(schema, "REVERSAL")
        post(
            schema, "purchase", reversal_variant, reversal_wh,
            date(2026, 7, 18), "5", "40", 90,
        )
        reversible_sale = post(
            schema, "sale", reversal_variant, reversal_wh,
            date(2026, 7, 19), "2", None, 91,
        )
        reversal = q(schema, """
            SELECT quantity_reverse_stock_movement(%s,%s,%s,1)
        """, [
            reversible_sale["movement_id"], date(2026, 7, 20), 92,
        ])[0][0]
        reversal = json.loads(reversal) if isinstance(reversal, str) else reversal
        restored_balance = q(schema, """
            SELECT b.on_hand_quantity,
                   COALESCE(sum(fl.remaining_quantity * fl.unit_cost_base), 0)
              FROM stock_balances b
              LEFT JOIN fifo_layers fl
                ON fl.variant_id=b.variant_id
               AND fl.warehouse_id=b.warehouse_id
             WHERE b.variant_id=%s AND b.warehouse_id=%s
             GROUP BY b.on_hand_quantity
        """, [reversal_variant, reversal_wh])[0]
        chk("outbound reversal restores quantity and original FIFO value",
            restored_balance == (Decimal("5"), Decimal("200"))
            and Decimal(str(reversal["total_cost_base"])) == Decimal("80"))
        chk("movement can be reversed only once",
            rejected(schema, """
                SELECT quantity_reverse_stock_movement(%s,%s,%s,1)
            """, [
                reversible_sale["movement_id"], date(2026, 7, 21), 93,
            ]))
        chk("a reversal movement cannot itself be reversed",
            rejected(schema, """
                SELECT quantity_reverse_stock_movement(%s,%s,%s,1)
            """, [
                reversal["movement_id"], date(2026, 7, 21), 94,
            ]))

        concurrency_variant, concurrency_wh = setup_scope(schema, "CONCURRENT")
        post(
            schema, "purchase", concurrency_variant, concurrency_wh,
            date(2026, 7, 19), "10", "75", 100,
        )
        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(
                concurrent_outbound,
                [
                    (schema, concurrency_variant, concurrency_wh, 1000 + i)
                    for i in range(20)
                ],
            ))
        chk("concurrent near-zero consumption allows exact availability",
            outcomes.count("posted") == 10
            and outcomes.count("rejected") == 10, outcomes)
        chk("concurrent consumption never creates negative stock",
            str(q(schema, """
                SELECT on_hand_quantity FROM stock_balances
                 WHERE variant_id=%s AND warehouse_id=%s
            """, [concurrency_variant, concurrency_wh])[0][0]) == "0")

        pairs_a = [
            {"warehouse_id": warehouse_id, "variant_id": variant_id},
            {"warehouse_id": other_warehouse, "variant_id": variant_id},
        ]
        pairs_b = list(reversed(pairs_a))
        with ThreadPoolExecutor(max_workers=2) as pool:
            locks = list(pool.map(lock_pairs, [
                (schema, pairs_a), (schema, pairs_b),
            ]))
        chk("reversed multi-scope requests use canonical deadlock-free locks",
            locks == [True, True], locks)

        reconciliation = q(schema, """
            SELECT movement_quantity, balance_quantity, fifo_quantity,
                   is_reconciled
              FROM quantity_inventory_reconciliation()
        """)
        chk("all movement, balance, and FIFO quantities reconcile",
            bool(reconciliation)
            and all(row[0] == row[1] == row[2] and row[3]
                    for row in reconciliation), reconciliation)
        chk("allocation quantity equals every outbound movement",
            q(schema, """
                SELECT count(*) FROM stock_movements sm
                 WHERE sm.quantity_out > 0
                   AND sm.quantity_out <> COALESCE((
                       SELECT sum(fa.quantity) FROM fifo_allocations fa
                        WHERE fa.outbound_movement_id=sm.movement_id
                   ), 0)
            """)[0][0] == 0)
        chk("FIFO remaining equals stock balance in every scope",
            q(schema, """
                SELECT count(*) FROM quantity_inventory_reconciliation()
                 WHERE NOT is_reconciled
            """)[0][0] == 0)
        chk("outbound allocation retains inbound source lineage",
            q(schema, """
                SELECT fl.source_type, fl.source_id
                  FROM fifo_allocations fa
                  JOIN fifo_layers fl ON fl.layer_id=fa.layer_id
                 WHERE fa.outbound_movement_id=%s
                 ORDER BY fa.allocation_order LIMIT 1
            """, [outbound_id])[0] == ("phase9_test", 1))

        tenant_b_variant, tenant_b_wh = setup_scope(schema_b, "A")
        post(
            schema_b, "purchase", tenant_b_variant, tenant_b_wh,
            date(2026, 7, 1), "50", "5", 1,
        )
        chk("same source IDs and SKU remain tenant-isolated",
            str(q(schema_b, """
                SELECT quantity_stock_availability(%s,%s,NULL)
            """, [tenant_b_variant, tenant_b_wh])[0][0]) == "50")
        chk("tenant B cannot see tenant A movements",
            q(schema_b, "SELECT count(*) FROM stock_movements")[0][0] == 1)
        chk("request/operation search path resets to public",
            q("public", "SELECT current_schema()")[0][0] == "public")
    finally:
        drop_company(company_b)
        drop_company(company)

    passed = sum(ok for _name, ok, _detail in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}: {name}"
              f"{' — ' + detail if detail and not ok else ''}")
    print(f"\nQuantity FIFO: {passed}/{len(RESULTS)} passed")
    if passed != len(RESULTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
