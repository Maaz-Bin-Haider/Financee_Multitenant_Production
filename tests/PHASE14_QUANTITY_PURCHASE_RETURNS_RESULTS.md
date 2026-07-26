# Phase 14 — Quantity Purchase Returns Results

Completed on 2026-07-26.

## Delivered

- Quantity schema family v10.
- Source-linked purchase-return headers, lines, revisions, and numbering.
- Persistent purchase-source allocation directives.
- FIFO replay that consumes only the selected original purchase source.
- Original purchase-cost valuation.
- Credit returns debit Accounts Payable; cash returns restore the original
  Cash/Bank account; every return credits Inventory.
- Partial, repeated, reverse, and guarded replacement/update lifecycles.
- Quantity-specific UI and HTTP adapter with serial lookup disabled.
- Automatic tenant rollout through `deploy/entrypoint.sh`.

The source directive is separate from the rebuildable FIFO projection. Replay
may reconstruct FIFO layers and allocations, while a purchase return remains
bound to stable inbound movement IDs and cannot substitute unrelated stock.

## Verification

- Focused Phase 14 suite: **22/22 passed**.
- Complete suite: **27/27 modules passed**.
- System checks: **111/111 passed**.
- HTTP probe: **66 endpoints, 0 problems**.
- Deep serial lifecycle regression: **2702/2702 passed**.

The focused suite covers partial/repeated returns, exhausted sources, wrong
vendor, sold stock, backdating, original-cost accounting, reversal, replacement
update, return-vs-return and return-vs-sale concurrency, credit/cash settlement,
isolation, schema verification, HTTP, and serial-route
denial. Transfers do not exist until Phase 15; transferred-source eligibility
will be exercised with that movement type.
