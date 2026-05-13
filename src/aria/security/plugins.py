"""Plugin registry — round-by-round defences without library churn.

Each round of the security audit (R1, R2, … R51, R52, …) can register
its own defence here.  The registry exposes well-known hook points;
any module that calls ``register(...)`` with a ``DefencePlugin`` gets
its hooks invoked at the right moment.

Hook points (alphabetical):

  * ``on_request``      — every inbound aiohttp request (after auth).
                          Receives (request, body_bytes) → may raise to abort.
  * ``on_response``     — every outbound aiohttp response.
                          Receives (request, response_body_bytes).  Used
                          by exfil-detection plugins to scan for decoy
                          token leakage.
  * ``on_score``        — extra scorer for ``adaptive.score_request``.
                          Hook signature: ``(endpoint, payload, identity)
                          -> (score_in_0_1, reason_string)``.
  * ``on_outbound_url`` — every URL passed to ``safe_open_url``.
                          Hook may return a list of error strings.
  * ``on_audit``        — every ``log_event`` call.
                          Hook receives the audit dict.

A defence plugin is just a dataclass listing the hooks it implements;
omit a hook to opt out of that point.  Plugins are deliberately
single-process and in-memory — they do not persist across restarts;
the round number that registered them is recorded so the audit doc
stays in sync with what's actually loaded.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional


logger = logging.getLogger("aria.security.plugins")


@dataclass
class DefencePlugin:
    """A single round's defence package.  All hooks are optional."""

    round_id: str                                            # e.g. "R52"
    name: str                                                # short label
    description: str = ""
    on_request: Optional[Callable[[Any, bytes], None]] = None
    on_response: Optional[Callable[[Any, bytes], None]] = None
    on_score: Optional[Callable[[str, bytes, str], "tuple[float, str]"]] = None
    on_outbound_url: Optional[Callable[[str], List[str]]] = None
    on_audit: Optional[Callable[[Dict[str, Any]], None]] = None
    enabled: bool = True


class _Registry:
    def __init__(self) -> None:
        self._plugins: Dict[str, DefencePlugin] = {}
        self._lock = threading.Lock()

    def register(self, plugin: DefencePlugin) -> None:
        with self._lock:
            if plugin.round_id in self._plugins:
                logger.info(
                    "plugins.replacing round=%s name=%s",
                    plugin.round_id, plugin.name,
                )
            self._plugins[plugin.round_id] = plugin
            # If the plugin offers a request scorer, also wire it into
            # the adaptive engine.
            if plugin.on_score and plugin.enabled:
                from aria.security.adaptive import register_request_scorer
                register_request_scorer(plugin.on_score)
        logger.info(
            "plugins.registered round=%s name=%s",
            plugin.round_id, plugin.name,
        )

    def list_active(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"round": p.round_id, "name": p.name,
                 "description": p.description, "enabled": p.enabled}
                for p in self._plugins.values()
            ]

    def disable(self, round_id: str) -> bool:
        with self._lock:
            p = self._plugins.get(round_id)
            if p is None:
                return False
            p.enabled = False
            return True

    def clear(self) -> None:
        """Remove every registered plugin.  Used by tests; do not call in
        production code unless you really mean to disarm everything."""
        with self._lock:
            self._plugins.clear()

    def fire_request(self, request: Any, body: bytes) -> None:
        for p in list(self._plugins.values()):
            if not p.enabled or p.on_request is None:
                continue
            try:
                p.on_request(request, body)
            except Exception:
                # Re-raise — request hooks are allowed to abort.
                raise

    def fire_response(self, request: Any, body: bytes) -> None:
        for p in list(self._plugins.values()):
            if not p.enabled or p.on_response is None:
                continue
            try:
                p.on_response(request, body)
            except Exception:
                logger.warning(
                    "plugins.on_response_failed round=%s", p.round_id,
                )

    def fire_outbound_url(self, url: str) -> List[str]:
        problems: List[str] = []
        for p in list(self._plugins.values()):
            if not p.enabled or p.on_outbound_url is None:
                continue
            try:
                problems.extend(p.on_outbound_url(url) or [])
            except Exception:
                logger.warning(
                    "plugins.on_outbound_url_failed round=%s", p.round_id,
                )
        return problems

    def fire_audit(self, event: Dict[str, Any]) -> None:
        for p in list(self._plugins.values()):
            if not p.enabled or p.on_audit is None:
                continue
            try:
                p.on_audit(event)
            except Exception:
                logger.warning(
                    "plugins.on_audit_failed round=%s", p.round_id,
                )


_REGISTRY = _Registry()


def register(plugin: DefencePlugin) -> None:
    _REGISTRY.register(plugin)


def clear_for_tests() -> None:
    """Drop every registered plugin AND every adaptive request-scorer hook.
    Test-only — never call in prod paths."""
    _REGISTRY.clear()
    try:
        from aria.security.adaptive import _clear_request_scorers_for_tests
        _clear_request_scorers_for_tests()
    except Exception:
        pass


def list_active() -> List[Dict[str, Any]]:
    return _REGISTRY.list_active()


def disable(round_id: str) -> bool:
    return _REGISTRY.disable(round_id)


def fire_request(request: Any, body: bytes) -> None:
    _REGISTRY.fire_request(request, body)


def fire_response(request: Any, body: bytes) -> None:
    _REGISTRY.fire_response(request, body)


def fire_outbound_url(url: str) -> List[str]:
    return _REGISTRY.fire_outbound_url(url)


def fire_audit(event: Dict[str, Any]) -> None:
    _REGISTRY.fire_audit(event)


__all__ = [
    "DefencePlugin",
    "register", "list_active", "disable",
    "fire_request", "fire_response", "fire_outbound_url", "fire_audit",
]
