# Project Context

Last updated: 2026-06-30

This file is the persistent engineering context for Financee. Update it on every meaningful project change, especially changes to architecture, routes, permissions, tenant SQL, deployment behavior, environment variables, tests, or data model assumptions.

## System Identity

Financee is a multitenant accounting and inventory system for multiple companies. It uses Django for request handling and PostgreSQL for business logic. Each tenant/company has a separate PostgreSQL schema named `tenant_company_<id>`.

## Current Architecture

- Shared `public` schema stores Django auth, sessions, admin tables, permissions, and tenancy registry tables.
- Tenant schemas store all business tables, functions, views, triggers, and tenant schema version metadata.
- `TenantSchemaMiddleware` resolves the authenticated user's `Membership`, sets `search_path` to `"<tenant_schema>", public`, and resets it after the response.
- Users are mapped to exactly one company through `tenancy.Membership`.
- Creating a `tenancy.Company` provisions a tenant schema from `tenancy/sql/tenant_template.sql`.
- Most feature views are thin wrappers around PostgreSQL stored functions.

## Source-of-Truth Files

- Django settings: `financee/settings.py`
- Root routes: `financee/urls.py`
- Security and permission guard: `financee/security.py`
- Tenant switching helpers: `tenancy/utils.py`
- Tenant provisioning: `tenancy/provisioning.py`
- Tenant registry models: `tenancy/models.py`
- Tenant SQL template: `tenancy/sql/tenant_template.sql`
- Existing-tenant SQL rollout command: `tenancy/management/commands/apply_sql_all_tenants.py`
- Docker production stack: `deploy/docker-compose.yml`, `deploy/Dockerfile`, `deploy/entrypoint.sh`
- Functional test docs: `tests/README.md`

## Key Business Modules

- Dashboard: `home`
- Party master: `parties`
- Item master: `items`
- Purchases: `purchase`
- Sales: `sale`
- Purchase returns: `purchaseReturn`
- Sales returns: `saleReturn`
- Payments: `payments`
- Receipts: `receipts`
- Contra entries: `contra`
- Accounting/inventory reports: `accountsReports`
- Sales analytics: `sales_reports`
- Opening cash: `set_opening`
- Opening stock: `opening_stock`
- Owner equity: `owner_equity`
- Month close: `month_close`
- Authentication: `authentication`
- Tenancy/admin support: `tenancy`, `financee/admin_site.py`

## Database Change Rule

For any tenant business database change:

1. Update `tenancy/sql/tenant_template.sql` for new tenants.
2. Add or update an idempotent patch SQL file under `tenancy/sql/` for existing tenants.
3. Apply with `python manage.py apply_sql_all_tenants <sql-file>`.
4. Update this file and `README.md` if the operational contract changes.

Idempotent SQL should use patterns such as `CREATE OR REPLACE FUNCTION`, `CREATE INDEX IF NOT EXISTS`, and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## Runtime and Deployment Notes

- Dependencies are pinned in `requirements.txt` and `requirements-lock.txt`.
- Docker production uses PostgreSQL 16, Redis, Gunicorn, and Nginx.
- Static files are collected at Docker image build time and synced into the shared static volume on container start.
- `python manage.py migrate` applies only public/shared Django migrations.
- Business schemas are not managed by Django migrations.
- `REDIS_URL` should be set in production so cache/rate-limit state is shared across workers.

## Security and Permission Notes

- Route-level guards live in `financee/security.py` and are enforced by `TenantSchemaMiddleware`.
- Authenticated users without an active company cannot access tenant features.
- Admin/auth/static/media routes are tenant-guard exempt.
- JSON errors are scrubbed by middleware to avoid leaking internal exception details.
- Login, dashboard, report, and lookup endpoints have lightweight cache-backed rate limits.

## Test Strategy

- `tests/test_system.py` exercises tenant stored functions and report functions through direct SQL.
- `tests/test_http.py` exercises real Django endpoints through the Django test client.
- `tests/run_tests.sh` runs both harnesses in Docker and can reset tenant schemas with `--reset`.

## Known Documentation Caveats

- The generated header comment in `financee/settings.py` says Django 5.2.6, but dependency files currently pin Django 6.0.6. Treat dependency files as source of truth unless code compatibility work says otherwise.
- Some view files retain older commented-out implementations. Active functions are the uncommented definitions later in the files.

## Maintenance Checklist

When changing the project, update this file if any answer changes:

- Did a route, app, or endpoint move?
- Did a permission, rate limit, or tenant guard rule change?
- Did a tenant table/function/view/trigger change?
- Did provisioning or existing-tenant rollout change?
- Did Docker, environment variables, or static handling change?
- Did test setup, commands, or expected coverage change?
