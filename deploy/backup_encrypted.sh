#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

: "${BACKUP_DEST:?Set BACKUP_DEST to an off-server mounted/synced directory}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE to a readable secret file}"
[[ "$BACKUP_DEST" = /* ]] || {
    echo "BACKUP_DEST must be an absolute path" >&2
    exit 2
}
[[ -s "$BACKUP_PASSPHRASE_FILE" ]] || {
    echo "Backup passphrase file is missing or empty" >&2
    exit 2
}

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
backup_name="financee-${stamp}"
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT

mkdir -p "$BACKUP_DEST"
umask 077

echo "==> Checking PostgreSQL and application containers"
"${compose[@]}" exec -T db pg_isready -U "${DB_USER:-financee}" -d "${DB_NAME:-financee}"
"${compose[@]}" exec -T web python manage.py release_preflight

echo "==> Capturing PostgreSQL custom-format dump"
"${compose[@]}" exec -T db pg_dump \
    -U "${DB_USER:-financee}" \
    -d "${DB_NAME:-financee}" \
    --format=custom --compress=6 --no-owner --no-acl \
    >"$work_dir/database.dump"

echo "==> Capturing media volume"
"${compose[@]}" exec -T web tar -C /app/media -cf - . \
    >"$work_dir/media.tar"

git_sha=$(git -C .. rev-parse HEAD 2>/dev/null || printf 'unknown')
cat >"$work_dir/manifest.txt" <<EOF
format=financee-recovery-v1
created_at_utc=$stamp
git_sha=$git_sha
database=${DB_NAME:-financee}
includes=database.dump,media.tar
EOF

(
    cd "$work_dir"
    sha256sum database.dump media.tar manifest.txt >SHA256SUMS
)

echo "==> Encrypting recovery bundle"
tar -C "$work_dir" -cf - database.dump media.tar manifest.txt SHA256SUMS |
    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
        -pass "file:$BACKUP_PASSPHRASE_FILE" \
        -out "$work_dir/$backup_name.tar.enc"

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -pass "file:$BACKUP_PASSPHRASE_FILE" \
    -in "$work_dir/$backup_name.tar.enc" |
    tar -tf - >/dev/null

(
    cd "$work_dir"
    sha256sum "$backup_name.tar.enc" >"$backup_name.tar.enc.sha256"
)
install -m 600 "$work_dir/$backup_name.tar.enc" \
    "$BACKUP_DEST/$backup_name.tar.enc"
install -m 600 "$work_dir/$backup_name.tar.enc.sha256" \
    "$BACKUP_DEST/$backup_name.tar.enc.sha256"

echo "BACKUP_PATH=$BACKUP_DEST/$backup_name.tar.enc"
echo "BACKUP_CREATED_AT_UTC=$stamp"
echo "BACKUP_GIT_SHA=$git_sha"
