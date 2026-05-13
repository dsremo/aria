"""R254 — SubResource Integrity (SRI) for external scripts.

Threat: a CDN-hosted script (jQuery, analytics, even Polyfill.io 2024)
swapped server-side becomes RCE on every embedding page.  SRI binds
the script tag to a SHA-384 of the expected bytes — any mismatch and
the browser refuses to execute.

Defence: ``compute_sri(blob)`` returns the SRI hash; ``audit_html``
walks ``<script src="https://…">`` tags and refuses any external
script without a matching ``integrity=`` attribute.
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_EXTERNAL_SCRIPT_RE = re.compile(
    r'<script\b[^>]*\bsrc\s*=\s*["\'](https?://[^"\']+)["\'][^>]*>',
    re.IGNORECASE,
)
_INTEGRITY_RE = re.compile(r'\bintegrity\s*=\s*["\'](sha(?:256|384|512)-[A-Za-z0-9+/=]+)["\']', re.IGNORECASE)


def compute_sri(blob: bytes, *, algo: str = "sha384") -> str:
    if algo not in ("sha256", "sha384", "sha512"):
        raise ValueError(f"R254: algo must be sha256/384/512, got {algo}")
    h = hashlib.new(algo, blob).digest()
    return f"{algo}-{base64.b64encode(h).decode('ascii')}"


def audit_html(html: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for m in _EXTERNAL_SCRIPT_RE.finditer(html or ""):
        tag = m.group(0)
        url = m.group(1)
        if not _INTEGRITY_RE.search(tag):
            issues.append(f"sri.missing_for:{url}")
    return not issues, issues


register(DefencePlugin(
    round_id="R254",
    name="sri",
    description="SubResource Integrity hash emitter + HTML audit (refuse unpinned external scripts).",
))
