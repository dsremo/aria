"""R93 — MISP threat-intel feed integration.

Threat: ARIA only knows about the threats we coded into rules; a fast-
moving campaign (XZ-class supply chain) needs an external feed to
catch.  MISP (Malware Information Sharing Platform) is the open-source
standard for sharing IOCs.  Banks + national CSIRTs run MISP instances.

Defence: a small client that pulls a MISP event JSON over the
SSRF-safe path, normalises IOC types we care about (IP, domain, URL,
SHA-256 file hash, regex), and merges them into the live rule set.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r93")


@dataclass
class _IntelSet:
    bad_ips: set = field(default_factory=set)
    bad_domains: set = field(default_factory=set)
    bad_urls: set = field(default_factory=set)
    bad_sha256: set = field(default_factory=set)


_LATEST = _IntelSet()


def fetch_misp_event(
    misp_url: str,
    *,
    auth_key: Optional[str] = None,
    event_id: Optional[str] = None,
    timeout: float = 30.0,
) -> Optional[Dict]:
    from aria.security.guard import GuardError, safe_open_url
    full = misp_url.rstrip("/") + (f"/events/view/{event_id}" if event_id else "/events/restSearch/json")
    headers = {"Accept": "application/json", "User-Agent": "aria-core r93"}
    if auth_key:
        headers["Authorization"] = auth_key
    try:
        body = safe_open_url(
            full,
            timeout=timeout,
            max_bytes=32 * 1024 * 1024,
            allowed_schemes=("https",),
            allowed_content_types=("application/json",),
            enforce_host_allowlist=False,
            headers=headers,
        )
        return json.loads(body.decode("utf-8"))
    except GuardError as exc:
        logger.warning("r93.misp_fetch_blocked %s", exc)
        return None
    except Exception as exc:
        logger.warning("r93.misp_fetch_failed %s", exc)
        return None


def normalise_iocs(misp_event: Dict) -> _IntelSet:
    """Walk the MISP event JSON and pull the IOC types ARIA cares about."""
    out = _IntelSet()
    try:
        ev = misp_event.get("Event") or {}
        for attr in ev.get("Attribute") or []:
            t = attr.get("type", "")
            v = attr.get("value", "")
            if not v:
                continue
            if t in ("ip-src", "ip-dst"):
                out.bad_ips.add(v)
            elif t in ("domain", "hostname"):
                out.bad_domains.add(v.lower())
            elif t in ("url", "uri"):
                out.bad_urls.add(v.lower())
            elif t == "sha256":
                out.bad_sha256.add(v.lower())
    except Exception:
        pass
    return out


def install_intel(intel: _IntelSet) -> None:
    """Replace the live IOC set."""
    global _LATEST
    _LATEST = intel
    # Push known-bad IPs into R90.
    try:
        from aria.security.rounds.r90_ip_reputation import add_known_bad
        for ip in intel.bad_ips:
            add_known_bad(ip)
    except Exception:
        pass


def is_known_bad_url(url: str) -> bool:
    return url.lower() in _LATEST.bad_urls


def is_known_bad_domain(host: str) -> bool:
    return host.lower() in _LATEST.bad_domains


def is_known_bad_sha256(digest: str) -> bool:
    return digest.lower() in _LATEST.bad_sha256


register(DefencePlugin(
    round_id="R93",
    name="misp_intel",
    description="MISP feed normaliser + IOC merge into R90 (IP) and runtime checks.",
))
