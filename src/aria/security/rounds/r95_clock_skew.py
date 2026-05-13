"""R95 — Clock-skew detection.

Threat: a compromised host where the attacker shifts the wall clock
backwards bypasses TTL-based defences (R8 nonce ledger, R10 sealed
audit, R28 token budget, R63 TOTP).  Banks pin the host clock to NTP
+ poll a reference periodically; nation-state defenders use RFC 5905
NTP authentication.

Defence: ``check_clock_skew(reference_url)`` issues a HEAD against a
``Date:``-providing URL (we default to a public time endpoint), parses
``Date:`` header per RFC 7231, and compares to local wall.  Returns
``(skew_seconds, ok_bool)``.  Operators wire this to a 5-min poll +
alert when |skew| > 5 s.
"""

from __future__ import annotations

import email.utils
import time
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_REFS = (
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.cisa.gov/",
)


def check_clock_skew(reference_url: Optional[str] = None) -> Tuple[float, bool]:
    """Return ``(skew_seconds, within_tolerance)``.

    Tolerance default: ±5 s.  Wider clock drift means TTL-based defences
    are at risk of being bypassed.
    """
    from aria.security.guard import safe_open_url
    refs = (reference_url,) if reference_url else _DEFAULT_REFS
    for ref in refs:
        if ref is None:
            continue
        try:
            local_before = time.time()
            # Use the basic safe_open_url; we only want the Date: response header.
            # safe_open_url returns body only — for accurate skew we'd want
            # headers; we wrap urllib directly here under the same allow-list.
            import urllib.request
            req = urllib.request.Request(
                ref, headers={"User-Agent": "aria-core r95"},
            )
            from aria.security.guard import validate_outbound_url
            validate_outbound_url(ref)
            with urllib.request.urlopen(req, timeout=5.0) as resp:        # nosec B310 (validated)
                local_after = time.time()
                date_header = resp.headers.get("Date") or ""
            if not date_header:
                continue
            server_dt = email.utils.parsedate_to_datetime(date_header)
            if server_dt is None:
                continue
            server_ts = server_dt.timestamp()
            local_avg = (local_before + local_after) / 2
            skew = local_avg - server_ts
            return skew, abs(skew) <= 5.0
        except Exception:
            continue
    return 0.0, False


register(DefencePlugin(
    round_id="R95",
    name="clock_skew",
    description="Check local-vs-internet wall clock; ±5 s tolerance default.",
))
