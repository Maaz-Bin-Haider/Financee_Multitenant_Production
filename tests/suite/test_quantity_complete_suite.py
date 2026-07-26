#!/usr/bin/env python3
"""Phase 23 two-tenant quantity lifecycle and release certification."""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402

from tenancy.models import (  # noqa: E402
    Company, Currency, INVENTORY_MODE_QUANTITY, PROVISIONING_READY,
)
from tenancy.report_catalog import QUANTITY_REPORTS  # noqa: E402
from tenancy.schema_families import schema_family  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402

TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}"
RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def q(schema, sql, params=None):
    quoted = connection.ops.quote_name(schema)
    with connection.cursor() as cursor:
        cursor.execute(f"SET search_path TO {quoted}, public")
        try:
            cursor.execute(sql, params or [])
            return cursor.fetchall() if cursor.description else []
        finally:
            cursor.execute("SET search_path TO public")


def js(value):
    return json.loads(value) if isinstance(value, str) else value


def call(schema, function, payload):
    return js(q(
        schema, f"SELECT {function}(%s::jsonb)", [json.dumps(payload)]
    )[0][0])


def rejected(schema, sql, params=None):
    try:
        with transaction.atomic():
            q(schema, sql, params)
        return False
    except DatabaseError:
        return True


def drop(company):
    if not company:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            f"DROP SCHEMA IF EXISTS "
            f"{connection.ops.quote_name(company.schema_name)} CASCADE"
        )
        cursor.execute("SET search_path TO public")
    Company.objects.filter(pk=company.pk).delete()


def setup_master(schema, suffix):
    product = q(schema, "SELECT quantity_create_product(%s::jsonb)", [
        json.dumps({
            "product_name": f"Certification Product {suffix}",
            "category": "Phase 23", "user_id": 1,
        })
    ])[0][0]
    unit = q(
        schema, "SELECT unit_id FROM units_of_measure WHERE code='PCS'"
    )[0][0]
    variant = q(schema, "SELECT quantity_create_variant(%s::jsonb)", [
        json.dumps({
            "product_id": product, "sku": f"CERT-{suffix}", "brand": "Financee",
            "model": suffix, "color": "Black", "storage": "256GB", "ram": "8GB",
            "region": "Global", "condition": "New", "unit_id": unit, "user_id": 1,
        })
    ])[0][0]
    source = q(schema, "SELECT quantity_create_warehouse(%s::jsonb)", [
        json.dumps({
            "warehouse_code": f"S{suffix}", "warehouse_name": f"Source {suffix}",
            "user_id": 1,
        })
    ])[0][0]
    destination = q(schema, "SELECT quantity_create_warehouse(%s::jsonb)", [
        json.dumps({
            "warehouse_code": f"D{suffix}",
            "warehouse_name": f"Destination {suffix}", "user_id": 1,
        })
    ])[0][0]
    return variant, source, destination


def lifecycle(company, suffix):
    schema = company.schema_name
    variant, source, destination = setup_master(schema, suffix)
    purchase = call(schema, "quantity_create_purchase", {
        "idempotency_key": f"{suffix}-purchase", "invoice_date": "2026-01-02",
        "vendor_name": f"Vendor {suffix}", "purchase_type": "credit",
        "created_by_id": 1, "items": [{
            "variant_id": variant, "warehouse_id": source,
            "quantity": "10", "unit_cost_base": "100",
        }],
    })
    purchase_line = q(
        schema, "SELECT purchase_line_id FROM purchase_lines "
        "WHERE purchase_invoice_id=%s", [purchase["purchase_invoice_id"]]
    )[0][0]
    sale = call(schema, "quantity_create_sale", {
        "idempotency_key": f"{suffix}-sale", "invoice_date": "2026-01-05",
        "customer_name": f"Customer {suffix}", "sale_type": "credit",
        "created_by_id": 1, "items": [{
            "variant_id": variant, "warehouse_id": source,
            "quantity": "4", "unit_price_base": "160",
        }],
    })
    sale_line = q(
        schema, "SELECT sale_line_id FROM sale_lines WHERE sale_invoice_id=%s",
        [sale["sale_invoice_id"]],
    )[0][0]
    sale_return = call(schema, "quantity_create_sale_return", {
        "idempotency_key": f"{suffix}-sale-return", "return_date": "2026-01-06",
        "customer_name": f"Customer {suffix}", "created_by_id": 1,
        "items": [{
            "source_sale_line_id": sale_line,
            "destination_warehouse_id": source, "quantity": "1",
        }],
    })
    purchase_return = call(schema, "quantity_create_purchase_return", {
        "idempotency_key": f"{suffix}-purchase-return",
        "return_date": "2026-01-07", "vendor_name": f"Vendor {suffix}",
        "created_by_id": 1, "items": [{
            "source_purchase_line_id": purchase_line, "quantity": "2",
        }],
    })
    transfer = call(schema, "quantity_create_transfer", {
        "idempotency_key": f"{suffix}-transfer", "transfer_date": "2026-01-08",
        "source_warehouse_id": source, "destination_warehouse_id": destination,
        "created_by_id": 1,
        "items": [{"variant_id": variant, "quantity": "1"}],
    })
    count = call(schema, "quantity_create_physical_count", {
        "idempotency_key": f"{suffix}-count", "count_date": "2026-01-09",
        "cutoff_date": "2026-01-09", "warehouse_id": destination,
        "created_by_id": 1,
        "items": [{
            "variant_id": variant, "counted_quantity": "1",
            "reason": "Phase 23 certification",
        }],
    })
    count_posted = js(q(
        schema, "SELECT quantity_approve_physical_count(%s,1)",
        [count["count_id"]],
    )[0][0])
    call(schema, "add_party_from_json", {
        "party_name": f"Finance Party {suffix}", "party_type": "Both",
        "opening_balance": "200", "balance_type": "Debit", "created_by_id": 1,
    })
    payment = call(schema, "make_payment", {
        "party_name": f"Finance Party {suffix}", "payment_date": "2026-01-10",
        "amount": "25", "method": "Cash", "created_by_id": 1,
    })
    receipt = call(schema, "make_receipt", {
        "party_name": f"Finance Party {suffix}", "receipt_date": "2026-01-11",
        "amount": "50", "method": "Bank", "created_by_id": 1,
    })
    reports_failed = []
    for report in QUANTITY_REPORTS:
        try:
            payload = js(q(
                schema, "SELECT quantity_run_report(%s,%s::jsonb)",
                [report.key, json.dumps({
                    "from": "2026-01-01", "to": "2026-01-31",
                    "variant_id": str(variant),
                })],
            )[0][0])
            if not isinstance(payload.get("rows"), list):
                reports_failed.append(report.key)
        except Exception as exc:
            connection.rollback()
            reports_failed.append(f"{report.key}: {exc}")

    balances = q(schema, """
        SELECT w.warehouse_code,b.on_hand_quantity
        FROM stock_balances b JOIN warehouses w USING(warehouse_id)
        WHERE b.variant_id=%s ORDER BY w.warehouse_code
    """, [variant])
    trial_variance = q(
        schema, "SELECT COALESCE(sum(debit-credit),0) FROM journal_lines"
    )[0][0]
    reconciliation = js(q(
        schema, "SELECT quantity_run_report('inventory_reconciliation','{}')"
    )[0][0])
    quantity_variance = Decimal(str(
        reconciliation["totals"]["quantity_variance"]
    ))
    return {
        "variant": variant, "source": source, "destination": destination,
        "purchase": purchase, "sale": sale, "sale_return": sale_return,
        "purchase_return": purchase_return, "transfer": transfer,
        "count": count_posted, "payment": payment, "receipt": receipt,
        "balances": balances, "trial_variance": trial_variance,
        "quantity_variance": quantity_variance,
        "reports_failed": reports_failed,
    }


def hostile_suite(schema, suffix, state):
    variant, source = state["variant"], state["source"]
    probes = (
        ("empty purchase", "SELECT quantity_create_purchase(%s::jsonb)", [{
            "idempotency_key": f"{suffix}-bad-empty", "invoice_date": "2026-01-12",
            "vendor_name": "Bad", "purchase_type": "credit", "items": [],
        }]),
        ("fractional PCS", "SELECT quantity_create_purchase(%s::jsonb)", [{
            "idempotency_key": f"{suffix}-bad-fraction", "invoice_date": "2026-01-12",
            "vendor_name": "Bad", "purchase_type": "credit", "items": [{
                "variant_id": variant, "warehouse_id": source,
                "quantity": "1.5", "unit_cost_base": "1",
            }],
        }]),
        ("oversell", "SELECT quantity_create_sale(%s::jsonb)", [{
            "idempotency_key": f"{suffix}-bad-oversell", "invoice_date": "2026-01-12",
            "customer_name": "Bad", "sale_type": "credit", "items": [{
                "variant_id": variant, "warehouse_id": source,
                "quantity": "999", "unit_price_base": "1",
            }],
        }]),
        ("same warehouse transfer", "SELECT quantity_create_transfer(%s::jsonb)", [{
            "idempotency_key": f"{suffix}-bad-transfer",
            "transfer_date": "2026-01-12", "source_warehouse_id": source,
            "destination_warehouse_id": source,
            "items": [{"variant_id": variant, "quantity": "1"}],
        }]),
        ("negative count", "SELECT quantity_create_physical_count(%s::jsonb)", [{
            "idempotency_key": f"{suffix}-bad-count", "count_date": "2026-01-12",
            "cutoff_date": "2026-01-12", "warehouse_id": source,
            "items": [{
                "variant_id": variant, "counted_quantity": "-1", "reason": "bad",
            }],
        }]),
    )
    failures = []
    for name, sql, params in probes:
        encoded = [json.dumps(params[0])]
        if not rejected(schema, sql, encoded):
            failures.append(name)
    if not rejected(
        schema, "SELECT quantity_run_report('serial_ledger','{}'::jsonb)"
    ):
        failures.append("serial report")
    if not rejected(
        schema,
        "INSERT INTO stock_movements(variant_id,warehouse_id,movement_date,"
        "effective_sequence,movement_type,quantity_in,source_type,source_id,"
        "source_line_id) VALUES(%s,%s,CURRENT_DATE,999999,'purchase',1,"
        "'hostile',1,1)",
        [variant, source],
    ):
        failures.append("direct stock mutation")
    return failures


def fingerprint(schema):
    definition = schema_family(INVENTORY_MODE_QUANTITY)
    return {
        "tables": tuple(q(schema, """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema=current_schema() AND table_type='BASE TABLE'
            ORDER BY table_name
        """)),
        "required_functions": tuple(q(schema, """
            SELECT routine_name FROM information_schema.routines
            WHERE routine_schema=current_schema() AND routine_name=ANY(%s)
            ORDER BY routine_name
        """, [list(definition.required_functions)])),
        "seed": tuple(q(schema, """
            SELECT seed_key,seed_version FROM quantity_seed_registry
            ORDER BY seed_key
        """)),
        "declared": js(q(schema, "SELECT quantity_schema_fingerprint()")[0][0]),
    }


def upgrade_chain_checks():
    definition = schema_family(INVENTORY_MODE_QUANTITY)
    expected = 2
    transitions = []
    for path in definition.bootstrap_paths:
        text = path.read_text(encoding="utf-8")
        assignments = [
            int(value) for value in re.findall(
                r"(?:(?<![a-z_])version\s*=\s*|"
                r"VALUES\s*\(\s*TRUE\s*,\s*'quantity'\s*,\s*)(\d+)",
                text, re.IGNORECASE,
            )
        ]
        if assignments:
            target = max(assignments)
            if target < expected:
                return False, f"{path.name} regresses {expected} to {target}"
            expected = target
        transitions.append((path.name, expected))
    return expected == definition.required_version, transitions


def traceability_checks():
    evidence = {
        "FR-TEN": "test_quantity_foundation.py",
        "FR-ITEM": "test_quantity_items_variants_units.py",
        "FR-WH": "test_quantity_warehouses.py",
        "FR-INV": "test_quantity_fifo.py",
        "FR-PUR": "test_quantity_purchases.py",
        "FR-SAL": "test_quantity_sales.py",
        "FR-SR": "test_quantity_sale_returns.py",
        "FR-PR": "test_quantity_purchase_returns.py",
        "FR-TRF": "test_quantity_transfers.py",
        "FR-CNT": "test_quantity_counts_adjustments.py",
        "FR-TAX": "test_quantity_tax_discounts.py",
        "FR-CUR": "test_quantity_currency_settlements.py",
        "FR-FIN": "test_quantity_financial_modules.py",
        "REP": "test_quantity_reports_dashboards.py",
        "INT-API": "test_quantity_type_aware_ui.py",
        "TST-FLOW": "test_quantity_complete_suite.py",
    }
    suite = ROOT / "tests/suite"
    return len(evidence) == 16 and all(
        suite.joinpath(test_file).is_file() for test_file in evidence.values()
    )


def main():
    companies = []
    try:
        currency = Currency.objects.get(pk="PKR")
        for suffix in ("A", "B"):
            company = Company.objects.create(
                name=f"PHASE23 QUANTITY {TAG} {suffix}",
                inventory_mode=INVENTORY_MODE_QUANTITY,
                base_currency=currency, tax_environment="non_tax",
            )
            companies.append(company)
        chk("two independent quantity tenants provisioned",
            len({company.schema_name for company in companies}) == 2
            and all(company.provisioning_state == PROVISIONING_READY
                    for company in companies))
        chk("both fresh schemas verify",
            all(verify_company_schema(company, use_cache=False).ok
                for company in companies))

        states = [
            lifecycle(company, suffix)
            for company, suffix in zip(companies, ("A", "B"))
        ]
        for suffix, state in zip(("A", "B"), states):
            chk(f"tenant {suffix} complete lifecycle posts",
                all(state[key]["status"] == "success" for key in (
                    "purchase", "sale", "sale_return", "purchase_return",
                    "transfer", "payment", "receipt",
                )) and state["count"]["status"] == "success", state)
            chk(f"tenant {suffix} inventory quantity is exact",
                sum(row[1] for row in state["balances"]) == Decimal("5"),
                state["balances"])
            chk(f"tenant {suffix} journal remains balanced",
                state["trial_variance"] == 0, state["trial_variance"])
            chk(f"tenant {suffix} inventory reconciles",
                state["quantity_variance"] == 0, state["quantity_variance"])
            chk(f"tenant {suffix} executes every quantity report",
                not state["reports_failed"], state["reports_failed"])
            hostile = hostile_suite(
                companies[0 if suffix == "A" else 1].schema_name, suffix, state
            )
            chk(f"tenant {suffix} hostile inputs rejected", not hostile, hostile)

        chk("tenant business rows and document sequences are isolated",
            q(companies[0].schema_name, "SELECT document_number FROM sale_invoices")
            == [("SAL-000001",)]
            and q(companies[1].schema_name, "SELECT document_number FROM sale_invoices")
            == [("SAL-000001",)]
            and q(companies[0].schema_name, "SELECT sku FROM product_variants")
            == [("CERT-A",)]
            and q(companies[1].schema_name, "SELECT sku FROM product_variants")
            == [("CERT-B",)])

        definition = schema_family(INVENTORY_MODE_QUANTITY)
        call_command(
            "apply_sql_all_tenants",
            str(definition.bootstrap_paths[-1]),
            family=INVENTORY_MODE_QUANTITY, stdout=io.StringIO(),
        )
        call_command(
            "apply_sql_all_tenants",
            str(definition.hardening_path),
            family=INVENTORY_MODE_QUANTITY, stdout=io.StringIO(),
        )
        chk("report upgrade and platform hardening repeat safely",
            all(verify_company_schema(company, use_cache=False).ok
                for company in companies)
            and all(q(
                company.schema_name,
                "SELECT version FROM tenant_schema_metadata WHERE id"
            )[0][0] == definition.required_version for company in companies))
        chain_ok, chain_detail = upgrade_chain_checks()
        chk("every registered quantity release upgrade is monotonic",
            chain_ok, chain_detail)
        chk("all functional P0/P1 families have traceable test evidence",
            traceability_checks())
        fingerprints = [fingerprint(company.schema_name) for company in companies]
        chk("both quantity schemas have identical required fingerprints",
            fingerprints[0] == fingerprints[1])
        chk("no release-blocking XFAIL exists in quantity suite",
            not any(
                re.search(
                    r"\b(?:xfail|known_bug)\s*\(",
                    path.read_text(encoding="utf-8"), re.IGNORECASE,
                )
                for path in (ROOT / "tests/suite").glob("test_quantity_*.py")
            ))
    finally:
        for company in reversed(companies):
            drop(company)

    failed = [result for result in RESULTS if not result[1]]
    for name, ok, detail in RESULTS:
        print(("PASS" if ok else "FAIL") + ":", name,
              "" if ok or not detail else f"— {detail}")
    print(f"{len(RESULTS)-len(failed)}/{len(RESULTS)} Phase 23 checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
