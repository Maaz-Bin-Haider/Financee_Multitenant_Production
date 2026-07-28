#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

[[ "$(id -u)" == "0" ]] || {
    echo "Run this installer as root" >&2
    exit 2
}
: "${FINANCEE_APP_DIR:?Set FINANCEE_APP_DIR to the absolute repository path}"
[[ "$FINANCEE_APP_DIR" = /* &&
   -f "$FINANCEE_APP_DIR/deploy/run_database_backup.sh" ]] || {
    echo "FINANCEE_APP_DIR is not a valid absolute Financee checkout" >&2
    exit 2
}
[[ -s /etc/financee-backup/github.env &&
   -s /etc/financee-backup/passphrase ]] || {
    echo "Create the documented root-readable credential files first" >&2
    exit 2
}

for command in docker gh jq openssl flock systemctl; do
    command -v "$command" >/dev/null || {
        echo "Missing required command: $command" >&2
        exit 2
    }
done

install -d -o root -g root -m 0700 /var/lib/financee-backup
install -d -o root -g root -m 0700 /etc/financee-backup
chmod 0600 /etc/financee-backup/github.env \
    /etc/financee-backup/passphrase

escaped_app_dir=${FINANCEE_APP_DIR//\\/\\\\}
escaped_app_dir=${escaped_app_dir//&/\\&}
escaped_app_dir=${escaped_app_dir//|/\\|}
sed "s|@APP_DIR@|$escaped_app_dir|g" \
    financee-db-backup.service.example \
    >/etc/systemd/system/financee-db-backup.service
install -o root -g root -m 0644 financee-db-backup.timer.example \
    /etc/systemd/system/financee-db-backup.timer
chmod 0644 /etc/systemd/system/financee-db-backup.service

systemctl daemon-reload
systemctl enable financee-db-backup.timer

echo "Installed and enabled financee-db-backup.timer."
echo "The timer was NOT started. Run the attended manual backup and restore rehearsal first."
