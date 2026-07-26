# Phase 22 — Quantity Reports and Dashboards Results

Date: 2026-07-26  
Result: PASS

## Delivered

- Quantity schema v22 with validated date, warehouse, SKU, variant, customer,
  vendor, tax, currency, threshold, age, and limit filters.
- Central mode-aware catalogue containing 40 accounts, stock/FIFO,
  reconciliation, sales/profit/return, purchase/vendor, and expense reports.
- Backend capability, company feature, and per-report permission enforcement.
- Dedicated responsive and accessible report workspace.
- UTF-8 CSV and native Excel SpreadsheetML exports.
- Quantity dashboard contracts for sales, stock, movement, parties,
  receivables, expenses, and alerts while retaining serial dashboard calls.
- Backend rejection of quantity access to serial-only report keys.
- Existing-tenant deployment ordering: reporting upgrade first, then
  idempotent quantity platform hardening without schema-version downgrade.

## Verification

- Phase 22 focused suite: **25/25 passed**.
- Every one of the 40 report keys executed on a freshly provisioned quantity
  tenant.
- All 14 quantity dashboard keys executed.
- Empty-ledger inventory movement reconciliation: exact zero variance.
- Complete mixed serial/quantity suite: **35/35 modules passed**.
- Legacy serial report suite: **60/60 passed**.
- HTTP regression suite: **70/70 passed**.
- Django system check: **0 issues**.
- Docker image build and static collection: passed.
- Python compilation, JavaScript syntax, and `git diff --check`: passed.

The expected exception logging in negative-path subscription, sale, and
currency tests was observed; those modules completed successfully.
