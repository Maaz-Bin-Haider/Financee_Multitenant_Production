# =============================================================================
# Dockerfile  —  Financee Django + Gunicorn image
# -----------------------------------------------------------------------------
# Key design point for the STATIC-CACHE fix:
#   `collectstatic` runs at BUILD time, so every image contains a freshly
#   hashed static tree AND a fresh staticfiles.json manifest. Because the
#   filenames are content-hashed, a changed CSS/JS file gets a NEW name on the
#   next build, the {% static %} tag emits that new name, and browsers fetch it
#   automatically — no hard refresh, no cache clearing, ever.
#
#   collectstatic with ManifestStaticFilesStorage does NOT touch the database,
#   so we run it with a throwaway SECRET_KEY and DEBUG=False at build time.
# =============================================================================

# ---- base ----
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# psycopg2-binary needs libpq at runtime; build tools only while installing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- python deps (cached layer) ----
COPY requirements.txt requirements-lock.txt* ./
# Pin Django to the version the code targets and add the production server +
# whitenoise fallback (optional) explicitly. requirements.txt currently leaves
# Django unpinned — pin it in your repo to avoid surprise upgrades.
RUN if [ -f requirements-lock.txt ]; then pip install -r requirements-lock.txt; else pip install -r requirements.txt; fi

# ---- app ----
COPY . .

# ---- collectstatic (bakes hashed names + manifest) ----
# Use a dummy key so settings import succeeds; DEBUG=False so the Manifest
# backend produces hashed files. No DB connection is made.
RUN SECRET_KEY="build-time-dummy-not-used-at-runtime" \
    DEBUG=False \
    DB_NAME=x DB_USER=x DB_PASSWORD=x DB_HOST=x DB_PORT=5432 \
    python manage.py collectstatic --no-input --clear \
    # Keep an immutable copy OUTSIDE the eventual volume mount point so the
    # entrypoint can refresh the shared `staticfiles` volume on every deploy
    # (named volumes are only seeded from the image on first creation).
    && cp -a /app/staticfiles /app/static_build

# ---- runtime ----
# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# entrypoint waits for DB, migrates public schema, then launches Gunicorn.
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "financee.wsgi:application", "-c", "/app/deploy/gunicorn.conf.py"]
