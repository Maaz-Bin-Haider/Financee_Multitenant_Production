# Phase 12 — Quantity Sales Results

**Completed:** 2026-07-26  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement to version 8.
- Added immutable sale invoices, lines, and revision snapshots.
- Added tenant-local `SAL-000001` numbering and idempotency locks.
- Added domestic base-currency credit and cash sales.
- Added manual whole/three-decimal quantities with no serial-number workflow.
- Locked SKU/warehouse inventory scopes and rejected overselling in PostgreSQL.
- Persisted FIFO allocations and exact line-level COGS.
- Posted credit sales as Debit Accounts Receivable / Credit Sales Revenue.
- Posted cash sales as Debit Cash or Bank / Credit Sales Revenue.
- Posted FIFO cost as Debit COGS / Credit Inventory.
- Added guarded edit with atomic FIFO replay, journal reversal/repost, retained
  document number, and immutable prior-revision evidence.
- Added guarded reversal that restores stock at the original FIFO cost.
- Added details, navigation, date summary, and cash/credit totals.
- Added a quantity-specific sales screen through the existing `/sale/` routes.
- Kept tax, discounts, foreign currency, returns, settlements, and attachments
  in their assigned later phases.

## Focused Evidence

`tests/suite/test_quantity_sales.py` passed 34/34 checks covering:

- fresh v8 provisioning and schema verification;
- multi-line, multi-SKU, multi-warehouse, whole and decimal sales;
- partial, exact-final-stock, and multiple-layer FIFO consumption;
- exact Revenue, AR/Cash, COGS, Inventory, and trial-balance accounting;
- repeated and changed-payload idempotency behavior;
- zero, fractionally invalid, excessive, and zero-price rejection;
- guarded date/quantity/price edits, revisions, replay, and rollback;
- reversal and repeat-reversal denial;
- concurrent final-stock sales where exactly one succeeds;
- details, navigation, summary, tenant isolation, and idempotent rollout;
- quantity HTTP page/create validation/navigation/summary behavior; and
- denial of serial lookup endpoints for quantity companies.

## Complete Regression Evidence

- Production image build: passed.
- Django system check: no issues.
- Missing-migration guard: no changes detected.
- Full mixed-family suite: all 25 modules passed.
- Existing serial sale suite: 30/30 per serial tenant.
- Serial system harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: 2702/2702 per tenant.

## Exit Gate

**PASS**

- Database locks prevent overselling under final-stock concurrency.
- FIFO allocations and COGS are exact and durable.
- Credit sales affect AR; cash sales affect Cash/Bank without AR.
- Revenue, COGS, Inventory, and the trial balance reconcile.
- Unsafe edits roll back atomically and successful edits retain audit evidence.
- Reversal restores stock and accounting without deleting history.
- Existing serial behavior remains unchanged.
- Phase 13 quantity sale-return work may begin.
