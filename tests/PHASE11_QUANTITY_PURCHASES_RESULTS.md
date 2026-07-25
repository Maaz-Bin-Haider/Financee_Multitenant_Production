# Phase 11 — Quantity Purchases Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement to version 7.
- Added immutable purchase invoice and line records plus immutable revision
  snapshots.
- Reused tenant-local `PUR-000001` numbering.
- Added required vendor-name snapshots pending Phase 19's shared party master.
- Added domestic base-currency credit and cash purchase modes.
- Added Cash (`1000`) and Bank (`1100`) selection for cash purchases.
- Added SKU, warehouse, quantity, six-decimal unit cost, line value,
  description, user, movement, journal, status, and reversal lineage.
- Posted all lines through the Phase 9 movement and FIFO engine.
- Posted credit purchases as Debit Inventory / Credit Accounts Payable.
- Posted cash purchases as Debit Inventory / Credit Cash or Bank.
- Added tenant-local idempotency locks so concurrent duplicate requests return
  the same purchase rather than racing at the unique constraint.
- Added complete details, first/current/previous/next/last navigation, date
  filtering, and cash/credit summary totals.
- Added guarded edits that retain the historical document number, snapshot the
  previous revision, replace source events under controlled database guards,
  replay affected FIFO scopes, and reverse/repost accounting atomically.
- Rejected edits that would make any historical point negative.
- Added guarded reversal for wholly unconsumed purchase layers.
- Enabled a quantity-specific no-serial purchase screen through the existing
  `/purchase/` routes and application theme.
- Kept tax, discounts, foreign currency, settlements, and attachments in their
  explicitly assigned later phases.

## Upgrade Evidence

The preserved isolated environment contained two serial tenants at serial
version 6 and one quantity tenant at quantity version 6. Production startup
applied serial hardening only to serial schemas and `quantity_purchases.sql`
only to the quantity schema. The quantity tenant reached version 7, passed
schema verification, and Gunicorn started successfully. Fresh quantity
schemas received the cumulative Phase 5–11 bootstrap and the same verified
fingerprint.

## Focused Evidence

`tests/suite/test_quantity_purchases.py` passed 46/46 checks covering:

- fresh version and fingerprint verification;
- multi-line, multi-SKU, multi-warehouse, whole and decimal purchases;
- exact movement quantity, FIFO layers, source lineage, and FIFO value;
- exact Inventory/AP/Cash and balanced journal assertions;
- cash purchases without vendor payable;
- repeated and simultaneous duplicate submission;
- changed-payload idempotency-key denial;
- fractional Piece, fourth-decimal measurement, zero cost, duplicate scope,
  and empty-document rollback;
- backdated purchase edits with deterministic later FIFO cost reflow;
- immutable previous-revision snapshots;
- historical-negative edit denial and complete rollback;
- untouched purchase reversal, repeat reversal denial, and consumed-layer
  reversal denial;
- concurrent purchase and sale scope locking without negative stock;
- details, navigation, date summary, and cash/credit totals;
- tenant-isolated numbering, idempotency keys, stock, and AP;
- idempotent rollout;
- quantity page/create/navigation/summary HTTP behavior;
- quantity serial-check endpoint denial; and
- tenant search-path reset.

## Complete Regression Evidence

- Django system check: no issues.
- Missing-migration guard: no changes detected.
- Full mixed-family suite: all 24 modules passed.
- Existing serial purchase suite: 29/29 per serial tenant.
- Serial system harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: all checks passed for both tenants.

## Exit Gate

**PASS**

- Domestic pre-tax purchases reconcile stock, FIFO, and accounting.
- Credit purchases affect AP while cash purchases affect only Cash/Bank.
- Duplicate requests cannot create duplicate documents or postings.
- Safe edits replay later FIFO costs and unsafe edits roll back.
- Historical numbers and revision evidence are retained.
- Quantity tenants never enter serial numbers.
- Existing serial purchase behavior remains unchanged.
- Phase 12 quantity-sales work may begin.
