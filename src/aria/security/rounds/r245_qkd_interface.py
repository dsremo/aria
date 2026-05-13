"""R245 — QKD (Quantum Key Distribution) interface stub.

Threat: even PQ KEMs (R68, R205) rely on computational assumptions.
For 50-year-secret data (national-archive class) operators may layer
QKD on top — BB84 / E91 — to obtain information-theoretic key
material between two physically-linked endpoints.

Defence: a thin interface so ARIA can consume keys from a QKD
appliance via ETSI GS QKD 014 (a vendor-standard REST API).  Soft-
fails to a logged warning when no QKD appliance is configured.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r245")


def fetch_key_from_qkd(*, key_id: str, length_bytes: int = 32) -> Tuple[Optional[bytes], str]:
    base = os.environ.get("ARIA_QKD_URL", "")
    token = os.environ.get("ARIA_QKD_TOKEN", "")
    if not base or not token:
        return None, "no_qkd_configured"
    try:
        from aria.security.guard import safe_open_url
        url = f"{base.rstrip('/')}/api/v1/keys/{key_id}?length={length_bytes * 8}"
        body = safe_open_url(
            url, timeout=5.0, max_bytes=64 * 1024,
            allowed_schemes=("https",),
            allowed_content_types=("application/json",),
            enforce_host_allowlist=False,
            headers={"Authorization": f"Bearer {token}", "User-Agent": "aria-core r245"},
        )
        import json
        data = json.loads(body.decode("utf-8"))
        keys = data.get("keys") or []
        if not keys:
            return None, "qkd.empty_keys"
        key_b64 = keys[0].get("key") or ""
        import base64
        key = base64.b64decode(key_b64)
        return key[:length_bytes], "qkd.fetched"
    except Exception as exc:
        logger.warning("r245.qkd_fetch_failed key_id=%s exc=%s", key_id, exc)
        return None, f"qkd.error:{type(exc).__name__}"


def is_qkd_available() -> bool:
    return bool(os.environ.get("ARIA_QKD_URL"))


register(DefencePlugin(
    round_id="R245",
    name="qkd_interface",
    description="ETSI GS QKD 014 client stub; soft-fail when no QKD appliance configured.",
))
