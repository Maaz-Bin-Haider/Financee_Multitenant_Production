# Serial-Only Consolidation Plan

**Started:** 2026-09-01

**Production:** AWS EC2 `t4g.medium`, ARM64, `ap-south-1`

**Safety owner:** The system owner manually verifies the real production system
after every phase.

**Progress rule:** The next phase must not start until the owner records an
explicit production PASS for the current phase.

## Non-Negotiable Safety Contract

- No fact about production company rows or physical schemas is assumed.
- Serial tenant business data and serial schema version 6 are never converted.
- No tenant schema is dropped automatically.
- Applied Django migrations are not deleted during the operational phases.
- Every production deployment uses the protected exact-SHA ARM64 workflow.
- Continuity evidence is captured before and after any behavior-changing
  deployment.
- A verified backup and isolated restore are required before destructive
  database cleanup.
- Any failed automated or manual gate stops the plan.

## Phase Gates

| Phase | Scope | Implementation | Automated evidence | Manual production verification |
|---|---|---|---|---|
| 0 | Production discovery, baseline, and approved test-tenant remediation | Complete | Production strict audit and fresh remote backup PASS; isolated restore pending | **Required — Phase 1 blocked** |
| 1 | Close quantity-company creation | Not started | Not run | Required — Phase 2 blocked |
| 2 | Remove quantity runtime and replace CI coverage | Not started | Not run | Required — Phase 3 blocked |
| 3 | Remove quantity database metadata and approved orphan schemas | Not started | Not run | Required — Phase 4 blocked |
| 4 | Source, documentation, test, and migration hygiene | Not started | Not run | Required — final acceptance |

## Phase 0 — Read-Only Production Discovery

Phase 0 changes no company, tenant schema, transaction, deployment setting, or
customer-facing behavior. It adds an operator-only audit command whose database
transaction is forced to `READ ONLY` by PostgreSQL.

### Implementation checklist

- [x] Roll back the prematurely started Phase 1 edits.
- [x] Preserve the original company admin and serial/quantity behavior.
- [x] Add a read-only Phase 0 discovery command.
- [x] Inventory active and inactive Company rows without exposing company names.
- [x] Discover physical `tenant_company_<id>` schemas independently of the
  public Company registry.
- [x] Classify schemas as serial, quantity, mixed, or unknown.
- [x] Report non-serial Company rows, orphan schemas, and missing schemas.
- [x] Record schema version, object counts, and privacy-safe structural hashes.
- [x] Fail readiness when serial schema structures drift from one another.
- [x] Report Company rows whose schema name is blank.
- [x] Add an optional bounded continuity scan for serial journals and inventory.
- [x] Add fail-closed strict mode.
- [x] Add a statement timeout to prevent sustained production load.
- [x] Add Phase 0 contracts to mandatory CI checks and the serial runtime gate.
- [x] Canonicalize physical schema names before cross-tenant structural hash
  comparison.
- [x] Detect and separately report the documented bootstrap-only
  `item_history_view` debug artifact without deleting or replicating it.
- [x] Add privacy-safe component hashes to localize structural drift without
  exposing function bodies.
- [x] Require complete continuity evidence before reporting Phase 1 readiness.
- [x] Pass static safety contracts (18/18 locally).
- [x] Confirm the production image's disposable bootstrap schema passes strict
  Phase 0 discovery.
- [x] Confirm a newly provisioned serial schema exposes pre-existing,
  function-only bootstrap/template drift and that strict mode fails closed.
- [x] Pass Django checks and migration-drift checks in the ARM64 production
  image path.
- [ ] Pass the command against an isolated restored production backup.
- [x] Pass strict discovery with continuity against production after retiring
  the individually approved orphan quantity test schema.
- [x] Review the complete Phase 0 diff: only this plan, the read-only command,
  its contracts, and CI wiring changed; no serial runtime file changed.

### Required isolated-restore execution

Run inside the restored production web container:

```bash
python manage.py serial_only_phase0_audit \
  --include-continuity \
  --strict-serial
```

Save stdout as Phase 0 evidence. If the command exits non-zero, do not alter or
delete the reported objects. Review each reported company/schema individually.

### Mandatory manual production verification

The owner must run or supervise the same read-only command against production
and record:

- [ ] The audited image/source Git SHA is known.
- [ ] Company count matches the admin's expected company count.
- [ ] Active/inactive counts are understood.
- [ ] Every Company row is serial, or every exception is explicitly documented.
- [ ] Every registered schema exists physically.
- [ ] No orphan tenant schema exists, or every orphan is documented.
- [ ] No schema is classified quantity, mixed, or unknown, or every exception
  is documented.
- [ ] Every serial schema reports version 6.
- [ ] Structural fingerprints are consistent where expected.
- [ ] Every scanned serial journal is balanced.
- [ ] Current encrypted backup status passes.
- [ ] A current backup restores successfully in isolation.
- [ ] Web, PostgreSQL, Redis, and Nginx remain healthy after the read-only scan.
- [ ] The owner explicitly decides whether Phase 1 may begin.

**Owner Phase 0 result:** `PENDING`

**Audited production SHA:** `PENDING`

**Verification date/time:** `PENDING`

**Verifier:** `PENDING`

**Evidence reference:** `PENDING`

**Exceptions discovered:** `PENDING`

Phase 1 remains blocked until the owner changes the Phase 0 result to `PASS`
and explicitly instructs work to continue.

## Later Phases

### Phase 1 — Creation Freeze

Remove quantity selection from admin and supported provisioning commands, force
new companies to serial, and add the serial-only database constraint only after
Phase 0 proves the production registry contains no conflicting rows.

### Phase 2 — Runtime Removal

Remove quantity dispatch, routes, views, templates, static assets, SQL rollout,
and entrypoint work. Replace quantity and mixed-family CI jobs with four-serial-
tenant isolation, lifecycle, recovery, security, and ARM64 gates.

### Phase 3 — Database Cleanup

Remove quantity-era public fields/permissions using expand-and-contract
migrations. Archive and remove only individually approved quantity/orphan
schemas. Never issue a broad tenant-schema drop.

### Phase 4 — Repository Hygiene

Remove inactive quantity source, tests, and active documentation; update all
runbooks; then use Django's supported migration replacement process only after
every environment has reached the required migration leaf.

## Audit Trail

| Date | Event | Result |
|---|---|---|
| 2026-09-01 | Serial-only consolidation authorized with manual production verification after every phase | Started |
| 2026-09-01 | Phase 1 was started prematurely due to prompt ambiguity | Stopped before commit/deploy |
| 2026-09-01 | All Phase 1 code edits rolled back | Original behavior restored |
| 2026-09-01 | Phase 0 read-only discovery started | In progress |
| 2026-09-01 | Two-tenant gate exposed the documented bootstrap-only `item_history_view` debug artifact | Narrowly excluded from equivalence; still reported; no database change |
| 2026-09-01 | Two-tenant gate localized remaining drift to `get_serial_number_details` and `update_purchase_return` | Pre-existing bootstrap/template function-body difference; reported and blocked; no serial SQL replayed |
| 2026-09-01 | Final disposable production-path validation | ARM64/Linux image; Django check clean; no migration drift; serial 51/51; Phase 0 contracts 18/18; runtime report 5/5; Compose stack removed |
| 2026-09-01 | Complete Phase 0 diff reviewed | Five Phase 0/CI files only; no frontend, model, migration, tenant SQL, or serial runtime change |
| 2026-09-01 | Owner verified the public production site manually | Availability smoke PASS; Phase 0 discovery still blocked |
| 2026-09-01 | Owner classified Company 2 as test-only and deleted it through Django admin | Public Company row and cascading relations removed; physical `tenant_company_2` schema not removed by admin |
| 2026-09-01 | Exact orphan-retirement maintenance prepared | Read-only inspection first; quantity-family proof, encrypted backup, exact confirmation, and post-change serial gates required |
| 2026-09-01 | First read-only retirement inspection stopped before EC2 commands | Empty optional SSH arguments were not preserved; no Docker or database command ran |
| 2026-09-01 | Corrected read-only production inspection | Company 2 absent from registry; `tenant_company_2` proven orphaned quantity v22 (54 tables, 4,087,808 bytes); serial Company 1 v6 balanced and healthy |
| 2026-09-01 | Existing remote backup cadence verified | Private backup repository has daily encrypted two-asset releases through `db-backup-20260901T022916Z`; execution still requires a new operation-time release |
| 2026-09-01 | Backup-first orphan retirement run `33535608469` | Fresh remotely verified release `db-backup-20260901T170630Z`; exact `tenant_company_2` drop committed; strict serial audit, serial preflight, and HTTP health PASS |
| 2026-09-01 | Independent post-operation public check | Financee login redirect and complete sign-in form healthy; owner serial workflow verification still required |
