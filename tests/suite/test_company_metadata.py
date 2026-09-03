#!/usr/bin/env python3
"""Serial-only company-registry and administration checks.

Runs inside the production web container. It intentionally does not provision
or delete schemas.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.core.exceptions import ValidationError  # noqa: E402
from django.db import DatabaseError, connection, transaction  # noqa: E402

from financee.admin_site import financee_admin_site  # noqa: E402
from tenancy.admin import CompanyAdmin, CompanyAdminForm  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company,
    INVENTORY_MODE_CHOICES,
    INVENTORY_MODE_SERIAL,
)


RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))


def validation_message(exc):
    return " ".join(
        message
        for messages in exc.message_dict.values()
        for message in messages
    )


def main():
    companies = list(Company.objects.order_by("id"))
    chk("active baseline companies exist", bool(companies), len(companies))
    chk(
        "all companies use serial inventory",
        bool(companies) and all(
            c.inventory_mode == INVENTORY_MODE_SERIAL
            for c in companies
        ),
        [(c.id, c.inventory_mode) for c in companies],
    )
    bootstrap = Company.objects.filter(name="Company One").first()
    chk(
        "legacy bootstrap company remains serial",
        bootstrap is None or bootstrap.inventory_mode == INVENTORY_MODE_SERIAL,
        None if bootstrap is None else bootstrap.inventory_mode,
    )

    choice_values = {value for value, _label in INVENTORY_MODE_CHOICES}
    chk(
        "model declares serial as the only company choice",
        choice_values == {INVENTORY_MODE_SERIAL},
        choice_values,
    )

    # Unsaved serial companies remain valid. Avoid save(): this phase must not
    # create or delete any physical tenant schema.
    serial_candidate = Company(
        name=f"PHASE3 SERIAL VALIDATION {time.time_ns()}",
        inventory_mode=INVENTORY_MODE_SERIAL,
    )
    try:
        serial_candidate.full_clean()
        chk("new serial company metadata validates", True)
    except Exception as exc:
        chk("new serial company metadata validates", False, repr(exc))

    quantity_candidate = Company(
        name=f"PHASE3 QUANTITY BLOCK {time.time_ns()}",
        inventory_mode="quantity",
    )
    try:
        quantity_candidate.full_clean()
        chk("quantity company metadata is rejected", False, "validation allowed")
    except ValidationError as exc:
        chk(
            "quantity company metadata is rejected",
            "only serial-number based" in validation_message(exc).lower(),
            validation_message(exc),
        )

    company = next(
        value for value in companies
        if value.inventory_mode == INVENTORY_MODE_SERIAL
    )
    original_schema = company.schema_name
    company.inventory_mode = "quantity"
    try:
        company.save(update_fields=["inventory_mode"])
        chk("existing company inventory mode is immutable", False, "save succeeded")
    except ValidationError as exc:
        company.refresh_from_db()
        chk(
            "existing company cannot be changed to quantity",
            company.inventory_mode == INVENTORY_MODE_SERIAL
            and company.schema_name == original_schema
            and "only serial-number based" in validation_message(exc).lower(),
            validation_message(exc),
        )

    # Before 3B the constraint rejects quantity; after certified 3B the column
    # itself no longer exists. Neither state can store a quantity company mode.
    with connection.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode')")
        legacy_present = cur.fetchone()[0]
        contracted = False
        if not legacy_present:
            from tenancy.management.commands.serial_only_phase3_cleanup import archive
            stored = archive(cur)
            contracted = bool(stored and stored["state"] == "applied")
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("UPDATE public.tenancy_company SET inventory_mode='quantity' WHERE id=%s", [company.pk])
        chk("database rejects quantity inventory mode", False, "update succeeded")
    except DatabaseError as exc:
        company.refresh_from_db()
        chk(
            "database rejects quantity inventory mode",
            company.inventory_mode == INVENTORY_MODE_SERIAL
            and getattr(exc.__cause__, "pgcode", None) == ("23514" if legacy_present else "42703"),
            company.inventory_mode,
        )

    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM pg_constraint
            WHERE conname = 'tenancy_company_valid_inventory_mode'
              AND conrelid = 'public.tenancy_company'::regclass
            """
        )
        constraint_count = cur.fetchone()[0]
    chk("serial-only database constraint or certified column contraction",
        constraint_count == 1 if legacy_present else contracted and constraint_count == 0, constraint_count)

    admin_obj = CompanyAdmin(Company, financee_admin_site)
    chk("admin form hides inventory mode", "inventory_mode" not in CompanyAdminForm.base_fields)
    chk("admin fieldsets hide inventory mode", all(
        "inventory_mode" not in fieldset[1].get("fields", ())
        for fieldset in admin_obj.fieldsets
    ))
    chk("admin list hides inventory mode", "inventory_mode" not in admin_obj.list_display)
    chk("admin filter hides inventory mode", "inventory_mode" not in admin_obj.list_filter)

    form = CompanyAdminForm(data={
        "name": f"PHASE3 ADMIN QUANTITY {time.time_ns()}",
        "inventory_mode": "quantity",
        "base_currency": "PKR",
        "tax_environment": "non_tax",
        "is_active": "on",
        "grace_days": "3",
        "warn_days_before": "7",
    })
    chk(
        "posted quantity value cannot alter the serial admin default",
        form.is_valid() and form.instance.inventory_mode == INVENTORY_MODE_SERIAL,
        form.errors.as_json(),
    )

    print("\n" + "=" * 78)
    passed = sum(1 for _name, ok, _detail in RESULTS if ok)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  [FAIL] {name} - {detail}")
    print("=" * 78)
    print(f"{passed}/{len(RESULTS)} company-metadata checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
