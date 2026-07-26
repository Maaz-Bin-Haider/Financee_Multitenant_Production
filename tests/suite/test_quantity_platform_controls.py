#!/usr/bin/env python3
"""Phase 20 quantity attachments, audit, features, permissions and UI gates."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")

import django  # noqa: E402
django.setup()

from django.db import connection  # noqa: E402

from attachments.utils import QUANTITY_DOCUMENT_CONFIG  # noqa: E402
from tenancy.features import FEATURE_GROUPS, feature_for_path, features_map  # noqa: E402
from tenancy.models import (  # noqa: E402
    Company, Currency, INVENTORY_MODE_QUANTITY, INVENTORY_MODE_SERIAL,
    PROVISIONING_READY,
)
from tenancy.schema_families import schema_family  # noqa: E402

RESULTS = []


def chk(name, ok, detail=""):
    RESULTS.append((name, bool(ok), "" if ok else str(detail)))


def static_checks():
    family = schema_family(INVENTORY_MODE_QUANTITY)
    chk("schema family includes Phase 20", family.required_version >= 20)
    chk("platform rollout registered",
        family.hardening_path.name == "quantity_platform_controls.sql"
        and family.hardening_path in family.bootstrap_paths)
    chk("attachment and audit tables fingerprinted",
        {"document_attachments", "quantity_audit_events"}.issubset(
            family.required_tables))
    chk("audit API function fingerprinted",
        "quantity_audit_log" in family.required_functions)
    chk("all four quantity document mappings exist",
        set(QUANTITY_DOCUMENT_CONFIG) == {
            "sale", "purchase", "sale_return", "purchase_return"})
    chk("quantity feature catalogue registered",
        FEATURE_GROUPS["quantity_controls"]["modes"] == ("quantity",))
    chk("quantity routes are feature guarded",
        feature_for_path("/transfers/") == "quantity_controls.transfers"
        and feature_for_path("/quantity-audit/") == "quantity_controls.audit")
    quantity = Company(name="q", inventory_mode=INVENTORY_MODE_QUANTITY)
    serial = Company(name="s", inventory_mode=INVENTORY_MODE_SERIAL)
    chk("catalogue applicable to quantity company",
        features_map(quantity)["quantity_controls"]["applicable"])
    chk("catalogue not applicable to serial company",
        not features_map(serial)["quantity_controls"]["applicable"])


def database_checks():
    family = schema_family(INVENTORY_MODE_QUANTITY)
    company = Company.objects.create(
        name=f"PHASE20 CONTROLS {time.time_ns()}",
        inventory_mode=INVENTORY_MODE_QUANTITY,
        base_currency=Currency.objects.get(pk="PKR"),
        tax_environment="non_tax",
    )
    company.refresh_from_db()
    schema = company.schema_name
    quoted = connection.ops.quote_name(schema)
    try:
        chk("temporary quantity tenant provisioned",
            company.provisioning_state == PROVISIONING_READY,
            company.provisioning_error_code)
        with connection.cursor() as cursor:
            cursor.execute(f"SET search_path TO {quoted}, public")
            cursor.execute("SELECT to_regclass('quantity_audit_events')")
            chk("audit table deployed", bool(cursor.fetchone()[0]))
            cursor.execute("SELECT to_regclass('document_attachments')")
            chk("attachment table deployed", bool(cursor.fetchone()[0]))
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname='quantity_audit_log')"
            )
            chk("audit query deployed", cursor.fetchone()[0])
            cursor.execute(
                "SELECT version FROM tenant_schema_metadata WHERE id"
            )
            chk("deployed schema version current",
                cursor.fetchone()[0] == family.required_version)
            cursor.execute(
                """INSERT INTO document_attachments
                   (document_type,document_id,file_kind,original_name,stored_name,
                    storage_path,content_type,file_size)
                   VALUES ('sale',999999,'image','a.png','a.png','x/a.png',
                           'image/png',1) RETURNING attachment_id"""
            )
            attachment_id = cursor.fetchone()[0]
            cursor.execute(
                """SELECT action FROM quantity_audit_events
                   WHERE entity_type='document_attachments' AND entity_id=%s
                   ORDER BY event_id""", [str(attachment_id)]
            )
            chk("attachment mutation creates audit event",
                cursor.fetchall() == [("create",)])
            cursor.execute(
                "UPDATE document_attachments SET original_name='b.png' "
                "WHERE attachment_id=%s", [attachment_id]
            )
            cursor.execute(
                """SELECT array_agg(action ORDER BY event_id)
                   FROM quantity_audit_events
                   WHERE entity_type='document_attachments' AND entity_id=%s""",
                [str(attachment_id)],
            )
            chk("attachment replacement is audited",
                cursor.fetchone()[0] == ["create", "update"])
            try:
                cursor.execute(
                    "DELETE FROM quantity_audit_events WHERE entity_type="
                    "'document_attachments' AND entity_id=%s", [str(attachment_id)]
                )
                immutable = False
            except Exception:
                connection.rollback()
                immutable = True
            chk("audit events reject deletion", immutable)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")
            if schema and schema.startswith("tenant_company_"):
                cursor.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
        Company.objects.filter(pk=company.pk).delete()


def permission_checks():
    # Migration source is checked without mutating the public database.
    migration = (
        os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        + "/authentication/migrations/0025_add_quantity_platform_permissions.py"
    )
    text = open(migration, encoding="utf-8").read()
    chk("audit permission migration present", "view_quantity_audit" in text)
    chk("attachment permission migration present",
        "manage_quantity_attachments" in text)


def main():
    static_checks()
    database_checks()
    permission_checks()
    failed = [x for x in RESULTS if not x[1]]
    for name, ok, detail in RESULTS:
        print(("PASS" if ok else "FAIL") + ":", name,
              ("" if ok or not detail else f"— {detail}"))
    print(f"{len(RESULTS)-len(failed)}/{len(RESULTS)} Phase 20 checks passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
