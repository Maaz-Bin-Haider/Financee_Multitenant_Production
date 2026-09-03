#!/usr/bin/env python3
"""3A migration/column-independence proof on a uniquely disposable stack only."""
from __future__ import annotations

import importlib
import io
import json
import os
from pathlib import Path
import sys
import time

if os.environ.get("PHASE3A_TEST_DISPOSABLE") != "1":
    raise SystemExit("Use the compatibility disposable-stack gate; never production.")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django
django.setup()

import psycopg2
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client
from django.test.utils import CaptureQueriesContext
from tenancy.admin import CompanyAdminForm
from tenancy.models import Company, Membership
from tenancy.schema_verification import verify_company_schema
from tenancy.management.commands.serial_only_phase3_audit import digest
from tenancy.management.commands.serial_only_phase0_audit import _schema_structure

MIGRATION = importlib.import_module("tenancy.migrations.0009_inventory_mode_compatibility")
OLD = [("tenancy", "0008_serial_only_company_creation")]
NEW = [("tenancy", "0009_inventory_mode_compatibility")]
RESULTS = []


def check(name, ok):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}", flush=True)


def sql(statement, params=None):
    with connection.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.fetchall() if cursor.description else []


def snapshot():
    data = []
    for table in ("tenancy_company", "tenancy_currency", "auth_permission",
                  "auth_user_user_permissions", "auth_group_permissions",
                  "tenancy_membership"):
        data.append(sql(f'SELECT to_jsonb(t) FROM public."{table}" t ORDER BY to_jsonb(t)::text'))
    return digest(data)


def constraint():
    return sql("""SELECT oid, pg_get_constraintdef(oid), convalidated FROM pg_constraint
                  WHERE conrelid='public.tenancy_company'::regclass
                    AND conname='tenancy_company_valid_inventory_mode'""")


def default():
    return sql("""SELECT column_default FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='tenancy_company'
                    AND column_name='inventory_mode'""")


def call_migration(function):
    with connection.schema_editor() as editor:
        function(None, editor)


def main():
    baseline = snapshot()
    original_constraint = constraint()
    check("physical legacy column has exact serial database default",
          default() == [("'serial'::character varying",)])
    try:
        Company._meta.get_field("inventory_mode")
        check("Company has no concrete inventory-mode field", False)
    except FieldDoesNotExist:
        check("Company has no concrete inventory-mode field", True)
    state = MigrationExecutor(connection).loader.project_state(NEW).apps.get_model("tenancy", "Company")
    check("migration state omits only legacy field/constraint",
          "inventory_mode" not in {f.name for f in state._meta.fields}
          and {c.name for c in state._meta.constraints} == {
              "tenancy_company_valid_tax_environment", "tenancy_company_valid_provisioning_state"})
    with connection.cursor() as cursor:
        structures = {c.schema_name: _schema_structure(cursor, c.schema_name)
                      for c in Company.objects.exclude(schema_name="")}
    # Exercise the real migration executor in both directions. No fake migration.
    with transaction.atomic():
        MigrationExecutor(connection).migrate(OLD)
        check("reverse restores old state and removes only the added default", default() == [(None,)])
        old_model = MigrationExecutor(connection).loader.project_state(OLD).apps.get_model("tenancy", "Company")
        check("historical ORM still reads all retained serial rows",
              old_model.objects.count() == Company.objects.count()
              and not old_model.objects.exclude(inventory_mode="serial").exists())
        before_output = io.StringIO()
        call_command("production_foundation_audit", serial_only=True, stdout=before_output)
        check("candidate pre-deploy continuity audit works before expansion",
              json.loads(before_output.getvalue())["ok"] and default() == [(None,)])
        MigrationExecutor(connection).migrate(NEW)
        check("forward keeps original constraint identity and all metadata values",
              constraint() == original_constraint and snapshot() == baseline)
        with connection.cursor() as cursor:
            check("forward/reverse leave every serial schema structure unchanged",
                  all(_schema_structure(cursor, name) == value for name, value in structures.items()))
        transaction.set_rollback(True)

    negative_sql = {
        "missing constraint": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode",
        "wrong constraint kind": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode; ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode UNIQUE (id)",
        "unvalidated constraint": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode; ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode CHECK (inventory_mode='serial') NOT VALID",
        "weakened constraint": "ALTER TABLE public.tenancy_company DROP CONSTRAINT tenancy_company_valid_inventory_mode; ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode CHECK (inventory_mode IN ('serial','quantity'))",
        "nullable column": "ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode DROP NOT NULL",
        "different column type": "ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode TYPE varchar(32)",
        "unexpected default": "ALTER TABLE public.tenancy_company ALTER COLUMN inventory_mode SET DEFAULT 'quantity'",
    }
    for name, statement in negative_sql.items():
        blocked = False
        with transaction.atomic():
            call_migration(MIGRATION.backwards)
            sql(statement)
            try:
                call_migration(MIGRATION.forwards)
            except RuntimeError as exc:
                blocked = str(exc).startswith("3A blocked:")
            transaction.set_rollback(True)
        check(f"migration fails closed on {name}, without persistent changes",
              blocked and snapshot() == baseline and constraint() == original_constraint
              and default() == [("'serial'::character varying",)])

    blocker = psycopg2.connect(**connection.get_connection_params())
    try:
        with blocker.cursor() as cursor:
            cursor.execute("LOCK TABLE public.tenancy_company IN ACCESS SHARE MODE")
        started = time.monotonic()
        blocked = False
        try:
            call_migration(MIGRATION.forwards)
        except DatabaseError as exc:
            blocked = getattr(exc.__cause__, "pgcode", None) == "55P03"
        check("busy production-style registry lock times out within a bounded wait",
              blocked and 1.5 <= time.monotonic() - started < 8)
    finally:
        blocker.rollback()
        blocker.close()

    for value in ("quantity", "unknown", "", None):
        for path in ("save", "bulk_create"):
            candidate = Company(name=f"Phase3A rejected {time.time_ns()}", inventory_mode=value)
            rejected = False
            try:
                if path == "save":
                    candidate.save()
                else:
                    Company.objects.bulk_create([candidate])
            except ValidationError:
                rejected = True
            check(f"{path} rejects explicit legacy mode {value!r} without inserting",
                  rejected and not Company.objects.filter(name=candidate.name).exists())

    # SQL references to the physical column must not occur on the application
    # path. All fixture rows/schema/DDL in this block are rolled back together.
    with transaction.atomic():
        sql("ALTER TABLE public.tenancy_company DROP COLUMN inventory_mode")
        tag = str(time.time_ns())
        with CaptureQueriesContext(connection) as queries:
            company = Company.objects.create(name=f"Phase3A no column {tag}")
            company.refresh_from_db()
            company.full_clean()
            verification = verify_company_schema(company, use_cache=False)
            check("new company provisions serial v6 without physical legacy column",
                  company.provisioning_state == "ready" and verification.ok and verification.family == "serial")
            check("legacy serial label remains unchanged without an ORM field",
                  company.inventory_mode == "serial" and company.get_inventory_mode_display() == "Serial-number based")
            form = CompanyAdminForm(instance=company)
            check("company administration and shared setup remain available",
                  "inventory_mode" not in form.fields and "base_currency" in form.fields
                  and "tax_environment" in form.fields)
            user = get_user_model().objects.create_superuser(
                username=f"phase3a_{tag}", email="phase3a@example.com", password="test-only")
            Membership.objects.create(user=user, company=company)
            client = Client(HTTP_HOST="localhost")
            client.force_login(user)
            for path in ("/", "/purchase/purchasing/", "/sale/sales/", "/items/items-dash/", "/admin/tenancy/company/"):
                response = client.get(path, follow=True)
                check(f"authenticated serial page works without column: {path}",
                      response.status_code == 200 and response.wsgi_request.user.is_authenticated
                      and not any("/authentication/login/" in location for location, _ in response.redirect_chain))
            company.disabled_features = ["stock_reports"]
            company.save(update_fields=["disabled_features"])
            company.refresh_from_db()
            check("shared feature settings still persist without legacy column",
                  not company.feature_enabled("stock_reports") and company.feature_enabled("sales_reports"))
            call_command("apply_sql_all_tenants", "tenancy/sql/tenant_indexes.sql", dry_run=True, stdout=io.StringIO())
            call_command("release_preflight", stdout=io.StringIO())
            call_command("production_foundation_audit", stdout=io.StringIO())
        check("application reads/writes and operational commands emit no legacy-column SQL",
              not any("inventory_mode" in query["sql"] for query in queries.captured_queries))
        # This audit intentionally detects an optional legacy column, unlike
        # the application paths above; absence must not prevent continuity.
        output = io.StringIO()
        call_command("serial_only_phase0_audit", include_continuity=True, stdout=output)
        report = json.loads(output.getvalue())
        check("continuity inventory remains available after future contraction",
              not report["non_serial_companies"] and not report["missing_schemas"]
              and not report["unbalanced_schemas"] and not report["continuity_missing_schemas"])
        transaction.set_rollback(True)
    check("destructive rehearsal rolls back column, constraints and all fixture rows",
          snapshot() == baseline and constraint() == original_constraint
          and default() == [("'serial'::character varying",)])
    print(f"{sum(ok for _, ok in RESULTS)}/{len(RESULTS)} Phase 3A compatibility checks passed")
    return 0 if all(ok for _, ok in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
