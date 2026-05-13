"""
TLE (Two-Line Element Set) parser.

Handles:
  - Standard 2-line and 3-line (with name) TLE formats
  - Alpha-5 numbering for NORAD IDs > 99,999
  - Checksum validation
  - Orbital element extraction directly from TLE fields
  - Batch parsing of multi-object TLE files

TLE Format Reference (NORAD/Space-Track):
  Line 1: 1 NNNNNC NNNNNAAA NNNNN.NNNNNNNN +.NNNNNNNN +NNNNN-N +NNNNN-N N NNNNN
  Line 2: 2 NNNNN NNN.NNNN NNN.NNNN NNNNNNN NNN.NNNN NNN.NNNN NN.NNNNNNNNNNNNNN
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from sgp4.api import WGS72, Satrec

from aria.conjunction.core.constants import MU_EARTH_KM, R_EARTH_KM, TWO_PI
from aria.conjunction.core.types import ObjectType, OrbitalElements, SpaceObject


class TLEParseError(Exception):
    """Raised when a TLE cannot be parsed."""


def classify_object_type(name: str) -> ObjectType:
    """Classify object type from its TLE catalog name.

    Parsing rules derived from Space-Track naming conventions:
      - 'DEB' anywhere → DEBRIS (e.g., "COSMOS 2251 DEB", "FENGYUN 1C DEB")
      - 'DEBRIS' → DEBRIS
      - 'R/B' → ROCKET_BODY (e.g., "CZ-2C R/B")
      - 'ROCKET' → ROCKET_BODY
      - Prefix 'SL-' → ROCKET_BODY (Soviet rocket stages)
      - Prefix 'CZ-' alone → ROCKET_BODY (Chinese Long March stages)
      - 'AKM' → ROCKET_BODY (Apogee Kick Motor)
      - Everything else → PAYLOAD
    """
    upper = name.upper().strip()
    if not upper:
        return ObjectType.UNKNOWN

    # Debris indicators
    if ' DEB' in upper or upper.startswith('DEB ') or upper == 'DEB':
        return ObjectType.DEBRIS
    if 'DEBRIS' in upper:
        return ObjectType.DEBRIS
    if 'COOLANT' in upper:  # NaK coolant droplets
        return ObjectType.DEBRIS
    if 'WESTFORD' in upper:  # Westford Needles
        return ObjectType.DEBRIS

    # Rocket body indicators
    if ' R/B' in upper or upper.endswith(' R/B') or upper.startswith('R/B'):
        return ObjectType.ROCKET_BODY
    if 'ROCKET' in upper:
        return ObjectType.ROCKET_BODY
    for prefix in ('SL-', 'CZ-', 'BREEZE', 'FREGAT', 'CENTAUR', 'DELTA ', 'ARIANE ',
                    'FALCON ', 'H-2A ', 'PSLV ', 'GSLV ', 'PROTON ', 'ATLAS '):
        if upper.startswith(prefix) and ' DEB' not in upper:
            # Only if it's the stage itself, not debris from it
            if 'DEB' not in upper:
                return ObjectType.ROCKET_BODY
    if upper.endswith(' AKM'):
        return ObjectType.ROCKET_BODY

    return ObjectType.PAYLOAD


# Hard-body radius estimates by object type and RCS size.
# Sources: ESA DISCOS average cross-sections, IADC guidelines.
# Radius = sqrt(A_cross / π) for spherical approximation.
RADIUS_TABLE_M = {
    # (ObjectType, RCS size) → radius in meters
    # RCS: SMALL < 0.1 m², MEDIUM 0.1-1.0 m², LARGE > 1.0 m²
    (ObjectType.PAYLOAD, "SMALL"): 0.5,
    (ObjectType.PAYLOAD, "MEDIUM"): 1.5,
    (ObjectType.PAYLOAD, "LARGE"): 3.0,
    (ObjectType.DEBRIS, "SMALL"): 0.05,
    (ObjectType.DEBRIS, "MEDIUM"): 0.15,
    (ObjectType.DEBRIS, "LARGE"): 0.5,
    (ObjectType.ROCKET_BODY, "SMALL"): 1.0,
    (ObjectType.ROCKET_BODY, "MEDIUM"): 2.0,
    (ObjectType.ROCKET_BODY, "LARGE"): 4.0,
    (ObjectType.UNKNOWN, "SMALL"): 0.1,
    (ObjectType.UNKNOWN, "MEDIUM"): 0.5,
    (ObjectType.UNKNOWN, "LARGE"): 1.5,
}

# Special large objects with known radii (meters)
KNOWN_RADII_M = {
    "25544": 54.0,   # ISS — 109m x 73m, effective sphere ~54m radius
    "48274": 10.0,   # CSS Tianhe
    "20580": 6.0,    # Hubble Space Telescope
}


def _estimate_radius(norad_id: str, name: str, obj_type: ObjectType,
                     rcs_size: str = "MEDIUM") -> float:
    """Estimate hard-body radius from object metadata.

    Priority: known object table → type+RCS lookup → default.
    """
    if norad_id in KNOWN_RADII_M:
        return KNOWN_RADII_M[norad_id]
    return RADIUS_TABLE_M.get((obj_type, rcs_size), 0.5)


# Alpha-5 decoding: letter in first position maps to digit offset
# A=10, B=11, ..., Z=35 (base-36 first character)
_ALPHA5_MAP = {chr(i + 65): i + 10 for i in range(26)}


def decode_alpha5(catalog_id: str) -> int:
    """Decode Alpha-5 NORAD catalog number to integer.

    Standard 5-digit: "25544" → 25544
    Alpha-5 extended: "A1234" → 101234 (A=10, so 10*10000 + 1234)
    """
    catalog_id = catalog_id.strip()
    if not catalog_id:
        raise TLEParseError("Empty catalog ID")
    first = catalog_id[0]
    if first.isdigit():
        return int(catalog_id)
    if first.upper() in _ALPHA5_MAP:
        return _ALPHA5_MAP[first.upper()] * 10000 + int(catalog_id[1:])
    raise TLEParseError(f"Invalid Alpha-5 catalog ID: {catalog_id}")


def encode_alpha5(norad_id: int) -> str:
    """Encode integer NORAD ID to Alpha-5 string.

    25544 → "25544"
    101234 → "A1234"
    """
    if norad_id < 100000:
        return f"{norad_id:05d}"
    prefix = norad_id // 10000
    suffix = norad_id % 10000
    # Reverse lookup: 10→A, 11→B, ...
    letter = chr(prefix - 10 + 65)
    return f"{letter}{suffix:04d}"


def _tle_checksum(line: str) -> int:
    """Compute TLE line checksum (modulo 10 of digit sum, '-' counts as 1)."""
    s = 0
    for ch in line[:68]:
        if ch.isdigit():
            s += int(ch)
        elif ch == "-":
            s += 1
    return s % 10


def _validate_checksum(line: str, line_num: int) -> None:
    """Validate TLE line checksum."""
    if len(line) < 69:
        raise TLEParseError(f"Line {line_num} too short: {len(line)} chars (need 69)")
    expected = int(line[68])
    computed = _tle_checksum(line)
    if computed != expected:
        raise TLEParseError(
            f"Line {line_num} checksum mismatch: computed {computed}, expected {expected}"
        )


def _parse_epoch(line1: str) -> datetime:
    """Extract epoch from TLE line 1 (columns 18-32).

    Format: YYDDD.DDDDDDDD
      YY = 2-digit year (57-99 → 1957-1999, 00-56 → 2000-2056)
      DDD.DDDDDDDD = fractional day of year

    Returns a timezone-aware datetime in UTC.  R44 fix: TLE epochs are
    UTC by definition; returning naïve datetimes broke downstream age
    checks that compared against UTC-aware ``datetime.now(tz=UTC)``.
    """
    from datetime import timezone as _tz
    epoch_str = line1[18:32].strip()
    year_2d = int(epoch_str[:2])
    day_frac = float(epoch_str[2:])

    year = year_2d + (1900 if year_2d >= 57 else 2000)
    jan1 = datetime(year, 1, 1, tzinfo=_tz.utc)
    return jan1 + timedelta(days=day_frac - 1.0)


def _parse_mean_motion_to_sma(
    mean_motion_rev_per_day: float,
    eccentricity: float = 0.0,
    inclination_rad: float = 0.0,
) -> float:
    """Convert Brouwer mean motion (from TLE) to osculating semi-major axis (km).

    TLE mean motion is the Brouwer (Kozai) mean motion, not the Keplerian
    mean motion. The relationship includes J2 corrections:

      n_kozai = n_kepler × (1 + δ)

    where δ depends on J2, eccentricity, and inclination. For LEO, this
    correction is ~0.1%, which is ~7 km in SMA — significant for screening.

    We first compute the mean SMA from Brouwer mean motion, then apply the
    J2 first-order correction to get the osculating SMA.
    """
    from aria.conjunction.core.constants import J2

    n_rad_per_s = mean_motion_rev_per_day * TWO_PI / SECONDS_PER_DAY

    # Mean (Brouwer) semi-major axis
    a_mean = (MU_EARTH_KM / (n_rad_per_s**2)) ** (1.0 / 3.0)

    # J2 correction: osculating a from Brouwer mean a
    # a_osc ≈ a_mean × (1 + δ)
    # where δ = (3 J2 R_E²) / (2 a² (1-e²)^(3/2)) × (1 - 3sin²i/2)
    if a_mean > 0 and eccentricity < 1.0:
        p = a_mean * (1 - eccentricity**2)
        if p > 0:
            sin_i = math.sin(inclination_rad)
            delta = (3 * J2 * R_EARTH_KM**2) / (2 * p**2) * (1 - 1.5 * sin_i**2)
            a_osc = a_mean * (1 + delta)
            return a_osc

    return a_mean


# Need this constant here to avoid circular import at module level
SECONDS_PER_DAY = 86400.0


class TLEParser:
    """Parse TLE strings into SpaceObject instances."""

    @staticmethod
    def parse_tle(
        line1: str,
        line2: str,
        name: str = "",
        object_type: ObjectType = ObjectType.UNKNOWN,
        validate_checksum: bool = True,
    ) -> SpaceObject:
        """Parse a single TLE (2 lines) into a SpaceObject.

        Args:
            line1: TLE line 1
            line2: TLE line 2
            name: Object name (from 3-line TLE or catalog)
            object_type: Classification of the object
            validate_checksum: Whether to validate TLE checksums

        Returns:
            SpaceObject with parsed elements and sgp4 Satrec
        """
        line1 = line1.strip()
        line2 = line2.strip()

        if validate_checksum:
            _validate_checksum(line1, 1)
            _validate_checksum(line2, 2)

        # Verify line numbers
        if line1[0] != "1":
            raise TLEParseError(f"Line 1 does not start with '1': {line1[:5]}")
        if line2[0] != "2":
            raise TLEParseError(f"Line 2 does not start with '2': {line2[:5]}")

        # Extract NORAD catalog number (Alpha-5 compatible)
        norad_str = line1[2:7].strip()
        norad_id = str(decode_alpha5(norad_str))

        # Parse orbital elements from line 2
        inclination_deg = float(line2[8:16].strip())
        raan_deg = float(line2[17:25].strip())
        eccentricity = float("0." + line2[26:33].strip())
        arg_perigee_deg = float(line2[34:42].strip())
        mean_anomaly_deg = float(line2[43:51].strip())
        mean_motion_rev_day = float(line2[52:63].strip())

        # Derive osculating semi-major axis from Brouwer mean motion
        semi_major_axis = _parse_mean_motion_to_sma(
            mean_motion_rev_day,
            eccentricity=eccentricity,
            inclination_rad=math.radians(inclination_deg),
        )

        # Parse epoch
        epoch = _parse_epoch(line1)

        # Convert mean anomaly to true anomaly (Newton's method on Kepler's equation)
        true_anomaly_rad = _mean_to_true_anomaly(
            math.radians(mean_anomaly_deg), eccentricity
        )

        elements = OrbitalElements(
            semi_major_axis=semi_major_axis,
            eccentricity=eccentricity,
            inclination=math.radians(inclination_deg),
            raan=math.radians(raan_deg),
            arg_perigee=math.radians(arg_perigee_deg),
            true_anomaly=true_anomaly_rad,
            epoch=epoch,
        )

        # Create sgp4 Satrec object for propagation
        satellite = Satrec.twoline2rv(line1, line2, WGS72)

        # Auto-classify object type from name if not explicitly provided
        obj_name = name.strip() or f"OBJECT-{norad_id}"
        if object_type == ObjectType.UNKNOWN:
            object_type = classify_object_type(obj_name)

        # Estimate hard-body radius from type and metadata
        radius = _estimate_radius(norad_id, obj_name, object_type)

        return SpaceObject(
            norad_id=norad_id,
            name=obj_name,
            tle_line1=line1,
            tle_line2=line2,
            object_type=object_type,
            radius_m=radius,
            elements=elements,
            satellite=satellite,
            tle_epoch=epoch,  # P0-E6: expose epoch for age validation
        )

    @staticmethod
    def parse_multi_tle(tle_text: str) -> list[SpaceObject]:
        """Parse a multi-object TLE file (3-line format with names).

        Handles both 2-line and 3-line formats:
          3-line: NAME\\n1 ...\\n2 ...
          2-line: 1 ...\\n2 ...
        """
        lines = [ln.rstrip() for ln in tle_text.strip().splitlines() if ln.strip()]
        objects = []
        i = 0

        while i < len(lines):
            # Detect if current line is a name (doesn't start with "1 " or "2 ")
            if not lines[i].startswith(("1 ", "2 ")):
                # 3-line format: name + line1 + line2
                if i + 2 >= len(lines):
                    break
                name = lines[i]
                line1 = lines[i + 1]
                line2 = lines[i + 2]
                i += 3
            else:
                # 2-line format
                if i + 1 >= len(lines):
                    break
                name = ""
                line1 = lines[i]
                line2 = lines[i + 1]
                i += 2

            try:
                obj = TLEParser.parse_tle(line1, line2, name=name)
                objects.append(obj)
            except TLEParseError:
                continue  # skip malformed entries

        return objects


def _mean_to_true_anomaly(M: float, e: float, tol: float = 1e-12, max_iter: int = 50) -> float:
    """Convert mean anomaly to true anomaly via Kepler's equation.

    Solves M = E - e*sin(E) for E (eccentric anomaly) using Newton-Raphson,
    then converts E to true anomaly ν.
    """
    # Initial guess for eccentric anomaly
    E = M + e * math.sin(M) if e < 0.8 else math.pi

    for _ in range(max_iter):
        dE = (E - e * math.sin(E) - M) / (1.0 - e * math.cos(E))
        E -= dE
        if abs(dE) < tol:
            break

    # Eccentric anomaly → true anomaly
    nu = 2.0 * math.atan2(
        math.sqrt(1.0 + e) * math.sin(E / 2.0),
        math.sqrt(1.0 - e) * math.cos(E / 2.0),
    )
    return nu
