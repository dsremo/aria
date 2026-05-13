"""Bridge between EventBus-style kwargs publish and MessageBus.publish(message).

HealthMonitor / FaultManager / CommandTracker are constructed long
before anyone knows whether the runtime bus is the production
``aria.bus.message_bus.MessageBus`` (``async def publish(message)``)
or the simulator's synchronous ``EventBus`` (``publish(topic, **kw)``).
This helper detects which shape is in use and dispatches accordingly,
matching the Recovery audit R-5 pattern already used in
``fdir_recovery_plans._dispatch``.

Wiring audit Pass 1 (F10.1 / F10.2 / F10.3): without this adapter,
swapping a ``bus=None`` constructor argument for the real
``MessageBus`` would raise ``TypeError`` on every publish call (the
EventBus-style kwargs do not match ``publish(message)``), and the
TypeError would be swallowed by the broad ``except`` blocks in the
agents that report faults — silently turning every fault into a no-op.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import structlog

logger = structlog.get_logger()


_SEVERITY_TO_PRIORITY = {
    # severity string → MessageBus EventPriority
    "debug":    "P3_ROUTINE",
    "info":     "P3_ROUTINE",
    "warning":  "P2_WARNING",
    "critical": "P1_CRITICAL",
}


def _is_message_bus(bus: Any) -> bool:
    """True iff ``bus.publish`` is the async ``publish(message)`` form.

    MessageBus.publish is ``async def publish(self, message)`` — argcount==2.
    Simulator EventBus.publish takes ``topic`` plus kwargs (more positional
    args). Argcount is the cheapest reliable discriminator and matches
    the R-5 pattern in ``fdir_recovery_plans``.
    """
    publish = getattr(bus, "publish", None)
    if publish is None:
        return False
    code = getattr(publish, "__code__", None)
    if code is None:
        return False
    return code.co_argcount <= 2


def publish_compat(
    bus: Any,
    topic: str,
    severity: str,
    source: str,
    payload: Dict[str, Any],
    sim_time_yr: float = 0.0,
) -> None:
    """Publish via ``bus``, adapting to MessageBus or EventBus shape.

    Fire-and-forget: on MessageBus the coroutine is scheduled via
    ``loop.create_task`` and never awaited, matching the existing
    callers' synchronous contract. Returns silently when ``bus`` is
    ``None`` so callers do not need to gate twice.
    """
    if bus is None:
        return
    if _is_message_bus(bus):
        # Lazy import keeps the simulator path free of the production
        # bus types (the simulator may not ship those modules).
        from aria.bus.message_bus import Message
        from aria.core.types import EventPriority

        priority_name = _SEVERITY_TO_PRIORITY.get(severity, "P2_WARNING")
        priority = getattr(EventPriority, priority_name, EventPriority.P2_WARNING)
        msg = Message(
            topic=topic,
            payload=payload,
            priority=priority,
            source_agent=source,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Not in a running loop. Production callers (agents,
            # coordinator health loop) always run under the asyncio
            # loop, so this branch is reached only by synchronous unit
            # tests where the publish is unobservable anyway.
            logger.debug("safety.publish_compat.no_loop", topic=topic)
            return
        loop.create_task(bus.publish(msg))
        return

    # Simulator EventBus path — preserve the legacy kwargs signature.
    bus.publish(
        topic,
        severity=severity,
        source=source,
        payload=payload,
        sim_time_yr=sim_time_yr,
    )
