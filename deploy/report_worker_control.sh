#!/usr/bin/env bash
# Only production/default Compose. Review stacks use their standalone helper.
set -euo pipefail
cd "$(dirname "$0")"
action=${1:?Use stop/start/restore/health}
compose=(docker compose -f docker-compose.yml)
if [[ -f /etc/nginx/cloudflare/origin.pem && -f docker-compose.tls.yml ]]; then
    compose+=(-f docker-compose.tls.yml)
fi
if [[ "$action" == stop ]]; then
    "${compose[@]}" stop report_worker
    exit
fi
if [[ "$action" == health ]]; then
    worker=$("${compose[@]}" ps -q report_worker)
    web=$("${compose[@]}" ps -q web)
    [[ -n "$worker" && -n "$web" ]]
    [[ "$(docker inspect -f '{{.Image}}' "$worker")" == "$(docker inspect -f '{{.Image}}' "$web")" ]]
    [[ "$(docker inspect -f '{{.State.Health.Status}}' "$worker")" == healthy ]]
    exit
fi
[[ "$action" == start || "$action" == restore ]] || exit 2
: "${WEB_IMAGE:?Pin worker to the web release image}"
"${compose[@]}" stop report_worker
# Old images have no worker command: leave it stopped during rollback. Check
# files with networking disabled, without importing settings or touching DB.
if docker run --rm --network none --entrypoint python "$WEB_IMAGE" -c \
    'from pathlib import Path; import sys; sys.exit(0 if Path("/app/reportmailer/management/commands/run_report_scheduler.py").is_file() else 1)'; then
    WEB_IMAGE="$WEB_IMAGE" "${compose[@]}" up -d --no-deps --wait --wait-timeout 150 report_worker
    bash report_worker_control.sh health
elif [[ "$action" == start ]]; then
    echo 'Candidate image lacks the report worker command.' >&2
    exit 1
else
    echo 'Rollback image predates report emails; worker remains stopped.'
fi
