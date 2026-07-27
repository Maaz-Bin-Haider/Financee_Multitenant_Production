#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

run_tag="${GITHUB_RUN_ID:-local_$$}"
source_project="phase28_source_$run_tag"
restore_project="phase28_restore_$run_tag"
source_project=${source_project//-/_}
restore_project=${restore_project//-/_}
current_image="financee-phase28-current:${GITHUB_SHA:-local}"
old_image="${PHASE28_OLD_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:4474d2a99be089c8d97c6640ffa29698577f3ff6}"
work_dir=$(mktemp -d)
artifact_dir="${PHASE28_ARTIFACT_DIR:-$repo_root/phase28-artifacts}"
mkdir -p "$artifact_dir"
started_at=$(date +%s)
deploy_env_backup="$work_dir/deploy.env.original"
had_deploy_env=0
if [[ -f deploy/.env ]]; then
    cp deploy/.env "$deploy_env_backup"
    had_deploy_env=1
fi

source_compose=(
    docker compose --project-name "$source_project"
    --env-file "$work_dir/source.env" -f deploy/docker-compose.yml
    -f "$work_dir/source.override.yml"
)
restore_compose=(
    docker compose --project-name "$restore_project"
    --env-file "$work_dir/restore.env" -f deploy/docker-compose.yml
    -f "$work_dir/restore.override.yml"
)

cleanup() {
    "${source_compose[@]}" down -v >/dev/null 2>&1 || true
    "${restore_compose[@]}" down -v >/dev/null 2>&1 || true
    if [[ "$had_deploy_env" == "1" ]]; then
        cp "$deploy_env_backup" deploy/.env
    else
        rm -f deploy/.env
    fi
    rm -rf -- "$work_dir"
}
trap cleanup EXIT

cat >"$work_dir/source.env" <<EOF
SECRET_KEY=phase28-source-only
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee
DB_USER=financee
DB_PASSWORD=phase28-source-db
DB_HOST=db
DB_PORT=5432
WEB_IMAGE=$current_image
EOF
cat >"$work_dir/restore.env" <<EOF
SECRET_KEY=phase28-restore-only
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee
DB_USER=financee
DB_PASSWORD=phase28-restore-db
DB_HOST=db
DB_PORT=5432
WEB_IMAGE=$current_image
EOF
cat >"$work_dir/source.override.yml" <<EOF
services:
  web:
    env_file: $work_dir/source.env
EOF
cat >"$work_dir/restore.override.yml" <<EOF
services:
  web:
    env_file: $work_dir/restore.env
EOF
# Compose validates the base service's ignored deploy/.env before applying the
# service override. Install a temporary compatibility copy for both clean CI
# and local runs; cleanup restores an operator file or removes this copy.
cp "$work_dir/source.env" deploy/.env
openssl rand -base64 48 >"$work_dir/passphrase"
chmod 600 "$work_dir/passphrase"

echo "==> Building disposable Phase 28 source image"
WEB_IMAGE="$current_image" "${source_compose[@]}" build web
"${source_compose[@]}" up -d db redis web
source_web=$("${source_compose[@]}" ps -q web)
for _ in $(seq 1 90); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$source_web")" = healthy ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$source_web")" = healthy ]]

echo "==> Creating representative serial and media recovery state"
"${source_compose[@]}" exec -T web \
    python manage.py provision_tenant "Phase 28 Serial Restored"
"${source_compose[@]}" exec -T web sh -c \
    'mkdir -p /app/media/phase28 && printf phase28-media-sentinel >/app/media/phase28/sentinel.txt'
"${source_compose[@]}" exec -T web python manage.py release_preflight \
    >"$artifact_dir/source-preflight.txt"

echo "==> Producing encrypted bundle outside both Compose projects"
backup_output=$(
    cd deploy
    BACKUP_DEST="$work_dir/offsite" \
    BACKUP_PASSPHRASE_FILE="$work_dir/passphrase" \
    BACKUP_COMPOSE_PROJECT="$source_project" \
    BACKUP_ENV_FILE="$work_dir/source.env" \
    BACKUP_COMPOSE_OVERRIDE="$work_dir/source.override.yml" \
    DB_USER=financee DB_NAME=financee \
    bash backup_encrypted.sh
)
backup_file=$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_PATH=//p')
backup_created=$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_CREATED_AT_UTC=//p')
[[ -s "$backup_file" && -s "$backup_file.sha256" ]]
cp "$backup_file" "$backup_file.sha256" "$artifact_dir/"
(
    cd "$artifact_dir"
    sha256sum -c "$(basename "$backup_file").sha256"
)

echo "==> Proving encrypted-bundle corruption is rejected"
corrupt_file="$work_dir/corrupt.tar.enc"
cp "$backup_file" "$corrupt_file"
printf 'phase28-corruption' | dd of="$corrupt_file" bs=1 seek=128 conv=notrunc 2>/dev/null
if (
    cd deploy
    BACKUP_FILE="$corrupt_file" \
    BACKUP_PASSPHRASE_FILE="$work_dir/passphrase" \
    RESTORE_ENV_FILE="$work_dir/restore.env" \
    RESTORE_PROJECT="phase28_corrupt_$run_tag" \
    RESTORE_COMPOSE_OVERRIDE="$work_dir/restore.override.yml" \
    bash restore_rehearsal.sh
) >"$artifact_dir/corrupt-bundle-check.txt" 2>&1; then
    echo "Corrupted encrypted bundle was incorrectly accepted" >&2
    exit 1
fi
echo "PASS: corrupted encrypted bundle rejected" \
    >"$artifact_dir/corrupt-bundle-check.txt"

echo "==> Restoring bundle into isolated project $restore_project"
restore_output=$(
    cd deploy
    BACKUP_FILE="$backup_file" \
    BACKUP_PASSPHRASE_FILE="$work_dir/passphrase" \
    RESTORE_ENV_FILE="$work_dir/restore.env" \
    RESTORE_PROJECT="$restore_project" \
    RESTORE_COMPOSE_OVERRIDE="$work_dir/restore.override.yml" \
    RESTORE_MEDIA_SENTINEL=phase28/sentinel.txt \
    KEEP_RESTORE_STACK=1 \
    bash restore_rehearsal.sh
)
restore_rto=$(printf '%s\n' "$restore_output" | sed -n 's/^RESTORE_RTO_SECONDS=//p')
[[ "$restore_output" = *"RESTORE_RESULT=PASS"* ]]

echo "==> Applying forward public/tenant migrations and adding quantity family"
"${restore_compose[@]}" exec -T web python manage.py migrate --noinput
"${restore_compose[@]}" exec -T web \
    python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql
"${restore_compose[@]}" exec -T web \
    python manage.py provision_tenant "Phase 28 Quantity Restored" \
    --inventory-mode quantity
"${restore_compose[@]}" exec -T web python manage.py release_preflight \
    >"$artifact_dir/forward-preflight.txt"

echo "==> Verifying previous production image against forward-applied database"
docker pull "$old_image"
WEB_IMAGE="$old_image" "${restore_compose[@]}" up -d --no-deps web
restore_web=$("${restore_compose[@]}" ps -q web)
for _ in $(seq 1 90); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$restore_web")" = healthy ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$restore_web")" = healthy ]]
WEB_IMAGE="$old_image" "${restore_compose[@]}" exec -T web python manage.py check
WEB_IMAGE="$old_image" "${restore_compose[@]}" exec -T db psql \
    -U financee -d financee -Atc \
    "SELECT inventory_mode || ':' || count(*) FROM tenancy_company GROUP BY inventory_mode ORDER BY inventory_mode" \
    >"$artifact_dir/old-image-family-check.txt"
grep -q '^quantity:' "$artifact_dir/old-image-family-check.txt"
grep -q '^serial:' "$artifact_dir/old-image-family-check.txt"

echo "==> Returning to current image and rechecking all families"
WEB_IMAGE="$current_image" "${restore_compose[@]}" up -d --no-deps web
restore_web=$("${restore_compose[@]}" ps -q web)
for _ in $(seq 1 90); do
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$restore_web")" = healthy ]] && break
    sleep 2
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$restore_web")" = healthy ]]
WEB_IMAGE="$current_image" "${restore_compose[@]}" exec -T web \
    python manage.py release_preflight >"$artifact_dir/final-preflight.txt"

bash tests/phase27_rollback_simulation.sh \
    >"$artifact_dir/failed-health-rollback.txt"

finished_at=$(date +%s)
cat >"$artifact_dir/phase28-results.env" <<EOF
PHASE28_RESULT=PASS
BACKUP_CREATED_AT_UTC=$backup_created
BACKUP_BYTES=$(wc -c <"$backup_file" | tr -d ' ')
RPO_SECONDS=0
RESTORE_RTO_SECONDS=$restore_rto
REHEARSAL_SECONDS=$((finished_at - started_at))
OLD_IMAGE=$old_image
CURRENT_IMAGE=$current_image
SOURCE_PROJECT=$source_project
RESTORE_PROJECT=$restore_project
EOF
cat "$artifact_dir/phase28-results.env"
