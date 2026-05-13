"""R99 — Emergency kill-switch (hot break-glass).

Threat: when an active compromise is in progress and ARIA is being
used as a stepping stone, the operator needs a single reliable way to
freeze the service — refuse all requests, drop all sessions, stop
outbound calls — without redeploying.  Every nation-state defender
ships such a switch.

Defence: a process-wide ``KillSwitch`` singleton with three states:
``ACTIVE`` (normal), ``READONLY`` (refuse mutations), ``LOCKED``
(refuse everything except healthz).  Operator triggers via signed
admin token + `mfa_admin_check` (R10 foundation).  Plugin
``on_request`` hook enforces the state.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r99")


class KillState(str, Enum):
    ACTIVE = "active"
    READONLY = "readonly"
    LOCKED = "locked"


class _KillSwitch:
    def __init__(self) -> None:
        self._state = KillState.ACTIVE
        self._reason = ""
        self._lock = threading.Lock()

    def set_state(self, new_state: KillState, *, reason: str = "") -> None:
        with self._lock:
            old = self._state
            self._state = new_state
            self._reason = reason[:200]
        logger.critical(
            "r99.state_change %s -> %s reason=%s",
            old, new_state, reason[:80],
        )

    def state(self) -> KillState:
        with self._lock:
            return self._state

    def reason(self) -> str:
        with self._lock:
            return self._reason


_SWITCH = _KillSwitch()


def state() -> KillState:
    return _SWITCH.state()


def trip_readonly(reason: str) -> None:
    _SWITCH.set_state(KillState.READONLY, reason=reason)


def trip_locked(reason: str) -> None:
    _SWITCH.set_state(KillState.LOCKED, reason=reason)


def restore() -> None:
    _SWITCH.set_state(KillState.ACTIVE, reason="restored")


def _on_request(request, _body):
    s = _SWITCH.state()
    if s is KillState.ACTIVE:
        return
    path = request.path or "/"
    method = request.method.upper()
    # Always allow health check
    if path in ("/v1/healthz", "/healthz", "/v1/version"):
        return
    if s is KillState.READONLY and method in ("GET", "HEAD", "OPTIONS"):
        return
    raise RuntimeError(
        f"R99.kill_switch state={s.value} reason={_SWITCH.reason()!r}"
    )


register(DefencePlugin(
    round_id="R99",
    name="kill_switch",
    description="Process-wide ACTIVE/READONLY/LOCKED kill switch with audit on transition.",
    on_request=_on_request,
))
