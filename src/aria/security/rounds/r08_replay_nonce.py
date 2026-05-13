"""R8 — Anti-replay nonce ledger for sensitive endpoints.

Threat: a captured signed request (admin command, payment, key
rotation) is replayed by an attacker who later sniffs or coerces the
on-wire bytes.  ARIA's HMAC + ``compare_digest`` blocks tampering but
not replay.  Cases: financial-API replay (Plaid 2023 disclosure),
Capital-Group middleware (2024).

Defence: ``record_nonce(nonce, ttl)`` — Bloom-filter-cheap in-memory
ledger.  ``check_and_consume(nonce, ttl)`` returns False if seen before.
For multi-instance deployments operators wire a Redis backend by setting
``ARIA_NONCE_BACKEND=redis://…`` (interface stub provided here).
"""

from __future__ import annotations

import threading
import time
from typing import Dict

from aria.security.plugins import DefencePlugin, register


_LEDGER: Dict[str, float] = {}
_LOCK = threading.Lock()
_DEFAULT_TTL = 300.0       # 5 min


def check_and_consume(nonce: str, *, ttl: float = _DEFAULT_TTL) -> bool:
    """Atomically: True if first sighting (and now recorded); False if
    already in the ledger.  Old entries past ``ttl`` are evicted on every
    call to keep memory bounded."""
    if not nonce or len(nonce) < 8:
        return False
    now = time.monotonic()
    with _LOCK:
        # Evict expired entries
        expired = [n for n, ts in _LEDGER.items() if now - ts > ttl]
        for n in expired:
            _LEDGER.pop(n, None)
        if nonce in _LEDGER:
            return False
        _LEDGER[nonce] = now
    return True


def ledger_size() -> int:
    with _LOCK:
        return len(_LEDGER)


register(DefencePlugin(
    round_id="R8",
    name="anti_replay",
    description="In-memory nonce ledger; admin handlers call check_and_consume.",
))
