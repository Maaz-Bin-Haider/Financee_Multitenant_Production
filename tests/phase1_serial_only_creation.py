#!/usr/bin/env python3
"""Phase 1 live-database proof that every company creation path is serial-only."""

from __future__ import annotations

import io
import importlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command, get_commands, load_command_class  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402

from financee.admin_site import financee_admin_site  # noqa: E402
from tenancy.admin import CompanyAdmin, CompanyAdminForm  # noqa: E402
from tenancy.models import Company, PROVISIONING_READY  # noqa: E402
from tenancy.provisioning import provision_schema  # noqa: E402
from tests.serial_api_compat import (  # noqa: E402
    RETIRED_API_PRESENT,
    SERIAL_SCHEMA_FAMILY,
    no_retired_mode_attribute,
    retired_mode_rejected,
)
from tenancy.schema_verification import verify_company_schema  # noqa: E402
from tenancy.utils import schema_exists  # noqa: E402


RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append((name, bool(passed), "" if passed else str(detail)))


def drop_company(company):
    if company is None:
        return
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO public")
        cursor.execute(
            f"DROP SCHEMA IF EXISTS "
            f"{connection.ops.quote_name(company.schema_name)} CASCADE"
        )
    Company.objects.filter(pk=company.pk).delete()


def main():
    created = None
    blocked_schema = f"tenant_company_{time.time_ns()}"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode')")
            legacy_present = cursor.fetchone()[0]
            contracted = False
            if legacy_present:
                cursor.execute("SELECT count(*) FROM public.tenancy_company WHERE inventory_mode IS DISTINCT FROM 'serial'")
                serial_registry = cursor.fetchone()[0] == 0
            else:
                from tenancy.management.commands.serial_only_phase3_cleanup import archive
                stored = archive(cursor)
                contracted = bool(stored and stored["state"] == "applied")
                # Three legitimate states now exist: pre-3B (column present),
                # post-3B (column contracted, archive applied), and a fresh
                # checkpoint 4A install, which never creates the column at all
                # and therefore has no archive to find. With no column there is
                # no value that could express a non-serial company.
                serial_registry = True
            check("production-compatible registry contains serial companies only", serial_registry)
        # The recovery gate runs this module inside the previously published
        # image, which still carries the temporary 3A compatibility API.
        check(
            "model never exposes a concrete inventory-mode field",
            "inventory_mode" not in {f.name for f in Company._meta.get_fields()}
            and (RETIRED_API_PRESENT
                 or not hasattr(Company, "inventory_mode")),
        )
        check(
            "model rejects quantity company",
            retired_mode_rejected(f"PHASE1 BLOCK {time.time_ns()}"),
        )

        company = Company.objects.order_by("pk").first()
        check("serial baseline company exists", company is not None)
        if company is not None:
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE public.tenancy_company SET inventory_mode='quantity' WHERE id=%s", [company.pk])
                check("database rejects quantity registry row", False, "update allowed")
            except DatabaseError as exc:
                company.refresh_from_db()
                check(
                    "database rejects quantity registry row",
                    getattr(exc.__cause__, "pgcode", None)
                    == ("23514" if legacy_present else "42703"),
                    getattr(exc.__cause__, "pgcode", None),
                )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_get_constraintdef(oid)
                  FROM pg_constraint
                 WHERE conname = 'tenancy_company_valid_inventory_mode'
                   AND conrelid = 'public.tenancy_company'::regclass
                """
            )
            row = cursor.fetchone()
        definition = row[0].lower() if row else ""
        check(
            "database has exact serial-only constraint or certified column contraction",
            (bool(row) and "serial" in definition and "quantity" not in definition)
            if legacy_present else row is None,
            f"legacy_present={legacy_present} contracted={contracted} {definition}",
        )

        if company is not None:
            migration = importlib.import_module(
                "tenancy.migrations.0008_serial_only_company_creation"
            )
            precondition_blocked = False
            with transaction.atomic():
                if not legacy_present:
                    # Reconstruct the historical fixture only in this rolled-back
                    # test transaction so 0008's original guard remains covered.
                    with connection.cursor() as cursor:
                        cursor.execute("ALTER TABLE public.tenancy_company ADD COLUMN inventory_mode varchar(16) NOT NULL DEFAULT 'serial'")
                        cursor.execute("ALTER TABLE public.tenancy_company ADD CONSTRAINT tenancy_company_valid_inventory_mode CHECK (inventory_mode='serial')")
                with connection.cursor() as cursor:
                    cursor.execute(
                        "ALTER TABLE tenancy_company DROP CONSTRAINT "
                        "tenancy_company_valid_inventory_mode"
                    )
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE public.tenancy_company SET inventory_mode='quantity' WHERE id=%s", [company.pk])
                try:
                    # Once the checkpoint 4A squash is applied, Django removes
                    # the replaced nodes from the graph, so the historical node
                    # cannot be addressed through the default loader. Load the
                    # real migration files with replacements disabled so 0008's
                    # original guard stays covered on both images.
                    historical_apps = MigrationLoader(
                        connection, replace_migrations=False
                    ).project_state(
                        [("tenancy", "0007_company_provisioning_state")]
                    ).apps
                    migration.require_serial_registry(historical_apps, None)
                except RuntimeError as exc:
                    precondition_blocked = (
                        str(company.pk) in str(exc)
                        and company.name not in str(exc)
                    )
                transaction.set_rollback(True)
            company.refresh_from_db()
            check(
                "migration precondition blocks conflicting IDs without names",
                precondition_blocked,
            )

        admin_obj = CompanyAdmin(Company, financee_admin_site)
        check(
            "admin add/change form has no inventory selector",
            "inventory_mode" not in CompanyAdminForm.base_fields,
        )
        check(
            "admin fieldsets have no inventory selector",
            all(
                "inventory_mode" not in fieldset[1].get("fields", ())
                for fieldset in admin_obj.fieldsets
            ),
        )
        check(
            "admin list and filters have no inventory selector",
            "inventory_mode" not in admin_obj.list_display
            and "inventory_mode" not in admin_obj.list_filter,
        )
        posted = CompanyAdminForm(data={
            "name": f"PHASE1 POST {time.time_ns()}",
            "inventory_mode": "quantity",
            "base_currency": "PKR",
            "tax_environment": "non_tax",
            "is_active": "on",
            "grace_days": "3",
            "warn_days_before": "7",
        })
        check(
            "forged admin quantity field cannot make the instance non-serial",
            posted.is_valid() and no_retired_mode_attribute(posted.instance),
            posted.errors.as_json(),
        )

        app_name = get_commands()["provision_tenant"]
        command = load_command_class(app_name, "provision_tenant")
        parser = command.create_parser("manage.py", "provision_tenant")
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        check(
            "provision_tenant exposes no inventory-mode option",
            "--inventory-mode" not in option_strings,
            sorted(option_strings),
        )

        before_count = Company.objects.count()
        output = io.StringIO()
        call_command(
            "provision_tenant",
            f"PHASE1 SERIAL {time.time_ns()}",
            stdout=output,
        )
        created = Company.objects.order_by("-pk").first()
        check(
            "provision_tenant creates exactly one serial company",
            Company.objects.count() == before_count + 1
            and created is not None,
            output.getvalue(),
        )
        if created is not None:
            created.refresh_from_db()
            verification = verify_company_schema(created, use_cache=False)
            check(
                "new serial company provisions and verifies unchanged schema",
                created.provisioning_state == PROVISIONING_READY
                and schema_exists(created.schema_name)
                and verification.ok
                and verification.family == SERIAL_SCHEMA_FAMILY,
                verification,
            )

        try:
            provision_schema(blocked_schema, family="quantity")
            check("low-level provisioning rejects quantity family", False, "call allowed")
        except ValueError as exc:
            check(
                "low-level provisioning rejects quantity family",
                "only serial" in str(exc).lower() and not schema_exists(blocked_schema),
                str(exc),
            )
    finally:
        drop_company(created)
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            cursor.execute(
                f"DROP SCHEMA IF EXISTS "
                f"{connection.ops.quote_name(blocked_schema)} CASCADE"
            )

    failed = [(name, detail) for name, passed, detail in RESULTS if not passed]
    for name, passed, detail in RESULTS:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        if not passed and detail:
            print(f"  {detail}")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} Phase 1 checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
