# Serial-Only Consolidation — Checkpoint 3B Preparation

**Date:** 2026-09-03

**Status:** Fresh protected production inventory PASS. Current-image recovery-only
tooling implemented and locally validated; not pushed or executed on production.
No cleanup migration or metadata archive is implemented. No production database
mutation, deployment, or deletion has run in 3B.

**Required rollback image:** deployed and owner-accepted 3A
`497b6650ed678bc462f85de6bff14692bffd6ace`.

## Verified entry gate

- GitHub `main` and the clean local starting checkout resolve to the 3A SHA.
- Workflow `33736055610` reports success for all 14 jobs at that SHA, including
  protected EC2 deployment. The separate duplicate run was cancelled earlier
  with owner approval. No later deployment appeared in the reviewed run list.
- The owner confirmed functionality and normal appearance in incognito, then
  authorized starting 3B. No application color change was needed or made.
- The existing read-only inventory contracts pass 20/20 and transport unit tests
  pass 5/5 on the local host; shell syntax passes. These are local checks, not
  evidence of current production database contents.

## Fresh inventory — protected execution PASS

[Run `33755059375`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33755059375)
was queued using the existing manual-only workflow on `main`, with explicit
expected deployed SHA `497b6650ed678bc462f85de6bff14692bffd6ace` and confirmation
`INSPECT-PHASE3-READ-ONLY`. The run's source SHA matches that same 3A commit.
Although the existing input description/default mentions Phase 2, the invocation
explicitly overrides the SHA; no old default is being used.

The unchanged wrapper checks the exact running image, ARM64 architecture and
health, executes database-enforced read-only metadata and strict continuity
audits, and checks that the container/image remain unchanged and healthy.
It shares the deployment concurrency group. It cannot restart, deploy, update
the host checkout, or remove data. No protected approval was submitted by the
agent. The owner approved it externally and subsequently reported it passed.

The reviewed run completed successfully at `2026-09-03T12:31:05Z`, with inventory
captured at 12:31:01 UTC and strict continuity at 12:31:02 UTC. All steps passed.

- All seven metadata readiness checks passed, with `authorizes_cleanup=false`.
- One active, ready serial company and one canonical registered serial v6 schema
  exist. There are 24 tenant tables; no missing, orphan, quantity, mixed, or
  noncanonical tenant schemas were reported.
- All 14 exact historical `auth.user` quantity permissions remain with their
  expected labels and 14 direct-user grant records total. This is a grant count,
  not a count of distinct users. There are zero group grants and zero matching
  codenames on other content types in this snapshot.
- The disabled-feature list remains empty: no stale or unclassified quantity
  entries and no preserved entries. No JSON rewrite is currently called for.
- The non-nullable `inventory_mode` column now has a database default. Its
  fingerprint matches the expected `'serial'::character varying` expression.
  Its three reported dependency rows identify that default and two dependency
  records for the expected serial constraint. No unexpected dependency was
  reported. This is the expected change from the earlier 3.0 snapshot.
- Strict serial discovery/continuity passed, with available continuity evidence
  and a balanced journal. This is a point-in-time audit, not a claim of unchanged
  financial balances while customers continue operating the system.
- The deployed and source SHAs both match 3A above; the same ARM64 container
  and image remained healthy. PostgreSQL reported 16.14. No production write,
  restart, checkout update or deployment ran.

The retained [artifact `9893321363`](https://github.com/Maaz-Bin-Haider/Financee_Multitenant_Production/actions/runs/33755059375/artifacts/9893321363)
has 90-day retention. Raw evidence is outside Git at
`/tmp/phase3b-inventory-33755059375.etNy5M/phase3-production-inventory.log`.

```text
dacdce19ec89dee649bb1e4ad6a7753bb352f3d9e895e3663854b43c746aa7d3  GitHub-reported artifact ZIP SHA-256
046ef97ca4c2bc4a428812f271aa7ec47b23bc1752306cb24c05d17503ec0e46  downloaded inventory log SHA-256
```

The inventory classifies dependencies; it is not itself an exhaustive approval
of a physical column contract. The contraction guard still requires exact
type/default/constraint and dependency validation under a bounded lock.

## Recovery-only candidate and local verification

The new manual workflow `phase3-production-recovery.yml` requires the protected
production environment and shares `production-deploy` concurrency. It first
runs unit tests and a synthetic encrypted backup/restore on the GitHub runner.
Only afterward does it stream the reviewed Python source over SSH to EC2.
It does not update the host checkout or pull/build/deploy images there.

`deploy/phase3_recovery_remote.py` requires root, the exact owner-accepted 3A SHA
and recovery-only confirmation. It takes a nonblocking host lock, verifies hashes
of the unchanged host Compose, bootstrap, backup-status and restore helper files,
and checks every production container's running state/image and ARM64 identity.
Web/database must be healthy. The existing 3A commands audit the live database
through read-only sessions in the existing web container.

The script requires at least 1.5 GiB host memory and 1 GiB Docker free space;
after the fresh backup it checks Docker and temporary-file storage against the
greater of 1 GiB or four times the audited database size plus two encrypted
copies. These are conservative guards, not a measured production capacity PASS.
Insufficient capacity stops the gate without silently reducing thresholds.

The existing encrypted DB-backup service creates and remotely verifies a new
managed release. The new guard matches local/remote/service release metadata,
operation-time timestamp, verified state, exact basename, bytes and checksum.
The existing service retains only the newest local encrypted recovery point;
earlier remote backups remain governed by the existing retention policy.
No new destination or credentials are introduced.

A verified encrypted copy is restored through the unchanged managed helper into
a UUID-named disposable project. Web, PostgreSQL and Redis are pinned to the
actual running image IDs, with `pull_policy=never`, no published ports, an
internal network, and isolated named volumes. Limits are DB 768 MiB/0.50 CPU,
web 512 MiB/0.35 CPU, Redis 64 MiB/0.05 CPU. Merged Compose configuration and
actual running limits/image IDs are both checked. The actual 3A entrypoint runs
only in the restored stack; restored metadata and continuity must pass.

The helper process group is stopped before cleanup on timeout/interruption.
Only the newly allocated project is removed, including its volumes/network,
and removal is verified. A cleanup failure retains its private environment path
for attended cleanup and fails certification. Production is independently
rechecked after success or failure, without inheriting restored DB/Compose
environment variables. Raw logs remain root-only under the managed backup
directory; only controlled operational summaries reach GitHub logs/artifacts.

This is database-only recovery, not a media restore or a cleanup command. It
neither removes quantity metadata nor proves rollback against a future contracted
database. Both remain separate requirements.

| Local gate | Result |
|---|---|
| New recovery unit/failure tests | 16/16 PASS on host and Linux/ARM64 Python 3.12 |
| Existing inventory transport/static-retirement tests | 8/8 PASS under Linux/ARM64 |
| Phase 0–3A / 27–30 release contracts | 152/152 PASS, including serial source preservation |
| Existing backup/retention/operation/restore contracts | 71/71 PASS |
| Earlier Phase 0 recovery contracts | 22/22 PASS; historical script unchanged |
| Actual Compose merge and synthetic encrypted DB restore | PASS using published 3A ARM64 image; RTO 44 seconds |
| Restored strict serial and metadata audits | PASS; cleanup authorization remains false |
| Actual restored image/resource limits and disposable removal | PASS; independently checked containers, volumes and networks absent |
| Production recovery | NOT RUN — push and protected approval still required |

The local synthetic backup timestamp was `20260903T124308Z`, size 542,752
encrypted bytes. Published 3A image ID:
`sha256:6cb14f877396118ccdae4b75f0bdef95861276e8bd1d31802acf86e8a1b8c6bc`.
The local PostgreSQL image differs from production's running image; the
production gate will pin the actual host image IDs, not local/runner tags.

Synthetic source project `dbbackup_rehearsal_phase3source_aec1a0e1ae4e4097ab8a56bc38c31f38`
and restore project `dbbackup_rehearsal_phase3_b6e68ac7eac9492d813e328c43388db5`
were removed. The synthetic environment and passphrase were removed; retained
synthetic logs/bundle are outside Git in the temporary directory
`phase3-recovery-synthetic-gowbzzfb`.

```text
6f52f1b44579b49bdbd041b33a2b27137f9d3ef665e8bb86ab49f4dd05f9062b  synthetic-backup.log
ac911a7afa2e918d40ce03e2fdb22c95a7385303c9ceb8c9a5583435ff9e2db2  restore-private.log
59a141a1d7e5e6015f4eb1904308f1df7e5caf93875fc94e0126f76f7b3ba465  restored-serial_only_phase3_audit.json
fecc21eb5ee87840b3d406d11c7104f9bfccff39bbdc273dc1f50532adeb964a  restored-serial_only_phase0_audit.json
```

An initial Linux unit-test invocation used a `noexec` temporary filesystem,
blocking the older transport test's fake executable before any Docker call.
It passed when rerun with executable temporary test fixtures; no production
permissions changed. Adding runner-only image pulls for synthetic rehearsal
also required narrowing the static no-pull assertion to the remote execution
step; production still never pulls images. Neither issue was a production
failure. The full application suite was not rerun for this recovery-only source
change; application/model/migration/frontend/tenant SQL remain unchanged.

## Required implementation and operational safeguards

1. Review the fresh inventory, then prepare recovery using the current 3A image.
   The existing Phase 0 recovery script defaults to an older audit image and its
   workflow uses a different concurrency group from production deployment. Do
   not run it unchanged or assume the historical recovery evidence is fresh.
   Preserve resource/capacity limits for the 4 GiB ARM64 production host, unique
   disposable stack targeting, isolated credentials, and explicit reset to the
   production environment after restore. New tooling requires local failure
   tests, exact source approval, and protected execution.
2. Design an exact-target archive and restoration path for reviewed permission
   rows and direct/group grants, including identifiers and original metadata.
   Account/grant mappings must remain in protected storage, never source control
   or normal workflow logs. Archive retention/removal is a separate decision.
   Prove restoration, conflict handling and transaction rollback before deletion.
3. Scope permissions by exact `auth.user` content type, codename, reviewed label
   and candidate identity. Preserve same-codename permissions on other content
   types, unrelated grants, users, memberships and subscriptions. Recheck the
   candidate set at execution; changed/customized or unexpected dependencies stop
   cleanup rather than silently expanding its targets.
4. Remove only reviewed retired feature-list entries, retaining all other values
   and order. If the fresh inventory still has no stale entries, do not rewrite
   company JSON merely to normalize it. Archive and verify originals if needed.
5. Contract only the redundant public `inventory_mode` column and its exact
   known default/constraint after bounded, fail-closed dependency checks. Never
   use `CASCADE` to overcome an unexpected dependency. Preserve shared currency,
   tax, provisioning and serial feature metadata and all serial tenant objects.
   Define and test reversal separately from image-only rollback.
6. Test actual deployed 3A normal startup, authenticated serial workflows and
   company creation on the contracted database, then re-upgrade. Check that
   old-image migration startup does not recreate retired metadata. Fresh installs
   must pass through historical migrations to the new leaf correctly. Applied
   historical migrations remain untouched during this operational checkpoint.
7. Pass serial source-preservation, full regression, isolation, ARM64, encrypted
   restore, exact-image staging, and failure/lock-contention tests. Prove the
   pre-deployment audit also works on the uncontracted production database.
8. Obtain exact-commit push approval and all protected release gates. A fresh
   operation-time production backup with verified isolated restore and reviewed
   exact-target cleanup approval must precede destructive execution. Revalidate
   all execution-time preconditions; an older inventory cannot authorize newly
   appearing records or dependencies. Serial continuity and health must pass
   afterward. The owner then manually verifies production before Phase 4.

No tenant-schema drop is planned based on the old inventory. Any newly found
orphan requires independent classification and exact-target authorization;
the earlier Company 2 permission cannot be reused. These are preparation
requirements, not claims of implemented controls or executed cleanup.
