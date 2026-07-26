#!/usr/bin/env bash
# =============================================================================
# deploy_pull.sh  —  registry-pull deploy on the EC2 host (used by CI/CD).
# -----------------------------------------------------------------------------
# Deploys the EXACT image that passed the test suite in GitHub Actions instead
# of rebuilding on the server (deploy.sh remains as the manual build-on-server
# fallback). Invoked by the workflow as:
#
#     WEB_IMAGE=ghcr.io/maaz-bin-haider/financee-web:<sha> ./deploy_pull.sh
#
# Steps:
#   1. Reclaim unused image/build-cache space, then pull the pinned image
#      (repo files — compose/nginx/tenant SQL — were
#      already git-pulled by the caller; run `git pull --ff-only` first when
#      invoking by hand).
#   2. Recreate web (+ nginx if its config changed). Nginx needs no restart
#      for a new web IP thanks to the resolver fix in nginx/financee.conf.
#      The web entrypoint applies public migrations + production_hardening.sql.
#   3. Health-check through nginx; on failure ROLL BACK web to the previous
#      image. (DB note: migrations already applied by the failed release are
#      NOT reverted — keep migrations/tenant SQL backward-compatible, which is
#      the existing idempotent-patch discipline.)
#   4. Apply idempotent tenant SQL to every tenant schema (anti-drift).
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose -f docker-compose.yml"
# Enable the Cloudflare TLS overlay automatically once the origin cert is on the
# host. Before that, deploys stay HTTP-only (no broken nginx, no flag day); the
# moment /etc/nginx/cloudflare/origin.pem exists, nginx comes up on 443 too.
if [ -f /etc/nginx/cloudflare/origin.pem ] && [ -f docker-compose.tls.yml ]; then
    COMPOSE="$COMPOSE -f docker-compose.tls.yml"
    echo "==> TLS overlay active (Cloudflare origin cert found)"
fi
: "${WEB_IMAGE:?Set WEB_IMAGE to the image tag to deploy (e.g. ghcr.io/maaz-bin-haider/financee-web:<sha>)}"
export WEB_IMAGE

PREV_CID=$($COMPOSE ps -q web | head -1 || true)
PREV_IMAGE=""
if [ -n "$PREV_CID" ]; then
    PREV_IMAGE=$(docker inspect -f '{{.Image}}' "$PREV_CID" || true)
fi
echo "==> Deploying $WEB_IMAGE (previous image: ${PREV_IMAGE:-none})"

# SHA-tagged releases are not dangling, so `docker image prune -f` never
# removed them. On a small EC2 root volume they accumulated until containerd
# could no longer extract the next ARM64 image. `-a` removes every image not
# referenced by a container; the currently running web image (our rollback
# target) is therefore retained. Volumes are deliberately never pruned.
echo "==> Docker disk usage before cleanup"
docker system df || true
echo "==> Reclaiming unused images and build cache (volumes are preserved)"
docker image prune -af
docker builder prune -af

DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}')
AVAILABLE_KB=$(df -Pk "$DOCKER_ROOT" | awk 'NR == 2 {print $4}')
MIN_AVAILABLE_KB=1048576
if [ -z "$AVAILABLE_KB" ] || [ "$AVAILABLE_KB" -lt "$MIN_AVAILABLE_KB" ]; then
    echo "!! Less than 1 GiB is free under $DOCKER_ROOT after safe cleanup."
    echo "!! Expand the EC2 root EBS volume or inspect large non-Docker files."
    df -h "$DOCKER_ROOT" || true
    exit 1
fi

echo "==> Pulling image"
$COMPOSE pull web

echo "==> Ensuring db + redis are up"
$COMPOSE up -d db redis

echo "==> Recreating web + nginx"
$COMPOSE up -d --no-deps web nginx

echo "==> Waiting for health through nginx"
healthy=""
for i in $(seq 1 30); do
    if curl -fsS -o /dev/null http://localhost/authentication/login/; then
        healthy=1
        break
    fi
    sleep 4
done

if [ -z "$healthy" ]; then
    echo "!! Health check FAILED after 120s"
    $COMPOSE logs --tail=100 web || true
    if [ -n "$PREV_IMAGE" ]; then
        echo "==> Rolling web back to previous image $PREV_IMAGE"
        WEB_IMAGE="$PREV_IMAGE" $COMPOSE up -d --no-deps web
    fi
    exit 1
fi

echo "==> Applying tenant SQL to all schemas (idempotent)"
$COMPOSE exec -T web python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql

echo "==> Pruning superseded images and build cache"
docker image prune -af
docker builder prune -af

echo "==> Deploy complete."
$COMPOSE ps
