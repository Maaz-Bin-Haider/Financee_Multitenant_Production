#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

: "${WEB_IMAGE:?Set WEB_IMAGE to the immutable SHA-tagged release image}"
: "${PHASE30_RELEASE_SHA:?Set PHASE30_RELEASE_SHA to the approved 40-character commit SHA}"
: "${PHASE30_CHANGE_ID:?Set PHASE30_CHANGE_ID to the approved change/window record}"
: "${PHASE30_NOTICE_REFERENCE:?Set PHASE30_NOTICE_REFERENCE to the maintenance notice record}"
: "${PHASE30_MAINTENANCE_WINDOW:?Set PHASE30_MAINTENANCE_WINDOW to the approved UTC window}"
: "${PHASE30_ROLLBACK_OWNER:?Set PHASE30_ROLLBACK_OWNER to the accountable operator}"
: "${BACKUP_DEST:?Set BACKUP_DEST to the off-server backup destination}"
: "${BACKUP_PASSPHRASE_FILE:?Set BACKUP_PASSPHRASE_FILE to the backup secret file}"

[[ "$PHASE30_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] || {
    echo "PHASE30_RELEASE_SHA must be a full lowercase Git SHA" >&2
    exit 2
}
[[ "$WEB_IMAGE" == *":$PHASE30_RELEASE_SHA" ]] || {
    echo "WEB_IMAGE must be pinned to PHASE30_RELEASE_SHA" >&2
    exit 2
}
[[ "$(git -C .. rev-parse HEAD)" == "$PHASE30_RELEASE_SHA" ]] || {
    echo "Checked-out source does not match PHASE30_RELEASE_SHA" >&2
    exit 2
}

evidence_dir="${PHASE30_EVIDENCE_DIR:-phase30-evidence/$PHASE30_RELEASE_SHA}"
mkdir -p "$evidence_dir"
evidence_dir=$(cd "$evidence_dir" && pwd)
compose=(docker compose -f docker-compose.yml)
if [[ -f /etc/nginx/cloudflare/origin.pem && -f docker-compose.tls.yml ]]; then
    compose+=(-f docker-compose.tls.yml)
fi

previous_container=$("${compose[@]}" ps -q web | head -1 || true)
previous_image=""
if [[ -n "$previous_container" ]]; then
    previous_image=$(docker inspect -f '{{.Config.Image}}' "$previous_container")
fi
deployment_started=0
completed=0

rollback() {
    local status=$?
    if [[ "$deployment_started" == "1" && "$completed" != "1" && -n "$previous_image" ]]; then
        {
            echo "phase=30"
            echo "change_id=$PHASE30_CHANGE_ID"
            echo "failed_release=$WEB_IMAGE"
            echo "rollback_image=$previous_image"
            echo "rollback_owner=$PHASE30_ROLLBACK_OWNER"
            echo "trigger_exit_status=$status"
            echo "triggered_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        } >"$evidence_dir/rollback-incident.txt"
        echo "!! Phase 30 gate failed; rolling web back to $previous_image"
        WEB_IMAGE="$previous_image" "${compose[@]}" up -d --no-deps web nginx
        curl -fsS --retry 20 --retry-delay 3 \
            -o /dev/null http://localhost/authentication/login/
    fi
    exit "$status"
}
trap rollback EXIT

cat >"$evidence_dir/change-control.txt" <<EOF
phase=30
release_sha=$PHASE30_RELEASE_SHA
release_image=$WEB_IMAGE
previous_image=${previous_image:-none}
change_id=$PHASE30_CHANGE_ID
notice_reference=$PHASE30_NOTICE_REFERENCE
maintenance_window=$PHASE30_MAINTENANCE_WINDOW
rollback_owner=$PHASE30_ROLLBACK_OWNER
max_http_latency_seconds=${PHASE30_MAX_HTTP_LATENCY_SECONDS:-5}
max_db_connections=${PHASE30_MAX_DB_CONNECTIONS:-100}
max_5xx=${PHASE30_MAX_5XX:-0}
max_container_cpu_percent=${PHASE30_MAX_CONTAINER_CPU_PERCENT:-90}
max_container_memory_percent=${PHASE30_MAX_CONTAINER_MEMORY_PERCENT:-90}
started_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo "==> Phase 30 preflight: serial-only production foundation"
"${compose[@]}" exec -T web python manage.py release_preflight \
    --require-family serial >"$evidence_dir/preflight-before.txt"
"${compose[@]}" exec -T web python manage.py production_foundation_audit \
    --serial-only --json >"$evidence_dir/continuity-before.json"

echo "==> Creating encrypted off-server restore point"
BACKUP_DEST="$BACKUP_DEST" \
BACKUP_PASSPHRASE_FILE="$BACKUP_PASSPHRASE_FILE" \
    bash backup_encrypted.sh | tee "$evidence_dir/backup.txt"
backup_path=$(sed -n 's/^BACKUP_PATH=//p' "$evidence_dir/backup.txt")
[[ -n "$backup_path" && -s "$backup_path" && -s "$backup_path.sha256" ]]
(
    cd "$(dirname "$backup_path")"
    sha256sum -c "$(basename "$backup_path").sha256"
) >"$evidence_dir/backup-integrity.txt"

echo "==> Deploying approved foundation release"
deployment_started=1
deploy_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
WEB_IMAGE="$WEB_IMAGE" bash deploy_pull.sh | tee "$evidence_dir/deploy.txt"

echo "==> Comparing all tenant balances and continuity fingerprints"
"${compose[@]}" cp "$evidence_dir/continuity-before.json" \
    web:/tmp/phase30-continuity-before.json
"${compose[@]}" exec -T web python manage.py production_foundation_audit \
    --serial-only --compare /tmp/phase30-continuity-before.json --json \
    >"$evidence_dir/continuity-after.json"

echo "==> Capturing operational thresholds"
latency=$(curl -fsS -o /dev/null -w '%{time_total}' \
    http://localhost/authentication/login/)
db_connections=$("${compose[@]}" exec -T db psql \
    -U "${DB_USER:-financee}" -d "${DB_NAME:-financee}" -Atc \
    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()")
docker_root=$(docker info --format '{{.DockerRootDir}}')
available_kb=$(df -Pk "$docker_root" | awk 'NR == 2 {print $4}')
http_5xx=$("${compose[@]}" logs --since "$deploy_started_at" nginx 2>&1 |
    awk '$0 ~ /" [5][0-9][0-9] / {count++} END {print count+0}')
"${compose[@]}" ps --format json >"$evidence_dir/containers.json"
mapfile -t phase30_container_ids < <("${compose[@]}" ps -q)
docker stats --no-stream "${phase30_container_ids[@]}" \
    >"$evidence_dir/docker-stats.txt"
docker stats --no-stream --format '{{json .}}' "${phase30_container_ids[@]}" \
    >"$evidence_dir/docker-stats.jsonl"
"${compose[@]}" logs --since "$deploy_started_at" --no-color \
    >"$evidence_dir/post-deploy.log" 2>&1

python3 - "$latency" "$db_connections" "$available_kb" "$http_5xx" \
    "${PHASE30_MAX_HTTP_LATENCY_SECONDS:-5}" \
    "${PHASE30_MAX_DB_CONNECTIONS:-100}" \
    "${PHASE30_MIN_AVAILABLE_KB:-1048576}" \
    "${PHASE30_MAX_5XX:-0}" \
    "$evidence_dir/docker-stats.jsonl" \
    "${PHASE30_MAX_CONTAINER_CPU_PERCENT:-90}" \
    "${PHASE30_MAX_CONTAINER_MEMORY_PERCENT:-90}" \
    >"$evidence_dir/monitoring.json" <<'PY'
import json
import sys

latency, connections, disk, errors, max_latency, max_connections, min_disk, max_errors = (
    float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]),
    float(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8]),
)
stats_path, max_cpu, max_memory = sys.argv[9], float(sys.argv[10]), float(sys.argv[11])
with open(stats_path, encoding="utf-8") as handle:
    container_stats = [json.loads(line) for line in handle if line.strip()]

def percent(row, key):
    return float(row[key].rstrip("%"))

peak_cpu = max((percent(row, "CPUPerc") for row in container_stats), default=0)
peak_memory = max((percent(row, "MemPerc") for row in container_stats), default=0)
checks = {
    "http_latency": latency <= max_latency,
    "database_connections": connections <= max_connections,
    "available_disk": disk >= min_disk,
    "http_5xx": errors <= max_errors,
    "container_cpu": peak_cpu <= max_cpu,
    "container_memory": peak_memory <= max_memory,
}
print(json.dumps({
    "values": {
        "http_latency_seconds": latency,
        "database_connections": connections,
        "available_disk_kb": disk,
        "http_5xx": errors,
        "peak_container_cpu_percent": peak_cpu,
        "peak_container_memory_percent": peak_memory,
    },
    "thresholds": {
        "max_http_latency_seconds": max_latency,
        "max_database_connections": max_connections,
        "min_available_disk_kb": min_disk,
        "max_http_5xx": max_errors,
        "max_container_cpu_percent": max_cpu,
        "max_container_memory_percent": max_memory,
    },
    "checks": checks,
    "ok": all(checks.values()),
}, indent=2, sort_keys=True))
raise SystemExit(0 if all(checks.values()) else 1)
PY

completed=1
trap - EXIT
echo "completed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    >>"$evidence_dir/change-control.txt"
echo "Phase 30 production foundation deployment PASS"
