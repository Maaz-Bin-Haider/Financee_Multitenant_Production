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
- Fixed issue log: `FIXED_ISSUES.md`

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
- Existing/bootstrapped tenant schemas must have `tenant_schema_version`. If an authenticated tenant user is denied after login, verify their `Membership`, company `is_active`, physical schema existence, and `SELECT * FROM tenant_schema_version` under that tenant search path.
- `build_multitenant_db.sql` includes the tenant schema version marker for the example `tenant_company_1` schema, and `deploy/entrypoint.sh` applies `tenancy/sql/production_hardening.sql` on every container start so older tenant schemas self-heal.
- Authenticated users with invalid tenant state receive a stable 403 tenant error instead of being redirected to login, preventing `/home/` and `/authentication/login/` redirect loops.
- AJAX login responses include `redirect_url`; staff users without an active company are sent to `/admin/`, while tenant users are sent to `/home/`.
- Keep `FIXED_ISSUES.md` updated when a production/setup issue is diagnosed and fixed, especially if the fix affects tenant provisioning, login routing, deployment startup, or recovery commands.
- Legacy Profit Reports routes `/accountsReports/company-valuation/` and `/accountsReports/sale-wise-report/` are retired from the UI/routes. Replacement coverage is in Monthly Reports, Sales Reports, and dashboard sales/profit widgets. Do not remove related DB objects or historical permissions unless a separate compatibility audit is completed.

## Security and Permission Notes

- Route-level guards live in `financee/security.py` and are enforced by `TenantSchemaMiddleware`.
- Authenticated users without an active company cannot access tenant features.
- Admin/auth/static/media routes are tenant-guard exempt.
- JSON errors are scrubbed by middleware to avoid leaking internal exception details.
- Login, dashboard, report, and lookup endpoints have lightweight cache-backed rate limits.

## Admin UI Notes

- Custom admin templates live in `templates/admin/`.
- The admin theme is owned by `static/css/financee_admin.css`.
- The admin UI is not stock Django only; it includes a custom dashboard, KPI strip, quick links, user activity overview/detail pages, PDF export links, tenant/company management, and custom user delete behavior.
- The current admin visual direction is a responsive professional theme with an off-white background, rounded cards, grey admin text/links, and restrained muted accents.
- Admin home KPI cards use subtle per-card accent colors: soft blue for total users, soft violet for superusers, soft green for active users, soft slate for groups, and soft amber for recorded actions. These accents should stay muted, not vibrant.
- Admin action buttons follow a semantic color system: default/primary buttons are dark grey with off-white text, add buttons are light green with dark green text, change/reset-password buttons are light yellow with dark muted-yellow text, and delete buttons are light red with maroon text.
- Avoid light-blue page/panel backgrounds throughout the admin. Panels, selector widgets, changelist headers, filter areas, and recent-action bodies should remain off-white or neutral.
- Admin links should generally be grey and non-underlined. The Financee brand mark can remain blue; filled primary controls may use dark grey rather than blue.
- The admin dashboard must remain single-column/responsive: recent actions stack below the main dashboard, and changelist/filter panels must fit small laptops and iPad widths without horizontal scrolling.
- Avoid inline styles in admin templates; put layout, spacing, and color in `financee_admin.css` so small laptop and iPad behavior stays consistent.

## Test Strategy

- `tests/test_system.py` exercises tenant stored functions and report functions through direct SQL.
- `tests/test_http.py` exercises real Django endpoints through the Django test client.
- `tests/test_transaction_lifecycle_deep.py` stress-tests real serial lifecycles across purchase, sale, sale return, resale, second return, purchase return, mixed purchase invoice corrections, partial returns, sale-return update/delete after resale, sale invoice update/delete after returns, cash-sale vs credit-sale returns, multi-item mixed serial invoices, and report execution after every entry.
- `tests/TRANSACTION_LIFECYCLE_FLOW_RESULTS.md` records the latest deep lifecycle flow matrix and known failing flows.
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
