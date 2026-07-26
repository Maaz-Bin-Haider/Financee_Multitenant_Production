# Phase 16 — Quantity Physical Counts and Adjustments Results

Completed on 2026-07-26.

## Delivered

- Quantity schema family v12.
- Immutable physical-count sessions and lines with CNT numbering.
- Reproducible warehouse/SKU system-quantity snapshots at a declared cutoff.
- Submitted → approved/posted → guarded reversed workflow.
- Separate count-entry, adjustment-approval, and reversal permissions.
- Shortages consume FIFO and post Adjustment Loss / Inventory.
- Surpluses require an entered approved cost and post Inventory / Adjustment
  Gain.
- Exact counts post no movement or journal.
- Later legitimate movements remain preserved when a cutoff count is posted.
- Quantity UI/API, route protection, tenant provisioning, idempotent rollout,
  and production entrypoint wiring.

Surplus reversal is allowed only while the created FIFO layer remains untouched
and next in FIFO order. Unsafe reversals are rejected rather than consuming
unrelated stock.

## Verification

- Focused Phase 16 suite: **17/17 passed**.
- Complete suite: **29/29 modules passed**.
- System checks: **111/111 passed**.
- HTTP probe: **66 endpoints, 0 problems**.
- Deep serial lifecycle regression: **2702/2702 passed**.

Focused coverage includes exact counts, shortages, surpluses, FIFO valuation,
gain/loss accounting, repeated-post prevention, guarded reversal, negative
quantity and missing-cost rejection, cutoff preservation, tenant isolation,
permissions, schema verification, and HTTP navigation/summary.
