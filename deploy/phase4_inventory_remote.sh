#!/usr/bin/env bash
# Read-only Phase 4 entry inspection. Audited Python arrives through stdin from
# the exact workflow commit; no checkout, image, container, or database changes.
set -euo pipefail

fail() {
    echo "Phase 4 entry inspection stopped: $1" >&2
    exit 1
}

app_dir=${1?app directory argument required (may be empty for the existing default)}
expected_deployed_sha=${2:?expected deployed SHA required}
audit_source_sha=${3:?audit source SHA required}
[[ "$expected_deployed_sha" =~ ^[0-9a-f]{40}$ ]] || fail 'invalid deployed SHA'
[[ "$audit_source_sha" =~ ^[0-9a-f]{40}$ ]] || fail 'invalid source SHA'
app_dir="${app_dir:-$HOME/Financee_Multitenant_Production}"
[[ "$app_dir" == /* && -d "$app_dir/deploy" ]] || fail 'application directory is unavailable'
cd "$app_dir/deploy"

compose=(sudo -n docker compose -f docker-compose.yml)
if [[ -f docker-compose.tls.yml ]]; then
    compose+=(-f docker-compose.tls.yml)
fi
web_id=$("${compose[@]}" ps -q web)
[[ "$web_id" =~ ^[0-9a-f]{64}$ ]] || fail 'expected exactly one running web container'
expected_image="ghcr.io/maaz-bin-haider/financee-web:$expected_deployed_sha"
actual_image=$(sudo -n docker inspect --format '{{.Config.Image}}' "$web_id")
[[ "$actual_image" == "$expected_image" ]] || fail 'deployed image mismatch'
[[ "$(sudo -n docker inspect --format '{{.State.Health.Status}}' "$web_id")" == healthy ]] || fail 'web is not healthy'
image_id=$(sudo -n docker inspect --format '{{.Image}}' "$web_id")
[[ "$(sudo -n docker image inspect --format '{{.Architecture}}' "$image_id")" == arm64 ]] || fail 'image is not ARM64'
printf 'PHASE4_AUDIT_SOURCE_SHA=%s\nPHASE4_DEPLOYED_SHA=%s\n' "$audit_source_sha" "$expected_deployed_sha"

audit_status=0
"${compose[@]}" exec -T -e 'PGOPTIONS=-c default_transaction_read_only=on' \
    web python - --strict || audit_status=$?

continuity_status=0
"${compose[@]}" exec -T -e 'PGOPTIONS=-c default_transaction_read_only=on' \
    web python manage.py serial_only_phase0_audit --include-continuity \
    --strict-serial || continuity_status=$?

[[ "$("${compose[@]}" ps -q web)" == "$web_id" ]] || fail 'web container changed during inspection'
[[ "$(sudo -n docker inspect --format '{{.Image}}' "$web_id")" == "$image_id" ]] || fail 'web image changed during inspection'
[[ "$(sudo -n docker inspect --format '{{.State.Health.Status}}' "$web_id")" == healthy ]] || fail 'web is not healthy after inspection'
echo 'PHASE4_PRODUCTION_CONTAINER_UNCHANGED=yes'
if [[ "$audit_status" != 0 || "$continuity_status" != 0 ]]; then
    echo 'PHASE4_ENTRY_RESULT=REVIEW_REQUIRED'
    exit 1
fi
echo 'PHASE4_ENTRY_RESULT=PASS'
echo 'PHASE4_REPLACEMENT_AUTHORIZED=no'
