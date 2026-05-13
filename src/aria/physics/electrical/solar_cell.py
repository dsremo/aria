"""Solar cell efficiency model: temperature and radiation degradation.

PROBLEM WITH THE PRIOR SIMULATION MODEL
-----------------------------------------
The generation ship simulation tracks solar panel output as a fixed power
budget with no physics — no temperature coefficient, no radiation damage,
no coverage angle, no AMO irradiance falloff with distance. Real triple-
junction GaAs cells degrade both thermally and under particle radiation;
at 0.56g the mission time scale (30 years) means radiation damage alone
can reduce output by >20%.

THIS MODULE
-----------
Implements the two main degradation mechanisms for triple-junction III-V
photovoltaic cells used on spacecraft:

1. TEMPERATURE COEFFICIENT (Bett 2007; Messenger 2001)
   P(T) = P_ref × [1 + γ_P × (T − T_ref)]
   γ_P = temperature coefficient of power [%/K]
   For 3J GaAs: γ_P ≈ −0.20 %/K (Bett 2007 Prog PV 15:563)
   P_ref measured at T_ref = 28°C (301 K) per ISO 15387 (space AMO)

2. RADIATION DEGRADATION (Messenger 2001; NASA CR-2001-210854)
   Beginning-of-life (BOL) to end-of-life (EOL) via equivalent fluence:
   P_EOL = P_BOL × D(Φ_eq)
   D(Φ_eq) = 1 − C_rad × log10(1 + Φ_eq / Φ_0)   [degradation factor]
   Φ_eq: 1 MeV electron equivalent fluence [e/cm²]
   C_rad = 0.18, Φ_0 = 1e12 e/cm² (3J GaAs fit to Messenger 2001 Fig. 4)

3. IRRADIANCE MODEL
   Solar irradiance at distance r from Sun:
   G(r) = G_AMO × (AU / r)²
   G_AMO = 1366 W/m² (solar constant at 1 AU; Kopp & Lean 2011)

4. INCIDENCE ANGLE CORRECTION
   P_actual = P × cos(θ)  for θ in [0, 90°]; P = 0 for θ > 90°

5. PANEL SOILING / CONTAMINATION (ISS experience)
   ARIA mission: no atmosphere, so only micrometeorite debris coating.
   Applied as a fixed loss factor:
   η_soiling ≈ 1.0 − f_soil    (f_soil = 0.02 after 30 yr; Wertz 2011 SMAD 2nd)

COMBINED MODEL
--------------
P(T, Φ_eq, r, θ) = P_BOL
    × [1 + γ_P × (T − T_ref)]   (temperature)
    × D(Φ_eq)                    (radiation)
    × (AU / r)²                  (irradiance falloff)
    × cos(θ)                     (incidence angle; clamped to [0,1])
    × (1 − f_soil)               (contamination)

REFERENCES
----------
  Bett A.W. et al. (2007) Prog PV 15:563 — 3J GaAs temperature coefficient
  Messenger S.R. et al. (2001) Prog PV 9:253 — radiation degradation model
  NASA CR-2001-210854 — JPL solar cell radiation handbook
  Kopp G. & Lean J.L. (2011) GRL 38:L01706 — solar constant 1366 W/m²
  Wertz J.R. et al. (2011) SMAD 2nd ed. §11 — solar array design
  ISO 15387:2005 — space AMO test standard (T_ref = 301 K)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Solar and orbital constants ───────────────────────────────────────────────

G_AMO_W_M2: float = 1366.0    # Solar constant at 1 AU [W/m²] (Kopp & Lean 2011 GRL 38:L01706)
AU_M: float = 1.495978707e11  # 1 AU in metres (IAU 2012)

# ── 3J GaAs cell parameters ───────────────────────────────────────────────────

TRIPLE_JUNCTION_GAAS_ETA_BOL: float = 0.295      # BOL AM0 efficiency (Spectrolab UTJ; Bett 2007)
TRIPLE_JUNCTION_T_REF_K: float = 301.0           # ISO 15387 AM0 test temperature [K]
TRIPLE_JUNCTION_GAMMA_P_PER_K: float = -2.0e-3   # Power temp coefficient [/K] (Bett 2007 Prog PV 15:563)

# Radiation degradation parameters (Messenger 2001 Prog PV 9:253; NASA CR-2001-210854)
# Fit to Spectrolab UTJ 3J GaAs: P_max ~29% BOL → ~24% at 1e15 e/cm² (D≈0.83)
# Equation: D = 1 - C_rad × log10(1 + Φ/Φ₀); fitted: C_rad=0.057, Φ₀=1e12
RADIATION_C_RAD: float = 0.057   # degradation slope constant (3J GaAs fit; Messenger 2001)
RADIATION_PHI_0: float = 1.0e12  # reference fluence [e/cm²] at 1 MeV equivalent

# Soiling factor: micrometeorite + outgassing deposits (Wertz 2011 SMAD 2nd §11)
DEFAULT_SOILING_FACTOR: float = 0.02  # 2% power loss over 30-year mission


@dataclass
class SolarCellConfig:
    """Configuration for a solar panel/array.

    Attributes:
        area_m2:        Total panel active area [m²].
        eta_bol:        Beginning-of-life AM0 efficiency [0–1].
        gamma_P_per_K:  Temperature coefficient of power [/K].
        T_ref_K:        Reference temperature for efficiency [K].
        C_rad:          Radiation degradation slope constant.
        phi_0_e_cm2:    Radiation reference fluence [e/cm²].
        soiling_factor: Fractional power loss from contamination [0–1].
    """
    area_m2: float = 100.0
    eta_bol: float = TRIPLE_JUNCTION_GAAS_ETA_BOL
    gamma_P_per_K: float = TRIPLE_JUNCTION_GAMMA_P_PER_K
    T_ref_K: float = TRIPLE_JUNCTION_T_REF_K
    C_rad: float = RADIATION_C_RAD
    phi_0_e_cm2: float = RADIATION_PHI_0
    soiling_factor: float = DEFAULT_SOILING_FACTOR


# ── Component models ──────────────────────────────────────────────────────────

def temperature_factor(
    T_K: float,
    gamma_P_per_K: float = TRIPLE_JUNCTION_GAMMA_P_PER_K,
    T_ref_K: float = TRIPLE_JUNCTION_T_REF_K,
) -> float:
    """Fractional power output at temperature T relative to T_ref.

    f_T = 1 + γ_P × (T − T_ref)

    Clamped to [0, 2] to avoid unphysical values.

    Args:
        T_K: Cell temperature [K].
        gamma_P_per_K: Temperature coefficient [/K].
        T_ref_K: Reference temperature [K].

    Returns:
        Temperature factor [dimensionless].

    Reference: Bett et al. (2007) Prog Photovolt 15:563.
    """
    return max(0.0, min(2.0, 1.0 + gamma_P_per_K * (T_K - T_ref_K)))


def radiation_degradation_factor(
    fluence_e_cm2: float,
    C_rad: float = RADIATION_C_RAD,
    phi_0: float = RADIATION_PHI_0,
) -> float:
    """Fractional remaining power after radiation damage.

    D(Φ) = 1 − C_rad × log₁₀(1 + Φ / Φ₀)

    Clamped to [0, 1].

    Args:
        fluence_e_cm2: 1 MeV equivalent electron fluence [e/cm²].
        C_rad: Degradation slope constant (fitted to 3J GaAs data).
        phi_0: Reference fluence [e/cm²].

    Returns:
        Remaining power fraction [0, 1].

    Reference: Messenger et al. (2001) Prog Photovolt 9:253.
        NASA CR-2001-210854 JPL Solar Cell Radiation Handbook.
    """
    if fluence_e_cm2 <= 0.0:
        return 1.0
    degradation = C_rad * math.log10(1.0 + fluence_e_cm2 / phi_0)
    return max(0.0, 1.0 - degradation)


def irradiance_W_m2(distance_AU: float) -> float:
    """Solar irradiance at a given distance from the Sun.

    G(r) = G_AMO × (1 AU / r)²

    Args:
        distance_AU: Distance from Sun [AU].

    Returns:
        Irradiance [W/m²].

    Reference: Kopp & Lean (2011) GRL 38:L01706 (G_AMO = 1366 W/m²).
    """
    if distance_AU <= 0.0:
        raise ValueError(f"distance_AU must be > 0, got {distance_AU}")
    return G_AMO_W_M2 * (1.0 / distance_AU) ** 2


def incidence_angle_factor(theta_deg: float) -> float:
    """Fractional power output at solar incidence angle θ.

    f_θ = cos(θ) for θ ∈ [0°, 90°]; 0 for θ > 90°.

    Args:
        theta_deg: Incidence angle between panel normal and Sun vector [°].

    Returns:
        Incidence factor [0, 1].
    """
    if theta_deg >= 90.0:
        return 0.0
    return max(0.0, math.cos(math.radians(theta_deg)))


# ── Combined power model ──────────────────────────────────────────────────────

def solar_panel_power_W(
    config: SolarCellConfig,
    T_K: float,
    fluence_e_cm2: float,
    distance_AU: float,
    incidence_angle_deg: float = 0.0,
) -> float:
    """Total power output of a solar panel under given conditions.

    P = G(r) × A × η_BOL
        × f_T(T)          (temperature correction)
        × D(Φ)            (radiation degradation)
        × cos(θ)          (incidence angle)
        × (1 − f_soil)    (contamination)

    Args:
        config: Solar cell configuration.
        T_K: Cell temperature [K].
        fluence_e_cm2: Cumulative 1 MeV equivalent fluence [e/cm²].
        distance_AU: Distance from Sun [AU].
        incidence_angle_deg: Angle between panel normal and sun vector [°].

    Returns:
        Power output [W].

    References:
        Bett 2007 Prog PV 15:563; Messenger 2001 Prog PV 9:253;
        Kopp & Lean 2011 GRL 38:L01706; Wertz 2011 SMAD §11.
    """
    G = irradiance_W_m2(distance_AU)
    f_T = temperature_factor(T_K, config.gamma_P_per_K, config.T_ref_K)
    D = radiation_degradation_factor(fluence_e_cm2, config.C_rad, config.phi_0_e_cm2)
    f_theta = incidence_angle_factor(incidence_angle_deg)
    f_clean = 1.0 - config.soiling_factor

    return G * config.area_m2 * config.eta_bol * f_T * D * f_theta * f_clean


def bol_power_W(config: SolarCellConfig, distance_AU: float = 1.0) -> float:
    """Beginning-of-life power at reference temperature, normal incidence.

    P_BOL = G_AMO × A × η_BOL × (1 − f_soil)

    Args:
        config: Solar cell config.
        distance_AU: Distance from Sun [AU].

    Returns:
        BOL power [W].
    """
    return solar_panel_power_W(
        config, T_K=config.T_ref_K, fluence_e_cm2=0.0,
        distance_AU=distance_AU, incidence_angle_deg=0.0,
    )


def eol_power_fraction(
    config: SolarCellConfig,
    T_K: float,
    fluence_e_cm2: float,
    distance_AU: float = 1.0,
    incidence_angle_deg: float = 0.0,
) -> float:
    """EOL power as a fraction of BOL.

    Args:
        config: Solar cell config.
        T_K: Operating temperature [K].
        fluence_e_cm2: Accumulated fluence [e/cm²].
        distance_AU: Distance from Sun [AU].
        incidence_angle_deg: Incidence angle [°].

    Returns:
        P_EOL / P_BOL [0, 1].
    """
    p_bol = bol_power_W(config, distance_AU)
    if p_bol <= 0.0:
        return 0.0
    p_eol = solar_panel_power_W(
        config, T_K, fluence_e_cm2, distance_AU, incidence_angle_deg
    )
    return p_eol / p_bol
