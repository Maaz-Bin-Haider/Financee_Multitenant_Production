#!/usr/bin/env python3
"""Live-stack proof that only the serial runtime is reachable in Phase 2."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402
from django.db import connection  # noqa: E402
from django.http import JsonResponse  # noqa: E402
from django.test import Client, RequestFactory  # noqa: E402
from django.urls import NoReverseMatch, Resolver404, resolve, reverse  # noqa: E402

from tenancy.capabilities import serial_inventory_view  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company,
    Currency,
    INVENTORY_MODE_SERIAL,
    Membership,
    PROVISIONING_READY,
)
from tenancy.schema_families import schema_family  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402


RESULTS = []
TAG = f"{time.strftime('%H%M%S')}_{os.getpid()}_{time.time_ns()}"


def check(name, passed, detail=""):
    RESULTS.append((name, bool(passed), "" if passed else str(detail)))


def drop(company, user):
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
        if company is not None:
            cursor.execute(
                f"DROP SCHEMA IF EXISTS "
                f"{connection.ops.quote_name(company.schema_name)} CASCADE"
            )
    if user is not None:
        user.delete()
    if company is not None:
        Company.objects.filter(pk=company.pk).delete()


def main():
    company = None
    user = None
    try:
        check(
            "registry contains serial companies only",
            not Company.objects.exclude(inventory_mode=INVENTORY_MODE_SERIAL).exists(),
        )
        definition = schema_family("quantity")
        check(
            "historical quantity schema descriptor cannot activate requests",
            not definition.runtime_enabled and definition.enabled_path_prefixes == (),
        )

        retired_modules = (
            "items.quantity_views", "purchase.quantity_views",
            "sale.quantity_views", "purchaseReturn.quantity_views",
            "saleReturn.quantity_views", "tenancy.report_views",
            "tenancy.warehouse_views", "tenancy.transfer_views",
            "tenancy.count_views", "tenancy.audit_views",
        )
        check(
            "retired quantity HTTP modules are not importable",
            all(importlib.util.find_spec(name) is None for name in retired_modules),
        )

        retired_names = (
            "quantity_reports:index", "quantity_warehouses:page",
            "quantity_transfers:page", "quantity_counts:page",
            "quantity_audit:index", "items:quantity_catalog",
            "purchase:quantity_tax_codes", "saleReturn:quantity_sources",
            "purchaseReturn:quantity_sources",
        )
        reverse_failures = 0
        for name in retired_names:
            try:
                reverse(name)
            except NoReverseMatch:
                reverse_failures += 1
        check(
            "all retired quantity URL names are absent",
            reverse_failures == len(retired_names),
            f"{reverse_failures}/{len(retired_names)}",
        )

        retired_paths = (
            "/quantity-reports/", "/quantity-reports/api/trial_balance/",
            "/warehouses/quantity/", "/transfers/", "/physical-counts/",
            "/quantity-audit/", "/items/quantity/catalog/",
            "/purchase/quantity-tax-codes/", "/saleReturn/quantity-sources/",
            "/purchaseReturn/quantity-sources/",
        )
        unresolved = 0
        for path in retired_paths:
            try:
                resolve(path)
            except Resolver404:
                unresolved += 1
        check(
            "all retired quantity paths are unresolved",
            unresolved == len(retired_paths),
            f"{unresolved}/{len(retired_paths)}",
        )

        currency = Currency.objects.get(pk="PKR")
        company = Company.objects.create(
            name=f"PHASE2 SERIAL {TAG}",
            inventory_mode=INVENTORY_MODE_SERIAL,
            base_currency=currency,
            tax_environment="non_tax",
        )
        company.refresh_from_db()
        verification = verify_company_schema(company, use_cache=False)
        check(
            "fresh serial tenant provisions unchanged schema",
            company.provisioning_state == PROVISIONING_READY
            and verification.ok
            and verification.family == INVENTORY_MODE_SERIAL,
            verification,
        )

        User = get_user_model()
        user = User.objects.create_superuser(
            username=f"phase2_{TAG}",
            email=f"phase2-{TAG}@example.com",
            password="phase2-test-only",
        )
        Membership.objects.create(user=user, company=company)
        client = Client(SERVER_NAME="localhost")
        client.force_login(user)

        serial_pages = (
            "/home/", "/items/items-dash/", "/purchase/purchasing/",
            "/sale/sales/", "/saleReturn/create-sale-return/",
            "/purchaseReturn/create-purchase-return/", "/opening-stock/",
            "/accountsReports/trial-balance/", "/sales-reports/",
        )
        page_statuses = {path: client.get(path).status_code for path in serial_pages}
        check(
            "serial pages remain reachable through real middleware",
            all(status == 200 for status in page_statuses.values()),
            page_statuses,
        )
        retired_statuses = {
            path: client.get(path).status_code for path in retired_paths
        }
        check(
            "retired quantity HTTP paths return 404 for an authenticated tenant",
            all(status == 404 for status in retired_statuses.values()),
            retired_statuses,
        )

        request = RequestFactory().post(
            "/purchase/purchasing/",
            data=json.dumps({"items": [{"variant_id": 1}]}),
            content_type="application/json",
        )
        request.tenant_company = SimpleNamespace(inventory_mode="serial")
        called = []

        def target(_request):
            called.append(True)
            return JsonResponse({"ok": True})

        response = serial_inventory_view(request, target)
        check(
            "serial request boundary rejects retired payload identifiers",
            response.status_code == 400 and not called,
        )
        request = RequestFactory().post(
            "/purchase/purchasing/",
            data=json.dumps({"items": [{"serials": ["S-1"]}]}),
            content_type="application/json",
        )
        request.tenant_company = SimpleNamespace(inventory_mode="serial")
        response = serial_inventory_view(request, target)
        check(
            "serial request boundary preserves serial payloads",
            response.status_code == 200 and called == [True],
        )

        try:
            call_command(
                "apply_sql_all_tenants",
                str(ROOT / "tenancy/sql/quantity_platform_controls.sql"),
                dry_run=True,
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
            rollout_blocked = False
        except CommandError as exc:
            rollout_blocked = "Only serial tenant SQL rollout" in str(exc)
        check("quantity SQL rollout is rejected", rollout_blocked)

        call_command(
            "release_preflight",
            require_family=["serial"],
            stdout=io.StringIO(),
        )
        check("serial-only release preflight passes", True)

        with connection.cursor() as cursor:
            cursor.execute(
                f"SET search_path TO {connection.ops.quote_name(company.schema_name)}, public"
            )
            cursor.execute("SELECT COALESCE(sum(debit-credit),0) FROM journallines")
            balanced = cursor.fetchone()[0] == 0
            cursor.execute("SELECT get_trial_balance_json()")
            report_ok = cursor.fetchone()[0] is not None
            cursor.execute("SET search_path TO public")
        check("serial journal and report continuity remain healthy", balanced and report_ok)
    finally:
        drop(company, user)

    failed = [(name, detail) for name, passed, detail in RESULTS if not passed]
    for name, passed, detail in RESULTS:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        if not passed and detail:
            print(f"  {detail}")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} Phase 2 checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
