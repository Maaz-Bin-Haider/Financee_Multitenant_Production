# Financee Multitenant Accounting and Inventory System

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

Only two Django ORM models represent tenancy:

| Model | Location | Purpose |
| --- | --- | --- |
| `Company` | `tenancy/models.py` | Tenant registry row. Auto-generates `schema_name` as `tenant_company_<id>`. |
| `Membership` | `tenancy/models.py` | One-to-one mapping from user to company. Enforces one company per user. |

Creating a `Company` through the custom admin or `provision_tenant` command provisions a physical tenant schema from `tenancy/sql/tenant_template.sql`.

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
| `/accountsReports/` | Accounting and inventory reports |
| `/sales-reports/` | Sales analytics |
| `/set-opening/` | Opening cash |
| `/opening-stock/` | Opening stock |
| `/owner-equity/` | Owner equity |
| `/month-close/` | Period close |

The legacy `/accountsReports/company-valuation/` and `/accountsReports/sale-wise-report/` Profit Reports page has been retired from the UI/routes. Its replacement coverage lives in Monthly Reports, Sales Reports, and dashboard sales/profit widgets. Database objects and historical permissions were left in place for compatibility.

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

## Tenant Operations

Create a tenant:

```bash
python manage.py provision_tenant "Company Name"
```

Create a tenant and assign an existing user:

```bash
python manage.py provision_tenant "Company Name" --owner username
```

Apply SQL to every tenant:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql
```

Preview target schemas without applying:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql --dry-run
```

Apply to one tenant:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql --only tenant_company_3
```

### Tenant Login Redirect Loop

If a company user signs in successfully but the browser reports too many redirects between `/home/` and `/authentication/login/`, the user is usually authenticated but the tenant guard is rejecting the assigned company schema.

Check that the user has a `Membership`, the company is active, the physical tenant schema exists, and the tenant schema has `tenant_schema_version`. Older databases bootstrapped before the schema-version guard may have business tables but no version table.

Apply the existing hardening patch to all tenants:

```bash
python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql
```

With Docker:

```bash
docker compose -f deploy/docker-compose.yml exec -T web python manage.py apply_sql_all_tenants tenancy/sql/production_hardening.sql
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

The suite has two major harnesses:

- `tests/test_system.py`: direct SQL business-function coverage per tenant
- `tests/test_http.py`: Django client coverage for real views, permissions, JSON, templates, and write flows
- `tests/test_transaction_lifecycle_deep.py`: direct SQL stress coverage for real serial lifecycles, mixed purchase invoice corrections, partial returns, sale-return update/delete after resale, sale invoice update/delete after returns, cash-sale vs credit-sale returns, multi-item mixed serial invoices, duplicate/wrong-party return guards, and report execution after every entry

## Project Rules for Future Changes

- Keep `PROJECT_CONTEXT.md` updated whenever architecture, routes, tenant SQL, deployment, environment variables, permissions, or tests change.
- Business schema changes must update both `tenant_template.sql` and an idempotent rollout SQL file for existing tenants.
- Do not introduce Django ORM models for tenant business tables unless the multitenant `search_path` strategy is explicitly accounted for.
- Always reset or preserve `search_path` in management commands and admin utilities that activate tenant schemas manually.
- Keep tenant-facing errors generic; middleware currently scrubs JSON error details for 4xx/5xx responses.
