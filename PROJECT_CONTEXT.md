# Project Context

Last updated: 2026-07-06

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

## Maintenance Checklist

When changing the project, update this file if any answer changes:

- Did a route, app, or endpoint move?
- Did a permission, rate limit, or tenant guard rule change?
- Did a tenant table/function/view/trigger change?
- Did provisioning or existing-tenant rollout change?
- Did Docker, environment variables, or static handling change?
- Did test setup, commands, or expected coverage change?
- Did the alert conventions change, or was `Swal.fire` used directly instead of the `Alerts` helper?
