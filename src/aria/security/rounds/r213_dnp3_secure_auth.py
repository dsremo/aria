"""R213 — DNP3 Secure Authentication v5/v6.

Threat: DNP3 is the dominant SCADA protocol in North-American power
utilities.  Plain DNP3 has no authentication; an attacker who reaches
the substation LAN can issue control operations.  Ukrainian grid
attack 2015 / 2016 used this class of access.

Defence: validate DNP3 SAv5/v6 messages — refuse session keys < 16
bytes, refuse messages without aggressive-mode HMAC, refuse non-
challenge-response control operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_dnp3_session(session: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    sav = int(session.get("sav_version", 0))
    if sav < 5:
        issues.append(f"dnp3.sav_version_too_low:{sav}")

    sk = session.get("session_key") or b""
    if not isinstance(sk, (bytes, bytearray)) or len(sk) < 16:
        issues.append("dnp3.session_key_too_short")

    if not session.get("hmac_sha256_enabled"):
        issues.append("dnp3.no_hmac_sha256")

    if session.get("aggressive_mode") and not session.get("aggressive_mode_hmac"):
        issues.append("dnp3.aggressive_no_hmac")

    if session.get("control_operation") and not session.get("challenged"):
        issues.append("dnp3.control_op_unchallenged")

    if int(session.get("key_change_interval_minutes", 1440)) > 1440:
        issues.append("dnp3.key_change_interval_too_long")

    return not issues, issues


register(DefencePlugin(
    round_id="R213",
    name="dnp3_secure_auth",
    description="DNP3 Secure Authentication v5/v6 audit; refuse weak session params.",
))
