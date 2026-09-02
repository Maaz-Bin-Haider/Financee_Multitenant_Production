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

from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command, get_commands, load_command_class  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.apps import apps as django_apps  # noqa: E402

from financee.admin_site import financee_admin_site  # noqa: E402
from tenancy.admin import CompanyAdmin, CompanyAdminForm  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company,
    INVENTORY_MODE_CHOICES,
    INVENTORY_MODE_SERIAL,
    PROVISIONING_READY,
)
from tenancy.provisioning import provision_schema  # noqa: E402
from tenancy.schema_verification import verify_company_schema  # noqa: E402
from tenancy.utils import schema_exists  # noqa: E402


RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append((name, bool(passed), "" if passed else str(detail)))


def validation_text(exc):
    return " ".join(
        message
        for messages in exc.message_dict.values()
        for message in messages
    )


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
        check(
            "production-compatible registry contains serial companies only",
            Company.objects.exclude(inventory_mode=INVENTORY_MODE_SERIAL).count() == 0,
        )
        check(
            "model exposes serial as its only company choice",
            {value for value, _label in INVENTORY_MODE_CHOICES}
            == {INVENTORY_MODE_SERIAL},
        )

        candidate = Company(name=f"PHASE1 BLOCK {time.time_ns()}", inventory_mode="quantity")
        try:
            candidate.full_clean()
            check("model rejects quantity company", False, "validation allowed")
        except ValidationError as exc:
            check(
                "model rejects quantity company",
                "only serial-number based" in validation_text(exc).lower(),
                validation_text(exc),
            )

        company = Company.objects.order_by("pk").first()
        check("serial baseline company exists", company is not None)
        if company is not None:
            try:
                with transaction.atomic():
                    Company.objects.filter(pk=company.pk).update(inventory_mode="quantity")
                check("database rejects quantity registry row", False, "update allowed")
            except IntegrityError:
                company.refresh_from_db()
                check(
                    "database rejects quantity registry row",
                    company.inventory_mode == INVENTORY_MODE_SERIAL,
                    company.inventory_mode,
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
            "database has exact serial-only check constraint",
            bool(row) and "serial" in definition and "quantity" not in definition,
            definition,
        )

        if company is not None:
            migration = importlib.import_module(
                "tenancy.migrations.0008_serial_only_company_creation"
            )
            precondition_blocked = False
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "ALTER TABLE tenancy_company DROP CONSTRAINT "
                        "tenancy_company_valid_inventory_mode"
                    )
                Company.objects.filter(pk=company.pk).update(inventory_mode="quantity")
                try:
                    migration.require_serial_registry(django_apps, None)
                except RuntimeError as exc:
                    precondition_blocked = (
                        str(company.pk) in str(exc)
                        and company.name not in str(exc)
                    )
                transaction.set_rollback(True)
            company.refresh_from_db()
            check(
                "migration precondition blocks conflicting IDs without names",
                precondition_blocked
                and company.inventory_mode == INVENTORY_MODE_SERIAL,
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
            "forged admin quantity field is ignored and remains serial",
            posted.is_valid() and posted.instance.inventory_mode == INVENTORY_MODE_SERIAL,
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
            and created is not None
            and created.inventory_mode == INVENTORY_MODE_SERIAL,
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
                and verification.family == INVENTORY_MODE_SERIAL,
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
