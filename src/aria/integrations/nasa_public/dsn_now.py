"""NASA Deep Space Network — live antenna / spacecraft contact state.

DSN-Now publishes XML at ``https://eyes.nasa.gov/dsn/data/dsn.xml`` that
refreshes ~every 5 seconds with the antenna pointings and downlink/uplink
state for every active interplanetary spacecraft. We pull the same feed
behind a 30-second TTL cache (5 s would hammer the upstream, 30 s is
plenty for a UI overlay) and parse the relevant subset:

  - station name (Goldstone / Madrid / Canberra)
  - antenna ID (DSS-XX)
  - configured target spacecraft
  - downlink data rate (bits/s)
  - signal strength (dBm)
  - one-way light time (s)

When the upstream is unreachable, the function returns an empty list with
``source = "offline"`` so the caller renders "no contact data" gracefully.

Roadmap Track 1 Phase 3 — see docs/ROADMAP_THREE_GAPS.md.
"""

from __future__ import annotations

import asyncio
import time
import xml.etree.ElementTree as ET  # noqa: S405 (only XMLParseError caught — actual parse runs through safe_xml_fromstring)
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aria.security.guard import XMLDisallowed, safe_xml_fromstring


DSN_NOW_URL = "https://eyes.nasa.gov/dsn/data/dsn.xml"
_CACHE: Dict[str, Any] = {"fetched_at_wall": 0.0, "data": None, "source": "offline"}
_CACHE_TTL_S = 30.0   # NASA-friendly polling rate


@dataclass(frozen=True)
class DsnContact:
    """One antenna's current contact state."""

    site: str            # Goldstone / Madrid / Canberra
    dish: str            # DSS-XX
    spacecraft: str
    spacecraft_id: str
    downlink_data_rate_bps: Optional[float]
    uplink_data_rate_bps: Optional[float]
    signal_dbm: Optional[float]
    light_time_s: Optional[float]
    activity: str        # 'transmit' / 'receive' / 'two-way' / 'unknown'


def _site_for_dish(dish_id: str) -> str:
    """Goldstone (10/14/24/25/26), Canberra (34/35/36/43), Madrid (53/54/55/56/63/65).

    Source: NASA DSN 810-005 Network Configuration v2025.
    """
    try:
        n = int("".join(c for c in dish_id if c.isdigit()))
    except ValueError:
        return "Unknown"
    if 10 <= n <= 26:
        return "Goldstone"
    if 34 <= n <= 43:
        return "Canberra"
    if 53 <= n <= 65:
        return "Madrid"
    return "Unknown"


def _parse_float(s: Optional[str]) -> Optional[float]:
    if s is None or s.strip() in ("", "none", "n/a", "off"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_dsn_xml(xml_text: str) -> List[DsnContact]:
    """Pull <dish> + <target> + <downSignal>/<upSignal> trios out of the feed.

    The DSN-Now XML structure (verified 2026-04 schema):
        <dsn>
          <dish name="DSS-14" ...>
            <target name="Voyager 1" id="VGR1" rtlt="80123.4"/>
            <downSignal dataRate="160" power="-152.3" ... />
            <upSignal dataRate="0" power="..." />
          </dish>
          ...
        </dsn>
    """
    contacts: List[DsnContact] = []
    try:
        root = safe_xml_fromstring(xml_text)
    except (ET.ParseError, XMLDisallowed):
        return contacts

    for dish in root.findall(".//dish"):
        dish_name = dish.attrib.get("name", "DSS-??")
        target = dish.find("target")
        if target is None or not target.attrib.get("name"):
            continue
        sc_name = target.attrib["name"]
        sc_id = target.attrib.get("id", "")
        rtlt_s = _parse_float(target.attrib.get("rtlt"))
        # round-trip light time / 2 = one-way
        owlt = rtlt_s / 2.0 if rtlt_s is not None else None

        down = dish.find("downSignal")
        up = dish.find("upSignal")
        downlink_bps = _parse_float(down.attrib.get("dataRate")) if down is not None else None
        uplink_bps = _parse_float(up.attrib.get("dataRate")) if up is not None else None
        signal_dbm = _parse_float(down.attrib.get("power")) if down is not None else None

        if (downlink_bps and downlink_bps > 0) and (uplink_bps and uplink_bps > 0):
            activity = "two-way"
        elif downlink_bps and downlink_bps > 0:
            activity = "receive"
        elif uplink_bps and uplink_bps > 0:
            activity = "transmit"
        else:
            activity = "idle"

        contacts.append(
            DsnContact(
                site=_site_for_dish(dish_name),
                dish=dish_name,
                spacecraft=sc_name,
                spacecraft_id=sc_id,
                downlink_data_rate_bps=downlink_bps,
                uplink_data_rate_bps=uplink_bps,
                signal_dbm=signal_dbm,
                light_time_s=owlt,
                activity=activity,
            )
        )
    return contacts


async def _fetch_live() -> Optional[str]:
    """Best-effort live fetch with 8-second timeout."""
    try:
        import aiohttp
    except ImportError:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(DSN_NOW_URL) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception:
        return None
    return None


async def get_dsn_contacts() -> Dict[str, Any]:
    """Return the cached or freshly fetched DSN contact list.

    Output shape:
        {
          "source": "live" | "offline",
          "fetched_at_wall": <unix_s>,
          "age_s": <int>,
          "count": <int>,
          "contacts": [<DsnContact dict>, ...],
        }
    """
    now = time.time()
    cached = _CACHE.get("data")
    if cached is not None and (now - _CACHE["fetched_at_wall"]) < _CACHE_TTL_S:
        return {
            "source": _CACHE["source"],
            "fetched_at_wall": round(_CACHE["fetched_at_wall"], 1),
            "age_s": int(now - _CACHE["fetched_at_wall"]),
            "count": len(cached),
            "contacts": [c.__dict__ for c in cached],
        }

    xml_text = await _fetch_live()
    if xml_text is None:
        # Keep the previous data if any so the UI doesn't flap on a single
        # network blip.
        contacts = cached or []
        source = "offline" if cached is None else _CACHE.get("source", "offline")
    else:
        contacts = _parse_dsn_xml(xml_text)
        source = "live"

    _CACHE["data"] = contacts
    _CACHE["fetched_at_wall"] = now
    _CACHE["source"] = source
    return {
        "source": source,
        "fetched_at_wall": round(now, 1),
        "age_s": 0,
        "count": len(contacts),
        "contacts": [c.__dict__ for c in contacts],
    }


def get_dsn_contacts_sync() -> Dict[str, Any]:
    """Synchronous wrapper for ad-hoc use (CLI / tests)."""
    return asyncio.run(get_dsn_contacts())
