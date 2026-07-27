#!/usr/bin/env python3
"""ARM64 startup, migration, provisioning, family and HTTP smoke."""
from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
import django  # noqa: E402
django.setup()

from django.db import connection  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402
from tenancy.models import Company, Currency  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402


def main():
    checks = []
    companies = []
    checks.append(("container architecture is ARM64",
                   platform.machine().lower() in {"aarch64", "arm64"}))
    currency = Currency.objects.get(pk="PKR")
    try:
        for family in ("serial", "quantity"):
            company = Company.objects.create(
                name=f"PHASE27 ARM64 {family} {time.time_ns()}",
                inventory_mode=family, base_currency=currency,
                tax_environment="non_tax",
            )
            companies.append(company)
            company.refresh_from_db()
            verification = verify_company_schema(company, use_cache=False)
            checks.append((f"{family} tenant provisions and verifies", verification.ok))
        response = Client(SERVER_NAME="localhost").get("/authentication/login/")
        checks.append(("HTTP login smoke", response.status_code == 200))
        try:
            call_command(
                "release_preflight",
                require_family=["serial", "quantity"],
                verbosity=0,
            )
            preflight_ok = True
        except Exception as exc:
            print(f"release preflight error: {exc}")
            preflight_ok = False
        checks.append(("mixed-family release preflight", preflight_ok))
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            for company in companies:
                cursor.execute(
                    f"DROP SCHEMA IF EXISTS "
                    f"{connection.ops.quote_name(company.schema_name)} CASCADE"
                )
        Company.objects.filter(pk__in=[c.pk for c in companies]).delete()
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    print(f"{sum(ok for _, ok in checks)}/{len(checks)} ARM64 smoke checks passed")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
