# Fixed Issues

This file records production/setup issues that were diagnosed and fixed, including the root cause, code or SQL changes, and verification steps.

## 2026-07-08: Freshly Provisioned Tenants 403'd Until the Next Container Restart (missing v6 bump in tenant_template.sql)

### Symptoms

The first CI run failed with "No active tenant memberships found." /
tenant-guard 403s ("No active company is assigned to this user.") against the
tenant that CI provisioned at runtime — while the same suite passed locally.

### Root Cause

When `add_document_attachments.sql` was folded into `tenant_template.sql`, the
`document_attachments` table was copied but its **schema version bump to 6 was
not**: the template's highest bump was `GREATEST(version, 5)`. A tenant
provisioned from the template therefore sat at version 5 while the middleware
requires `TENANT_SCHEMA_VERSION` (6) and returned 403 for its users. Locally
the bug was invisible because `deploy/entrypoint.sh` reruns
`production_hardening.sql` (which bumps to 6) on every container start — so
the window only existed for tenants provisioned *between* restarts. In CI the
second tenant is provisioned after startup, exposing it immediately.
(`add_document_attachments.sql` and `build_multitenant_db.sql` both had the
bump; only the template copy was missing it.)

### Fix

Added the `UPDATE tenant_schema_version ... GREATEST(version, 6)` bump to the
attachments section of `tenancy/sql/tenant_template.sql`. Verified by
provisioning a throwaway schema from the updated template: it reports
version 6 immediately. Existing tenants were never affected (hardening had
already bumped them).

CI itself gained `tests/ci_bootstrap.py`, which creates one tenant user +
membership per active company, because the suite discovers tenants through
`tenancy_membership` — a freshly seeded database has companies but no users.

## 2026-07-08: CSV Export Button Survived the excel_export Feature Switch (JSON double-encoding)

### Symptoms

With the new per-company feature flags, disabling **CSV / Excel export** in the
admin removed the template-rendered CSV buttons, but the **JS-injected**
toolbars (Accounts/Stock report pages build their toolbar in
`accounts_reports.js` / `stock_reports.js` after each report render) still
showed a fully working CSV button — even in an incognito window, so it was not
browser cache.

### Root Cause

`tenancy.context_processors.company_features` pre-serialized the feature map
with `json.dumps()` and passed that **string** to the `json_script` template
filter in `base.html`. `json_script` JSON-encodes whatever it receives, so the
map was double-encoded: `JSON.parse` in the browser returned a *string*, not
an object. `window.FinanceeFeatures["excel_export"]` was therefore
`undefined`, and `financeeFeatureEnabled()` — which deliberately fails open
for unknown keys — reported every feature as enabled. Server-side rendering
(sidebar, template-gated buttons, middleware URL blocking) uses the `features`
dict directly and was unaffected, which made the page look "half gated".

The test suite missed it because the Django test client never executes JS,
and the server-side substring assertions matched the escaped string too.

### Fix

- `tenancy/context_processors.py` now exposes only the raw `features` dict;
  `templates/base/base.html` passes that dict straight to
  `json_script` (which performs the one and only serialization).
- `tests/suite/test_feature_flags.py` now asserts the page embeds a JSON
  **object** (the literal substring `"excel_export": {"enabled": ...` — a
  double-encoded string would have `\"`-escaped quotes), in both the enabled
  and disabled states, so this class of bug fails the suite.

### Verification

`tests/suite/test_feature_flags.py` — 76/76 (includes the two new
double-encoding guards); rendered `/accountsReports/stock-summary/` as a
Company_2 member and confirmed the embedded `financee-features` script starts
with `{` and carries `"excel_export": {"enabled": false`.

## 2026-07-08: 502 Bad Gateway After Rebuilding Only the web Container

### Symptoms

After `docker compose up -d --build web`, browsing `http://localhost/`
returned `502 Bad Gateway (nginx)`, while the web container was healthy and
answering its own healthcheck.

### Root Cause

Nginx resolves the `web` upstream hostname **once at startup**. Recreating the
web container gives it a new internal Docker IP; the long-running nginx
container kept proxying to the old IP (`connect() failed (111: Connection
refused) ... upstream: "http://172.19.0.3:8000"` in `logs nginx`).

### Fix / Operational Rule

Restart nginx whenever the web container is recreated:

```bash
docker compose -f deploy/docker-compose.yml restart nginx
```

Diagnosis recipe: `ps` (is web healthy?), `logs --tail=100 web` (backend
tracebacks?), `logs --tail=50 nginx` (stale-upstream connection refused =
this issue).

**Permanent fix applied later the same day** (with the CI/CD work): the static
`upstream` block in `deploy/nginx/financee.conf` was replaced with
`resolver 127.0.0.11 valid=10s` + a variable `proxy_pass`, so nginx re-resolves
the `web` hostname at request time. Verified by force-recreating the web
container without touching nginx: port 80 answered 200 within 5 seconds
(previously a permanent 502 until an nginx restart). The `restart nginx` rule
above is now only needed on stacks without the updated config.

## 2026-07-03: Cash-Party Feature Ported to All Tenants (last drift item healed)

### Symptoms

The cash-party feature (`parties.is_cash`, `get_cash_party_id`, cash-aware
journal builders) existed only on `tenant_company_2` (deferred item #5 of the
2026-07-01 drift heal; tracked in `todo.md`). On `tenant_company_1`:

- The cash sale/purchase path in `sale/views.py` / `purchase/views.py` calls
  `get_cash_party_id(...)` and reads `COALESCE(is_cash,false)` unconditionally,
  so submitting a cash sale/purchase **errored** (the function and column did
  not exist) — worse than the silent AR/AP misclassification originally feared.
- The invoice-description feature was also missing (no `description` columns on
  `salesinvoices`/`purchaseinvoices`/`salesreturns`/`purchasereturns`; older
  `get_current_*` fetchers read `je.description`), and the views' description
  `UPDATE` would fail.

### Root cause

`add_cash_transactions.sql`, `add_cash_party_ledger.sql`, and
`add_invoice_description.sql` were applied to `tenant_company_2` but never to
`tenant_company_1` — classic tenant drift. The port had been deferred over fear
that replaying `add_cash_transactions.sql` would overwrite integrity-fixed
functions. Live-DB inspection (pg_get_functiondef diffs on both tenants) showed
the fear was moot: **no integrity patch redefines the four `rebuild_*` journal
builders or `detailed_ledger`/`detailed_ledger2`** — the COGS-reflow fix only
*calls* `rebuild_sales_journal`. The cash-aware bodies live on
`tenant_company_2` were byte-identical to the patch files and already pass the
full suite + deep lifecycle together with the integrity guards.

### Fix

Added `tenancy/sql/fix_cash_party_port.sql` (idempotent; folded into
`tenant_template.sql`, `production_hardening.sql`, and
`build_multitenant_db.sql`; tenant schema version bumped to **5**):

1. Invoice-description prerequisite: the four `description` columns and the
   four read-only `get_current_*` fetchers (from `add_invoice_description.sql`).
2. `parties.is_cash` + `get_cash_party_id(kind)`.
3. The four cash-aware `rebuild_*` journal builders (bodies proven on
   `tenant_company_2`).
4. Cash-aware `detailed_ledger` / `detailed_ledger2` (also carry the
   description enrichment).
5. Eager seeding of the "Cash Sale" / "Cash Purchase" sentinel parties.
6. **Pre-flag journal backfill** (added after the port, same day): documents of
   a cash party posted *before* the party carried `is_cash = true` had journals
   with party AR/AP lines instead of Cash lines. They were invisible to the
   cash-party ledger (which reads Cash-account lines of the party's documents)
   and left a residual, never-collectable party balance (`Cash Sale` on
   `tenant_company_1` sat at +500 AR). The patch rebuilds the journal of every
   cash-party document whose journal still carries a party-tagged line — a
   balance-sheet-neutral swap (AR/AP → Cash) that is a no-op on later runs.
   Symptom that surfaced it: the Detailed Ledger for "Cash Sale"/"Cash
   Purchase" appeared to show only returns. (Also note: seeded test invoices
   carry fixture dates in 2025 while returns default to `CURRENT_DATE`, so a
   date range starting in 2026 legitimately excludes those invoices.)

`tests/suite/test_sales.py` now asserts the cash path unconditionally on every
tenant (feature-detection branch removed) and checks the sentinel parties and
`get_cash_party_id` resolution.

### Verification

```bash
docker compose -f deploy/docker-compose.yml exec -T web \
  python manage.py apply_sql_all_tenants tenancy/sql/fix_cash_party_port.sql
docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py
docker compose -f deploy/docker-compose.yml exec web python tests/test_transaction_lifecycle_deep.py
```

Result: suite `ALL MODULES PASSED` (both tenants at 60/60 reports, 30/30 sales
including the cash path on each; 70/70 HTTP); deep lifecycle fully passed on
both tenants; the updated `tenant_template.sql` builds cleanly in a throwaway
schema; the updated `production_hardening.sql` reruns cleanly on both tenants
(it self-heals this feature on container start). Both tenants report
`tenant_schema_version = 5` and 2 seeded cash parties.

## 2026-07-01: Full-System Test Suite Added; Tenant Schema Drift Diagnosed

### Summary

A comprehensive test suite was added under `tests/suite/` covering every domain
(parties, items, purchases, sales, returns, cash movement, opening cash/stock,
owner equity, month close), every report (accounts, stock, serial, sales
analytics, monthly, dashboard functions + views), and the HTTP endpoint layer.
It runs against every active tenant and asserts real accounting invariants
(double-entry balance, party balances, COGS, stock/serial coherence). Latest
run: **ALL MODULES PASSED** (570 real checks across both tenants).

Run it with:

```bash
docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py
```

Details and per-module counts are in `tests/suite/RESULTS.md`.

### Tenant schema drift — diagnosed and healed

The suite surfaced that several idempotent `tenancy/sql/` patches had been applied
to one tenant but not the other. These were healed by
`tenancy/sql/fix_tenant_drift.sql` (idempotent; applied to all tenants and folded
into `tenant_template.sql`, `production_hardening.sql`, and
`build_multitenant_db.sql`; tenant schema version bumped to 4).

1. **Fixed** — `create_purchase_return` on `tenant_company_1` had **no in-stock
   guard**: a sold serial could be purchase-returned and serials double-returned
   (`tenant_company_2` already blocked both). The guard was added on all tenants.
   A fresh `CREATE OR REPLACE` was used rather than replaying the historical
   `fix_return_serial_integrity.sql`, because that older patch also redefines
   `create_sale_return`/`update_sale_return` and would have regressed the later
   sale-return lifecycle guards.
2. **Fixed** — `item_transaction_history(text)` (1-arg) was ambiguous on
   `tenant_company_1` (a 3-arg-with-defaults variant collided). The redundant
   1-arg overload was dropped; the 3-arg defaulted form covers 1-arg calls, as on
   `tenant_company_2`.
3. **Fixed** — `get_item_names_like` was broken on PostgreSQL 16 (ambiguous
   `item_name`) on both tenants; the column is now qualified. (It is not used by
   the active item autocomplete, which runs an inline query, but is now correct.)
4. **Not a report** — `item_history_view` existed only on `tenant_company_1` and
   was hardcoded to `%iPhone 15 Pro%` (a debug artifact). It is left in place and
   excluded from the suite rather than replicated.
5. **Deferred** — the cash-party feature (`parties.is_cash`, `get_cash_party_id`)
   is absent on `tenant_company_1`. Porting it means replaying
   `add_cash_transactions.sql`, which redefines `rebuild_*` journal functions and
   risks regressing the transaction-integrity fixes, so it was intentionally left
   for a dedicated migration. The suite feature-detects and exercises the cash
   path only where the feature is present.

### Verification

```bash
docker compose -f deploy/docker-compose.yml exec -T web \
  python manage.py apply_sql_all_tenants tenancy/sql/fix_tenant_drift.sql
docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py
docker compose -f deploy/docker-compose.yml exec web python tests/test_transaction_lifecycle_deep.py
```

Result: suite `ALL MODULES PASSED` with 0 `XFAIL`; deep lifecycle 2702/2702 on
both tenants; the folded `tenant_template.sql` builds cleanly.

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
All CI/CD is applied
```
