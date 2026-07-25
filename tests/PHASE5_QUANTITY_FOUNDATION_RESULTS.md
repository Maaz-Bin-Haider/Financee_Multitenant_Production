# Phase 5 — Quantity Schema Foundation Results

**Completed:** 2026-07-25  
**Environment:** isolated production-path Docker Compose projects  
**Live/production data changed:** no

## Delivered

- Added a central schema-family registry defining, per family:
  - template;
  - production hardening;
  - required version;
  - metadata table;
  - required object fingerprint;
  - controlled rollout files;
  - runtime capability gate.
- Added the independent quantity SQL artifacts:
  - `tenancy/sql/quantity_tenant_template.sql`;
  - `tenancy/sql/quantity_production_hardening.sql`.
- Added quantity schema version 1 metadata:
  - family;
  - version;
  - base-currency snapshot;
  - creation and application timestamps.
- Added deterministic foundation objects:
  - singleton `tenant_schema_metadata`;
  - idempotent `quantity_seed_registry`;
  - ten independently seeded document counters;
  - `quantity_foundation_id_seq`;
  - family assertion and fingerprint functions.
- Added family-aware transactional provisioning with required-object
  verification before commit.
- Added public company provisioning states: pending, provisioning, ready, and
  failed, with a sanitized failure code.
- Added controlled `retry_tenant_provisioning` for pending/failed builds.
- Added `--inventory-mode` to `provision_tenant`.
- Made `apply_sql_all_tenants`:
  - family-filtered;
  - controlled-file aware;
  - resistant to file/family mismatch;
  - post-upgrade verifying;
  - explicit about family and resulting version.
- Updated Docker startup to apply serial hardening/indexes only to serial
  companies and quantity hardening only to quantity companies.
- Added family/version/base-currency/fingerprint verification before request
  activation.
- Kept quantity business routes runtime-gated until their required accounting,
  master-data, and transaction phases are implemented. An authenticated
  quantity user receives a controlled 403 instead of reaching serial SQL.
- Made legacy serial test discovery explicitly family-aware.

Phase 5 does not implement quantity accounting, products, warehouses, FIFO,
invoices, or reports. Those remain assigned to Phases 6 onward.

## Upgrade-Database Evidence

The preserved isolated database contained two established serial companies:

- Public migration `tenancy.0007_company_provisioning_state` applied
  successfully.
- Both existing companies were backfilled to ready.
- Startup applied serial hardening and indexes to exactly the two serial
  schemas.
- Startup found no quantity schemas and made no quantity SQL attempt against a
  serial schema.
- Django checks and missing-migration guard passed.
- Quantity foundation: 28/28 final checks passed.
- Complete suite: all 18 modules passed.
- System harness: 111/111 per serial tenant; 222/222 total.
- Standalone HTTP harness: 66 endpoints; zero problems.
- Deep lifecycle: all checks passed for both serial tenants.

## Clean Mixed-Family Evidence

A fresh isolated database was created and validated with:

- `tenant_company_1`: bootstrap serial tenant.
- `tenant_company_2`: freshly provisioned serial tenant.
- `tenant_company_3`: freshly provisioned USD/tax quantity foundation tenant.

On restart:

- Serial hardening targeted only `tenant_company_1` and `tenant_company_2`.
- Serial indexes targeted only `tenant_company_1` and `tenant_company_2`.
- Quantity hardening targeted only `tenant_company_3`.
- Every rollout printed successful post-upgrade family/version verification.

The focused suite additionally created two temporary quantity companies:

- Both reached ready.
- Both schemas had identical table/sequence/function fingerprints.
- Neither schema contained serial inventory tables.
- Hardening reran twice without duplicate seeds or document counters.
- Public-family/physical-family mismatch was denied.
- Base-currency metadata mismatch was denied.
- Quantity SQL directly executed against a serial schema rejected itself before
  mutation.
- A forced template failure left an inactive failed company with the sanitized
  code `schema_build_failed` and no physical schema.
- Controlled retry created and verified the schema; retrying a ready company
  was rejected.
- Search path returned to public after operations.
- A quantity user received controlled HTTP 403 while runtime capabilities
  remain gated.

All 18 suite modules and all serial standalone/deep harnesses passed in the
mixed-family environment.

## Test-Driven Corrections

The phase gate exposed and corrected:

1. Provisioning lifecycle fields were initially included as editable
   `ModelForm` inputs. They are now excluded from submitted fields and shown
   read-only in admin.
2. Legacy attachment, company-setup, SQL-system, CI bootstrap, suite discovery,
   and deep-lifecycle harnesses assumed every physical schema was serial. They
   now explicitly select the serial family; dedicated quantity harnesses own
   quantity validation.
3. Running two production-worker test stacks simultaneously caused one local
   exit-137 memory kill. The unused stack was stopped and the same tests passed
   with one stack active; there was no failed application assertion.

## Migration Compatibility

On the disposable mixed-family database:

1. Reversed public migration `0007` to `0006`.
2. Reapplied `0007`.
3. Reran quantity foundation checks.
4. Reran 222 serial accounting checks.

The quantity SQL template/hardening remains independent of the Django public
migration and its persistent quantity schema survived the public metadata
rollback/reapplication.

## Exit Gate

**PASS**

- Fresh and repeated quantity provisioning is deterministic.
- Quantity and serial artifacts have independent registry ownership.
- Wrong-family rollout is rejected by command dispatch and quantity SQL.
- Family, version, base currency, and fingerprint mismatches deny activation.
- Failed provisioning cannot appear ready or active and supports controlled
  retry.
- Existing serial workflows and accounting remain unchanged.
- Phase 6 may begin.
