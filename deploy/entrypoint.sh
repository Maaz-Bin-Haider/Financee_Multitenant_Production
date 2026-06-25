#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh
# -----------------------------------------------------------------------------
# Runs every time the web container starts:
#   1. Wait for PostgreSQL to accept connections.
#   2. Apply Django migrations to the SHARED public schema (auth, sessions,
#      tenancy_company, tenancy_membership). Business tables live in tenant
#      schemas and are NOT managed by Django migrate — see apply_sql_all_tenants.
#   3. Hand off (exec) to the CMD (Gunicorn).
#
# NOTE: collectstatic is intentionally NOT here — it already ran at image build
# so the hashed static tree + manifest are baked into the image.
# =============================================================================
set -euo pipefail

echo "[entrypoint] waiting for database ${DB_HOST}:${DB_PORT} ..."
until python - <<'PY' 2>/dev/null
import os, sys, psycopg2
try:
    psycopg2.connect(
        dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"], host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"], connect_timeout=3,
    ).close()
except Exception:
    sys.exit(1)
PY
do
    echo "[entrypoint] database not ready, retrying in 2s ..."
    sleep 2
done
echo "[entrypoint] database is up."

# Refresh the shared static volume with THIS image's freshly hashed files.
# (A named volume persists across deploys and would otherwise keep serving the
# previous build's hashes — the very staleness we are eliminating.)
if [ -d /app/static_build ]; then
    echo "[entrypoint] syncing baked static into the shared volume ..."
    cp -a /app/static_build/. /app/staticfiles/ 2>/dev/null || true
fi

echo "[entrypoint] applying public-schema migrations ..."
python manage.py migrate --no-input

# OPTIONAL: keep every tenant schema in sync with pending idempotent SQL on each
# deploy. Uncomment once you have a change file to roll out (e.g. indexes).
# python manage.py apply_sql_all_tenants tenancy/sql/tenant_indexes.sql || true

echo "[entrypoint] starting: $*"
exec "$@"
