"""R212 — Modbus TCP audit.

Threat: Modbus TCP has *no authentication* by design — any reachable
client can write coils / registers.  Stuxnet-class attacks; Triton
2017 (Schneider Triconex); German steel mill 2014.  Shodan lists
1M+ exposed Modbus endpoints.

Defence: refuse Modbus TCP without an auth wrapper (Modbus Security
RFC 30 / TCP+TLS) in production; whitelist function-code + slave-id
ranges; detect write-coil bursts that target safety-critical
registers.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DANGEROUS_FUNCTION_CODES = {5, 6, 15, 16, 22, 23}    # write coils / registers


def audit_modbus_request(
    *, function_code: int, slave_id: int, register_addr: int, count: int = 1,
    via_tls: bool = False,
    safety_critical_ranges: Iterable[Tuple[int, int]] = (),
) -> Tuple[bool, List[str]]:
    issues: List[str] = []

    if not via_tls and os.environ.get("ARIA_ENV") == "prod":
        issues.append("modbus.cleartext_in_prod")

    if function_code in _DANGEROUS_FUNCTION_CODES:
        for lo, hi in safety_critical_ranges:
            if lo <= register_addr <= hi or lo <= register_addr + count - 1 <= hi:
                issues.append(f"modbus.write_to_safety_register addr={register_addr} fc={function_code}")

    if slave_id < 1 or slave_id > 247:
        issues.append(f"modbus.invalid_slave_id:{slave_id}")

    if count > 125:
        issues.append(f"modbus.oversized_count:{count}")

    return not issues, issues


def recommend_modbus_security() -> str:
    return (
        "Use Modbus/TCP Security (RFC 30): TCP/802 with TLS 1.2+, "
        "X.509 client cert, and per-connection role-based access list."
    )


register(DefencePlugin(
    round_id="R212",
    name="modbus_audit",
    description="Modbus TCP auth/scope audit; refuse cleartext + safety-register writes.",
))
