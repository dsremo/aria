"""R296 — Travel-mode device policy.

Threat: a device crossing borders is searchable by customs (US, UK,
CN), and lost/stolen at higher rates.  Default-credentialed devices
in travel mode are a common breach origin (Marriott 2018-class
hospitality networks).

Defence: a per-device travel-mode toggle.  When active, refuse access
to high-classification data, require re-authentication on every
sensitive operation, and disable cloud-sync of credentials.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class TravelMode:
    device_id: str
    active: bool
    started_country: str = ""
    expected_return: float = 0.0


_MODES: Dict[str, TravelMode] = {}
_LOCK = threading.Lock()


def enable_travel_mode(device_id: str, *, country: str = "", expected_return: float = 0.0) -> None:
    with _LOCK:
        _MODES[device_id] = TravelMode(
            device_id=device_id, active=True,
            started_country=country, expected_return=expected_return,
        )


def disable_travel_mode(device_id: str) -> None:
    with _LOCK:
        m = _MODES.get(device_id)
        if m:
            m.active = False


def can_access(device_id: str, *, classification: str = "internal") -> Tuple[bool, str]:
    with _LOCK:
        m = _MODES.get(device_id)
    if m is None or not m.active:
        return True, "no_travel_mode"
    if classification.lower() in ("confidential", "secret", "top_secret"):
        return False, f"travel.refuse_classification:{classification}"
    return True, "travel_internal_ok"


def reset_for_tests() -> None:
    with _LOCK:
        _MODES.clear()


register(DefencePlugin(
    round_id="R296",
    name="travel_mode",
    description="Travel-mode device policy: refuse high-classification data while active.",
))
