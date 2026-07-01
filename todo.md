# TODO

> Start here next session. The item below is the outstanding work, captured in
> full so it can be picked up cold.

---

## [ ] TODO (next): Port the cash-party feature to `tenant_company_1`

Status: **deferred / not started.** Tenant schema drift found by `tests/suite/`.
Everything else the suite surfaced has been healed (`tenancy/sql/fix_tenant_drift.sql`,
tenant schema version 4). This is the one remaining gap.

### What the "cash-party" feature is

Financee records sales and purchases as **credit** transactions by default: a
sale debits the customer's Accounts Receivable, a purchase credits the vendor's
Accounts Payable. The **cash-party feature** adds first-class support for **cash**
transactions — a cash sale should debit the **Cash** account (money received now)
instead of a customer's AR, and a cash purchase should credit **Cash** instead of
a vendor's AP.

The implementation on `tenant_company_2` works like this:

- A boolean column **`parties.is_cash`** marks special parties.
- Two seeded parties, **"Cash Sale"** and **"Cash Purchase"**, carry `is_cash = true`.
- A helper **`get_cash_party_id(kind)`** resolves the right cash party.
- The journal builders (`rebuild_sales_journal`, `rebuild_purchase_journal`, and
  the two return variants) check `COALESCE(is_cash, false)` on the party and
  branch: if the party is a cash party, post the cash leg to the **Cash** account
  (no party AR/AP line); otherwise post to the party's AR/AP as usual.

So on `tenant_company_2`, selecting "Cash Sale" as the customer produces
`Debit Cash / Credit Sales Revenue` (+ COGS/Inventory), and the cash party never
accrues a receivable balance.

### What's actually on each tenant (verified)

| | `tenant_company_1` | `tenant_company_2` |
|---|---|---|
| `parties.is_cash` column | **absent** | present |
| `get_cash_party_id()` function | **absent** | present |
| `rebuild_sales_journal` references `is_cash` | **no** | yes |
| "Cash Sale" / "Cash Purchase" parties | **absent** | present |

On `tenant_company_1` the entire cash branch simply doesn't exist —
`rebuild_sales_journal` always posts to the party's AR line, unconditionally.

### How the drift happened

Classic **tenant schema drift**. Business objects here are not Django models —
they live in each tenant's PostgreSQL schema and are rolled out with idempotent
SQL patches via `apply_sql_all_tenants`. The cash-party patches
(`add_cash_transactions.sql`, `add_cash_party_ledger.sql`) were applied to
`tenant_company_2` but **never applied to `tenant_company_1`**. Nothing enforces
that every patch reaches every tenant, so the two schemas diverged. (This is
exactly the class of problem the `tests/suite/` suite was built to catch, and
it did.)

### Why it matters — the impact

On `tenant_company_1` there is no way to record a true cash sale/purchase:

- If someone designates a sale as "cash" by pointing it at a cash-style party,
  the journal still debits that party's **Accounts Receivable** rather than
  **Cash**. The books stay *balanced* (debits = credits), so the trial-balance
  invariant doesn't catch it — but the **Cash account is understated** and a
  party accrues a receivable that will never be collected. It is a silent
  misclassification, not a crash.
- Cash-oriented reports (cash ledger, dashboard cash KPIs) and party balances are
  correspondingly wrong for any transaction that should have been cash.

So it is a **feature-parity / correctness gap**, not a hard failure — which is
why the suite treats it as a feature-detected skip rather than a failing test.

### Why porting it is risky (why it was deferred)

The obvious fix — "just apply `add_cash_transactions.sql` to `tenant_company_1`"
— is dangerous because of **function-redefinition ordering**:

- `add_cash_transactions.sql` does `CREATE OR REPLACE` on `rebuild_sales_journal`,
  `rebuild_purchase_journal`, `rebuild_sales_return_journal`, and
  `rebuild_purchase_return_journal`.
- Earlier work in `fix_transaction_integrity_guards.sql` fixed the **COGS-reflow
  bug**: `update_purchase_invoice` now calls `rebuild_sales_journal` to keep COGS
  in sync after a price-only purchase edit. That fix *depends on* the current,
  correct `rebuild_sales_journal`.
- Blindly replaying the older `add_cash_transactions.sql` would **overwrite
  `rebuild_sales_journal` with an older cash-aware version that predates the
  integrity fixes**, potentially reintroducing a COGS/reflow regression — and the
  trial balance would still balance, so it would not be obvious.

This is the same trap avoided when healing the purchase-return guard: a *fresh*
`CREATE OR REPLACE` was written in `fix_tenant_drift.sql` rather than replaying
`fix_return_serial_integrity.sql`, because that old patch also redefines
`create_sale_return`/`update_sale_return` and would have regressed the later
sale-return lifecycle guards.

So the cash-party port needs a **carefully-ordered, dedicated migration that
reconciles the cash logic with the current journal builders** — not a blind
replay.

### What a safe migration looks like

1. `ALTER TABLE parties ADD COLUMN IF NOT EXISTS is_cash boolean NOT NULL DEFAULT false;`
2. Seed the "Cash Sale" / "Cash Purchase" parties (idempotent) and add
   `get_cash_party_id`.
3. Produce **merged** versions of the four `rebuild_*` journal functions that
   contain **both** the cash branch (from `add_cash_transactions.sql`) **and** the
   current integrity behavior (the COGS logic the reflow fix relies on) —
   reviewed line-by-line, not replayed.
4. Apply to **all** tenants via `apply_sql_all_tenants`, and fold into
   `tenant_template.sql` / `production_hardening.sql` / `build_multitenant_db.sql`
   (bump the tenant schema version).
5. Verify: `tests/suite/test_sales.py`'s cash path now runs on
   `tenant_company_1` (no longer skipped); the transaction-integrity fixes and
   the deep lifecycle test still pass on **both** tenants.

### How the suite handles it today

`tests/suite/test_sales.py` calls `t.has_column("parties", "is_cash")`. Where the
feature exists (`tenant_company_2`) it runs the full cash-sale assertions (Cash
debited, party AR stays 0). Where it does not (`tenant_company_1`) it records a
passing "skipped: not on this tenant" note instead of failing — so the gap is
visible but does not produce a false red. **Once the migration lands, remove that
feature-detection branch** so the cash path is asserted on every tenant.

### References

- `FIXED_ISSUES.md` — 2026-07-01 "Tenant schema drift — diagnosed and healed"
  (item #5, cash-party deferred).
- `tests/suite/RESULTS.md` — "Tenant drift — healed" (item #5).
- `tests/suite/test_sales.py` — the `has_column("parties","is_cash")` branch.
- `tenancy/sql/add_cash_transactions.sql`, `tenancy/sql/add_cash_party_ledger.sql`
  — the original cash-party patches (source material; do not replay blindly).
- `tenancy/sql/fix_transaction_integrity_guards.sql` — the COGS-reflow fix the
  merged `rebuild_*` functions must preserve.
