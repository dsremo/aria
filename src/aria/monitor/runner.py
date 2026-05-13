"""ARIA Independent Monitor Runner — separate-process entry point.

Launch as::

    python -m aria.monitor.runner

This is the long-missing process referenced by ``aria/monitor/__init__.py``
("Different process — run via aria.monitor.runner").  The primary
controller's ``HeartbeatWatcher`` (wired in ``main.py``) listens for
``aria.monitor.heartbeat`` events on its local bus; this runner is the
sidecar that produces those heartbeats from a different process so the
T-V-2 threat ("monitor compromised silently") is actually mitigated.

Architecture
============

The primary's bus is in-memory and process-local, so this runner cannot
publish to it directly.  An IPC bridge is required.  Three plausible
designs:

1. **HTTP POST to the primary's API** — runner POSTs HMAC-signed
   heartbeats to ``${ARIA_PRIMARY_URL}/api/internal/monitor-heartbeat``;
   the endpoint authenticates with ``ARIA_HEARTBEAT_SECRET`` and
   re-publishes the message on the local bus.  Simplest if the primary
   is already serving HTTP.

2. **File-based bridge** — runner writes
   ``data/runtime/monitor_heartbeat.json`` atomically every 5 s; the
   primary polls the file in a daemon thread and re-publishes.  Works
   without networking; useful for bare-metal deploys.

3. **External broker** — both processes connect to a shared Redis /
   NATS / ZeroMQ broker.  Most flexible; adds an infrastructure
   dependency.

The choice is a product/architecture decision logged in the wiring
audit tracker as F14.4.  This module exposes the runner-side scaffolding
(emitter construction, period, HMAC signing); the publish callable is
injected so the IPC implementation can be swapped without touching the
emitter.

Environment variables
=====================

  ``ARIA_HEARTBEAT_SECRET``     — hex HMAC key (required in prod; same
                                  secret the primary's watcher uses).
  ``ARIA_MONITOR_EMITTER_ID``   — defaults to ``"monitor"`` (must match
                                  the primary's expected_emitter).
  ``ARIA_MONITOR_HEARTBEAT_PERIOD_S`` — defaults to ``5.0``.

Security
========

The ``HeartbeatEmitter`` already signs ``boot_id`` with the shared HMAC
secret per S-14, so a bus attacker cannot forge a "monitor restarted"
message even if they can publish to the primary's bus.  The IPC bridge
inherits that authentication.

"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict

import structlog

from aria.monitor.heartbeat import HeartbeatEmitter

logger = structlog.get_logger()


PublishFn = Callable[[str, Dict[str, Any]], None]


def _stub_publish_fn(topic: str, payload: Dict[str, Any]) -> None:
    """Fallback publisher: structured log line only — does NOT cross
    process boundaries to the primary.  Useful for proving the runner
    itself runs; not useful for the actual oversight chain.

    Production deploys MUST replace this with one of the three IPC
    designs documented in this module's docstring.  Operators get a
    CRITICAL log on every beat so the gap is impossible to miss.
    """
    logger.critical(
        "monitor.runner.publish_stub",
        topic=topic,
        payload=payload,
        impact=(
            "no IPC to primary — F14.4 architectural decision pending; "
            "see aria/monitor/runner.py docstring"
        ),
    )


def make_publish_fn() -> PublishFn:
    """Resolve the publish callable from environment configuration.

    Resolution order:

    1. ``ARIA_MONITOR_PUBLISH_FN`` — dotted import path to a callable.
       Highest precedence so operators can plug a custom IPC.
    2. ``ARIA_MONITOR_HEARTBEAT_FILE`` — atomic file-bridge to that
       path; the primary's file-poller in ``aria.main`` re-publishes
       onto the local bus. Simplest IPC; no networking required.
    3. ``_stub_publish_fn`` — loud CRITICAL on every beat so any
       deploy that forgot to configure transport notices immediately.
    """
    publish_dotted = os.environ.get("ARIA_MONITOR_PUBLISH_FN", "").strip()
    if publish_dotted:
        module_name, _, attr_name = publish_dotted.rpartition(".")
        if not module_name:
            raise ValueError(
                "ARIA_MONITOR_PUBLISH_FN must be a fully-qualified dotted path "
                "to a callable, e.g. aria.monitor.bridges.file_publish_fn"
            )
        from importlib import import_module
        module = import_module(module_name)
        return getattr(module, attr_name)

    heartbeat_file = os.environ.get("ARIA_MONITOR_HEARTBEAT_FILE", "").strip()
    if heartbeat_file:
        from aria.monitor.bridges import file_publish_fn
        logger.info("monitor.runner.file_bridge_selected", path=heartbeat_file)
        return file_publish_fn(heartbeat_file)

    return _stub_publish_fn


def run(
    publish_fn: PublishFn | None = None,
    emitter_id: str | None = None,
    period_s: float | None = None,
) -> int:
    """Run the monitor sidecar until SIGINT/SIGTERM.

    Returns the exit code.  Construction failures (e.g. missing HMAC
    secret in production) bubble up as exceptions so a process
    supervisor sees a non-zero exit and restarts.
    """
    publish_fn = publish_fn or make_publish_fn()
    emitter_id = emitter_id or os.environ.get("ARIA_MONITOR_EMITTER_ID", "monitor")
    if period_s is None:
        period_s = float(os.environ.get("ARIA_MONITOR_HEARTBEAT_PERIOD_S", "5.0"))

    emitter = HeartbeatEmitter(
        publish_fn=publish_fn,
        emitter_id=emitter_id,
        period_s=period_s,
    )

    stop = threading.Event()

    def _handle_signal(signum: int, _frame: Any) -> None:
        logger.info("monitor.runner.signal", signum=signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    emitter.start()
    logger.info(
        "monitor.runner.started",
        emitter_id=emitter_id,
        period_s=period_s,
        publish=getattr(publish_fn, "__qualname__", repr(publish_fn)),
    )

    try:
        while not stop.is_set():
            stop.wait(1.0)
    finally:
        emitter.stop()
        logger.info("monitor.runner.stopped", emitter_id=emitter_id)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ARIA independent monitor runner (F-7)."
    )
    parser.add_argument(
        "--emitter-id",
        default=None,
        help="emitter_id to advertise (must match primary's expected_emitter)",
    )
    parser.add_argument(
        "--period-s",
        type=float,
        default=None,
        help="heartbeat period in seconds (default 5.0)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("ARIA_LOG_LEVEL", "INFO"),
        help="logging level (default INFO)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(message)s",
    )

    return run(emitter_id=args.emitter_id, period_s=args.period_s)


if __name__ == "__main__":
    sys.exit(main())
