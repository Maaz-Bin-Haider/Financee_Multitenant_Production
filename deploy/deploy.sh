#!/usr/bin/env bash
# =============================================================================
# deploy.sh  —  pull, rebuild, and roll out on the EC2 host.
# -----------------------------------------------------------------------------
# Run from the deploy/ directory:  ./deploy.sh
#
# Each deploy:
#   1. Pulls the latest code.
#   2. Rebuilds the web image  -> collectstatic re-hashes changed CSS/JS and
#      regenerates staticfiles.json. New content => new filenames.
#   3. Recreates containers; entrypoint refreshes the shared static volume,
#      then runs public-schema migrations.
#   4. Applies any pending idempotent tenant SQL to EVERY tenant schema
#      (keeps the 50 schemas from drifting apart).
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# Use ONLY the base compose file on the server (ignore any local-dev override
# that may exist in the repo, which shrinks Postgres and exposes the DB port).
COMPOSE="docker compose -f docker-compose.yml"

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building images (re-hashes static)"
$COMPOSE build

echo "==> Starting database"
$COMPOSE up -d db

echo "==> Recreating app + nginx"
$COMPOSE up -d --no-deps web nginx

echo "==> Waiting for web health"
sleep 5

echo "==> Public-schema migrations (idempotent)"
$COMPOSE exec -T web python manage.py migrate --no-input

# ---- tenant business-schema changes -----------------------------------------
# Roll out index / function / table changes to all existing tenant schemas.
# Safe to run every deploy because the scripts use IF NOT EXISTS / OR REPLACE.
echo "==> Applying tenant SQL to all schemas"
$COMPOSE exec -T web python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql

echo "==> Pruning old images"
docker image prune -f

echo "==> Deploy complete."
$COMPOSE ps
