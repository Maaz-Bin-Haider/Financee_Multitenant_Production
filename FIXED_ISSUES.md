# Fixed Issues

This file records production/setup issues that were diagnosed and fixed, including the root cause, code or SQL changes, and verification steps.

## 2026-07-01: Tenant Login Redirect Loop and Admin Login Regression

### Symptoms

- A normal company user could sign in, but the browser showed:

```text
This page isn't working
localhost redirected you too many times.
ERR_TOO_MANY_REDIRECTS
```

- The web logs repeated this pattern:

```text
GET /home/ 302
GET /authentication/login/ 302
GET /home/ 302
GET /authentication/login/ 302
```

- After the redirect-loop prevention change, signing in as `admin` showed:

```text
No active company is assigned to this user.
```

instead of opening the admin panel.

### Root Cause

There were two related issues.

First, the existing bootstrapped tenant schema `tenant_company_1` had business tables but did not have the tenant schema version marker:

```sql
tenant_schema_version
```

`TenantSchemaMiddleware` checks `tenant_schema_version` for authenticated tenant users. When the table is missing, the middleware treats the tenant as inactive or outdated.

The resulting loop was:

1. User signs in successfully.
2. Login redirects the authenticated user to `/home/`.
3. Middleware rejects `/home/` because the assigned tenant schema is not version-valid.
4. Middleware redirects to `/authentication/login/`.
5. Login view sees an already-authenticated user and redirects back to `/home/`.
6. Browser repeats until it reports too many redirects.

Second, the login page used AJAX and always redirected successful logins to `/home/`. Staff/admin users without a company should go to `/admin/`, but the frontend ignored that distinction.

### Fix

#### Bootstrap SQL

`build_multitenant_db.sql` now creates and seeds `tenant_schema_version` inside the example tenant schema before resetting `search_path` to `public`:

```sql
CREATE TABLE IF NOT EXISTS tenant_schema_version (
    id boolean PRIMARY KEY DEFAULT true,
    version integer NOT NULL,
    applied_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tenant_schema_version_singleton CHECK (id)
);

INSERT INTO tenant_schema_version (id, version)
VALUES (true, 1)
ON CONFLICT (id) DO UPDATE
SET version = GREATEST(tenant_schema_version.version, EXCLUDED.version),
    applied_at = CURRENT_TIMESTAMP;
```

This prevents fresh Docker databases from bootstrapping an invalid `tenant_company_1`.

#### Existing Tenant Self-Healing

`deploy/entrypoint.sh` now applies the existing idempotent hardening patch after public Django migrations:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql
```

This repairs older tenant schemas on container start. The patch is safe to rerun because it uses idempotent SQL patterns.

#### Redirect Loop Prevention

`financee/security.py` changed `tenant_required_response()` so authenticated users with invalid tenant state receive a stable HTTP 403 response instead of being redirected to login.

This prevents authenticated users from bouncing between `/home/` and `/authentication/login/`.

#### Correct Admin Login Redirect

`authentication/views.py` now returns `redirect_url` in successful AJAX login responses:

- Staff/admin user without an active company: `/admin/`
- Normal tenant user: `/home/`

`templates/authentication_templates/login_template.html` now uses `data.redirect_url` instead of always sending users to `/home/`.

### Verification

Rebuild and restart:

```powershell
docker compose -f deploy\docker-compose.yml up -d --build
```

Check startup logs:

```powershell
docker compose -f deploy\docker-compose.yml logs --tail=80 web
```

Expected log lines:

```text
[entrypoint] applying required tenant hardening SQL ...
applying 'tenancy/sql/production_hardening.sql' to 1 schema(s).
  ok   -> tenant_company_1
Done. 1 succeeded, 0 failed.
```

Verify tenant version:

```powershell
docker compose -f deploy\docker-compose.yml exec -T db psql -U financee -d financee -c "set search_path to tenant_company_1, public; select * from tenant_schema_version;"
```

Expected result includes:

```text
id | version
t  | 1
```

Run Django checks:

```powershell
docker compose -f deploy\docker-compose.yml exec -T web python manage.py check
```

Expected:

```text
System check identified no issues (0 silenced).
```

Confirmed behavior:

- `user1` reaches `/home/` with HTTP 200.
- `admin` login response points to `/admin/`.
- Authenticated users with invalid/no tenant state receive HTTP 403 instead of a redirect loop.

### Operational Notes

- Clearing browser cookies for `localhost` or using a private window may be needed after a previous redirect loop.
- Public Django migrations do not update tenant business schemas. Tenant SQL patches must be applied through:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql
```

- For Docker deployments, required tenant patches should remain idempotent if they run from `deploy/entrypoint.sh`.

## 2026-07-01: Legacy Profit Reports UI Removed

### Symptoms

The sidebar still exposed an outdated `Profit Reports` section even though its replacements already existed in other parts of the application.

The retired page contained:

- Company Valuation
- Sale-wise Profit

### Root Cause

The legacy page remained wired into the sidebar, URLconf, views, template, and JavaScript after replacement reporting surfaces were added.

Replacement coverage now lives in:

- Dashboard Sales & Profit widgets
- Dashboard Revenue & Profit Trend
- Monthly Reports
- Sales Reports

### Fix

Removed the retired UI/routing layer:

- Removed the `Profit Reports` sidebar link from `templates/base/base.html`.
- Removed `/accountsReports/company-valuation/` and `/accountsReports/sale-wise-report/` from `accountsReports/urls.py`.
- Removed `company_valuation_report` and `sale_wise_report` from `accountsReports/views.py`.
- Removed `templates/display_report_templates/profit_reports_template.html`.
- Removed `static/js/profit_reports.js`.
- Removed the old `/accountsReports/company-valuation/` probe from `tests/test_http.py`.

### What Was Intentionally Kept

No database objects were removed.

The following were intentionally left in place for compatibility:

- SQL functions/views such as `standing_company_worth_view` and `sale_wise_profit(...)`.
- Historical permissions such as `auth.view_company_valuation` and `auth.view_sale_wise_profit_report`.
- `static/css/profit_reports.css`, because `templates/display_report_templates/monthly_reports_template.html` still imports it for shared report styling.

### Verification

Reference scan confirmed:

- `static/js/profit_reports.js` was only used by the retired Profit Reports template.
- `static/css/profit_reports.css` is still used by Monthly Reports, so it was not removed.

Expected behavior:

- No `Profit Reports` item appears in the sidebar.
- `/accountsReports/company-valuation/` returns 404.
- `/accountsReports/sale-wise-report/` returns 404.
- Monthly Reports, Sales Reports, and dashboard sales/profit widgets remain available.
