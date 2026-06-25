# =============================================================================
# settings_production_patch.py
# -----------------------------------------------------------------------------
# These are the changes to merge into financee/settings.py for a safe production
# deployment. They are shown as a diff-style block; apply them in your repo.
# Nothing here changes business behaviour — it hardens the deployment and makes
# the per-request tenancy model behave correctly behind Nginx.
# =============================================================================

# --- 1. Hosts / CSRF (replace ALLOWED_HOSTS = ['*']) -------------------------
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- 2. Behind the Nginx TLS terminator -------------------------------------
# Nginx forwards X-Forwarded-Proto; this lets Django know the request was HTTPS
# so secure cookies and request.is_secure() work correctly.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# --- 3. Persistent DB connections -------------------------------------------
# Reuse connections for ~60s instead of opening a new one per request. Safe with
# the tenancy middleware because the start-of-request SET search_path overwrites
# any stale value before a single query runs. Big win given the dashboard's
# ~15-call fan-out. Keep workers*threads below Postgres max_connections.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# --- 4. Production security flags (only enforce when DEBUG is off) -----------
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)  # True once HTTPS is on
    # Enable HSTS only after HTTPS is confirmed working end-to-end:
    # SECURE_HSTS_SECONDS = 31536000
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_HSTS_PRELOAD = True

# --- 5. Logging to stdout/stderr (captured by `docker logs`) ----------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        # Surface the DB errors that the views' bare `except:` blocks swallow:
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# --- 6. (OPTIONAL, later) Redis cache + cached sessions ---------------------
# Not required at 50 tenants / 750 users. Add only if you introduce real caching
# (e.g. memoizing expensive report functions) or move sessions out of the DB.
# CACHES = {"default": {
#     "BACKEND": "django.core.cache.backends.redis.RedisCache",
#     "LOCATION": env("REDIS_URL", default="redis://redis:6379/0"),
# }}
# SESSION_ENGINE = "django.contrib.sessions.backends.cache"
