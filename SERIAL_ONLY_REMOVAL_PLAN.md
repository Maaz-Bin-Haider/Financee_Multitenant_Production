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
| 0 | Production discovery, baseline, and approved test-tenant remediation | **PASS** | Production and restored strict audits, fresh remote backup, cleanup, preflight, and health PASS | **PASS** |
| 1 | Close quantity-company creation | **PASS** | Local gates and protected exact-SHA workflow `33636045130` PASS; production deployed without rollback | **PASS** |
| 2 | Remove quantity runtime and replace CI coverage | **PASS** | Local gates and all 12 jobs in protected exact-SHA workflow `33728502631` PASS; production controller PASS | **PASS** |
| 3 | Remove quantity database metadata and approved orphan schemas | Not started | Not run | Required — Phase 4 blocked |
| 4 | Source, documentation, test, and migration hygiene | Not started | Not run | Required — final acceptance |

## Phase 0 — Production Discovery and Approved Test-Tenant Remediation

The discovery command changes no company, tenant schema, transaction,
deployment setting, or customer-facing behavior; its database transaction is
forced to `READ ONLY` by PostgreSQL. The separately approved remediation
retired only the individually classified Company 2 test schema after backup.

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
- [x] Pass the command against an isolated restored production backup.
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

- [x] The audited image/source Git SHA is known.
- [x] Company count matches the admin's expected company count.
- [x] Active/inactive counts are understood.
- [x] Every Company row is serial, or every exception is explicitly documented.
- [x] Every registered schema exists physically.
- [x] No orphan tenant schema exists, or every orphan is documented.
- [x] No schema is classified quantity, mixed, or unknown, or every exception
  is documented.
- [x] Every serial schema reports version 6.
- [x] Structural fingerprints are consistent where expected.
- [x] Every scanned serial journal is balanced.
- [x] Current encrypted backup status passes.
- [x] A current backup restores successfully in isolation.
- [x] Web, PostgreSQL, Redis, and Nginx remain healthy after the read-only scan.
- [x] The owner explicitly decides whether Phase 1 may begin.

**Owner Phase 0 result:** `PASS`

**Audited production SHA:** audit image `8f407dea9e488eab8980b48309c064a00db714cd`; recovery workflow `cb8792c21ba252d79e91c0ee3310827ff1884841`

**Verification date/time:** `2026-09-02T12:45:08Z`

**Verifier:** system owner and protected production workflow

**Evidence reference:** workflow runs `33535608469` and `33631445649`; `tests/PHASE0_SERIAL_ONLY_DISCOVERY_RESULTS.md`

**Exceptions discovered:** approved quantity test tenant retired; no remaining production exception

Phase 1 was explicitly started by the owner on 2026-09-02.

## Later Phases

### Phase 1 — Creation Freeze

Remove quantity selection from admin and supported provisioning commands, force
new companies to serial, and add the serial-only database constraint only after
Phase 0 proves the production registry contains no conflicting rows.

#### Implementation checklist

- [x] Hide inventory mode from company add/change forms, lists, and filters.
- [x] Expose serial as the only model choice and reject non-serial model saves.
- [x] Remove `--inventory-mode` from `provision_tenant` and assign serial explicitly.
- [x] Reject non-serial low-level and retry provisioning paths.
- [x] Add a fail-closed migration precondition before replacing the database
  check constraint with an exact serial-only constraint.
- [x] Replace active quantity-company CI creation with a creation-freeze gate.
- [x] Convert mandatory mixed-family isolation and ARM64 creation smokes to
  serial-only operation without deleting quantity runtime source.
- [x] Preserve encrypted restore and previous-image compatibility rehearsal on
  the forward serial-only database.
- [x] Pass local static, Django, migration, live PostgreSQL, serial regression,
  four-serial isolation, recovery, staging, and ARM64 gates.
- [x] Review the complete diff and verify no serial business runtime behavior
  or serial tenant SQL was changed.
- [x] Push exact commit `102e55e857bbffa8bd4318e6afaec42e048c8e67`
  and pass protected CI/CD workflow `33636045130`.
- [x] Owner manually verifies production and records Phase 1 PASS.

**Owner Phase 1 result:** `PASS`

**Deployed production SHA:** `102e55e857bbffa8bd4318e6afaec42e048c8e67`

**Verification date:** `2026-09-02`

**Verifier:** system owner and protected production workflow

**Evidence reference:** workflow run `33636045130` and
`tests/PHASE1_SERIAL_ONLY_CREATION_RESULTS.md`

Phase 2 was explicitly started by the owner on 2026-09-02.

### Phase 2 — Runtime Removal

Remove quantity dispatch, routes, views, templates, static assets, SQL rollout,
and entrypoint work. Replace quantity and mixed-family CI jobs with four-serial-
tenant isolation, lifecycle, recovery, security, and ARM64 gates.

#### Implementation checklist

- [x] Remove quantity request dispatch while retaining the serial payload guard.
- [x] Remove quantity routes, HTTP adapters, templates, and static assets.
- [x] Remove quantity dashboard, attachment, feature, and security branches.
- [x] Remove quantity SQL maintenance from container startup.
- [x] Restrict supported tenant SQL rollout and release preflight to serial.
- [x] Make the retired schema descriptor fail closed with no enabled paths.
- [x] Remove dormant quantity lifecycle code from active isolation coverage.
- [x] Add mandatory static and live-stack Phase 2 removal gates to CI.
- [x] Pass the focused static contract and isolated live-stack route gate.
- [x] Remove only allowlisted retired files from the persistent static volume;
  verify rollback repopulates old assets and serial cached files survive.
- [x] Prove the 12 serial document implementations, 212 serial UI source files,
  and 17 serial SQL/bootstrap files match deployed Phase 1.
- [x] Pass Django/migration checks and complete serial regression.
- [x] Pass four-serial isolation, full active suite, ARM64, recovery, and staging.
- [x] Review and commit the exact Phase 2 diff locally.
- [x] Obtain explicit owner authorization before pushing to GitHub `main`.
- [x] Pass protected exact-SHA CI/CD and production deployment.
- [x] Owner manually verifies production and records Phase 2 PASS.

**Evidence:** workflow `33728502631` and
`tests/PHASE2_SERIAL_ONLY_RUNTIME_RESULTS.md`.

**Owner Phase 2 result:** `PASS` — owner reported: “the complete CI CD passed
and the actual deployed site is working fine”.

**Deployed production SHA:** `e44737f1f740fa936e853a3d6bbbd068a1b6d89d`

**Production controller PASS:** `2026-09-03T07:39:52Z`

**Owner verification date:** `2026-09-03`

**Verifier:** system owner and protected production workflow. The owner's
overall manual acceptance is recorded as supplied; individual transaction
checklist actions were not separately reported.

Phase 2 is complete. Phase 3 is eligible but has not started and requires a
separate explicit owner instruction. This sign-off authorizes no database
cleanup or schema deletion.

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
| 2026-09-01 | Owner reported the online production system working correctly after retirement | Manual online verification PASS; isolated post-cleanup restore remains required |
| 2026-09-01 | First post-cleanup recovery run `33536964690` stopped at capacity preflight | Docker free space was below the conservative 3 GiB threshold; no production audit, backup, container, volume, restore, or database command ran |
| 2026-09-01 | Recovery run `33537295401` restored and verified the post-cleanup estate | Backup `db-backup-20260901T172204Z`, restore RTO 52s, strict restored audit ready; exact disposable stack removed; final production recheck used stale restore env and failed authentication without changing production |
| 2026-09-02 | Final recovery run `33631445649` | Post-cleanup backup `db-backup-20260902T124354Z`; isolated restore and strict audit PASS; exact disposable cleanup PASS; production strict audit, serial preflight, and HTTP health PASS |
| 2026-09-02 | Phase 0 gate review | Automated and owner production verification PASS; Phase 1 eligible but not started pending explicit instruction |
| 2026-09-02 | Owner explicitly instructed “Start Phase 1” | Phase 1 creation freeze started; production unchanged pending all gates and protected approval |
| 2026-09-02 | Phase 1 local candidate validation | Static/release contracts 90/90; serial 51/51; creation freeze 15/15; isolation 16/16; full suite, ARM64, recovery, and staging PASS; production unchanged |
| 2026-09-02 | Phase 1 protected workflow `33636045130` deployed exact commit `102e55e` | All required CI/CD and post-deployment checks PASS; ARM64 production deployment completed without rollback |
| 2026-09-02 | Owner manually verified the live site after Phase 1 deployment | Phase 1 PASS; Phase 2 remains unstarted pending explicit instruction |
| 2026-09-02 | Owner explicitly instructed “start phase 2” | Phase 2 runtime removal started; production unchanged pending all local and protected gates |
| 2026-09-02 | Phase 2 focused runtime-removal gate | Static contracts and isolated live PostgreSQL/Django route gate PASS; retired paths return 404; fresh serial tenant and serial pages remain healthy |
| 2026-09-03 | Phase 2 resumed after usage interruption | Lost completion result was not assumed; full active suite rerun and captured, 21/21 modules PASS |
| 2026-09-03 | Local test harness safety correction | Default-project volume cleanup blocked by safety review; unique disposable project/private environment implemented; full and ARM64 runs PASS |
| 2026-09-03 | Production-Python preservation contracts | Version-specific AST formatting false failure replaced with independent exact-source hashes; 114/114 release/static contracts and 71/71 backup contracts PASS under Python 3.12 |
| 2026-09-03 | Phase 2 recovery and static rollback rehearsal | Synthetic encrypted restore RTO 43s; deployed Phase 1 image compatibility PASS; re-upgrade removes retired assets and preserves serial cache; disposable stacks removed |
| 2026-09-03 | Phase 2 local staging and diff review | Serial 51/51, creation 15/15, runtime removal 13/13, isolation 16/16, security 5/5, continuity and capacity preflight PASS; no schema/migration/serial SQL changes; push and production gates pending |
| 2026-09-03 | Owner explicitly authorized pushing Phase 2 commit `e44737f`; exact commit pushed to `main` | CI/CD workflow `33728502631` started |
| 2026-09-03 | Phase 2 protected exact-SHA workflow verified | All 12 jobs succeeded, including ARM64, full regression, recovery, staging approval, publication, and EC2 deployment; production controller PASS at 07:39:52 UTC after continuity/operational gates |
| 2026-09-03 | Owner reported the actual deployed site working fine | Phase 2 manual production PASS; Phase 2 complete; Phase 3 not started pending explicit instruction |
