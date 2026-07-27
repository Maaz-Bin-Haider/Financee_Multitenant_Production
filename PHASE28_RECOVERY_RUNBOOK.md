# Phase 28 Recovery Runbook

Status: implemented and rehearsed 2026-07-27

## Recovery contract

The recovery unit is one encrypted bundle containing a PostgreSQL
custom-format dump, the complete media volume, a source commit, and SHA-256
checksums. The passphrase is never stored in the bundle or repository.

Backups are acceptable only when copied to storage outside the EC2 instance
and subsequently restored into an isolated `phase28_*` Compose project.

The CI recovery gate uploads its encrypted bundle and evidence as a retained
GitHub Actions artifact, proving that the recovery object leaves the ephemeral
runner. Production operators must point `BACKUP_DEST` at an off-instance mount
or synchronize it to versioned object storage before treating a production
backup as complete.

## Create an encrypted backup

Create a root-readable passphrase file outside the repository and point
`BACKUP_DEST` at an off-server mount or a directory synchronized to remote
object storage:

```bash
cd deploy
BACKUP_DEST=/mnt/offsite/financee \
BACKUP_PASSPHRASE_FILE=/run/secrets/financee_backup_passphrase \
bash backup_encrypted.sh
```

Preserve both the `.tar.enc` bundle and its `.sha256` sidecar. Record the
printed UTC creation time as the recovery point.

## Isolated restore rehearsal

Use credentials that are not production credentials. The project-name guard
prevents the restore script from addressing the normal production Compose
volumes:

```bash
cd deploy
BACKUP_FILE=/mnt/offsite/financee/financee-<timestamp>.tar.enc \
BACKUP_PASSPHRASE_FILE=/run/secrets/financee_backup_passphrase \
RESTORE_ENV_FILE=/run/secrets/phase28-restore.env \
RESTORE_PROJECT=phase28_rehearsal \
bash restore_rehearsal.sh
```

The restore is successful only if checksums pass, PostgreSQL restores without
error, the application becomes healthy, and `release_preflight` verifies every
active restored tenant. The stack and its volumes are removed automatically;
set `KEEP_RESTORE_STACK=1` only during an attended investigation.

## RPO and RTO

- RPO is the elapsed time between the bundle's `created_at_utc` and the
  declared incident recovery point.
- RTO is measured automatically from restore start through application health
  and all-tenant preflight.
- Phase 28 evidence must record both values and the tested data/media sizes.

## Safety

- Never place the passphrase beside the bundle.
- Never restore into project names `deploy`, `financee`, `production`, or
  `prod`.
- Never prune Docker volumes during backup, restore, deployment, or rollback.
- Application rollback does not reverse forward-applied migrations. Only
  expand-and-contract migrations are eligible for release.

## Rehearsal result

The 2026-07-27 rehearsal completed in 163 seconds. The 1,003,552-byte encrypted
bundle restored in 43 seconds with an RPO of zero seconds for the declared
synthetic recovery point. Two serial schemas, restored media, one post-restore
quantity schema, forward migrations, the previous Phase 26 production image,
the current image, ciphertext corruption rejection, and failed-health rollback
all passed. Full evidence is in
`tests/PHASE28_BACKUP_RESTORE_ROLLBACK_RESULTS.md`.
