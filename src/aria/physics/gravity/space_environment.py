"""Space environment models — radiation belts, plasma, magnetic field.

Provides first-order approximations of the space environment that
spacecraft encounter. Used for:
- Radiation dose accumulation (trapped belt protons/electrons)
- Spacecraft charging risk in plasma
- Magnetic torque computation (ADCS magnetic control)
- Orbit decay in upper atmosphere (density from time/altitude)

For precision, use external tools (SPENVIS, ONERA OMERE, AP8/AE8
trapped radiation models) — these Python functions are analytical
approximations adequate for:
- Mission planning (what belt do we cross? dose rate?)
- Design trade studies (radiation shielding requirements)
- Real-time alerting (unexpected flux increase)

References:
    AE8/AP8: Vette (1991) NSSDC/WDC-A-R&S 91-24
    Vampola (1996) Adv Space Res 17(2): AE8 critique
    Daly (1994) ESA Workshop on Space Environment: SPENVIS models
    Jursa (1985) USAF Handbook of Geophysics and the Space Environment
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# ══════════════════════════════════════════════════════════════════
#  Earth magnetic field (dipole approximation)
# ══════════════════════════════════════════════════════════════════

_B0_EQUATOR_NT = 30438.0  # IGRF equatorial field strength [nT] (Maus 2010)
_R_EARTH_M = 6378137.0
_DIPOLE_TILT_RAD = math.radians(10.5)  # magnetic dipole tilt from rotation axis


def igrf_dipole(r_eci: np.ndarray) -> np.ndarray:
    """Earth magnetic field at ECI position using IGRF dipole approximation.

    B = B0 * (R_E / r)³ * [3(m̂·r̂)r̂ - m̂]

    where m̂ is the dipole axis direction (tilted 10.5° from -z).
    Accurate to ~10% below 3 Earth radii. For precision use IGRF-13.

    Args:
        r_eci: (3,) position in ECI [m]

    Returns:
        (3,) magnetic field vector [nT]

    Reference: Wertz 1978 App. H; IGRF-13 (Alken et al. 2021).
    """
    r = np.linalg.norm(r_eci)
    if r < _R_EARTH_M:
        return np.zeros(3)

    # Dipole axis (approximate — pointing mostly -z with 10.5° tilt to x)
    m_hat = np.array([
        math.sin(_DIPOLE_TILT_RAD),
        0.0,
        -math.cos(_DIPOLE_TILT_RAD),
    ])

    r_hat = r_eci / r
    m_dot_r = np.dot(m_hat, r_hat)

    # Dipole field formula
    B = _B0_EQUATOR_NT * (_R_EARTH_M / r) ** 3 * (3 * m_dot_r * r_hat - m_hat)
    return B


def magnetic_torque(
    magnetic_moment_am2: np.ndarray, r_eci: np.ndarray,
) -> np.ndarray:
    """Torque on a spacecraft from Earth's magnetic field.

    τ = m × B

    Used for passive magnetic stabilization and B-dot detumbling.
    Magnetorquer dipole moments are typically 0.1-10 A·m² for cubesats.

    Args:
        magnetic_moment_am2: (3,) spacecraft dipole moment [A·m²]
        r_eci: (3,) spacecraft position [m]

    Returns:
        (3,) torque [N·m]
    """
    B_nT = igrf_dipole(r_eci)
    B_T = B_nT * 1e-9  # nT → T
    return np.cross(magnetic_moment_am2, B_T)


# ══════════════════════════════════════════════════════════════════
#  Trapped radiation belts (AE8/AP8-like)
# ══════════════════════════════════════════════════════════════════

def van_allen_proton_flux(
    altitude_km: float,
    energy_mev: float = 10.0,
) -> float:
    """Trapped proton flux in the Van Allen inner belt.

    Analytical approximation of AP8 at solar minimum. The inner belt
    peaks around L=1.5 (altitude ~2000 km over equator) with protons
    up to ~400 MeV.

    Args:
        altitude_km: altitude above Earth surface [km]
        energy_mev: proton kinetic energy threshold [MeV]

    Returns:
        Omnidirectional integral flux [#/cm²/s]

    Reference: Vette 1991 NSSDC/WDC-A-R&S 91-24 (AP8)
    """
    if altitude_km < 200 or altitude_km > 40000:
        return 0.0

    # Peak at ~2000 km (L~1.5)
    peak_alt = 2000.0
    sigma_alt = 2500.0
    altitude_factor = math.exp(-((altitude_km - peak_alt) / sigma_alt) ** 2)

    # Peak flux ~1e4 #/cm²/s for E > 10 MeV at L=1.5
    peak_flux_10mev = 1e4

    # Spectrum falls roughly as E^-2
    energy_factor = (10.0 / max(energy_mev, 1.0)) ** 2

    return peak_flux_10mev * altitude_factor * energy_factor


def van_allen_electron_flux(
    altitude_km: float,
    energy_mev: float = 1.0,
) -> float:
    """Trapped electron flux in outer Van Allen belt.

    Peaks around L=4-5 (altitude ~18000-25000 km). Electrons up to ~7 MeV.
    """
    if altitude_km < 1000 or altitude_km > 50000:
        return 0.0

    peak_alt = 22000.0
    sigma_alt = 8000.0
    altitude_factor = math.exp(-((altitude_km - peak_alt) / sigma_alt) ** 2)

    peak_flux_1mev = 5e6
    energy_factor = math.exp(-energy_mev / 0.5)

    return peak_flux_1mev * altitude_factor * energy_factor


def south_atlantic_anomaly_boost(
    latitude_deg: float, longitude_deg: float, altitude_km: float,
) -> float:
    """Flux multiplier for the South Atlantic Anomaly (SAA).

    The SAA is where the magnetic field is weakest, so trapped
    particles dip lower — at ISS altitude (400 km) proton fluxes are
    10-100x higher over the SAA than elsewhere.

    SAA center: ~-30° lat, -40° lon (Atlantic Ocean off Brazil)

    Returns a multiplier (1.0 = outside SAA, 10-100 = inside).
    """
    if altitude_km > 800:
        return 1.0

    saa_center_lat = -30.0
    saa_center_lon = -40.0
    # Approximate SAA as 2D Gaussian
    delta_lat = (latitude_deg - saa_center_lat) / 20.0
    delta_lon = (longitude_deg - saa_center_lon) / 30.0
    gaussian = math.exp(-(delta_lat ** 2 + delta_lon ** 2))

    # Peak boost depends on altitude (bigger at low altitude where
    # field is weakest)
    altitude_factor = math.exp(-(altitude_km - 400) / 300) if altitude_km < 800 else 0.1
    peak_boost = 1.0 + 50.0 * altitude_factor

    return 1.0 + (peak_boost - 1.0) * gaussian


# ══════════════════════════════════════════════════════════════════
#  Plasma environment (density + temperature)
# ══════════════════════════════════════════════════════════════════

def plasma_density_m3(altitude_km: float, solar_activity: str = "medium") -> float:
    """Plasma electron density as a function of altitude.

    Peaks in the ionosphere F2 layer (300-400 km), drops off in the
    plasmasphere and plasmapause.

    Args:
        altitude_km: altitude [km]
        solar_activity: "low", "medium", or "high" (affects F2 peak)

    Returns:
        Electron density [#/m³]

    Reference: Jursa 1985 USAF Handbook, Kelley 2009 "The Earth's Ionosphere"
    """
    # F2 peak multiplier by solar activity
    f2_peak = {"low": 5e11, "medium": 1e12, "high": 3e12}.get(solar_activity, 1e12)

    if altitude_km < 150:
        # E region + below — low density
        return 5e10
    elif altitude_km < 400:
        # F region ramp up to peak
        return f2_peak * math.exp(-((altitude_km - 350) / 100) ** 2)
    elif altitude_km < 2000:
        # Topside ionosphere decay
        return f2_peak * math.exp(-(altitude_km - 350) / 500)
    elif altitude_km < 25000:
        # Plasmasphere
        return 1e10 * math.exp(-altitude_km / 10000)
    else:
        # Plasmasheet / solar wind
        return 5e6


def plasma_temperature_k(altitude_km: float) -> float:
    """Approximate plasma electron temperature [K]."""
    if altitude_km < 300:
        return 1500.0  # ionosphere F region
    elif altitude_km < 1000:
        return 3000.0
    elif altitude_km < 10000:
        return 5000.0 + altitude_km * 0.5  # plasmasphere ramp
    else:
        return 1e5  # magnetosphere


# ══════════════════════════════════════════════════════════════════
#  Spacecraft charging risk
# ══════════════════════════════════════════════════════════════════

@dataclass
class ChargingRisk:
    """Spacecraft charging assessment."""
    region: str                     # "ionosphere", "plasmasphere", "GEO", "magnetotail"
    risk_level: str                 # "low", "moderate", "high", "severe"
    potential_v: float              # Expected differential potential [V]
    recommendation: str


def assess_charging_risk(
    altitude_km: float, in_eclipse: bool = False,
) -> ChargingRisk:
    """Assess spacecraft charging risk based on environment.

    GEO satellites in eclipse experience severe charging (-10 kV to -20 kV
    possible during sub-storms). LEO is generally safe.

    Reference: Garrett & Whittlesey (1981) NASA TP-1879 Spacecraft Charging,
    Purvis et al. (1984) NASA TP-2361 Design Guidelines.
    """
    if altitude_km < 1000:
        return ChargingRisk(
            region="ionosphere",
            risk_level="low",
            potential_v=-5.0,
            recommendation="Standard bonding and grounding sufficient.",
        )
    elif altitude_km < 20000:
        return ChargingRisk(
            region="plasmasphere",
            risk_level="moderate",
            potential_v=-500.0,
            recommendation="Conductive surface coatings recommended.",
        )
    elif altitude_km < 50000:
        # GEO region — worst-case charging
        potential = -20000.0 if in_eclipse else -2000.0
        return ChargingRisk(
            region="GEO",
            risk_level="severe" if in_eclipse else "high",
            potential_v=potential,
            recommendation=(
                "Full ESD protection required; differential charging control; "
                "transient protection on all sensor inputs."
            ),
        )
    else:
        return ChargingRisk(
            region="magnetotail",
            risk_level="moderate",
            potential_v=-1000.0,
            recommendation="Monitor for substorm activity.",
        )


# ══════════════════════════════════════════════════════════════════
#  Integrated dose rate
# ══════════════════════════════════════════════════════════════════

def dose_rate_msv_day(
    altitude_km: float, shielding_g_cm2: float = 5.0,
) -> float:
    """Approximate radiation dose rate behind given shielding.

    Integrates over proton + electron + GCR + SPE contributions.
    Shielding reduces dose exponentially with areal density.

    Args:
        altitude_km: altitude [km]
        shielding_g_cm2: Al-equivalent shielding areal density [g/cm²]

    Returns:
        Dose rate [mSv/day]

    Reference: NCRP 132 (2000), NASA-STD-3001 Vol. 1 Rev. B,
    Cucinotta 2014 NASA TP-2014-218284.
    """
    # Base dose rates (unshielded) at various altitudes
    if altitude_km < 500:
        # LEO — dominated by trapped protons
        base_dose = 0.3
    elif altitude_km < 20000:
        # MEO / belt crossing — very high dose
        base_dose = 50.0 * math.exp(-((altitude_km - 5000) / 5000) ** 2)
    elif altitude_km < 50000:
        # GEO — GCR + SPE dominant
        base_dose = 1.5
    else:
        # Deep space — GCR only
        base_dose = 1.3  # 0.42 Sv/yr ÷ 365

    # Shielding attenuation (exponential with ~25 g/cm² e-folding for GCR)
    attenuation = math.exp(-shielding_g_cm2 / 25.0)

    return base_dose * attenuation


# ══════════════════════════════════════════════════════════════════
#  Lorentz force + magnetic L-shell
# ══════════════════════════════════════════════════════════════════

#  Elementary charge and proton mass (CODATA 2018)
_E_CHARGE_C = 1.60217663e-19    # C
_M_PROTON_KG = 1.67262192e-27   # kg


def lorentz_force(
    charge_c: float,
    velocity_m_s: np.ndarray,
    b_field_t: np.ndarray,
) -> np.ndarray:
    """Lorentz magnetic force on a charged particle.

    F = q × (v × B)

    Used for:
    - Van Allen belt particle guiding-center motion
    - Electrodynamic tether thrust / drag
    - Ion thruster exhaust plume deflection in magnetosphere
    - Charged micrometeorite trajectory deviation

    Args:
        charge_c: Particle charge [C]. Positive for protons/ions.
        velocity_m_s: (3,) velocity in any inertial frame [m/s].
        b_field_t: (3,) magnetic field [T].

    Returns:
        (3,) Lorentz force [N].

    Reference: Jackson 1999 "Classical Electrodynamics" §6.1.
    """
    return charge_c * np.cross(velocity_m_s, b_field_t)


def lorentz_acceleration(
    charge_c: float,
    mass_kg: float,
    velocity_m_s: np.ndarray,
    r_eci: np.ndarray,
) -> np.ndarray:
    """Lorentz acceleration on a charged particle in Earth's magnetic field.

    Computes B from the IGRF dipole model at r_eci, then returns
    F/m = q/m × (v × B).

    Args:
        charge_c: Particle charge [C].
        mass_kg: Particle mass [kg].
        velocity_m_s: (3,) velocity [m/s].
        r_eci: (3,) ECI position [m].

    Returns:
        (3,) acceleration [m/s²].

    Reference: Jackson 1999 §6.1; Walt 1994 "Introduction to Geomagnetically
        Trapped Radiation" Ch. 2.
    """
    b_nt = igrf_dipole(r_eci)
    b_t = b_nt * 1.0e-9       # nT → T
    return (charge_c / mass_kg) * np.cross(velocity_m_s, b_t)


def magnetic_l_shell(r_eci: np.ndarray) -> float:
    """McIlwain L-shell parameter in dipole approximation.

    L = r / (R_E × cos²(λ_mag))

    where λ_mag is the magnetic latitude. For a dipole, cos²(λ) can be
    derived from the field-line equation r = L × R_E × cos²(λ), giving:

        cos²(λ_mag) = r_eq / r    (r_eq = L × R_E, radial distance at equator)

    We compute L from the magnetic latitude projected onto the dipole axis:
        cos(λ_mag) = |r × m̂| / r    (cross product with dipole axis)

    This gives the standard dipole result: L = r / (R_E × cos²(λ_mag)).

    Args:
        r_eci: (3,) ECI position [m].

    Returns:
        McIlwain L parameter (dimensionless). L=1 at Earth's surface on
        magnetic equator; L=6.6 at GEO; L→∞ at poles.
        Returns 0.0 for positions inside Earth.

    Reference: McIlwain 1961 JGR 66 3681; Walt 1994 Ch. 3.
    """
    r_mag = np.linalg.norm(r_eci)
    if r_mag < _R_EARTH_M:
        return 0.0

    # Dipole axis direction (same as in igrf_dipole)
    m_hat = np.array([math.sin(_DIPOLE_TILT_RAD), 0.0, -math.cos(_DIPOLE_TILT_RAD)])
    r_hat = r_eci / r_mag

    # cos(magnetic latitude) = magnitude of component perpendicular to m̂
    sin_lambda = np.dot(m_hat, r_hat)  # sin of magnetic latitude
    cos2_lambda = 1.0 - sin_lambda ** 2

    if cos2_lambda < 1e-10:
        return float('inf')   # at the magnetic poles

    return r_mag / (_R_EARTH_M * cos2_lambda)


def gyroradius_m(
    kinetic_energy_mev: float,
    charge_c: float,
    mass_kg: float,
    b_field_nt: float,
) -> float:
    """Larmor (gyro) radius of a relativistic charged particle in a magnetic field.

    r_L = γ m v_perp / (|q| B)

    For a purely perpendicular velocity (pitch angle 90°), v_perp = v.

    Args:
        kinetic_energy_mev: Particle kinetic energy [MeV].
        charge_c: Particle charge magnitude [C].
        mass_kg: Particle rest mass [kg].
        b_field_nt: Magnetic field strength [nT].

    Returns:
        Gyroradius [m].

    Reference: Walt 1994 Ch. 2, Eq. (2.4); Jackson 1999 §12.2.
    """
    # Rest mass energy in MeV
    m_c2_mev = mass_kg * (2.99792458e8) ** 2 / (1.60217663e-13)  # J → MeV
    gamma = 1.0 + kinetic_energy_mev / m_c2_mev
    # Relativistic momentum p = γ m v; total energy E = γ m c²
    # v = c × sqrt(1 - 1/γ²); p = γ m v
    beta_gamma = math.sqrt(gamma ** 2 - 1.0)
    p_si = beta_gamma * mass_kg * 2.99792458e8   # kg·m/s

    b_t = max(b_field_nt * 1.0e-9, 1.0e-20)      # avoid division by zero
    return p_si / (abs(charge_c) * b_t)


def van_allen_traversal_dose_msv(
    altitude_start_km: float,
    altitude_end_km: float,
    shielding_g_cm2: float = 5.0,
    n_steps: int = 100,
) -> float:
    """Dose accumulated during a radial pass through the Van Allen belts.

    Integrates `dose_rate_msv_day` over the altitude profile, assuming a
    2-hour radial traversal (LEO → altitude_end or vice versa).  This is
    an engineering-level estimate for mission phase dose; for precision use
    AE8/AP8 and the actual trajectory.

    Args:
        altitude_start_km: Starting altitude [km] (typically LEO ~400 km).
        altitude_end_km: Ending altitude [km] (GEO ~35786, interplanetary >60000).
        shielding_g_cm2: Spacecraft shielding areal density [g/cm²].
        n_steps: Number of integration steps.

    Returns:
        Total dose [mSv] for the traversal segment.

    Reference: NCRP 132 (2000); Cucinotta 2014 §5.3 belt transit dose.
    """
    # Integrate over altitude profile (trapezoidal rule)
    alts = [altitude_start_km + i * (altitude_end_km - altitude_start_km) / n_steps
            for i in range(n_steps + 1)]

    rates = [dose_rate_msv_day(alt, shielding_g_cm2) for alt in alts]

    # Transit duration: 2 hours = 2/24 day for typical GTO perigee-to-apogee pass
    transit_days = 2.0 / 24.0  # ESTIMATE — GTO transit time (2h apogee-perigee)

    # Trapezoidal integration over altitude → convert to time integral
    # rate × time (uniform time for this approximation)
    avg_rate = sum(rates) / len(rates)
    return avg_rate * transit_days
