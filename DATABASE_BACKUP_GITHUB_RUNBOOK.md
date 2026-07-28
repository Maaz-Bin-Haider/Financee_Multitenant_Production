# Financee Daily Database Backup to Private GitHub Releases

Status: implemented locally; production installation and first remote restore
rehearsal require operator credentials and approval.

## Recovery contract

This job creates a PostgreSQL-only recovery point every 24 hours. It captures
the shared `public` schema and every tenant schema in one custom-format dump,
places the dump and its manifest/internal checksums in an encrypted bundle, and
uploads only the encrypted bundle plus its ciphertext SHA-256 sidecar.

The approved destination is the private repository:
`Maaz-Bin-Haider/financee_pk_backup`.

This does not include uploaded invoice images or PDFs. Continue using the
separate Phase 28 database-plus-media procedure whenever complete application
recovery is required.

## One-time GitHub setup

1. Confirm `financee_pk_backup` is private.
2. Create a fine-grained personal access token restricted to only
   `Maaz-Bin-Haider/financee_pk_backup`. Grant only the repository permissions
   required to read repository metadata and create/list/delete releases,
   release assets, and their tags.
3. Give the token an expiry date and schedule rotation before expiry.
4. Never place the token or encryption passphrase in either Git repository.

GitHub Release assets are used instead of Git commits. Regular Git repository
objects are blocked above 100 MiB and make repository history grow
permanently. The implementation fails at 1.9 GiB, below the current 2 GiB
per-release-asset boundary.

## EC2 secret and state setup

Run on EC2 as root. Replace the placeholders without printing them into shell
history where possible:

```bash
install -d -o root -g root -m 0700 /etc/financee-backup
install -d -o root -g root -m 0700 /var/lib/financee-backup
editor /etc/financee-backup/github.env
editor /etc/financee-backup/passphrase
chmod 0600 /etc/financee-backup/github.env
chmod 0600 /etc/financee-backup/passphrase
```

`/etc/financee-backup/github.env`:

```env
GITHUB_BACKUP_REPOSITORY=Maaz-Bin-Haider/financee_pk_backup
GH_TOKEN=<fine-grained-token>
GITHUB_BACKUP_KEEP_DAILY=30
GITHUB_BACKUP_KEEP_MONTHLY=12
```

The passphrase file contains one strong, randomly generated passphrase and a
final newline. Keep a second offline copy. Losing it makes every encrypted
backup unrecoverable.

Install GitHub CLI and `jq` on EC2 if absent, then authenticate only through
the service's `GH_TOKEN`; do not run a broad interactive `gh auth login` for
root.

## Attended first backup

From the production checkout:

```bash
cd /home/ubuntu/Financee_Multitenant_Production/deploy
set -a
source /etc/financee-backup/github.env
set +a
BACKUP_DEST=/var/lib/financee-backup \
BACKUP_PASSPHRASE_FILE=/etc/financee-backup/passphrase \
bash run_database_backup.sh
```

Success requires `FINANCEE_DB_BACKUP_RESULT=PASS`. The uploader independently
downloads both release assets, verifies the ciphertext checksum, decrypts the
bundle, verifies internal checksums, and reads the `pg_restore` catalogue
before recording success. Inspect application health and EC2 CPU, memory,
disk, and CPU-credit metrics during this first run.

## Isolated remote restore rehearsal

Download one release into a root-only temporary directory:

```bash
install -d -o root -g root -m 0700 /var/lib/financee-restore-rehearsal
gh release download db-backup-<UTC_TIMESTAMP> \
  --repo Maaz-Bin-Haider/financee_pk_backup \
  --dir /var/lib/financee-restore-rehearsal
```

Create a non-production restore environment file with a unique database
password:

```env
SECRET_KEY=restore-only-not-production
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee_restore
DB_USER=financee_restore
DB_PASSWORD=<unique-restore-password>
DB_HOST=db
DB_PORT=5432
```

Run:

```bash
cd /home/ubuntu/Financee_Multitenant_Production/deploy
BACKUP_FILE=/var/lib/financee-restore-rehearsal/financee-db-<UTC_TIMESTAMP>.dump.tar.enc \
BACKUP_PASSPHRASE_FILE=/etc/financee-backup/passphrase \
RESTORE_ENV_FILE=/etc/financee-backup/restore-rehearsal.env \
RESTORE_PROJECT=dbbackup_rehearsal_manual \
bash restore_database_backup_rehearsal.sh
```

The restore tool rejects production-like project names, uses isolated Compose
volumes, verifies both checksum layers, restores PostgreSQL, compares the
schema count with the encrypted manifest, starts the application, and runs
`release_preflight`. It removes the isolated stack and volumes automatically.
`KEEP_RESTORE_STACK=1` is allowed only during an attended investigation.

Do not enable the timer until the remotely downloaded restore passes.

## Install and start the daily timer

Installation enables but intentionally does not start the timer:

```bash
cd /home/ubuntu/Financee_Multitenant_Production/deploy
sudo FINANCEE_APP_DIR=/home/ubuntu/Financee_Multitenant_Production \
  bash install_database_backup_timer.sh
sudo systemctl start financee-db-backup.timer
systemctl list-timers financee-db-backup.timer
```

The timer runs daily at 02:15 UTC with up to 15 minutes randomized delay.
`Persistent=true` runs a missed job after the EC2 instance returns. The backup
lock rejects overlapping manual or scheduled runs.

## Monitoring

```bash
sudo /home/ubuntu/Financee_Multitenant_Production/deploy/database_backup_status.sh
sudo systemctl status financee-db-backup.service
sudo journalctl -u financee-db-backup.service --since "2 days ago"
```

The status command exits non-zero if no managed release exists or the newest
one is older than 26 hours. Two consecutive failures or an age above 26 hours
is an operations incident. Logs must never include the token, passphrase,
plaintext dump, database password, or customer data.

Retention runs only after a new remote backup has passed all verification.
It retains the newest 30 daily releases and the first successful recovery
point in each of the newest 12 represented UTC months. Only exact
`db-backup-YYYYMMDDTHHMMSSZ` releases and their tags can be selected.

## Token and passphrase handling

- Rotate the fine-grained token before expiry, update only
  `/etc/financee-backup/github.env`, then run an attended backup.
- Do not rotate the encryption passphrase casually: older releases require the
  passphrase that encrypted them. A passphrase rotation needs a versioned key
  custody plan and restore rehearsal.
- Repository visibility must remain private. A visibility change is an
  incident even though assets are encrypted.

## Disable or remove

```bash
sudo systemctl disable --now financee-db-backup.timer
sudo systemctl stop financee-db-backup.service
```

Wait for any active backup to finish before removal. Removing the timer must
not remove PostgreSQL volumes, application configuration, Phase 28 recovery
scripts, local state, or remote releases. Remote deletion requires a separate
owner-approved decommission decision after a final restore rehearsal.
