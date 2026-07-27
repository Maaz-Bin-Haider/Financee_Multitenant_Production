#!/usr/bin/env bash
set -euo pipefail

# Phase 29 production-like staging acceptance.
# The source image is built exactly once, pinned by source revision, and every
# acceptance command runs in that same container image.

root_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root_dir"

source_revision="${GITHUB_SHA:-$(git rev-parse HEAD)}"
short_revision="${source_revision:0:12}"
image="${PHASE29_IMAGE:-financee-phase29-staging:${source_revision}}"
project="${PHASE29_COMPOSE_PROJECT:-financee_phase29_${GITHUB_RUN_ID:-$$}}"
artifact_dir="${PHASE29_ARTIFACT_DIR:-phase29-artifacts}"
compose=(docker compose -p "$project" -f deploy/docker-compose.yml)
env_backup=$(mktemp)
had_deploy_env=0

mkdir -p "$artifact_dir"
if [[ -f deploy/.env ]]; then
  cp deploy/.env "$env_backup"
  had_deploy_env=1
fi

cleanup() {
  "${compose[@]}" logs --no-color >"$artifact_dir/staging-stack.log" 2>&1 || true
  "${compose[@]}" ps --format json >"$artifact_dir/staging-containers.json" 2>&1 || true
  "${compose[@]}" down -v >/dev/null 2>&1 || true
  if [[ "$had_deploy_env" == "1" ]]; then
    cp "$env_backup" deploy/.env
  else
    rm -f deploy/.env
  fi
  rm -f "$env_backup"
}
trap cleanup EXIT

cat >deploy/.env <<'EOF'
SECRET_KEY=phase29-staging-only-not-secret
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
SECURE_COOKIES=False
DB_NAME=financee
DB_USER=financee
DB_PASSWORD=phase29-postgres-password
DB_HOST=db
DB_PORT=5432
WEB_CONCURRENCY=2
GUNICORN_THREADS=2
EOF

echo "==> Building immutable Phase 29 staging image ${image}"
docker build -f deploy/Dockerfile \
  --label "org.opencontainers.image.revision=${source_revision}" \
  -t "$image" .
expected_image_id=$(docker image inspect -f '{{.Id}}' "$image")

echo "==> Starting isolated production-like staging services"
WEB_IMAGE="$image" "${compose[@]}" up -d db redis web
web_id=$("${compose[@]}" ps -q web)
for _ in $(seq 1 90); do
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$web_id")
  [[ "$health" == "healthy" ]] && break
  sleep 5
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$web_id")" == "healthy" ]]

running_image_id=$(docker inspect -f '{{.Image}}' "$web_id")
[[ "$running_image_id" == "$expected_image_id" ]]
image_revision=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
[[ "$image_revision" == "$source_revision" ]]

cat >"$artifact_dir/image-provenance.json" <<EOF
{
  "source_revision": "${source_revision}",
  "short_revision": "${short_revision}",
  "image": "${image}",
  "image_id": "${expected_image_id}",
  "running_image_id": "${running_image_id}",
  "result": "PASS"
}
EOF

run_gate() {
  local name=$1
  shift
  echo "==> ${name}"
  "$@" 2>&1 | tee "$artifact_dir/${name}.log"
}

run_gate release-preflight \
  "${compose[@]}" exec -T web python manage.py release_preflight
run_gate security-runtime \
  "${compose[@]}" exec -T web python -m unittest tests.test_hardening
run_gate serial-t4-t5 \
  "${compose[@]}" exec -T web python tests/phase24_serial_matrix.py
run_gate quantity-t4-t5-uat \
  "${compose[@]}" exec -T web python tests/suite/test_quantity_complete_suite.py
run_gate mixed-family-t6-security \
  "${compose[@]}" exec -T web python tests/phase25_four_company_isolation.py
run_gate selected-t7-smoke \
  "${compose[@]}" exec -T web python tests/phase26_performance_capacity.py \
    --profile smoke --output /tmp/phase29-t7.json
"${compose[@]}" cp web:/tmp/phase29-t7.json "$artifact_dir/phase29-t7.json"

run_gate final-release-preflight \
  "${compose[@]}" exec -T web python manage.py release_preflight
run_gate redis-health \
  "${compose[@]}" exec -T redis redis-cli ping

python3 - "$artifact_dir/acceptance-summary.json" "$source_revision" <<'PY'
import json
import sys
from datetime import datetime, timezone

path, revision = sys.argv[1:]
payload = {
    "phase": 29,
    "source_revision": revision,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "data_classification": "synthetic-sanitized",
    "coverage": {
        "T4_serial": "PASS",
        "T5_quantity": "PASS",
        "T6_mixed_family_isolation": "PASS",
        "T7_selected_smoke": "PASS",
        "T8_encrypted_recovery": "enforced-by-recovery-gate",
        "tenant_auth_security": "PASS",
        "wholesaler_workflow_and_reports": "PASS",
        "monitoring_health": "PASS",
    },
    "result": "PASS",
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
PY

echo "Phase 29 staging acceptance PASS (${short_revision})"
