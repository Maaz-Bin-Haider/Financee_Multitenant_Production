#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

: "${BACKUP_FILE:?Set BACKUP_FILE to an encrypted DB-only bundle}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE}"
: "${RESTORE_ENV_FILE:?Set RESTORE_ENV_FILE to isolated non-production credentials}"
: "${RESTORE_PROJECT:?Set RESTORE_PROJECT to a disposable project name}"

case "$RESTORE_PROJECT" in
    deploy|financee|production|prod|financee_production)
        echo "Refusing unsafe RESTORE_PROJECT=$RESTORE_PROJECT" >&2
        exit 2
        ;;
esac
[[ "$RESTORE_PROJECT" =~ ^dbbackup_rehearsal_[a-z0-9_]+$ ]] || {
    echo "RESTORE_PROJECT must start with dbbackup_rehearsal_ and use [a-z0-9_]" >&2
    exit 2
}
[[ "$BACKUP_FILE" = /* && -f "$BACKUP_FILE" &&
   -f "$BACKUP_FILE.sha256" ]] || {
    echo "Encrypted backup and checksum sidecar must be absolute existing paths" >&2
    exit 2
}
[[ -s "$BACKUP_PASSPHRASE_FILE" && -f "$RESTORE_ENV_FILE" ]] || {
    echo "Passphrase or isolated restore environment file is missing" >&2
    exit 2
}

backup_basename=$(basename "$BACKUP_FILE")
[[ "$backup_basename" =~ ^financee-db-[0-9]{8}T[0-9]{6}Z\.dump\.tar\.enc$ ]] || {
    echo "Backup filename does not match the managed format" >&2
    exit 2
}
(
    cd "$(dirname "$BACKUP_FILE")"
    sha256sum -c "$(basename "$BACKUP_FILE.sha256")"
)

compose=(
    docker compose
    --project-name "$RESTORE_PROJECT"
    --env-file "$RESTORE_ENV_FILE"
    -f docker-compose.yml
)
if [[ -n "${RESTORE_COMPOSE_OVERRIDE:-}" ]]; then
    compose+=(-f "$RESTORE_COMPOSE_OVERRIDE")
fi

work_dir=$(mktemp -d)
started_at=$(date +%s)
cleanup() {
    status=$?
    rm -rf -- "$work_dir"
    if [[ "${KEEP_RESTORE_STACK:-0}" != "1" ]]; then
        "${compose[@]}" down -v >/dev/null 2>&1 || true
    fi
    return "$status"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

echo "==> Decrypting DB-only recovery bundle"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass "file:$BACKUP_PASSPHRASE_FILE" \
    -in "$BACKUP_FILE" |
    tar -xf - -C "$work_dir"
(
    cd "$work_dir"
    sha256sum -c SHA256SUMS
)
grep -qx 'format=financee-db-backup-v1' "$work_dir/manifest.txt"
[[ -s "$work_dir/database.dump" ]]

expected_schema_count=$(
    sed -n 's/^schema_count=//p' "$work_dir/manifest.txt" | tail -1
)
[[ "$expected_schema_count" =~ ^[0-9]+$ ]] || {
    echo "Encrypted manifest has an invalid schema count" >&2
    exit 4
}

echo "==> Starting isolated PostgreSQL and Redis"
"${compose[@]}" up -d db redis
db_cid=$("${compose[@]}" ps -q db)
for _ in $(seq 1 60); do
    health=$(docker inspect -f \
        '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
        "$db_cid" 2>/dev/null || true)
    [[ "$health" == "healthy" ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$db_cid")" == "healthy" ]]

db_user=$(sed -n 's/^DB_USER=//p' "$RESTORE_ENV_FILE" | tail -1)
db_name=$(sed -n 's/^DB_NAME=//p' "$RESTORE_ENV_FILE" | tail -1)
: "${db_user:?RESTORE_ENV_FILE must define DB_USER}"
: "${db_name:?RESTORE_ENV_FILE must define DB_NAME}"

echo "==> Validating and restoring PostgreSQL archive"
"${compose[@]}" exec -T db pg_restore --list \
    <"$work_dir/database.dump" >/dev/null
"${compose[@]}" exec -T db pg_restore \
    -U "$db_user" -d "$db_name" \
    --clean --if-exists --no-owner --no-acl \
    <"$work_dir/database.dump"

restored_schema_count=$(
    "${compose[@]}" exec -T db psql -U "$db_user" -d "$db_name" -Atc \
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'public' OR schema_name LIKE 'tenant_company_%'" |
        tr -d '\r'
)
[[ "$restored_schema_count" == "$expected_schema_count" ]] || {
    echo "Restored schema count does not match encrypted manifest" >&2
    exit 5
}

echo "==> Starting restored application and verifying all tenant families"
"${compose[@]}" up -d web
web_cid=$("${compose[@]}" ps -q web)
for _ in $(seq 1 90); do
    health=$(docker inspect -f \
        '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
        "$web_cid" 2>/dev/null || true)
    [[ "$health" == "healthy" ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$web_cid")" == "healthy" ]]
"${compose[@]}" exec -T web python manage.py release_preflight

finished_at=$(date +%s)
echo "RESTORE_PROJECT=$RESTORE_PROJECT"
echo "RESTORE_SCHEMA_COUNT=$restored_schema_count"
echo "RESTORE_RTO_SECONDS=$((finished_at - started_at))"
echo "RESTORE_RESULT=PASS"
