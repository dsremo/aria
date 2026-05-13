"""R9 — Geographic / impossible-travel anomaly.

Threat: a stolen credential lights up from two continents within
minutes — classic ATO (account takeover).  Real cases: AT&T 2024
(Snowflake breach lateral), Microsoft Midnight Blizzard 2024, every
SaaS phishing kit since 2022.

Defence: per-token sliding window of (timestamp, source_ip).  On every
new request we ask "is this IP plausibly within travel distance of
the previous IP given the time gap?".  We do NOT bundle a GeoIP
database — operators wire one via ``configure_geoip_lookup()`` if they
have one (MaxMind GeoLite2, IPInfo, etc.); without it the round
degrades to an IP-set diversity score still useful in CGNAT scenarios.
"""

from __future__ import annotations

import collections
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _Event:
    ts: float
    ip: str
    lat: Optional[float] = None
    lon: Optional[float] = None


_TRAILS: Dict[str, Deque[_Event]] = collections.defaultdict(
    lambda: collections.deque(maxlen=8)
)
_LOCK = threading.Lock()
_GEOIP_FN: Optional[Callable[[str], Optional[Tuple[float, float]]]] = None


def configure_geoip_lookup(fn: Callable[[str], Optional[Tuple[float, float]]]) -> None:
    """Wire a callable that returns (lat, lon) for an IP, or None if unknown."""
    global _GEOIP_FN
    _GEOIP_FN = fn


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def observe(token: str, source_ip: str) -> Tuple[float, str]:
    """Return ``(score, reason)`` for the current event."""
    if not token or len(token) < 8:
        return 0.0, ""
    now = time.monotonic()
    coords: Optional[Tuple[float, float]] = None
    if _GEOIP_FN is not None:
        try:
            coords = _GEOIP_FN(source_ip)
        except Exception:
            coords = None
    ev = _Event(ts=now, ip=source_ip,
                lat=coords[0] if coords else None,
                lon=coords[1] if coords else None)
    with _LOCK:
        d = _TRAILS[token]
        prev = d[-1] if d else None
        d.append(ev)
    if prev is None:
        return 0.0, ""
    dt = max(now - prev.ts, 1.0)
    if prev.lat is not None and ev.lat is not None:
        dist_km = _haversine_km(prev.lat, prev.lon, ev.lat, ev.lon)
        # Implied speed; > 1 000 km/h is supersonic = impossible travel.
        speed_kmph = dist_km / (dt / 3600.0)
        if speed_kmph > 1_000.0:
            return 1.0, f"r09.impossible_travel speed={speed_kmph:.0f}km/h"
        if speed_kmph > 500.0:
            return 0.5, f"r09.fast_travel speed={speed_kmph:.0f}km/h"
        return 0.0, ""
    # No GeoIP: fall back to IP-set diversity.
    with _LOCK:
        ips = {e.ip for e in _TRAILS[token]}
    if len(ips) >= 4:
        return 0.4, f"r09.ip_diversity={len(ips)}"
    return 0.0, ""


def _on_request(request, _body: bytes) -> None:
    tok = (
        request.headers.get("X-ARIA-Token", "")
        or request.headers.get("Authorization", "")[:128]
    )
    if not tok:
        return
    src = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
           or (request.remote or ""))
    score, reason = observe(tok, src)
    if score >= 1.0:
        raise RuntimeError(reason)


register(DefencePlugin(
    round_id="R9",
    name="geo_anomaly",
    description="Impossible-travel detection per token; opt-in GeoIP wiring.",
    on_request=_on_request,
))
