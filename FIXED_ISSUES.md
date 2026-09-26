# Fixed Issues

This file records production/setup issues that were diagnosed and fixed, including the root cause, code or SQL changes, and verification steps.

## 2026-09-26: Sidebar Hid Sales Reports From Most Report Permissions and Showed an Empty Inventory Badge

### Symptoms

Two defects in the tenant sidebar (`templates/base/base.html`), found while
auditing the README against the code:

1. A user granted only some of the sales-report permissions (for example only
   *Sales Trend* or *Invoice Register*) saw no **Sales Reports** link in the
   sidebar, although `/sales-reports/` itself opened for them.
2. Every tenant page showed an empty badge with a barcode icon under the
   company name (`aria-label="Inventory mode"`).

### Root Cause

1. The link's condition ended in a literal placeholder:
   `{% if perms.auth.can_view_sales_summary or perms.auth.can_view_product_profitability or ... %}`.
   Django parses `...` as a variable, which resolves to an empty string
   (false), so only the first two of the eight `SALES_REPORT_PERMS` counted.
   The route guard in `financee/security.py` correctly accepts any one of all
   eight (mode `any`).
2. The badge rendered `request.tenant_company.get_inventory_mode_display`. That
   method went away with `Company.inventory_mode` in the serial-only
   consolidation, and Django renders a missing attribute as an empty string,
   so the badge stayed on screen with no text.

### Fix

- The condition now lists all eight `SALES_REPORT_PERMS`, with a comment
  pointing at `financee/security.py`.
- The inventory-mode badge is removed; there is no inventory mode left to
  display.
- `tests/phase2_serial_runtime_removal_contracts.py` now fails if any
  `SALES_REPORT_PERMS` entry is missing from the sidebar condition (or the
  condition contains `...`), and if `inventory_mode` appears in `base.html`.
  `base.html` is excluded from the UI byte-identity pin, so no hash changed.

Template only: no SQL, schema version, migration or static-file change.

### Verification

- The old and new templates were rendered with Django 6.0.6 for each of the
  eight permissions on its own. The old template hid the link for six of them;
  the new one shows it for all eight, and still hides it with no sales-report
  permission or when the `sales_reports` feature is switched off. The old
  template rendered the empty badge; the new one does not and still shows the
  company name.
- The two new contract checks pass on the fixed tree and fail against the old
  `base.html`. All 13 database-free contract scripts from the CI `checks` job
  pass.

**Deployed to production 2026-09-26** (19:18 UTC) as
`53a12e0966f6519e8372f652b215c85b71fc31c3` (pushed directly to `main`,
workflow run `36264512993`), replacing
`3c50327197e55cb7a35f585c239e9d48265fdc4c`. All 15 gate, staging and publish
jobs passed first. The Phase 30 controller then passed every gate: preflight
before and after (`tenant_company_1`, serial v6, identical contract
fingerprint), the continuity comparison across all tenant balances, health
through nginx, and the latency / 5xx / CPU / memory thresholds. No rollback
was triggered. The tenant SQL step reported
`ok -> tenant_company_1 (serial v6)`; no tenant SQL changed in this release.

## 2026-09-16: Expense Parties Counted as Receivables on the Dashboard

### Symptoms

Paying an ordinary shop expense — rent, salaries, a utility bill — made that
expense head appear on the dashboard as a customer who owed the business
money. The Smart Alerts popup raised entries such as:

```text
Risky Customer: Staff Salaries
High receivable PKR 165000.00 with no payment received in the last 45 days.

Stale Receivable: Shop Rent
Balance PKR 85000.00 - last activity 12 days ago.
```

`fn_dash_receivables_aging` counted the same amounts in its aging buckets and
in `total_overdue_amount` / `total_medium_amount` / `total_fresh_amount`, so
the dashboard's receivables totals were overstated by the value of every
expense paid.

Found while seeding realistic demo data for the user guide; reproduced on a
fresh serial tenant.

### Root Cause

`add_party_from_json` wires an **Expense** party with *both* `ar_account_id`
(the shared Accounts Receivable account) **and** `ap_account_id` (its own newly
created Expense chart-of-accounts row). That is correct: `make_payment` then
debits the Expense account and credits Cash, tagging the line with the expense
party's id.

`vw_dash_party_ar_balance` summed **every** journal line carrying a party id,
regardless of which account the line was posted to, and admitted any party
whose `ar_account_id` was not null:

```sql
WHERE (p.ar_account_id IS NOT NULL)
GROUP BY ...
HAVING (COALESCE(sum(jl.debit) - sum(jl.credit), 0) > 0)
```

So the expense debit was counted as a receivable. Inspecting a real tenant made
the shape of the bug obvious:

| party_type | account its party-tagged lines hit | `= ar_account_id` |
|---|---|---|
| Customer | Accounts Receivable | always |
| Both | Accounts Receivable | always |
| Expense | its own Expense account | never |
| Vendor | Accounts Payable | n/a (`ar_account_id` is NULL) |

**Not affected:** `get_accounts_receivable_json_excluding` reads
`vw_trial_balance` and already filtered `type NOT ILIKE '%Expense%'`, so the
Accounts Receivable *report* was always correct. Only the dashboard was wrong,
which is why this survived so long — the two surfaces disagreed and nobody
compared them.

### Fix

Added `tenancy/sql/fix_dashboard_expense_receivables.sql` (idempotent; folded
into `tenancy/sql/tenant_template.sql`,
`tenancy/sql/production_hardening.sql` and `build_multitenant_db.sql`). The view
is constrained to lines actually
posted to the party's own receivables account:

```sql
WHERE (p.ar_account_id IS NOT NULL)
  AND (jl.account_id = p.ar_account_id)
```

This is deliberately an **account** test rather than `party_type <> 'Expense'`,
so the rule stays correct if a new party type is ever added. Customer and Both
parties are untouched (all their party-tagged lines are already on the AR
account); Vendors were already excluded.

Both consumers of the view — `fn_dash_smart_alerts` (the "Stale Receivable" and
"Risky Customer" alerts) and `fn_dash_receivables_aging` — are fixed by the
view change alone and needed no edit.

**Behaviour note.** For a *Both* party the view previously netted receivable
against payable, because it summed every line. It now reports only what they
owe, which is what a receivables view should show; their payable is still
reported by the payables report and the trial balance.

### Verification

On an isolated seeded stack (never production):

```bash
./fc.sh exec -T web python tests/suite/test_reports.py      # before: 61/65, 4 FAIL
./fc.sh exec -T web python manage.py apply_sql_all_tenants \
    tenancy/sql/fix_dashboard_expense_receivables.sql
./fc.sh exec -T web python tests/suite/test_reports.py      # after: 65/65
```

The four new checks in `tests/suite/test_reports.py`
(`_receivables_exclude_expenses`) fail against the old view and pass against
the new one, covering the view, `fn_dash_smart_alerts` and
`fn_dash_receivables_aging`, plus a guard that a genuine credit customer is
still reported.

Full regression after the patch: `tests/suite/run_all.py` **ALL MODULES
PASSED** (21 modules, including the phase gates), `tests/test_system.py` 0
failures, `tests/test_transaction_lifecycle_deep.py` fully passed,
`manage.py release_preflight` OK. Customer balances were byte-identical before
and after (Hassan Traders 1,111,600.00), confirming the change is surgical. A
tenant provisioned fresh from the updated template carries the fixed view;
rerunning `production_hardening.sql` on an already-patched tenant is a no-op.

**Deployed to production 2026-09-16** as
`3c50327197e55cb7a35f585c239e9d48265fdc4c` (PR #2, workflow run
`35116450398`), replacing `39dc506d610e930531271ef4e7c0a48a4d06ef80`. The
Phase 30 controller passed every gate: preflight, the pre/post continuity
fingerprint comparison across all tenant balances, health through nginx, and
the latency / 5xx / CPU / memory thresholds. No rollback was triggered. The
tenant SQL step reported `ok -> tenant_company_1 (serial v6)`, confirming the
fix rolled out with the schema version unchanged.

### Why there is no schema version bump

The first attempt bumped the tenant schema version to 7, following the
precedent of the v3/v4/v5 behaviour fixes. CI rejected it, and the reason is
worth recording: three separate places pin the serial schema version, and one
of them is
`serial_only_phase3_cleanup.registry`, which requires every tenant to be at
**exactly** version 6 before it will act. `operate()` routes *all* actions
through that guard — including `--action restore`, the Phase 3B reversal path
that `CLAUDE.md` says must be preserved. Bumping to 7 would therefore have left
a booby trap in disaster recovery: the reversal would refuse to run on a
production database until somebody edited a guarded, hash-pinned maintenance
command under incident pressure.

The bump bought nothing here. This change replaces one reporting view and is
compatible in both directions, and `production_hardening.sql` already applies
it to every tenant on every container start. The version gate exists for schema
changes that code depends on structurally; a reporting view is not one.

Two version pins were nevertheless made robust while investigating, because
both were latent bugs that would desync on any future bump:
`tests/phase0_serial_only_discovery_contracts.py` and
`serial_only_phase3_audit` now read the expected version from
`settings.TENANT_SCHEMA_VERSION` instead of a hardcoded literal (as the Phase 0
audit already did). `serial_only_phase3_cleanup` was deliberately left
untouched so its reviewed-source hash pin stays intact.

## 2026-07-27: Phase 28 Recovery Rehearsal Isolation and Portable Evidence

### Symptoms

The first disposable recovery source web container could not authenticate to
its database even though Compose was invoked with an isolated `--env-file`.
An interrupted retry also reused its constant local project volumes, and the
encrypted bundle sidecar named a temporary absolute path. The older Phase 27
stack helper also overwrote `deploy/.env` during local runs without restoring
the caller's file.

### Root causes

- Compose `--env-file` supplies substitution values but does not replace a
  service-level `env_file: .env`.
- A constant local project name makes interrupted disposable volumes reusable.
- `sha256sum` was initially invoked with the temporary absolute bundle path.
- The Phase 27 helper wrote its CI environment directly to `deploy/.env`.

### Fix and verification

- The rehearsal creates explicit source/restore service env-file overrides.
- Local project names include the process ID; CI uses `GITHUB_RUN_ID`.
- Sidecars contain only the relocatable bundle basename.
- The Phase 27 helper now saves and restores an existing `deploy/.env` (or
  removes its temporary file when none existed).
- The complete rerun passed in 163 seconds, restored in 43 seconds, rejected
  deliberately corrupted ciphertext, verified two serial schemas and restored
  media, provisioned quantity v22, ran the previous image against forward
  migrations, returned to the current image, and passed rollback simulation.

## 2026-07-25: Phase 1 Baseline Exposed a False-Green HTTP Harness and Fresh-Database Index Drift

### Symptoms

The comprehensive suite passed on a fresh isolated two-tenant stack, but the
separate `tests/test_http.py` harness printed 66/66 endpoint failures (all
tenant-guard 403 responses) and still exited with status 0. In the same fresh
stack, `tenant_company_1` had only 36 indexes while the newly provisioned
`tenant_company_2` had 86.

### Root Causes

1. The standalone HTTP harness looked for a user literally named `user1`, then
   fell back to the superuser. Fresh CI creates `ci_user1`, while the superuser
   intentionally has no tenant membership. The tenant middleware correctly
   denied every business route. Unlike `tests/suite/test_http.py`, the legacy
   harness did not attach a temporary membership.
2. The harness printed failures but never returned a non-zero process status,
   so CI treated the failing HTTP stage as green.
3. The 50 secondary indexes from `tenant_indexes.sql` were present at the end
   of `tenant_template.sql`, so tenants provisioned at runtime received them.
   The bootstrap tenant from `build_multitenant_db.sql` did not. Deploy scripts
   apply the index patch later, but the web entrypoint/CI startup path ran only
   `production_hardening.sql`, leaving the first tenant unindexed during CI and
   on a fresh startup before a deploy-script pass.

### Fix

- `tests/test_http.py` now uses the superuser with a temporary membership in
  the first active provisioned company, removes only the membership it created,
  and exits non-zero when any endpoint fails.
- `deploy/entrypoint.sh` now applies the idempotent `tenant_indexes.sql` patch
  after tenant hardening on every web-container start.

### Verification

- The repaired standalone HTTP harness exercises all 66 endpoints successfully
  on a fresh isolated tenant and returns status 0.
- Applying `tenant_indexes.sql` to both fresh tenants is idempotent and brings
  the bootstrap tenant to the same required secondary-index set as a tenant
  provisioned from `tenant_template.sql`.
- The comprehensive suite, SQL business-function harness, and deep transaction
  lifecycle suite remain green; full baseline details are recorded in
  `tests/PHASE1_BASELINE_RESULTS.md`.

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
