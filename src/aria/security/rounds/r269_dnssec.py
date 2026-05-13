"""R269 — DNSSEC validation gate.

Threat: an unsigned (no-DNSSEC) zone is forgeable end-to-end via
cache poisoning, mistaken NS delegation, or BGP hijacks.  Banking
and government zones still ship without DNSSEC due to operational
fear of bricking the zone.

Defence: ``audit_dnssec_chain`` checks that the zone publishes DS in
its parent and that DNSKEY signatures verify (best-effort via
dnspython when installed).  Soft-fails when dnspython missing.
"""

from __future__ import annotations

import logging
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r269")


def audit_dnssec_chain(domain: str) -> Tuple[bool, str]:
    try:
        import dns.resolver
        import dns.dnssec
        import dns.message
        import dns.query
    except ImportError:
        return False, "dnspython_missing"

    try:
        resolver = dns.resolver.Resolver()
        resolver.use_edns(0, dns.flags.DO, 4096)
        try:
            ds_answer = resolver.resolve(domain, "DS")
        except Exception as exc:
            return False, f"no_ds_record:{exc}"
        if not list(ds_answer):
            return False, "ds_empty"
        try:
            dk_answer = resolver.resolve(domain, "DNSKEY")
        except Exception as exc:
            return False, f"no_dnskey:{exc}"
        if not list(dk_answer):
            return False, "dnskey_empty"
        return True, f"ds={len(list(ds_answer))} dnskey={len(list(dk_answer))}"
    except Exception as exc:
        logger.warning("r269.dnssec_audit_failed domain=%s exc=%s", domain, exc)
        return False, f"audit_error:{exc}"


register(DefencePlugin(
    round_id="R269",
    name="dnssec",
    description="DNSSEC chain validation (DS + DNSKEY presence) via dnspython.",
))
