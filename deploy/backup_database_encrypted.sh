#!/usr/bin/env bash
set -euo pipefail

# Financee DB-only backup.
# This is intentionally separate from backup_encrypted.sh, whose Phase 28
# recovery contract includes both PostgreSQL and uploaded media.

cd "$(dirname "$0")"

: "${BACKUP_DEST:?Set BACKUP_DEST to an absolute local staging directory}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE to a readable secret file}"

[[ "$BACKUP_DEST" = /* ]] || {
    echo "BACKUP_DEST must be an absolute path" >&2
    exit 2
}
[[ -s "$BACKUP_PASSPHRASE_FILE" ]] || {
    echo "Backup passphrase file is missing or empty" >&2
    exit 2
}

lock_file="${BACKUP_LOCK_FILE:-/tmp/financee-db-backup.lock}"
fallback_lock_dir=""
if command -v flock >/dev/null 2>&1; then
    exec 9>"$lock_file"
    flock -n 9 || {
        echo "Another Financee database backup is already running" >&2
        exit 3
    }
else
    fallback_lock_dir="${lock_file}.d"
    mkdir "$fallback_lock_dir" 2>/dev/null || {
        echo "Another Financee database backup is already running" >&2
        exit 3
    }
    trap 'rmdir "$fallback_lock_dir" >/dev/null 2>&1 || true' EXIT
fi

compose=(docker compose)
if [[ -n "${BACKUP_COMPOSE_PROJECT:-}" ]]; then
    compose+=(--project-name "$BACKUP_COMPOSE_PROJECT")
fi
if [[ -n "${BACKUP_ENV_FILE:-}" ]]; then
    compose+=(--env-file "$BACKUP_ENV_FILE")
fi
compose+=(-f docker-compose.yml)
if [[ -n "${BACKUP_COMPOSE_OVERRIDE:-}" ]]; then
    compose+=(-f "$BACKUP_COMPOSE_OVERRIDE")
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_name="financee-db-${stamp}.dump.tar.enc"
work_dir=$(mktemp -d)
umask 077

cleanup() {
    rm -rf -- "$work_dir"
    if [[ -n "$fallback_lock_dir" ]]; then
        rmdir "$fallback_lock_dir" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$BACKUP_DEST"

echo "==> Checking PostgreSQL and application tenant contracts"
"${compose[@]}" exec -T db pg_isready \
    -U "${DB_USER:-financee}" -d "${DB_NAME:-financee}"
"${compose[@]}" exec -T web python manage.py release_preflight

postgres_version=$(
    "${compose[@]}" exec -T db psql \
        -U "${DB_USER:-financee}" -d "${DB_NAME:-financee}" \
        -Atc "SHOW server_version" | tr -d '\r'
)
schema_count=$(
    "${compose[@]}" exec -T db psql \
        -U "${DB_USER:-financee}" -d "${DB_NAME:-financee}" \
        -Atc "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'public' OR schema_name LIKE 'tenant_company_%'" |
        tr -d '\r'
)

echo "==> Capturing transactionally consistent PostgreSQL custom-format dump"
"${compose[@]}" exec -T db pg_dump \
    -U "${DB_USER:-financee}" \
    -d "${DB_NAME:-financee}" \
    --format=custom --compress=6 --no-owner --no-acl \
    >"$work_dir/database.dump"
[[ -s "$work_dir/database.dump" ]] || {
    echo "Database dump is empty" >&2
    exit 4
}

git_sha=$(git -C .. rev-parse HEAD 2>/dev/null || printf 'unknown')
cat >"$work_dir/manifest.txt" <<EOF
format=financee-db-backup-v1
created_at_utc=$stamp
git_sha=$git_sha
database=${DB_NAME:-financee}
postgres_version=$postgres_version
schema_count=$schema_count
includes=database.dump
EOF

(
    cd "$work_dir"
    sha256sum database.dump manifest.txt >SHA256SUMS
)

echo "==> Encrypting database backup"
tar -C "$work_dir" -cf - database.dump manifest.txt SHA256SUMS |
    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
        -pass "file:$BACKUP_PASSPHRASE_FILE" \
        -out "$work_dir/$backup_name"

echo "==> Verifying encrypted bundle and PostgreSQL archive catalogue"
verify_dir="$work_dir/verify"
mkdir -m 700 "$verify_dir"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass "file:$BACKUP_PASSPHRASE_FILE" \
    -in "$work_dir/$backup_name" |
    tar -xf - -C "$verify_dir"
(
    cd "$verify_dir"
    sha256sum -c SHA256SUMS
)
grep -qx "format=financee-db-backup-v1" "$verify_dir/manifest.txt"
"${compose[@]}" exec -T db pg_restore --list <"$verify_dir/database.dump" >/dev/null

(
    cd "$work_dir"
    sha256sum "$backup_name" >"$backup_name.sha256"
)

install -m 600 "$work_dir/$backup_name" "$BACKUP_DEST/$backup_name"
install -m 600 "$work_dir/$backup_name.sha256" \
    "$BACKUP_DEST/$backup_name.sha256"

backup_bytes=$(wc -c <"$BACKUP_DEST/$backup_name" | tr -d ' ')
echo "BACKUP_PATH=$BACKUP_DEST/$backup_name"
echo "BACKUP_SHA256_PATH=$BACKUP_DEST/$backup_name.sha256"
echo "BACKUP_CREATED_AT_UTC=$stamp"
echo "BACKUP_GIT_SHA=$git_sha"
echo "BACKUP_SCHEMA_COUNT=$schema_count"
echo "BACKUP_BYTES=$backup_bytes"
echo "BACKUP_RESULT=PASS"
