# Phase 8 — Warehouse Foundation Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose project  
**Live/production data changed:** no

## Delivered

- Raised the quantity schema requirement to version 4.
- Added normalized warehouse code/name identity, address, active/inactive
  state, default state, timestamps, and user attribution.
- Enforced tenant-unique normalized warehouse codes and names.
- Enforced at most one active default warehouse with a partial unique index.
- Serialized default selection using a transaction advisory lock.
- Made the first active warehouse the default when no default exists.
- Added atomic default switching and default replacement when the current
  default is deactivated or deleted.
- Added active-only and historical warehouse lookup plus explicit default
  resolution.
- Added a warehouse reference registry. Referenced warehouses may be
  deactivated but cannot be hard-deleted.
- Added four explicit Django permissions:
  - `view_warehouse`;
  - `create_warehouse`;
  - `update_warehouse`;
  - `delete_warehouse`.
- Added central route permission mapping and duplicate view-level enforcement.
- Added the quantity-only `/warehouses/quantity/` JSON API.
- Added ordered cumulative bootstrap artifacts so fresh schemas receive the
  item and warehouse phases while existing schemas receive only the current
  idempotent upgrade.

Transfers, stock balances, movements, FIFO layers, and availability remain in
their assigned later phases.

## Upgrade Evidence

The preserved mixed-family environment contained:

- two serial tenants at serial schema version 6;
- one quantity tenant at quantity schema version 3.

Production startup:

- applied public permission migration
  `authentication.0022_add_quantity_warehouse_permissions`;
- applied serial hardening/indexes only to serial tenants;
- applied `quantity_warehouse_foundation.sql` only to the quantity tenant;
- upgraded that tenant to quantity version 4;
- passed family/version/table/function/sequence verification;
- started Gunicorn successfully.

The public migration was reversed to `authentication.0021`, reapplied to
`0022`, and followed by a clean 38/38 focused warehouse run.

## Focused Evidence

The Phase 8 suite passed 38/38 checks across two fresh quantity tenants:

- version/fingerprint and exact public permissions;
- first/default and second/non-default creation;
- default lookup and switching;
- normalized duplicate code/name rejection;
- blank code/name and inactive-default rejection;
- rename, recode, and address update;
- direct database rejection of a second active default;
- default deactivation and automatic replacement;
- active-only and historical lookup;
- referenced deletion denial with allowed deactivation;
- no-default state when no active warehouses exist;
- unreferenced deletion and deleted-default replacement;
- same-name/code cross-tenant isolation;
- idempotent hardening;
- HTTP list/default/create/update/delete behavior;
- HTTP referenced-delete denial;
- viewer access and unauthorized mutation denial;
- serial-family route denial;
- continued gating of unfinished quantity routes;
- request search-path reset.

## Complete Regression Evidence

- Django checks: no issues.
- Missing-migration guard: no changes detected.
- Phase 5 quantity foundation: 28/28.
- Phase 6 quantity accounting: 39/39.
- Phase 7 item/variant/unit master: 60/60.
- Full mixed-family suite: all 21 modules passed.
- Serial item suite: 10/10 per serial tenant.
- Serial system harness: 111/111 per tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep serial transaction lifecycle: all checks passed for both tenants.

## Exit Gate

**PASS**

- Multiple warehouse identities are deterministic and tenant-isolated.
- Default selection cannot produce two active defaults.
- Deactivation and default replacement preserve history.
- Referenced warehouse deletion is prohibited.
- Lookup and mutation contracts enforce explicit permissions.
- Serial tenants cannot execute quantity warehouse SQL.
- Existing serial workflows remain unchanged.
- Phase 9 may begin.
