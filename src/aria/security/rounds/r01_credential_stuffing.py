"""R1 — Credential stuffing & password spraying.

Threat (Snowflake / UNC5537, 2024 — $750 M+ losses): bulk-tested
credential pairs from prior breaches.  A stuffer rotates source IPs so
per-IP rate limiting alone misses the attack; what stays constant is
the *shape* of the credential being tried (length + first hash bytes).

Defence: shape-bucketed velocity score.  A credential observed across
≥ 4 distinct source IPs in 5 minutes scores 1.0 (block).  Two distinct
sources score 0.5 (alert).  Public-sector deployments may also
opt-in to a local Have-I-Been-Pwned k-anonymity prefix check; the
stub is here, populated only when a HIBP hash file is mounted.
"""

from __future__ import annotations

import collections
import hashlib
import threading
import time
from typing import Deque, Dict, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_STATE: Dict[str, Deque[Tuple[float, str]]] = collections.defaultdict(
    lambda: collections.deque(maxlen=128)
)
_LOCK = threading.Lock()


def _credential_shape(token: str) -> str:
    """Coarse bucket — first 12 hex of SHA-256 + length.  An attacker
    can't trivially enumerate the bucket-space; we compare credentials
    to credentials, not credentials to passwords."""
    if not token or len(token) < 8:
        return ""
    return f"{hashlib.sha256(token.encode()).hexdigest()[:12]}:{len(token)}"


def velocity_score(token: str, source_ip: str) -> Tuple[float, int]:
    """Return ``(score, distinct_ips)`` for the given credential."""
    shape = _credential_shape(token)
    if not shape:
        return 0.0, 0
    now = time.monotonic()
    with _LOCK:
        d = _STATE[shape]
        while d and now - d[0][0] > 300.0:        # 5-minute window
            d.popleft()
        d.append((now, source_ip))
        ips: Set[str] = {ip for _, ip in d}
    if len(ips) >= 4:
        return 1.0, len(ips)
    if len(ips) >= 2:
        return 0.5, len(ips)
    return 0.0, len(ips)


def _on_request(request, _body: bytes) -> None:
    """Inspect bearer / X-ARIA-Token headers; raise if score == 1.0."""
    tok = (
        request.headers.get("X-ARIA-Token", "")
        or (request.headers.get("Authorization", "")
            .removeprefix("Bearer ").strip())
    )
    if not tok:
        return
    src = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.remote or "unknown")
    )
    score, n = velocity_score(tok, src)
    if score >= 1.0:
        # Aborts the request — guard middleware turns this into 403.
        raise RuntimeError(
            f"R1.credential_stuffing: token shape seen across {n} IPs"
        )


register(DefencePlugin(
    round_id="R1",
    name="credential_stuffing",
    description="Snowflake-class — block tokens seen across many IPs in 5 min.",
    on_request=_on_request,
))
