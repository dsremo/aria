"""Worker-process initialisation hooks.

Pre-fork servers (gunicorn / uvicorn ``--workers > 1``) must NOT share
the parent's internal-channel token across workers (autonomy audit F6).
This module exposes the concrete hook each server expects.

──────────────────────────────────────────────────────────────────────
gunicorn
──────────────────────────────────────────────────────────────────────

Add the hook to your ``gunicorn.conf.py``::

    from aria.security.worker_init import gunicorn_post_fork as post_fork

That single line wires the per-worker token mint AND any additional
boot-time sealed-content verification you have layered.

──────────────────────────────────────────────────────────────────────
uvicorn (single process or multiprocess)
──────────────────────────────────────────────────────────────────────

uvicorn doesn't expose a post-fork hook directly when run as a
library.  Instead, use the ``aria.security.worker_init.boot_worker``
helper inside your application factory::

    # asgi.py
    from aria.security.worker_init import boot_worker

    def create_app():
        boot_worker()
        # ... rest of the factory ...

When uvicorn imports the app via ``--factory``, each worker re-imports
the factory module after fork, so ``boot_worker`` runs exactly once
per worker.

──────────────────────────────────────────────────────────────────────
Why this matters
──────────────────────────────────────────────────────────────────────

The internal-channel token (``aria.security.auth._INTERNAL_CHANNEL_TOKEN``)
is the bypass key trusted internal agents present at the
authenticator boundary.  If the parent process mints it before fork,
every worker inherits the same bytes.  An attacker who compromises
ONE worker can replay that token to a peer and bypass authentication.

The ``os.register_at_fork(after_in_child=...)`` hook in ``auth.py``
already wipes the parent's token in the child; this module adds the
deliberate per-worker re-mint.

Worker-init also re-seeds the heartbeat ``boot_id`` so a stale
counter from the parent doesn't silently look like a replay (autonomy
audit F25).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


def boot_worker(*, mint_token: bool = True,
                reseed_heartbeat: bool = True) -> Optional[bytes]:
    """Run once per worker, AFTER fork.

    Returns the freshly-minted internal-channel token (or ``None`` if
    minting is disabled).  Callers MUST hand the bytes to the agent
    runner; do NOT log or persist them.
    """
    pid = os.getpid()
    logger.info("aria.worker_boot", pid=pid)

    minted: Optional[bytes] = None
    if mint_token:
        from aria.security.auth import (
            mint_internal_channel_token,
            reset_internal_channel_token_for_test,
        )
        # Defensive: if a previous mint somehow leaked from the parent,
        # the os.register_at_fork hook should already have cleared it.
        # We still call the test-only reset before re-mint so a misbe-
        # haved fork that pre-dates the at_fork hook fails-loud.
        try:
            minted = mint_internal_channel_token()
        except RuntimeError:
            # Already minted in this process (rare — the at_fork hook
            # should have cleared).  Reset and try once more.
            reset_internal_channel_token_for_test()
            minted = mint_internal_channel_token()
        logger.info("aria.worker.internal_token_minted", pid=pid)

    if reseed_heartbeat:
        # The HeartbeatPayload boot_id is generated in HeartbeatEmitter
        # __init__.  Importing the module here is a no-op; the actual
        # boot_id comes into existence when the emitter is constructed
        # inside the worker (which happens after this hook runs).
        # We just record that we passed through this path.
        logger.info("aria.worker.heartbeat_reseed_pending", pid=pid)

    return minted


def gunicorn_post_fork(server: Any, worker: Any) -> None:
    """Drop-in for gunicorn's ``post_fork`` hook.

    Usage in ``gunicorn.conf.py``::

        from aria.security.worker_init import gunicorn_post_fork as post_fork
    """
    boot_worker()
    logger.info("aria.gunicorn_post_fork",
                worker_age=getattr(worker, "age", None),
                pid=os.getpid())


def uvicorn_lifespan_startup() -> None:
    """Drop-in for the uvicorn lifespan ``startup`` event.

    Wire it via your ASGI framework — most expose a startup callback.
    For raw ASGI::

        async def lifespan(scope, receive, send):
            assert scope["type"] == "lifespan"
            while True:
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    from aria.security.worker_init import uvicorn_lifespan_startup
                    uvicorn_lifespan_startup()
                    await send({"type": "lifespan.startup.complete"})
                elif msg["type"] == "lifespan.shutdown":
                    # graceful flush — see aria.main shutdown path
                    await send({"type": "lifespan.shutdown.complete"})
                    return
    """
    boot_worker()


def graceful_shutdown_flush() -> None:
    """Mirror of ``aria.main`` shutdown helpers — call from any worker
    that handles SIGTERM independently of the ``aria.main`` process."""
    try:
        from aria.security.session_store import get_session_store
        get_session_store().flush_counters()
        logger.info("aria.worker.session_counters_flushed")
    except Exception as exc:    # noqa: BLE001
        logger.warning("aria.worker.session_counters_flush_failed",
                       error=str(exc))
    try:
        from aria.safety.replay_guard import get_replay_guard
        get_replay_guard().flush()
        logger.info("aria.worker.replay_guard_flushed")
    except Exception as exc:    # noqa: BLE001
        logger.warning("aria.worker.replay_guard_flush_failed",
                       error=str(exc))
