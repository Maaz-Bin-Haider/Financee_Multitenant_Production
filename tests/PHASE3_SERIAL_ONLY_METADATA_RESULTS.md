# Serial-Only Consolidation Phase 3 — Metadata Inventory Preparation

**Date:** 2026-09-03

**Status:** Checkpoint 3.0 local validation PASS; not pushed or run on production.

**Current production image:** `e44737f1f740fa936e853a3d6bbbd068a1b6d89d` (Phase 2)

**Production target:** EC2 `t4g.medium`, ARM64, `ap-south-1`

## Why this checkpoint precedes cleanup

The current Django model and multiple commands still read the physical
`inventory_mode` column. An immediate column drop would break the running
Phase 2 image and the image-only rollback contract. A first compatibility
release must stop relying on the column while keeping it usable by the old
image. Only after deployment and owner verification may a separate release
remove the column, with the compatibility image as its rollback target.

Currency, tax environment, provisioning state, subscriptions, memberships, and
serial feature settings remain part of the existing serial-company workflow.
None is designated for deletion simply because it was introduced alongside
quantity support. The physical serial tenant SQL remains unchanged.

## Inventory-only implementation

- New `serial_only_phase3_audit` command reads physical PostgreSQL metadata and
  uses no Company ORM model dependency. It also runs from stdin inside the
  already-deployed Phase 2 image; installing/deploying the command is not
  required for inspection.
- PostgreSQL enforces a read-only, repeatable-read transaction. Statement
  timeout defaults to 60 seconds, is bounded to 1–120 seconds, and lock timeout
  is two seconds. The production wrapper additionally forces session-level
  `default_transaction_read_only=on`.
- All Company rows, including inactive rows, are inventoried. Physical tenant-
  prefixed schemas are enumerated independently and classified; noncanonical,
  orphan, missing, mixed/quantity, or unready cases require review.
- The permission allowlist exactly matches the 14 seeds from authentication
  migrations 0022–0025, scoped to content type `auth.user`. It reports direct
  user and group assignment counts, checks expected seed labels, and preserves
  same-codename permissions on other content types.
- Seven exact stale feature keys are inventoried. Other keys/order/values are
  fingerprinted for preservation; malformed lists or unclassified legacy
  keys fail strict review. No feature JSON is rewritten.
- The inventory-mode column's physical contract and dependencies are captured.
  Unexpected dependency types/constraints fail strict review. Definitions and
  shared currency/tax values are represented by hashes, not exported records.
- Output excludes company names, usernames, group names, permission assignees,
  emails, financial records, secrets, and customer data. Identifiers, fixed
  schema/permission names, counts, and hashes are operational metadata.
- `inventory_review_ready=true` never authorizes cleanup; every report contains
  `authorizes_cleanup=false` and requires a compatibility release before drop.

## Protected production execution

The new **Phase 3 read-only production inventory** workflow is manual-only and
uses the protected `production` environment. Its concurrency group matches
the normal production deployment job. Inputs require the exact deployed SHA
and the confirmation `INSPECT-PHASE3-READ-ONLY`.

The runner streams the exact workflow checkout's audit source over SSH into
the existing web container. The remote wrapper verifies exactly one running
web container, expected SHA-pinned image, ARM64 architecture, and health
before execution. It then runs the existing strict Phase 0 continuity audit
in a read-only session and checks the web container/image/health afterward.
It does not pull Git or images, build, migrate, restart, create containers,
copy files into the container, or delete anything on EC2.

If inventory or continuity fails, evidence is retained and the workflow fails;
there is no bypass for the known local bootstrap/template drift on production.
If the deployed image has changed, stop and review the actual SHA rather than
silently changing the expected-image guard.

## Local verification

| Gate | Result |
|---|---|
| Phase 0–3 and Phase 27–30 static/release contracts | 134/134 PASS |
| Phase 3 read-only safety contracts (included above) | 20/20 PASS |
| Live PostgreSQL inventory and negative tests | 24/24 PASS |
| Remote wrapper unit tests (host Bash and Linux/Python 3.12) | 5/5 PASS in each environment |
| Stdin execution inside actual deployed Phase 2 image | PASS, read-only filesystem and database session |
| Django system check | PASS — 0 issues |
| Model/migration source drift check | PASS — no changes detected |
| Final diff whitespace and shell syntax | PASS |
| Production inventory | NOT RUN |

The live tests verify no change to public registry/permission/grant snapshots,
force PostgreSQL to reject an injected write (SQLSTATE `25006`), and exercise
inactive companies, scoped permissions, grants, privacy, malformed/stale
feature metadata, customized permission labels, unknown dependencies, orphan
quantity schemas, noncanonical schemas, and timeout bounds. All fixture
changes are confined to uniquely named disposable Docker projects, never the
production database. Both local stacks and their volumes were removed and
their cleanup was independently verified.

The standalone test ran the new audit source inside the published Phase 2
image `ghcr.io/maaz-bin-haider/financee-web:e44737f1f740fa936e853a3d6bbbd068a1b6d89d`
against a synthetic database, without running the image entrypoint. Its result
was inventory-review ready, with cleanup authorization explicitly false.
The same source passed the wrapper tests under Linux/Python 3.12. The offline
model-drift check reports an expected unavailable-database warning; it is not
represented as a production migration-history check.

The complete diff changes only new audit/transport/tests, CI gate wiring, and
the consolidation documents. Existing business views, templates/assets,
models, applied migrations, provisioning/middleware, and serial SQL are
unchanged. Phase 2's 12 serial document source, 212 UI-file, and 17 SQL-file
preservation contracts still pass.

These results are synthetic, not the current production inventory. Production
permission counts, feature keys, and absence of orphans are not assumed from
earlier phases. A new production snapshot remains necessary.

Local evidence (not added to Git):

```text
b27bb93921b3efccae2ad43893e1f81abe17d5ffb603956b410a05ee841ccc8e  /tmp/phase3-inventory-final-20260903.log
680ea861a04cd349b03ada76ddb2b4a070a5c527439d448cc9c3fb19dee28aeb  /tmp/phase3-static-contracts-20260903.log
51fa9867fb6a91ac8d4f2779fda7ee56a85d55f148fab3ed11edaad8dac5dbf8  phase27-artifacts/metadata-inventory/phase3-deployed-image-inventory.json
```

## Issues found during implementation

- A source scanner initially mistook permission labels such as “Can update
  quantity warehouses” for SQL mutation statements. The test now inspects
  actual `cursor.execute` SQL arguments; it still prohibits write operations.
- Wrapper tests exposed failed `[[ ... ]]` checks not stopping under the local
  Bash version when relying only on `set -e`. Every safety guard now has an
  explicit failure exit. Wrong image, wrong architecture, unhealthy web,
  changed container, invalid SHA, and failed audit/continuity are tested.
- The optional empty EC2 app-directory input is preserved as an argument and
  accepted explicitly, avoiding the argument-loss problem encountered during
  Phase 0 maintenance.

## Exit boundary

No migration, permission removal, feature cleanup, schema/column deletion, or
production mutation belongs to this preparatory commit. After local testing,
the owner must authorize its `[skip ci]` push and approve the protected read-
only inventory. Review that evidence before implementing checkpoint 3A/3B.

Phase 3 is not complete. Phase 4 is blocked until the controlled cleanup and
the owner's mandatory production verification are complete.
