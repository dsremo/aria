"""TLE (Two-Line Element) parser and utilities.

Parses the standard NORAD TLE format used to describe orbits of tracked
Earth satellites. TLEs are updated by USSPACECOM and distributed via
Celestrak, Space-Track.org, and other catalogs.

Format reference: https://celestrak.org/NORAD/documentation/tle-fmt.php

Example TLE:
    ISS (ZARYA)
    1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9994
    2 25544  51.6413   0.0000 0005291 132.2917  16.7083 15.49309239432456

References:
    Hoots & Roehrich (1980) Spacetrack Report 3: Models for propagation
    of NORAD element sets.
    Vallado et al. (2006) Revisiting Spacetrack Report #3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional


@dataclass
class TLE:
    """Parsed Two-Line Element set."""
    name: str
    satellite_number: int
    classification: str          # 'U' unclassified, 'C' classified, 'S' secret
    international_designator: str
    epoch: datetime
    epoch_year: int
    epoch_day: float
    mean_motion_derivative: float  # d(MM)/dt / 2 [rev/day²]
    mean_motion_second_deriv: float  # [rev/day³]
    bstar: float                 # drag coefficient [1/earth_radii]
    ephemeris_type: int
    element_number: int
    inclination_deg: float
    raan_deg: float
    eccentricity: float
    arg_perigee_deg: float
    mean_anomaly_deg: float
    mean_motion_rev_per_day: float
    revolution_number: int
    checksum_line1: int
    checksum_line2: int

    def semi_major_axis_m(self) -> float:
        """Derive semi-major axis from mean motion (Kepler's 3rd law)."""
        mu = 3.986004418e14
        n_rad_s = self.mean_motion_rev_per_day * 2 * math.pi / 86400.0
        if n_rad_s <= 0:
            return 0.0
        return (mu / n_rad_s ** 2) ** (1.0 / 3.0)

    def period_seconds(self) -> float:
        """Orbital period from mean motion."""
        if self.mean_motion_rev_per_day <= 0:
            return 0.0
        return 86400.0 / self.mean_motion_rev_per_day

    def altitude_perigee_km(self) -> float:
        """Perigee altitude above Earth surface [km]."""
        a = self.semi_major_axis_m()
        r_earth = 6378137.0
        return (a * (1 - self.eccentricity) - r_earth) / 1000.0

    def altitude_apogee_km(self) -> float:
        """Apogee altitude above Earth surface [km]."""
        a = self.semi_major_axis_m()
        r_earth = 6378137.0
        return (a * (1 + self.eccentricity) - r_earth) / 1000.0


def parse_tle(line1: str, line2: str, name: str = "") -> TLE:
    """Parse a TLE from two (or three) text lines.

    The lines must be exactly 69 characters each, per the NORAD spec.
    Supports both 2-line (no name) and 3-line (with name) formats.

    Raises:
        ValueError if the lines don't match the expected format.
    """
    if len(line1) != 69 or len(line2) != 69:
        raise ValueError(f"TLE lines must be 69 chars; got {len(line1)}/{len(line2)}")
    if line1[0] != "1":
        raise ValueError("Line 1 must start with '1'")
    if line2[0] != "2":
        raise ValueError("Line 2 must start with '2'")

    # Line 1 fields
    sat_num = int(line1[2:7])
    classification = line1[7]
    intl_designator = line1[9:17].strip()

    # Epoch
    epoch_year_2 = int(line1[18:20])
    epoch_year = 2000 + epoch_year_2 if epoch_year_2 < 57 else 1900 + epoch_year_2
    epoch_day = float(line1[20:32])

    # Mean motion derivatives
    mm_deriv = float(line1[33:43])
    # Second derivative in NORAD's "assumed leading decimal" format
    mm_second = _parse_assumed_decimal(line1[44:52])
    bstar = _parse_assumed_decimal(line1[53:61])

    ephemeris_type = int(line1[62])
    element_num = int(line1[64:68])
    checksum1 = int(line1[68])

    # Line 2 fields
    if int(line2[2:7]) != sat_num:
        raise ValueError("Satellite numbers don't match between lines")

    inclination = float(line2[8:16])
    raan = float(line2[17:25])
    ecc_str = line2[26:33]
    eccentricity = float("0." + ecc_str)
    arg_perigee = float(line2[34:42])
    mean_anomaly = float(line2[43:51])
    mean_motion = float(line2[52:63])
    revolution = int(line2[63:68])
    checksum2 = int(line2[68])

    # Construct epoch datetime
    jan1 = datetime(epoch_year, 1, 1, tzinfo=timezone.utc)
    epoch_dt = jan1 + timedelta(days=epoch_day - 1)

    return TLE(
        name=name.strip(),
        satellite_number=sat_num,
        classification=classification,
        international_designator=intl_designator,
        epoch=epoch_dt,
        epoch_year=epoch_year,
        epoch_day=epoch_day,
        mean_motion_derivative=mm_deriv,
        mean_motion_second_deriv=mm_second,
        bstar=bstar,
        ephemeris_type=ephemeris_type,
        element_number=element_num,
        inclination_deg=inclination,
        raan_deg=raan,
        eccentricity=eccentricity,
        arg_perigee_deg=arg_perigee,
        mean_anomaly_deg=mean_anomaly,
        mean_motion_rev_per_day=mean_motion,
        revolution_number=revolution,
        checksum_line1=checksum1,
        checksum_line2=checksum2,
    )


def parse_tle_text(text: str) -> List[TLE]:
    """Parse multi-TLE text file (name + 2 lines per satellite)."""
    tles = []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    i = 0
    while i < len(lines):
        # Skip non-TLE lines (comments, blanks)
        if i + 1 < len(lines) and lines[i][0] not in ("1", "2"):
            name = lines[i]
            if i + 2 < len(lines):
                try:
                    tle = parse_tle(lines[i + 1], lines[i + 2], name)
                    tles.append(tle)
                    i += 3
                    continue
                except ValueError:
                    i += 1
                    continue
        # 2-line format (no name)
        elif i + 1 < len(lines) and lines[i][0] == "1" and lines[i + 1][0] == "2":
            try:
                tle = parse_tle(lines[i], lines[i + 1])
                tles.append(tle)
                i += 2
                continue
            except ValueError:
                pass
        i += 1
    return tles


def _parse_assumed_decimal(s: str) -> float:
    """Parse NORAD's space-saving decimal format.

    '12345-3' → 0.12345e-3 = 1.2345e-5
    ' 12345-3' → 0.12345e-3
    '-12345-3' → -0.12345e-3
    """
    s = s.strip()
    if not s or s == "00000-0" or s == "+00000-0":
        return 0.0

    sign = 1.0
    if s[0] == "-":
        sign = -1.0
        s = s[1:]
    elif s[0] == "+":
        s = s[1:]

    # Find exponent sign
    for i in range(len(s) - 1, 0, -1):
        if s[i] in ("+", "-"):
            mantissa_str = s[:i]
            exponent = int(s[i:])
            try:
                return sign * float("0." + mantissa_str) * 10 ** exponent
            except ValueError:
                return 0.0

    try:
        return sign * float(s)
    except ValueError:
        return 0.0
