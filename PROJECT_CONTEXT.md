# Project Context

Last updated: 2026-07-27

This file is the persistent engineering context for Financee. Update it on every meaningful project change, especially changes to architecture, routes, permissions, tenant SQL, deployment behavior, environment variables, tests, or data model assumptions.

## Session Resume Checkpoint

- **Last completed phase:** Phase 27 — CI/CD and ARM64.
- **Next phase:** Phase 28 — Backup, Restore, Migration, and Rollback
  Rehearsal.
- **Phase 27 status:** complete. PR and main T8 gates passed, the immutable
  multi-architecture image was published, and EC2 deployment stopped at the
  protected production approval boundary. Evidence:
  `tests/PHASE27_CICD_ARM64_RESULTS.md`.
- **Phase 26 delivered:** a 2-vCPU/4-GiB constrained capacity profile,
  production PostgreSQL/Gunicorn tuning, 100,000 SKUs, five million movements,
  100,000 units, 100 simultaneous sessions, real 100,000-row CSV export,
  representative daily writes, 10,000-event FIFO replay, report timing,
  resource/lock/restart telemetry, reconciliation report optimization, and
  complete serial/quantity/isolation regression.
- **Phase 26 evidence:** `tests/PHASE26_PERFORMANCE_CAPACITY_RESULTS.md` and
  `tests/phase26_target_results.json`.
- **Quantity schema development baseline:** version 22.
- **Phase 22 delivered:** central mode-aware 40-report catalogue, validated
  report-filter contract, accounting/stock/FIFO/sales/purchase/return and
  reconciliation SQL, quantity dashboard dispatch, permission and feature
  enforcement, responsive report UI, and CSV plus native Excel exports.
- **Phase 22 evidence:** `tests/PHASE22_QUANTITY_REPORTS_DASHBOARDS_RESULTS.md`.
- **Phase 23 delivered:** a permanent two-tenant quantity certification gate
  covering the complete domestic lifecycle, shared financial activity, every
  quantity report, hostile inputs, isolation, inventory and journal
  reconciliation, repeat rollout/hardening, monotonic upgrade registration,
  P0/P1 evidence mapping, identical schema fingerprints, and zero quantity
  XFAIL.
- **Phase 23 evidence:** `tests/PHASE23_COMPLETE_QUANTITY_SUITE_RESULTS.md`.
- **Phase 24 delivered:** a permanent two-fresh-serial-tenant matrix that
  reruns unchanged legacy domains, system functions, and deep lifecycle;
  compares the Phase 1 schema, accounting, and report contracts; reapplies
  serial hardening/indexes; rejects XFAIL; and proves quantity database, route,
  and navigation surfaces remain absent.
- **Phase 24 evidence:** `tests/PHASE24_COMPLETE_SERIAL_REGRESSION_RESULTS.md`.
- **Phase 25 delivered:** a permanent four-company mixed-mode concurrency
  matrix (two serial, two quantity) covering simultaneous posting, returns,
  transfers, counts, reports, exports, attachment probes, logouts, persistent
  connections, rate-limit cache separation, exception reset/scrubbing, schema
  mismatch rejection, and final `public` search paths. It also fixed
  tenant-scoped rate-limit keys, real JSONB report response decoding, and the
  completed quantity home/attachment/audit route allowlist.
- **Phase 25 evidence:** `tests/PHASE25_FOUR_COMPANY_ISOLATION_RESULTS.md`.
- **Phase 20 delivered:** quantity attachments and lifecycle cleanup, smart
  descriptions, immutable cross-module audit events, new platform permissions,
  a permission-gated audit UI/API, type-aware feature catalogue/route guards,
  and verified shared subscription enforcement.
- **Phase 20 evidence:** `tests/PHASE20_QUANTITY_PLATFORM_CONTROLS_RESULTS.md`.
- **Phase 21 delivered:** central trusted-company capability dispatch,
  cross-family payload rejection, shared quantity JSON/multipart parsing,
  mode-aware template context/navigation, authoritative purchase/sale previews,
  quantity warehouse management, and shared loading, Alerts, keyboard,
  responsive, and accessibility behavior.
- **Phase 21 evidence:** `tests/PHASE21_TYPE_AWARE_UI_RESULTS.md`.
- **Phase 19 delivered:** quantity-compatible shared party and opening-balance
  contracts, payments, receipts, contra, opening cash, owner equity, period
  preview/close/reversal, shared financial UI routes, and universal closed-
  period guards across quantity inventory and financial mutations.
- **Phase 19 evidence:** `tests/PHASE19_QUANTITY_FINANCIAL_MODULES_RESULTS.md`.
- **Phase 18 delivered:** foreign/base invoice and line snapshots, durable
  payment/receipt allocations, partial/final cash or bank settlement, realized
  exchange gain/loss journals and reporting, unsettled-balance-aware foreign
  returns, and purchase/sale currency and settlement UI.
- **Phase 18 evidence:** `tests/PHASE18_QUANTITY_CURRENCY_RESULTS.md`.
- **Required Phase 17 scope:** tax/non-tax configuration, inclusive/exclusive
  calculations, discounts, historical snapshots, returns, and control accounts.
- **Phase 17 delivered:** tenant tax-environment snapshots,
  tax-code/control-account administration functions, immutable document
  calculation columns, and the canonical inclusive/exclusive discount-before-
  tax calculator with deterministic invoice-discount allocation.
- **Phase 17 evidence:** `tests/PHASE17_QUANTITY_TAX_DISCOUNTS_RESULTS.md`.
- **Preserve:** all serial-company behavior and the completed quantity schema
  version 12 count/adjustment lifecycle.
- **Do not commit or push:** provide commit text to the owner after Phase 25;
  the owner performs the commit.

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

## CI/CD

- `.github/workflows/ci.yml`: on every push/PR — `checks` job (django check +
  missing-migration guard on a plain runner) and `test` job (builds the
  production image, boots the real compose stack with a throwaway
  `deploy/.env`, bootstraps a CI superuser + a second tenant via
  `provision_tenant`, and runs `tests/suite/run_all.py`, `test_system.py`,
  `test_http.py`, `test_transaction_lifecycle_deep.py` inside the container).
  On `main` the tested image is pushed to
  `ghcr.io/maaz-bin-haider/financee-web` (`<sha>` + `latest`).
- `deploy` job: gated by repo variable `DEPLOY_ENABLED=true` AND manual
  approval via the `production` GitHub environment; SSHes to EC2 (secrets
  `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY`/optional `EC2_APP_DIR`) and runs
  `deploy/deploy_pull.sh` with the SHA tag.
- `deploy/deploy_pull.sh`: pull-based deploy — pulls the pinned image,
  recreates web+nginx, health-checks through nginx, rolls back web to the
  previous image on failure, then `apply_sql_all_tenants tenant_indexes.sql`.
  `deploy/deploy.sh` stays as the manual build-on-server fallback. DB changes
  are not rolled back — keep migrations/tenant SQL backward-compatible.
- `deploy/docker-compose.yml` web service now carries
  `image: ${WEB_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:latest}` so local
  builds tag the same name CI pushes and the server can `compose pull web`.
- Nginx stale-upstream fix (2026-07-08): the shared `location /` (now in
  `deploy/nginx/financee_common.conf`) uses `resolver 127.0.0.11` + variable
  `proxy_pass` instead of a static `upstream` block, so recreating web never
  needs an nginx restart (upstream `keepalive` was retired with it; negligible
  on the Docker network).
- HTTPS / custom domain (2026-07-09): production domain
  `financee-swisstech.com` (+ `www`) is on **Cloudflare, proxied**, TLS handled
  by a **Cloudflare Origin Certificate** on nginx with SSL mode **Full
  (strict)** — no certbot/Let's Encrypt, no renewal (15-yr cert). Nginx config
  is split so the HTTP (`financee.conf`, port 80, kept for localhost health
  checks) and HTTPS (`financee_tls.conf`, port 443) servers share one body
  (`financee_common.conf`) and cannot drift. The 443 listener + cert mount
  (`/etc/nginx/cloudflare/{origin.pem,origin.key}`, server-only, uncommitted)
  live in the `deploy/docker-compose.tls.yml` overlay, which
  `deploy_pull.sh`/`deploy.sh` add **automatically once `origin.pem` exists on
  the host** (HTTP-only before that — no flag day). Local dev + the CI test job
  use base `docker-compose.yml` only, so neither needs a cert. Once HTTPS is
  live, drop `SECURE_COOKIES=False` from the server `.env` and set
  `CSRF_TRUSTED_ORIGINS` to the `https://` origins. Full runbook:
  `DEPLOYMENT_GUIDE.md` Part F.

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

## Subscription Control (manual billing, admin-driven)

Clients pay monthly outside the system (direct bank transfer, no payment
gateway). The operator controls access entirely from the custom admin panel.
Everything lives in the **public** schema (Django ORM) — no tenant SQL involved.

Data model (`tenancy/models.py`, migration `tenancy/0002_subscription_control`):

- `Company.paid_until` (date, nullable): subscription paid through this date
  (inclusive). **NULL disables enforcement** for that company (default for
  pre-existing companies, so the migration blocks nobody).
- `Company.grace_days` (default 3): extra access days after `paid_until`
  before the automatic block.
- `Company.warn_days_before` (default 7): renewal banner window before expiry.
- `Company.is_suspended`: manual kill switch, blocks immediately regardless of
  dates.
- `SubscriptionPayment`: immutable audit log (company, amount, date_received,
  months_covered, note, paid_until_after, created_by). Saving a **new** payment
  atomically extends `paid_until` by `months_covered` — from the current
  `paid_until` if still in the future, else from `date_received` (calendar-aware
  month math via `add_months`, clamping e.g. Jan 31 + 1 → Feb 28) — and clears
  `is_suspended`. Edits/deletes never re-shrink `paid_until`.
- `Company.subscription_state()` returns one of `unrestricted / active /
  expiring / grace / blocked / suspended`; `BLOCKED_STATES = {suspended,
  blocked}` deny access.

Enforcement (`tenancy/middleware.py` + `financee/security.py`):

- `TenantSchemaMiddleware._resolve_schema` now also returns the `Company`
  (stored as `request.tenant_company`; zero extra queries). `process_view`
  checks `subscription_state()` after the tenant guard and before permissions.
- Blocked users get `subscription_blocked_response()`: a branded 403
  suspension page (`templates/tenancy_templates/subscription_suspended.html`)
  that mentions the overdue payment; AJAX/API paths get scrubbed 403 JSON.
- Exemptions: **superusers are never blocked** (the operator), and
  `TENANT_GUARD_EXEMPT_PREFIXES` (`/admin/`, `/authentication/`, `/static/`,
  `/media/`) stay reachable — login/logout always work; users log in and land
  on the suspension page. `Company.is_active` remains the separate,
  pre-existing hard registry switch (generic 403, middleware `tenant_ok=False`).
- Warning banner: middleware stamps `request.subscription_state`; the
  `tenancy.context_processors.subscription_notice` context processor
  (registered in settings) feeds a dismissible banner in
  `templates/base/base.html` for the `expiring`/`grace` states (dismissal is
  per-session via sessionStorage). Styles in `static/css/subscription.css`
  (banner + suspension page, incl. dark mode).

Admin (`tenancy/admin.py`, superuser-only custom site):

- Company changelist shows a muted subscription badge (Not enforced / Active /
  Expires {date} / Grace until {date} / Blocked — unpaid / Suspended; pill
  styles `.pill-warn`, `.pill-grace` added to `financee_admin.css`), plus
  `paid_until` and an `is_suspended` filter. Bulk actions: suspend / lift
  suspension.
- Company change form has a Subscription fieldset and a Subscription payments
  inline (add-only; existing rows immutable). Recording a payment there or in
  the standalone Subscription payments admin extends access and lifts
  suspension in one step; `created_by` is stamped automatically.
- Admin index gained two KPI cards — Client Companies (soft slate) and Blocked
  Subscriptions (soft red, `.fin-kpi.red`) — and quick links to Companies &
  Subscriptions and Subscription Payments.

Tests: `tests/suite/test_subscription.py` (wired into `run_all.py`) covers the
state machine boundaries, payment-extension math, and HTTP enforcement
(suspension page, JSON denial, logout exemption, superuser exemption,
banner rendering, payment-restores-access). It mutates only public-schema
registry fields and restores them in `finally`.

### Subscription notification emails

Automatic emails to the **company's billing address** (`Company.contact_email`
— never to individual users), fully configured from the admin panel. Migration
`tenancy/0003_subscription_emails`; engine in `tenancy/subscription_emails.py`.

- Two date-driven emails per billing cycle: **expired** (sent the day
  `paid_until` lapses: "you have N grace days, access restricted after X") and
  **suspended** (sent the day the grace window ends: "access is suspended,
  resumes after payment"). Companies with `is_suspended=True` are skipped by
  the scanner — the operator-triggered email covers them.
- `BillingSettings` (singleton, `tenancy_billing_settings`): sender account
  (SMTP host/port/TLS + sender email + **app password**, defaults to Gmail
  smtp.gmail.com:587 TLS), `emails_enabled` master switch, and the contact
  details embedded in every email (WhatsApp number, phone, free-text note).
  Its admin changelist redirects to the single change form, which has a
  **Send a test email** button (custom admin URL
  `tenancy_billingsettings_test_email`).
- `SubscriptionEmailLog` (`tenancy_subscription_email_log`): audit trail and
  dedup guard. Date-driven sends INSERT the row first under the unique
  `(company, kind, paid_until)` constraint (condition: date-driven kinds only),
  so a cycle can never email twice across gunicorn workers; a `failed` row is
  reclaimed and retried on the next scan. Read-only in the admin (no
  add/change/delete — deleting a sent row would allow a duplicate email).
- Delivery loop: `start_email_scheduler()` is invoked from **`financee/wsgi.py`**
  (only serving processes, never management commands) and runs an hourly
  daemon-thread scan; workers coordinate via a shared-cache tick lock
  (`subscription_email_tick`, Redis in production). Manual run:
  `python manage.py send_subscription_emails [--dry-run]`.
- Manual suspension from the admin (Suspend action or ticking Suspended on the
  form) sends the suspension email immediately (`manual_suspension` kind, no
  dedup) and reports the outcome via admin messages.
- `SUBSCRIPTION_EMAIL_BACKEND` (optional Django setting) overrides the mail
  backend — the test suite points it at locmem.
- Tests: `tests/suite/test_subscription_emails.py` (singleton behavior,
  scanner states/dedup/retry, content incl. WhatsApp/contact details, manual +
  test emails, admin screens and suspend-action email). Nothing real is sent.

## Per-Company Feature Flags (admin-controlled)

The operator can switch features on/off **per company** from the company admin
form. Everything lives in the public schema — no tenant SQL. Migration
`tenancy/0004_company_feature_flags`; registry and enforcement helpers in
`tenancy/features.py`.

Feature keys (stable, persisted): group switches `accounts_reports`,
`stock_reports`, `monthly_reports`, `sales_reports`, `opening_stock`,
`opening_cash`, `excel_export`, `attachments`, plus one `group.sub` switch per
sub-report of the four report groups (e.g. `accounts_reports.cash_ledger`,
`stock_reports.serial_ledger`, `monthly_reports.monthly_income`,
`sales_reports.trend`). Sub key names follow the URLs; admin labels follow the
UI button text (note `/detailed-ledger/` renders as "Party Ledger" and
`/detailed-ledger2/` as "Detailed Ledger"; `/stock-summary/` as "Stock Report"
and `/stock-report/` as "Stock Serial Wise").

Semantics and storage:

- `Company.disabled_features` (JSONField, list of **disabled** keys; default
  `[]` = everything on, so the migration changes nothing for existing
  companies). `Company.feature_enabled(key)` — disabling a group disables all
  of its subs; unknown keys fail open.
- `excel_export` removes only the **CSV/Excel** download buttons across all
  report screens plus Month-End Close and Owner Equity; PDF and Print stay.
- `attachments` hides the whole document-attachment widget (upload **and**
  existing-file preview/download) and blocks `/attachments/`; files are never
  deleted, so re-enabling restores them. `attachments/utils.py`
  (`validate_request_attachments` raises / `save_document_attachments`
  no-ops) guards uploads server-side.

Enforcement (`tenancy/middleware.py` after the subscription guard, applied to
**every** user of the company, superusers included):
`tenancy.features.feature_for_path` longest-prefix-maps the request path to a
feature key; disabled paths get `feature_disabled_response`
(`financee/security.py`): non-GET/AJAX/API → scrubbed 403 JSON ("This feature
is not enabled for your company."); a plain GET on a disabled **sub-report
page** redirects to the first enabled sibling of the group
(`GROUP_LANDING_PATHS`) so sidebar entry points keep working, else to the
dashboard.

UI hiding: `tenancy.context_processors.company_features` (registered in
settings) exposes `features` (nested map) to every template. `base.html`
gates the sidebar links and embeds `window.FinanceeFeatures` +
`financeeFeatureEnabled()` by passing the **raw dict** through `json_script`
(pre-serializing with `json.dumps` double-encodes it into a string and every
JS feature check fails open — the suite asserts the page embeds a JSON
object) for the JS-built toolbars (`accounts_reports.js`, `stock_reports.js`,
`detailed_ledger2.js` gate their CSV buttons; report-page init handlers now
start on the first *visible* report button). The report templates gate each
sub-report button; the 7 document templates gate the attachment widget
include.

Admin (`tenancy/admin.py`): `CompanyAdminForm` renders the JSON column as
grouped Boolean switches (one collapsible fieldset per group, master switch +
sub switches; unticked = disabled); the changelist shows a "Features off"
count. Tests: `tests/suite/test_feature_flags.py` (wired into `run_all.py`).

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
- Admin home KPI cards use subtle per-card accent colors: soft blue for total users, soft violet for superusers, soft green for active users, soft slate for groups and client companies, soft amber for recorded actions, and soft red for blocked subscriptions. These accents should stay muted, not vibrant.
- Admin action buttons follow a semantic color system: default/primary buttons are dark grey with off-white text, add buttons are light green with dark green text, change/reset-password buttons are light yellow with dark muted-yellow text, and delete buttons are light red with maroon text.
- Avoid light-blue page/panel backgrounds throughout the admin. Panels, selector widgets, changelist headers, filter areas, and recent-action bodies should remain off-white or neutral.
- Admin links should generally be grey and non-underlined. The Financee brand mark can remain blue; filled primary controls may use dark grey rather than blue.
- The admin dashboard must remain single-column/responsive: recent actions stack below the main dashboard, and changelist/filter panels must fit small laptops and iPad widths without horizontal scrolling.
- Avoid inline styles in admin templates; put layout, spacing, and color in `financee_admin.css` so small laptop and iPad behavior stays consistent.

## Dark Mode (temporarily retired) & Sidebar Identity

- Dark mode is **temporarily retired** pending a rework (2026-07-06). The
  tenant sidebar toggle, the early theme-apply scripts, and the
  `dark_mode.js` include in `templates/base/base.html` are **commented out**
  (not deleted, per project convention); `static/js/dark_mode.js` and
  `static/css/dark_mode.css` remain in the tree for the future rework. Stored
  `localStorage` theme preferences are ignored — everyone gets light mode.
- The admin is locked to the light theme: `templates/admin/base_site.html`
  blanks Django's `{% block dark-mode-vars %}` (drops the admin dark CSS
  variables and `theme.js`), and `templates/admin/color_theme_toggle.html` is
  a blank override of the stock toggle. Delete that override and restore the
  block to bring the stock behavior back.
- The tenant sidebar footer shows the logged-in username **and the company
  name** (`request.tenant_company.name`, server-rendered, hidden when the
  request has no tenant company). Styles: `.company_name` in
  `static/css/base_styling.css`.

## Frontend Alert Layer (SweetAlert2)

All user-facing alerts go through a single helper, **`static/js/alerts.js`** (global `Alerts`), which wraps SweetAlert2 v11. Animations and per-type theming live in **`static/css/alerts.css`**. Both are loaded in `templates/base/base.html` immediately after the SweetAlert2 CDN, and also directly in `templates/authentication_templates/login_template.html` (the only page that does not extend `base.html`). **Do not call `Swal.fire` directly in new code — use the `Alerts` helper** so behavior stays consistent system-wide.

The five standardized types and their fixed placement/behavior:

| Helper | Use | Position | Dismissal | Buttons |
| --- | --- | --- | --- | --- |
| `Alerts.success(msg, {title})` | an action completed | top-right toast | auto ~2.5s | none |
| `Alerts.error(msg, {title})` | an action failed | top-right toast | **manual close only (no timer)** | none (close ×) |
| `Alerts.notify(msg, {title})` | neutral status / navigation boundary | top-right toast | auto ~3s | none |
| `Alerts.warning(msg, {title})` | validation / can't-proceed | bottom-center toast | auto ~4s | none |
| `Alerts.confirm({title,text,confirmText,danger})` → `Promise<boolean>` | consequential/irreversible action | centered modal | — | Confirm + Cancel |

Plus `Alerts.loading(msg)` / `Alerts.close()` (centered blocking spinner) and `Alerts.dialog(opts)` (centered modal for detail/history views and date-range/bulk-paste input forms — pass raw SweetAlert2 options like `html`, `preConfirm`, `didOpen`). `Alerts.raw` exposes the underlying `Swal`.

Conventions:
- **Only consequential actions get a confirmation dialog** (deletes, month close/reverse, opening-balance reclassify, sale-price-override). Everything else is a non-blocking toast.
- Message text is the first arg; `{ title }` overrides the default heading. `.then()` chains are preserved (success/confirm return the SweetAlert2 promise; `confirm` resolves to a boolean).
- Animations are defined as keyframe classes in `alerts.css` and referenced via SweetAlert2 `showClass`/`hideClass`; they honor `prefers-reduced-motion`. Put alert styling there, not inline.
- The migration commented out (did not delete) the previous inline `Swal.fire` calls across `static/js/*.js` and the feature templates, leaving `Alerts.*` calls in their place.

## Test Strategy

- `tests/test_system.py` exercises tenant stored functions and report functions through direct SQL.
- `tests/test_http.py` exercises real Django endpoints through the Django test client.
- `tests/test_transaction_lifecycle_deep.py` stress-tests real serial lifecycles across purchase, sale, sale return, resale, second return, purchase return, mixed purchase invoice corrections, partial returns, sale-return update/delete after resale, sale invoice update/delete after returns, cash-sale vs credit-sale returns, multi-item mixed serial invoices, and report execution after every entry.
- `tests/test_transaction_lifecycle_deep.py` also asserts financial invariants at every checkpoint (trial balance balances, no orphaned journal lines, no negative amounts, in_stock vs active-Sold coherence) and supports a `known_bug`/`XFAIL` channel for documenting confirmed-but-unfixed defects without failing the suite.
- `tests/TRANSACTION_LIFECYCLE_FLOW_RESULTS.md` records the latest deep lifecycle flow matrix and current pass/fail status.
- `tests/suite/` is the comprehensive full-system suite (own harness `_harness.py`, one module per domain plus `test_reports.py` for every report and `test_http.py` for endpoints; run with `python tests/suite/run_all.py`). It runs against every active tenant and asserts real accounting invariants (double-entry balance, party balances, COGS, stock/serial coherence), not just "did not error". It reuses the `XFAIL`/`known_bug` convention. See `tests/suite/README.md` and `tests/suite/RESULTS.md`.
- `tests/suite/test_subscription.py` covers the subscription-control layer: the paid-until/grace/suspension state machine, calendar-aware payment extension, and HTTP enforcement (suspension page, JSON denial, exemptions, warning banner).
- `tests/suite/test_subscription_emails.py` covers the subscription email layer: BillingSettings singleton, expiry/suspension emails with per-cycle dedup and failure retry, contact-detail embedding, manual-suspension/test emails, and the admin email screens (locmem backend, nothing real sent).
- `tests/suite/test_attachments.py` adds dedicated document-attachment coverage for sale, purchase, sale return, purchase return, payment, receipt, and contra documents: upload/update/replacement, preservation of the unselected file kind, metadata/preview/download endpoints, invalid file validation, cleanup, failed-delete preservation, attachment-only bypass for sale/purchase/returns, and no bypass for payments/receipts/contra.
- `tests/run_tests.sh` runs both harnesses in Docker and can reset tenant schemas with `--reset`.

## Document Attachment Feature

The `attachments` app adds optional image/PDF support for sale, purchase, sale return, purchase return, payment, receipt, and contra documents.

- Tenant SQL: `tenancy/sql/add_document_attachments.sql` creates `document_attachments` with `(document_type, document_id, file_kind)` uniqueness. It is folded into `tenancy/sql/tenant_template.sql`, `tenancy/sql/production_hardening.sql`, and `build_multitenant_db.sql`; tenant schema version is 6.
- Storage: metadata lives in the active tenant schema; file bytes live below `PRIVATE_MEDIA_ROOT/document_attachments/<tenant>/<document_type>/<document_id>/`. `financee/settings.py` defines `MEDIA_ROOT` and `PRIVATE_MEDIA_ROOT`.
- Security: `/attachments/<document_type>/<document_id>/` returns metadata only. Preview/download endpoints stream the file through Django after authentication, tenant activation, and the relevant view permission check. Nginx blocks direct `/media/private/` access.
- Limits: one image and one PDF per document. Images are JPG/JPEG, PNG, WEBP, or GIF up to 10 MB. PDFs are `application/pdf` up to 20 MB.
- Replacement semantics: uploading a new image replaces only the image; uploading a new PDF replaces only the PDF. Missing file kinds on update are preserved.
- Delete semantics: document delete flows call attachment cleanup only after the business delete succeeds, so a failed accounting/inventory delete does not remove files.
- Frontend: `templates/components/document_attachments.html`, `static/css/document_attachments.css`, and `static/js/document_attachments.js` provide the shared widget. Metadata loads asynchronously after the business document renders; file bytes load only on explicit preview/download.
- Update locking: sale, purchase, sale-return, and purchase-return views detect attachment-only updates and save files without calling the stored update function when the submitted business payload matches the current document. Payments, receipts, and contra intentionally do not use this bypass.

## Tenant Schema Drift (fully healed)

The `tests/suite/` run surfaced idempotent `tenancy/sql/` patches applied to one tenant but not the other. Most were healed by `tenancy/sql/fix_tenant_drift.sql` (tenant schema version 4); the final deferred item — the cash-party feature — was ported by `tenancy/sql/fix_cash_party_port.sql` (tenant schema version 5, 2026-07-03). See `FIXED_ISSUES.md` and `tests/suite/RESULTS.md`.

- Fixed (v4): `create_purchase_return` in-stock guard added on all tenants; redundant ambiguous `item_transaction_history(text)` 1-arg overload dropped; `get_item_names_like` ambiguous column qualified.
- Fixed (v5): cash-party feature (`parties.is_cash`, `get_cash_party_id`, cash-aware `rebuild_*` journal builders, cash-aware `detailed_ledger`/`detailed_ledger2`) and its invoice-description prerequisite (`description` columns + `get_current_*` fetchers) are now on **every** tenant; the "Cash Sale"/"Cash Purchase" sentinel parties are seeded eagerly. The suite asserts the cash-sale path unconditionally.
- Not a report: `item_history_view` (present only on `tenant_company_1`) is a hardcoded debug artifact, excluded from the suite.

Always roll out tenant SQL to **all** tenants via `apply_sql_all_tenants` to prevent widening drift.

## Current Tenant SQL Hardening

- `tenancy/sql/production_hardening.sql` is applied at Docker startup and includes sale-return lifecycle guards plus the transaction integrity guards below.
- `tenancy/sql/fix_sale_return_lifecycle_guards.sql` contains the standalone idempotent patch for active-sale return lookup and sale invoice mutation blocking after return history.
- `tenancy/sql/fix_transaction_integrity_guards.sql` (standalone idempotent patch, folded into template/hardening/bootstrap; tenant schema version 3) fixes three data-integrity defects: `delete_purchase` now blocks when serials have sale/purchase-return history; `create_sale`/`update_sale_invoice` reject a `qty` that does not match the serial count; `update_purchase_invoice` rebuilds the journals of sales that consumed the edited units so COGS stays in sync. See `FIXED_ISSUES.md`.
- `tenancy/sql/fix_tenant_drift.sql` (standalone idempotent patch, folded into template/hardening/bootstrap; tenant schema version 4) heals tenant drift found by `tests/suite/`: adds the `create_purchase_return` in-stock guard, drops the redundant ambiguous `item_transaction_history(text)` overload, and qualifies the ambiguous column in `get_item_names_like`.
- `tenancy/sql/fix_cash_party_port.sql` (standalone idempotent patch, folded into template/hardening/bootstrap; tenant schema version 5) ports the cash-party feature and its invoice-description prerequisite to every tenant: `parties.is_cash`, `get_cash_party_id`, the four cash-aware `rebuild_*` journal builders, cash-aware `detailed_ledger`/`detailed_ledger2`, the four invoice `description` columns, the description-aware `get_current_*` fetchers, and eager seeding of the "Cash Sale"/"Cash Purchase" parties. The journal-builder bodies are the ones proven live on `tenant_company_2` alongside the integrity guards (no integrity patch redefines them, so no regression risk). It also **backfills pre-flag journals**: cash-party documents posted before the party carried `is_cash` had AR/AP party lines instead of Cash lines (invisible to the cash-party ledger, residual party balance); the patch rebuilds any cash-party document journal that still carries a party-tagged line (balance-sheet neutral, no-op on reruns).
- `tenancy/sql/add_document_attachments.sql` (standalone idempotent patch, folded into template/hardening/bootstrap; tenant schema version 6) adds the generic `document_attachments` metadata table for sale, purchase, sale return, purchase return, payment, receipt, and contra files. Files are stored outside invoice JSON and served through authenticated Django endpoints so previous/next navigation remains lightweight.
- Keep `tenancy/sql/tenant_template.sql`, `build_multitenant_db.sql`, and `production_hardening.sql` aligned when tenant SQL behavior changes.

## Known Documentation Caveats

- The generated header comment in `financee/settings.py` says Django 5.2.6, but dependency files currently pin Django 6.0.6. Treat dependency files as source of truth unless code compatibility work says otherwise.
- Some view files retain older commented-out implementations. Active functions are the uncommented definitions later in the files.

## Approved Quantity-Company Requirements (Phase 0, 2026-07-25)

This is an approved design target, not an implemented feature. Existing
companies remain serial-based. A future quantity company will use a separate
schema family selected by an immutable company type during provisioning.

- Inventory: FIFO costing; no negative stock; clear insufficient-stock
  warnings; multiple warehouses; warehouse transfers; physical counts and
  controlled/audited adjustments.
- Quantities and units: `numeric(18, 3)` capacity; Pieces and Boxes must be
  whole numbers; Kilograms, Grams, Litres, and Metres may use up to three
  decimals; one inventory unit per item/variant and no unit conversions.
- Products: brand, model, color, storage, RAM, region, and condition variants.
  Every unique sellable combination has a unique SKU. The system suggests a
  SKU, which may be edited only before transactions exist.
- Transactions: backdating is allowed only in open periods and must safely
  rebuild FIFO/COGS without creating negative stock. Posted documents are
  editable only when downstream state can be atomically and safely rebuilt.
  Document types have independent, gap-preserving sequences such as
  `SAL-000001` and `PUR-000001`.
- Returns: sale returns restore exact original FIFO COGS; purchase returns use
  original purchase cost and require eligible stock; partial returns are
  allowed but cumulative returns cannot exceed the source line.
- Tax and discounts: company creation selects tax or non-tax environment.
  Tax names/codes/rates are tenant-configurable. Tax-based companies support
  inclusive/exclusive pricing, taxable/zero-rated/exempt lines, per-line
  calculation, invoice summaries, and optional exemption references. Percentage
  and fixed discounts work at line and invoice levels and reduce taxable value
  before tax by default. Applied calculation inputs are stored historically.
- Currency: admin selects the base currency from a worldwide catalogue during
  company creation. Foreign invoices store transaction currency, foreign
  amount, manually entered invoice rate, and base amount. Settlement stores its
  manual rate and automatically posts proportional realized exchange gain/loss,
  including partial settlements. No month-end unrealized revaluation is
  required.
- Reporting: the approved quantity report catalogue in `todo.md` replaces
  serial-only reports with movement, valuation, reconciliation, aging, reorder,
  margin, return-rate, purchase-variance, and fast/slow-moving reports.
- Validation target: four isolated companies (two serial and two quantity),
  concurrent tenant-leakage tests, 100 concurrent sessions, 100,000 SKUs, five
  million stock movements, ordinary reports under three seconds, and a pilot
  quantity wholesaler holding approximately 100,000 physical units across
  warehouses.
- Rollout: all three current paying companies remain serial-based. The first
  quantity company is a new pilot after staging, full regression, backup,
  security, performance, and rollback approval.

Full phase gates, report definitions, tests, and rollout tasks are maintained in
`todo.md`. The implementation-grade requirements baseline, requirement IDs,
origin labels, acceptance criteria, and traceability register are maintained in
`SRS_QUANTITY_BASED_COMPANY.md`. The authoritative implementation order,
mandatory per-phase test gates, evidence format, staging process, deployment,
rollback, pilot, and observation plan are maintained in
`IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md`.

The detailed plan intentionally divides delivery into 33 phases (0–32). Tests
are mandatory after every phase, including a relevant serial regression subset.
Dependent work does not begin until the previous phase exit gate passes.

Phase 1 completed on 2026-07-25 against two fresh isolated serial tenants. The
comprehensive suite, SQL harness, standalone HTTP harness, and deep lifecycle
tests all pass. The baseline also fixed two test/deployment defects:
`tests/test_http.py` now creates a temporary tenant membership and returns a
non-zero exit on reported problems, and the web entrypoint applies
`tenant_indexes.sql` so the bootstrap tenant receives the same required 50
secondary indexes as runtime-provisioned tenants. Evidence is in
`tests/PHASE1_BASELINE_RESULTS.md`.

Phase 2 completed on 2026-07-25 as a design-only gate. The approved dual-family
architecture, logical quantity data model, FIFO/source lineage, deterministic
backdated replay, canonical locks, idempotency, document lifecycles, precision,
capability/payload contracts, reconciliation, provisioning, and rollback design
are in `ARCHITECTURE_QUANTITY_COMPANY.md`. Requirement ownership and planned
test evidence are in `REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md`; review
evidence is in `tests/PHASE2_ARCHITECTURE_RESULTS.md`. No runtime code or SQL
was introduced in Phase 2.

Phase 3 completed on 2026-07-25. The public `Company` record now has an
`inventory_mode` constrained to `serial` or `quantity`; migration
`tenancy.0005_company_inventory_mode` safely assigns `serial` to all existing
and bootstrap companies. The mode is immutable after creation at both model
validation and normal `save()` boundaries, and the admin displays it as
read-only on existing companies. Quantity creation is intentionally rejected
until the quantity schema template and provisioning registry exist in Phase 5.
Upgrade, clean-install, migration rollback/reapply, 14 focused metadata checks,
all 16 suite modules, and the serial system/lifecycle regressions passed in
isolated Docker environments. Evidence is in
`tests/PHASE3_COMPANY_METADATA_RESULTS.md`. Base currency and tax-environment
configuration remain Phase 4 work.

Phase 4 completed on 2026-07-25. Public migration
`tenancy.0006_currency_company_setup` adds the controlled `Currency` catalogue,
required company base currency, and tax/non-tax environment. The frozen
catalogue contains 178 entries from the official SIX/ISO 4217 List One
published 2026-01-01; 165 entries with defined minor-unit precision are active
for selection. Existing companies are safely backfilled to PKR/non-tax without
changing tenant schemas or stored financial values. Base currency and tax
environment can be corrected before tenant journal activity and are locked
afterward. Admin and `provision_tenant` support the setup fields, and
`seed_currencies` refreshes catalogue data idempotently. Upgrade, clean install,
rollback/reapply, 30 focused checks, all 17 suite modules, and full serial
accounting/lifecycle regressions passed. Evidence is in
`tests/PHASE4_COMPANY_SETUP_RESULTS.md`.

Phase 5 completed on 2026-07-25. A central schema-family registry now owns
serial/quantity templates, hardening paths, required versions, fingerprints,
and runtime gates. Quantity schema version 1 is independently provisionable
from `quantity_tenant_template.sql` and maintained by the idempotent
`quantity_production_hardening.sql`; it contains family/base-currency metadata,
seed registry, document counters, a foundation sequence, and verification
functions, with no serial inventory tables. Public migration
`tenancy.0007_company_provisioning_state` adds pending/provisioning/ready/failed
operational states and sanitized failure codes. Provisioning verifies the
required fingerprint before commit, supports controlled failed-build retry, and
rollout commands enforce family/file ownership plus post-upgrade verification.
Middleware denies family/version/base-currency/fingerprint mismatch. Quantity
business routes remain intentionally gated until later functional phases.
Evidence from clean and upgraded mixed-family environments, 28 focused checks,
all 18 suite modules, and full serial accounting/lifecycle regressions is in
`tests/PHASE5_QUANTITY_FOUNDATION_RESULTS.md`.

Phase 6 completed on 2026-07-25. Quantity schema version 2 adds an idempotently
seeded 17-account system chart covering cash/bank, AR/AP, inventory, revenue,
COGS, opening balance, capital/retained earnings, input/output tax, inventory
adjustment gain/loss, realized exchange gain/loss, and rounding difference.
The base-currency ledger uses `numeric(24,4)` journal lines, immutable posted
journals, linked reversing journals, source-document uniqueness, and deferred
database constraint triggers that reject empty or unbalanced direct writes.
`quantity_post_journal`, `quantity_reverse_journal`, account lookup, trial
balance, and atomic per-document numbering form the SQL boundary for later
quantity modules. Existing version-1 quantity schemas upgrade through
`quantity_accounting_foundation.sql`; fresh schemas receive the same objects
from `quantity_tenant_template.sql`. The schema verifier now correctly
fingerprints PostgreSQL identity sequences through `pg_class`. Evidence from
the preserved Phase 5 upgrade database, two fresh quantity tenants, concurrent
numbering, 39 focused checks, all 19 suite modules, and complete serial
regressions is in `tests/PHASE6_ACCOUNTING_FOUNDATION_RESULTS.md`. Quantity
business routes remain gated; Phase 7 is the product/variant/SKU/unit master.

Phase 7 completed on 2026-07-25. Quantity schema version 3 adds controlled
Piece, Box, Kilogram, Gram, Litre, and Metre units; normalized products; and
sellable variants requiring brand, model, color, storage, RAM, region, and
condition. The unit participates in normalized combination identity, so the
same attributes stocked as Pieces and Boxes remain separate SKUs. Suggested
SKUs are normalized, deterministic, collision-suffixed under an advisory lock,
and may be manually supplied. SKU and unit become immutable when
`variant_transaction_registry` records the first business reference. Piece/Box
quantities are whole-only; measurement units accept at most three decimals,
and exact numeric checks reject rather than silently round a fourth decimal.
The `/items/quantity/` JSON API slice provides unit lookup, product/variant
creation and updates, SKU suggestion, and active/inactive catalogue search.
This path is centrally enabled for quantity tenants while all unimplemented
quantity routes remain gated. Fresh provisioning composes the stable quantity
base template with the current family hardening artifact, ensuring the same
SQL upgrades fresh and existing tenants. Evidence from the preserved upgrade,
two fresh quantity tenants, 60 focused checks, all 20 suite modules, and full
serial regressions is in `tests/PHASE7_ITEM_MASTER_RESULTS.md`.

Phase 8 completed on 2026-07-25. Quantity schema version 4 adds normalized
multi-warehouse identity, address and active/inactive state, and at most one
active default warehouse. Default creation, switching, deactivation,
replacement, and unreferenced deletion are serialized with a tenant-local
transaction advisory lock. `warehouse_reference_registry` is the integration
contract for later stock/document tables and prevents any referenced warehouse
from being hard-deleted while still permitting deactivation for future use.
The `/warehouses/quantity/` JSON API provides lookup, default resolution,
create, rename/update, deactivate/reactivate, and guarded deletion. Four
explicit Django permissions are installed by
`authentication.0022_add_quantity_warehouse_permissions`, and both central
route mapping and view-level checks enforce them. Fresh quantity provisioning
now executes ordered cumulative family upgrades (item master, then warehouse)
after the stable base template; existing version-3 tenants receive only the
idempotent Phase 8 artifact during deployment. Evidence from the preserved
upgrade, migration rollback/reapply, two fresh quantity tenants, 38 focused
checks, all 21 suite modules, and full serial regressions is in
`tests/PHASE8_WAREHOUSE_RESULTS.md`. Transfers and warehouse stock remain in
their assigned later phases.

Phase 9 completed on 2026-07-25. Quantity schema version 5 adds the inventory
core independently of invoice screens: immutable stock movements, atomic
per-variant/per-warehouse balances, FIFO receipt layers, durable outbound
allocation lineage, and current or historical availability. All writes pass
through controlled SQL functions. Tenant-and-scope advisory locks serialize
near-zero consumption, while multi-scope operations acquire warehouse/variant
locks in a canonical order. Deterministic replay orders events by business
date and effective sequence, rejects any backdated event that would make
historical stock negative, and rebuilds projections and allocations
atomically. Reconciliation compares movements, balances, FIFO remainder, and
allocated outbound quantities. The focused suite passed 38/38, all 22
mixed-family modules passed, and the complete serial system, HTTP, and deep
lifecycle regressions remained green. Evidence is in
`tests/PHASE9_FIFO_ENGINE_RESULTS.md`. Quantity invoice UI remains gated;
Phase 10 adds opening stock through this engine.

Phase 10 completed on 2026-07-25. Quantity schema version 6 adds immutable
opening-stock documents and lines with independent `OPN-000001` numbering.
Each document posts SKU quantities into their selected warehouses through the
Phase 9 movement/FIFO engine and atomically debits Inventory while crediting
Opening Balance. Piece and Box remain whole-only; measurement units retain
three-decimal quantity precision and costs retain six decimals. An opening
document can be reversed only while every original FIFO layer remains wholly
unconsumed, preventing a reversal from substituting arbitrary current FIFO
cost. Reversal uses linked stock movements and an immutable reversing journal.
Opening Balance status and serialized reclassification move its exact balance
to Owner's Capital, including the inverse direction when necessary. The shared
opening-stock route now selects a quantity-specific no-serial UI for quantity
tenants while preserving the existing serial screen and functions unchanged.
Evidence from 37 focused checks, all 23 mixed-family modules, and complete
serial system/HTTP/deep-lifecycle regressions is in
`tests/PHASE10_OPENING_STOCK_RESULTS.md`. Phase 11 adds domestic quantity
purchases.

Phase 11 completed on 2026-07-25. Quantity schema version 7 adds domestic
base-currency purchases with immutable invoice/line records, tenant-local
`PUR-000001` numbering, required vendor-name snapshots, credit or cash mode,
SKU/warehouse quantities, six-decimal unit costs, movement/FIFO lineage, and
balanced journals. Credit purchases debit Inventory and credit Accounts
Payable; cash purchases credit the selected Cash or Bank control account.
Database advisory locking by tenant and idempotency key makes simultaneous
duplicate submissions return one purchase. Edits preserve the document number,
store the complete prior document in an immutable revision record, replace the
source movements under controlled guards, replay every affected FIFO timeline,
and reverse/repost accounting atomically. Any edit producing historical
negative stock rolls back completely. Reversal is allowed only while every
purchase layer remains wholly unconsumed. Quantity purchase navigation,
summary, and the shared `/purchase/` routes now select a quantity-specific
no-serial UI/API. The general quantity party master remains Phase 19, so Phase
11 stores the vendor snapshot and uses the AP control account; tax, discounts,
foreign currency, settlements, and attachments remain in their assigned
phases. Evidence from 46 focused checks, all 24 mixed-family modules, and full
serial regressions is in `tests/PHASE11_QUANTITY_PURCHASES_RESULTS.md`. Phase
12 adds domestic quantity sales with FIFO COGS.

Phase 12 completed on 2026-07-26. Quantity schema version 8 adds domestic
base-currency quantity sales with immutable invoices, lines, revisions,
tenant-local `SAL-000001` numbering, warehouse-scoped availability locks,
durable FIFO allocations, line-level COGS, credit/cash modes, idempotency,
guarded edit/replay and reversal, navigation/summary, and a no-serial sales UI.
Credit sales debit Accounts Receivable while cash sales debit Cash/Bank; both
credit Sales Revenue and post exact COGS/Inventory entries. Final-stock
concurrency permits exactly one sale and cannot oversell. Evidence from 34
focused checks, all 25 mixed-family modules, and full serial
system/HTTP/deep-lifecycle regressions is in
`tests/PHASE12_QUANTITY_SALES_RESULTS.md`. Phase 13 adds quantity sale returns.

## Maintenance Checklist

When changing the project, update this file if any answer changes:

- Did a route, app, or endpoint move?
- Did a permission, rate limit, or tenant guard rule change?
- Did a tenant table/function/view/trigger change?
- Did provisioning or existing-tenant rollout change?
- Did Docker, environment variables, or static handling change?
- Did test setup, commands, or expected coverage change?
- Did the alert conventions change, or was `Swal.fire` used directly instead of the `Alerts` helper?
