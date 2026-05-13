"""Proper-motion propagation of nearby stars (§4.9 of A1 scope).

At cruise time `t` (seconds past J2000.0 TDB), a catalog star's ICRS
heliocentric position is propagated linearly along its 3-D space
velocity:

    R_*(t) = R_*(J2000) + V_*(J2000) · (t − t_J2000)     [m]

The space velocity is assembled from the cataloged transverse proper
motion (μ_α* = μ_α cos δ, μ_δ), the distance, and the radial velocity:

    v_ra_m_s = μ_α* · d                                   (transverse, +RA)
    v_dec_m_s = μ_δ · d                                   (transverse, +Dec)
    v_rad_m_s = v_radial                                  (line of sight)

(Hipparcos & Tycho Catalogues conventions, ESA SP-1200, 1997). The
linearised transverse velocity ignores the curvature of the spherical
shell over the propagation time, which is a ~ppm correction for
centuries-long propagations.

Unit audit: μ in [rad/s] · d in [m] = [m/s]. Catalogue values are
typically given as mas/yr and must be converted: 1 mas/yr = 1e-3 arcsec /
yr = (1e-3 / 206264.806) rad / (365.25 · 86400 s) ≈ 1.536e-16 rad/s.

Canonical test target: Proxima Centauri — Gaia DR3 source
5853498713160606720 (Gaia Collaboration 2021 A&A 649 A1
DOI 10.1051/0004-6361/202039657), radial velocity from Kervella 2017
A&A 598 L7 DOI 10.1051/0004-6361/201629930.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .constants import LIGHT_YEAR_M, SPEED_OF_LIGHT_M_S

# Unit conversions (exact).
ARCSEC_PER_RAD: float = 180.0 * 3600.0 / math.pi
MAS_PER_YR_TO_RAD_PER_S: float = (
    1.0e-3 / ARCSEC_PER_RAD / (365.25 * 86400.0)
)  # rad/s per mas/yr
KM_PER_S_TO_M_PER_S: float = 1.0e3


@dataclass
class StarCatalogEntry:
    """Snapshot of a star's ICRS 6-state at J2000.0.

    Attributes:
        name: human-readable label.
        ra_j2000_rad: right ascension at J2000 (rad).
        dec_j2000_rad: declination at J2000 (rad).
        distance_m: geometric distance from Sun to star at J2000 (m).
        pm_ra_cosdec_mas_yr: μ_α* = μ_α · cos(δ) (mas/yr).
        pm_dec_mas_yr: μ_δ (mas/yr).
        radial_velocity_km_s: v_radial at J2000 (km/s). Positive = recession.
        gm_m3_s2: stellar gravitational parameter (m³/s²).
    """

    name: str
    ra_j2000_rad: float
    dec_j2000_rad: float
    distance_m: float
    pm_ra_cosdec_mas_yr: float
    pm_dec_mas_yr: float
    radial_velocity_km_s: float
    gm_m3_s2: float

    @property
    def position_j2000_icrf_m(self) -> np.ndarray:
        """Cartesian ICRF position (heliocentric) at J2000.0."""
        cd = math.cos(self.dec_j2000_rad)
        return self.distance_m * np.array(
            [
                cd * math.cos(self.ra_j2000_rad),
                cd * math.sin(self.ra_j2000_rad),
                math.sin(self.dec_j2000_rad),
            ]
        )

    @property
    def velocity_j2000_icrf_m_s(self) -> np.ndarray:
        """Cartesian ICRF velocity (heliocentric) at J2000.0.

        Decomposes the 3-D velocity into local RA, Dec, radial unit
        vectors and sums them.
        """
        ra = self.ra_j2000_rad
        dec = self.dec_j2000_rad
        # Unit vectors of the local triad at (ra, dec).
        e_rad = np.array(
            [
                math.cos(dec) * math.cos(ra),
                math.cos(dec) * math.sin(ra),
                math.sin(dec),
            ]
        )
        e_ra = np.array([-math.sin(ra), math.cos(ra), 0.0])
        e_dec = np.array(
            [
                -math.sin(dec) * math.cos(ra),
                -math.sin(dec) * math.sin(ra),
                math.cos(dec),
            ]
        )
        # Linear speeds from proper motion (rad/s × m = m/s).
        v_ra = self.pm_ra_cosdec_mas_yr * MAS_PER_YR_TO_RAD_PER_S * self.distance_m
        v_dec = self.pm_dec_mas_yr * MAS_PER_YR_TO_RAD_PER_S * self.distance_m
        v_rad = self.radial_velocity_km_s * KM_PER_S_TO_M_PER_S
        return v_rad * e_rad + v_ra * e_ra + v_dec * e_dec


def propagate_proper_motion(
    star: StarCatalogEntry, seconds_past_j2000: float
) -> tuple[np.ndarray, np.ndarray]:
    """Linearly propagate a star's ICRF 6-state from J2000.

    Returns:
        ``(position_m, velocity_m_s)`` — both shape (3,) heliocentric
        ICRF vectors. Velocity is unchanged from J2000 (linear model).
    """
    r0 = star.position_j2000_icrf_m
    v0 = star.velocity_j2000_icrf_m_s
    r_t = r0 + v0 * seconds_past_j2000
    return r_t, v0.copy()


# ──────────────────────────────────────────────────────────────────────
#  Canonical catalog entries (constants kept inline with citations)
# ──────────────────────────────────────────────────────────────────────

# Proxima Centauri — Gaia DR3 source 5853498713160606720 (Gaia
# Collaboration 2021 A&A 649 A1 DOI 10.1051/0004-6361/202039657);
# radial velocity from Kervella 2017 A&A 598 L7
# DOI 10.1051/0004-6361/201629930; distance from Lurie 2014 AJ 148 91
# DOI 10.1088/0004-6256/148/5/91 (4.2465 ly).
# Catalog RA/Dec at J2000:
#   α = 14h 29m 42.9487s = 217.4289529° (Hipparcos 70890)
#   δ = −62° 40′ 46.141″ = −62.679484° (Hipparcos 70890)
PROXIMA_CENTAURI_J2000: StarCatalogEntry = StarCatalogEntry(
    name="Proxima Centauri",
    ra_j2000_rad=math.radians(217.4289529),
    dec_j2000_rad=math.radians(-62.679484),
    distance_m=4.2465 * LIGHT_YEAR_M,  # Lurie 2014 AJ 148 91
    pm_ra_cosdec_mas_yr=-3775.75,  # Gaia DR3 source 5853498713160606720
    pm_dec_mas_yr=769.77,  # Gaia DR3 source 5853498713160606720
    radial_velocity_km_s=-22.204,  # Kervella 2017 A&A 598 L7
    gm_m3_s2=0.1221 * 1.32712440041939e20,  # Mann 2019 ApJ 871 63 × GM_sun
)
