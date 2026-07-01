# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Financee is a Django + PostgreSQL multitenant accounting/inventory system. The defining architectural choice: **Django only handles HTTP (routing, auth, permissions, templates, tenant activation, admin). All business logic — accounting, inventory, returns, ledgers, reports — lives in PostgreSQL stored functions, triggers, and views.** Feature views are thin wrappers that validate input and call SQL functions via `connection.cursor()`. Do not port business logic into Python; extend the SQL.

Each company is an isolated PostgreSQL **schema** (`tenant_company_<id>`). Shared Django data (auth, sessions, permissions) and the tenant registry live in `public`.

Deeper context lives in `README.md`, `PROJECT_CONTEXT.md` (persistent engineering context — keep it current), and `FIXED_ISSUES.md` (diagnosed production/setup bugs). Read these before non-trivial work.

## Multitenancy model — the core mechanism

- Only **two ORM models exist**: `Company` and `Membership` (`tenancy/models.py`), both in `public`. A user belongs to exactly one company (OneToOne). Business tables are **not** Django models.
- `tenancy/middleware.py` (`TenantSchemaMiddleware`) resolves the user's membership per request, runs `SET search_path TO "<schema>", public`, and **always resets to `public` in a `finally`**. Tenant context lives only on the connection for the request's duration — never in module/global state.
- `tenancy/utils.py` holds the schema helpers. Schema names are never bound parameters (identifiers aren't parameterizable) — they're validated against `SCHEMA_NAME_RE` and double-quoted. Reuse these helpers; never interpolate a raw schema name into SQL.
- Provisioning (`tenancy/provisioning.py`): saving a `Company` fires a post_save signal that materializes the schema from `tenancy/sql/tenant_template.sql`. Idempotent — skips if tables already exist.
- Any management command or admin utility that activates a tenant schema manually **must reset `search_path`** afterward.

## Changing the tenant business database (critical workflow)

Business schema changes require **two coordinated edits**, or new tenants and existing tenants diverge:

1. Update `tenancy/sql/tenant_template.sql` (so new tenants get it).
2. Add/update an **idempotent** patch under `tenancy/sql/` using `CREATE OR REPLACE FUNCTION`, `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
3. Apply to existing tenants: `python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql`

Keep `tenant_template.sql`, `build_multitenant_db.sql`, and `tenancy/sql/production_hardening.sql` aligned — `production_hardening.sql` is re-run on every Docker container start (`deploy/entrypoint.sh`) to self-heal older schemas, so anything critical must live there and be safe to rerun.

Every tenant schema must have a `tenant_schema_version` row (checked by middleware via `TENANT_SCHEMA_VERSION`, default 1). A schema with business tables but no version row triggers a 403 and, historically, a login redirect loop — see `FIXED_ISSUES.md`.

## Permissions & guards

Route-level guards live in `financee/security.py` and are enforced in `TenantSchemaMiddleware.process_view`. `PROTECTED_PREFIX_PERMS` maps URL prefixes to required `auth.*` perms (mode `all`); `/sales-reports/` uses `SALES_REPORT_PERMS` with mode `any`. Permissions are seeded via migrations in `authentication/migrations/`. Views also re-check perms individually. JSON error responses are scrubbed of internal detail by the middleware. Rate limits (dashboard/reports/lookup/login) are cache-backed — set `REDIS_URL` in production so they apply across workers.

## Common commands

```bash
# Local dev
pip install -r requirements-lock.txt
python manage.py migrate                      # applies ONLY public/shared Django migrations
python manage.py createsuperuser
python manage.py provision_tenant "Demo Co" --owner alice
python manage.py runserver

# Tenant SQL rollout
python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql
python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql --dry-run
python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql --only tenant_company_3
```

`python manage.py migrate` never touches tenant business schemas — only `public`.

## Tests (require the Docker stack)

The suite runs inside the running `web` container, not the host venv:

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh            # copies tests in, runs all harnesses
./tests/run_tests.sh --reset    # ALSO drops + re-provisions tenant schemas for a clean signal

# run one harness directly (after the runner has copied tests in once)
docker compose -f deploy/docker-compose.yml exec web python tests/test_transaction_lifecycle_deep.py
```

Harnesses in `tests/` (see `tests/README.md`): `test_system.py` (SQL business functions per tenant), `test_http.py` (Django client over real views/permissions), `test_transaction_lifecycle_deep.py` (serial lifecycle stress: purchase→sale→return→resale, mixed invoices, return guards). `test_transaction_lifecycle_deep.py` intentionally **fails** on duplicate returns / invalid serial-state transitions rather than treating them as no-ops. Opening cash (singleton) and month close (one per period) are single-shot — use `--reset` for a pristine run.

The comprehensive suite is `tests/suite/` (run `python tests/suite/run_all.py` in the container; see `tests/suite/README.md` and `tests/suite/RESULTS.md`). It covers **every** domain and **every** report against all tenants, asserting real accounting invariants (double-entry balance, party balances, COGS, stock/serial coherence). It supports an `XFAIL`/`known_bug` channel and has surfaced genuine **tenant schema drift** — some idempotent `tenancy/sql/` patches were applied to one tenant but not the other (e.g. `create_purchase_return`'s in-stock guard and the cash-party feature are missing on `tenant_company_1`). When you change tenant SQL, apply it to *all* tenants (`apply_sql_all_tenants`) to avoid widening this drift.

## Gotchas

- **Django version:** the `financee/settings.py` header comment says Django 5.2, but `requirements*.txt` pin **Django 6.0.6**. Dependency files are the source of truth.
- Some view files keep older **commented-out implementations**; the active function is the uncommented one, usually later in the file.
- Retired **Profit Reports** routes (`/accountsReports/company-valuation/`, `/sale-wise-report/`) 404 by design; their DB objects and permissions were intentionally left in place for compatibility. Don't remove them without an audit.
- The admin uses a **custom admin site** (`financee/admin_site.py`), not Django's default. Admin styling rules (muted palette, no inline styles, single-column responsive) are documented in `PROJECT_CONTEXT.md` → Admin UI Notes; put styles in `static/css/financee_admin.css`.
- Deployment: Docker stack in `deploy/` (Postgres 16, Redis, Gunicorn, Nginx). Static is collected at image build with `ManifestStaticFilesStorage` and synced into the shared volume by the entrypoint.

## When you change things

Update `PROJECT_CONTEXT.md` when architecture, routes, permissions, tenant SQL, deployment, env vars, or tests change. Log diagnosed production/setup fixes in `FIXED_ISSUES.md`.
