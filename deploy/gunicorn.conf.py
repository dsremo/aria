# Gunicorn configuration for ARIA workers.
#
# Wires the autonomy / security audit follow-ups:
#   * Per-worker internal-channel token mint via worker_init.boot_worker.
#   * Graceful-shutdown flush of replay-defence + F-19 counter state.
#
# Usage:
#   gunicorn --config deploy/gunicorn.conf.py aria.simulator.web_dashboard:app
#
# Tune ``workers`` to your traffic profile.  Each worker is sandboxed
# by the seccomp profile + cap_drop ALL in deploy/screener/docker-compose.yml.

import multiprocessing

# Bind only to the loopback in production — Caddy fronts the service
# (deploy/screener/docker-compose.yml).  An explicit private interface
# is the second safest choice; ``0.0.0.0`` is refused by
# aria.security.guard.runtime_check_environment in production mode.
bind = "127.0.0.1:8090"

# Worker model: synchronous workers are fine for the autonomy
# dashboard which is mostly aiohttp-driven.  ``gevent``/``uvicorn``
# variants are supported but require their own per-worker hook.
workers = max(2, multiprocessing.cpu_count() // 2)
worker_class = "sync"

# Long requests (NDJSON streaming, screen_bulk) need a generous
# timeout but short-circuit at the asyncio.wait_for(2.0) level inside
# the screener.  Match the proxy's read_timeout from the Caddyfile.
timeout = 60
graceful_timeout = 30
keepalive = 5

# Resource hardening — the seccomp profile + cap_drop already cover
# most of this in containers; here we cap the worker memory + lifecycle.
max_requests = 10000
max_requests_jitter = 500

# Autonomy audit F6 — per-worker internal-channel token mint.
# This wires aria.security.worker_init.boot_worker into gunicorn's
# post-fork hook so each worker holds its own token.
from aria.security.worker_init import gunicorn_post_fork as post_fork    # noqa: F401, E402

# Logging via structlog goes to stdout; gunicorn's access log mirrors
# the same redaction the Caddyfile applies (Authorization, X-ARIA-*).
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" trace=%({x-trace-id}o)s'
)


def on_exit(server) -> None:
    """Graceful-shutdown flush — run once when the master exits."""
    from aria.security.worker_init import graceful_shutdown_flush
    graceful_shutdown_flush()
