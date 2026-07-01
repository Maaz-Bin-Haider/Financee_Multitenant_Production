# Fixed Issues

This file records production/setup issues that were diagnosed and fixed, including the root cause, code or SQL changes, and verification steps.

## 2026-07-01: Transaction Integrity Guards (delete_purchase, qty vs serials, COGS reflow)

### Symptoms

A deep coverage review of the sale / purchase / sale-return / purchase-return
lifecycle found three latent data-integrity defects. Each was reproduced on both
`tenant_company_1` and `tenant_company_2` with a non-persistent probe and then
encoded in `tests/test_transaction_lifecycle_deep.py`.

1. Deleting a purchase invoice whose serial had already been sold succeeded and
   silently destroyed the sale.
2. A sale with a `qty` that did not match the number of serials was accepted,
   charging the customer for a different quantity than was shipped.
3. After the supported price-only purchase edit, a later sale return recorded a
   different cost basis than the sale's COGS, drifting inventory/COGS.

### Root Cause

1. `soldunits_unit_id_fkey` is `ON DELETE CASCADE`, and `delete_purchase` deleted
   `PurchaseUnits` unconditionally, so the `SoldUnits` rows were cascade-deleted
   while the `SalesInvoice` and revenue journal survived — an orphaned sale with
   destroyed COGS and stock. Unlike `update_purchase_invoice`, `delete_purchase`
   had no guard.
2. `create_sale` / `update_sale_invoice` set `SalesItems.quantity` and
   `total_amount` from the payload `qty` while shipping only the listed serials.
   Revenue and units shipped diverged; the trial balance still balanced, hiding
   the discrepancy.
3. `update_purchase_invoice` rebuilt only the purchase journal. The sale's COGS
   stayed frozen at the original cost while the return recaptured cost from the
   edited `PurchaseItems.unit_price`.

### Fix

Added `tenancy/sql/fix_transaction_integrity_guards.sql` (idempotent) and folded
the same SQL into `tenancy/sql/tenant_template.sql`,
`tenancy/sql/production_hardening.sql`, and `build_multitenant_db.sql`. Tenant
schema version bumped to 3.

- New `assert_purchase_invoice_deletable(...)`; `delete_purchase` blocks when any
  serial has sale or purchase-return history.
- `create_sale` / `update_sale_invoice` reject a `qty` that does not equal the
  number of serials supplied.
- `update_purchase_invoice` rebuilds the journal of every sale that consumed a
  unit from the edited purchase, keeping COGS in sync with the corrected cost.

### Verification

Applied to both tenants and re-ran the deep suite:

```bash
docker compose -f deploy/docker-compose.yml exec -T web \
  python manage.py apply_sql_all_tenants tenancy/sql/fix_transaction_integrity_guards.sql
docker compose -f deploy/docker-compose.yml exec -T web python tests/test_transaction_lifecycle_deep.py
```

Result:

```text
tenant_company_1: 2702/2702 real checks passed
tenant_company_2: 2702/2702 real checks passed
PASSED: all deep lifecycle checks passed.
```

`test_system.py` (111/111 per tenant), `test_returns_full.py` (21/21), and
`test_cash.py` (20/20) still pass. The updated `tenant_template.sql` was verified
to build cleanly in a throwaway schema. `production_hardening.sql` runs on every
container start, so existing tenants self-heal.

### Note (out of scope)

`tests/test_return_fix.py` has one pre-existing failing assertion unrelated to
this change: it greps for the message "not sold to this customer" when updating a
re-sold sale return, but the sale-return hardening already returns "…has since
been re-sold. Reverse the later sale first." The stale substring should be
updated separately.

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

## 2026-07-01: Sale Return Lifecycle Guards Hardened

### Symptoms

The deep transaction lifecycle test found failures in serial return workflows:

- Duplicate sale returns could be accepted for already-returned serials.
- A sale invoice could be updated or deleted even after one of its serials had sale-return history.
- Cash-sale versus credit-sale return lookup could bind to historical sale rows instead of the currently active sale.
- The same mutation risks reproduced on multi-item invoices with mixed serial states.

### Root Cause

Some tenant schemas still had older sale-return functions that did not consistently resolve the currently active `SoldUnits.status = 'Sold'` row. Sale invoice update/delete functions also lacked a guard against downstream sale-return history.

### Fix

Added `tenancy/sql/fix_sale_return_lifecycle_guards.sql` and folded the same idempotent SQL into `tenancy/sql/production_hardening.sql`, `tenancy/sql/tenant_template.sql`, and `build_multitenant_db.sql`.

The fix:

- Resolves sale returns against the newest active sold unit only.
- Blocks duplicate sale returns when no active sold unit remains.
- Enforces the active sale customer for cash and credit returns.
- Blocks `update_sale_invoice(...)` and `delete_sale(...)` when any serial in the sale has return history.
- Preserves journal rebuild behavior for valid sale updates.

### Verification

Applied the hardening SQL to both tenant schemas:

```bash
docker compose -f deploy/docker-compose.yml exec -T web python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql
```

Regression results:

```text
PASSED: all deep lifecycle checks passed.
tenant_company_1: 111/111 passed, 0 failed
tenant_company_2: 111/111 passed, 0 failed
```
