# Financee Multitenant Accounting and Inventory System

> Development resume point: Phases 0–26 are complete. **Phase 27 —
> CI/CD and ARM64** is next.
> Read `PROJECT_CONTEXT.md` and
> `IMPLEMENTATION_ROLLOUT_PLAN_QUANTITY_COMPANY.md` before starting.

Financee is a Django-based accounting and inventory application for multiple companies. Each company is isolated in its own PostgreSQL schema while shared Django data, users, permissions, and tenant registry tables live in `public`.

The application is intentionally SQL-centric: Django handles HTTP routing, authentication, permissions, templates, tenant activation, admin screens, and request validation; PostgreSQL stored functions, triggers, and views handle the accounting and inventory transactions.

## Current Stack

| Layer | Technology |
| --- | --- |
| Web framework | Django, pinned in `requirements.txt` / `requirements-lock.txt` |
| Database | PostgreSQL, schema-per-tenant design |
| Cache / rate limits | Django cache; Redis in Docker production |
| App server | Gunicorn |
| Reverse proxy | Nginx |
| Frontend | Django templates, static CSS, vanilla JavaScript |
| PDF/report support | ReportLab |
| Deployment | Docker Compose stack in `deploy/` |

> Note: `financee/settings.py` still contains a generated Django 5.2 header comment. The dependency files are the actual runtime source of truth.

## Architecture

```text
Browser
  |
  v
Nginx
  |
  v
Gunicorn / Django
  |
  |-- public schema
  |     auth_user, auth_group, permissions, sessions,
  |     tenancy_company, tenancy_membership
  |
  |-- tenant_company_1 schema
  |     business tables, functions, views, triggers
  |
  |-- tenant_company_2 schema
        business tables, functions, views, triggers
```

### Request Flow

1. A user logs in through `/authentication/login/`.
2. `TenantSchemaMiddleware` resolves the authenticated user's `Membership`.
3. The middleware sets PostgreSQL `search_path` to `"<tenant_schema>", public`.
4. Feature views execute raw SQL / stored functions without hard-coding a schema.
5. The middleware resets `search_path` to `public` after the response or exception.

Unauthenticated requests use `public`. Authenticated users without an active company are blocked from tenant features and redirected to login, except admin/auth/static paths.

## Multitenancy Model

The public tenancy registry and setup models include:

| Model | Location | Purpose |
| --- | --- | --- |
| `Company` | `tenancy/models.py` | Tenant registry row with immutable inventory mode, base currency, and tax environment. Auto-generates `schema_name` as `tenant_company_<id>`. |
| `Currency` | `tenancy/models.py` | Controlled ISO 4217 catalogue used for company base-currency selection. |
| `Membership` | `tenancy/models.py` | One-to-one mapping from user to company. Enforces one company per user. |

Creating a `Company` through the custom admin or `provision_tenant` command
selects the registered serial or quantity template from the trusted company
inventory mode. Quantity schemas use separate template, hardening, metadata,
and versioning artifacts.

Business tables are not Django models. They are created in each tenant schema from SQL.

## Database Design

The tenant template contains the per-company business database. Core objects include:

| Area | Main objects |
| --- | --- |
| Accounting | `chartofaccounts`, `journalentries`, `journallines`, `generalledger`, `vw_trial_balance` |
| Masters | `items`, `parties` |
| Purchase cycle | `purchaseinvoices`, `purchaseitems`, `purchaseunits` |
| Sales cycle | `salesinvoices`, `salesitems`, `soldunits` |
| Returns | `purchasereturns`, `purchasereturnitems`, `salesreturns`, `salesreturnitems` |
| Cash movement | `payments`, `receipts`, `contra_entries`, `opening_cash` |
| Inventory | `stockmovements`, `stock_report`, `stock_worth_report`, serial ledger functions |
| Equity / period close | `owner_equity_transactions`, `period_closes` |
| Reporting | dashboard functions, sales report JSON functions, monthly reports |
| Tenant versioning | `tenant_schema_version` |

Important SQL entry points include:

- `add_party_from_json`, `update_party_from_json`, `get_party_by_name`
- `add_item_from_json`, `update_item_from_json`, `get_item_by_name`
- `create_purchase`, `delete_purchase`, `get_current_purchase`, `get_purchase_summary`
- `create_sale`, `delete_sale`, `get_current_sale`, `get_sales_summary`
- `create_sale_return`, `update_sale_return`, `delete_sale_return`
- `create_purchase_return`, `update_purchase_return`, `delete_purchase_return`
- `make_payment`, `update_payment`, `delete_payment`
- `make_receipt`, `update_receipt`, `delete_receipt`
- `make_contra`, `update_contra`, `delete_contra`
- `create_opening_stock`, `delete_opening_stock`, `reclassify_opening_balance_to_capital`
- `set_opening_cash_from_json`
- `add_owner_equity_txn`, `delete_owner_equity_txn`
- `preview_period_close`, `close_period_from_json`, `reverse_period_close`
- `sales_summary_json`, `product_profitability_json`, `customer_profitability_json`, `invoice_register_json`

When changing business tables or stored functions:

1. Update `tenancy/sql/tenant_template.sql` so new tenants receive the change.
2. Create an idempotent SQL patch in `tenancy/sql/`.
3. Apply it to existing tenants with:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/<patch>.sql
```

Use `CREATE OR REPLACE FUNCTION`, `CREATE INDEX IF NOT EXISTS`, and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` patterns so patches are safe to rerun.

## Django Apps

| App | Responsibility |
| --- | --- |
| `authentication` | Login, logout, current-user JSON, login rate limit |
| `tenancy` | Company registry, membership, schema switching, provisioning, tenant SQL rollout commands |
| `home` | Dashboard page and dashboard JSON APIs |
| `parties` | Customer/vendor/expense/cash party master screens and autocomplete |
| `items` | Item master screens, item updates, autocomplete, item list JSON |
| `purchase` | Purchase invoice create/update/delete, navigation, summary, serial checks |
| `sale` | Sale invoice create/update/delete, navigation, summary, serial lookup |
| `purchaseReturn` | Purchase return create/update/delete, serial lookup, summaries |
| `saleReturn` | Sale return create/update/delete, serial lookup, summaries |
| `payments` | Outgoing payments, navigation, history, party balance |
| `receipts` | Incoming receipts, navigation, history, party balance |
| `contra` | Party-to-party contra entries, navigation, history, party balance |
| `attachments` | Authenticated image/PDF metadata, preview, download, and file cleanup for business documents |
| `accountsReports` | Ledgers, trial balance, cash ledger, receivable/payable, stock, serial, and monthly reports |
| `sales_reports` | Sales analytics APIs and report screen |
| `set_opening` | Opening cash singleton |
| `opening_stock` | Opening stock loads and opening-balance reclassification |
| `owner_equity` | Owner capital drawings/investments |
| `month_close` | Period close preview, close, and reversal |

## Main URL Surface

| Prefix | Purpose |
| --- | --- |
| `/authentication/` | Login, logout, current user |
| `/admin/` | Custom Financee admin site |
| `/home/` | Dashboard and dashboard APIs |
| `/parties/` | Party master |
| `/items/` | Item master |
| `/purchase/` | Purchase workflow |
| `/sale/` | Sales workflow |
| `/purchaseReturn/` | Purchase returns |
| `/saleReturn/` | Sales returns |
| `/payments/` | Payments |
| `/receipts/` | Receipts |
| `/contra/` | Contra entries |
| `/attachments/` | Authenticated attachment metadata, preview, and download endpoints |
| `/accountsReports/` | Accounting and inventory reports |
| `/sales-reports/` | Sales analytics |
| `/set-opening/` | Opening cash |
| `/opening-stock/` | Opening stock |
| `/owner-equity/` | Owner equity |
| `/month-close/` | Period close |

The legacy `/accountsReports/company-valuation/` and `/accountsReports/sale-wise-report/` Profit Reports page has been retired from the UI/routes. Its replacement coverage lives in Monthly Reports, Sales Reports, and dashboard sales/profit widgets. Database objects and historical permissions were left in place for compatibility.

## Document Attachments

Sale, purchase, sale return, purchase return, payment, receipt, and contra screens support optional document attachments. Each document can have at most one image and one PDF. A user may upload either file type or both file types on create/update.

Attachment metadata is stored in each tenant schema in `document_attachments`; file bytes are stored under `PRIVATE_MEDIA_ROOT/document_attachments/<tenant>/<document_type>/<document_id>/`. Private media is never served directly by Nginx: `deploy/nginx/financee.conf` returns 404 for `/media/private/`, and files are streamed only through authenticated Django endpoints.

Supported files:

- Images: JPG/JPEG, PNG, WEBP, GIF; maximum 10 MB.
- PDFs: `application/pdf`; maximum 20 MB.
- One file per kind per document: one `image` row and one `pdf` row.

Update behavior:

- Uploading a new image replaces only the existing image.
- Uploading a new PDF replaces only the existing PDF.
- If a document already has an image and the user later uploads only a PDF, the image is preserved. The reverse is also true.
- The frontend warns when a selected file will replace an existing file of the same kind.
- Deleting a document removes its attachment metadata and physical files after the business delete succeeds.

Performance behavior:

- Navigation endpoints such as previous/next invoice fetches do not return file blobs.
- The page renders the business document first, then loads attachment metadata asynchronously from `/attachments/<document_type>/<document_id>/`.
- Image/PDF bytes are fetched only when the user chooses Preview or Download, so old-document navigation remains lightweight.

Business update behavior:

- Sale, purchase, sale-return, and purchase-return updates support an attachment-only path. If the submitted business payload matches the current document and only files are being added/replaced, the view saves attachments without calling the stored update function. This allows files to be added to locked documents, such as sale invoices with return history, without mutating accounting or inventory data.
- Payments, receipts, and contra entries do not use that attachment-only bypass. Their update flow still calls the normal stored update function, then saves attachments after a successful update.

Existing tenant rollout:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/add_document_attachments.sql
```

With Docker:

```bash
docker compose -f deploy/docker-compose.yml exec -T web python manage.py apply_sql_all_tenants tenancy/sql/add_document_attachments.sql
docker compose -f deploy/docker-compose.yml exec -u root web chown -R 10001:10001 /app/media
```

`tenancy/sql/add_document_attachments.sql` is idempotent and folded into `tenant_template.sql`, `production_hardening.sql`, and `build_multitenant_db.sql`. New tenants receive the table automatically; existing tenants need the rollout patch before uploads are tested.

## Subscription Control

Financee is sold per company on manual monthly billing: clients pay outside
the system (e.g. bank transfer) and the operator controls access from the
admin panel. There is no payment gateway.

How it works:

- Each `Company` has a **Paid until** date, **Grace days** (default 3), and
  **Warn days before** (default 7). When `paid_until + grace_days` passes,
  every user of that company is blocked automatically. Leaving **Paid until**
  empty disables enforcement for that company.
- **Suspended** is a manual kill switch on the company that blocks access
  immediately, regardless of dates.
- Blocked users can still log in, but every page shows a branded
  "Account Suspended" notice explaining that the subscription payment is
  overdue and access resumes after payment. API/AJAX calls receive a 403 JSON
  denial. Login, logout, static files, and the admin remain reachable, and
  superusers are never blocked.
- In the warning window (and during grace) tenant users see a dismissible
  renewal banner with the exact dates.

Admin workflow when a client pays:

1. Open **Companies & Subscriptions** (or the company itself) in the admin.
2. Add a **Subscription payment** (amount, date received, months covered,
   optional note) — inline on the company or via the Subscription Payments
   changelist.
3. Saving the payment extends **Paid until** by the covered months (from the
   current paid-until date when still active, otherwise from the payment date)
   and automatically lifts a manual suspension. Payments are an immutable
   audit log; editing or deleting them never shrinks the paid-until date.

The admin dashboard shows **Client Companies** and **Blocked Subscriptions**
KPI cards, and the company list shows a live subscription badge
(Active / Expires soon / Grace / Blocked / Suspended / Not enforced) with bulk
suspend / lift-suspension actions.

### Subscription emails

The system emails the **company's billing address** (set per company as
**Contact email** — not individual users) automatically:

- On the day the subscription expires: "your subscription expired on X, you
  have N days to pay, access will be restricted after Y".
- On the day the grace window ends (access suspended): "your access is now
  suspended and resumes as soon as the payment is received".
- When you manually suspend a company from the admin, it is emailed
  immediately.

Setup, all inside the admin under **Billing & email settings**:

1. Enter the sender account: sender name, email, and an SMTP **app password**
   (for Gmail: Google Account → Security → 2-Step Verification → App
   passwords). Host/port default to Gmail (`smtp.gmail.com:587`, TLS).
2. Enter the contact details embedded in every email: WhatsApp number, phone,
   and an optional note (e.g. bank account details or office hours). All
   editable at any time.
3. Save, then click **Send a test email to the sender address** to verify.
4. Set each company's **Contact email** on its admin page.

Every email (sent, failed, test) is listed under **Sent Emails** in the admin.
Each billing cycle sends each notice at most once (failed deliveries are
retried automatically on the next hourly scan), and recording a payment starts
a fresh cycle. The scan runs hourly inside the web container; it can also be
run manually:

```bash
docker compose -f deploy/docker-compose.yml exec -T web python manage.py send_subscription_emails --dry-run
```

All subscription data lives in the shared `public` schema
(`tenancy/migrations/0002_subscription_control.py`); tenant business schemas
are untouched. Applying the migration blocks nobody: existing companies start
with enforcement disabled until you set their first paid-until date or record
a payment.

## Per-Company Feature Flags

The operator can enable/disable features for a specific company from the
company's admin page (collapsible **Features** sections). Everything is
public-schema registry data (`Company.disabled_features`,
`tenancy/0004_company_feature_flags`) — no tenant SQL. All features start
enabled; existing companies are unaffected by the migration.

What can be switched per company:

- **Report groups** — Accounts Reports, Stock Reports, Monthly Reports,
  Sales Reports, Opening Stock, Opening Cash (Set Opening). Each group has a
  master switch, and every sub-report inside the four report groups has its
  own switch (e.g. Cash Ledger, Trial Balance, Serial Ledger, Company
  Position, Invoice Register).
- **CSV / Excel export** — removes the CSV download buttons from every report
  screen (including Month-End Close and Owner Equity). PDF and Print stay.
- **Document attachments** — hides the image/PDF widget entirely (uploads and
  existing files) and blocks the attachment endpoints. Files are never
  deleted; re-enabling the feature brings them back.

Disabled features disappear from the sidebar and from in-page report buttons,
and their URLs are enforced by the tenant middleware: data/API calls get a
scrubbed 403 JSON, while a plain page visit to a disabled sub-report redirects
to the first enabled report of the same group (or the dashboard). Enforcement
applies to every user of the company, superusers included.

The company changelist shows a **Features off** count per company. Coverage
lives in `tests/suite/test_feature_flags.py`.

## Permissions and Guards

Permissions are seeded through migrations in `authentication/migrations/`. The middleware has a path-level guard in `financee/security.py`.

Protected prefixes include sales, purchases, returns, payments, receipts, parties, items, contra, opening stock, owner equity, set opening, and month close. Sales report APIs use an "any of these report permissions" rule, so a user can access the report module if they have at least one sales report permission.

The middleware also applies basic rate limits:

- dashboard APIs: 180 requests per minute
- report APIs: 90 requests per minute
- lookup/autocomplete endpoints: 240 requests per minute
- login POST: 10 requests per minute

In production, Redis should be configured through `REDIS_URL` so rate limits apply across workers.

## Admin Site

The project uses `financee/admin_site.py` instead of Django's default admin site directly.

Admin features:

- superuser-only custom admin access
- Financee branding
- Company and Membership management
- tenant schema provisioning when companies are created
- user activity pages and PDF export
- optional cross-tenant activity aggregation through `TENANCY_CROSS_TENANT_ACTIVITY`

## Local Setup

Create an environment file. For Docker, copy `deploy/.env.example` to `deploy/.env`. For direct local development, create `.env` at the project root with the same variables:

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=
DB_NAME=financee
DB_USER=financee
DB_PASSWORD=change-me
DB_HOST=localhost
DB_PORT=5432
```

Install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-lock.txt
```

Run public-schema migrations:

```bash
python manage.py migrate
```

Create a superuser:

```bash
python manage.py createsuperuser
```

Provision a tenant and attach an existing user:

```bash
python manage.py provision_tenant "Demo Company" --owner alice
```

Run the development server:

```bash
python manage.py runserver
```

## Docker Deployment

The production stack lives in `deploy/`:

- `db`: PostgreSQL 16
- `redis`: shared cache / rate limits
- `web`: Django + Gunicorn
- `nginx`: reverse proxy and static/media serving

Start it with:

```bash
cd deploy
cp .env.example .env
# edit .env
docker compose up -d --build
```

On first database boot, `build_multitenant_db.sql` seeds public objects and an example tenant. On every web container start, `deploy/entrypoint.sh` waits for Postgres, syncs baked static files, and runs `python manage.py migrate --no-input` for the shared public schema.

Static files are collected at image build time with `ManifestStaticFilesStorage`. The entrypoint copies the baked static tree into the shared static volume so Nginx serves current hashed assets after deploys.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and pull
request:

1. **checks** — installs `requirements-lock.txt`, runs `manage.py check` and
   `makemigrations --check --dry-run` (fails if a model change is missing its
   migration).
2. **test** — builds the production Docker image, boots the real compose
   stack (fresh Postgres seeds `build_multitenant_db.sql`; the entrypoint runs
   public migrations + `production_hardening.sql` exactly like production),
   creates a CI superuser, provisions a second tenant, then runs **all** test
   harnesses inside the container: `tests/suite/run_all.py`,
   `test_system.py`, `test_http.py`, `test_transaction_lifecycle_deep.py`.
   Stack logs are uploaded as an artifact on failure.
3. On `main`, the **exact tested image** is pushed to GHCR
   (`ghcr.io/maaz-bin-haider/financee-web`) tagged with the commit SHA and
   `latest`.
4. **deploy** — pauses for manual approval (the `production` GitHub
   environment), then SSHes to the EC2 host and runs
   `deploy/deploy_pull.sh`, which pulls the SHA-tagged image (no build on the
   server), recreates web + nginx, health-checks through nginx, **rolls back
   to the previous image if the health check fails**, and applies idempotent
   tenant SQL to every schema. `deploy/deploy.sh` remains as the manual
   build-on-server fallback.

One-time setup:

- **Approval gate:** Settings → Environments → create `production` → add a
  required reviewer.
- **Secrets** (Settings → Secrets and variables → Actions): `EC2_HOST`,
  `EC2_USER`, `EC2_SSH_KEY` (private key), optional `EC2_APP_DIR` (defaults
  to `~/Financee_Multitenant_Production`).
- **Activate deploys:** add repository *variable* `DEPLOY_ENABLED=true`.
  Until then the deploy job is skipped and CI is test-only.
- **Image pull on the server:** make the GHCR package public, or run a
  one-time `docker login ghcr.io` on EC2 with a `read:packages` PAT.

Nginx no longer needs a restart when the web container is recreated: the
static `upstream` block was replaced with Docker's DNS resolver + a variable
`proxy_pass` in `deploy/nginx/financee.conf` (see FIXED_ISSUES.md 2026-07-08).

Rollback caveat: rolling back the web image does not revert public migrations
or tenant SQL already applied by the failed release — keep both
backward-compatible (the existing idempotent-patch discipline).

## Tenant Operations

Create a tenant:

```bash
python manage.py provision_tenant "Company Name"
```

Create a tenant and assign an existing user:

```bash
python manage.py provision_tenant "Company Name" --owner username
```

Select company accounting setup explicitly:

```bash
python manage.py provision_tenant "Company Name" \
  --inventory-mode quantity \
  --base-currency USD \
  --tax-environment tax \
  --owner username
```

Synchronize the bundled ISO 4217 catalogue idempotently:

```bash
python manage.py seed_currencies
```

Apply SQL to every tenant:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql \
  --family serial
```

Preview target schemas without applying:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql \
  --family serial --dry-run
```

Apply to one tenant:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql \
  --family serial --only tenant_company_3
```

Retry a failed or pending schema build:

```bash
python manage.py retry_tenant_provisioning COMPANY_ID
```

The quantity accounting foundation includes the system chart of accounts, immutable
double-entry journals and reversals, trial balance, and concurrency-safe
document numbering.

Quantity schema version 3 also provides the product/variant master through
`/items/quantity/`: six controlled units, seven required variant dimensions,
unique or suggested SKUs, unit precision validation, catalogue lookup, and
transaction-aware SKU/unit locking. Other quantity business screens remain
intentionally gated until warehouse, stock, and transaction phases are
complete.

Quantity schema version 4 adds multi-warehouse setup through
`/warehouses/quantity/`. Authorized users can list, create, rename, activate,
deactivate, select a default, and delete only unreferenced warehouses. The
database enforces normalized code/name uniqueness and at most one active
default warehouse per quantity tenant.

Quantity schema version 5 adds the isolated stock core used by later quantity
documents. It records immutable movements, maintains per-SKU/per-warehouse
balances, consumes FIFO cost layers with durable allocation lineage, supports
historical availability, and deterministically replays permitted backdated
events. Scope locks prevent overselling under concurrency, canonical lock
ordering supports future multi-warehouse operations, and reconciliation
functions prove movement, balance, and FIFO agreement. Quantity invoice screens
remain gated until their assigned phases; Phase 10 is opening stock.

Quantity schema version 6 enables `/opening-stock/` for quantity companies.
Users select SKU, warehouse, quantity, and unit cost without entering serial
numbers. Posting creates an immutable opening document, FIFO stock movements,
and a balanced Inventory/Opening Balance journal. Untouched opening layers can
be reversed through linked movements and journals, and Opening Balance can be
reclassified to Owner's Capital after onboarding is complete. Serial companies
continue to use the existing serial-based opening-stock screen. Phase 11 is
quantity purchases.

Quantity schema version 7 enables `/purchase/` for quantity companies.
Domestic credit and cash purchases accept vendor, date, SKU, warehouse,
quantity, unit cost, and description without serial numbers. Posting creates
FIFO stock and balanced Inventory/AP or Inventory/Cash/Bank accounting.
Duplicate requests are idempotent, navigation and summaries are available,
safe edits retain revision history and replay later FIFO allocations, and
untouched purchases can be reversed. Tax, discounts, foreign currency,
attachments, and the full quantity party master remain scheduled later.
Serial companies continue to use the existing serial purchase workflow.

Quantity schema version 8 enables `/sale/` for quantity companies. Domestic
credit and cash sales accept customer, date, SKU, warehouse, manual quantity,
unit price, and description without serial numbers. PostgreSQL locks stock,
persists FIFO allocations, rejects overselling, and posts Revenue,
Accounts Receivable or Cash/Bank, COGS, and Inventory atomically. Idempotent
create, guarded edit/replay and reversal, navigation, and summaries are
available. Sale returns, tax, discounts, foreign currency, attachments, and
the full quantity party master remain scheduled for later phases.

Quantity schema version 13 adds tax and discounts across purchases, sales, and
both source-linked return flows. Tax companies support administered tax codes,
inclusive/exclusive pricing, taxable/zero-rated/exempt lines, and
percentage/fixed discounts at line and invoice levels. Posted inputs and
results are immutable snapshots; partial returns reverse historical tax
proportionally. Non-tax companies retain zero-tax behavior and cannot post tax
control entries.

### Tenant Login Redirect Loop

If a company user signs in successfully but the browser reports too many redirects between `/home/` and `/authentication/login/`, the user is usually authenticated but the tenant guard is rejecting the assigned company schema.

Check that the user has a `Membership`, the company is active, the physical tenant schema exists, and the tenant schema has `tenant_schema_version`. Older databases bootstrapped before the schema-version guard may have business tables but no version table.

Apply the existing hardening patch to all tenants:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql \
  --family serial
```

With Docker:

```bash
docker compose -f deploy/docker-compose.yml exec -T web \
  python manage.py apply_sql_all_tenants \
  tenancy/sql/production_hardening.sql --family serial
```

After applying it, clear the browser cookie/session for the host or use a fresh private window before logging in again.

## Testing

The functional test suite is documented in `tests/README.md`.

Run through Docker:

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh
```

Run with tenant reset:

```bash
./tests/run_tests.sh --reset
```

The suite has three major harnesses:

- `tests/test_system.py`: direct SQL business-function coverage per tenant
- `tests/test_http.py`: Django client coverage for real views, permissions, JSON, templates, and write flows
- `tests/suite/test_attachments.py`: dedicated document-attachment coverage for sale, purchase, sale return, purchase return, payment, receipt, and contra files, including upload/update/replacement, endpoint access, validation, cleanup, and bypass rules.
- `tests/suite/test_subscription.py`: subscription-control coverage — paid-until/grace/suspension state machine, payment-extension math, suspension page and JSON denial, exemptions (logout, superuser), and the renewal warning banner.
- `tests/suite/test_subscription_emails.py`: subscription email coverage — settings singleton, expiry/suspension emails with per-cycle dedup and failure retry, contact-detail embedding, manual-suspension and test emails, and the admin email screens (locmem backend; nothing real is sent).
- `tests/test_transaction_lifecycle_deep.py`: direct SQL stress coverage for real serial lifecycles, mixed purchase invoice corrections, partial returns, sale-return update/delete after resale, sale invoice update/delete after returns, cash-sale vs credit-sale returns, multi-item mixed serial invoices, duplicate/wrong-party return guards, and report execution after every entry. It also asserts financial invariants at every checkpoint (trial balance balances, no orphaned journal lines, stock/sold coherence) and covers the transaction-integrity guards from `tenancy/sql/fix_transaction_integrity_guards.sql` (delete_purchase sold-serial guard, qty-vs-serial validation, COGS reflow on purchase price edits). Confirmed-but-unfixed defects can be marked `known_bug=True` and are reported as `XFAIL` without failing the suite. See `tests/TRANSACTION_LIFECYCLE_FLOW_RESULTS.md`.

## Project Rules for Future Changes

- Keep `PROJECT_CONTEXT.md` updated whenever architecture, routes, tenant SQL, deployment, environment variables, permissions, or tests change.
- Business schema changes must update both `tenant_template.sql` and an idempotent rollout SQL file for existing tenants.
- Do not introduce Django ORM models for tenant business tables unless the multitenant `search_path` strategy is explicitly accounted for.
- Always reset or preserve `search_path` in management commands and admin utilities that activate tenant schemas manually.
- Keep tenant-facing errors generic; middleware currently scrubs JSON error details for 4xx/5xx responses.
- Checking CI CD from new device
