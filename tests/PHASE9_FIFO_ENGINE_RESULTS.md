# Phase 9 — Stock Movement and FIFO Engine Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement to version 5.
- Added an immutable stock movement ledger with business date, deterministic
  effective sequence, source identity, document lineage, direction, quantity,
  exact base cost, user attribution, and reversal linkage.
- Added atomic stock balances per variant and warehouse.
- Added FIFO receipt layers with original and remaining quantities.
- Added durable FIFO allocations joining each outbound movement to its exact
  inbound source layers and costs.
- Added current and historical availability per SKU and warehouse.
- Added controlled posting and reversal functions with idempotent source
  handling and transaction-local write guards.
- Added tenant/scope advisory locking and canonical warehouse/variant lock
  ordering for future multi-scope documents.
- Added deterministic replay ordered by business date and effective sequence.
- Added whole-history negative-stock validation before a replay mutates any
  projection.
- Added reconciliation across movement quantity, balance quantity, FIFO
  remainder, and outbound allocation quantity, with FIFO value calculated from
  the remaining cost layers.
- Registered stock references so transacted variants and warehouses retain
  their historical identity.
- Kept all quantity invoice UI and unfinished business routes gated.

## Upgrade Evidence

The preserved mixed-family Docker environment started with two serial tenants
and one quantity tenant at schema version 4. Production startup applied the
serial hardening path only to serial schemas and
`quantity_fifo_engine.sql` only to the quantity schema. The quantity tenant
reached version 5, passed family fingerprint verification, and Gunicorn
started successfully. Fresh quantity schemas reached the same state through
the cumulative bootstrap path.

## Focused Evidence

`tests/suite/test_quantity_fifo.py` passed 38/38 checks covering:

- single, partial, full, and multiple FIFO cost layers;
- exact weighted outbound cost and durable inbound source lineage;
- current and historical availability;
- the same SKU held independently in multiple warehouses;
- deterministic cost reflow after a backdated inbound layer;
- rollback of a backdated movement that would create historical negative stock;
- whole-unit and three-decimal measurement precision;
- idempotent sources and changed-payload duplicate denial;
- database guards against direct movement insertion, update, and deletion;
- catalogue and warehouse reference protection;
- outbound reversal at original FIFO value, one-reversal-only enforcement, and
  reversal-of-reversal denial;
- 20 simultaneous one-unit sales against 10 available units, producing exactly
  10 posts, 10 denials, and zero negative stock;
- reversed multi-scope requests completing under canonical locks without a
  deadlock;
- movement/balance/FIFO/allocation reconciliation;
- same identifiers remaining isolated between two quantity tenants; and
- PostgreSQL search-path reset after tenant operations.

## Complete Regression Evidence

- Django system check: no issues.
- Missing-migration guard: no changes detected.
- Full mixed-family suite: all 22 modules passed.
- Serial item suite: 10/10 per serial tenant.
- Serial system harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: 2,702/2,702 per tenant; 5,404/5,404 total.

## Exit Gate

**PASS**

- FIFO results are deterministic, concurrent-safe, and reconcilable.
- Backdating cannot introduce negative stock at any historical point.
- Source lineage and costs survive replay.
- Tenant and warehouse boundaries remain isolated.
- Existing serial workflows remain unchanged.
- No invoice UI was integrated before the inventory core passed.
- Phase 10 opening-stock work may begin.
