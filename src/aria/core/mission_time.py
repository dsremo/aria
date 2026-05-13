"""Mission time system with multiple time scales.

Provides conversions between astronomical time scales needed for
precision orbit computation and mission operations:

- UTC: civil time, used for ground operations and timestamps
- TAI: International Atomic Time, continuous (no leap seconds)
- TT:  Terrestrial Time = TAI + 32.184s (used in ephemerides)
- TDB: Barycentric Dynamical Time (used in JPL ephemerides)
- MET: Mission Elapsed Time (seconds since launch)
- SYR: Simulation years (ARIA's internal mission clock)

Time system handling studied from Skyfield timelib.py (MIT) and
Orekit TimeScalesFactory (Apache 2.0, Java).

For interstellar missions, the distinction between TT and TDB matters:
at 0.1c, the accumulated difference over 100 years is ~1.6 ms due to
gravitational time dilation from the Sun. Small, but it affects
navigation precision for Earth comms.

References:
    IAU 2006 Resolution B3: definition of TDB
    Seidelmann, P.K. (ed.) (1992). "Explanatory Supplement to the
    Astronomical Almanac." University Science Books. Ch. 2.
    Skyfield timelib.py: time scale conversions (MIT license)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


# ── Constants ────────────────────────────────────────────────────

# TAI - UTC offset as of 2025 (37 leap seconds since 1972)
# Updated when new leap seconds are announced by IERS
_TAI_UTC_OFFSET_S = 37.0  # IAU/IERS Bulletin C (2017-01-01)

# TT = TAI + 32.184s (by definition, IAU 1991 Resolution A4)
_TT_TAI_OFFSET_S = 32.184

# TDB - TT: periodic term (Fairhead & Bretagnon 1990)
# TDB ≈ TT + 0.001658*sin(g) + 0.000014*sin(2g)
# where g = 357.53° + 35999.050°*T (mean anomaly of Earth)
_TDB_AMPLITUDE_S = 0.001658  # Fairhead & Bretagnon 1990 A&A 229 240

# J2000.0 epoch in Julian Date
_J2000_JD = 2451545.0  # 2000-01-01 12:00:00 TT

# Seconds per Julian year
_YEAR_S = 365.25 * 86400.0

# Julian century
_CENTURY_S = 36525.0 * 86400.0


@dataclass
class MissionTime:
    """A point in time with multiple time scale representations.

    The canonical representation is TT (Terrestrial Time) as a Julian
    Date. All other scales are derived from this.
    """
    tt_jd: float           # Julian Date in TT scale
    met_s: float = 0.0     # Mission Elapsed Time [seconds]
    sim_yr: float = 0.0    # Simulation years (ARIA internal)

    @classmethod
    def from_utc(cls, year: int, month: int = 1, day: int = 1,
                 hour: int = 0, minute: int = 0, second: float = 0.0) -> MissionTime:
        """Create from UTC calendar date."""
        jd_utc = _calendar_to_jd(year, month, day, hour, minute, second)
        jd_tt = jd_utc + (_TAI_UTC_OFFSET_S + _TT_TAI_OFFSET_S) / 86400.0
        return cls(tt_jd=jd_tt)

    @classmethod
    def from_j2000_years(cls, years: float) -> MissionTime:
        """Create from years since J2000.0."""
        jd_tt = _J2000_JD + years * 365.25
        return cls(tt_jd=jd_tt, sim_yr=years)

    @classmethod
    def from_met(cls, met_s: float, launch_jd_tt: float) -> MissionTime:
        """Create from Mission Elapsed Time."""
        jd_tt = launch_jd_tt + met_s / 86400.0
        return cls(tt_jd=jd_tt, met_s=met_s)

    # ── Time scale properties ────────────────────────────────

    @property
    def tt(self) -> float:
        """Terrestrial Time as Julian Date."""
        return self.tt_jd

    @property
    def tai_jd(self) -> float:
        """International Atomic Time as Julian Date."""
        return self.tt_jd - _TT_TAI_OFFSET_S / 86400.0

    @property
    def utc_jd(self) -> float:
        """UTC as Julian Date (approximate — ignores future leap seconds)."""
        return self.tai_jd - _TAI_UTC_OFFSET_S / 86400.0

    @property
    def tdb_jd(self) -> float:
        """Barycentric Dynamical Time as Julian Date.

        TDB ≈ TT + 0.001658*sin(g) where g is Earth's mean anomaly.
        Fairhead & Bretagnon (1990) A&A 229 240.
        """
        T = (self.tt_jd - _J2000_JD) / 36525.0  # Julian centuries from J2000
        g = math.radians(357.53 + 35999.050 * T)  # Earth mean anomaly
        dt_s = _TDB_AMPLITUDE_S * math.sin(g) + 0.000014 * math.sin(2 * g)
        return self.tt_jd + dt_s / 86400.0

    @property
    def j2000_centuries(self) -> float:
        """Julian centuries since J2000.0 in TT."""
        return (self.tt_jd - _J2000_JD) / 36525.0

    @property
    def j2000_years(self) -> float:
        """Julian years since J2000.0."""
        return (self.tt_jd - _J2000_JD) / 365.25

    @property
    def unix_s(self) -> float:
        """Approximate Unix timestamp (seconds since 1970-01-01 UTC)."""
        return (self.utc_jd - 2440587.5) * 86400.0

    # ── Arithmetic ───────────────────────────────────────────

    def advance_seconds(self, dt_s: float) -> MissionTime:
        """Return a new MissionTime advanced by dt_s seconds."""
        return MissionTime(
            tt_jd=self.tt_jd + dt_s / 86400.0,
            met_s=self.met_s + dt_s,
            sim_yr=self.sim_yr + dt_s / _YEAR_S,
        )

    def advance_years(self, dy: float) -> MissionTime:
        """Return a new MissionTime advanced by dy Julian years."""
        dt_s = dy * _YEAR_S
        return self.advance_seconds(dt_s)

    def difference_s(self, other: MissionTime) -> float:
        """Time difference in seconds (self - other)."""
        return (self.tt_jd - other.tt_jd) * 86400.0

    def __sub__(self, other: MissionTime) -> float:
        """Returns difference in seconds."""
        return self.difference_s(other)

    def __repr__(self) -> str:
        return f"MissionTime(tt_jd={self.tt_jd:.6f}, sim_yr={self.sim_yr:.3f})"


# ── Calendar ↔ Julian Date ───────────────────────────────────────

def _calendar_to_jd(
    year: int, month: int, day: int,
    hour: int = 0, minute: int = 0, second: float = 0.0
) -> float:
    """Convert calendar date to Julian Date.

    Valid for dates after October 15, 1582 (Gregorian calendar).
    Algorithm from Meeus (1991) "Astronomical Algorithms" Ch. 7.
    """
    if month <= 2:
        year -= 1
        month += 12

    A = int(year / 100)
    B = 2 - A + int(A / 4)

    jd = (int(365.25 * (year + 4716)) + int(30.6001 * (month + 1))
          + day + B - 1524.5)
    jd += (hour + minute / 60.0 + second / 3600.0) / 24.0

    return jd


def jd_to_calendar(jd: float) -> tuple[int, int, int, int, int, float]:
    """Convert Julian Date to calendar (year, month, day, hour, minute, second).

    Meeus (1991) Ch. 7.
    """
    jd += 0.5
    Z = int(jd)
    F = jd - Z

    if Z < 2299161:
        A = Z
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - int(alpha / 4)

    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)

    day = B - D - int(30.6001 * E)
    month = E - 1 if E < 14 else E - 13
    year = C - 4716 if month > 2 else C - 4715

    hour = int(F * 24)
    minute = int((F * 24 - hour) * 60)
    second = ((F * 24 - hour) * 60 - minute) * 60

    return year, month, day, hour, minute, second
