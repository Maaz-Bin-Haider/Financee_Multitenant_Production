# Phase 3 — Public Company Metadata Migration Results

**Completed:** 2026-07-25  
**Environment:** isolated Docker Compose projects; production compose/image path  
**Production/live data changed:** no

## Scope Delivered

- Added `Company.inventory_mode` with the supported values `serial` and
  `quantity`.
- Added migration `tenancy.0005_company_inventory_mode`.
- Backfilled existing and bootstrap companies to `serial` through the migration
  default without changing schema names.
- Added database constraint `tenancy_company_valid_inventory_mode`.
- Enforced inventory-mode immutability in model validation and `save()`.
- Kept quantity-company creation blocked until the quantity template and
  provisioning registry are delivered in Phase 5.
- Exposed inventory mode in company administration, with the field read-only
  after creation.
- Added `tests/suite/test_company_metadata.py` and included it in the complete
  suite.
- Updated the existing feature-flag admin test payload to explicitly preserve
  the serial inventory mode.

Base currency and tax-environment setup remain Phase 4 work, as assigned by the
approved implementation plan and requirements traceability. They were not
silently combined with this migration.

## Upgrade-Database Evidence

The Phase 1 isolated database and its two existing serial tenants were retained
and upgraded:

- `tenancy.0005_company_inventory_mode` applied successfully.
- Both existing companies remained `serial`.
- Both schema names remained unchanged.
- The database check constraint accepted only `serial` or `quantity`.
- `manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes detected.
- Company metadata suite: 14/14 checks passed.
- Complete suite: all 16 modules passed.
- System harness: 111/111 checks per tenant, 222/222 total.
- Standalone HTTP harness: 66 endpoints, zero problems.
- Deep transaction lifecycle: all checks passed for both tenants.

The first complete-suite run exposed one legitimate test-fixture regression:
the feature-flag `CompanyAdminForm` fixture omitted the new required field. The
fixture now submits the existing company's `serial` mode; the rerun passed
77/77 feature-flag checks.

## Clean-Database Evidence

A second isolated Compose project used newly created PostgreSQL, Redis, static,
and media volumes:

- All public migrations through `tenancy.0005` applied successfully from an
  empty database.
- Bootstrap `tenant_company_1` and runtime-provisioned `tenant_company_2`
  were both serial-based.
- Tenant hardening and required indexes applied successfully.
- `manage.py check`: no issues.
- Missing-migration guard: no changes detected.
- Company metadata suite: 14/14 checks passed.
- Complete suite: all 16 modules passed after adding the standard disposable CI
  superuser required by the web/admin test modules.
- System harness: 111/111 checks per tenant, 222/222 total.

The initial clean-suite attempt correctly reported that five admin/web modules
could not run without a superuser. No application assertion failed. After the
documented CI prerequisite was created, every module passed.

## Migration Compatibility Rehearsal

On the disposable clean database:

1. Rolled `tenancy` back from `0005` to `0004` successfully.
2. Reapplied `0005` successfully.
3. Reran the 14 company-metadata checks successfully.

This confirms forward application and rollback/reapplication at the Phase 3
migration boundary. Application rollback while the database remains at `0005`
is compatible because the migration is additive and existing companies retain
the serial default.

## Exit Gate

**PASS**

- Existing serial behavior and serial provisioning are unchanged.
- Existing company types are safely backfilled.
- Inventory mode cannot be changed after creation/provisioning.
- Quantity provisioning remains unavailable until its schema family exists.
- Upgrade, clean-install, rollback/reapply, admin/model, and serial regression
  evidence are green.

Phase 4 may begin.
