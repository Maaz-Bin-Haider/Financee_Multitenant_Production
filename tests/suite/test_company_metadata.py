#!/usr/bin/env python3
"""Company inventory-mode metadata and Phase 5 availability checks.

Runs inside the production web container. It intentionally does not provision
or delete schemas. Quantity schema provisioning is covered separately by the
Phase 5 foundation suite.
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
from django.db import IntegrityError, connection, transaction  # noqa: E402

from financee.admin_site import financee_admin_site  # noqa: E402
from tenancy.admin import CompanyAdmin, CompanyAdminForm  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company,
    INVENTORY_MODE_CHOICES,
    INVENTORY_MODE_QUANTITY,
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
        "all companies use a supported inventory mode",
        bool(companies) and all(
            c.inventory_mode in {INVENTORY_MODE_SERIAL, INVENTORY_MODE_QUANTITY}
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
        "model declares serial and quantity choices",
        choice_values == {INVENTORY_MODE_SERIAL, INVENTORY_MODE_QUANTITY},
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
        inventory_mode=INVENTORY_MODE_QUANTITY,
    )
    try:
        quantity_candidate.full_clean()
        chk("quantity company metadata is available in Phase 5", True)
    except ValidationError as exc:
        chk("quantity company metadata is available in Phase 5", False, validation_message(exc))

    company = next(
        value for value in companies
        if value.inventory_mode == INVENTORY_MODE_SERIAL
    )
    original_schema = company.schema_name
    company.inventory_mode = INVENTORY_MODE_QUANTITY
    try:
        company.save(update_fields=["inventory_mode"])
        chk("existing company inventory mode is immutable", False, "save succeeded")
    except ValidationError as exc:
        company.refresh_from_db()
        chk(
            "existing company inventory mode is immutable",
            company.inventory_mode == INVENTORY_MODE_SERIAL
            and company.schema_name == original_schema
            and "permanent" in validation_message(exc).lower(),
            validation_message(exc),
        )

    # The database constraint protects against unknown/corrupt family values,
    # while deliberately allowing the future supported "quantity" value.
    try:
        with transaction.atomic():
            Company.objects.filter(pk=company.pk).update(inventory_mode="invalid-family")
        chk("database rejects unknown inventory mode", False, "update succeeded")
    except IntegrityError:
        company.refresh_from_db()
        chk(
            "database rejects unknown inventory mode",
            company.inventory_mode == INVENTORY_MODE_SERIAL,
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
    chk("inventory mode database constraint exists", constraint_count == 1, constraint_count)

    admin_obj = CompanyAdmin(Company, financee_admin_site)
    add_readonly = set(admin_obj.get_readonly_fields(None, None))
    change_readonly = set(admin_obj.get_readonly_fields(None, company))
    chk("admin allows inventory mode selection on add", "inventory_mode" not in add_readonly)
    chk("admin makes inventory mode readonly on change", "inventory_mode" in change_readonly)
    chk("admin list displays inventory mode", "inventory_mode" in admin_obj.list_display)
    chk("admin can filter by inventory mode", "inventory_mode" in admin_obj.list_filter)

    form = CompanyAdminForm(data={
        "name": f"PHASE3 ADMIN QUANTITY {time.time_ns()}",
        "inventory_mode": INVENTORY_MODE_QUANTITY,
        "base_currency": "PKR",
        "tax_environment": "non_tax",
        "is_active": "on",
        "grace_days": "3",
        "warn_days_before": "7",
    })
    chk(
        "admin form accepts quantity foundation company in Phase 5",
        form.is_valid(),
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
