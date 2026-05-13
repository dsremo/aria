"""
Core data types for the conjunction prediction system.

All units follow astrodynamics convention:
  - Distances: km
  - Velocities: km/s
  - Angles: radians (internally), degrees only at I/O boundaries
  - Time: datetime (UTC)
  - Mass: kg
"""

from __future__ import annotations

import enum
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np


class RiskLevel(enum.Enum):
    GREEN = "GREEN"  # Pc < 1e-5 — no action
    YELLOW = "YELLOW"  # 1e-5 ≤ Pc < 1e-4 — monitor
    RED = "RED"  # Pc ≥ 1e-4 — maneuver required


class ObjectType(enum.Enum):
    PAYLOAD = "PAYLOAD"
    DEBRIS = "DEBRIS"
    ROCKET_BODY = "ROCKET_BODY"
    UNKNOWN = "UNKNOWN"


class CoordinateFrame(enum.Enum):
    TEME = "TEME"  # True Equator Mean Equinox (SGP4 native output)
    ECI_J2000 = "ECI_J2000"  # Earth-Centered Inertial, J2000 epoch
    ECEF = "ECEF"  # Earth-Centered Earth-Fixed (ITRF)
    RTN = "RTN"  # Radial-Transverse-Normal (relative frame)


@dataclass
class StateVector:
    """Position and velocity of an object at a specific epoch."""

    position: np.ndarray  # [x, y, z] km
    velocity: np.ndarray  # [vx, vy, vz] km/s
    epoch: datetime
    frame: CoordinateFrame = CoordinateFrame.TEME

    def __post_init__(self):
        self.position = np.asarray(self.position, dtype=np.float64)
        self.velocity = np.asarray(self.velocity, dtype=np.float64)

    @property
    def speed(self) -> float:
        """Magnitude of velocity vector (km/s)."""
        return float(np.linalg.norm(self.velocity))

    @property
    def altitude_km(self) -> float:
        """Altitude above Earth's equatorial surface (km). Approximate — spherical Earth."""
        from aria.conjunction.core.constants import R_EARTH_KM

        return float(np.linalg.norm(self.position)) - R_EARTH_KM


@dataclass
class OrbitalElements:
    """Classical Keplerian orbital elements."""

    semi_major_axis: float  # km
    eccentricity: float
    inclination: float  # rad
    raan: float  # rad — Right Ascension of Ascending Node
    arg_perigee: float  # rad — Argument of Perigee
    true_anomaly: float  # rad
    epoch: datetime

    @property
    def apogee_radius(self) -> float:
        """Apogee distance from Earth center (km)."""
        return self.semi_major_axis * (1.0 + self.eccentricity)

    @property
    def perigee_radius(self) -> float:
        """Perigee distance from Earth center (km)."""
        return self.semi_major_axis * (1.0 - self.eccentricity)

    @property
    def apogee_altitude(self) -> float:
        """Apogee altitude above equatorial surface (km)."""
        from aria.conjunction.core.constants import R_EARTH_KM

        return self.apogee_radius - R_EARTH_KM

    @property
    def perigee_altitude(self) -> float:
        """Perigee altitude above equatorial surface (km)."""
        from aria.conjunction.core.constants import R_EARTH_KM

        return self.perigee_radius - R_EARTH_KM

    @property
    def period_minutes(self) -> float:
        """Orbital period (minutes)."""
        import math

        from aria.conjunction.core.constants import MU_EARTH_KM

        return 2.0 * math.pi * math.sqrt(self.semi_major_axis**3 / MU_EARTH_KM) / 60.0

    @property
    def mean_motion_rad_per_s(self) -> float:
        """Mean motion (rad/s)."""
        import math

        from aria.conjunction.core.constants import MU_EARTH_KM

        return math.sqrt(MU_EARTH_KM / self.semi_major_axis**3)


@dataclass
class SpaceObject:
    """A tracked space object with its TLE and derived orbital data."""

    norad_id: str  # Alpha-5 compatible (e.g., "25544" or "A1234")
    name: str
    tle_line1: str
    tle_line2: str
    object_type: ObjectType = ObjectType.UNKNOWN
    rcs_size: str = "MEDIUM"  # "SMALL", "MEDIUM", "LARGE"
    radius_m: float = 1.0  # hard-body radius in meters for Pc
    elements: OrbitalElements | None = None
    satellite: Any = None  # sgp4.api.Satrec object (set during parsing)
    # P0-E6: TLE epoch for age validation. Set by TLE parser from line 1, columns 18-32.
    # SGP4 accuracy: ~1 km error at 1 day, ~10 km at 1 week.
    tle_epoch: datetime | None = None

    @property
    def radius_km(self) -> float:
        return self.radius_m / 1000.0

    @property
    def tle_age_days(self) -> float | None:
        """Days since TLE epoch. None if tle_epoch not set."""
        if self.tle_epoch is None:
            return None
        now = datetime.now(tz=timezone.utc)
        utc = timezone.utc
        epoch = self.tle_epoch if self.tle_epoch.tzinfo else self.tle_epoch.replace(tzinfo=utc)
        return (now - epoch).total_seconds() / 86400.0

    def check_tle_age(self) -> None:
        """Validate TLE age. Warns if >3 days, raises ValueError if >7 days.

        P0-E6 (Expert 6, Wertz): Stale TLE on a debris object can make a genuine
        near-miss appear safe. Policy: warn at 3 days, reject at 7 days.
        """
        age = self.tle_age_days
        if age is None:
            warnings.warn(
                f"SpaceObject {self.norad_id} ({self.name}): tle_epoch not set. "
                "Cannot validate TLE age — SGP4 accuracy unknown.",
                stacklevel=2,
            )
            return
        if age > 7.0:
            raise ValueError(
                f"TLE for {self.norad_id} ({self.name}) is {age:.1f} days old "
                f"(>7 days). SGP4 positional error may exceed 10 km. "
                "Refresh TLE from SpaceTrack/CelesTrak before use."
            )
        if age > 3.0:
            warnings.warn(
                f"TLE for {self.norad_id} ({self.name}) is {age:.1f} days old "
                f"(>3 days). SGP4 positional error may exceed 3 km. "
                "Consider refreshing from SpaceTrack.",
                stacklevel=2,
            )


@dataclass
class CloseApproach:
    """A detected close approach event between two space objects."""

    primary: SpaceObject
    secondary: SpaceObject
    tca: datetime  # Time of Closest Approach
    miss_distance_km: float  # total miss distance
    miss_distance_rtn: np.ndarray  # [R, T, N] components in km
    relative_velocity_km_s: float  # relative speed at TCA
    relative_position: np.ndarray  # relative position vector at TCA (km, ECI)
    relative_velocity_vec: np.ndarray  # relative velocity vector at TCA (km/s, ECI)
    primary_state: StateVector | None = None
    secondary_state: StateVector | None = None
    primary_covariance: np.ndarray | None = None  # 6x6 or 3x3 in ECI
    secondary_covariance: np.ndarray | None = None
    probability_of_collision: float | None = None
    mahalanobis_distance: float | None = None
    risk_level: RiskLevel = RiskLevel.GREEN
    # P0-E1: Multi-method Pc results for operator transparency.
    # Populated by PcCalculator.calculate_all_methods(). If methods disagree
    # by >1 order of magnitude, pc_method_disagreement is set True.
    pc_foster: float | None = None
    pc_chan: float | None = None
    pc_monte_carlo: float | None = None
    pc_method_disagreement: bool = False

    def __post_init__(self):
        self.miss_distance_rtn = np.asarray(self.miss_distance_rtn, dtype=np.float64)
        self.relative_position = np.asarray(self.relative_position, dtype=np.float64)
        self.relative_velocity_vec = np.asarray(self.relative_velocity_vec, dtype=np.float64)

    @property
    def combined_radius_km(self) -> float:
        return self.primary.radius_km + self.secondary.radius_km


@dataclass
class ConjunctionDataMessage:
    """CCSDS Conjunction Data Message (CDM) v2.0 — key fields."""

    # Header
    ccsds_cdm_vers: str = "2.0"
    # R65 (2026-04-24): datetime.utcnow() is deprecated (Py 3.12+) and
    # returned naive datetimes — mixing naive + aware in CCSDS CDM TCA
    # comparisons silently produced wrong deltas.  Aware UTC now.
    creation_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    originator: str = "DSREMO"
    message_id: str = ""

    # Relative metadata
    tca: datetime | None = None
    miss_distance_km: float = 0.0
    relative_speed_km_s: float = 0.0
    relative_position_rtn: np.ndarray = field(default_factory=lambda: np.zeros(3))
    relative_velocity_rtn: np.ndarray = field(default_factory=lambda: np.zeros(3))
    collision_probability: float = 0.0
    collision_probability_method: str = "FOSTER-1992"

    # Object 1 (primary)
    object1_designator: str = ""
    object1_name: str = ""
    object1_catalog_name: str = "SATCAT"
    object1_object_type: str = ""
    object1_state: StateVector | None = None
    object1_covariance: np.ndarray | None = None  # 6x6
    object1_hard_body_radius_m: float = 0.0

    # Object 2 (secondary)
    object2_designator: str = ""
    object2_name: str = ""
    object2_catalog_name: str = "SATCAT"
    object2_object_type: str = ""
    object2_state: StateVector | None = None
    object2_covariance: np.ndarray | None = None  # 6x6
    object2_hard_body_radius_m: float = 0.0
    # P2-E6 (Wertz): If Object 2 is a defunct satellite (non-maneuverable),
    # the primary spacecraft bears full responsibility for the avoidance maneuver.
    # If both objects are active, ITU RR No. 22 requires coordination.
    # This field enables the UI to show the correct operator action.
    object2_maneuverable: bool = False
    object2_operator_contact: str | None = None  # e.g. "ops@spacex.com" or "JSPOC coordination"
