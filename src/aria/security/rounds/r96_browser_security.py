"""R96 — Browser-side security headers (Subresource Integrity + COOP/COEP).

Threat: ARIA's web dashboard (`web/`) loads JavaScript via ``<script
src="...">``.  Without Subresource Integrity (SRI) a CDN compromise
(Polyfill.io 2024 class) executes attacker code in the dashboard
context.  Without COOP/COEP, cross-origin process isolation is
incomplete and Spectre-class side channels become exploitable.

Defence: a small ``compute_sri(url, content)`` helper that returns the
``integrity="sha384-..."`` attribute caller should put on the script
tag, plus ``recommended_browser_headers()`` extending R-foundation's
security headers with COOP / COEP / CORP for the dashboard origin.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Dict

from aria.security.plugins import DefencePlugin, register


def compute_sri(content: bytes, *, alg: str = "sha384") -> str:
    if alg not in ("sha256", "sha384", "sha512"):
        raise ValueError(f"unsupported alg: {alg}")
    digest = hashlib.new(alg, content).digest()
    return f"{alg}-{base64.b64encode(digest).decode('ascii')}"


def recommended_browser_headers() -> Dict[str, str]:
    """Headers the dashboard origin should send on every HTML response.

    Composes with R-foundation's ``_security_headers`` (which already
    sets X-Frame-Options, CSP, HSTS, etc.).  These add the cross-origin
    isolation triad needed for full Spectre mitigation in the browser.
    """
    return {
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Origin-Agent-Cluster": "?1",
    }


register(DefencePlugin(
    round_id="R96",
    name="browser_security",
    description="SRI computation + COOP/COEP/CORP header pack for dashboard origin.",
))
