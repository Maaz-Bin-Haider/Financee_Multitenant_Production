# Project Context

Last updated: 2026-10-02

This file is the persistent engineering context for Financee. Update it on every meaningful project change, especially changes to architecture, routes, permissions, tenant SQL, deployment behavior, environment variables, tests, or data model assumptions.

## Session Resume Checkpoint

- **System state:** serial-only, and the consolidation is **complete**. The
  quantity company family is retired in runtime, database and repository.
  Serial business behaviour is unchanged throughout.
- **Governing plan:** `SERIAL_ONLY_REMOVAL_PLAN.md` — **STATUS: COMPLETE**. All
  phases 0–4 carry an explicit owner production PASS.
  - Phase 0 discovery, Phase 1 creation freeze, Phase 2 runtime removal,
    Phase 3 database cleanup (3A compatibility release, 3B guarded reversible
    cleanup) — all PASS and deployed.
  - Phase 4 repository hygiene and the migration transition — PASS. Checkpoint
    4A (`a4f915f`) shipped the squashed replacements beside the originals;
    checkpoint 4B (`5f42cd1`) deleted the replaced files and removed
    `replaces`, so each squash is now an ordinary initial migration.
- **Last release:** `cf12d6a` (pushed to `main` 2026-10-01) added Draft Sale
  Invoices (Proforma) — see that section below. The release before it,
  `53a12e0` (2026-09-26), fixed two sidebar bugs in
  `templates/base/base.html`: the Sales Reports link now honours all eight
  `SALES_REPORT_PERMS`, and the empty inventory-mode badge is gone. See
  `FIXED_ISSUES.md`.
- **Production today:** image
  `cf12d6a54f828e41cbb0f72001eda59d2fe35d7e` (deployed 2026-10-01, workflow run
  `36856609567`, Phase 30 controller PASS with matching before/after continuity
  fingerprints and no rollback), one serial company, tenant schema version 6,
  no `inventory_mode` column, no retired permissions or feature keys. The
  Phase 3B archive remains `applied` and is the reversal path — do not delete
  it. The previous release was `53a12e0966f6519e8372f652b215c85b71fc31c3`.
- **Tenant schema version stays at 6** after the 2026-09-16 dashboard
  receivables fix. That fix replaces one reporting view and is compatible in
  both directions, so it needs no version gate — and bumping would have blocked
  the Phase 3B reversal path, whose registry guard requires each tenant to be at
  exactly serial version 6 (`serial_only_phase3_cleanup.registry`). Reserve
  version bumps for schema changes that code actually depends on.
- **Deployed image is not `main` HEAD.** `main` carries later documentation
  commits made with `[skip ci]`, which deliberately publish and deploy nothing.
  Check the last successful `CI/CD` run for what is actually deployed rather
  than assuming `main` HEAD.
- **Migrations:** only `tenancy/migrations/0001_serial_only.py` and
  `authentication/migrations/0001_serial_only.py` exist on disk. Production's
  `django_migrations` holds **36** rows for these two apps — 34 replaced
  (9 tenancy + 25 authentication) plus the 2 replacements. The 34 have **not**
  been pruned, deliberately; see the prune section below.
- **Serial-only is proven physically.** There is no registry mode value to
  trust: `verify_company_schema` checks each schema's own
  `tenant_schema_version`, and `Company` has no `inventory_mode` field,
  property or choice list. The retired keyword is refused by `Model.__init__`.
- **Docs audited 2026-09-26.** `README.md`, `CLAUDE.md`, `DEPLOYMENT_GUIDE.md`
  and this file were corrected against the code (no code or SQL changed).
  Known remaining doc drift is listed under Known Documentation Caveats.
- **Draft Sale Invoices (Proforma)** were added on 2026-09-30 and released in
  `cf12d6a`. See the section of that name below: new tenant SQL, a `draft`
  app, 11 permissions seeded without a migration, and a Phase 30 audit change.
- **Per-module feature switches and the new-company default plan** were added
  on 2026-10-02 (branch `feature/company-feature-defaults`; not yet released
  when this was written). Every module now has a switch and a new company
  starts with the default plan; existing companies keep what they have. See
  Per-Company Feature Flags. No SQL, model or migration change.

### Three migration rules to know before touching this again

1. **Pruning breaks rollback, and a rollback attempted afterwards corrupts the
   history.** Django drops a replacement from `applied_migrations` when the
   migrations it replaces are absent, *even though the replacement's own row
   exists*. So after a prune every `replaces`-carrying image believes nothing is
   applied and re-plans the initial migration. That does **not** fail cleanly:
   the `authentication` replacement is pure `RunPython`, so it re-applies and
   re-records its rows before the `tenancy` replacement dies on `CREATE TABLE`,
   leaving a half-applied history and an app that will not start.
   The loss is recoverable — `serial_only_phase4c_prune --action restore` resets
   the rows from its archive and repairs even that damaged state — but only if
   whoever rolls back knows to run it. Nothing in the deployment path prunes,
   and a contract enforces that.
2. **Prune is per-app.** Django refuses a project-wide prune:
   `migrate tenancy --prune`, `migrate authentication --prune`.
3. **A fresh install has no pre-4B rollback path**, because it never had the
   replaced rows. Only an upgraded database retains one.

### The read-only Phase 4 audit

`serial_only_phase4_audit` **discovers** which migration history the estate
holds rather than being told: `pre-4A` (original chain), `post-4A` (chain plus
both replacement records) or `pruned` (replacements only). It reports the state
and fails closed on anything unrecognised. `--expect-state` is an optional
assertion. Its workflow derives the deployed SHA from the commit it runs from
and requires that commit to be an ancestor of the ref; the remote wrapper still
refuses to proceed unless it matches the running container. Nothing needs
repinning after a release.

### The migration-record prune — decided: skipped

Production keeps the 34 replaced `django_migrations` rows. `migrate --prune`
would remove them, and `serial_only_phase4c_prune` implements that guarded and
**reversibly** (it archives the rows first). It was proven on real PostgreSQL and
then deliberately not run.

The reason is a hazard found while building it: a rollback attempted against a
pruned database does not fail cleanly. The `authentication` replacement is pure
`RunPython`, so it re-applies and re-records before the `tenancy` replacement
dies on `CREATE TABLE`, leaving a half-applied history and an app that will not
start. `restore` repairs that, but the trap would exist for anyone rolling back
without knowing. Removing 34 inert rows is not worth it.

If it is ever run: `inspect` first for the digest, then `apply` with the typed
confirmation and a backup reference under 30 minutes old. Never plain
`migrate --prune`, which is refused project-wide and must be per-app.

### Deliberate leftovers, not oversights

- **`tests/serial_api_compat.py`** and the pre-3B fixture reconstruction in the
  Phase 3 inventory proof. The Phase 3B cleanup rehearsal still needs a pre-3B
  database, which only the 3A image produces, so the shim must survive as long
  as that rehearsal targets 3A. Every gate passes with it present.
- **`tests/retired_permissions_reference.json`** — the 14 retired permission
  codenames frozen from the deleted migrations, so the Phase 3 audit and
  Phase 3B cleanup catalogues keep an *independent* cross-check instead of the
  tooling agreeing with itself.
- **The Phase 3B archive** in production and its restore tooling.
- **19 `tests/PHASE*_RESULTS.md` evidence documents** and `todo.md`, which is
  banner-marked as a historical record of the retired family.

### Do not

- Reintroduce an inventory-mode concept.
- Delete the Phase 3B archive or its restore tooling.
- Assume "quantity" in code means the retired family — serial purchases, sales,
  returns and stock reports legitimately store counts named `qty`/`quantity`.

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
- Serial-only consolidation plan and audit trail: `SERIAL_ONLY_REMOVAL_PLAN.md`
- Phase 3B reversal runbook: `PHASE3B_MAINTENANCE_RUNBOOK.md`

## Key Business Modules

- Dashboard: `home`
- Party master: `parties`
- Item master: `items`
- Purchases: `purchase`
- Sales: `sale`
- Draft sale invoices (proforma), their conversion and returns: `draft`
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
3. Register a new patch filename in `rollout_files` (`tenancy/schema_families.py`); `apply_sql_all_tenants` refuses unregistered files (9 of the 18 are registered today).
4. Apply with `python manage.py apply_sql_all_tenants <sql-file>`.
5. Fold critical changes into `tenancy/sql/production_hardening.sql` and the example-tenant section of `build_multitenant_db.sql`, and re-pin the Phase 2 byte-identity contract (`tests/phase2_serial_runtime_removal_contracts.py`) in the same commit.
6. Leave the tenant schema version at 6 unless code depends on the change — the Phase 3B restore guard requires exactly 6.
7. Update this file and `README.md` if the operational contract changes.

Idempotent SQL should use patterns such as `CREATE OR REPLACE FUNCTION`, `CREATE INDEX IF NOT EXISTS`, and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## CI/CD

- `.github/workflows/ci.yml`: on every push/PR — a `checks` job on a plain
  runner (compile, django check, missing-migration guard, the database-free
  contracts and release gates below, `pip check`) plus stack gates that each
  boot a disposable Compose stack through `tests/ci_phase27_stack.sh`.
  `full-regression` builds the production image, bootstraps a CI superuser +
  a second tenant via `provision_tenant`, and runs `tests/suite/run_all.py`
  inside the container; `test_system.py`, `test_http.py` and
  `test_transaction_lifecycle_deep.py` are not run in CI. On `main`, after the
  protected `staging-release-approval`, `publish` rebuilds the commit as a
  multi-arch image and pushes it to `ghcr.io/maaz-bin-haider/financee-web`
  (`<sha>` + `latest`).
- **Serial-only gates (mandatory on every push/PR).** `ci.yml` runs the phase
  contract set in `checks` — `phase0_serial_only_discovery_contracts`,
  `phase1_serial_only_creation_contracts`,
  `phase2_serial_runtime_removal_contracts`,
  `phase3_metadata_inventory_contracts`, `phase3a_compatibility_contracts`,
  `phase3b_cleanup_contracts`, `phase3b_executor_contracts`,
  `phase4_repository_hygiene_contracts` — plus the dedicated jobs
  `serial-gate`, `creation-freeze-gate`, `runtime-removal-gate`,
  `metadata-inventory-gate`, `compatibility-gate`, `cleanup-rehearsal-gate`,
  `isolation-gate`, `arm64-smoke`, `full-regression`, `recovery-gate` and
  `staging-security-gate`. Publication and deployment are blocked until they
  pass. `migration-transition-gate` also runs on every push: it proves on
  disposable stacks that a fresh database records only the two squashed
  migrations and creates no retired column, constraint or permission; that a
  database carrying the post-4A history upgrades as a no-op with a
  byte-identical registry; that per-app `--prune` removes exactly the stale
  rows; and that the release stays rollback-safe before pruning. It is **not**
  listed in the `needs` of `staging-release-approval` or `publish`, so today it
  does not block publication. The
  Phase 2 contracts additionally pin byte-identity baselines for the 12 serial
  document view implementations, 225 serial UI files (everything under
  `static/` and `templates/` except `templates/base/base.html`), the 18 serial
  tenant SQL files (re-pinned 2026-09-30 for draft invoices) and the bootstrap's 12,248-line
  tenant business-schema build, so any accidental change to serial behavior
  fails CI; a deliberate change must re-pin in the same commit.
- `deploy` job: gated by repo variable `DEPLOY_ENABLED=true` AND manual
  approval via the `production` GitHub environment; SSHes to EC2 (secrets
  `EC2_HOST`/`EC2_USER`/`EC2_SSH_KEY`/optional `EC2_APP_DIR`, plus
  `BACKUP_DEST`/`BACKUP_PASSPHRASE_FILE`), runs `git pull --ff-only` in the host
  checkout, then `deploy/phase30_foundation_deploy.sh` with the SHA tag and the
  `PHASE30_*` release metadata (see `PHASE30_PRODUCTION_FOUNDATION_RUNBOOK.md`).
- `deploy/phase30_foundation_deploy.sh`: requires the host HEAD to equal the
  release SHA, runs `release_preflight`, audits the candidate image, takes an
  encrypted backup only when `PHASE30_BACKUP_MODE=encrypted` (default
  `external`), calls `deploy_pull.sh`, then checks the continuity fingerprint,
  container health, three consecutive nginx 200s and resource thresholds. Its
  EXIT trap rolls web back to the previous image on **any** failure after the
  deploy starts.
- `deploy/deploy_pull.sh`: pull-based deploy — pulls the pinned image,
  recreates web+nginx, health-checks through nginx, rolls back web to the
  previous image on failure, then `apply_sql_all_tenants tenant_indexes.sql`.
  `deploy/deploy.sh` stays as the manual build-on-server fallback (a fixed
  5-second wait instead of a health check, no preflight, no rollback). A
  rollback restores the web image only: public migrations, tenant SQL (the new
  container's entrypoint has already applied `production_hardening.sql`), nginx
  and the host checkout are not rolled back — keep migrations/tenant SQL
  backward-compatible.
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
  the host** (HTTP-only before that — no flag day). Local dev + the CI stack gates
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

Data model (`tenancy/models.py`; introduced by migration `0002_subscription_control`, now squashed into `tenancy/migrations/0001_serial_only.py`):

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
— never to individual users), fully configured from the admin panel. Introduced by migration
`0003_subscription_emails` (now squashed into
`tenancy/migrations/0001_serial_only.py`); engine in
`tenancy/subscription_emails.py`.

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

The operator switches features on/off **per company** from the company admin
form, to sell the system in plans. Everything lives in the public schema — no
tenant SQL. Introduced by migration `0004_company_feature_flags` (now squashed
into `tenancy/migrations/0001_serial_only.py`); registry, defaults and
enforcement helpers in `tenancy/features.py`.

Every module has a switch (keys are stable — they are persisted). A main
switch off hides all of its sub-features; while it is on, each sub-feature
follows its own switch. The **new-company default plan** is
`DEFAULT_DISABLED_FEATURES`:

| Main feature (key) | Sub-features | New company |
|---|---|---|
| Dashboard (`dashboard`) | `sales_overview`, `cash_balance`, `stock_overview`, `balances` (party & item lists), `top_parties`, `receivables_aging`, `recent_transactions`, `expenses`, `smart_alerts` | on |
| Sales, Sale Returns, Purchases, Purchase Returns, Payments, Receipts, Contra Entry, Items, Parties (`sales`, `sale_returns`, `purchases`, `purchase_returns`, `payments`, `receipts`, `contra`, `items`, `parties`) | — | on |
| Accounts Reports (`accounts_reports`) | Party Ledger `detailed_ledger`, Cash Ledger, Trial Balance, Accounts Receivable, Accounts Payable on; Detailed Ledger `detailed_ledger2` **off** | on |
| Stock Reports (`stock_reports`) | Stock Report `stock_summary`, Stock Serial Wise `stock_report`, Serial Ledger, Item History, Stock Worth on; Serial Ledger Sold Flag / Purchase / Sale, Item Detail, Item Last Purchase, Items Last Sale **off** | on |
| Monthly Reports (`monthly_reports`) | Income Statement on; Company Position **off** | on |
| PDF generation (`pdf_export`) | `documents` (sale, purchase, both returns, draft proforma and history), `reports` (every report, owner equity, month close, pending drafts, dashboard; includes the Monthly Reports Print button) | on |
| Sales Reports (`sales_reports`) | the 8 tabs | **off** |
| Draft Invoices (`draft_invoices`) | `drafts`, `confirm`, `returns`, `pending_report`, `dashboard_card` | **off** |
| Opening Stock, Opening Cash, Owner Equity, Month-End Close (`opening_stock`, `opening_cash`, `owner_equity`, `month_close`) | — | **off** |
| CSV / Excel export (`excel_export`), Document attachments (`attachments`) | — | **off** |

Sub key names follow the URLs; admin labels follow the UI button text (note
`/detailed-ledger/` renders as "Party Ledger" and `/detailed-ledger2/` as
"Detailed Ledger"; `/stock-summary/` as "Stock Report" and `/stock-report/` as
"Stock Serial Wise"). Keys must never start with `quantity` or
`purchase_reports`: the Phase 3/3B/4 audits reserve those prefixes.

Semantics and storage:

- `Company.disabled_features` (JSONField, list of **disabled** keys).
  `Company.feature_enabled(key)` — disabling a group disables all of its subs;
  unknown keys fail open. The list is exactly what is off: a key not in it is
  on.
- **Defaults are written at creation, never read at request time.** The admin
  add form pre-ticks the default plan and `provision_tenant` stores
  `default_disabled_features()` (`--all-features`, `--enable KEY`,
  `--disable KEY` adjust it; enabling a sub-feature also enables its main
  switch). The model keeps `default=list` — changing it would need a
  migration, which the migration-history gates refuse — so a company created
  in code (tests) and the example "Company One" a fresh install registers keep
  every feature. Existing companies are untouched by the deploy that
  introduced the plan; the changelist actions **Apply the default feature
  set** and **Enable every feature** move companies in one click.
- `excel_export` removes only the **CSV/Excel** download buttons across all
  report screens plus Month-End Close and Owner Equity.
- `pdf_export` hides PDF (and the Monthly Reports Print) buttons. PDFs are
  built in the browser (jsPDF), so there is no URL to block; the jsPDF
  `<script>` tags stay because several scripts read `window.jspdf` before
  checking it.
- `attachments` hides the whole document-attachment widget (upload **and**
  existing-file preview/download) and blocks `/attachments/`; files are never
  deleted, so re-enabling restores them. `attachments/utils.py`
  (`validate_request_attachments` raises / `save_document_attachments`
  no-ops) guards uploads server-side.

Enforcement (`tenancy/middleware.py` after the subscription guard, applied to
**every** user of the company, superusers included):
`tenancy.features.feature_for_path` maps the request path to a feature key —
`FEATURE_EXACT_PATHS` first (the Draft Invoices screen is `/draft/`), then the
**longest** matching prefix in `FEATURE_PATH_PREFIXES` (order no longer
matters). A `None` key keeps a path open whatever is switched off: the shared
pickers `/parties/autocomplete-party` (11 screens in 9 modules) and
`/items/autocomplete-item/` (Purchases, Opening Stock, Stock Reports).
**`/home/` is never mapped**: every denial redirects there, so blocking it
would loop; the dashboard is switched off in its template (a plain welcome
page with quick links) and its widget data endpoints (`/home/api/...`) are
mapped to the dashboard sub-features. `/draft/get/` and `/draft/summary/` map
to the Draft Invoices main switch because both the Draft and Confirm screens
load drafts through them. Disabled paths get `feature_disabled_response`
(`financee/security.py`): non-GET/AJAX/API → scrubbed 403 JSON ("This feature
is not enabled for your company."); a plain GET on a disabled **sub-feature
page** redirects to the first enabled sibling of the group
(`GROUP_LANDING_PATHS`: the three report groups and the draft screens) so
entry points keep working, else to the dashboard.

UI hiding: `tenancy.context_processors.company_features` (registered in
settings) exposes `features` — per group `enabled` (main switch on **and**, for
groups with sub-features, at least one of them on), `subs`, and `landing` (the
first enabled page of a report group) — to every template. `base.html` gates
every sidebar link (report groups link to `landing`; each draft screen to its
own sub-feature) and embeds `window.FinanceeFeatures` +
`financeeFeatureEnabled()` by passing the **raw dict** through `json_script`
(pre-serializing with `json.dumps` double-encodes it into a string and every
JS feature check fails open — the suite asserts the page embeds a JSON
object; `enabled` must stay each group's first key). JS-built toolbars
(`accounts_reports.js`, `stock_reports.js`, `detailed_ledger2.js`,
`monthly_reports.js`, `pending_drafts_page.js`, the draft history popups)
gate their CSV and PDF buttons and re-check in the handlers; report-page init
handlers start on the first *visible* report button. The report templates
gate each sub-report button; the 7 document templates gate the attachment
widget include; `home_template.html` wraps each widget in its switch and
`home_script.js` skips loading switched-off widgets. Quick actions
(`templates/home_templtes/quick_actions.html`) follow the module switches.

Admin (`tenancy/admin.py`): `CompanyAdminForm` renders the JSON column as
Boolean switches in four collapsible sections (Core modules, Reports, Add-on
modules, Export & documents — `FEATURE_CATEGORIES`); each main switch is
followed by its sub-features, which `static/js/admin_company_features.js`
indents and dims while the main switch is off (their ticks are kept). Help
text says how each switch starts for a new company. `fieldsets` stays a static
attribute (the Phase 30 deploy audit reads it). The changelist shows a
"Features off" count. Tests: `tests/suite/test_feature_flags.py` (wired into
`run_all.py`; checks that need the default plan skip on older images).

Rollback: an older image ignores keys it does not know (they fail open, so
e.g. Owner Equity reappears for a company that had it off), and saving a
company in an older admin drops them from its list. Nothing else changes —
there is no SQL, model or migration behind the switches.

When adding a feature later: add its key to `FEATURE_GROUPS` and a category,
decide its default (add it to `DEFAULT_DISABLED_FEATURES` if new companies
should not get it), map its URLs, and gate its UI. Existing companies see a
new key as **on** (it is not in their list); to keep it off for them, apply
the change with the admin action or a one-off update after the deploy —
never in a `post_migrate` handler, which would change the registry rows the
checkpoint-4B transition gate requires to stay byte-identical.

## Security and Permission Notes

- Route-level guards live in `financee/security.py` and are enforced by `TenantSchemaMiddleware`.
- Authenticated users without an active company cannot access tenant features.
- Admin/auth/static/media routes are tenant-guard exempt.
- JSON errors are scrubbed by middleware to avoid leaking internal exception details.
- Login, dashboard, report, and lookup endpoints have lightweight cache-backed rate limits.
- `/draft/` is not in `PROTECTED_PREFIX_PERMS`: each draft view checks its own permission (screen and endpoint differ, e.g. Confirm Draft needs `confirm_draft_invoice`, not `view_draft_invoice`), after the deployment switch and before any cursor opens. The 11 draft permissions are seeded by a `post_migrate` handler in `draft/apps.py`, not by a migration (see Draft Sale Invoices).
- The sidebar's Sales Reports link shows when the user holds any one of the eight `SALES_REPORT_PERMS`, the same rule as the `/sales-reports/` route guard. The template has to repeat that list; `tests/phase2_serial_runtime_removal_contracts.py` fails CI if the two drift (a literal `...` placeholder hid the link from six of the eight until 2026-09-26).

## Admin UI Notes

- Custom admin templates live in `templates/admin/`.
- The admin theme is owned by `static/css/financee_admin.css`.
- The admin UI is not stock Django only; it includes a custom dashboard, KPI strip, quick links, user activity overview/detail pages, PDF export links, tenant/company management, and custom user delete behavior. User activity aggregates across tenant schemas only when `TENANCY_CROSS_TENANT_ACTIVITY=True`; it defaults to False in `financee/settings.py`, so those pages are empty by default (the comment in `tenancy/apps.py` saying "on by default" is outdated).
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
  `static/css/base_styling.css`. The retired inventory-mode badge that sat
  under the company name (and had rendered empty since the serial-only
  consolidation) was removed on 2026-09-26.

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
- `tests/suite/test_reports.py` asserts that an Expense party which has been paid never appears in `vw_dash_party_ar_balance`, `fn_dash_smart_alerts` or `fn_dash_receivables_aging`, while a genuine credit customer still does (`_receivables_exclude_expenses`). These four checks fail against the pre-2026-09-16 view.
- `tests/suite/test_subscription.py` covers the subscription-control layer: the paid-until/grace/suspension state machine, calendar-aware payment extension, and HTTP enforcement (suspension page, JSON denial, exemptions, warning banner).
- `tests/suite/test_subscription_emails.py` covers the subscription email layer: BillingSettings singleton, expiry/suspension emails with per-cycle dedup and failure retry, contact-detail embedding, manual-suspension/test emails, and the admin email screens (locmem backend, nothing real sent).
- `tests/suite/test_drafts.py` covers draft sale invoices on every tenant (the reservation guard against sale, purchase return, purchase delete and sale return; the lifecycle; a books snapshot proving no draft operation moves the journal, stock, invoices or balances; conversion; the Confirmed Draft Return incl. its date and segregation; reports; a two-connection proof that a reservation and a sale of one serial serialise on the row lock) plus the HTTP layer as a non-superuser (permission per endpoint, the deployment switch, the company flag, the read-only group, and the Sale / Sale Return / Purchase Return lookups). It prints SKIP and exits 0 on a build without the feature (the Phase 3B rehearsal runs it inside the 3A image).
- `tests/suite/test_feature_flags.py` covers the per-company switches; on builds with the new-company default plan it also checks the plan itself, the admin add view and its two actions, `provision_tenant`, and the module, dashboard-widget, PDF and draft-screen switches (older images in the Phase 3B rehearsal skip those). Because companies created by `provision_tenant` or the admin now start on the default plan, HTTP harnesses switch on the features they exercise and restore the company's own switches afterwards (`test_attachments.py`, `test_http.py`, `test_drafts.py`); companies created directly in code keep everything on.
- `tests/suite/test_attachments.py` adds dedicated document-attachment coverage for sale, purchase, sale return, purchase return, payment, receipt, and contra documents: upload/update/replacement, preservation of the unselected file kind, metadata/preview/download endpoints, invalid file validation, cleanup, failed-delete preservation, attachment-only bypass for sale/purchase/returns, and no bypass for payments/receipts/contra.
- `tests/run_tests.sh` runs `test_system.py` and `test_http.py` in Docker and can reset tenant schemas with `--reset`. `test_system.py` always exits 0, so read its `TOTAL FAILURES` line.
- **Serial-only enforcement tests.** `tests/phase1_serial_only_creation.py`
  proves no supported path can express a non-serial company (the retired
  keyword is refused by `Model.__init__`, the database rejects a retired-mode
  write, and the migration precondition still blocks conflicting rows).
  `tests/phase2_serial_runtime_removal.py` proves retired routes/modules are
  unreachable, the schema-family registry refuses the retired key, the request
  boundary fails closed without a resolved tenant, and the rollout registry
  refuses a retired SQL filename. `tests/phase24_serial_matrix.py` certifies no
  retired table, function or route exists in a fresh serial schema;
  `tests/phase25_four_company_isolation.py` runs four concurrent serial
  companies and rejects a non-serial schema shape.

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

## Draft Sale Invoices (Proforma)

Goods are often promised to a customer before the price is agreed. A **draft**
reserves specific serial numbers for a named customer and moves nothing else —
no stock, journal or balance. When the rate is agreed, a tranche converts into
an ordinary **credit** sale invoice and the rest stays reserved. Ported on
2026-09-30 from the single-tenant Financee (`Accounting-Plus-Inventory-System`,
commit `80e8f8a` plus its post-release fixes; design in its
`DRAFT_SALES_PLAN.md`, user guide `DRAFT_INVOICE_FEATURE_GUIDE.md`). Its
Spotlight search, Team Activity and lookup-by-id pickers do not exist here and
were not ported.

- **Tenant SQL:** `tenancy/sql/add_draft_invoices.sql`, registered in
  `rollout_files` and appended byte-identically to the end of
  `tenant_template.sql` and `production_hardening.sql` (the serial gate allows
  only stored functions to differ between the bootstrap tenant and a
  provisioned one, so tables, indexes, triggers and views must match). It is
  deliberately **not** in `build_multitenant_db.sql`: the bootstrap tenant gets
  it from `production_hardening.sql` at first start, like `tenant_indexes.sql`.
  That keeps the bootstrap pins (including the hash in
  `deploy/phase3_recovery_remote.py`) and the Phase 3B rehearsal — which seeds
  this bootstrap under the old 3A image and its 24-table template — unchanged.
  Tenant schema version stays 6.
- **Tables:** `draftinvoices`, `draftitems` (`unit_price` NULL = no rate yet),
  `draftunits` (one row per reserved unit; `Reserved` / `Converted` /
  `Released`, history kept; partial unique index
  `draft_units_one_live_reservation`; `unit_id` cascades on a purchase-unit
  delete), `draftreturns`; discriminators `salesinvoices.draft_invoice_id` and
  `salesreturns.draft_return_id`. "Partially Converted" is derived, never
  stored.
- **The guard (no accounting function forked):** `trg_protect_reserved_units`
  (BEFORE UPDATE OR DELETE on `purchaseunits`) refuses taking a reserved unit
  out of stock or deleting it. That covers `create_sale`,
  `update_sale_invoice`, `create_purchase_return`, sale-return undo,
  `delete_purchase`, `update_purchase_invoice` and `delete_opening_stock`
  without editing them. `trg_reserve_only_stocked_units` takes the same row lock
  as `create_sale`, so reserving and selling one serial serialise. Conversion
  flips its units to `Converted` first and then calls the unchanged 4-arg
  `create_sale`.
- **Returns:** a Confirmed Draft Return is an ordinary `salesreturns` row (so
  every ledger and the trial balance see it) under a `draftreturns` header,
  booked on the date picked (never in the future or before the sale). The
  description lives on the `salesreturns` row. `create_sale_return` is now a
  wrapper over `sale_return_core(...)`; ordinary paths refuse draft-sold
  serials and draft paths refuse ordinary ones on create **and** update;
  `delete_sale_return` refuses a row that still has a draft-return header.
  Ordinary Sale Return navigation and history leave draft returns out.
- **Existing functions changed:** `get_serial_number_details` (3 reservation
  columns appended; guarded DROP + CREATE, which also replaces the bootstrap's
  old multi-row version with the single-row one), `stock_summary()`
  (`reserved_on_drafts`), the `stock_report` view (`reserved_for`,
  `reserved_on_draft`), `get_serial_ledger` / `get_serial_ledger_sales` (draft
  events, qty 0/0), `validate_purchase_update2` / `validate_purchase_delete`
  (`reserved_serials`), `delete_opening_stock` (reserved pre-check),
  `create/update/delete_sale_return`, and the ordinary sale-return listing
  functions.
- **Django:** app `draft` at `/draft/` (Draft Invoices, Confirm Draft,
  Confirmed Draft Return, Pending Drafts, plus JSON endpoints). The 11
  permissions (`view/create/update/delete_draft_invoice`,
  `confirm_draft_invoice`, `view/create/update/delete_draft_return`,
  `view_pending_drafts_report`, `view_dash_draft_reservations`) are seeded by a
  `post_migrate` handler in `draft/apps.py`, **not** by a migration: the
  Phase 4 migration audit recognises only the two squashed initial migrations
  and would fail closed on a new row. `tests/phase4b_migration_transition.sh`
  therefore compares permission counts excluding `%draft%` codenames. The
  `view_only_users` group is refused every draft action.
- **Switches:** `DRAFT_SALES_ENABLED` (env, deployment-wide: endpoints 404,
  screens redirect, sidebar and card hidden), the per-company `draft_invoices`
  feature flag (admin; **off for a new company**; the middleware blocks
  `/draft/` and `/home/api/dash/drafts/`) with one sub-feature per screen —
  `drafts`, `confirm`, `returns`, `pending_report`, `dashboard_card` (see
  Per-Company Feature Flags) — and `DRAFT_AGE_WARNING_DAYS` (default 30).
  **Switching drafts off hides the interface but does not free reserved
  serials** — release or convert open drafts first.
- **Elsewhere in the UI:** four sidebar entries after Sales; the dashboard card
  "Stock Reserved on Drafts"; the Sale, Sale Return and Purchase Return lookups
  name the reservation (Sale has no override); Purchase edit/delete messages
  list reserved serials; Serial Wise Stock and Stock Report columns (the Stock
  Reports table renderer now escapes cell text); the Proforma PDF through
  `static/js/report_pdf.js` (`FinanceePdf`). The draft customer picker uses
  `/parties/autocomplete-party?receivable=1` (Customer / Both, never cash), so
  a draft user also needs `view_party` for suggestions, as on the Sale screen.
- **Deploy continuity:** `production_foundation_audit` leaves empty tables out
  of `table_counts`. The Phase 30 "before" snapshot is taken before the new
  container's hardening run creates the draft tables, so without this the
  first release would fail its continuity comparison and roll back. A table
  that gains or loses rows still changes the map.
- **Rollback:** the old image re-runs its own `production_hardening.sql`,
  restoring the old `create/update/delete_sale_return` bodies (no draft
  segregation — harmless). Draft tables, triggers and the other functions stay,
  and **reserved serials stay blocked while the old UI has no Release
  screen**: before rolling back, cancel or convert open drafts
  (`SELECT cancel_draft(draft_invoice_id) FROM draftinvoices WHERE
  status = 'Open'` per tenant). Running the registered
  `fix_sale_return_lifecycle_guards.sql` by hand likewise reverts those three
  functions until the next container start.
- **Not ported / known limits:** Spotlight, Team Activity, `?party=` links.
  The ordinary Sale Return and Purchase Return still stamp `CURRENT_DATE`;
  the draft return is the model for fixing them. There is no period locking,
  so a back-dated conversion or return posts into a closed month (pre-existing,
  as for any document).

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
- `tenancy/sql/fix_dashboard_expense_receivables.sql` (standalone idempotent patch, folded into template/hardening/bootstrap; no version bump) stops Expense parties being reported as receivables on the dashboard. `add_party_from_json` gives an Expense party both `ar_account_id` (shared AR) and `ap_account_id` (its own Expense account), and `vw_dash_party_ar_balance` summed every party-tagged journal line regardless of account — so paying rent or salaries surfaced that expense head as a customer owing money, and raised "Stale Receivable" / "Risky Customer" alerts. The view is now constrained to `jl.account_id = p.ar_account_id`, an account test rather than a `party_type` test so it stays correct if a party type is ever added. Fixes `fn_dash_smart_alerts` and `fn_dash_receivables_aging` with no edit to either. `get_accounts_receivable_json_excluding` was never affected (it filters expense types over `vw_trial_balance`). Note: a `Both` party's receivable is no longer netted against their payable in this view. See `FIXED_ISSUES.md`.
- `tenancy/sql/add_draft_invoices.sql` (standalone idempotent patch, appended byte-identically to the end of template and hardening; **not** folded into the bootstrap — see Draft Sale Invoices below; no version bump) adds draft sale invoices: the four draft tables, the reservation guard triggers and the draft/return/report functions.
- Keep `tenancy/sql/tenant_template.sql`, `build_multitenant_db.sql`, and `production_hardening.sql` aligned when tenant SQL behavior changes.

## Known Documentation Caveats

- The generated header comment in `financee/settings.py` says Django 5.2.6, but dependency files currently pin Django 6.0.6. Treat dependency files as source of truth unless code compatibility work says otherwise.
- Some view files retain older commented-out implementations. Active functions are the uncommented definitions later in the files.
- `tests/suite/RESULTS.md` is the 2026-07-06 matrix (12 modules). The newest full-run evidence is in `FIXED_ISSUES.md` (2026-09-16, 21 modules).
- `build_multitenant_db.sql` seeds `tenant_company_1` at tenant schema version 4; it reaches 6 only because the entrypoint applies `production_hardening.sql`. Its header still says 15 `authentication` migrations are left unseeded (there is now one).
- Stale comments inside CI byte-pinned SQL (editing them means re-pinning): `production_hardening.sql` labels the dashboard receivables fix "schema version 7" (the bump was dropped), and `tenant_template.sql` says `add_document_attachments.sql` and the bootstrap carry the v6 bump (neither does).
- Other stale comments: the re-pin note in `tests/phase2_serial_runtime_removal_contracts.py` also mentions version 7; `deploy/docker-compose.yml` says the bootstrap builds the tenancy tables; `deploy/entrypoint.sh`'s header lists only three steps; `tenancy/apps.py` calls cross-tenant activity "on by default".
- Several runbooks carry stale status lines: `PHASE30_PRODUCTION_FOUNDATION_RUNBOOK.md` still says approved production execution is required, and `PHASE3B_MAINTENANCE_RUNBOOK.md` says production remains on the 3A image.

## Retired Quantity-Company Family (design retired 2026-09)

The quantity/FIFO company family was designed and built across historical
phases 5–23 but was **never used by a production customer**. It has been
retired end to end under `SERIAL_ONLY_REMOVAL_PLAN.md`.

What was removed, and where the record lives:

- **Runtime (Phase 2):** quantity HTTP routes, view adapters, dispatchers,
  templates, static assets, dashboard branches and startup SQL maintenance.
- **Database (Phase 3):** the `inventory_mode` column and its check
  constraint, 14 retired permissions with their direct grants, and the retired
  feature keys — removed in one guarded, reversible transaction with a private
  archive retained in state `applied`.
- **Repository (Phase 4A):** 18 quantity SQL templates/patches, 20 quantity
  suite modules, the quantity phase result and design documents
  (`ARCHITECTURE_QUANTITY_COMPANY.md`, `SRS_QUANTITY_BASED_COMPANY.md`,
  `IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md`,
  `REQUIREMENTS_TRACEABILITY_QUANTITY_COMPANY.md`), the quantity schema-family
  registry, the temporary inventory-mode compatibility API, the T7 quantity
  benchmark harness and the one-shot static-retirement code.

What is deliberately **retained**:

- The Phase 3B archive, its restore command, controller, workflow, tests and
  `PHASE3B_MAINTENANCE_RUNBOOK.md` — these are the reversal path.
- Phase 0–3 operational evidence under `tests/PHASE*_RESULTS.md`.
- The 34 replaced `django_migrations` rows in production. The files themselves
  were deleted in checkpoint 4B and `replaces` was removed; the row prune was
  deliberately skipped (see the prune section above).
- `todo.md` and `tests/PHASE26_PERFORMANCE_CAPACITY_RESULTS.md` as historical
  execution records. They describe a system that no longer exists — read them
  as history, not as current behavior.

**Important for future work:** the ordinary word "quantity" is not by itself
evidence that something belongs to the retired family. Serial purchases,
sales, returns and stock reports legitimately store and display counts named
`qty`/`quantity`. Those are serial business fields and must be preserved.

## Maintenance Checklist

When changing the project, update this file if any answer changes:

- Did a route, app, or endpoint move?
- Did a permission, rate limit, or tenant guard rule change?
- Did a tenant table/function/view/trigger change?
- Did provisioning or existing-tenant rollout change?
- Did Docker, environment variables, or static handling change?
- Did test setup, commands, or expected coverage change?
- Did the alert conventions change, or was `Swal.fire` used directly instead of the `Alerts` helper?
