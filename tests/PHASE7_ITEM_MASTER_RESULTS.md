# Phase 7 — Product, Variant, SKU, and Unit Master Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement to version 3.
- Seeded exactly six controlled units:
  - Piece (`PCS`) and Box (`BOX`) with whole-number quantities;
  - Kilogram (`KG`), Gram (`GM`), Litre (`LTR`), and Metre (`MTR`) with up to
    three decimal places.
- Added normalized parent products with name, category, description,
  active/inactive state, timestamps, and user attribution.
- Added sellable variants requiring brand, model, color, storage, RAM, region,
  and condition.
- Added tenant-unique normalized SKU and normalized combination constraints.
  Unit is part of the combination, so Piece and Box stock remain distinct
  SKUs without conversion.
- Added deterministic SKU suggestions with transaction-scoped advisory locking
  and collision suffixes.
- Allowed manual SKU entry and changes before transactions exist.
- Added a transaction-reference registry and database trigger locking SKU and
  unit after the first business reference.
- Added exact numeric quantity validation. A fourth decimal is rejected rather
  than silently rounded.
- Added product and variant create/update functions, active/inactive catalogue,
  search/autocomplete, unit lookup, SKU suggestion, and shared quantity
  validation functions.
- Added a permission-protected quantity JSON API under `/items/quantity/`.
- Kept every other unfinished quantity route behind the runtime gate.
- Changed fresh quantity provisioning to compose the stable base template with
  the family's current hardening artifact, keeping one authoritative upgrade
  body for fresh and existing tenants.

Warehouses, stock balances/movements, FIFO, invoices, and reports remain in
their assigned later phases.

## Upgrade and Idempotency Evidence

The preserved mixed-family database contained two serial schemas and one
quantity version-2 schema. Production startup:

- applied serial hardening/indexes only to serial tenants;
- applied `quantity_item_master.sql` only to the quantity tenant;
- upgraded it to quantity schema version 3;
- passed post-upgrade family/version/object verification;
- started Gunicorn successfully.

The artifact was rerun against all quantity schemas. Units remained exactly
six and the foundation/accounting/item seed registry remained exactly three
distinct rows.

An intermediate prerelease rerun exposed a trigger/type-alter ordering issue;
the rollout now drops the precision trigger before changing the prototype
column type and recreates it transactionally. Another focused test exposed
that generated columns are unavailable during `BEFORE UPDATE`; the
transaction lock now compares the normalized raw SKU expression directly.

## Focused Evidence

The final Phase 7 suite passed 60/60 checks across two fresh quantity tenants:

- exact unit seed and idempotency;
- normalized product identity and duplicate rejection;
- every required variant dimension;
- automatic suggestion, manual SKU, and deterministic collision suffix;
- case-insensitive duplicate SKU and normalized-combination rejection;
- each missing/blank dimension;
- Piece/Box whole-number rules;
- valid and invalid boundaries for all six units;
- exact three-decimal acceptance and fourth-decimal rejection;
- SKU/unit editing before a transaction;
- SKU/unit lock after a transaction;
- permitted non-identity edits and active/inactive behavior;
- catalogue lookup and inactive-history retention;
- cross-tenant same-SKU isolation;
- quantity unit, catalogue, suggestion, product, and variant HTTP behavior;
- read-only access and mutation denial;
- continued gating of unfinished quantity routes;
- request search-path reset.

## Complete Regression Evidence

- Django checks: no issues.
- Missing-migration guard: no changes detected.
- Phase 5 quantity foundation: 28/28.
- Phase 6 quantity accounting: 39/39.
- Full mixed-family suite: all 20 modules passed.
- Serial item suite: 10/10 per serial tenant.
- Serial system harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: all checks passed for both tenants.

## Exit Gate

**PASS**

- Every sellable quantity variant has one unambiguous normalized SKU.
- All seven approved dimensions are represented and required.
- Units and precision are database-enforced and HTTP-enforced.
- SKU/unit history cannot be rewritten after transaction reference.
- Product/variant lookup and active/inactive lifecycle are operational.
- Tenant and permission isolation hold.
- Existing serial item and accounting behavior remains unchanged.
- Phase 8 may begin.
