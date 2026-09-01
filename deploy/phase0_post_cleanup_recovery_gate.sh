#!/usr/bin/env bash
set -euo pipefail

# Root-only, attended production recovery rehearsal. It creates a new encrypted
# post-cleanup recovery point, restores it into a uniquely named and
# resource-limited Compose project, runs strict serial discovery there, removes
# only that disposable project, and rechecks production.

cd "$(dirname "$0")"

[[ "$(id -u)" == "0" ]] || {
    echo "Run the Phase 0 recovery gate as root" >&2
    exit 2
}
[[ "${PHASE0_RECOVERY_CONFIRMATION:-}" == "VERIFY-PHASE0-POST-CLEANUP-RESTORE" ]] || {
    echo "Exact Phase 0 recovery confirmation is required" >&2
    exit 2
}

audit_image="${PHASE0_AUDIT_IMAGE:-ghcr.io/maaz-bin-haider/financee-web:8f407dea9e488eab8980b48309c064a00db714cd}"
backup_dir="/var/lib/financee-backup"
passphrase_file="/etc/financee-backup/passphrase"
restore_override="$(pwd)/docker-compose.phase0-recovery.yml"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
restore_project="dbbackup_rehearsal_phase0_${stamp,,}"
work_dir=$(mktemp -d)
restore_env="$work_dir/restore.env"
evidence_dir="phase0-recovery-evidence/$stamp"
mkdir -p "$evidence_dir"
evidence_dir=$(cd "$evidence_dir" && pwd)
cleanup_done=0

cleanup() {
    status=$?
    if [[ "$cleanup_done" != "1" && -f "$restore_env" ]]; then
        WEB_IMAGE="$audit_image" WEB_ENV_FILE="$restore_env" \
        docker compose --project-name "$restore_project" \
            --env-file "$restore_env" -f docker-compose.yml \
            -f "$restore_override" down -v >/dev/null 2>&1 || true
    fi
    rm -rf -- "$work_dir"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

[[ -s "$passphrase_file" ]] || {
    echo "Production backup passphrase file is unavailable" >&2
    exit 2
}
[[ -f "$restore_override" ]] || {
    echo "Resource-limited recovery override is unavailable" >&2
    exit 2
}

available_kb=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
docker_root=$(docker info --format '{{.DockerRootDir}}')
disk_available_kb=$(df -Pk "$docker_root" | awk 'NR == 2 {print $4}')
[[ "$available_kb" =~ ^[0-9]+$ && "$available_kb" -ge 1258291 ]] || {
    echo "Refusing recovery rehearsal: less than 1.2 GiB host memory is available" >&2
    exit 3
}
[[ "$disk_available_kb" =~ ^[0-9]+$ && "$disk_available_kb" -ge 3145728 ]] || {
    echo "Refusing recovery rehearsal: less than 3 GiB Docker disk is available" >&2
    exit 3
}

production_compose=(docker compose -f docker-compose.yml)
if [[ -f /etc/nginx/cloudflare/origin.pem && -f docker-compose.tls.yml ]]; then
    production_compose+=(-f docker-compose.tls.yml)
fi

echo "==> Proving current production is serial-only before backup"
WEB_IMAGE="$audit_image" "${production_compose[@]}" run --rm --no-deps -T \
    --entrypoint python web manage.py serial_only_phase0_audit \
    --include-continuity --strict-serial >"$evidence_dir/production-before.json"

echo "==> Creating a new post-cleanup encrypted remote backup"
backup_started_epoch=$(date -u +%s)
systemctl start financee-db-backup.service
bash database_backup_status.sh | tee "$evidence_dir/backup-status.txt"
grep -qx 'REMOTE_BACKUP_STATUS=FRESH' "$evidence_dir/backup-status.txt"
backup_release=$(sed -n 's/^REMOTE_LAST_RELEASE=//p' \
    "$evidence_dir/backup-status.txt" | tail -1)
python3 - "$backup_release" "$backup_started_epoch" <<'PY'
import datetime
import re
import sys

match = re.fullmatch(r"db-backup-(\d{8}T\d{6}Z)", sys.argv[1])
if not match:
    raise SystemExit("Backup service did not report a managed release")
created = datetime.datetime.strptime(
    match.group(1), "%Y%m%dT%H%M%SZ"
).replace(tzinfo=datetime.timezone.utc)
if int(created.timestamp()) < int(sys.argv[2]):
    raise SystemExit("Backup release predates this recovery operation")
PY

backup_stamp=${backup_release#db-backup-}
backup_file="$backup_dir/financee-db-${backup_stamp}.dump.tar.enc"
[[ -s "$backup_file" && -s "$backup_file.sha256" ]] || {
    echo "Fresh managed backup is not retained locally for rehearsal" >&2
    exit 4
}

echo "==> Preparing ephemeral non-production restore credentials"
secret_key=$(openssl rand -hex 48)
db_password=$(openssl rand -hex 32)
umask 077
{
    echo "SECRET_KEY=$secret_key"
    echo "DEBUG=False"
    echo "ALLOWED_HOSTS=localhost,127.0.0.1"
    echo "CSRF_TRUSTED_ORIGINS=http://localhost"
    echo "DB_NAME=financee_phase0_restore"
    echo "DB_USER=financee_phase0_restore"
    echo "DB_PASSWORD=$db_password"
    echo "DB_HOST=db"
    echo "DB_PORT=5432"
} >"$restore_env"
unset secret_key db_password

export WEB_IMAGE="$audit_image"
export WEB_ENV_FILE="$restore_env"
restore_compose=(
    docker compose --project-name "$restore_project"
    --env-file "$restore_env" -f docker-compose.yml -f "$restore_override"
)

echo "==> Restoring into the isolated resource-limited project"
restore_started_epoch=$(date -u +%s)
BACKUP_FILE="$backup_file" \
BACKUP_PASSPHRASE_FILE="$passphrase_file" \
RESTORE_ENV_FILE="$restore_env" \
RESTORE_PROJECT="$restore_project" \
RESTORE_COMPOSE_OVERRIDE="$restore_override" \
KEEP_RESTORE_STACK=1 \
    bash restore_database_backup_rehearsal.sh | tee "$evidence_dir/restore.txt"
grep -qx 'RESTORE_RESULT=PASS' "$evidence_dir/restore.txt"

echo "==> Proving the restored estate is strictly serial-only"
"${restore_compose[@]}" exec -T web python manage.py serial_only_phase0_audit \
    --include-continuity --strict-serial | tee "$evidence_dir/restored-phase0.json"

echo "==> Removing only the disposable restore project and volumes"
"${restore_compose[@]}" down -v
cleanup_done=1
[[ -z "$(docker ps -aq --filter "label=com.docker.compose.project=$restore_project")" ]]

echo "==> Rechecking production after isolated recovery"
WEB_IMAGE="$audit_image" "${production_compose[@]}" run --rm --no-deps -T \
    --entrypoint python web manage.py serial_only_phase0_audit \
    --include-continuity --strict-serial >"$evidence_dir/production-after.json"
"${production_compose[@]}" exec -T web python manage.py release_preflight \
    --require-family serial >"$evidence_dir/production-preflight.txt"
curl -fsS --retry 5 --retry-delay 2 --retry-all-errors \
    -o /dev/null http://localhost/authentication/login/

finished_epoch=$(date -u +%s)
echo "PHASE0_RECOVERY_BACKUP_RELEASE=$backup_release"
echo "PHASE0_RECOVERY_PROJECT=$restore_project"
echo "PHASE0_RECOVERY_RESTORE_SECONDS=$((finished_epoch - restore_started_epoch))"
echo "PHASE0_RECOVERY_EVIDENCE_DIR=$evidence_dir"
echo "PHASE0_RECOVERY_RESULT=PASS"
