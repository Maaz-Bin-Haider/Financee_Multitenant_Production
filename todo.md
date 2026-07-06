# TODO

## [x] DONE (2026-07-06): Write detailed document-attachment tests

Added `tests/suite/test_attachments.py` and wired it into `tests/suite/run_all.py`.
The module creates real tenant business documents, uses Django's real test
client with tenant middleware, isolates private media under a temp directory,
and covers sale, purchase, sale return, purchase return, payment, receipt, and
contra attachment flows.

Coverage includes one image + one PDF uploads, one-file-per-kind replacement,
preserving the unselected file kind during update, authenticated
metadata/preview/download endpoints, invalid file type/size validation, cleanup
after successful document delete, no cleanup after failed business delete,
attachment-only update bypass for sale/purchase/returns, and validation proving
payments/receipts/contra do not use that bypass.

Verification: in-memory Python syntax check passed;
`docker compose -f deploy/docker-compose.yml exec web python tests/suite/test_attachments.py`
passed 208/208 attachment checks; full
`docker compose -f deploy/docker-compose.yml exec web python tests/suite/run_all.py`
passed all modules.

---

## [x] DONE (2026-07-03): Port the cash-party feature to `tenant_company_1`

Completed by `tenancy/sql/fix_cash_party_port.sql` (idempotent; applied to all
tenants via `apply_sql_all_tenants`; folded into `tenant_template.sql`,
`production_hardening.sql`, and `build_multitenant_db.sql`; tenant schema
version bumped to **5**). Full write-up in `FIXED_ISSUES.md` →
"2026-07-03: Cash-Party Feature Ported to All Tenants".

Key findings from the port (vs. the risk analysis below, kept for history):

- The feared function-redefinition conflict **did not exist**: no integrity
  patch redefines the four `rebuild_*` journal builders or
  `detailed_ledger`/`detailed_ledger2` — the COGS-reflow fix only *calls*
  `rebuild_sales_journal`. Live `pg_get_functiondef` diffs proved
  `tenant_company_2`'s cash-aware bodies were byte-identical to
  `add_cash_transactions.sql` / `add_cash_party_ledger.sql` and already passed
  every integrity test alongside the guards. The "merge" reduced to applying
  those exact bodies.
- The gap was **worse than a misclassification**: `sale/views.py` and
  `purchase/views.py` call `get_cash_party_id(...)` / read `is_cash`
  unconditionally, so cash sales/purchases *errored* on `tenant_company_1`.
- A second drift layer surfaced during verification: the **invoice-description
  feature** (`description` columns on the four document tables +
  description-aware `get_current_*` fetchers from
  `add_invoice_description.sql`) was also missing on `tenant_company_1`, and
  the cash-aware ledger functions read those columns. It is included in the
  port patch as a prerequisite.
- `tests/suite/test_sales.py` now asserts the cash path **unconditionally**
  (feature-detection branch removed) plus sentinel-party seeding and
  `get_cash_party_id` resolution.

Verification (all green, 2026-07-03): `tests/suite/run_all.py` — ALL MODULES
PASSED (30/30 sales and 60/60 reports on *both* tenants; 70/70 HTTP);
`tests/test_transaction_lifecycle_deep.py` — all deep lifecycle checks passed
on both tenants; updated `tenant_template.sql` builds cleanly in a throwaway
schema; updated `production_hardening.sql` reruns cleanly on both tenants;
both tenants at `tenant_schema_version = 5` with both cash parties seeded.

<details>
<summary>Historical risk analysis (pre-port, superseded)</summary>

The original deferral reasoning: blindly replaying `add_cash_transactions.sql`
was believed dangerous because it does `CREATE OR REPLACE` on
`rebuild_sales_journal` etc., and the COGS-reflow fix in
`fix_transaction_integrity_guards.sql` depends on the current
`rebuild_sales_journal`. The planned mitigation was a hand-merged migration.
Live inspection showed the integrity patches never touch those functions, so
the patch bodies themselves were already the correct "merged" versions.

</details>
