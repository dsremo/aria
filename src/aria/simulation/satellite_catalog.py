"""Curated catalog of famous tracked Earth satellites (TLEs).

Hardcoded so the planetarium has known objects to render even without
a live Celestrak fetch. TLEs are public data (USSPACECOM via Celestrak,
unrestricted use) but they decay quickly — refresh by pasting a fresh
TLE in the TLE Parser tab and persisting via /api/satellites/refresh
(future endpoint).

Sources: Celestrak active catalog snapshots; epochs cluster around
2024-Jan to 2024-Dec for representative use. The propagator (Kepler+J2)
gives <10 km error within ~1 day of the TLE epoch — fine for sky
visualization, not for collision-avoidance work.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.simulation.tle_parser import TLE, parse_tle


# ════════════════════════════════════════════════════════════════════
#  Curated TLE list — name, line1, line2, category
#  Categories: 'crewed', 'science', 'navigation', 'comm', 'earth_obs', 'geo'
# ════════════════════════════════════════════════════════════════════

_TLE_DATA: List[Tuple[str, str, str, str]] = [
    # === REAL TLEs from Celestrak 2024-Dec snapshot (via Wayback) ===
    # Previously this list contained synthetic TLEs with epoch 24015 and
    # zeroed RAAN/mean-anomaly fields, which broke rendezvous/ground-track
    # calculations for dates other than the synthetic epoch. These are now
    # the actual TLEs Celestrak published; re-fetch via
    # scripts/fetch_celestrak_tle.py to refresh.
    ("ISS (ZARYA)",
     "1 25544U 98067A   24357.81415843  .00061122  00000+0  10662-2 0  9993",
     "2 25544  51.6377 100.8061 0005268 355.1085 147.9826 15.50107458487805",
     "crewed"),
    ("CSS (TIANHE)",
     "1 48274U 21035A   24357.81767204  .00027672  00000+0  33233-3 0  9992",
     "2 48274  41.4679  13.6319 0001982 252.7034 107.3587 15.60253132208597",
     "crewed"),
    ("HST",
     "1 20580U 90037B   24349.79952594  .00008297  00000+0  34685-3 0  9990",
     "2 20580  28.4668 211.6744 0001802 213.0977 146.9504 15.21765358704537",
     "science"),
    ("CXO (CHANDRA)",
     "1 25867U 99040B   24347.67995738  .00000403  00000+0  00000+0 0  9999",
     "2 25867  45.2638 139.9696 8693340 305.0901   0.0820  0.37810292 15235",
     "science"),
    ("XMM-NEWTON",
     "1 25989U 99066A   24349.90380838  .00000026  00000+0  00000+0 0  9990",
     "2 25989  67.0695 290.3422 4981166  74.3225   0.1184  0.50136307 20256",
     "science"),
    ("TERRA",
     "1 25994U 99068A   24349.82146083  .00001013  00000+0  21907-3 0  9991",
     "2 25994  98.0263  47.8375 0003063 136.0257 356.2870 14.60310430329400",
     "earth_obs"),
    ("GPS BIIR-2 (PRN 13)",
     "1 24876U 97035A   24256.52931729  .00000020  00000+0  00000+0 0  9998",
     "2 24876  55.6956 123.7167 0084035  53.9679 306.8950  2.00561092199062",
     "navigation"),
    ("GPS BIIR-4 (PRN 20)",
     "1 26360U 00025A   24256.96254800 -.00000026  00000+0  00000+0 0  9994",
     "2 26360  54.7379  45.3088 0039046 216.6814 184.2148  2.00572572178398",
     "navigation"),
    ("GPS BIIRM-1 (PRN 17)",
     "1 28874U 05038A   24256.31990251  .00000003  00000+0  00000+0 0  9995",
     "2 28874  55.4244 299.0215 0137641 285.0051 167.4260  2.00549596138947",
     "navigation"),
    ("FREGAT DEB",
     "1 49271U 11037PF  24356.75883163  .00025413  00000+0  53551-1 0  9990",
     "2 49271  51.6479 165.9387 0941563 163.3305 200.0857 12.24545406158116",
     "comm"),
    ("POLAR",
     "1 23802U 96013A   24349.11624299  .00000204  00000+0  00000+0 0  9994",
     "2 23802  79.2655 232.9020 5982739 227.6410  63.2968  1.29846678137718",
     "science"),
    ("SWAS",
     "1 25560U 98071A   24348.59565416  .00004496  00000+0  33575-3 0  9993",
     "2 25560  69.8960 201.4291 0005950 352.4785   7.6286 15.03527923414588",
     "science"),
    ("ODIN",
     "1 26702U 01007A   24348.48287302  .00016553  00000+0  55340-3 0  9999",
     "2 26702  97.4654   3.8013 0007519  21.9148 338.2413 15.31049248304251",
     "earth_obs"),
    ("TDRS 3",
     "1 19548U 88091B   25031.22544617 -.00000290  00000+0  00000+0 0  9995",
     "2 19548  12.9853 344.3486 0041686 341.3685 197.3331  1.00271889120358",
     "geo"),
    ("TDRS 7",
     "1 23613U 95035B   25032.87058588 -.00000194  00000+0  00000+0 0  9991",
     "2 23613  13.5848 351.6311 0023069  66.6738 112.0826  1.00267369108230",
     "geo"),
]


# ════════════════════════════════════════════════════════════════════
#  Loader (parse on first use, cache)
# ════════════════════════════════════════════════════════════════════

_CACHE: List[TLE] = []
_CATEGORIES: List[str] = []


def load_satellites() -> List[Tuple[TLE, str]]:
    """Return all catalog satellites with their category tag.

    First call parses the hardcoded TLE list; subsequent calls hit cache.
    """
    global _CACHE, _CATEGORIES
    if _CACHE:
        return list(zip(_CACHE, _CATEGORIES))
    out: List[Tuple[TLE, str]] = []
    for name, l1, l2, cat in _TLE_DATA:
        try:
            tle = parse_tle(l1, l2, name)
            out.append((tle, cat))
        except Exception:
            continue
    _CACHE = [t for t, _ in out]
    _CATEGORIES = [c for _, c in out]
    return out


def categories() -> List[str]:
    """Distinct categories present in the catalog."""
    return sorted({cat for _, cat in load_satellites()})
