# Phase 17 — Quantity Tax and Discount Engine Results

Completed on 2026-07-26.

## Delivered

- Quantity schema family v13 with synchronized tenant tax environments.
- Authorized tax-code administration and validated Input/Output Tax accounts.
- Taxable, zero-rated, exempt, inclusive, and exclusive calculations.
- Percentage/fixed line and invoice discounts in the approved order.
- Deterministic proportional invoice-discount allocation.
- Immutable purchase/sale snapshots and tax-control journals.
- Historical proportional tax/discount reversal for both partial-return flows.
- Purchase/sale calculation controls and tax-code administration UI.
- Database-enforced non-tax company boundary.

## Verification

- Focused Phase 17 suite: **26/26 passed**.
- Complete mixed-family suite: **30/30 modules passed**.
- HTTP checks: **70/70 passed**.
- Serial system harness: **111/111 passed**.
- Deep serial lifecycle: **2702/2702 passed**.
- Quantity foundation: **29/29 passed**.
- Quantity accounting: **39/39 passed**.
- Phase 16 regression: **17/17 passed**.
- Python compilation, `git diff --check`, migration drift, and Compose
  configuration checks passed.
- Django deployment check had no errors; only the three expected isolated-test
  warnings for HSTS, SSL redirect, and the dummy secret.

The matrix covers rounding remainders, 0%/100% tax, 100% discounts,
negative/excessive rejection, history stability, non-tax denial, all four
transaction lifecycles, control-account reconciliation, reversals,
existing-tenant rollout, administration, and UI.
