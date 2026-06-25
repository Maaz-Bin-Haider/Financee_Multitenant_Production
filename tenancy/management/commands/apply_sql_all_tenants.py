"""
apply_sql_all_tenants
======================
Run a .sql file against EVERY provisioned tenant schema (and, optionally, the
shared `public` schema), one schema at a time, with that schema first on the
search_path.

WHY THIS COMMAND EXISTS  (this is the answer to "how do schema changes get
applied across tenants?")
------------------------------------------------------------------------------
In a schema-per-tenant design every company owns a *physical copy* of the 22
business tables, 124 functions, 13 views and 11 triggers. Django's own
`migrate` only manages the SHARED `public` schema (auth, sessions, tenancy).
So any change to a business table or stored function must be replayed in every
tenant schema, or the schemas silently DRIFT apart (tenant A has the new column,
tenant B does not). This command is the disciplined mechanism for that:

    1. Add the change to tenancy/sql/tenant_template.sql  -> new tenants inherit it.
    2. Run this command with the same .sql                -> existing tenants catch up.

Make every migration script idempotent (CREATE INDEX IF NOT EXISTS,
CREATE OR REPLACE FUNCTION, ADD COLUMN IF NOT EXISTS, ...) so re-runs are safe.

USAGE
-----
    python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql
    python manage.py apply_sql_all_tenants path/to/change.sql --include-public
    python manage.py apply_sql_all_tenants path/to/change.sql --only tenant_company_3
    python manage.py apply_sql_all_tenants path/to/change.sql --dry-run
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenancy.utils import (
    PUBLIC_SCHEMA,
    list_tenant_schemas,
    search_path_for,
)


class Command(BaseCommand):
    help = "Apply a .sql file to every tenant schema (idempotent scripts only)."

    def add_arguments(self, parser):
        parser.add_argument("sql_file", help="Path to the .sql file to execute.")
        parser.add_argument(
            "--include-public",
            action="store_true",
            help="Also run the script against the shared public schema.",
        )
        parser.add_argument(
            "--only",
            default=None,
            help="Apply to a single named schema instead of all tenants.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the schemas that would be touched, but execute nothing.",
        )

    def handle(self, *args, **opts):
        sql_path = opts["sql_file"]
        if not os.path.isfile(sql_path):
            raise CommandError(f"SQL file not found: {sql_path!r}")

        with open(sql_path, "r", encoding="utf-8") as fh:
            sql_text = fh.read()

        if opts["only"]:
            targets = [opts["only"]]
        else:
            targets = list_tenant_schemas()
            if opts["include_public"]:
                targets = [PUBLIC_SCHEMA] + targets

        if not targets:
            self.stdout.write(self.style.WARNING("No tenant schemas found."))
            return

        self.stdout.write(
            f"{'DRY RUN: ' if opts['dry_run'] else ''}applying {sql_path!r} "
            f"to {len(targets)} schema(s)."
        )

        ok, failed = 0, 0
        for schema in targets:
            if opts["dry_run"]:
                self.stdout.write(f"  would apply -> {schema}")
                continue
            try:
                with connection.cursor() as cur:
                    cur.execute("SHOW search_path")
                    previous = cur.fetchone()[0]
                    cur.execute(f"SET search_path TO {search_path_for(schema)}")
                    try:
                        cur.execute(sql_text)
                    finally:
                        cur.execute(f"SET search_path TO {previous}")
                self.stdout.write(self.style.SUCCESS(f"  ok   -> {schema}"))
                ok += 1
            except Exception as exc:  # noqa: BLE001 - report and continue
                self.stderr.write(self.style.ERROR(f"  FAIL -> {schema}: {exc}"))
                failed += 1

        # Always restore the shared path on this connection before returning.
        with connection.cursor() as cur:
            cur.execute(f"SET search_path TO {PUBLIC_SCHEMA}")

        self.stdout.write(
            self.style.SUCCESS(f"Done. {ok} succeeded, {failed} failed.")
        )
        if failed:
            raise CommandError(f"{failed} schema(s) failed — see errors above.")
