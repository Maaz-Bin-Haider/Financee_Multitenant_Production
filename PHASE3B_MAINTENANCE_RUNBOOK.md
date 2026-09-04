# Phase 3B — Attended metadata cleanup and reversal

## Current boundary

The reviewed first apply completed successfully on 2026-09-04 in protected run
`33887331226` from exact source `bc5cdce`. Its outcome was
`confirmed_committed`; final checks passed, and the owner subsequently reported
the live site online and working. Phase 3B is complete. Production remains on
the accepted 3A image `497b6650ed678bc462f85de6bff14692bffd6ace` on the ARM64
t4g.medium host because this was a no-image-change operation.

This runbook remains authoritative for evidence interpretation and any future
attended reversal. The completed apply is not standing authorization to rerun,
restore, remove the archive, or begin Phase 4. Any reversal requires a fresh
read-only applied-state digest, explicit restore authorization, a new backup and
isolated proof, a new attended window, and separate protected approval.

This operation does not deploy an image. It streams reviewed maintenance source
into the existing environment and executes the checksum-pinned transactional
core. This candidate adds incoming-FK guards for assignments, archive state and
feature lists, plus exact permission-table contracts to reject unarchived
extensions; its stronger inspector must run read-only in production before
cleanup approval. No host checkout update, production container-file copy,
image pull, production restart or tenant business SQL rollout is performed.

## Scope and reviewed evidence

Protected read-only run `33773691381` inspected source `a70f8a1` against deployed
3A. The exact state digest was:

```text
f29440c28fb0acf2640e9a9794918d5adf932cf8a4a2932b0e9b9dacd114b4b4
```

That snapshot contained the 14 reviewed historical `auth.user` quantity
permissions, IDs 125–138, with 14 direct-user grant records and no group grants.
There was one ready serial company/schema, no stale feature entries or orphan
schemas, no retirement archive, and the redundant mode column remained present.
The exact column/dependency guards and strict serial continuity passed.
The digest is historical evidence, **not permission to delete**. Because the
candidate adds dependency checks absent from `a70f8a1`, first run the existing
protected read-only inspection workflow from the newly approved source and
review its result, even if it produces the same digest. A changed digest requires
a new read-only inspection and reviewed exact-target approval, never silently
substituting a new value or broadening the candidate set.

The proposed first apply archives original permission/grant IDs and metadata
inside the protected database, removes only those reviewed quantity records,
and drops only `public.tenancy_company.inventory_mode` with its exact known
default/check dependencies. No feature UPDATE is expected for this snapshot.
No schema, customer account, membership, currency/tax/subscription field,
serial feature, serial document or tenant business object is targeted.
The archive remains in place for attended reversal; deleting it requires a
separate retention decision and is not implemented here.

The final strengthened source `bc5cdce` was separately inspected by protected
read-only run `33879212477`, which reconfirmed the same target digest and passed
the added incoming-FK/table-contract guards. Protected apply run `33887331226`
then created verified backup `db-backup-20260904T155103Z`, passed actual-image
isolated apply/reverse/apply recovery with a 50-second restore RTO, committed
once, and produced final contracted-state digest
`129d702094a015931d8cb7f79a12838a54cecb6d5a281ec570a075870d8e8f32`.
See `tests/PHASE3B_PRODUCTION_RESULTS.md` for the exact closeout evidence.

## Approvals before dispatch

1. Review the complete executor, source bundle, workflow, exact core hash,
   unit/failure tests and local integration evidence. Authorize the **exact**
   source commit for pushing. The proposed push must use `[skip ci]`; it does
   not itself execute maintenance or deploy.
2. Run and review the stronger protected read-only inspection, then obtain
   explicit authorization for the exact operation and newly inspected target
   digest. For the first apply, the scope is the records/column above, subject
   to execution-time revalidation. A later restore needs its own newly inspected
   digest and explicit restore authorization.
3. Agree an attended maintenance window and name the person responsible for
   recovery decisions. Inputs are explicit UTC start/end timestamps, with a
   positive window of at most one hour. The executor must start inside it and
   have at least two minutes left before sending the live mutation. Account for
   runner tests and protected approval waiting time when choosing the window.
4. Queue only the reviewed `phase3b-controlled-cleanup.yml` from the approved
   commit/ref. Inspect the run's source SHA and inputs. The dedicated synthetic
   rehearsal job must pass before the `production` gate can be approved.
5. The owner/reviewer approves that protected gate in GitHub. The agent does
   not supply this approval or infer it from a previous inspection/recovery PASS.

Required workflow inputs: `action`, its exact `confirmation`,
`expected_state_sha256`, exact `expected_deployed_sha`, `window_start_utc`,
`window_end_utc`, and `rollback_owner`. The target digest intentionally has no
default. Apply and restore use distinct typed confirmations; neither is an
automatic rollback mechanism. No raw shell mutation command is an approved
substitute for this workflow.

## Execution order and guarantees

The runner first executes release/backup contracts, controller failure tests,
the core cleanup suite and 21-module full serial regression, plus the
new encrypted executor apply/reversal rehearsal. All runner data is synthetic.
This dedicated maintenance gate replaces an image-publication/staging sequence
for this no-image-change operation; existing application CI/CD gates remain
unchanged and mandatory for any later application release. A local PASS does
not substitute for this protected run or for the owner check afterward.

On EC2, the streamed bundle verifies its source identities and the exact
candidate core SHA-256. The executor requires root, the approved 3A tag, healthy
unchanged ARM64 production container/image identities, known host-helper hashes,
at least 1.5 GiB available host memory and required disk capacity. It shares the
recovery host lock and production-deployment concurrency group. Raw evidence
is created in a unique root-only directory, not sent to GitHub.

1. Inspect exact metadata through a read-only database session and require the
   approved digest and an applicable starting state. Already-applied operations
   stop before backup or mutation; do not blindly rerun them.
2. Require strict serial continuity and HTTP health.
3. Run the existing managed encrypted DB-backup service. Verify the release
   timestamp belongs to this operation, remote/local/service state agrees,
   remote verification is recorded, and local encrypted file size/checksum match.
   Existing backup destination, credentials and retention behavior are unchanged.
4. Restore a verified encrypted copy using the actual production web, PostgreSQL
   and Redis image IDs into a UUID-named isolated project. No published ports or
   external network; web 512 MiB/0.35 CPU, DB 768 MiB/0.50 CPU, Redis 64 MiB/0.05
   CPU. Merged configuration and running resource/image identities are checked.
5. Compare restored candidate shape and serial structure against live preflight.
   PostgreSQL object IDs differ after restore, so the restored database gets its
   own local metadata digest, not the live approval digest. Apply → restore →
   apply (or restore → apply → restore for approved reversal), checking serial
   structure and financial-continuity fingerprints between every isolated step.
   Recreate only the disposable web from the published 3A image; normal startup
   must leave cleanup state and serial continuity unchanged.
6. Remove only that disposable project and verify its containers, volumes and
   network are absent. A failed cleanup prevents the live mutation. Failed
   disposable cleanup retains its private work-directory path for attended
   investigation; never use broad Docker pruning to remove it.
7. Recheck production container/image identity, capacity, window, exact live
   target digest and serial structure. Only then mark the durable operation
   status `unknown` and send **one** live mutation. The core rechecks the same
   digest under bounded table/advisory locks, archives before deletion, and
   commits the metadata/DDL operation atomically.
8. Check metadata, strict serial continuity, unchanged healthy container/image
   identities and HTTP afterward. Production balances may legitimately change
   while customers work; equality of business fingerprints is required only
   in the disconnected restored copy, not across live pre/post snapshots.

Company-table access can wait briefly during the exclusive metadata transaction.
Individual statement timeout is 30 seconds, lock wait is two seconds, and the
worker has an in-container 90-second deadline. This is not a promise of zero
latency or zero interruption. The host controller also has bounded subprocess
and overall deadlines. Managed recovery remains DB-only, not uploaded-media
recovery; metadata cleanup does not target media.

## Failure handling and attended reversal

The root-only evidence directory is printed as `PHASE3B_EVIDENCE_DIR`. It contains
private `intent.json` (including window and attending owner), durable
`status.json`, backup/rehearsal logs, mutation output, final inspections and
private failure diagnostics. Only controlled operational summaries are retained
in the workflow artifact. Do not commit raw host logs, backup contents, grant
assignees, customer records or credentials.

| `mutation_outcome` | Meaning and required action |
|---|---|
| `not_attempted` | The executor did not send the live mutation. Resolve the failed gate; any fresh attempt still requires valid scope, window and approvals. |
| `unknown` | The live write may have committed, for example before a connection loss. Do **not** retry or restore automatically. Inspect private evidence and run a separately approved read-only state inspection after the worker has settled. |
| `confirmed_committed` | The core returned a successful committed result. Later health/drift failures can still make the workflow FAIL. Review actual state and customer impact; do not treat a red workflow as proof of database rollback. |

The in-container deadline helps bound a surviving worker if its Docker client
disconnects; killing a Docker client alone does not prove server-side rollback.
SIGKILL, host loss and storage failure can prevent a final status update. The
last durable status and a fresh read-only database inspection are therefore
needed before deciding on recovery. No automatic image rollback, database
restore, metadata reversal, repeated mutation, or production restart occurs.

For a reviewed reversal, first obtain a new read-only digest from the applied
state, an explicit restore authorization and another attended window. The same
workflow takes a **new backup of the cleaned database**, restores it in isolation
and proves the requested reverse/forward/reverse path before the live restore.
The archive restores original permission/grant IDs and supported column/default/
check semantics. ID conflicts, deleted assignees, changed affected feature lists,
new dependencies or an archive that cannot safely be reapplied fail closed.
These cases need individual review, not overwrites, recreated users, weakened
checks, `CASCADE`, or a force option. A supported metadata reversal does not
promise to recreate PostgreSQL object IDs/column ordinal or later unrelated
metadata changes.

The old Phase 3 inventory/recovery default expects the retained mode column and
must not be used unchanged as a post-cleanup certification. Use the new inspector
with strict Phase 0 continuity and the executor's contracted-state recovery hook.
The existing daily DB-backup/preflight helper is exercised against the cleaned
database by the local integration; its default backup behavior is not changed.

## Completion

Workflow PASS requires a confirmed committed result and successful final checks.
Then **STOP** and ask the owner to manually verify the real production system.
Record exactly which checks the owner reports; do not claim independently
observed sales, purchases, returns, reports or payments without evidence.
Only a separately recorded post-cleanup owner PASS can close 3B. Historical seed
retirement/fresh-install consolidation remains Phase 4 work, not part of this
operational cleanup.
