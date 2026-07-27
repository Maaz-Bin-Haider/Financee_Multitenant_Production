#!/usr/bin/env python3
"""Phase 26 T7 benchmark: disposable 100k-SKU/5m-movement tenant."""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django  # noqa: E402
django.setup()

import psycopg2  # noqa: E402
from django.db import connection  # noqa: E402
from tenancy.models import Company, Currency, INVENTORY_MODE_QUANTITY, PROVISIONING_READY  # noqa: E402

PROFILES = {
    "smoke": {"skus": 1_000, "movements": 20_000, "sessions": 20},
    "target": {"skus": 100_000, "movements": 5_000_000, "sessions": 100},
}
DSN = {key: os.environ.get(env, default) for key, env, default in (
    ("dbname", "DB_NAME", "financee"), ("user", "DB_USER", "postgres"),
    ("password", "DB_PASSWORD", ""), ("host", "DB_HOST", "localhost"),
    ("port", "DB_PORT", "5432"),
)}


def scalar(cur, sql, params=None):
    if params is None:
        cur.execute(sql)
    else:
        cur.execute(sql, params)
    return cur.fetchone()[0]


def pct(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(len(values) * fraction) - 1)]


def timed(cur, name, sql, params=None):
    started = time.perf_counter()
    value = scalar(cur, sql, params)
    return {"name": name, "seconds": round(time.perf_counter() - started, 4),
            "result_bytes": len(str(value).encode())}


def timed_export(cur):
    output = io.StringIO()
    started = time.perf_counter()
    cur.cursor.copy_expert("""COPY (
        SELECT v.sku,p.product_name,w.warehouse_code,b.on_hand_quantity
          FROM product_variants v
          JOIN products p USING(product_id)
          JOIN stock_balances b USING(variant_id)
          JOIN warehouses w USING(warehouse_id)
         ORDER BY v.normalized_sku
    ) TO STDOUT WITH (FORMAT CSV, HEADER true)""", output)
    seconds = time.perf_counter() - started
    return {
        "name": "100k_sku_csv_export",
        "seconds": round(seconds, 4),
        "bytes": output.tell(),
        "rows": output.getvalue().count("\n") - 1,
        "mode": "streamed_postgresql_csv",
    }


def telemetry(cur):
    cur.execute("""SELECT numbackends,xact_commit,blks_read,blks_hit,temp_files,
                          temp_bytes,deadlocks
                     FROM pg_stat_database WHERE datname=current_database()""")
    row = cur.fetchone()
    cur.execute("""SELECT count(*) FILTER (WHERE granted),
                          count(*) FILTER (WHERE NOT granted) FROM pg_locks""")
    locks = cur.fetchone()
    return {
        "load_average": list(os.getloadavg()),
        "database_bytes": scalar(cur, "SELECT pg_database_size(current_database())"),
        "connections": row[0], "commits": row[1], "blocks_read": row[2],
        "blocks_hit": row[3], "temp_files": row[4], "temp_bytes": row[5],
        "deadlocks": row[6], "locks_granted": locks[0],
        "locks_waiting": locks[1],
    }


def create_company(profile):
    company = Company.objects.create(
        name=f"PHASE26 T7 {profile} {time.time_ns()}",
        inventory_mode=INVENTORY_MODE_QUANTITY,
        base_currency=Currency.objects.get(pk="PKR"),
        tax_environment="non_tax",
    )
    company.refresh_from_db()
    if company.provisioning_state != PROVISIONING_READY:
        raise RuntimeError(company.provisioning_error_code)
    return company


def seed(cur, skus, movements):
    if movements % skus:
        raise ValueError("movements must divide evenly by SKUs")
    per_sku = movements // skus
    base_per_sku = per_sku if per_sku % 2 else per_sku - 1
    hot_extra = movements - (base_per_sku * skus)
    warehouse = scalar(cur, """INSERT INTO warehouses(
        warehouse_code,warehouse_name,is_default)
        VALUES('T7MAIN','T7 Main Warehouse',true) RETURNING warehouse_id""")
    scalar(cur, """INSERT INTO warehouses(warehouse_code,warehouse_name)
                   VALUES('T7ALT','T7 Alternate Warehouse')
                   RETURNING warehouse_id""")
    unit = scalar(cur, "SELECT unit_id FROM units_of_measure WHERE code='KG'")
    cur.execute("""INSERT INTO products(product_name,category)
                   SELECT 'T7 Product '||g,'Capacity'
                     FROM generate_series(1,%s) g""", [skus])
    cur.execute("""INSERT INTO product_variants(
        product_id,sku,brand,model,color,storage,ram,region,condition,unit_id)
        SELECT product_id,'T7-'||product_id,'Financee',product_id::text,
               'Standard','NA','NA','Global','New',%s
          FROM products WHERE category='Capacity'""", [unit])
    first_variant = scalar(
        cur, "SELECT min(variant_id) FROM product_variants WHERE sku LIKE 'T7-%'"
    )
    scalar(cur, "SELECT set_config('financee.inventory_engine','allowed',false)")
    cur.execute("""INSERT INTO stock_movements(
        variant_id,warehouse_id,movement_date,effective_sequence,movement_type,
        quantity_in,quantity_out,source_type,source_id,source_line_id,
        document_number,unit_cost_base,total_cost_base)
        SELECT v.variant_id,%s,DATE '2025-01-01'+((n-1)%%365),
               nextval('inventory_effective_sequence_seq'),
               CASE WHEN n%%2=1 THEN 'adjustment_in' ELSE 'adjustment_out' END,
               CASE WHEN n%%2=1 THEN 1 ELSE 0 END,
               CASE WHEN n%%2=0 THEN 1 ELSE 0 END,
               't7_seed',v.variant_id,n,'T7-'||v.variant_id,10,10
          FROM product_variants v CROSS JOIN generate_series(1,%s) n
         WHERE v.sku LIKE 'T7-%%'""", [warehouse, base_per_sku])
    if hot_extra:
        first_hot = min(hot_extra, 9_951)  # 49 base + 9,951 = replay limit 10k.
        cur.execute("""INSERT INTO stock_movements(
            variant_id,warehouse_id,movement_date,effective_sequence,movement_type,
            quantity_in,quantity_out,source_type,source_id,source_line_id,
            document_number,unit_cost_base,total_cost_base)
            SELECT %s,%s,DATE '2024-01-01'+(((n-1)/2)%%365),
                   nextval('inventory_effective_sequence_seq'),
                   CASE WHEN n%%2=1 THEN 'adjustment_in' ELSE 'adjustment_out' END,
                   CASE WHEN n%%2=1 THEN 1 ELSE 0 END,
                   CASE WHEN n%%2=0 THEN 1 ELSE 0 END,
                   't7_hot',%s,n,'T7-HOT',10,10
              FROM generate_series(1,%s) n""",
                    [first_variant, warehouse, first_variant, first_hot])
        remaining_hot = hot_extra - first_hot
        if remaining_hot:
            cur.execute("""WITH events AS (
                SELECT n, %s+1+((n-1)%%10) AS variant_id,
                       1+((n-1)/10) AS local_n
                  FROM generate_series(1,%s) n
            )
            INSERT INTO stock_movements(
                variant_id,warehouse_id,movement_date,effective_sequence,
                movement_type,quantity_in,quantity_out,source_type,source_id,
                source_line_id,document_number,unit_cost_base,total_cost_base)
            SELECT variant_id,%s,DATE '2024-01-01'+(((local_n-1)/2)%%365),
                   nextval('inventory_effective_sequence_seq'),
                   CASE WHEN local_n%%2=1
                        THEN 'adjustment_in' ELSE 'adjustment_out' END,
                   CASE WHEN local_n%%2=1 THEN 1 ELSE 0 END,
                   CASE WHEN local_n%%2=0 THEN 1 ELSE 0 END,
                   't7_hot',variant_id,n,'T7-HOT-'||variant_id,10,10
              FROM events""",
                        [first_variant, remaining_hot, warehouse])
    cur.execute("""INSERT INTO stock_balances(
        variant_id,warehouse_id,on_hand_quantity)
        SELECT variant_id,%s,1 FROM product_variants WHERE sku LIKE 'T7-%%'""",
                [warehouse])
    cur.execute("""INSERT INTO fifo_layers(
        inbound_movement_id,variant_id,warehouse_id,source_type,source_id,
        source_line_id,source_date,effective_sequence,original_quantity,
        remaining_quantity,unit_cost_base)
        SELECT DISTINCT ON (variant_id) movement_id,variant_id,warehouse_id,
               source_type,source_id,source_line_id,movement_date,
               effective_sequence,1,1,10
          FROM stock_movements WHERE source_type='t7_seed' AND quantity_in>0
         ORDER BY variant_id,effective_sequence DESC""")
    for table in ("products", "product_variants", "stock_movements",
                  "stock_balances", "fifo_layers"):
        cur.execute(f"ANALYZE {table}")
    return warehouse, first_variant


def daily_workload(cur, warehouse, first_variant):
    durations = []
    workload_variant = first_variant + 20
    for number in range(100):
        payload = json.dumps({
            "idempotency_key": f"T7-P-{number}", "invoice_date": str(date.today()),
            "vendor_name": f"T7 Vendor {number % 10}", "purchase_type": "credit",
            "items": [{"variant_id": workload_variant + number,
                       "warehouse_id": warehouse, "quantity": "1",
                       "unit_cost_base": "10"}],
        })
        started = time.perf_counter()
        scalar(cur, "SELECT quantity_create_purchase(%s::jsonb)", [payload])
        durations.append(time.perf_counter() - started)
    for number in range(40):
        started = time.perf_counter()
        scalar(cur, "SELECT quantity_stock_availability(%s,%s,NULL)",
               [workload_variant + number, warehouse])
        durations.append(time.perf_counter() - started)
    return {"operations": 140, "seconds": round(sum(durations), 4),
            "p95_seconds": round(pct(durations, .95), 4)}


def concurrent_sessions(schema, warehouse, first_variant, count):
    barrier = threading.Barrier(count)

    def worker(index):
        conn = psycopg2.connect(**DSN)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f'SET search_path TO "{schema}", public')
                barrier.wait(timeout=30)
                started = time.perf_counter()
                cur.execute("""SELECT pg_sleep(0.25),
                    quantity_stock_availability(%s,%s,NULL)""",
                            [first_variant + index, warehouse])
                cur.fetchone()
                return time.perf_counter() - started
        finally:
            conn.close()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=count) as pool:
        durations = [future.result() for future in as_completed(
            [pool.submit(worker, index) for index in range(count)]
        )]
    return {"sessions": count, "failures": 0,
            "wall_seconds": round(time.perf_counter() - started, 4),
            "p50_seconds": round(statistics.median(durations), 4),
            "p95_seconds": round(pct(durations, .95), 4),
            "p99_seconds": round(pct(durations, .99), 4)}


def run(args):
    cfg = PROFILES[args.profile]
    company = create_company(args.profile)
    quoted = connection.ops.quote_name(company.schema_name)
    result = {"profile": args.profile, "targets": cfg,
              "schema": company.schema_name, "passed": False}
    try:
        with connection.cursor() as cur:
            cur.execute(f"SET search_path TO {quoted}, public")
            result["telemetry_before"] = telemetry(cur)
            started = time.perf_counter()
            warehouse, first_variant = seed(cur, cfg["skus"], cfg["movements"])
            result["seed_seconds"] = round(time.perf_counter() - started, 4)
            result["counts"] = {
                "skus": scalar(cur, """SELECT count(*) FROM product_variants
                                       WHERE sku LIKE 'T7-%'"""),
                "movements": scalar(cur, "SELECT count(*) FROM stock_movements"),
                "physical_units": str(
                    scalar(cur, "SELECT sum(on_hand_quantity) FROM stock_balances")),
            }
            filters = json.dumps({"limit": 100})
            result["normal_reports"] = [
                timed(cur, key, "SELECT quantity_run_report(%s,%s::jsonb)",
                      [key, filters])
                for key in ("trial_balance", "stock_summary", "stock_valuation",
                            "stock_movement", "inventory_reconciliation",
                            "valuation_reconciliation", "low_stock")
            ]
            result["heavy_export"] = timed_export(cur)
            started = time.perf_counter()
            scalar(cur, "SELECT quantity_replay_inventory(%s,%s)",
                   [first_variant, warehouse])
            result["backdated_fifo_replay_seconds"] = round(
                time.perf_counter() - started, 4)
            result["daily_workload"] = daily_workload(
                cur, warehouse, first_variant)
            result["telemetry_after_serial_work"] = telemetry(cur)
        result["concurrency"] = concurrent_sessions(
            company.schema_name, warehouse, first_variant, cfg["sessions"])
        with connection.cursor() as cur:
            cur.execute(f"SET search_path TO {quoted}, public")
            after = telemetry(cur)
            result["telemetry_after"] = after
            result["invariants"] = {
                "movement_count_at_least_target":
                    scalar(cur, "SELECT count(*) FROM stock_movements")
                    >= cfg["movements"],
                "sku_count": scalar(cur, """SELECT count(*) FROM product_variants
                                            WHERE sku LIKE 'T7-%'""") == cfg["skus"],
                "physical_units_at_least_target":
                    scalar(cur, "SELECT sum(on_hand_quantity) FROM stock_balances")
                    >= cfg["skus"],
                "trial_balance_exact": scalar(
                    cur, "SELECT COALESCE(sum(debit-credit),0) FROM journal_lines") == 0,
                "negative_stock_absent": scalar(
                    cur, "SELECT count(*) FROM stock_balances "
                         "WHERE on_hand_quantity<0") == 0,
                "waiting_locks_absent": after["locks_waiting"] == 0,
                "deadlocks_unchanged":
                    after["deadlocks"] == result["telemetry_before"]["deadlocks"],
            }
        limit = 3 if args.profile == "target" else 10
        result["passed"] = (
            all(result["invariants"].values())
            and result["concurrency"]["failures"] == 0
            and all(report["seconds"] < limit
                    for report in result["normal_reports"])
        )
        return result
    finally:
        with connection.cursor() as cur:
            cur.execute("SET search_path TO public")
            if not args.keep:
                cur.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
        if not args.keep:
            Company.objects.filter(pk=company.pk).delete()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES, default="smoke")
    parser.add_argument("--confirm-target", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.profile == "target" and not args.confirm_target:
        parser.error("target profile requires --confirm-target")
    result = run(args)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    print(rendered)
    if args.output:
        Path(args.output).write_text(rendered + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
