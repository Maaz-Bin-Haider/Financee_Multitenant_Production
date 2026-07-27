#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

: "${BACKUP_FILE:?Set BACKUP_FILE to an encrypted Phase 28 bundle}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE}"
: "${RESTORE_ENV_FILE:?Set RESTORE_ENV_FILE to isolated non-production credentials}"
: "${RESTORE_PROJECT:?Set RESTORE_PROJECT to a disposable Compose project name}"

case "$RESTORE_PROJECT" in
    deploy|financee|production|prod)
        echo "Refusing unsafe RESTORE_PROJECT=$RESTORE_PROJECT" >&2
        exit 2
        ;;
esac
[[ "$RESTORE_PROJECT" =~ ^phase28_[a-z0-9_]+$ ]] || {
    echo "RESTORE_PROJECT must start with phase28_ and contain [a-z0-9_]" >&2
    exit 2
}
[[ -f "$BACKUP_FILE" && -s "$BACKUP_PASSPHRASE_FILE" ]] || {
    echo "Backup or passphrase file is missing" >&2
    exit 2
}
[[ -f "$RESTORE_ENV_FILE" ]] || {
    echo "Isolated restore environment file is missing" >&2
    exit 2
}

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
    rm -rf -- "$work_dir"
    if [[ "${KEEP_RESTORE_STACK:-0}" != "1" ]]; then
        "${compose[@]}" down -v >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

echo "==> Decrypting and authenticating backup bundle"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass "file:$BACKUP_PASSPHRASE_FILE" \
    -in "$BACKUP_FILE" |
    tar -xf - -C "$work_dir"
(
    cd "$work_dir"
    sha256sum -c SHA256SUMS
)
grep -qx 'format=financee-recovery-v1' "$work_dir/manifest.txt"

echo "==> Creating isolated restore database"
"${compose[@]}" up -d db redis
db_cid=$("${compose[@]}" ps -q db)
for _ in $(seq 1 60); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$db_cid")" = healthy ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$db_cid")" = healthy ]]

db_user=$(sed -n 's/^DB_USER=//p' "$RESTORE_ENV_FILE" | tail -1)
db_name=$(sed -n 's/^DB_NAME=//p' "$RESTORE_ENV_FILE" | tail -1)
: "${db_user:?RESTORE_ENV_FILE must define DB_USER}"
: "${db_name:?RESTORE_ENV_FILE must define DB_NAME}"

echo "==> Restoring PostgreSQL and media"
"${compose[@]}" exec -T db pg_restore \
    -U "$db_user" -d "$db_name" \
    --clean --if-exists --no-owner --no-acl \
    <"$work_dir/database.dump"
"${compose[@]}" run --rm --no-deps -T --entrypoint tar web \
    -C /app/media -xf - <"$work_dir/media.tar"

echo "==> Starting restored application and verifying every tenant"
"${compose[@]}" up -d web
web_cid=$("${compose[@]}" ps -q web)
for _ in $(seq 1 90); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$web_cid")" = healthy ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$web_cid")" = healthy ]]
"${compose[@]}" exec -T web python manage.py release_preflight
if [[ -n "${RESTORE_MEDIA_SENTINEL:-}" ]]; then
    [[ "$RESTORE_MEDIA_SENTINEL" != /* && "$RESTORE_MEDIA_SENTINEL" != *".."* ]] || {
        echo "RESTORE_MEDIA_SENTINEL must be a safe path relative to /app/media" >&2
        exit 2
    }
    "${compose[@]}" exec -T web test -f "/app/media/$RESTORE_MEDIA_SENTINEL"
fi

finished_at=$(date +%s)
echo "RESTORE_PROJECT=$RESTORE_PROJECT"
echo "RESTORE_RTO_SECONDS=$((finished_at - started_at))"
echo "RESTORE_RESULT=PASS"
