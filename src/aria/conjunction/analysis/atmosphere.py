"""
Atmospheric density model using NRLMSISE-00.

NRLMSISE-00 (Naval Research Laboratory Mass Spectrometer and Incoherent
Scatter Radar Exosphere) is the standard empirical atmospheric model used
by NASA, ESA, and DoD for satellite drag prediction.

Provides:
  - Total mass density at any altitude/location/time
  - Temperature profiles
  - Density variation with solar activity (F10.7) and geomagnetic activity (Ap)
  - Drag coefficient estimation for orbital decay prediction

This replaces the constant B* drag model in SGP4 with physics-based
density computation, enabling:
  - More accurate TCA prediction during solar storms
  - Better covariance realism (density uncertainty → position uncertainty)
  - Orbital lifetime estimation for debris fragments
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

try:
    from nrlmsise00 import msise_model
    _HAS_NRLMSISE = True
except ImportError:
    _HAS_NRLMSISE = False


@dataclass
class AtmosphereResult:
    """Atmospheric conditions at a point."""

    total_mass_density_kg_m3: float  # total mass density
    temperature_exospheric_K: float  # exospheric temperature
    temperature_local_K: float  # temperature at altitude

    # Number densities (per m³)
    n_He: float = 0.0   # Helium
    n_O: float = 0.0    # Atomic oxygen
    n_N2: float = 0.0   # Molecular nitrogen
    n_O2: float = 0.0   # Molecular oxygen
    n_Ar: float = 0.0   # Argon
    n_H: float = 0.0    # Hydrogen
    n_N: float = 0.0    # Atomic nitrogen


class AtmosphericDensityModel:
    """NRLMSISE-00 atmospheric density model.

    Computes atmospheric density as a function of:
      - Altitude (km)
      - Geodetic latitude/longitude (deg)
      - Date/time (UTC)
      - Solar activity (F10.7 index)
      - Geomagnetic activity (Ap index)
    """

    def __init__(self, f107: float = 150.0, f107a: float = 150.0, ap: float = 4.0):
        """
        Args:
            f107: Daily F10.7 solar radio flux (SFU). ~70 at solar min, ~250 at max.
                  Tapping 2013 Space Weather 11 394: F10.7=150 SFU moderate activity.
            f107a: 81-day centered average F10.7.
            ap: Daily Ap geomagnetic index. Quiet=4, Storm=100+.
                Menvielle & Berthelier 1991 Rev Geophys 29 415: Ap=4 geomagnetically quiet.
        """
        if not _HAS_NRLMSISE:
            raise ImportError("nrlmsise00 package required: pip install nrlmsise00")
        self.f107 = f107
        self.f107a = f107a
        self.ap = ap

    def density(
        self,
        altitude_km: float,
        latitude_deg: float = 0.0,
        longitude_deg: float = 0.0,
        dt: datetime | None = None,
    ) -> AtmosphereResult:
        """Compute atmospheric density at a point.

        Args:
            altitude_km: Altitude above sea level (km)
            latitude_deg: Geodetic latitude (degrees)
            longitude_deg: Geodetic longitude (degrees)
            dt: Date/time (UTC). Default: 2024-01-01T12:00.

        Returns:
            AtmosphereResult with density and composition
        """
        if dt is None:
            dt = datetime(2024, 1, 1, 12, 0, 0)

        dt.timetuple().tm_yday
        ut_sec = dt.hour * 3600 + dt.minute * 60 + dt.second
        ut_sec / 3600.0 + longitude_deg / 15.0  # local solar time (hours)

        # Call NRLMSISE-00
        # msise_model returns (densities[9], temperatures[2])
        densities, temperatures = msise_model(
            dt, altitude_km, latitude_deg, longitude_deg,
            self.f107a, self.f107, self.ap,
        )

        # densities indices:
        # 0: He, 1: O, 2: N2, 3: O2, 4: Ar, 5: total mass density (g/cm³),
        # 6: H, 7: N, 8: anomalous O
        return AtmosphereResult(
            total_mass_density_kg_m3=densities[5] * 1000.0,  # g/cm³ → kg/m³
            temperature_exospheric_K=temperatures[0],
            temperature_local_K=temperatures[1],
            n_He=densities[0] * 1e6,  # /cm³ → /m³
            n_O=densities[1] * 1e6,
            n_N2=densities[2] * 1e6,
            n_O2=densities[3] * 1e6,
            n_Ar=densities[4] * 1e6,
            n_H=densities[6] * 1e6,
            n_N=densities[7] * 1e6,
        )

    def density_profile(
        self,
        alt_min_km: float = 100.0,
        alt_max_km: float = 1000.0,
        n_points: int = 100,
        latitude_deg: float = 0.0,
        dt: datetime | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute density profile across an altitude range.

        Returns:
            (altitudes_km, densities_kg_m3): arrays of length n_points
        """
        alts = np.linspace(alt_min_km, alt_max_km, n_points)
        densities = np.zeros(n_points)

        for i, alt in enumerate(alts):
            result = self.density(alt, latitude_deg, 0.0, dt)
            densities[i] = result.total_mass_density_kg_m3

        return alts, densities

    def drag_acceleration(
        self,
        altitude_km: float,
        velocity_km_s: float,
        cd: float = 2.2,         # ESTIMATE — Cd=2.2 free-molecular flow (Sentman 1961; Emmert 2015 J Geophys Res 120 585)
        area_m2: float = 10.0,   # ESTIMATE — 10 m² typical small LEO satellite cross-section
        mass_kg: float = 1000.0, # ESTIMATE — 1000 kg typical small satellite mass
        latitude_deg: float = 0.0,
        dt: datetime | None = None,
    ) -> float:
        """Compute atmospheric drag acceleration.

        a_drag = -½ × ρ × v² × Cd × A / m

        Args:
            altitude_km: Altitude (km)
            velocity_km_s: Object velocity (km/s)
            cd: Drag coefficient (typically 2.0-2.5)
            area_m2: Cross-sectional area (m²)
            mass_kg: Object mass (kg)
            latitude_deg: Latitude (deg)
            dt: Date/time

        Returns:
            Drag acceleration magnitude in m/s²
        """
        result = self.density(altitude_km, latitude_deg, 0.0, dt)
        rho = result.total_mass_density_kg_m3
        v = velocity_km_s * 1000.0  # m/s

        return 0.5 * rho * v**2 * cd * area_m2 / mass_kg

    def compare_solar_conditions(
        self, altitude_km: float,
    ) -> dict[str, float]:
        """Compare density at the same altitude under different solar conditions.

        Returns density ratio relative to quiet conditions.
        """
        conditions = {
            "solar_minimum": (70.0, 70.0, 4.0),
            "moderate": (120.0, 120.0, 7.0),
            "solar_maximum": (200.0, 200.0, 15.0),
            "geomag_storm": (150.0, 150.0, 100.0),
            "extreme_storm": (250.0, 250.0, 300.0),
        }

        results = {}
        for name, (f107, f107a, ap) in conditions.items():
            model = AtmosphericDensityModel(f107, f107a, ap)
            result = model.density(altitude_km)
            results[name] = result.total_mass_density_kg_m3

        # Normalize to solar minimum
        baseline = results["solar_minimum"]
        return {k: v / baseline for k, v in results.items()}
