"""
gunicorn.conf.py
================
Production Gunicorn configuration for the Financee multi-tenant ERP.

WORKER MODEL — why gthread / sync and NOT gevent
------------------------------------------------
Tenant isolation is enforced by `SET search_path` on the *current request's*
database connection (see tenancy/middleware.py). That is safe only when a
connection is never shared between two requests that are in flight at the same
time.

  * sync workers     : one request at a time per worker  -> safe.
  * gthread workers  : Django connections are THREAD-LOCAL, so each worker
                       thread gets its own connection and its own search_path
                       -> safe.
  * gevent/eventlet  : many greenlets share one OS thread and could interleave
                       on the SAME connection mid-request -> a tenant could read
                       another tenant's data. DO NOT USE without first refactoring
                       the app to set search_path per-transaction.

We use gthread: it gives I/O concurrency (the dashboard fires ~15 parallel API
calls per page) while staying leak-safe.

SIZING
------
Tune `workers` to the box. Rule of thumb for gthread on a CPU where Postgres
runs on the SAME host (so leave headroom for the DB):
    workers = (2 * vCPU) ... but cap so workers*threads*~25MB fits in RAM and
    workers stay well under Postgres max_connections.
Override at runtime with env vars WEB_CONCURRENCY / GUNICORN_THREADS.
"""
import multiprocessing
import os

# --- socket -----------------------------------------------------------------
# Bind to a TCP port that Nginx proxies to. In docker-compose the service name
# "web" resolves to this container; Nginx upstreams to web:8000.
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# --- workers ----------------------------------------------------------------
worker_class = "gthread"

# Default: 2 x vCPU, but allow explicit override. On a 2-vCPU box this is 4
# workers; on 4-vCPU, 8. Keep workers*threads below Postgres max_connections.
_default_workers = max(2, multiprocessing.cpu_count() * 2)
workers = int(os.environ.get("WEB_CONCURRENCY", _default_workers))
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# --- robustness -------------------------------------------------------------
# Recycle workers periodically to bound memory growth / leaked cursors.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = 100

# Reporting / PDF generation can be slow; allow a generous but bounded timeout.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
keepalive = 5

# --- logging ----------------------------------------------------------------
accesslog = "-"   # stdout -> captured by docker logs
errorlog = "-"    # stderr
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
# Add request time (%(D)s = microseconds) so slow endpoints are visible.
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sus'

# --- preload ----------------------------------------------------------------
# Load app once in the master and fork -> lower memory, faster boot. Safe here
# because no DB connection is opened at import time.
preload_app = True
