# Phase 4 — Repository Hygiene and Migration Transition

**Started:** 2026-09-04

**Current status:** Checkpoint 4.0 read-only entry gate prepared and validated
locally. No
Phase 4 push, protected production inspection, migration replacement, file
retirement, CI/CD release, deployment, archive change, or production mutation
has been authorized or performed.

## Entry decision

Phase 3 and its required owner production check passed. Phase 4 is not a simple
text search for “quantity”: serial purchases, sales, returns and stock reports
legitimately store/display counts named quantity. Those serial components must
remain byte-for-byte behaviorally compatible.

The removable family-owned inventory currently includes the inactive quantity
schema registry, 18 quantity SQL templates/patches, 20 inactive quantity suite
modules, quantity-family result/design documents, and migration operations that
historically introduced then retired the family. Exact deletion lists and
reference rewrites will be contract-tested in checkpoint 4A; this entry step
does not delete them.

The Phase 3B archive is intentionally present in production in state `applied`.
Its restore command, controller, workflow, tests and runbook remain required
recovery assets and are excluded from repository cleanup. Archive deletion or
reversal requires separate explicit authority and fresh protected evidence.

## Migration replacement rule

The pinned framework is Django 6.0.6. Its supported process requires two
releases:

1. add squashed replacements beside the old files, deploy, and run `migrate` on
   every environment so both partial-history and fresh-install paths are safe;
2. only after that rollout is proven, delete replaced files, update dependencies,
   remove `replaces`, validate pruning, and make a second release.

Phase 4 is therefore split into checkpoints 4A and 4B. A one-release deletion of
already-applied migrations is expressly forbidden.

## Checkpoint 4.0 implementation

- `serial_only_phase4_audit.py` starts a repeatable-read PostgreSQL transaction
  and explicitly makes it read-only. It requires exact original migration leaves
  `tenancy.0009` and `authentication.0025` before any squashing work.
- It requires the physical `inventory_mode` column, 14 retired permissions and
  seven retired feature keys to remain absent after Phase 3B.
- It requires the private Phase 3B archive marker/checksum and state `applied`,
  without exporting its payload or permission assignees.
- It requires all company rows and physical schemas to match, be canonical
  active/ready serial tenants, contain serial metadata, and contain no retired
  quantity-family metadata table.
- The SSH wrapper pins the accepted 3A image SHA, ARM64 architecture, healthy
  web container and unchanged image/container identities; both database sessions
  independently use PostgreSQL `default_transaction_read_only=on`.
- The existing strict Phase 0 continuity audit runs in the second read-only
  session. The workflow is manual-only, protected by the `production`
  environment and serialized with deployments.
- Output contains counts, migration leaf names and cryptographic fingerprints
  only, and explicitly returns `authorizes_migration_replacement=false` and
  `PHASE4_REPLACEMENT_AUTHORIZED=no`.

## Remaining checkpoint 4.0 gates

1. Obtain explicit approval before pushing an exact `[skip ci]` audit commit.
2. Obtain separate authorization before dispatching the protected read-only
   workflow, then review its retained artifact.
3. Only after that evidence may checkpoint 4A implementation begin. Any drift,
   non-serial schema, missing archive, unexpected migration record, continuity
   failure or container change stops Phase 4.

## Local validation result

- Static/read-only and transition contracts: 14/14 PASS.
- Hostile remote-wrapper unit tests: 5/5 PASS.
- Complete Phase 0–4/release/security/backup contract set: 285/285 PASS.
- Inventory/recovery/cleanup/static-retirement/Phase 4 unit set: 51/51 PASS.
- Real PostgreSQL cleanup/reversal plus Phase 4 entry audit: 69/69 PASS.
- Actual published 3A restart on the contracted database: PASS.
- Complete post-cleanup serial suite: PASS.
- Exact disposable Docker project and its containers, volumes and network:
  removed and independently rejected as remaining by the existing harness.

Final synthetic evidence directory (outside Git):
`/var/folders/qv/qpbw48nx28x_w6tw3q_g7v440000gn/T/phase3-recovery-synthetic-fplpyw5_`.

```text
a9f50137c74e28d6200719e5301f900180736b63f3dd2c9d1d8c03f201738e65  cleanup-tests.log
506f1a158a92bd1cda96a3caadfb69d264c435a73507ea0529aad9a959cad6aa  old-image-proof.log
0dfbfa1b1530634abd11cc1a9473feeaa816f65a5e244c957f7a98fc1e9cb50a  post-cleanup-full-suite.log
ca54bc68ccd3b0e49b07ec22ac524439dcaa1d58f412b5e39d520d8a48aced06  synthetic-cleanup.log
```

Reviewed entry-gate source SHA-256 values:

```text
98b3ac3521e68a43288636aed00b480fb4013de7566959a2219ff386d63c0e04  serial_only_phase4_audit.py
c620949f61fb339e41974901372d876e2640525c84d0af194b1e16b119ccdc6f  phase4_inventory_remote.sh
475f30a4f0929418d706a7c2f58fe1a9084a8041fd7a6b926b5a406b2af43713  phase4_repository_hygiene_contracts.py
8b378ff425da3cd1da0cbf5ad6d0b0d6d22edb8822cc41b14d2b55b000198cf8  test_phase4_inventory_remote.py
208acf52a4dcce68d5b28f2e86958a35b69e340fc6dc0938e93047c9519601cd  phase4-migration-leaf-inspection.yml
```

Three local defects were exposed before any production contact: the published
image fixture initially lacked the new streamed audit module, the archive
checksum regex had an invalid doubled quantifier, and two schema-discovery SQL
spellings conflicted with Python/PostgreSQL formatting rules. The harness setup,
regex and SQL were corrected; all gates were rerun from a fresh disposable
project to PASS. The failed projects also reported exact cleanup success.
