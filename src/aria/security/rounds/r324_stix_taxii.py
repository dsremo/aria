"""R324 — STIX 2.1 / TAXII feed consumer.

Threat: an organisation that doesn't ingest STIX/TAXII feeds from
ISACs / commercial vendors / CISA AIS misses every published
indicator hours-to-days after disclosure.

Defence: a STIX 2.1 indicator parser + TAXII client wrapper around
``safe_open_url``.  Returns parsed indicator-of-compromise (IOC)
patterns ready to feed into R90 IP reputation, R93 KEV, etc.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r324")


def parse_stix_bundle(blob: bytes) -> Tuple[bool, List[Dict[str, str]]]:
    try:
        data = json.loads(blob.decode("utf-8"))
    except Exception as exc:
        return False, [{"error": f"stix.parse:{exc}"}]
    if data.get("type") not in ("bundle",):
        return False, [{"error": "stix.not_bundle"}]
    indicators: List[Dict[str, str]] = []
    for obj in data.get("objects", []):
        if obj.get("type") != "indicator":
            continue
        pattern = obj.get("pattern") or ""
        ioc_kind, value = _classify_pattern(pattern)
        if ioc_kind:
            indicators.append({
                "id": obj.get("id", ""),
                "kind": ioc_kind, "value": value,
                "name": obj.get("name", ""),
                "valid_from": obj.get("valid_from", ""),
            })
    return True, indicators


def _classify_pattern(pattern: str) -> Tuple[str, str]:
    p = (pattern or "").strip()
    for kind, prefix in (
        ("ipv4-addr", "[ipv4-addr:value = '"),
        ("ipv6-addr", "[ipv6-addr:value = '"),
        ("domain-name", "[domain-name:value = '"),
        ("url", "[url:value = '"),
        ("file-sha256", "[file:hashes.'SHA-256' = '"),
    ):
        if p.startswith(prefix):
            try:
                return kind, p.split("'", 2)[1]
            except IndexError:
                return "", ""
    return "", ""


def fetch_taxii_collection(*, taxii_url: str, headers: Dict[str, str] = None) -> Tuple[bool, List[Dict[str, str]]]:
    try:
        from aria.security.guard import safe_open_url
        body = safe_open_url(
            taxii_url, timeout=10.0, max_bytes=4 * 1024 * 1024,
            allowed_schemes=("https",),
            allowed_content_types=("application/taxii+json", "application/stix+json", "application/json"),
            enforce_host_allowlist=False,
            headers=headers or {"Accept": "application/taxii+json;version=2.1"},
        )
        return parse_stix_bundle(body)
    except Exception as exc:
        logger.warning("r324.taxii_fetch_failed url=%s exc=%s", taxii_url, exc)
        return False, [{"error": f"taxii:{type(exc).__name__}"}]


register(DefencePlugin(
    round_id="R324",
    name="stix_taxii",
    description="STIX 2.1 bundle parser + TAXII client (consumes ISAC / CISA AIS feeds).",
))
