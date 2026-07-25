# Phase 10 — Quantity Opening Stock Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement to version 6.
- Added immutable opening-stock document and line tables.
- Added tenant-local `OPN-000001` document numbering.
- Added SKU, warehouse, quantity, six-decimal unit cost, line value,
  description, creator, journal, movement, status, and reversal lineage.
- Posted every opening line through the Phase 9 stock/FIFO engine.
- Posted each document atomically as Debit Inventory / Credit Opening Balance.
- Added list and detailed document functions with SKU, unit, warehouse,
  quantity, cost, value, journal, movement, and status information.
- Added guarded reversal using linked movement and journal reversals.
- Prohibited reversal after any quantity from an original opening FIFO layer
  has been consumed.
- Added Opening Balance and Owner's Capital status.
- Added serialized Opening Balance reclassification in either debit/credit
  direction and safe no-op behavior when the account is already zero.
- Enabled the existing opening-stock route for quantity tenants with a
  quantity-specific, no-serial screen using the current application theme.
- Preserved the existing serial opening-stock page, SQL, and behavior.

## Upgrade Evidence

The preserved isolated environment contained two serial tenants at serial
version 6 and one quantity tenant at quantity version 5. Production startup
applied serial hardening only to the serial schemas and
`quantity_opening_stock.sql` only to the quantity schema. The quantity tenant
reached version 6, passed schema verification, and Gunicorn started
successfully. Fresh quantity schemas received all cumulative Phase 5–10
artifacts and produced the same verified fingerprint.

## Focused Evidence

`tests/suite/test_quantity_opening_stock.py` passed 37/37 checks covering:

- fresh provisioning, version, fingerprint, and document prefix;
- a whole Piece line and three-decimal Kilogram line in separate warehouses;
- exact stock balances, movements, FIFO layers, quantity, and FIFO value;
- exact Inventory debit, Opening Balance credit, and balanced journal totals;
- document list and detailed SKU/warehouse/unit lineage;
- duplicate SKU/warehouse rollback;
- fractional Piece, fourth-decimal measurement, negative-cost, and empty
  document rejection without partial stock or journals;
- direct document and line mutation denial;
- untouched-layer movement and journal reversal;
- double-reversal denial;
- consumed-layer reversal denial;
- exact Opening Balance to Owner's Capital reclassification and repeat no-op;
- independent document numbering and stock between quantity tenants;
- idempotent rollout;
- quantity page, create, list, detail, and reversal HTTP behavior;
- serial-validation endpoint denial for a quantity tenant; and
- tenant search-path reset.

## Complete Regression Evidence

- Django system check: no issues.
- Missing-migration guard: no changes detected.
- Full mixed-family suite: all 23 modules passed.
- Serial opening suite: 20/20 per serial tenant.
- Serial system harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: all checks passed for both tenants.

## Exit Gate

**PASS**

- Opening quantity and FIFO value agree.
- Inventory and Opening Balance journal amounts are exact and balanced.
- Reversal cannot corrupt consumed FIFO history.
- Reclassification clears Opening Balance and preserves double entry.
- Quantity tenants use a no-serial workflow.
- Existing serial opening-stock and opening-cash workflows remain unchanged.
- Phase 11 quantity-purchase work may begin.
