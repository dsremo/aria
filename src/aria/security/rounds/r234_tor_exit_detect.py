"""R234 — Tor exit / VPN egress detection.

Threat: legitimate services have legitimate Tor users, but high-risk
flows (financial transfers, account creation, key rotation) from a
Tor exit deserve elevated scrutiny.  Some attackers also chain Tor
through residential VPNs to evade ASN block-lists.

Defence: a soft helper that maintains an in-memory exit-list (loaded
on demand from operator data) and returns ``(is_exit, source)`` for
an IP, plus a risk-bump signal that callers can fold into adaptive
scoring.
"""

from __future__ import annotations

import threading
from typing import Iterable, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_EXIT_LIST: Set[str] = set()
_VPN_LIST: Set[str] = set()
_LOCK = threading.Lock()


def load_exit_list(ips: Iterable[str]) -> int:
    with _LOCK:
        before = len(_EXIT_LIST)
        for ip in ips:
            ip = (ip or "").strip()
            if ip:
                _EXIT_LIST.add(ip)
        return len(_EXIT_LIST) - before


def load_vpn_list(ips: Iterable[str]) -> int:
    with _LOCK:
        before = len(_VPN_LIST)
        for ip in ips:
            ip = (ip or "").strip()
            if ip:
                _VPN_LIST.add(ip)
        return len(_VPN_LIST) - before


def classify_ip(ip: str) -> Tuple[bool, str]:
    """Returns ``(is_anonymising, source)`` where source is
    ``tor_exit`` / ``vpn`` / ``clean``."""
    with _LOCK:
        if ip in _EXIT_LIST:
            return True, "tor_exit"
        if ip in _VPN_LIST:
            return True, "vpn"
    return False, "clean"


def risk_bump(ip: str, *, sensitive_action: bool = False) -> float:
    is_anon, _ = classify_ip(ip)
    if not is_anon:
        return 0.0
    return 0.4 if sensitive_action else 0.15


def reset_for_tests() -> None:
    with _LOCK:
        _EXIT_LIST.clear()
        _VPN_LIST.clear()


register(DefencePlugin(
    round_id="R234",
    name="tor_exit_detect",
    description="Tor exit + VPN egress classifier; sensitive-action risk bump.",
))
