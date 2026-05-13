"""Annual meteor showers — IAU-recognized peaks.

Hardcoded list of the major annual showers from the IAU Meteor Data
Center (https://www.ta3.sk/IAUC22DB/MDC2007/) — public-domain
astronomical fact. Each entry has:
  - peak month/day (UT)
  - duration window (days)
  - radiant J2000 (RA/Dec)
  - ZHR  (Zenithal Hourly Rate at peak under ideal conditions)
  - parent body (where known)
  - velocity (km/s) of meteoroids upon Earth-atmosphere entry

The list focuses on showers with ZHR ≥ 5 since those are routinely
observable. Sporadic + minor showers are out of scope.

References:
    Jenniskens, P. (2006) "Meteor Showers and their Parent Comets"
        Cambridge University Press.
    IAU MDC online catalog (open data).
    IMO Meteor Shower Calendar 2025 (Roggemans et al.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class MeteorShower:
    """A single annual meteor shower."""
    code: str            # IAU 3-letter code
    name: str            # English name
    peak_month: int      # 1..12
    peak_day: int        # day of month at peak (UT)
    activity_start_month: int
    activity_start_day: int
    activity_end_month: int
    activity_end_day: int
    radiant_ra_deg: float
    radiant_dec_deg: float
    zhr: int             # Zenithal Hourly Rate at peak
    velocity_kmps: float # geocentric velocity of meteoroid stream
    parent_body: str     # "Halley", "Encke", "Phaethon", etc. (or "")


# Major shower list, alphabetical by name. ZHR values are typical years;
# Leonids and Geminids vary widely depending on parent stream encounters.
SHOWERS: List[MeteorShower] = [
    MeteorShower("QUA", "Quadrantids",          1, 4,    1, 1,   1, 12,  230.1,  +49.7, 110, 41, "2003 EH1"),
    MeteorShower("LYR", "Lyrids",               4, 22,   4, 14,  4, 30,  271.4,  +33.6,  18, 49, "C/1861 G1 Thatcher"),
    MeteorShower("ETA", "Eta Aquariids",        5, 6,    4, 19,  5, 28,  338.1,  -1.0,   60, 66, "1P/Halley"),
    MeteorShower("CAP", "Alpha Capricornids",   7, 30,   7, 3,   8, 15,  306.7,  -10.4,  5,  23, "169P/NEAT"),
    MeteorShower("SDA", "Southern Delta Aquariids", 7, 30, 7, 12, 8, 23, 339.0,  -16.3,  25, 41, "96P/Machholz"),
    MeteorShower("PER", "Perseids",             8, 13,   7, 17,  8, 24,   48.0,  +58.0, 100, 59, "109P/Swift-Tuttle"),
    MeteorShower("DRA", "October Draconids",   10, 8,   10, 6,  10, 10,  262.0,  +54.0,  10, 20, "21P/Giacobini-Zinner"),
    MeteorShower("ORI", "Orionids",            10, 22,  10, 2,  11, 7,    95.0,  +16.0,  20, 66, "1P/Halley"),
    MeteorShower("STA", "Southern Taurids",    10, 10,   9, 7,  11, 19,   32.0,  +9.0,   5,  27, "2P/Encke"),
    MeteorShower("NTA", "Northern Taurids",    11, 12,  10, 19, 12, 10,   58.0,  +22.0,  5,  29, "2P/Encke"),
    MeteorShower("LEO", "Leonids",             11, 18,  11, 6,  11, 30,  152.0,  +22.0,  15, 71, "55P/Tempel-Tuttle"),
    MeteorShower("GEM", "Geminids",            12, 14,  12, 4,  12, 17,  112.0,  +33.0, 150, 35, "3200 Phaethon"),
    MeteorShower("URS", "Ursids",              12, 22,  12, 17, 12, 26,  217.0,  +76.0,  10, 33, "8P/Tuttle"),
]


# ════════════════════════════════════════════════════════════════════
#  Find showers active at a given date / find peaks in a date range
# ════════════════════════════════════════════════════════════════════

def _ymd_to_doy(year: int, month: int, day: int) -> int:
    """Day-of-year (1..366) for a calendar date."""
    leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    days_in_month = [31, 29 if leap else 28, 31, 30, 31, 30,
                     31, 31, 30, 31, 30, 31]
    return sum(days_in_month[:month - 1]) + day


def active_showers(year: int, month: int, day: int) -> List[MeteorShower]:
    """Showers whose activity window contains the given date.

    Handles year-wrap (Quadrantids straddle Jan 1).
    """
    doy = _ymd_to_doy(year, month, day)
    out: List[MeteorShower] = []
    for s in SHOWERS:
        start = _ymd_to_doy(year, s.activity_start_month, s.activity_start_day)
        end = _ymd_to_doy(year, s.activity_end_month, s.activity_end_day)
        if start <= end:
            if start <= doy <= end:
                out.append(s)
        else:    # wraps year boundary
            if doy >= start or doy <= end:
                out.append(s)
    return out


def peaks_in_range(year_start: int, year_end: int) -> List[tuple]:
    """All shower peaks (date, shower) inside [year_start, year_end] inclusive."""
    out: List[tuple] = []
    for y in range(year_start, year_end + 1):
        for s in SHOWERS:
            out.append(((y, s.peak_month, s.peak_day), s))
    out.sort(key=lambda x: x[0])
    return out
