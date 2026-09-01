#!/usr/bin/env bash
set -euo pipefail

gate="${1:?gate required: serial|quantity|isolation|arm64|full}"
compose="docker compose -f deploy/docker-compose.yml"
artifact_dir="${GITHUB_WORKSPACE:-.}/phase27-artifacts/$gate"
mkdir -p "$artifact_dir"
env_backup=$(mktemp)
had_deploy_env=0
if [[ -f deploy/.env ]]; then
  cp deploy/.env "$env_backup"
  had_deploy_env=1
fi

cleanup() {
  $compose logs --no-color >"$artifact_dir/stack.log" 2>&1 || true
  $compose ps --format json >"$artifact_dir/containers.json" 2>&1 || true
  $compose down -v >/dev/null 2>&1 || true
  if [[ "$had_deploy_env" == "1" ]]; then
    cp "$env_backup" deploy/.env
  else
    rm -f deploy/.env
  fi
  rm -f "$env_backup"
}
trap cleanup EXIT

cat > deploy/.env <<'EOF'
SECRET_KEY=phase27-ci-only-not-secret
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee
DB_USER=financee
DB_PASSWORD=ci-postgres-password
DB_HOST=db
DB_PORT=5432
EOF

if [[ "$gate" != "arm64" ]]; then
  $compose build web
fi
$compose up -d
cid=$($compose ps -q web)
for _ in $(seq 1 90); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$cid")
  [[ "$status" == "healthy" ]] && break
  sleep 5
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" == "healthy" ]]
$compose cp tests web:/app/

case "$gate" in
  serial)
    $compose exec -T web python manage.py check
    $compose exec -T web python manage.py makemigrations --check --dry-run
    $compose exec -T web python tests/phase24_serial_matrix.py
    $compose exec -T web python manage.py serial_only_phase0_audit \
      --include-continuity --strict-serial \
      >"$artifact_dir/phase0-single-serial-audit.json"
    $compose exec -T web python manage.py provision_tenant \
      "Phase 0 Audit Second Serial" --inventory-mode serial
    if ! $compose exec -T web python manage.py serial_only_phase0_audit \
        --include-continuity --strict-serial \
        >"$artifact_dir/phase0-serial-only-audit.json"; then
      python3 tests/phase0_serial_only_discovery_contracts.py \
        --assert-known-ci-drift \
        "$artifact_dir/phase0-serial-only-audit.json"
    fi
    ;;
  quantity) $compose exec -T web python tests/suite/test_quantity_complete_suite.py ;;
  isolation) $compose exec -T web python tests/phase25_four_company_isolation.py ;;
  arm64)
    $compose exec -T web python tests/phase27_arm64_smoke.py
    $compose exec -T web python manage.py release_preflight
    ;;
  full)
    $compose exec -T \
      -e DJANGO_SUPERUSER_USERNAME=admin \
      -e DJANGO_SUPERUSER_PASSWORD=ci-admin-password \
      -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
      web python manage.py createsuperuser --noinput
    $compose exec -T web python manage.py provision_tenant "CI Company Two"
    $compose exec -T web python tests/ci_bootstrap.py
    $compose exec -T web python tests/suite/run_all.py
    ;;
  *) echo "unknown gate: $gate" >&2; exit 2 ;;
esac
