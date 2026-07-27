# Phase 30 Controlled Production Foundation Runbook

Status: implementation and disposable rehearsal complete; approved production
execution required

## Purpose

Phase 30 deploys only the shared/public migration and serial-family hardening.
It must not provision the quantity pilot. The controller fails if any active
quantity tenant already exists.

## Required change record

The default `PHASE30_BACKUP_MODE=external` records that backup and disaster
recovery are handled by the operator's separate plan. It does not require or
create backup files on EC2.

To re-enable the integrated encrypted backup later, set
`PHASE30_BACKUP_MODE=encrypted` and configure:

- `BACKUP_DEST`: an off-server mounted or synchronized absolute directory;
- `BACKUP_PASSPHRASE_FILE`: an EC2-local readable secret file.

The following repository/environment variables are optional overrides:

- `MAINTENANCE_NOTICE_REFERENCE`: the customer/operator notice record;
- `MAINTENANCE_WINDOW_UTC`: the approved start/end window;
- `ROLLBACK_OWNER`: the named operator empowered to roll back.

When those variables are absent, the protected GitHub production approval/run
ID is recorded as the notice and window reference, and the approving workflow
actor is recorded as rollback owner. The workflow supplies the exact release
SHA, image, and GitHub run/change ID.
The controller rejects a non-SHA image, source/SHA mismatch, missing change
metadata, an invalid backup mode, missing encrypted-mode configuration,
quantity tenant, failed tenant verification, or unbalanced serial ledger.

## Execution order

`deploy/phase30_foundation_deploy.sh` performs:

1. Validate the exact SHA-tagged image, checked-out SHA, notice/window, and
   rollback ownership.
2. Capture read-only T9 platform contracts and a privacy-preserving continuity
   fingerprint for every active serial tenant.
3. Record the external backup plan, or create and verify an encrypted
   database/media restore point when encrypted mode is selected.
4. Run the existing approval-gated pull deployment.
5. Apply public migrations and serial hardening through the image entrypoint;
   no quantity company is created.
6. Repeat T9 and require identical tenant sets, table counts, journals, serial
   state, trial balance, and continuity fingerprints.
7. Enforce login latency, HTTP 5xx, PostgreSQL connection, free-disk,
   container CPU, and container memory thresholds.
8. Retain change, backup, deploy, continuity, container, metric, and log
   evidence under `deploy/phase30-evidence/<release-sha>/`.

Any failure after deployment begins recreates the previous web image, checks
login health, and writes `rollback-incident.txt`. Forward database changes
remain backward-compatible under the rehearsed Phase 27/28 contract.

Application rollback does not undo a destructive database event. External
backup/disaster recovery remains the operator's responsibility in `external`
mode.

## Production-safe T9 coverage

The T9 command is deliberately non-mutating. It verifies:

- authentication, admin, and protected attachment route contracts;
- inventory-family locking in company administration;
- valid subscription state evaluation;
- active user and membership registry readability;
- every active company is registered and physically verified as serial;
- all tenant base-table row counts;
- balanced journal totals and trial-balance report availability;
- available/sold/returned serial inventory state.

It fingerprints sensitive totals rather than placing customer balances in
logs. Exact before/after equality proves the foundation deployment did not
alter customer business data.

## Decision thresholds

Defaults are five seconds login latency, 100 database connections, zero 5xx
responses during deployment, at least 1 GiB free Docker disk, and no container
above 90% CPU or memory at the post-deploy sample. Operators may lower limits
with the documented `PHASE30_*` environment variables. Raising a threshold
requires an approved change-record amendment.
