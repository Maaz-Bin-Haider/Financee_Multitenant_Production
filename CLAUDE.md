# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Financee is a Django + PostgreSQL multitenant accounting/inventory system. The defining architectural choice: **Django only handles HTTP (routing, auth, permissions, templates, tenant activation, admin). All business logic — accounting, inventory, returns, ledgers, reports — lives in PostgreSQL stored functions, triggers, and views.** Feature views are thin wrappers that validate input and call SQL functions via `connection.cursor()`. Do not port business logic into Python; extend the SQL.

Each company is an isolated PostgreSQL **schema** (`tenant_company_<id>`). Shared Django data (auth, sessions, permissions) and the tenant registry live in `public`.

Deeper context lives in `README.md`, `PROJECT_CONTEXT.md` (persistent engineering context — keep it current), and `FIXED_ISSUES.md` (diagnosed production/setup bugs). Read these before non-trivial work.

**Serial-only.** Financee tracks inventory by physical serial number and supports exactly one schema family. A second "quantity/FIFO" family was built but never used in production and has been retired in runtime, database and repository under `SERIAL_ONLY_REMOVAL_PLAN.md` (phase gates + audit trail; **complete** — checkpoint 4B deleted the replaced migration files and the 4C migration-record prune was deliberately skipped; read `PROJECT_CONTEXT.md` before touching migrations). There is no `inventory_mode` — `Company` has no such field, property or choice list, and the physical column and its constraint were dropped from production under the Phase 3B guarded, reversible cleanup. **Do not reintroduce an inventory-mode concept.** Note that the ordinary word "quantity" is *not* evidence of the retired family: serial purchases, sales, returns and stock reports legitimately store counts named `qty`/`quantity`, and those must be preserved. The Phase 3B archive and its restore tooling are the reversal path — never delete them.

## Multitenancy model — the core mechanism

- Tenancy rests on **two ORM models**, `Company` and `Membership` (`tenancy/models.py`). The only other models are `Currency` and the billing trio (`SubscriptionPayment`, `BillingSettings`, `SubscriptionEmailLog`) — all in `public`. A user belongs to exactly one company (OneToOne); a company has many members. Business tables are **not** Django models.
- `tenancy/middleware.py` (`TenantSchemaMiddleware`) resolves the user's membership per request, runs `SET search_path TO "<schema>", public`, and **resets to `public` in `process_response` / `process_exception`**. Tenant context lives only on the connection for the request's duration — never in module/global state. Gunicorn runs thread-local `gthread` workers; never switch to gevent/eventlet (requests could interleave on one connection).
- `tenancy/utils.py` holds the schema helpers. Schema names are never bound parameters (identifiers aren't parameterizable) — they're validated against `SCHEMA_NAME_RE` and double-quoted. Reuse these helpers; never interpolate a raw schema name into SQL.
- Provisioning (`tenancy/provisioning.py`): saving a `Company` fires a post_save signal that materializes the schema from `tenancy/sql/tenant_template.sql`. Idempotent — skips if tables already exist.
- Any management command or admin utility that activates a tenant schema manually **must reset `search_path`** afterward.

## Changing the tenant business database (critical workflow)

Business schema changes require **coordinated edits**, or new tenants and existing tenants diverge:

1. Update `tenancy/sql/tenant_template.sql` (so new tenants get it).
2. Add/update an **idempotent** patch under `tenancy/sql/` using `CREATE OR REPLACE FUNCTION`, `CREATE INDEX IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
3. Register a new patch filename in `rollout_files` in `tenancy/schema_families.py` — `apply_sql_all_tenants` refuses any unregistered file (only 9 of the 18 files are registered today).
4. Apply to existing tenants: `python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql`
5. Re-pin `tests/phase2_serial_runtime_removal_contracts.py` in the same commit — it pins the count and bytes of every tenant SQL file and the bootstrap's example-tenant section, so any SQL change fails CI until re-pinned.

**Do not make `build_multitenant_db.sql` create the `public` tenancy tables or seed a `tenancy` row into `django_migrations`.** It used to, and that left the serial-only squashed migration *partially* applied — Django only uses a replacement when all or none of what it replaces is applied, so it replayed the original chain and recreated the retired `inventory_mode` column on every fresh install. Migrations own the public tenancy schema; the bootstrap builds the example `tenant_company_1` business schema and the entrypoint registers it with `manage.py register_bootstrap_tenant`.

Keep `tenant_template.sql`, `build_multitenant_db.sql`, and `tenancy/sql/production_hardening.sql` aligned — `production_hardening.sql` is re-run on every Docker container start (`deploy/entrypoint.sh`) to self-heal older schemas, so anything critical must live there and be safe to rerun.

Every tenant schema must have a `tenant_schema_version` row at **or above** `TENANT_SCHEMA_VERSION` (default **6**, `financee/settings.py`). A schema with business tables but no version row triggers a 403 and, historically, a login redirect loop — see `FIXED_ISSUES.md`. **Keep the version at 6** unless code depends on the change: the Phase 3B restore guard requires exactly 6, so a bump blocks that reversal path. The bootstrap seeds `tenant_company_1` at version 4 and relies on the entrypoint's `production_hardening.sql` run to lift it to 6.

## Permissions & guards

Route-level guards live in `financee/security.py` and are enforced in `TenantSchemaMiddleware.process_view`. `PROTECTED_PREFIX_PERMS` maps URL prefixes to required `auth.*` perms (mode `all`); `/sales-reports/` uses `SALES_REPORT_PERMS` with mode `any`. Permissions are seeded via migrations in `authentication/migrations/` — except the 11 draft-invoice permissions, which a `post_migrate` handler in `draft/apps.py` seeds so that no new migration row trips the Phase 4 migration-history audit. Views also re-check perms individually. JSON error responses are scrubbed of internal detail by the middleware. Rate limits (dashboard/reports/lookup/login) are cache-backed — set `REDIS_URL` in production so they apply across workers.

## Common commands

```bash
# Local dev
pip install -r requirements-lock.txt
python manage.py migrate                      # applies ONLY public/shared Django migrations
python manage.py createsuperuser
python manage.py provision_tenant "Demo Co" --owner alice   # default feature plan; --all-features for everything
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
./tests/run_tests.sh            # copies tests in, runs test_system.py + test_http.py
./tests/run_tests.sh --reset    # ALSO drops + re-provisions tenant schemas for a clean signal

# run one harness directly (after the runner has copied tests in once)
docker compose -f deploy/docker-compose.yml exec web python tests/test_transaction_lifecycle_deep.py
```

Harnesses in `tests/` (see `tests/README.md`): `test_system.py` (SQL business functions per tenant; always exits 0 — read its `TOTAL FAILURES` line), `test_http.py` (Django client over real views/permissions), `test_transaction_lifecycle_deep.py` (serial lifecycle stress: purchase→sale→return→resale, mixed invoices, return guards). `test_transaction_lifecycle_deep.py` intentionally **fails** on duplicate returns / invalid serial-state transitions rather than treating them as no-ops. Opening cash (singleton) and month close (one per period) are single-shot — use `--reset` for a pristine run.

The comprehensive suite is `tests/suite/` (run `python tests/suite/run_all.py` in the container; see `tests/suite/README.md` and `tests/suite/RESULTS.md`). It covers **every** domain and **every** report against all tenants, asserting real accounting invariants (double-entry balance, party balances, COGS, stock/serial coherence), and supports an `XFAIL`/`known_bug` channel. It is the only harness CI runs (the `full-regression` gate). Latest recorded run (2026-09-16): all 21 modules pass — see `FIXED_ISSUES.md`; `tests/suite/RESULTS.md` is the older 2026-07-06 matrix.

The suite surfaced genuine **tenant schema drift** — idempotent `tenancy/sql/` patches applied to one tenant but not the other. It is now **fully healed**: `tenancy/sql/fix_tenant_drift.sql` (tenant schema version 4) fixed the `create_purchase_return` in-stock guard, the ambiguous `item_transaction_history(text)` overload, and `get_item_names_like`; `tenancy/sql/fix_cash_party_port.sql` (tenant schema version 5) ported the cash-party feature (`is_cash`, `get_cash_party_id`, cash-aware journal builders/ledgers) and its invoice-description prerequisite to every tenant. The suite asserts the cash path unconditionally. When you change tenant SQL, apply it to *all* tenants (`apply_sql_all_tenants`) to avoid widening drift.

## Gotchas

- **Django version:** the `financee/settings.py` header comment says Django 5.2, but `requirements*.txt` pin **Django 6.0.6**. Dependency files are the source of truth.
- Some view files keep older **commented-out implementations**; the active function is the uncommented one, usually later in the file. The same applies to the alerts migration: the previous inline `Swal.fire` calls in `static/js/*.js` and feature templates were commented out (not deleted) next to their `Alerts.*` replacements.
- **Alerts:** all user-facing alerts go through the `Alerts` helper (`static/js/alerts.js`, styled by `static/css/alerts.css`, loaded in `base.html`). Use `Alerts.success/error/warning/notify/confirm/loading/dialog` — don't call `Swal.fire` directly. Fixed conventions (positions, animations, which alerts get a confirmation dialog) are documented in `PROJECT_CONTEXT.md` → Frontend Alert Layer.
- Retired **Profit Reports** routes (`/accountsReports/company-valuation/`, `/sale-wise-report/`) 404 by design; their DB objects and permissions were intentionally left in place for compatibility. Don't remove them without an audit.
- The admin uses a **custom admin site** (`financee/admin_site.py`), not Django's default. Admin styling rules (muted palette, no inline styles, single-column responsive) are documented in `PROJECT_CONTEXT.md` → Admin UI Notes; put styles in `static/css/financee_admin.css`.
- Deployment: Docker stack in `deploy/` (Postgres 16, Redis, Gunicorn, Nginx). Static is collected at image build with `ManifestStaticFilesStorage` and synced into the shared volume by the entrypoint. Production deploys run `deploy/phase30_foundation_deploy.sh` from the CI `deploy` job (see `PHASE30_PRODUCTION_FOUNDATION_RUNBOOK.md`); a rollback restores the web image only.
- **CI byte-pins:** `tests/phase2_serial_runtime_removal_contracts.py` hashes 225 files under `static/` and `templates/` (all but `templates/base/base.html`), every tenant SQL file, the bootstrap's example-tenant section and 12 serial document views. A deliberate change there must re-pin the hash in the same commit.
- **Doc contracts:** `tests/phase4_repository_hygiene_contracts.py` requires exact sentences in `README.md`, `CLAUDE.md` and `PROJECT_CONTEXT.md` (e.g. "There is no inventory-mode concept left to configure" in the README). Keep each one verbatim and on a single line.
- **Draft invoices (`draft` app, `tenancy/sql/add_draft_invoices.sql`):** a serial reserved on a draft is guarded by the trigger `trg_protect_reserved_units` on `purchaseunits`, so every path that would sell, return or delete it is refused — no accounting function was forked, and conversion goes through the unchanged `create_sale`. Switching drafts off (`DRAFT_SALES_ENABLED` or the company's `draft_invoices` flag) hides the UI but never frees reserved serials. The patch is appended to the template and hardening files but deliberately not to `build_multitenant_db.sql`. See `PROJECT_CONTEXT.md` → Draft Sale Invoices.
- **Feature switches (`tenancy/features.py`):** every module, report, dashboard widget, PDF, CSV and attachment has a per-company switch, and a new company starts with `default_disabled_features()`. The admin add form and `provision_tenant` write that default plan; the model never does — its `default=list` is frozen in the migration, so companies created in code and the bootstrap "Company One" keep everything on, and existing companies are untouched. Keep `disabled_features` a list of strings (the Phase 3/3B/4 audits parse it), never map `/home/` to a switch (every denial redirects there), keep the shared pickers (`/parties/autocomplete-party`, `/items/autocomplete-item/`) unrestricted, and never write company rows from `post_migrate` (the checkpoint-4B gate needs them byte-identical). HTTP test harnesses must switch on the features they exercise. See `PROJECT_CONTEXT.md` → Per-Company Feature Flags.
- `TENANCY_CROSS_TENANT_ACTIVITY` defaults to **False** (`financee/settings.py`), so the admin user-activity pages are empty unless it is enabled; the comment in `tenancy/apps.py` saying "on by default" is outdated.

## When you change things

Update `PROJECT_CONTEXT.md` when architecture, routes, permissions, tenant SQL, deployment, env vars, or tests change. Log diagnosed production/setup fixes in `FIXED_ISSUES.md`.
