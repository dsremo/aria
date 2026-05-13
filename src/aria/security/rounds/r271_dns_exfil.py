"""R271 — DNS query exfiltration detector.

Threat: malware tunnels stolen data through DNS queries — encoding
chunks of payload in subdomain labels of an attacker-controlled zone
(``<base32-payload>.exfil.example.com``).  Often slips past blocking
proxies because port-53 is rarely filtered.

Defence: score outbound DNS queries — high entropy in subdomain
labels, unusual TXT-only patterns, very long FQDNs, sustained query
rate to a single second-level zone are exfil indicators.
"""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _ZoneState:
    timestamps: Deque[float] = field(default_factory=lambda: deque(maxlen=256))


_ZONE_STATES: Dict[str, _ZoneState] = defaultdict(_ZoneState)
_LOCK = threading.Lock()


def _shannon(text: str) -> float:
    if not text:
        return 0.0
    counts = Counter(text)
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def score_query(fqdn: str, *, qtype: str = "A", now: float = 0.0) -> Tuple[float, str]:
    if not fqdn:
        return 0.0, "empty"

    fq = fqdn.lower().rstrip(".")
    parts = fq.split(".")
    score = 0.0
    notes = []

    if len(fq) > 90:
        score += 0.3
        notes.append(f"long_fqdn:{len(fq)}")

    if parts:
        first = parts[0]
        ent = _shannon(first)
        if ent >= 4.0 and len(first) >= 20:
            score += 0.4
            notes.append(f"high_entropy_label:{ent:.1f}")

    if qtype.upper() == "TXT":
        score += 0.1
        notes.append("txt_only")

    zone = ".".join(parts[-2:]) if len(parts) >= 2 else fq
    t = now or time.time()
    with _LOCK:
        state = _ZONE_STATES[zone]
        state.timestamps.append(t)
        recent = sum(1 for ts in state.timestamps if t - ts <= 60.0)
    if recent >= 30:
        score += 0.3
        notes.append(f"rate_burst:{recent}/60s")

    return min(1.0, score), ",".join(notes) or "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _ZONE_STATES.clear()


register(DefencePlugin(
    round_id="R271",
    name="dns_exfil",
    description="DNS-tunnel detector: subdomain entropy + length + TXT + per-zone burst rate.",
))
