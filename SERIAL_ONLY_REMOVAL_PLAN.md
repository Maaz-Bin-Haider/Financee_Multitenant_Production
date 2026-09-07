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
| 3 | Remove quantity database metadata and approved orphan schemas | **PASS** | 3A workflow `33736055610`; 3B inventory/recovery; strengthened inspection `33879212477`; protected cleanup `33887331226` with `confirmed_committed` and final checks PASS | **PASS — owner confirmed the live site online and working after cleanup** |
| 4 | Source, documentation, test, and migration hygiene | **In progress — checkpoint 4.0 closed; 4A implementation complete and fully gated locally** | Protected read-only production audit `33896979203` PASS and reviewed. Every static and container-backed gate PASS, including the new `migration-replacement-gate`: fresh installs create no retired column, constraint or permission, and an original-leaves database upgrades as a no-op with its data intact. No push or deployment | Required after each 4A/4B release and at final acceptance |

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

Phase 2 is complete. The owner explicitly started Phase 3 on 2026-09-03.
The Phase 2 sign-off itself authorizes no database cleanup or schema deletion.

### Phase 3 — Database Cleanup

Remove quantity-era public fields/permissions using expand-and-contract
migrations. Archive and remove only individually approved quantity/orphan
schemas. Never issue a broad tenant-schema drop.

#### Discovery findings and staged release requirement

The deployed Phase 2 image still maps `Company.inventory_mode` as an ORM field.
Dropping its physical column now would break that image, including rollback.
The existing recovery contract explicitly says image rollback does not reverse
forward migrations. Therefore this phase requires a compatibility release
before a separate column-removal release, not a single destructive deployment.

`base_currency`, `tax_environment`, the currency catalogue, provisioning state,
subscriptions, memberships, and serial feature keys are shared with the serial
system. Preserve them and their existing validation/admin behavior. They are
not automatically classified as quantity-only because they originated during
the historical quantity project.

| Checkpoint | Work | Required exit gate |
|---|---|---|
| 3.0 — Inventory | Read-only production registry, column/dependency, permission/grant, stale-feature, physical-schema and continuity evidence | Protected inventory PASS, every exception reviewed; no cleanup authorized by the report |
| 3A — Compatibility | Remove runtime/ORM dependence on the redundant inventory-mode column while retaining the physical column, exact serial constraint, and a compatible database default; retain existing serial responses and shared setup | Old/new-image company creation, serial regression, ARM64, full suite, recovery and protected deployment PASS; owner manually verifies production |
| 3B — Controlled cleanup | Archive and remove only the reviewed quantity permission/grant and stale-feature records; separately contract the redundant column only after deployed 3A no longer needs it | Fresh production inventory and backup/isolated restore; exact dependency review; reversible metadata proof; rollback to deployed 3A; protected deployment; owner manual PASS |
| Any orphan schema | Classify individually if the new inventory finds one | Separate exact-target approval and backup/restore before any deletion; never infer authorization from the already-retired Company 2 |

Checkpoint 3B must not be bundled into the first 3A deployment. The actual 3A
SHA becomes the tested rollback target before a physical column is removed.
Any archive retention/removal decision remains separate from its creation.

#### Current implementation checklist — checkpoint 3.0 only

- [x] Verify Phase 2 deployed SHA and owner PASS before starting Phase 3.
- [x] Identify the 14 exact `auth.user` permission seeds in migrations 0022–0025.
- [x] Identify the seven exact retired feature keys; preserve all other keys.
- [x] Add a database-enforced read-only, repeatable-snapshot inventory with
  bounded statement/lock waits, no customer names or permission assignees.
- [x] Inspect physical schemas independently, including noncanonical
  tenant-prefixed schemas, inactive companies, missing schemas and orphans.
- [x] Inspect `inventory_mode` dependencies and report unexpected objects.
- [x] Prepare a protected manual workflow that streams audited source into
  the unchanged, exact-SHA ARM64 Phase 2 container without a checkout update,
  image pull, deployment, migration, restart, or container-file copy on EC2.
- [x] Finish local contracts, real PostgreSQL negative tests, exact deployed-
  image execution, wrapper failure tests, and diff review.
- [x] Obtain explicit approval to push the inventory-only commit (`[skip ci]`).
- [x] Obtain protected approval and run the read-only production inventory.
- [x] Review current production candidates and exceptions before implementing
  cleanup migrations.
- [x] Obtain owner manual site confirmation after the read-only inventory.
- [x] Deploy compatibility checkpoint 3A and obtain owner manual production PASS.
- [x] Complete approved cleanup checkpoint 3B and owner manual production PASS.

**Owner checkpoint 3.0 result:** `PASS` — the owner reported “the site is live
and fine” after the protected inventory. This records the supplied site check,
not independently observed transaction-by-transaction verification.

**Overall Phase 3 result:** `PASS` — compatibility deployed and accepted; the
exact protected cleanup committed with final checks PASS, followed by the
owner's required live-site PASS on 2026-09-04.

**Local and production evidence:** `tests/PHASE3_SERIAL_ONLY_METADATA_RESULTS.md`.

**Verified production snapshot:** workflow `33732596063` ran audit source
`330d22e8bb378545872983351b0d58c2cb731e2d` against unchanged deployed Phase 2
image `e44737f1f740fa936e853a3d6bbbd068a1b6d89d`. At 08:19 UTC on 2026-09-03,
all seven inventory checks passed: one active serial company and one registered
serial v6 schema, no orphan/quantity schemas, 14 exact historical quantity
permissions with 14 direct-user grant records and no group grants, and no stale
quantity feature keys. Grant-record counts do not identify distinct users.
The redundant `inventory_mode` column is non-nullable with no database default;
its reported dependencies identify only the expected serial constraint. The
strict continuity audit passed with a balanced journal. The ARM64 web container
and image remained unchanged and healthy; no cleanup was authorized or run.

**Current boundary:** the explicitly invoked reversible cleanup completed under
protected run `33887331226` from exact source `bc5cdce`, after strengthened
read-only inspection `33879212477`, fresh encrypted backup and isolated
apply/reversal proof. The result was `confirmed_committed`; final continuity and
health checks passed, and the owner accepted the live site afterward.
No automatic cleanup migration is introduced. Checkpoint 3A is deployed at
`497b6650ed678bc462f85de6bff14692bffd6ace` and owner-accepted. Its compatibility
work removed Django's dependency before the physical column was retired. No
application image, tenant schema, serial business data, historical migration, or
host checkout changed during 3B. Phase 4 is not started or authorized.

**Checkpoint 3A evidence:** `tests/PHASE3A_COMPATIBILITY_RESULTS.md`.

#### Checkpoint 3A implementation and release checklist

- [x] Remove the physical-column dependency from ORM reads/inserts and rollout
  queries, preserving the serial display/API compatibility and input rejection.
- [x] Add the bounded, atomic, fail-closed default-only migration; preserve the
  physical column, constraint identity, metadata values and serial tenant SQL.
- [x] Test migration forward/reverse, unexpected physical contracts, contention,
  candidate pre-deployment audit, and application operation without the column.
- [x] Test the actual Phase 2 image on the expanded database, including normal
  entrypoint rollback, serial company creation and return to the candidate.
- [x] Pass full regression, preservation/static checks, metadata inventory,
  ARM64, encrypted restore and local production-like staging acceptance.
- [x] Create and validate the exact source commit through staging.
- [x] Obtain explicit push approval, then verify all GitHub CI/CD gates.
- [x] Obtain protected-production approval and deploy the exact tested image.
- [x] STOP: owner manually checks production and explicitly records 3A PASS.
- [x] Obtain owner authorization to start separate 3B discovery/preparation.
- [x] Review a separate 3B cleanup candidate with fresh evidence.

**Owner checkpoint 3A result:** `PASS` — 2026-09-03. The owner reported all
functionality working, initially raised a background-color concern, then
confirmed normal appearance in incognito. This records the owner's overall
acceptance, not independently observed transaction-by-transaction checks.
No frontend change was made; the precise normal-browser cause was not proven.

#### Checkpoint 3B ordered gates

- [x] Verify deployed 3A, all 14 CI/CD jobs, and owner manual acceptance.
- [x] Queue fresh protected read-only inventory `33755059375`, explicitly
  expecting deployed SHA `497b6650ed678bc462f85de6bff14692bffd6ace`.
- [x] Obtain protected approval; review the fresh report and reported dependencies.
- [x] Prepare and validate current-image, resource-bounded backup/isolated
  recovery tooling; do not reuse the older Phase 0 audit-image default unchanged.
- [x] Obtain approval to push recovery-only tooling, then separately approve
  its protected production backup/restore rehearsal; review retained evidence.
- [x] Record owner manual live-site PASS after the production recovery rehearsal.
- [x] Design and test exact-target metadata archival/restoration and bounded
  column contraction, preserving all serial data and unrelated permissions.
- [x] Locally prove published 3A normal startup/company creation on the
  contracted database, exact metadata restoration/reapply, and full regression
  on ARM64. Start from an empty synthetic database through historical migrations.
- [x] Approve the exact local candidate for push, then separately approve its
  protected read-only inspection to obtain the new exact-state fingerprint.
- [x] Review the successful inspection and retained exact-state fingerprint.
- [x] Implement/test the separately approved local
  production execution wrapper, including verified operation-time recovery.
- [x] Run and review the strengthened candidate's protected read-only inspection;
  final review added guards for incoming assignment/archive/feature-list foreign
  keys, so the old `a70f8a1` inspection alone does not complete this gate.
- [x] Approve the exact executor commit for push, then pass dedicated maintenance
  runner tests and its protected production gate (no application image release).
- [x] Complete actual-host current-image backup/isolated round-trip rehearsal
  inside that separately approved operation before any production mutation;
  local tests and a backup-reference timestamp alone do not satisfy this gate.
- [x] Obtain fresh production backup/isolated restore evidence and exact-target
  cleanup approval; revalidate preconditions at execution, not only discovery.
- [x] Run the separately approved cleanup/release and verify continuity/health.
- [x] STOP: owner manually verifies production and records checkpoint 3B PASS.

Detailed preparation and unresolved safety decisions are recorded in
`tests/PHASE3B_CLEANUP_RESULTS.md`. No archive or tenant-schema removal is
authorized by starting preparation or approving the read-only inventory.

**Recovery gate:** `PASS` — protected run `33760176723`, source `962f36f`,
unchanged deployed 3A `497b665`. New backup `db-backup-20260903T135747Z` was
remotely verified and restored in isolation (helper RTO 51 seconds). Disposable
cleanup and final production audits/health passed. The operational artifact and
independent remote release metadata were reviewed; raw host logs remain private.
No quantity permission/grant/feature or column cleanup ran. This recovery result
is not final checkpoint 3B acceptance or permanent authorization to use this
backup for a later destructive operation.

**Owner post-recovery site check:** `PASS` — 2026-09-03, “yes it working fine”.
This is the owner's overall live-site confirmation, not an independently
observed transaction checklist or authorization to execute cleanup.

**Implementation refinement:** 3A migration 0009 already removed the field
from Django state. The 3B candidate therefore performs physical retirement
through an explicitly invoked, fingerprint-bound maintenance transaction, not
an automatic application-startup migration. It archives original permission and
grant IDs privately in the database, validates exact dependencies under bounded
locks, and supports conflict-aware reversal. No serial business implementation,
tenant SQL, frontend, historical migration, or entrypoint changed. No schema
drop is implemented. Ordinary startup will not run cleanup.

**Exact-state inspection:** `PASS` — protected run `33773691381`, source
`a70f8a1`, unchanged healthy ARM64 deployed 3A `497b665`. At 15:45 UTC the
read-only evidence confirmed one ready serial company/schema, permissions
125–138 with 14 direct grants and no group grants, no stale feature entries or
orphan schemas, archive absent and the redundant column still present. Exact
column/dependency guards and strict serial continuity passed. Target-state digest:
`f29440c28fb0acf2640e9a9794918d5adf932cf8a4a2932b0e9b9dacd114b4b4`.
The report expressly does not authorize cleanup. The owner reported the workflow
passed; no new manual post-cleanup acceptance is implied.

**Strengthened inspection and execution:** `PASS` — the final dependency-guarded
source `bc5cdce` passed protected read-only run `33879212477` and reconfirmed the
same target digest against unchanged 3A. Separately authorized protected apply
run `33887331226` passed its 8m54s runner rehearsal, created and verified fresh
backup `db-backup-20260904T155103Z`, restored it with actual production image
identities, proved the isolated apply/reverse/apply round trip (50s restore RTO),
and committed the exact live transaction once. The retained result reports
`mutation_outcome=confirmed_committed`, final checks PASS and contracted-state
digest `129d702094a015931d8cb7f79a12838a54cecb6d5a281ec570a075870d8e8f32`.
The owner then reported the live site online and working. Full evidence is in
`tests/PHASE3B_PRODUCTION_RESULTS.md`.

Fresh-install retirement of historical quantity seeds remains Phase 4 work;
this operational cleanup did not rewrite migration history or claim that fresh
installs are fully consolidated.
Candidate and inspection evidence: `tests/PHASE3B_CONTROLLED_CLEANUP_RESULTS.md`.
Executor evidence: `tests/PHASE3B_EXECUTOR_RESULTS.md`; attended procedure:
`PHASE3B_MAINTENANCE_RUNBOOK.md`. This no-image-change operation uses a dedicated
full-regression/recovery runner gate plus protected maintenance approval instead
of publishing/deploying another image. Existing application-release gates are
unchanged. The executor did not automatically retry, reverse, deploy, or restart
production; the required owner manual production check is now recorded PASS.

### Phase 4 — Repository Hygiene

Remove inactive quantity source, tests, and active documentation; update all
runbooks; then use Django's supported migration replacement process only after
every environment has reached the required migration leaf.

Phase 4 started on 2026-09-04 after the owner instructed “continue” following
the recorded Phase 3 PASS. This instruction starts local discovery and
implementation only; it does not authorize a push, protected inspection,
deployment, migration-history write, archive removal, or production change.

#### Non-negotiable Phase 4 boundary

- Preserve every serial business quantity/count field, serial SQL function,
  report, route, template and test. The ordinary word “quantity” is not itself
  evidence that a component belongs to the retired company family.
- Preserve the Phase 3B archive and its inspected restore tooling until a later
  explicit archive-retention decision. Repository hygiene is not authorization
  to destroy the reversal path.
- Preserve Phase 0–3 operational evidence and the serial-only regression,
  isolation, backup/recovery, ARM64 and security gates.
- Delete only source, SQL, tests and active design/runbook material proven to be
  owned exclusively by the retired quantity-company family.
- Do not rewrite or delete applied migration history in one release.

#### Checkpoint 4.0 — protected read-only entry gate

- [x] Inventory remaining quantity-family files and distinguish them from
  serial line quantities and retained reversal evidence.
- [x] Prepare a database-enforced read-only audit for the exact pre-squash
  leaves `tenancy.0009` and `authentication.0025`.
- [x] Require the Phase 3B archive to remain checksummed and `applied`, the
  physical mode column and retired permissions/features to remain absent, and
  every registered/physical tenant schema to be canonical active ready serial.
- [x] Reuse strict serial continuity and pin the unchanged healthy ARM64 3A
  image/container before and after the streamed audit.
- [x] Pass local contracts and hostile transport tests, including the real
  PostgreSQL post-cleanup/reversal fixture and complete serial suite.
- [x] Review the exact local diff and obtain approval for a `[skip ci]` push.
  Exact commit `4f7f49f` is on `origin/main` with `[skip ci]`; no CI/CD ran.
- [x] Separately authorize and pass the protected read-only production audit.
  Protected run `33896979203` from exact `4f7f49f` PASSED on 2026-09-04
  against deployed 3A `497b665`. The owner released the fresh confirmation
  run `34080323205`, which PASSED on 2026-09-07 with an identical state
  digest `3524c499…` and identical structure fingerprint `b764c48d…`,
  proving production is unchanged across the two audits.
- [x] Review retained operational counts/fingerprint. The audit expressly sets
  `authorizes_migration_replacement=false`; its PASS is evidence, not authority.
  Reviewed artifact of run `33896979203`: `PHASE4_ENTRY_RESULT=PASS`,
  `PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes`,
  `PHASE4_REPLACEMENT_AUTHORIZED=no`. Exact pre-squash leaves
  `tenancy.0009_inventory_mode_compatibility` and
  `authentication.0025_add_quantity_platform_permissions` — precisely the
  leaves the two replacements list. `inventory_mode_column_present=false`,
  `retired_permission_count=0`, `retired_feature_occurrences=0`, Phase 3B
  archive `applied` with payload digest `a7b4b186…`. One company, one physical
  schema, canonical active ready serial v6, journal balanced, no orphan,
  missing, invalid or non-serial schema. Production structure fingerprint
  `b764c48d…` (86 indexes) — the same value the corrected synthetic recovery
  estate now reproduces, independently confirming that fix.

#### Checkpoint 4A — first migration-replacement release

Following Django 6.0's supported process, create serial-only squashed replacement
migrations while **the old migration files remain** beside them. Existing
instances can finish the original chain; new installations use the replacements.

- [x] Generate and independently review squashed `tenancy` and `authentication`
  replacements from the exact audited leaves.
  Reviewed 2026-09-07 against the leaves the protected audit confirmed.
  Both `replaces` lists match the on-disk chains exactly — 9 and 25 entries,
  ending at `tenancy.0009_inventory_mode_compatibility` and
  `authentication.0025_add_quantity_platform_permissions` — and both carry
  dependencies identical to the originals they replace.
  **tenancy:** the final ORM state built from the original chain
  (`replace_migrations=False`) and from the replacement is *identical* across
  all 6 models — fields, options, constraints and managers. The two retained
  constraints are `tenancy_company_valid_tax_environment` and
  `tenancy_company_valid_provisioning_state`; the retired
  `tenancy_company_valid_inventory_mode` is absent, and neither
  `inventory_mode` nor `quantity` appears anywhere in the operations. The one
  apparent difference in the data migrations — original `0006`'s named
  `reverse_backfill` replaced by `RunPython.noop` — is behaviourally identical,
  because `reverse_backfill` is an empty documented `pass`.
  **authentication:** the chain is purely additive (no migration deletes a
  permission), so the union is the correct target. Static analysis and an
  empirical two-database comparison agree exactly: the original chain creates
  90 custom `auth.user` permissions, the replacement creates 76, and the
  difference is *precisely* the 14 retired quantity codenames. Nothing is
  added, nothing is relabelled, and every retained label is byte-identical.
  `makemigrations --check` reports no drift in the built image.
- [x] Remove quantity-only SQL templates/patches, inactive quantity test modules,
  obsolete result/design documents and retired static cleanup code.
  18 SQL files, 20 suite modules, 22 quantity phase results and 4 root design
  documents removed; `deploy/retire_quantity_static.py`, its entrypoint call,
  its unit test and its CI step retired; the quantity-only T7 benchmark
  harness `tests/phase26_performance_capacity.py` removed with its recorded
  evidence retained and annotated.
- [x] Remove the inactive quantity schema-family registry and temporary runtime
  inventory-mode compatibility API without changing serial behavior.
  The dead `all_schema_families()` leftover was removed, and
  `production_foundation_audit --serial-only` was restored to a real
  fail-closed gate driven by physical schema verification after the 4A edit
  had reduced it to an inert `non_serial = []` stub. The Phase 2 byte-identity
  baselines (12 serial view functions, 212 serial UI files, 17 serial SQL
  files) still PASS, proving serial behavior is unchanged.
- [x] Update active README, runbooks, CI and tests to describe and enforce the
  serial-only system; retain Phase 3B reversal tooling and evidence.
  Rewrote every contract and test module that referenced retired code; updated
  `README.md`, `PROJECT_CONTEXT.md`, `CLAUDE.md`, `tests/README.md`,
  `tests/suite/README.md` and the Phase 28/29/30 runbooks; banner-marked
  `todo.md` as a historical record. Added `tests/serial_api_compat.py` so the
  five modules the Phase 3 recovery gate runs *inside the previously published
  3A image* assert the correct invariant on both application shapes. Added 8
  checkpoint 4A contracts covering the exact deletion list, the preserved
  reversal path, absence of dangling references, and the documentation
  contract. The Phase 3B archive, its restore tooling and all Phase 0-3
  evidence are retained.
- [x] Prove a fresh database uses only the squashed serial state and never creates
  the retired column or permissions; prove a database with the original leaves
  produces a no-op migration plan and retains its data.
  Executed by `tests/phase4a_migration_proof.sh` on disposable stacks.
  **Original-leaves upgrade: PASS.** The published 3A image migrated to leaves
  `tenancy.0009` / `authentication.0025`; the 4A image then reported
  "No planned migration operations." and "No migrations to apply.", company
  rows/registry digest/138 permissions were unchanged, the replacement was
  recorded and the 9 replaced rows correctly remain for the 4B prune.
  **Fresh install: PASS, after fixing a defect this proof exposed.**
  `build_multitenant_db.sql` seeded `django_migrations` with
  `('tenancy','0001_initial')` and created the registry tables, so the tenancy
  replacement was only *partially* applied. Django only uses a replacement when
  **all** or **none** of what it replaces is applied, so it discarded the
  replacement, replayed the original chain, and `0005` recreated the retired
  `inventory_mode` column and its constraint on every fresh install.
  On the owner's decision the bootstrap no longer creates the tenancy registry
  or seeds that row: `migrate` owns the public tenancy schema, and
  `deploy/entrypoint.sh` registers the pre-built example schema afterwards with
  the new `register_bootstrap_tenant` command, which refuses to act on any
  database that already contains a company. A fresh install now measures
  retired column = 0, retired constraint = 0, retired permissions = 0, with
  nothing left to migrate and the example tenant registered exactly once.
  Two safety pins were updated under this review: the `HOST_HASHES` entry for
  the bootstrap, and the Phase 2 SQL byte-identity baseline, which was split so
  the 16 serial tenant SQL files and the bootstrap's 12,248-line tenant
  business-schema build are each still pinned byte-for-byte to deployed
  Phase 1.
- [x] Pass full serial, four-company isolation, security, backup/recovery,
  ARM64 and production-like staging gates.
  All container-backed gates PASS locally on ARM64: serial, creation-freeze
  (15/15), runtime-removal (16/16), metadata-inventory (24/24), compatibility
  (34/34 new image + old-image proof), isolation (17/17), ARM64 smoke (34/34),
  full regression (21/21 modules), Phase 3B cleanup (69/69) and executor round
  trips, and the Phase 28 encrypted recovery rehearsal (restore RTO 43s, RPO
  0s). The post-cleanup suite also passes **inside the published 3A image**,
  proving the dual-image shim. Production-like staging was not run separately.
- [ ] Review, approve, publish and deploy the exact 4A image through normal
  protected CI/CD. Stop for owner manual production PASS.

#### Checkpoint 4B — transition replacements and final retirement

Only after every environment has run the 4A release and a new read-only audit
confirms the replacement migration records may the transition complete.

- [ ] Remove the old replaced migration files, update dependencies to the
  squashed migrations, and remove `replaces` so each becomes a normal migration.
- [ ] Validate `migrate --prune` on restored and synthetic databases before any
  separately approved pruning of obsolete migration-table rows.
- [ ] Reprove fresh install, upgraded original history, rollback compatibility,
  serial continuity, backup/restore and all mandatory CI/CD gates.
- [ ] Deploy exact 4B through protected production approval; verify migration
  plan, application health and serial continuity.
- [ ] STOP: owner manually verifies the real production system and records final
  Phase 4 PASS. Only then is the serial-only consolidation plan complete.

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
| 2026-09-03 | Owner explicitly instructed “start phase 3” | Phase 3 started with read-only metadata discovery; production unchanged |
| 2026-09-03 | Phase 3 dependency review | Deployed Phase 2 still reads `inventory_mode`; compatibility release required before column drop. Shared serial currency/tax/provisioning/subscription fields preserved |
| 2026-09-03 | Phase 3 local inventory validation | 134/134 static/release contracts including 20/20 inventory contracts, 24/24 PostgreSQL inventory checks, 5/5 wrapper tests on host and Linux, and exact deployed Phase 2 image stdin execution PASS; disposable projects removed |
| 2026-09-03 | Phase 3 read-only preparation boundary | Source scanner label false-positive corrected; shell guards made explicit after negative tests; no runtime/model/migration/serial SQL change; inventory-only push and protected production inspection require approval |
| 2026-09-03 | Owner explicitly authorized inventory-only push and then protected read-only inspection | Commit `330d22e` pushed to `main` with `[skip ci]`; no automatic CI/CD; manual inventory run `33732596063` queued and separately approved |
| 2026-09-03 | Protected Phase 3 inventory and retained artifact reviewed | All seven inventory checks and strict continuity audit PASS; one serial tenant, 14 legacy quantity permissions/14 direct grant records, no stale quantity feature keys or orphan schemas; deployed Phase 2 ARM64 image and healthy container unchanged |
| 2026-09-03 | Owner reported “the site is live and fine” after the inventory | Checkpoint 3.0 automated and owner site checks PASS; 3A eligible but not started; no cleanup/deployment authorization inferred |
| 2026-09-03 | Owner instructed “continue” after the checkpoint 3A implementation prompt | Local compatibility implementation started; no push/deployment/cleanup authorization inferred |
| 2026-09-03 | Checkpoint 3A local implementation and negative review | Default-only physical migration plus state-only field/constraint removal; existing serial display/validation preserved; wrong constraint kind fails clearly; test-discovery legacy filters corrected without changing serial business logic |
| 2026-09-03 | Checkpoint 3A local validation | 152 static/release and 71 backup contracts, 8 wrapper tests, 36 compatibility checks, all 21 active modules, serial 51/51, ARM64, metadata 24/24 and staging PASS; actual Phase 2 image recovery and serial creation PASS with synthetic restore RTO 43s; no production mutation |
| 2026-09-03 | Exact checkpoint 3A commit `497b665` staged, explicitly approved for push, and deployed by workflow `33736055610` | All 14 jobs PASS; production controller PASS at 09:05:11 UTC; duplicate run `33736057506` cancelled with owner authorization |
| 2026-09-03 | Owner verified functionality and subsequently confirmed normal appearance in incognito | Checkpoint 3A manual PASS; no appearance fix or production mutation made during diagnosis |
| 2026-09-03 | Owner authorized starting checkpoint 3B; fresh read-only inventory queued | Run `33755059375` expects deployed 3A `497b665`, awaits protected production approval; no cleanup authorized or executed |
| 2026-09-03 | Fresh checkpoint 3B production inventory reviewed | Run `33755059375` PASS at 12:31 UTC; one serial company/schema, 14 exact quantity permissions and 14 direct grant records, no stale keys/orphans; expected serial default present; unchanged healthy ARM64 container |
| 2026-09-03 | Current-image recovery-only tooling prepared and tested locally | 16 new unit tests, 152 release contracts, 71 backup contracts and eight existing wrapper/static tests PASS; published 3A ARM64 synthetic encrypted DB restore RTO 44s; exact disposable cleanup verified; production recovery and cleanup remain unexecuted |
| 2026-09-03 | Owner explicitly authorized recovery-only push and separately authorized protected workflow dispatch | Commit `962f36f` pushed with `[skip ci]`; run `33760176723` queued and approved by the owner in GitHub |
| 2026-09-03 | Protected production recovery evidence reviewed | All steps PASS; new encrypted release `db-backup-20260903T135747Z` independently found in private backup repository; isolated restore RTO 51s, disposable cleanup and final production checks PASS; same 3A image/containers, no quantity cleanup authorized or executed |
| 2026-09-03 | Owner reported “yes it working fine” after recovery | Manual live-site check PASS; local cleanup preparation continued, with no push/deployment/destructive approval inferred |
| 2026-09-03 | Explicit transactional 3B cleanup candidate prepared locally | Exact-state read-only inspection, private reversible archive, bounded physical contraction and failure tests; published 3A image and full regression tested on contracted synthetic database; production write wrapper and cleanup remain pending |
| 2026-09-03 | Owner explicitly approved candidate push and asked to retry | Verified remote still at `962f36f`, then pushed exact `a70f8a1` to `main` with `[skip ci]`; remote SHA confirmed and no workflow runs present at verification |
| 2026-09-03 | Owner separately authorized read-only inspection dispatch | Run `33773691381` queued from exact `a70f8a1` against deployed 3A; pending protected production approval verified, not submitted by the agent |
| 2026-09-03 | Protected cleanup-state inspection and artifact reviewed | All steps PASS at 15:45 UTC; exact-state digest captured, 14 permissions/14 direct grants/0 group grants, no stale features/orphans; strict continuity and unchanged healthy ARM64 web PASS; no cleanup authorized or run |
| 2026-09-03 | Owner authorized local preparation/testing of the protected cleanup executor | Added exact-source streamed controller, fresh-backup/isolated round-trip gates, explicit maintenance window/owner, durable uncertain-outcome handling and manual-only protected workflow; no production access or execution in this step |
| 2026-09-03 | Final local guard review expanded inspection preconditions | Reject unreviewed assignment/archive/feature-list FK cascades and permission-table extensions/custom checks/inheritance; archive/apply/restore/transaction bodies unchanged; 68 negative/positive core checks PASS; a fresh protected inspection of this candidate is required before cleanup approval |
| 2026-09-03 | Final executor candidate local validation | ARM64: 200 release contracts, 71 backup contracts, 46 controller/transport units, 68 cleanup checks and all 21 serial modules PASS; encrypted apply/reversal round trips and original recovery path PASS; exact disposable resources removed; no production access, push or execution |
| 2026-09-04 | Final executor commit explicitly authorized and pushed | Exact `bc5cdce` pushed to `main` with `[skip ci]`; remote SHA verified; no automatic CI/CD or deployment run |
| 2026-09-04 | Strengthened protected read-only inspection `33879212477` | Exact final-source dependency/table guards, target digest, serial continuity and unchanged deployed 3A container PASS; no write authorized by inspection |
| 2026-09-04 | Owner authorized exact cleanup scope and named attended owner/window | Digest `f29440c...14b4b4`, action `apply`, owner `Maaz`, approved 15:30–16:30 UTC; protected approval remained separate |
| 2026-09-04 | Protected cleanup run `33887331226` | Runner rehearsal PASS; fresh encrypted backup and actual-image isolated apply/reverse/apply PASS; exact live transaction `confirmed_committed`; final continuity/health PASS; no image deployment or restart |
| 2026-09-04 | Owner reported “yes the site is online fine” after cleanup | Checkpoint 3B and overall Phase 3 manual production PASS; Phase 4 remains unstarted pending explicit instruction |
| 2026-09-04 | Owner instructed “continue” after Phase 3 closeout | Phase 4 local discovery and entry-gate preparation started; no push, protected inspection, migration replacement or production change authorized |
| 2026-09-04 | Phase 4 repository/migration boundary review | Serial line quantities and Phase 3B reversal tooling retained; obsolete family source targeted separately; Django 6.0 requires a two-release squash transition |
| 2026-09-04 | Phase 4 entry-gate local validation | 14/14 Phase 4 and 285/285 complete static/release/backup contracts, 51/51 units and 69/69 PostgreSQL cleanup/audit checks PASS; published 3A restart and complete serial suite PASS; exact disposable project removed |
| 2026-09-06 | Owner instructed “finish 4A's test and doc rewrite” | Local-only implementation started; no push, protected inspection, deployment or production change authorized or performed |
| 2026-09-06 | Checkpoint 4A test rewrite | Every contract/test module that referenced retired code rewritten to assert the stronger serial-only invariant (absence, not rejection). `tests/test_phase2_static_retirement.py` and its CI step removed with the code they tested; the quantity-only T7 benchmark harness removed and its evidence annotated |
| 2026-09-06 | Two defects found in the staged 4A source, not just its tests | `production_foundation_audit --serial-only` had been reduced to an inert `non_serial = []` stub while `deploy/` still passes the flag — restored as a fail-closed gate driven by physical schema verification; the dead `all_schema_families()` leftover removed |
| 2026-09-06 | Cross-image defect found and fixed | The Phase 3 recovery gate deliberately runs the *current* suite inside the previously published 3A image; the first rewrite encoded 4A-only assumptions and would have failed there (3A has no `SERIAL_SCHEMA_FAMILY` and still carries the compatibility API). Added `tests/serial_api_compat.py`; the five affected modules now assert the same guarantee on both shapes and the branching was simulated against both |
| 2026-09-06 | Checkpoint 4A documentation rewrite | `README.md`, `PROJECT_CONTEXT.md` (stale Phase 29/30 resume checkpoint replaced; retired-family section replaced with a retirement record), `CLAUDE.md`, `tests/README.md`, `tests/suite/README.md` and the Phase 28/29/30 runbooks updated; `todo.md` banner-marked historical. PHASE3B runbook and FIXED_ISSUES left unchanged as accurate history |
| 2026-09-06 | Checkpoint 4A local gate run | 21/21 Phase 4 contracts (8 new 4A contracts), 13/13 static contract gates, 4/4 remote-wrapper unittest modules, 3/3 backup test modules, rollback simulation and `compileall` PASS on the host. Serial byte-identity baselines unchanged. Container-backed gates, the fresh/original-leaves migration proof and the protected production inspection remain unrun |
| 2026-09-06 | Container-backed gates executed on local ARM64 Docker | Ran with the owner's approval to stop only the local dev nginx (port 80), restarted afterwards; all disposable projects, volumes and networks verified removed. Every gate PASS: serial, creation-freeze 15/15, runtime-removal 16/16, metadata-inventory 24/24, compatibility 34/34 plus the old-image proof, isolation 17/17, ARM64 34/34, full regression 21/21, Phase 3B cleanup 69/69 and executor round trips, Phase 28 encrypted recovery (RTO 43s, RPO 0s) |
| 2026-09-06 | Four defects the container gates exposed that static gates could not | (1) `phase1_serial_only_creation.py` and (2) `phase3a_compatibility.py` addressed migration nodes the squash removes from Django's graph once applied — both now load history with `replace_migrations=False`; (3) `phase3_metadata_inventory.py` assumed a retired permission pre-exists, which the authentication squash correctly no longer creates — it now seeds and removes its own fixture set; (4) `tests/suite/test_feature_flags.py` still posted `company.inventory_mode` in an admin payload |
| 2026-09-06 | Dual-image shim validated against the real published 3A image | The first shim pass still failed five assertions inside the 3A container (admin instance attribute, request-boundary company stub, retired SQL templates present in that image, and a different rollout rejection message). All five corrected; the complete suite then passed both on the 4A image (21/21) and inside the published 3A image, which is the guarantee the shim exists to provide |
| 2026-09-06 | Checkpoint 4A migration proof executed (`tests/phase4a_migration_proof.sh`) | Original-leaves upgrade PASS: no-op plan, no migrations applied, data and 138 permissions retained, replacement recorded, 9 replaced rows retained for the 4B prune. Fresh-install proof FAILS for `tenancy`: the bootstrap seeds `('tenancy','0001_initial')`, so the replacement is partially applied, Django replays the original chain and `0005` recreates the retired `inventory_mode` column and constraint. The `authentication` squash is correct and creates 0 retired permissions |
| 2026-09-06 | Checkpoint 4A release BLOCKED pending an owner decision | A fresh install would carry a vestigial `inventory_mode` column that production no longer has. The fix touches `build_multitenant_db.sql`, which is hash-pinned by `HOST_HASHES` and needs a fresh source review. No push, deployment or production change was made |
| 2026-09-06 | Owner decided: drop the tenancy bootstrap seed so the squash runs | `build_multitenant_db.sql` no longer creates `tenancy_company`/`tenancy_membership` and no longer seeds `('tenancy','0001_initial')`; Django migrations now own the public tenancy schema. New `register_bootstrap_tenant` command registers the pre-built `tenant_company_1` schema after `migrate`, guarded to refuse any database that already contains a company, so it is a no-op on every existing deployment including production |
| 2026-09-06 | Two safety pins updated under that review | `HOST_HASHES['build_multitenant_db.sql']` re-pinned, and the Phase 2 SQL byte-identity baseline split so the 16 serial tenant SQL files and the bootstrap's 12,248-line tenant business-schema build stay pinned byte-for-byte to deployed Phase 1. That business section is unchanged; only the Django migration bookkeeping changed |
| 2026-09-06 | Fresh-install migration proof now PASSES | Retired column 0, retired constraint 0, retired permissions 0, nothing left to migrate, example tenant registered exactly once, re-registration a no-op. Original-leaves upgrade still a no-op with data retained. Wired into CI as the mandatory `migration-replacement-gate` |
| 2026-09-06 | The bootstrap change cascaded into five further gate defects, all fixed | Fresh installs are a third legitimate database state (column never created, so no 3B archive exists) — accepted in the Phase 1 and company-metadata tests; the Phase 3 inventory and Phase 3A compatibility proofs now reconstruct the retired pre-3B contract on their disposable stacks, because a fresh 4A install no longer provides it; the Phase 28 rollback target was corrected from the Phase 2 image to the actually deployed 3A image (Phase 2 still declares `inventory_mode` as a concrete ORM field and cannot run without that column) and its family check now reads the physical schemas instead of the dropped column; and the synthetic recovery estate registers the bootstrap tenant before applying the rollout SQL, matching the entrypoint's order |
| 2026-09-06 | Complete local gate set re-run green | serial, creation-freeze, runtime-removal, metadata-inventory, compatibility, isolation, full regression, ARM64, 3B cleanup, 3B executor, migration-replacement proof and Phase 28 encrypted recovery all PASS, alongside every static contract gate. Nothing was pushed, deployed or changed in production |
| 2026-09-07 | Documentation gap corrected: the checkpoint 4.0 production audit had already run | Protected run `33896979203` from exact `4f7f49f` completed successfully on 2026-09-04, but the plan checkbox and the Phase 4 results document still said "not dispatched", and that error was repeated in session summaries. Both corrected against the retained artifact |
| 2026-09-07 | Checkpoint 4.0 artifact reviewed | `PHASE4_ENTRY_RESULT=PASS`, container unchanged, `PHASE4_REPLACEMENT_AUTHORIZED=no`. Exact pre-squash leaves `tenancy.0009` / `authentication.0025`; retired column absent, 0 retired permissions, 0 retired feature occurrences; Phase 3B archive `applied` (payload `a7b4b186…`); one canonical active ready serial v6 schema, journal balanced, no orphan or non-serial schema. Production structure fingerprint `b764c48d…` matches what the corrected synthetic recovery estate now reproduces |
| 2026-09-07 | Owner instructed "dispatch the phase 4.0 production audit"; fresh confirmation run queued | Run `34080323205` dispatched from `4f7f49f` with confirmation `INSPECT-PHASE4-MIGRATION-LEAVES` and expected deployed SHA `497b665`. It is held at the `production` environment approval gate with the owner as sole reviewer; the agent verified the pending gate and did not submit the approval |
| 2026-09-07 | Owner released the protected gate; confirmation run `34080323205` PASS | Identical state digest `3524c499…`, identical structure fingerprint `b764c48d…` (86 indexes), container unchanged, `PHASE4_REPLACEMENT_AUTHORIZED=no`. Production provably unchanged across two audits three days apart. Checkpoint 4.0 fully closed |
| 2026-09-07 | Independent review of both squashed replacements completed | `replaces` lists match the on-disk chains exactly and end at the audited leaves; dependencies identical to the originals. tenancy: final ORM state proven identical to the original chain across all 6 models, retired constraint absent, `RunPython.noop` shown behaviourally identical to the original empty `reverse_backfill`, no model drift. authentication: static parse and an empirical two-database diff agree exactly — 90 custom permissions become 76, the difference is precisely the 14 retired codenames, with none added or relabelled. No defects found; two inherited patterns recorded rather than changed |
