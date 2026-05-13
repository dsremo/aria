"""Propellant tank pressurization: blowdown and regulated systems.

Spacecraft propellant systems require a pressurant (He, N₂, or GN₂) to
expel propellant from the tank to the thruster. Two architectures:

1. BLOWDOWN — single sealed pressurant charge at top of tank. As propellant
   is expelled, ullage volume increases and pressurant expands → pressure
   falls over mission. Simpler but thrust varies with pressure.

2. REGULATED — separate high-pressure pressurant bottle with regulator
   maintains constant feed pressure. More mass but constant thrust.

BLOWDOWN PRESSURE MODELS
--------------------------
The pressurant expands from initial ullage volume V_u0 to V_u(t):

  ISOTHERMAL (slow expulsion, heat exchange with walls):
      P(V_u) = P_0 × V_u0 / V_u

  ADIABATIC (fast expulsion, no heat exchange):
      P(V_u) = P_0 × (V_u0 / V_u)^γ

In practice, real systems lie between these limits. A polytropic
model with exponent n interpolates between them (n=1 isothermal,
n=γ adiabatic).

PRESSURANT ABSORPTION (HENRY'S LAW)
--------------------------------------
He and N₂ dissolve into bipropellant liquids (MMH, N₂O₄, hydrazine) per
Henry's law:
    C = k_H(T) × P_partial   [mol/m³]

where k_H is the Henry's law constant. Gas dissolved into the propellant
reduces the effective pressurant volume, causing a larger pressure drop
than a purely gaseous model predicts. For He in hydrazine:
    k_H ≈ 1.4×10⁻⁷ mol/(m³·Pa) at 20°C  (Wiktorowicz 1972).

PRESSURANT MASS BUDGET
-----------------------
Required pressurant mass for regulated (constant-pressure) expulsion:

    m_press = P_feed × V_prop / (R_specific × T) × (1 + f_absorption)

where R_specific = R_universal / M_press and f_absorption accounts for
dissolved gas.

References
----------
Larson & Wertz 1999 *Space Mission Engineering* §18 — pressurant sizing
Wiktorowicz S. 1972 AIAA 72-1077 — He/hydrazine absorption
Huzel & Huang 1992 *Modern Engineering for Design of Liquid Propellant
  Rocket Engines* Chapter 4 — blowdown and regulated systems
Brown C.D. 2002 *Spacecraft Propulsion* AIAA Education Series — tank design
NASA SP-8071 1975 — metallic propellant tanks (design reference)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

R_UNIVERSAL: float = 8.314   # J/(mol·K) (NIST CODATA 2018)


# ── Pressurant gas properties ─────────────────────────────────────────────────

@dataclass(frozen=True)
class PressurantGas:
    """Properties of a pressurant gas for blowdown/regulated systems.

    Attributes:
        name: Gas name.
        molar_mass_kg_mol: Molar mass [kg/mol].
        gamma: Heat capacity ratio Cp/Cv [dimensionless].
        henry_k_mol_m3_Pa: Henry's law constant in hydrazine at 293 K [mol/(m³·Pa)].
            Set to 0 if absorption is negligible.
    """
    name: str
    molar_mass_kg_mol: float
    gamma: float
    henry_k_mol_m3_Pa: float


# Helium — lightest; minimal absorption; Wiktorowicz 1972 AIAA 72-1077
HELIUM = PressurantGas(
    name="He",
    molar_mass_kg_mol=0.004003,  # IUPAC 2021
    gamma=5.0 / 3.0,             # monatomic ideal gas (exactly 5/3)
    henry_k_mol_m3_Pa=1.4e-7,   # Wiktorowicz 1972 (He in hydrazine, 20°C)
)

# Nitrogen — heavier; more absorbed; common in regulated systems
# Henry's constant: N₂ in hydrazine (approx from solubility at 20°C, Larson 1999)
NITROGEN = PressurantGas(
    name="N₂",
    molar_mass_kg_mol=0.028014,  # IUPAC 2021
    gamma=7.0 / 5.0,             # diatomic ideal gas (7/5)
    henry_k_mol_m3_Pa=6.0e-7,   # Larson & Wertz 1999 §18 (N₂ in hydrazine approx)
)

# GN₂ (gaseous nitrogen) — same as N₂ for physics purposes
GN2 = NITROGEN


# ── Blowdown pressure models ──────────────────────────────────────────────────

def blowdown_pressure_Pa(
    initial_pressure_Pa: float,
    initial_ullage_volume_m3: float,
    final_ullage_volume_m3: float,
    gamma: float = HELIUM.gamma,
    n_polytropic: float = 1.0,
) -> float:
    """Tank pressure after blowdown expansion [Pa] using polytropic model.

    P(V) = P_0 × (V_u0 / V_u)^n

    n = 1.0 → isothermal (Boyle's law)
    n = γ → adiabatic (isentropic)

    Reference: Huzel & Huang 1992 Ch. 4; Brown 2002 §4.3.

    Args:
        initial_pressure_Pa: Initial tank pressure [Pa].
        initial_ullage_volume_m3: Initial gas ullage volume [m³].
        final_ullage_volume_m3: Final gas ullage volume [m³].
        gamma: Heat capacity ratio (used only if n_polytropic = γ).
        n_polytropic: Polytropic exponent (1.0 = isothermal, γ = adiabatic).

    Returns:
        Tank pressure after expansion [Pa].
    """
    if initial_ullage_volume_m3 <= 0.0:
        raise ValueError("initial_ullage_volume_m3 must be > 0")
    if final_ullage_volume_m3 <= 0.0:
        raise ValueError("final_ullage_volume_m3 must be > 0")
    if initial_pressure_Pa <= 0.0:
        raise ValueError("initial_pressure_Pa must be > 0")
    volume_ratio = initial_ullage_volume_m3 / final_ullage_volume_m3
    return initial_pressure_Pa * (volume_ratio ** n_polytropic)


def blowdown_pressure_ratio(
    initial_ullage_fraction: float,
    final_ullage_fraction: float,
    n_polytropic: float = 1.0,
) -> float:
    """Pressure ratio P_final / P_initial for blowdown [dimensionless].

    Convenience function using ullage volume fractions (fraction of total
    tank volume occupied by pressurant gas).

    Args:
        initial_ullage_fraction: Initial ullage fraction [0, 1].
        final_ullage_fraction: Final ullage fraction [0, 1].
        n_polytropic: Polytropic exponent.

    Returns:
        P_final / P_initial.
    """
    if not (0.0 < initial_ullage_fraction <= 1.0):
        raise ValueError("initial_ullage_fraction must be in (0, 1]")
    if not (0.0 < final_ullage_fraction <= 1.0):
        raise ValueError("final_ullage_fraction must be in (0, 1]")
    return (initial_ullage_fraction / final_ullage_fraction) ** n_polytropic


def blowdown_pressure_ratio_isothermal(
    initial_ullage_fraction: float,
    final_ullage_fraction: float,
) -> float:
    """Isothermal blowdown pressure ratio (n=1).

    P_f/P_0 = V_u0 / V_uf = f_0 / f_f

    Args:
        initial_ullage_fraction: V_u0 / V_tank.
        final_ullage_fraction: V_uf / V_tank.

    Returns:
        P_f / P_0.
    """
    return blowdown_pressure_ratio(initial_ullage_fraction, final_ullage_fraction, 1.0)


def blowdown_pressure_ratio_adiabatic(
    initial_ullage_fraction: float,
    final_ullage_fraction: float,
    gamma: float = HELIUM.gamma,
) -> float:
    """Adiabatic (isentropic) blowdown pressure ratio.

    P_f/P_0 = (V_u0 / V_uf)^γ

    Args:
        initial_ullage_fraction: V_u0 / V_tank.
        final_ullage_fraction: V_uf / V_tank.
        gamma: Heat capacity ratio.

    Returns:
        P_f / P_0.
    """
    return blowdown_pressure_ratio(initial_ullage_fraction, final_ullage_fraction, gamma)


# ── Pressurant absorption (Henry's law) ───────────────────────────────────────

def dissolved_pressurant_mol_m3(
    gas: PressurantGas,
    partial_pressure_Pa: float,
    temperature_K: float,
    T_ref_K: float = 293.15,
) -> float:
    """Gas dissolved in propellant per unit liquid volume [mol/m³].

    C = k_H(T) × P_partial

    Henry's constant temperature dependence approximated by van't Hoff:
        k_H(T) ≈ k_H(T_ref) × exp(−ΔH_sol/R × (1/T − 1/T_ref))

    For He/hydrazine, ΔH_sol ≈ +12 kJ/mol (Wiktorowicz 1972 — endothermic:
    less soluble at higher T, as expected for gases).

    Args:
        gas: Pressurant gas properties.
        partial_pressure_Pa: Partial pressure of gas [Pa].
        temperature_K: Temperature [K].
        T_ref_K: Reference temperature for k_H [K].

    Returns:
        Dissolved concentration [mol/m³].
    """
    if temperature_K <= 0.0:
        raise ValueError("temperature_K must be > 0")
    # Van't Hoff: gas dissolution is exothermic → ΔH_sol < 0 → less soluble at higher T
    # ΔH_sol ≈ −12 kJ/mol for He/N₂ in hydrazine (Wiktorowicz 1972)
    DELTA_H_SOL_J_MOL = -12000.0
    k_H_T = gas.henry_k_mol_m3_Pa * math.exp(
        -DELTA_H_SOL_J_MOL / R_UNIVERSAL * (1.0 / temperature_K - 1.0 / T_ref_K)
    )
    return k_H_T * partial_pressure_Pa


def absorbed_pressurant_volume_m3(
    gas: PressurantGas,
    partial_pressure_Pa: float,
    propellant_volume_m3: float,
    temperature_K: float,
) -> float:
    """Effective volume of pressurant gas absorbed into propellant [m³].

    Converts the dissolved moles back to an equivalent gas volume at
    the tank pressure and temperature:

        V_absorbed = n_dissolved × R × T / P

    Args:
        gas: Pressurant gas properties.
        partial_pressure_Pa: Gas partial pressure [Pa].
        propellant_volume_m3: Volume of liquid propellant [m³].
        temperature_K: Temperature [K].

    Returns:
        Equivalent gas volume absorbed [m³].
    """
    C = dissolved_pressurant_mol_m3(gas, partial_pressure_Pa, temperature_K)
    n_mol = C * propellant_volume_m3
    return n_mol * R_UNIVERSAL * temperature_K / partial_pressure_Pa


def absorption_volume_fraction(
    gas: PressurantGas,
    partial_pressure_Pa: float,
    propellant_volume_m3: float,
    initial_ullage_volume_m3: float,
    temperature_K: float,
) -> float:
    """Fraction of pressurant volume absorbed relative to initial ullage [dimensionless].

    f_abs = V_absorbed / V_ullage_initial

    Reference: Larson & Wertz 1999 §18.3 (pressurant sizing with absorption).

    Args:
        gas: Pressurant gas.
        partial_pressure_Pa: Gas partial pressure [Pa].
        propellant_volume_m3: Propellant volume [m³].
        initial_ullage_volume_m3: Initial ullage volume [m³].
        temperature_K: Temperature [K].

    Returns:
        Absorption fraction (0 → no absorption; >0 → gas dissolved).
    """
    if initial_ullage_volume_m3 <= 0.0:
        raise ValueError("initial_ullage_volume_m3 must be > 0")
    V_abs = absorbed_pressurant_volume_m3(
        gas, partial_pressure_Pa, propellant_volume_m3, temperature_K
    )
    return V_abs / initial_ullage_volume_m3


# ── Pressurant mass budget ────────────────────────────────────────────────────

def pressurant_mass_kg_regulated(
    gas: PressurantGas,
    feed_pressure_Pa: float,
    propellant_volume_m3: float,
    temperature_K: float,
    absorption_fraction: float = 0.0,
) -> float:
    """Pressurant gas mass required for a regulated system [kg].

    For regulated (constant-pressure) expulsion, the pressurant must
    fill the volume vacated by all propellant plus compensate for gas
    absorbed into the propellant:

        m_press = P_feed × V_prop × (1 + f_abs) / (R_spec × T)

    where R_spec = R_universal / M_press.

    Reference: Huzel & Huang 1992 §4.2; Brown 2002 eq. 4.6.

    Args:
        gas: Pressurant gas properties.
        feed_pressure_Pa: Required feed pressure [Pa].
        propellant_volume_m3: Total propellant volume to be expelled [m³].
        temperature_K: Tank temperature [K].
        absorption_fraction: Fraction of pressurant volume absorbed
            (from absorption_volume_fraction or 0 for no absorption).

    Returns:
        Required pressurant mass [kg].
    """
    if temperature_K <= 0.0:
        raise ValueError("temperature_K must be > 0")
    R_specific = R_UNIVERSAL / gas.molar_mass_kg_mol   # J/(kg·K)
    rho_press = feed_pressure_Pa / (R_specific * temperature_K)   # ideal gas density
    return rho_press * propellant_volume_m3 * (1.0 + absorption_fraction)


def pressurant_bottle_volume_m3(
    gas: PressurantGas,
    pressurant_mass_kg: float,
    storage_pressure_Pa: float,
    temperature_K: float,
) -> float:
    """Volume of the high-pressure pressurant storage bottle [m³].

    V_bottle = m_press × R_spec × T / P_storage

    Args:
        gas: Pressurant gas.
        pressurant_mass_kg: Required pressurant mass [kg].
        storage_pressure_Pa: Bottle storage pressure [Pa].
        temperature_K: Storage temperature [K].

    Returns:
        Bottle volume [m³].
    """
    if temperature_K <= 0.0:
        raise ValueError("temperature_K must be > 0")
    if storage_pressure_Pa <= 0.0:
        raise ValueError("storage_pressure_Pa must be > 0")
    R_specific = R_UNIVERSAL / gas.molar_mass_kg_mol
    return pressurant_mass_kg * R_specific * temperature_K / storage_pressure_Pa


def blowdown_final_pressure_with_absorption(
    gas: PressurantGas,
    initial_pressure_Pa: float,
    initial_ullage_volume_m3: float,
    propellant_expelled_volume_m3: float,
    temperature_K: float,
    n_polytropic: float = 1.0,
) -> float:
    """Blowdown final pressure accounting for gas absorbed by propellant [Pa].

    The absorbed gas acts as an additional volume sink. The effective
    final ullage volume is:

        V_uf_eff = V_u0 + V_expelled - V_absorbed

    where V_absorbed = absorbed_pressurant_volume_m3(...).

    Reference: Brown 2002 §4.4.

    Args:
        gas: Pressurant gas.
        initial_pressure_Pa: Initial tank pressure [Pa].
        initial_ullage_volume_m3: Initial gas ullage [m³].
        propellant_expelled_volume_m3: Propellant volume expelled [m³].
        temperature_K: Tank temperature [K].
        n_polytropic: Polytropic exponent (1.0 = isothermal).

    Returns:
        Final tank pressure [Pa] after blowdown with absorption.
    """
    # Geometric final ullage (determined by tank volume, not gas amount)
    V_uf = initial_ullage_volume_m3 + propellant_expelled_volume_m3

    # Absorbed moles leave with expelled propellant → reduce remaining gas
    C_dissolved = dissolved_pressurant_mol_m3(gas, initial_pressure_Pa, temperature_K)
    n_abs_mol = C_dissolved * propellant_expelled_volume_m3   # moles lost to liquid
    n_initial_mol = (initial_pressure_Pa * initial_ullage_volume_m3
                     / (R_UNIVERSAL * temperature_K))
    n_remaining_mol = max(0.0, n_initial_mol - n_abs_mol)

    # Pressure from remaining moles in final geometric volume (isothermal consistent)
    P_no_abs = blowdown_pressure_Pa(
        initial_pressure_Pa,
        initial_ullage_volume_m3,
        V_uf,
        n_polytropic=n_polytropic,
    )
    # Correction: absorbed gas reduces pressure proportionally
    # ΔP = n_abs × R × T / V_uf (moles absorbed → pressure reduction)
    delta_P = n_abs_mol * R_UNIVERSAL * temperature_K / V_uf
    return max(0.0, P_no_abs - delta_P)


# ── Blowdown pressure vs time integration ────────────────────────────────────

def blowdown_pressure_history(
    gas: PressurantGas,
    initial_pressure_Pa: float,
    tank_volume_m3: float,
    initial_ullage_fraction: float,
    propellant_mass_flow_kg_s: float,
    propellant_density_kg_m3: float,
    duration_s: float,
    n_steps: int = 100,
    n_polytropic: float = 1.0,
    temperature_K: float = 293.15,
) -> list[tuple[float, float]]:
    """Time-resolved tank pressure during blowdown [Pa] at constant flow rate.

    Integrates the blowdown in n_steps uniform time steps.

    Args:
        gas: Pressurant gas.
        initial_pressure_Pa: Initial tank pressure [Pa].
        tank_volume_m3: Total tank internal volume [m³].
        initial_ullage_fraction: Initial ullage volume / tank volume.
        propellant_mass_flow_kg_s: Propellant expulsion rate [kg/s].
        propellant_density_kg_m3: Propellant liquid density [kg/m³].
        duration_s: Total blowdown duration [s].
        n_steps: Number of integration steps.
        n_polytropic: Polytropic exponent.
        temperature_K: Tank temperature [K].

    Returns:
        List of (time_s, pressure_Pa) tuples.
    """
    dt = duration_s / n_steps
    vol_flow = propellant_mass_flow_kg_s / propellant_density_kg_m3  # m³/s
    V_u = initial_ullage_fraction * tank_volume_m3
    V_u0 = V_u
    history = [(0.0, initial_pressure_Pa)]
    for i in range(1, n_steps + 1):
        t = i * dt
        V_expelled = vol_flow * t
        V_u_now = min(V_u0 + V_expelled, tank_volume_m3)
        P = blowdown_pressure_Pa(
            initial_pressure_Pa, V_u0, V_u_now, n_polytropic=n_polytropic
        )
        history.append((t, P))
    return history
