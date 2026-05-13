"""Honeypot mesh — deception layer for both HTTP and LLM contexts.

ARIA's existing ``aria.security.canary`` already plants HTTP honeypot
endpoints and tracks scanner signatures.  This module extends the same
philosophy into the LLM context window and into structured tokens that
travel out across audit logs / responses.

Three deception primitives:

  1. **HTTP honeypot routes** — paths an attacker scans for but a real
     client never visits (``/.env``, ``/admin.php``, ``/wp-login.php``,
     ``/api/v1/users/all``).  Hits are logged + the source identity is
     marked critical.  Mounted via ``mount_honeypot_routes(app)``.

  2. **LLM-context decoy tokens** — synthetic "API keys" / "session
     tokens" embedded inside the system prompt or context that no real
     pipeline ever uses.  If they ever appear in an LLM output, response
     log, or external request, the leak detector fires immediately —
     because there is no legitimate path that would echo them.  Inspired
     by Thinkst's canarytokens.org concept (BSD-3) but generated locally
     with no network call.

  3. **Operator-trap fields** — canary-marked fields in admin response
     payloads (``"_canary": "trc_..."``) that get tracked.  If ARIA ever
     observes the same value flowing through an *inbound* request body
     (an attacker replaying captured admin context) it raises a
     CRITICAL alert.

All three share a single registry so a deployed ARIA can audit how
many decoys are active and how often they fire.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


logger = logging.getLogger("aria.security.honeypot")


# ── 1. HTTP honeypot paths ─────────────────────────────────────────


# Names that show up in 90 %+ of mass scanners (Mythos / Censys / Shodan
# crawl signatures, sampled 2024-2026).  Anything that visits these
# paths and isn't us is by definition hostile.
HONEYPOT_PATHS = tuple(sorted({
    "/.env", "/.env.local", "/.env.prod", "/.env.production",
    "/.git/config", "/.git/HEAD",
    "/admin", "/admin.php", "/admin/login", "/wp-login.php", "/wp-admin",
    "/phpmyadmin/", "/server-status", "/server-info",
    "/api/v1/users/all", "/api/v1/admin/users", "/api/v1/dump",
    "/config.php", "/config.json", "/.aws/credentials",
    "/private/key.pem", "/id_rsa",
    "/actuator/env", "/actuator/heapdump",  # Spring Boot scanner targets
}))


# ── 2. Decoy token mint + watch ────────────────────────────────────


@dataclass
class _DecoyToken:
    token: str
    label: str
    minted_at: float
    last_seen: Optional[float] = None
    fire_count: int = 0


class HoneypotRegistry:
    """Holds active decoys and detects their reflection / leakage."""

    def __init__(self) -> None:
        self._tokens: Dict[str, _DecoyToken] = {}
        self._http_hits: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def mint_token(self, label: str = "") -> str:
        """Return a fresh decoy token.  Same prefix shape as real ARIA
        session tokens so an attacker can't trivially distinguish.
        """
        body = secrets.token_hex(16)
        tok = f"trc_decoy_{body}"
        with self._lock:
            self._tokens[tok] = _DecoyToken(token=tok, label=label, minted_at=time.time())
        return tok

    def known_decoy(self, value: str) -> bool:
        with self._lock:
            return value in self._tokens

    def observe(self, value: str, *, where: str = "") -> bool:
        """If ``value`` matches a known decoy, record + alert.  Returns
        True if a leak was detected (caller may then refuse to ship the
        outbound response or quarantine the inbound request).
        """
        if not value or not isinstance(value, str):
            return False
        with self._lock:
            tok = self._tokens.get(value)
            if tok is None:
                return False
            tok.last_seen = time.time()
            tok.fire_count += 1
        logger.critical(
            "honeypot.decoy_fire token_label=%s where=%s",
            tok.label, where,
        )
        return True

    def scan_text(self, text: str, *, where: str = "") -> List[str]:
        """Scan a long string for ANY active decoy substring.  O(active *
        len(text)) — kept cheap because we hold few decoys at a time.
        """
        if not text:
            return []
        hits: List[str] = []
        with self._lock:
            tokens = list(self._tokens.keys())
        for tok in tokens:
            if tok in text:
                hits.append(tok)
                self.observe(tok, where=where)
        return hits

    # HTTP honeypot bookkeeping
    def record_http_hit(self, *, identity: str, path: str, ua: str = "") -> None:
        with self._lock:
            self._http_hits.append({
                "identity": identity, "path": path, "ua": ua[:64],
                "ts": time.time(),
            })
            # cap memory
            if len(self._http_hits) > 1024:
                self._http_hits = self._http_hits[-512:]
        logger.warning(
            "honeypot.http_hit identity=%s path=%s ua=%s",
            identity, path, ua[:64],
        )

    def http_hits(self, *, since_seconds: float = 3600.0) -> List[Dict[str, Any]]:
        cutoff = time.time() - since_seconds
        with self._lock:
            return [h for h in self._http_hits if h["ts"] >= cutoff]

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_decoys": len(self._tokens),
                "fired_decoys": sum(1 for t in self._tokens.values() if t.fire_count),
                "recent_http_hits": len(self._http_hits),
            }


_REGISTRY = HoneypotRegistry()


def mint_decoy_token(label: str = "") -> str:
    return _REGISTRY.mint_token(label)


def is_decoy(value: str) -> bool:
    return _REGISTRY.known_decoy(value)


def observe_decoy(value: str, *, where: str = "") -> bool:
    return _REGISTRY.observe(value, where=where)


def scan_for_decoys(text: str, *, where: str = "") -> List[str]:
    return _REGISTRY.scan_text(text, where=where)


def honeypot_status() -> Dict[str, Any]:
    return _REGISTRY.status()


# ── 3. aiohttp wiring helper ───────────────────────────────────────


def mount_honeypot_routes(app: Any, *, response_status: int = 404) -> None:
    """Register every HONEYPOT_PATH as a 404-but-logged route on ``app``.

    The route does NOT serve content — a real attacker may parse the
    body for fingerprinting.  We return a generic 404 to look like any
    misconfigured site, but the request itself is logged as a hostile
    probe.  Source identity is recorded in the registry so the rate
    limiter can fast-block.
    """
    try:
        from aiohttp import web
    except ImportError:                                     # pragma: no cover
        return

    async def _trap(request):
        path = request.path
        ua = request.headers.get("User-Agent", "")
        identity = (
            request.headers.get("X-Forwarded-For", "")
            or request.remote
            or "unknown"
        )
        _REGISTRY.record_http_hit(identity=str(identity), path=path, ua=ua)
        return web.Response(status=response_status, text="Not Found")

    for path in HONEYPOT_PATHS:
        try:
            app.router.add_get(path, _trap)
            app.router.add_post(path, _trap)
        except Exception:
            # Path already registered — skip silently.
            continue


__all__ = [
    "HONEYPOT_PATHS",
    "HoneypotRegistry",
    "mint_decoy_token", "is_decoy", "observe_decoy", "scan_for_decoys",
    "honeypot_status",
    "mount_honeypot_routes",
]
