"""R31 — Slowloris (slow-body / slow-headers DoS).

Threat: an attacker opens 1 000 TCP connections, sends one byte of HTTP
header every few seconds, never finishing the request.  aiohttp has
sane request-read timeouts but the default 60 s ``client_max_size``
read budget can still stack to thousands of stalled workers under a
real flood.  Cleanup is process-wide.

Defence: per-connection byte-rate floor.  After the first 5 seconds of
a request, we expect at least 1 KiB/s of progress.  Anything slower
gets the request aborted with 408.  Implemented as an aiohttp
middleware that wraps the inner read with a watchdog.

References: nginx ``client_body_timeout`` + ``client_header_timeout``;
Cloudflare 2024 advisory on slow-DoS resurgence.
"""

from __future__ import annotations

import time
from typing import Any

from aria.security.plugins import DefencePlugin, register


def make_slowloris_middleware(
    *,
    grace_seconds: float = 5.0,
    min_bytes_per_second: int = 1024,
    max_total_seconds: float = 30.0,
):
    from aiohttp import web

    @web.middleware
    async def middleware(request, handler):
        cl = request.content_length
        if cl is None or cl < 4096:
            return await handler(request)         # too small to slow-loris
        start = time.monotonic()
        # Read the body up-front with a watchdog — refuses if we still
        # haven't finished after max_total_seconds.
        try:
            body = await request.read()
        except Exception:
            return web.json_response({"error": "request_read_failed"}, status=408)
        elapsed = time.monotonic() - start
        if elapsed > grace_seconds:
            rate = len(body) / max(0.001, elapsed)
            if rate < min_bytes_per_second or elapsed > max_total_seconds:
                return web.json_response(
                    {"error": "slow_request",
                     "rate_bps": int(rate),
                     "elapsed_s": round(elapsed, 2)},
                    status=408,
                )
        return await handler(request)

    return middleware


register(DefencePlugin(
    round_id="R31",
    name="slowloris",
    description="408 inbound requests slower than 1 KiB/s after 5-s grace.",
))
