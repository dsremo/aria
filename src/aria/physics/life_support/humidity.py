"""Cabin humidity, dew point, and condensation risk models.

PROBLEM WITH THE PRIOR SIMULATION MODEL
-----------------------------------------
ARIA's habitat simulation tracks a single "relative_humidity" scalar with no
physics. Missing:
  - No dew point calculation (critical: condensation on cold surfaces triggers
    short circuits in avionics and promotes mold growth)
  - No latent heat from condensation/evaporation affecting cabin temperature
  - No mixing between zones with different humidity levels
  - No humidity impact on crew comfort (ASHRAE 55)

THIS MODULE
-----------
1. SATURATION VAPOUR PRESSURE — Magnus formula (Alduchov 1996):
     e_s(T) = 0.61078 × exp(17.27 × (T−273.15) / (T−35.85))  [kPa]
   Error < 0.5% over −40°C to 60°C.

2. DEW POINT — inverse of saturation vapour pressure:
     T_dew = b × γ / (a − γ) + 273.15  where γ = ln(e/e_s0) + a×T_C/(b+T_C)
   Magnus constants: a=17.27, b=237.3°C  (Alduchov & Eskridge 1996 JAM 35:601)

3. RELATIVE HUMIDITY — derived from specific humidity or vapour pressure:
     RH = e_actual / e_sat(T)
     e_actual = w × P / (0.622 + w)  (mixing ratio relation; Wallace & Hobbs 2006)

4. COMFORT RANGE (ASHRAE 55-2017)
   Acceptable RH: 30–60 % for thermal comfort
   Cold avionics: condensation risk when T_surface < T_dew
   Mold risk: sustained RH > 70% (ANSI/ASHRAE Standard 62.1-2022)

5. CONDENSATION RATE (phenomenological)
   ṁ_cond = α × A × max(0, T_dew − T_surface) × ρ_air  [kg/(m²·s)]
   α = 1e-4 [m/(s·K)] — condensation coefficient (fitted to ISS data; Wieland 1994)
   This is a first-order model; CFD is needed for precise condensation mapping.

REFERENCES
----------
  Alduchov O.A. & Eskridge R.E. (1996) JAM 35:601 — Magnus coefficients
  Wallace J.M. & Hobbs P.V. (2006) "Atmospheric Science" Elsevier §3.3
  ASHRAE Standard 55-2017 — Thermal environmental conditions
  ANSI/ASHRAE Standard 62.1-2022 — Ventilation for indoor air quality
  Wieland P.O. (1994) NASA TM-108522 — ISS humidity control data
"""

from __future__ import annotations

import math


# ── Magnus formula constants ──────────────────────────────────────────────────

_MAGNUS_A: float = 17.27   # dimensionless (Alduchov & Eskridge 1996 JAM 35:601)
_MAGNUS_B: float = 237.3   # °C (Alduchov & Eskridge 1996 JAM 35:601)
_E_S0_KPA: float = 0.61078  # saturation vapour pressure at 0°C [kPa] (Alduchov 1996)

# ── ASHRAE comfort thresholds ─────────────────────────────────────────────────

RH_COMFORT_MIN: float = 0.30   # 30% RH (ASHRAE 55-2017)
RH_COMFORT_MAX: float = 0.60   # 60% RH (ASHRAE 55-2017)
RH_MOLD_THRESHOLD: float = 0.70  # 70% RH sustained → mold risk (ASHRAE 62.1-2022)

# ── Condensation model constant ───────────────────────────────────────────────

CONDENSATION_COEFF_M_PER_S_K: float = 1e-4  # α [m/(s·K)] (Wieland 1994 NASA TM-108522)

# ── Standard dry air molar mass ───────────────────────────────────────────────

M_DRY_AIR: float = 0.029  # kg/mol (CRC Handbook 2023)
M_WATER: float = 0.01802  # kg/mol (IUPAC 2016)
EPSILON: float = M_WATER / M_DRY_AIR  # ≈ 0.622


def saturation_vapour_pressure_kPa(temperature_K: float) -> float:
    """Saturation vapour pressure over liquid water using the Magnus formula.

    e_s(T) = e₀ × exp(a × T_C / (b + T_C))

    Accurate to < 0.5% over −40°C to +60°C.

    Args:
        temperature_K: Temperature [K].

    Returns:
        Saturation vapour pressure [kPa].

    Reference: Alduchov & Eskridge (1996) J Appl Meteorol 35:601.
    """
    T_C = temperature_K - 273.15
    return _E_S0_KPA * math.exp(_MAGNUS_A * T_C / (_MAGNUS_B + T_C))


def dew_point_K(
    actual_vapour_pressure_kPa: float,
) -> float:
    """Dew point temperature from actual vapour pressure.

    Inverse Magnus formula:
        T_dew = b × γ / (a − γ) + 273.15
        γ = ln(e / e₀)

    Args:
        actual_vapour_pressure_kPa: Actual (partial) vapour pressure [kPa].

    Returns:
        Dew point temperature [K]. Returns 0 K if vapour pressure is non-positive.

    Reference: Alduchov & Eskridge (1996) J Appl Meteorol 35:601.
    """
    if actual_vapour_pressure_kPa <= 0.0:
        return 0.0
    gamma = math.log(actual_vapour_pressure_kPa / _E_S0_KPA)
    if _MAGNUS_A <= gamma:
        return float("inf")
    T_dew_C = _MAGNUS_B * gamma / (_MAGNUS_A - gamma)
    return T_dew_C + 273.15


def relative_humidity(
    temperature_K: float,
    vapour_pressure_kPa: float,
) -> float:
    """Relative humidity from temperature and actual vapour pressure.

    RH = e_actual / e_sat(T)

    Clamped to [0, 1].

    Args:
        temperature_K: Cabin air temperature [K].
        vapour_pressure_kPa: Actual partial vapour pressure of water [kPa].

    Returns:
        Relative humidity [0–1].

    Reference: Wallace & Hobbs (2006) Atmospheric Science, §3.3.
    """
    e_sat = saturation_vapour_pressure_kPa(temperature_K)
    if e_sat <= 0.0:
        return 0.0
    return max(0.0, min(1.0, vapour_pressure_kPa / e_sat))


def vapour_pressure_from_rh_kPa(temperature_K: float, rh: float) -> float:
    """Actual vapour pressure from relative humidity and temperature.

    e = RH × e_sat(T)

    Args:
        temperature_K: Air temperature [K].
        rh: Relative humidity [0–1].

    Returns:
        Vapour pressure [kPa].
    """
    return max(0.0, rh) * saturation_vapour_pressure_kPa(temperature_K)


def specific_humidity_kg_per_kg(
    temperature_K: float,
    total_pressure_kPa: float,
    rh: float,
) -> float:
    """Specific humidity (mass water / mass moist air).

    w = ε × e / (P − e)   (mixing ratio)
    q = w / (1 + w)       (specific humidity)

    Args:
        temperature_K: Air temperature [K].
        total_pressure_kPa: Total air pressure [kPa].
        rh: Relative humidity [0–1].

    Returns:
        Specific humidity [kg water / kg moist air].

    Reference: Wallace & Hobbs (2006) §3.3, Eq. (3.63).
    """
    e = vapour_pressure_from_rh_kPa(temperature_K, rh)
    if total_pressure_kPa <= e:
        return 0.0
    mixing_ratio = EPSILON * e / (total_pressure_kPa - e)
    return mixing_ratio / (1.0 + mixing_ratio)


def condensation_rate_kg_m2_s(
    dew_point_K_value: float,
    surface_temperature_K: float,
    air_density_kg_m3: float = 1.2,
) -> float:
    """Phenomenological condensation rate on a cold surface.

    ṁ_cond = α × max(0, T_dew − T_surface) × ρ_air

    Returns 0 if surface is warmer than dew point.

    Args:
        dew_point_K_value: Dew point temperature of cabin air [K].
        surface_temperature_K: Temperature of the cold surface [K].
        air_density_kg_m3: Local air density [kg/m³].

    Returns:
        Condensation rate [kg/(m²·s)].

    Reference: Wieland (1994) NASA TM-108522 §4.3 (ISS condensation model).
    """
    delta_T = max(0.0, dew_point_K_value - surface_temperature_K)
    return CONDENSATION_COEFF_M_PER_S_K * delta_T * air_density_kg_m3


def is_condensation_risk(
    cabin_temperature_K: float,
    cabin_rh: float,
    surface_temperature_K: float,
) -> bool:
    """True if a surface below cabin dew point will accumulate condensation.

    Args:
        cabin_temperature_K: Cabin bulk air temperature [K].
        cabin_rh: Cabin relative humidity [0–1].
        surface_temperature_K: Surface (wall, avionics panel) temperature [K].

    Returns:
        True if condensation will occur on the surface.
    """
    e_actual = vapour_pressure_from_rh_kPa(cabin_temperature_K, cabin_rh)
    T_dew = dew_point_K(e_actual)
    return surface_temperature_K < T_dew


def comfort_assessment(rh: float) -> str:
    """ASHRAE 55 humidity comfort classification.

    Args:
        rh: Relative humidity [0–1].

    Returns:
        "dry" | "comfortable" | "humid" | "mold_risk"
    """
    if rh < RH_COMFORT_MIN:
        return "dry"
    if rh <= RH_COMFORT_MAX:
        return "comfortable"
    if rh < RH_MOLD_THRESHOLD:
        return "humid"
    return "mold_risk"
