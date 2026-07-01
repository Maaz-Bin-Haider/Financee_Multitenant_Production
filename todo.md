# TODO

## Deferred

- [ ] **Port the cash-party feature to `tenant_company_1`.**
  The cash-party feature (`parties.is_cash` column, `get_cash_party_id`, and the
  cash `rebuild_*` journal variants) exists on `tenant_company_2` but is absent
  on `tenant_company_1` (tenant schema drift found by `tests/suite/`).
  - Why deferred: porting it means replaying `add_cash_transactions.sql`, which
    redefines the `rebuild_sales_journal` / `rebuild_purchase_journal` /
    `rebuild_*_return_journal` functions and would risk regressing the
    transaction-integrity fixes in `fix_transaction_integrity_guards.sql`. It
    needs a carefully-ordered, dedicated migration rather than a blind replay.
  - Acceptance: `tenant_company_1` has the `is_cash` column and
    `get_cash_party_id`; the cash-sale path in `tests/suite/test_sales.py` runs
    on `tenant_company_1` (no longer feature-detected/skipped); the integrity
    fixes and deep lifecycle test still pass on both tenants; roll the change out
    to **all** tenants via `apply_sql_all_tenants` and fold into
    `tenant_template.sql` / `production_hardening.sql` / `build_multitenant_db.sql`.
  - References: `FIXED_ISSUES.md` (2026-07-01 drift heal entry),
    `tests/suite/RESULTS.md` (Tenant drift — healed, item #5),
    `tenancy/sql/add_cash_transactions.sql`, `tenancy/sql/add_cash_party_ledger.sql`.
