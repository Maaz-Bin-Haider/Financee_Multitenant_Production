#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

: "${BACKUP_DEST:?Set BACKUP_DEST}"
: "${GITHUB_BACKUP_REPOSITORY:?Set GITHUB_BACKUP_REPOSITORY}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE}"
: "${GH_TOKEN:?Set GH_TOKEN}"

[[ "$BACKUP_DEST" = /* ]] || {
    echo "BACKUP_DEST must be absolute" >&2
    exit 2
}
mkdir -p "$BACKUP_DEST"
umask 077

run_dir=$(mktemp -d)
cleanup() {
    rm -rf -- "$run_dir"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

echo "FINANCEE_DB_BACKUP_STARTED_AT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
backup_output="$run_dir/backup-output.txt"
BACKUP_DEST="$BACKUP_DEST" \
BACKUP_PASSPHRASE_FILE="$BACKUP_PASSPHRASE_FILE" \
    bash backup_database_encrypted.sh | tee "$backup_output"

backup_file=$(sed -n 's/^BACKUP_PATH=//p' "$backup_output" | tail -1)
[[ -n "$backup_file" && -f "$backup_file" && -f "$backup_file.sha256" ]] || {
    echo "Backup producer did not return a valid encrypted bundle" >&2
    exit 4
}

upload_output="$run_dir/upload-output.txt"
BACKUP_FILE="$backup_file" \
BACKUP_PASSPHRASE_FILE="$BACKUP_PASSPHRASE_FILE" \
GITHUB_BACKUP_REPOSITORY="$GITHUB_BACKUP_REPOSITORY" \
GH_TOKEN="$GH_TOKEN" \
    bash upload_database_backup_github.sh | tee "$upload_output"
grep -qx 'GITHUB_BACKUP_REMOTE_VERIFIED=true' "$upload_output"
grep -qx 'GITHUB_BACKUP_RESULT=PASS' "$upload_output"

release=$(sed -n 's/^GITHUB_BACKUP_RELEASE=//p' "$upload_output" | tail -1)
bytes=$(sed -n 's/^GITHUB_BACKUP_BYTES=//p' "$upload_output" | tail -1)
state_file="${BACKUP_STATE_FILE:-$BACKUP_DEST/last-success.env}"
state_tmp="$run_dir/last-success.env"
cat >"$state_tmp" <<EOF
LAST_SUCCESS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
LAST_RELEASE=$release
LAST_BACKUP_BYTES=$bytes
LAST_BACKUP_FILE=$(basename "$backup_file")
REMOTE_VERIFIED=true
EOF
install -m 600 "$state_tmp" "$state_file"

# The remote release is now independently verified. Retain only the newest
# local encrypted recovery point and its checksum; remote retention is handled
# separately by exact managed release tags.
find "$BACKUP_DEST" -maxdepth 1 -type f \
    -name 'financee-db-*.dump.tar.enc' ! -name "$(basename "$backup_file")" \
    -delete
find "$BACKUP_DEST" -maxdepth 1 -type f \
    -name 'financee-db-*.dump.tar.enc.sha256' \
    ! -name "$(basename "$backup_file").sha256" -delete

echo "FINANCEE_DB_BACKUP_FINISHED_AT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "FINANCEE_DB_BACKUP_RESULT=PASS"
