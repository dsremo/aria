"""ISM ablation of the front shield at cruise velocity (β ≈ 0.1).

At ARIA's cruise speed v = 0.1 c ≈ 3×10⁷ m/s the ship ploughs through
the local interstellar medium (LISM). The bow-face accumulates two
erosion mechanisms:

1. GAS-ION SPUTTERING — H⁺ and He²⁺ arrive with KE ~ 4.7 MeV (H)
   and ~18.8 MeV (He). In the electronic-stopping regime above ~1 MeV/amu,
   each ion sputters a small number of shield atoms. The yield S is
   taken from Matsunami et al. 1984 empirical tables and SRIM-2013
   for the relevant material at the cruise-velocity proton energy.

2. DUST-GRAIN ABLATION — ISM silicate/carbonaceous grains (mean ~0.1 μm,
   ~1.4×10⁻¹⁸ kg) are encountered at 0.1 c. Grain impact at this
   speed is firmly in the plasma-ablation regime (v ≫ v_plasma ~ 5 km/s)
   where both grain and shield surface are vaporised. The crater volume is
   estimated from the specific ablation energy of the shield material
   (energy required to vaporise unit mass), using grain KE as input.

ISM composition (local bubble, Frisch et al. 2011 ARA&A 49:237):
  n_H = 0.3 cm⁻³,  n_He/n_H = 0.085,  dust/gas mass ratio = 0.01.

LIMITATIONS
-----------
- Steady-state (secondary) sputtering only; no cascade depth corrections.
- Single representative grain mass; full MRN (Mathis 1977) distribution
  not implemented.
- No magnetic deflection of ions (relevant if a magnetic shield is deployed).
- Stopping power is approximated by a constant sputtering yield at the
  cruise-velocity proton energy; actual yield varies with σ as the probe
  decelerates over the mission.

References
----------
McKee & Ostriker 1977 ApJ 218:148          — ISM three-phase model; n_H
Frisch et al. 2011 ARA&A 49:237            — LISM density and composition
Draine & Lee 1984 ApJ 285:89               — dust properties, ρ_dust/ρ_gas ≈ 0.01
Mathis, Rumpl & Nordsieck 1977 ApJ 217:425 — grain size distribution
Matsunami et al. 1984 Radiat Eff 91:149    — empirical sputtering yield formula
Hoang et al. 2017 ApJ 847:77              — relativistic probe ablation
Tielens et al. 1994 ApJ 431:321            — interstellar grain sputtering
Ziegler 2008 Nucl Instrum Meth B 268:1818  — SRIM sputtering database
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .relativistic_dust import SPEED_OF_LIGHT_M_S, _lorentz_gamma

# ── ISM bulk constants ─────────────────────────────────────────────────────────

# local ISM H number density (Frisch et al. 2011 ARA&A 49:237)
ISM_N_H_PER_M3: float = 3.0e5          # 0.3 cm⁻³ → 3×10⁵ m⁻³

# He/H number ratio (Frisch et al. 2011)
ISM_HE_H_RATIO: float = 0.085          # ~8.5% He by number

# dust-to-gas mass ratio (Draine & Lee 1984 ApJ 285:89)
ISM_DUST_GAS_RATIO: float = 0.01

# mean ISM silicate grain mass [kg]: 4π/3 × (0.1 μm)³ × 3300 kg/m³
# (Mathis et al. 1977 MRN mean; ρ_grain from Draine & Lee 1984)
ISM_MEAN_GRAIN_MASS_KG: float = 1.38e-18

# ── Physical constants ─────────────────────────────────────────────────────────

M_PROTON_KG: float = 1.67262192e-27   # NIST CODATA 2018
M_ALPHA_KG:  float = 6.64465743e-27   # NIST CODATA 2018 (He-4 nucleus)


# ── Shield material ablation properties ───────────────────────────────────────

@dataclass(frozen=True)
class AblationMaterial:
    """Front-shield material properties for ISM ablation modelling.

    Attributes:
        name: Material name.
        density_kg_m3: Bulk density [kg/m³].
        atomic_mass_kg: Representative surface-atom mass [kg].
        sputtering_yield_H: Atoms/ion for H⁺ at 4.7 MeV (0.1 c).
        sputtering_yield_He: Atoms/ion for He²⁺ at 18.8 MeV (0.1 c).
        specific_ablation_energy_J_kg: Energy to vaporise unit mass [J/kg].
    """
    name: str
    density_kg_m3: float
    atomic_mass_kg: float
    sputtering_yield_H: float
    sputtering_yield_He: float
    specific_ablation_energy_J_kg: float


# Ti-6Al-4V: MMPDS-17 (density); SRIM-2013 Ti (sputtering); H_sub from
# enthalpy of sublimation ~9.5 MJ/kg (Chase 1998 NIST-JANAF; Boyer 1994 ASM)
ABLATION_TI_6AL_4V = AblationMaterial(
    name="Ti-6Al-4V",
    density_kg_m3=4430.0,             # MMPDS-17
    atomic_mass_kg=47.867 * 1.6605e-27,  # Ti atomic mass, IUPAC 2021
    sputtering_yield_H=0.08,          # SRIM-2013 Ti/H at 4.7 MeV (Ziegler 2008)
    sputtering_yield_He=0.28,         # Matsunami 1984 Z²-scaling (≈3.5× H yield)
    specific_ablation_energy_J_kg=9.5e6,  # ΔH_sub Ti (Chase 1998 NIST-JANAF)
)

# Beryllium (low-Z bow-shield candidate; Breakthrough Starshot reference case)
# Sputtering yields: SRIM-2013 Be table (Ziegler 2008)
ABLATION_BE = AblationMaterial(
    name="Be",
    density_kg_m3=1850.0,             # ASM Handbook vol 2
    atomic_mass_kg=9.0122 * 1.6605e-27,  # Be atomic mass, IUPAC 2021
    sputtering_yield_H=0.03,          # SRIM-2013 Be/H at ~4.7 MeV (Ziegler 2008)
    sputtering_yield_He=0.10,         # Matsunami 1984
    specific_ablation_energy_J_kg=32.4e6,  # ΔH_sub Be (Chase 1998 NIST-JANAF)
)

# Carbon-carbon composite (Hoang 2017 reference shield material)
ABLATION_C_C = AblationMaterial(
    name="C-C composite",
    density_kg_m3=1750.0,             # typical CFC density (Savage 1993 Composites)
    atomic_mass_kg=12.011 * 1.6605e-27,  # C atomic mass, IUPAC 2021
    sputtering_yield_H=0.07,          # SRIM-2013 C/H at 4.7 MeV (Ziegler 2008)
    sputtering_yield_He=0.20,         # Matsunami 1984
    specific_ablation_energy_J_kg=59.0e6,  # ΔH_sub graphite (Chase 1998 NIST-JANAF)
)


# ── Regime flag ───────────────────────────────────────────────────────────────

# Above ~5 km/s grain impacts enter the plasma-ablation regime (Hoang 2017)
PLASMA_ABLATION_VELOCITY_M_S: float = 5.0e3


def is_plasma_ablation_regime(velocity_m_s: float) -> bool:
    """True when grain impact velocity exceeds the plasma-ablation threshold.

    Above ~5 km/s, impact energy density per unit area exceeds the
    material's sublimation threshold and the physics shifts from
    mechanical cratering to plasma formation and ablation.

    Reference: Hoang et al. 2017 ApJ 847:77 §3.
    """
    if velocity_m_s < 0.0:
        raise ValueError("velocity_m_s must be non-negative")
    return velocity_m_s > PLASMA_ABLATION_VELOCITY_M_S


# ── Proton / alpha flux ───────────────────────────────────────────────────────

def ism_proton_flux_per_m2_s(
    velocity_m_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
) -> float:
    """Number of ISM protons striking the bow per m² per second.

    Φ_H = n_H × v  [m⁻² s⁻¹]

    In the ship frame, ISM hydrogen appears as a beam at relative speed v.

    Args:
        velocity_m_s: Ship velocity relative to LSR [m/s].
        n_H_per_m3: ISM H number density [m⁻³].

    Returns:
        Proton flux [m⁻² s⁻¹].
    """
    if velocity_m_s < 0.0:
        raise ValueError("velocity_m_s must be non-negative")
    return n_H_per_m3 * velocity_m_s


def ism_alpha_flux_per_m2_s(
    velocity_m_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
    he_h_ratio: float = ISM_HE_H_RATIO,
) -> float:
    """Alpha-particle (He²⁺) flux striking the bow per m² per second.

    Φ_He = he_h_ratio × n_H × v

    Args:
        velocity_m_s: Ship velocity [m/s].
        n_H_per_m3: ISM H number density [m⁻³].
        he_h_ratio: He/H number ratio (default Frisch 2011).

    Returns:
        Alpha flux [m⁻² s⁻¹].
    """
    return he_h_ratio * ism_proton_flux_per_m2_s(velocity_m_s, n_H_per_m3)


def proton_kinetic_energy_J(velocity_m_s: float) -> float:
    """Relativistic KE of a single ISM proton in the ship frame [J].

    KE = (γ − 1) m_p c²

    At 0.1 c: γ = 1.00504, KE ≈ 7.5×10⁻¹³ J (4.7 MeV).

    Args:
        velocity_m_s: Ship (= proton beam) speed [m/s].

    Returns:
        Proton kinetic energy [J].
    """
    gamma = _lorentz_gamma(velocity_m_s)
    return (gamma - 1.0) * M_PROTON_KG * SPEED_OF_LIGHT_M_S**2


# ── Sputtering mass-loss rate ─────────────────────────────────────────────────

def gas_sputtering_rate_kg_m2_s(
    material: AblationMaterial,
    velocity_m_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
    he_h_ratio: float = ISM_HE_H_RATIO,
) -> float:
    """Mass ablation rate from ISM gas-ion sputtering [kg m⁻² s⁻¹].

    Combines H⁺ and He²⁺ contributions:

        ṁ_sput = (Φ_H × S_H + Φ_He × S_He) × m_atom

    where S is the sputtering yield [atoms/ion] at the cruise-velocity
    proton/alpha energy (from Matsunami 1984 / SRIM-2013 tables).

    Args:
        material: Shield material with sputtering yields.
        velocity_m_s: Ship speed [m/s].
        n_H_per_m3: ISM hydrogen number density [m⁻³].
        he_h_ratio: He/H number ratio.

    Returns:
        Sputtering-driven mass loss rate [kg m⁻² s⁻¹]. Non-negative.
    """
    phi_H = ism_proton_flux_per_m2_s(velocity_m_s, n_H_per_m3)
    phi_He = he_h_ratio * phi_H
    atoms_per_m2_s = (
        phi_H  * material.sputtering_yield_H
        + phi_He * material.sputtering_yield_He
    )
    return atoms_per_m2_s * material.atomic_mass_kg


# ── Dust-grain ablation rate ──────────────────────────────────────────────────

def ism_dust_flux_kg_m2_s(
    velocity_m_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
    dust_gas_ratio: float = ISM_DUST_GAS_RATIO,
) -> float:
    """Mass flux of ISM dust grains hitting the bow per m² per second [kg m⁻² s⁻¹].

    ρ_dust = dust_gas_ratio × n_H × m_H
    ṁ_dust = ρ_dust × v

    Args:
        velocity_m_s: Ship speed [m/s].
        n_H_per_m3: ISM H number density [m⁻³].
        dust_gas_ratio: Dust-to-gas mass ratio (Draine & Lee 1984).

    Returns:
        Dust mass flux [kg m⁻² s⁻¹].
    """
    rho_dust = dust_gas_ratio * n_H_per_m3 * M_PROTON_KG
    return rho_dust * velocity_m_s


def dust_grain_ablation_rate_kg_m2_s(
    material: AblationMaterial,
    velocity_m_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
    dust_gas_ratio: float = ISM_DUST_GAS_RATIO,
    grain_mass_kg: float = ISM_MEAN_GRAIN_MASS_KG,
) -> float:
    """Mass ablation rate of shield caused by dust-grain impacts [kg m⁻² s⁻¹].

    In the plasma-ablation regime (v ≫ 5 km/s at ARIA cruise) each grain
    deposits its full kinetic energy into a plasmoid that erodes the
    shield. The shield mass ablated per grain impact is:

        Δm_shield = KE_grain / E_abl

    where E_abl = specific_ablation_energy_J_kg × Δm_grain, but we use
    the simpler form:

        ṁ_shield_abl = (grain_KE / E_abl_per_kg) × grain_flux

    with grain_flux = dust_mass_flux / grain_mass (grains m⁻² s⁻¹).

    At v = 0.1 c, grain KE ≫ E_abl for μm grains, so the shield
    mass eroded per grain ≈ KE_grain / E_abl_specific.

    Reference: Hoang et al. 2017 ApJ 847:77 eq. 12 (plasma ablation limit).

    Args:
        material: Shield material.
        velocity_m_s: Ship speed [m/s].
        n_H_per_m3: ISM H number density [m⁻³].
        dust_gas_ratio: Dust-to-gas mass ratio.
        grain_mass_kg: Representative grain mass [kg].

    Returns:
        Dust-ablation mass loss rate [kg m⁻² s⁻¹].
    """
    gamma = _lorentz_gamma(velocity_m_s)
    grain_ke_J = (gamma - 1.0) * grain_mass_kg * SPEED_OF_LIGHT_M_S**2

    # grains per m² per s
    dust_flux = ism_dust_flux_kg_m2_s(velocity_m_s, n_H_per_m3, dust_gas_ratio)
    grain_flux = dust_flux / grain_mass_kg

    # shield mass ablated per grain impact [kg] (Hoang 2017)
    shield_mass_per_grain = grain_ke_J / material.specific_ablation_energy_J_kg

    return grain_flux * shield_mass_per_grain


# ── Total ablation ────────────────────────────────────────────────────────────

def ism_ablation_rate_kg_m2_s(
    material: AblationMaterial,
    velocity_m_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
    he_h_ratio: float = ISM_HE_H_RATIO,
    dust_gas_ratio: float = ISM_DUST_GAS_RATIO,
    grain_mass_kg: float = ISM_MEAN_GRAIN_MASS_KG,
) -> float:
    """Total front-shield mass ablation rate from ISM at cruise speed [kg m⁻² s⁻¹].

    Combines ion sputtering and dust-grain plasma ablation:

        ṁ_total = ṁ_sput + ṁ_dust_abl

    Args:
        material: Shield material.
        velocity_m_s: Ship speed relative to LSR [m/s].
        n_H_per_m3: ISM H number density [m⁻³].
        he_h_ratio: He/H number ratio.
        dust_gas_ratio: Dust-to-gas mass ratio.
        grain_mass_kg: Representative grain mass [kg].

    Returns:
        Total ablation rate [kg m⁻² s⁻¹]. Non-negative.
    """
    sput = gas_sputtering_rate_kg_m2_s(material, velocity_m_s, n_H_per_m3, he_h_ratio)
    dust = dust_grain_ablation_rate_kg_m2_s(
        material, velocity_m_s, n_H_per_m3, dust_gas_ratio, grain_mass_kg
    )
    return sput + dust


def ism_ablation_depth_m(
    material: AblationMaterial,
    velocity_m_s: float,
    time_s: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
    he_h_ratio: float = ISM_HE_H_RATIO,
    dust_gas_ratio: float = ISM_DUST_GAS_RATIO,
    grain_mass_kg: float = ISM_MEAN_GRAIN_MASS_KG,
) -> float:
    """Cumulative ablation depth of the front shield over time_s [m].

    depth = (ṁ_total / ρ_shield) × time_s

    Args:
        material: Shield material.
        velocity_m_s: Ship speed [m/s].
        time_s: Duration at cruise speed [s].
        n_H_per_m3: ISM H number density [m⁻³].
        he_h_ratio: He/H number ratio.
        dust_gas_ratio: Dust-to-gas mass ratio.
        grain_mass_kg: Representative grain mass [kg].

    Returns:
        Cumulative ablation depth [m]. Non-negative.
    """
    if time_s <= 0.0:
        return 0.0
    rate = ism_ablation_rate_kg_m2_s(
        material, velocity_m_s, n_H_per_m3, he_h_ratio, dust_gas_ratio, grain_mass_kg
    )
    return (rate / material.density_kg_m3) * time_s


def mission_ablation_budget(
    material: AblationMaterial,
    velocity_m_s: float,
    mission_duration_yr: float,
    initial_shield_thickness_m: float,
    n_H_per_m3: float = ISM_N_H_PER_M3,
) -> dict:
    """Ablation budget over a full interstellar mission.

    Returns a dict with:
        ablation_rate_kg_m2_s : float
        ablation_depth_m       : float — total depth eroded
        fraction_eroded        : float — depth / initial thickness
        shield_survives        : bool  — True if depth < thickness

    Args:
        material: Shield material.
        velocity_m_s: Cruise speed [m/s].
        mission_duration_yr: Mission duration [years].
        initial_shield_thickness_m: Front-shield thickness [m].
        n_H_per_m3: ISM H number density [m⁻³].

    Returns:
        Ablation budget dict.
    """
    S_PER_YR = 365.25 * 86400.0        # seconds per year (Julian year)
    time_s = mission_duration_yr * S_PER_YR
    rate = ism_ablation_rate_kg_m2_s(material, velocity_m_s, n_H_per_m3)
    depth = (rate / material.density_kg_m3) * time_s
    fraction = depth / initial_shield_thickness_m if initial_shield_thickness_m > 0.0 else float("inf")
    return {
        "ablation_rate_kg_m2_s": rate,
        "ablation_depth_m": depth,
        "fraction_eroded": fraction,
        "shield_survives": depth < initial_shield_thickness_m,
    }
