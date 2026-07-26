#!/usr/bin/env python3
"""Phase 5 quantity schema foundation, dispatch, and isolation checks."""

import io
import os
import sys
import time
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.core.cache import cache  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402
from django.db import connection  # noqa: E402
from django.db import DatabaseError, transaction  # noqa: E402
from django.test import Client  # noqa: E402

from tenancy.models import (  # noqa: E402
    INVENTORY_MODE_QUANTITY,
    INVENTORY_MODE_SERIAL,
    PROVISIONING_FAILED,
    PROVISIONING_READY,
    Company,
    Currency,
    Membership,
)
from tenancy.schema_families import family_for_sql_file, schema_family  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402
from tenancy.utils import schema_exists  # noqa: E402

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


def object_fingerprint(schema):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT 'table', table_name
              FROM information_schema.tables WHERE table_schema = %s
            UNION ALL
            SELECT 'sequence', sequence_name
              FROM information_schema.sequences WHERE sequence_schema = %s
            UNION ALL
            SELECT 'function', routine_name
              FROM information_schema.routines WHERE routine_schema = %s
            ORDER BY 1, 2
            """,
            [schema, schema, schema],
        )
        return cur.fetchall()


def drop_test_company(company):
    if company is None:
        return
    schema = company.schema_name
    if schema and schema.startswith("tenant_company_"):
        with connection.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {connection.ops.quote_name(schema)} CASCADE")
            cur.execute("SET search_path TO public")
    Company.objects.filter(pk=company.pk).delete()


def main():
    serial = schema_family(INVENTORY_MODE_SERIAL)
    quantity = schema_family(INVENTORY_MODE_QUANTITY)
    chk("families use separate templates", serial.template_path != quantity.template_path)
    chk("families use separate hardening", serial.hardening_path != quantity.hardening_path)
    chk("quantity required version includes sales",
        quantity.required_version == 8)
    chk("quantity runtime remains gated after foundation",
        quantity.runtime_enabled is False)
    chk("SQL ownership resolves serial hardening",
        family_for_sql_file(str(serial.hardening_path)) == INVENTORY_MODE_SERIAL)
    chk("SQL ownership resolves quantity hardening",
        family_for_sql_file(str(quantity.hardening_path)) == INVENTORY_MODE_QUANTITY)

    currency = Currency.objects.get(pk="PKR")
    companies = []
    failed_company = None
    quantity_user = None
    try:
        for suffix in ("A", "B"):
            company = Company.objects.create(
                name=f"PHASE5 QUANTITY {TAG} {suffix}",
                inventory_mode=INVENTORY_MODE_QUANTITY,
                base_currency=currency,
                tax_environment="non_tax",
            )
            company.refresh_from_db()
            companies.append(company)

        chk("two quantity companies reach ready state",
            all(c.provisioning_state == PROVISIONING_READY for c in companies),
            [(c.schema_name, c.provisioning_state) for c in companies])
        chk("two physical quantity schemas exist",
            all(schema_exists(c.schema_name) for c in companies))

        metadata = [
            q(c.schema_name, """
                SELECT family, version, base_currency_code
                FROM tenant_schema_metadata WHERE id = true
            """)[0]
            for c in companies
        ]
        chk("metadata family/version/currency matches public company",
            all(row == ("quantity", 8, "PKR") for row in metadata), metadata)
        chk("quantity verifier accepts both schemas",
            all(verify_company_schema(c, use_cache=False).ok for c in companies))

        quantity_user = get_user_model().objects.create_user(
            username=f"phase5_quantity_{TAG}",
            password="phase5-test-password",
        )
        Membership.objects.create(user=quantity_user, company=companies[0])
        client = Client(SERVER_NAME="localhost")
        client.force_login(quantity_user)
        response = client.get("/home/")
        chk("quantity business UI remains safely gated after foundation",
            response.status_code == 403, response.status_code)

        fingerprints = [object_fingerprint(c.schema_name) for c in companies]
        chk("two quantity schema fingerprints are identical",
            fingerprints[0] == fingerprints[1], fingerprints)
        names = {name for _kind, name in fingerprints[0]}
        chk("quantity schema has required foundation objects",
            {
                "tenant_schema_metadata", "quantity_seed_registry",
                "document_sequences", "quantity_foundation_id_seq",
                "quantity_schema_fingerprint", "quantity_assert_schema_family",
            }.issubset(names), names)
        chk("quantity schema contains no serial inventory tables",
            not {"purchaseunits", "soldunits", "stockmovements"}.intersection(names),
            names)
        chk("document sequences seeded exactly once",
            all(q(c.schema_name, "SELECT count(*) FROM document_sequences")[0][0] == 11
                for c in companies))
        chk("all eight quantity phase seeds registered exactly once",
            all(q(c.schema_name, """
                SELECT count(*), count(DISTINCT seed_key)
                  FROM quantity_seed_registry
            """)[0] == (8, 8) for c in companies))

        for _ in range(2):
            call_command(
                "apply_sql_all_tenants",
                str(quantity.hardening_path),
                family=INVENTORY_MODE_QUANTITY,
                stdout=io.StringIO(),
            )
        chk("quantity hardening is idempotent",
            all(q(c.schema_name, "SELECT count(*) FROM document_sequences")[0][0] == 11
                for c in companies)
            and all(q(c.schema_name, """
                SELECT count(*), count(DISTINCT seed_key)
                  FROM quantity_seed_registry
            """)[0] == (8, 8) for c in companies))

        serial_output = io.StringIO()
        call_command(
            "apply_sql_all_tenants",
            str(serial.hardening_path),
            family=INVENTORY_MODE_SERIAL,
            dry_run=True,
            stdout=serial_output,
        )
        chk("serial rollout excludes quantity schemas",
            all(c.schema_name not in serial_output.getvalue() for c in companies),
            serial_output.getvalue())

        try:
            call_command(
                "apply_sql_all_tenants",
                str(quantity.hardening_path),
                family=INVENTORY_MODE_SERIAL,
                dry_run=True,
                stdout=io.StringIO(),
            )
            chk("file/family mismatch is rejected", False, "command succeeded")
        except CommandError:
            chk("file/family mismatch is rejected", True)

        serial_company_for_guard = Company.objects.filter(
            inventory_mode=INVENTORY_MODE_SERIAL
        ).first()
        try:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        f"SET LOCAL search_path TO "
                        f"{connection.ops.quote_name(serial_company_for_guard.schema_name)}, public"
                    )
                    cur.execute(quantity.hardening_path.read_text(encoding="utf-8"))
            chk("quantity SQL self-rejects a serial schema", False, "SQL succeeded")
        except DatabaseError:
            chk("quantity SQL self-rejects a serial schema", True)

        # Public quantity record pointed at a serial schema must never activate.
        serial_company = Company.objects.filter(
            inventory_mode=INVENTORY_MODE_SERIAL
        ).first()
        original_mode = serial_company.inventory_mode
        Company.objects.filter(pk=serial_company.pk).update(
            inventory_mode=INVENTORY_MODE_QUANTITY
        )
        serial_company.refresh_from_db()
        mismatch = verify_company_schema(serial_company, use_cache=False)
        chk("public quantity / physical serial mismatch denied",
            not mismatch.ok and mismatch.reason in {
                "metadata_invalid", "metadata_missing", "fingerprint_tables",
            }, mismatch)
        Company.objects.filter(pk=serial_company.pk).update(
            inventory_mode=original_mode
        )

        # Base-currency disagreement is also a safe denial.
        target = companies[0]
        q(target.schema_name,
          "UPDATE tenant_schema_metadata SET base_currency_code = 'USD' WHERE id = true")
        cache.clear()
        mismatch = verify_company_schema(target, use_cache=False)
        chk("quantity base-currency mismatch denied",
            not mismatch.ok and mismatch.reason == "base_currency_mismatch",
            mismatch)
        q(target.schema_name,
          "UPDATE tenant_schema_metadata SET base_currency_code = 'PKR' WHERE id = true")

        with patch("tenancy.provisioning._read_template", side_effect=RuntimeError("secret sql")):
            failed_company = Company.objects.create(
                name=f"PHASE5 FAILED {TAG}",
                inventory_mode=INVENTORY_MODE_QUANTITY,
                base_currency=currency,
                tax_environment="non_tax",
            )
        failed_company.refresh_from_db()
        chk("failed provisioning is inactive with sanitized state",
            failed_company.provisioning_state == PROVISIONING_FAILED
            and failed_company.is_active is False
            and failed_company.provisioning_error_code == "schema_build_failed",
            (
                failed_company.provisioning_state,
                failed_company.is_active,
                failed_company.provisioning_error_code,
            ))
        chk("failed provisioning leaves no physical schema",
            not schema_exists(failed_company.schema_name),
            failed_company.schema_name)
        chk("failure state contains no raw exception or SQL",
            "secret" not in failed_company.provisioning_error_code.lower())

        retry_output = io.StringIO()
        call_command(
            "retry_tenant_provisioning",
            failed_company.pk,
            stdout=retry_output,
        )
        failed_company.refresh_from_db()
        chk("controlled retry provisions failed company",
            failed_company.provisioning_state == PROVISIONING_READY
            and failed_company.is_active
            and schema_exists(failed_company.schema_name)
            and verify_company_schema(failed_company, use_cache=False).ok,
            retry_output.getvalue())
        try:
            call_command(
                "retry_tenant_provisioning",
                failed_company.pk,
                stdout=io.StringIO(),
            )
            chk("ready company cannot be retried", False, "command succeeded")
        except CommandError:
            chk("ready company cannot be retried", True)

        with connection.cursor() as cur:
            cur.execute("SHOW search_path")
            path = cur.fetchone()[0]
        chk("management/test operations restore public search path",
            path.strip() in {"public", '"public"'}, path)
    finally:
        cache.clear()
        if quantity_user is not None:
            quantity_user.delete()
        drop_test_company(failed_company)
        for company in reversed(companies):
            drop_test_company(company)

    print("\n" + "=" * 78)
    passed = sum(1 for _name, ok, _detail in RESULTS if ok)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    print(f"{passed}/{len(RESULTS)} quantity-foundation checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
