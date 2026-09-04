"""Read-only Phase 4 entry audit for migration replacement and hygiene.

This command verifies the exact post-Phase-3 public state and migration leaves.
It never changes migration records, the retirement archive, company rows, tenant
schemas, permissions, grants, containers, or application files.
"""
from __future__ import annotations

import hashlib
import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


TENANCY_MIGRATIONS = (
    "0001_initial",
    "0002_subscription_control",
    "0003_subscription_emails",
    "0004_company_feature_flags",
    "0005_company_inventory_mode",
    "0006_currency_company_setup",
    "0007_company_provisioning_state",
    "0008_serial_only_company_creation",
    "0009_inventory_mode_compatibility",
)
AUTHENTICATION_MIGRATIONS = (
    "0001_payments_permissions",
    "0002_receipts_permissions",
    "0003_purchase_permissions",
    "0004_sale_permissions",
    "0005_purchase_return_permissions",
    "0006_sale_return_permissions",
    "0007_items_permissions",
    "0008_parties_permissions",
    "0009_accounts_reports_permissions",
    "0010_stock_reports_page",
    "0011_profit_reports_permissions",
    "0012_add_stock_reports_permissions_version2",
    "0013_add_account_reports_permissions_version2",
    "0014_add_stock_reports_permissions_version3",
    "0015_add_dashboard_options_permissions",
    "0016_add_set_opening_permission",
    "0017_add_owner_equity_permission",
    "0018_add_month_close_permission",
    "0019_add_sales_reports_permissions",
    "0020_add_contra_permissions",
    "0021_add_opening_stock_permissions",
    "0022_add_quantity_warehouse_permissions",
    "0023_add_quantity_transfer_permissions",
    "0024_add_quantity_count_adjustment_permissions",
    "0025_add_quantity_platform_permissions",
)
RETIRED_PERMISSION_CODES = (
    "view_warehouse",
    "create_warehouse",
    "update_warehouse",
    "delete_warehouse",
    "view_warehouse_transfer",
    "create_warehouse_transfer",
    "update_warehouse_transfer",
    "delete_warehouse_transfer",
    "view_physical_count",
    "create_physical_count",
    "approve_inventory_adjustment",
    "reverse_inventory_adjustment",
    "view_quantity_audit",
    "manage_quantity_attachments",
)
RETIRED_FEATURE_KEYS = (
    "purchase_reports",
    "quantity_controls",
    "quantity_controls.warehouses",
    "quantity_controls.transfers",
    "quantity_controls.counts",
    "quantity_controls.tax",
    "quantity_controls.audit",
)
ARCHIVE = "public.tenancy_phase3b_retirement_archive"
ARCHIVE_MARKER = "financee-serial-only-phase3b-archive-v1"
ARCHIVE_KEY = "serial-only-phase3b-v1"


def require(value, message):
    if not value:
        raise CommandError("Phase 4 entry audit blocked: " + message)


def scalar(cursor, query, params=None):
    cursor.execute(query, params or [])
    return cursor.fetchone()[0]


def inspect():
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL lock_timeout='2s'")
            cursor.execute("SET LOCAL statement_timeout='60s'")
            cursor.execute("SET LOCAL search_path TO public")

            cursor.execute(
                """SELECT app, name FROM django_migrations
                     WHERE app IN ('tenancy', 'authentication')
                     ORDER BY app, name"""
            )
            observed = {"tenancy": [], "authentication": []}
            for app, name in cursor.fetchall():
                observed[app].append(name)
            require(
                tuple(observed["tenancy"]) == TENANCY_MIGRATIONS,
                "tenancy migration history is not at the exact 0009 leaf",
            )
            require(
                tuple(observed["authentication"]) == AUTHENTICATION_MIGRATIONS,
                "authentication migration history is not at the exact 0025 leaf",
            )

            column_present = scalar(
                cursor,
                """SELECT EXISTS (
                       SELECT 1 FROM pg_attribute
                        WHERE attrelid='public.tenancy_company'::regclass
                          AND attname='inventory_mode' AND NOT attisdropped)""",
            )
            require(not column_present, "retired inventory_mode column is present")

            require(
                scalar(cursor, "SELECT to_regclass(%s)", [ARCHIVE]) is not None,
                "Phase 3B reversal archive is absent",
            )
            require(
                scalar(
                    cursor,
                    "SELECT obj_description(%s::regclass, 'pg_class')",
                    [ARCHIVE],
                )
                == ARCHIVE_MARKER,
                "Phase 3B archive marker is unexpected",
            )
            cursor.execute(
                f"""SELECT operation_key, payload_sha256, state
                       FROM {ARCHIVE} ORDER BY operation_key"""
            )
            archive_rows = cursor.fetchall()
            require(
                len(archive_rows) == 1
                and archive_rows[0][0] == ARCHIVE_KEY
                and re.fullmatch(r"[0-9a-f]{64}", archive_rows[0][1] or "")
                and archive_rows[0][2] == "applied",
                "Phase 3B archive is not in the reviewed applied state",
            )

            permission_count = scalar(
                cursor,
                """SELECT count(*) FROM auth_permission p
                     JOIN django_content_type ct ON ct.id=p.content_type_id
                    WHERE ct.app_label='auth' AND ct.model='user'
                      AND p.codename = ANY(%s)""",
                [list(RETIRED_PERMISSION_CODES)],
            )
            require(permission_count == 0, "retired quantity permissions remain")

            stale_feature_count = scalar(
                cursor,
                """SELECT count(*) FROM tenancy_company c
                     CROSS JOIN LATERAL jsonb_array_elements_text(
                         COALESCE(c.disabled_features, '[]'::jsonb)
                     ) AS feature(value)
                    WHERE feature.value = ANY(%s)""",
                [list(RETIRED_FEATURE_KEYS)],
            )
            require(stale_feature_count == 0, "retired feature keys remain")

            cursor.execute(
                """SELECT id, schema_name, is_active, provisioning_state
                     FROM tenancy_company ORDER BY id"""
            )
            companies = cursor.fetchall()
            require(companies, "no registered company exists")
            require(
                all(
                    schema == f"tenant_company_{company_id}"
                    and active
                    and state == "ready"
                    for company_id, schema, active, state in companies
                ),
                "company registry is not canonical active ready serial-only",
            )

            cursor.execute(
                """SELECT nspname FROM pg_namespace
                    WHERE strpos(nspname, 'tenant_company_') = 1
                    ORDER BY nspname"""
            )
            physical = [row[0] for row in cursor.fetchall()]
            registered = [row[1] for row in companies]
            require(physical == sorted(registered), "tenant schema registry drift exists")
            for schema in physical:
                require(
                    scalar(
                        cursor,
                        "SELECT to_regclass(quote_ident(%s) || '.tenant_schema_version')",
                        [schema],
                    )
                    is not None,
                    "registered schema lacks serial metadata",
                )
                require(
                    scalar(
                        cursor,
                        "SELECT to_regclass(quote_ident(%s) || '.tenant_schema_metadata')",
                        [schema],
                    )
                    is None,
                    "retired quantity-family schema detected",
                )

            state = {
                "archive_payload_sha256": archive_rows[0][1],
                "archive_state": archive_rows[0][2],
                "authentication_leaf": AUTHENTICATION_MIGRATIONS[-1],
                "company_count": len(companies),
                "inventory_mode_column_present": column_present,
                "physical_schema_count": len(physical),
                "retired_feature_occurrences": stale_feature_count,
                "retired_permission_count": permission_count,
                "tenancy_leaf": TENANCY_MIGRATIONS[-1],
            }
            encoded = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
            return {
                "audit": "serial-only-phase4-entry",
                "authorizes_migration_replacement": False,
                "mode": "database-enforced-read-only",
                "state_sha256": hashlib.sha256(encoded).hexdigest(),
                **state,
            }


class Command(BaseCommand):
    help = "Read-only Phase 4 migration-leaf and post-cleanup entry audit."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(inspect(), indent=2, sort_keys=True))


if __name__ == "__main__":
    import os
    import sys

    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "financee.settings")
    django.setup()
    Command().run_from_argv(
        ["manage.py", "serial_only_phase4_audit", *sys.argv[1:]]
    )
