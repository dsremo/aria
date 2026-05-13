"""First-principles combustion kinetics for spacecraft fire safety.

Provides Arrhenius rate-based models for:

1. GLOBAL ONE-STEP REACTION RATES (Westbrook & Dryer 1981)
   For hydrocarbon-air mixtures the overall reaction rate follows:

       ω [mol/m³/s] = A × [fuel]^a × [O₂]^b × exp(−E_a / (R × T))

   where A, a, b, E_a are fitted from flame-speed experiments.

2. ADIABATIC FLAME TEMPERATURE (Borman & Ragland 1998)
   The maximum temperature rise at stoichiometric conditions, from
   enthalpy balance at constant pressure:

       T_ad = T_reactants + ΔH_c / (c_p_products × (1 + (1/AFR)))

3. LAMINAR FLAME SPEED (Metghalchi & Keck 1982)
   Empirical fit for lean/rich flames across temperature and pressure:

       S_L = S_L0 × (T/T_ref)^α × (P/P_ref)^β × (1 − 2.1 × Y_diluent)

4. OXYGEN INDEX (ASTM D2863)
   Minimum O₂ fraction required to sustain flame propagation:
   critical LOI criterion used by NASA STD-6001 flammability testing.

5. FLASHOVER CRITERION (Quintiere 1995)
   Cabin fire escalation to full-room flashover condition:
   heat release rate threshold Q_fo based on opening factor.

6. MICROGRAVITY CORRECTIONS
   At reduced gravity, buoyancy-driven convection decreases.
   The flame speed reduction factor for microgravity is applied
   from Ronney 1985 (spherical diffusion flame limit) and Olson 1991
   (radiative extinction limit).

SPACECRAFT-SPECIFIC CONTEXT
---------------------------
- Cabin O₂ is typically 21% at 101.325 kPa (normal), but some
  early designs used elevated O₂ (Apollo 1: ~100% O₂ at 16 psia →
  catastrophic — Bond 1967 NASA accident report).
- ISS atmosphere: 21% O₂, 79% N₂, 101.3 kPa (NASA SSP 41000).
- Materials tested per NASA-STD-6001B rev. F (flammability screening).
- Microgravity reduces buoyancy; flames become spherical and
  oxygen-transport-limited (Berlad 1972).

References
----------
Westbrook & Dryer 1981 Prog Energy Combust Sci 10:1 — global kinetics
Metghalchi & Keck 1982 Combust Flame 48:191 — laminar flame speed
Borman & Ragland 1998 Combustion Engineering McGraw-Hill ISBN 0070066418
Quintiere 1995 Fire Mater 19:179 — flashover criterion
Ronney 1985 Combust Flame 62:121 — microgravity flame speed
Olson 1991 Combust Flame 83:129 — radiative extinction limit, μg
NASA-STD-6001B — flammability, offgassing compatibility requirements
Bond 1967 NASA TM-X-67565 — Apollo 1 fire investigation report
"""

from __future__ import annotations

import math
from dataclasses import dataclass

R_GAS: float = 8.314   # J/(mol·K) universal gas constant (NIST CODATA 2018)

# ── Fuel kinetic parameters ────────────────────────────────────────────────────

@dataclass(frozen=True)
class FuelKinetics:
    """Global one-step Arrhenius kinetics parameters.

    Rate: ω = A × [fuel]^a × [O₂]^b × exp(−E_a / (R × T))
    Units: A in (mol/m³)^(1−a−b) × m³/mol/s

    Attributes:
        name: Fuel name.
        A: Pre-exponential factor [(mol/m³)^(1-a-b) / s].
        E_a: Global activation energy [J/mol].
        a: Fuel concentration exponent.
        b: O₂ concentration exponent.
        stoich_O2_mol_per_mol_fuel: Stoichiometric O₂ moles per mole fuel.
        delta_H_c_J_mol: Heat of combustion [J/mol fuel] (LHV).
        M_fuel_kg_mol: Molar mass of fuel [kg/mol].
        S_L0_m_s: Laminar flame speed at T_ref, P_ref [m/s].
        alpha_SL: Temperature exponent for S_L (Metghalchi & Keck 1982).
        beta_SL: Pressure exponent for S_L (Metghalchi & Keck 1982).
        loi: Limiting oxygen index (volume fraction) per NASA-STD-6001B.
    """
    name: str
    A: float            # (mol/m³)^(1-a-b)/s
    E_a: float          # J/mol
    a: float            # fuel exponent
    b: float            # O₂ exponent
    stoich_O2_mol_per_mol_fuel: float
    delta_H_c_J_mol: float
    M_fuel_kg_mol: float
    S_L0_m_s: float
    alpha_SL: float
    beta_SL: float
    loi: float          # LOI volume fraction (e.g. 0.21 for most hydrocarbons)


# Methane (CH₄): primary cabin air contaminant and worst-case spacecraft fire scenario
# Westbrook & Dryer 1981 Table I
METHANE = FuelKinetics(
    name="methane (CH₄)",
    A=2.119e11,            # Westbrook & Dryer 1981 Table I (adjusted for SI)
    E_a=2.027e5,           # 202.7 kJ/mol (Westbrook & Dryer 1981 Table I)
    a=0.20,                # fuel exponent (Westbrook & Dryer 1981)
    b=1.30,                # O₂ exponent (Westbrook & Dryer 1981)
    stoich_O2_mol_per_mol_fuel=2.0,   # CH₄ + 2O₂ → CO₂ + 2H₂O
    delta_H_c_J_mol=802.3e3,          # 802.3 kJ/mol LHV (NIST WebBook)
    M_fuel_kg_mol=0.01604,            # CH₄ (IUPAC 2021)
    S_L0_m_s=0.448,        # stoichiometric, 1 atm, 298 K (Metghalchi & Keck 1982)
    alpha_SL=1.83,         # Metghalchi & Keck 1982 Table 2
    beta_SL=-0.356,        # Metghalchi & Keck 1982 Table 2
    loi=0.21,              # barely flammable at 21% O₂ (NASA-STD-6001B tests)
)

# Ethanol (C₂H₅OH): common spacecraft cleaning solvent
# Westbrook & Dryer 1981; Metghalchi & Keck 1982
ETHANOL = FuelKinetics(
    name="ethanol (C₂H₅OH)",
    A=1.584e12,            # Westbrook & Dryer 1981 (similar to n-heptane)
    E_a=1.255e5,           # 125.5 kJ/mol (Westbrook & Dryer 1981)
    a=0.15,
    b=1.60,
    stoich_O2_mol_per_mol_fuel=3.0,   # C₂H₅OH + 3O₂ → 2CO₂ + 3H₂O
    delta_H_c_J_mol=1235.0e3,         # 1235 kJ/mol LHV (NIST WebBook)
    M_fuel_kg_mol=0.04607,            # C₂H₅OH (IUPAC 2021)
    S_L0_m_s=0.440,        # Metghalchi & Keck 1982
    alpha_SL=1.75,         # Metghalchi & Keck 1982
    beta_SL=-0.17,
    loi=0.21,              # NASA-STD-6001B
)

# n-Heptane (C₇H₁₆): surrogate for cable insulation thermal decomposition
# Westbrook & Dryer 1981 Table I
N_HEPTANE = FuelKinetics(
    name="n-heptane (C₇H₁₆)",
    A=5.058e9,             # Westbrook & Dryer 1981 Table I
    E_a=1.255e5,           # 125.5 kJ/mol (Westbrook & Dryer 1981)
    a=0.25,
    b=1.50,
    stoich_O2_mol_per_mol_fuel=11.0,  # C₇H₁₆ + 11O₂ → 7CO₂ + 8H₂O
    delta_H_c_J_mol=4502.0e3,         # 4502 kJ/mol LHV (NIST WebBook)
    M_fuel_kg_mol=0.10021,            # C₇H₁₆ (IUPAC 2021)
    S_L0_m_s=0.390,        # Metghalchi & Keck 1982
    alpha_SL=1.80,         # Metghalchi & Keck 1982
    beta_SL=-0.16,
    loi=0.21,
)

# Hydrogen (H₂): electrolysis product, risk in OGA compartment
# Westbrook & Dryer 1981 Table I; very wide flammability range 4–75% H₂
HYDROGEN = FuelKinetics(
    name="hydrogen (H₂)",
    A=1.800e10,            # Westbrook & Dryer 1981 Table I
    E_a=3.347e4,           # 33.47 kJ/mol (Westbrook & Dryer 1981)
    a=1.00,
    b=1.10,
    stoich_O2_mol_per_mol_fuel=0.5,   # H₂ + 0.5 O₂ → H₂O
    delta_H_c_J_mol=241.8e3,          # 241.8 kJ/mol LHV (NIST WebBook)
    M_fuel_kg_mol=0.002016,           # H₂ (IUPAC 2021)
    S_L0_m_s=2.91,         # stoichiometric air (Qin et al. 2000 Proc Combust Inst 28)
    alpha_SL=1.54,         # Metghalchi & Keck 1982 extrapolation
    beta_SL=-0.20,
    loi=0.05,              # LOI 5% (very low — wide flammability range)
)


# ── Reference conditions ───────────────────────────────────────────────────────

T_REF_K: float = 298.0    # Metghalchi & Keck reference temperature [K]
P_REF_PA: float = 101325.0  # reference pressure [Pa]


# ── Core kinetic functions ─────────────────────────────────────────────────────

def molar_concentration_mol_m3(
    mole_fraction: float,
    total_pressure_Pa: float,
    temperature_K: float,
) -> float:
    """Molar concentration from ideal gas law [mol/m³].

    [X] = x × P / (R × T)

    Args:
        mole_fraction: Species mole fraction [0, 1].
        total_pressure_Pa: Total pressure [Pa].
        temperature_K: Temperature [K].

    Returns:
        Molar concentration [mol/m³].
    """
    if temperature_K <= 0.0:
        raise ValueError("temperature_K must be > 0")
    return mole_fraction * total_pressure_Pa / (R_GAS * temperature_K)


def global_reaction_rate_mol_m3_s(
    fuel: FuelKinetics,
    fuel_mole_fraction: float,
    o2_mole_fraction: float,
    temperature_K: float,
    pressure_Pa: float = P_REF_PA,
) -> float:
    """Global one-step volumetric reaction rate [mol m⁻³ s⁻¹].

    ω = A × [fuel]^a × [O₂]^b × exp(−E_a / (R × T))

    Returns 0 below 500 K (below any ignition threshold) to prevent
    spurious pre-ignition reactions.

    Args:
        fuel: Fuel kinetic parameters.
        fuel_mole_fraction: Fuel mole fraction [0, 1].
        o2_mole_fraction: O₂ mole fraction [0, 1].
        temperature_K: Temperature [K].
        pressure_Pa: Total pressure [Pa].

    Returns:
        Reaction rate [mol m⁻³ s⁻¹]. Non-negative.
    """
    if temperature_K < 500.0:
        return 0.0
    if fuel_mole_fraction <= 0.0 or o2_mole_fraction <= 0.0:
        return 0.0
    C_fuel = molar_concentration_mol_m3(fuel_mole_fraction, pressure_Pa, temperature_K)
    C_O2 = molar_concentration_mol_m3(o2_mole_fraction, pressure_Pa, temperature_K)
    return (
        fuel.A
        * (C_fuel ** fuel.a)
        * (C_O2 ** fuel.b)
        * math.exp(-fuel.E_a / (R_GAS * temperature_K))
    )


def heat_release_rate_W_m3(
    fuel: FuelKinetics,
    fuel_mole_fraction: float,
    o2_mole_fraction: float,
    temperature_K: float,
    pressure_Pa: float = P_REF_PA,
) -> float:
    """Volumetric heat release rate [W/m³].

    Q̇ = ω × ΔH_c

    Args:
        fuel: Fuel kinetic parameters.
        fuel_mole_fraction: Fuel mole fraction.
        o2_mole_fraction: O₂ mole fraction.
        temperature_K: Temperature [K].
        pressure_Pa: Total pressure [Pa].

    Returns:
        Heat release rate [W/m³].
    """
    omega = global_reaction_rate_mol_m3_s(
        fuel, fuel_mole_fraction, o2_mole_fraction, temperature_K, pressure_Pa
    )
    return omega * fuel.delta_H_c_J_mol


def adiabatic_flame_temperature_K(
    fuel: FuelKinetics,
    equivalence_ratio: float,
    T_reactants_K: float,
    pressure_Pa: float = P_REF_PA,
    cp_products_J_mol_K: float = 39.6,
) -> float:
    """Adiabatic flame temperature [K] for a premixed charge.

    For a lean/stoichiometric mixture:

        T_ad = T_reactants + ΔH_c × min(φ, 1) / (c_p × n_products)

    where n_products is the total moles of products per mole of fuel,
    approximated by the stoichiometric product count. This is a
    first-order estimate; proper T_ad requires equilibrium chemistry.

    Args:
        fuel: Fuel kinetic parameters.
        equivalence_ratio: φ = (fuel/O₂)_actual / (fuel/O₂)_stoich.
            φ < 1 → lean; φ = 1 → stoichiometric; φ > 1 → rich.
        T_reactants_K: Initial mixture temperature [K].
        pressure_Pa: Pressure [Pa] (weak effect on T_ad; used for n_products).
        cp_products_J_mol_K: Mean molar heat capacity of products [J/mol/K].
            Default 33 J/mol/K ≈ CO₂/H₂O mixture (Borman & Ragland 1998 Table 2).

    Returns:
        Adiabatic flame temperature [K].
    """
    if equivalence_ratio <= 0.0:
        raise ValueError("equivalence_ratio must be > 0")
    phi_burn = min(equivalence_ratio, 1.0)
    # Product moles per mole of fuel (combustion in air, 79/21 N₂/O₂):
    #   n_CO₂+H₂O ≈ stoich_O₂ × 1.5  (average for CxHy)
    #   n_N₂      = stoich_O₂ × 3.762 (79/21 ratio from air)
    # Total: stoich_O₂ × 5.262 — includes N₂ heat sink (Borman & Ragland 1998 §3.2)
    n_products = fuel.stoich_O2_mol_per_mol_fuel * 5.262
    dT = (phi_burn * fuel.delta_H_c_J_mol) / (cp_products_J_mol_K * n_products)
    return T_reactants_K + dT


def laminar_flame_speed_m_s(
    fuel: FuelKinetics,
    equivalence_ratio: float,
    temperature_K: float,
    pressure_Pa: float = P_REF_PA,
    diluent_volume_fraction: float = 0.0,
) -> float:
    """Laminar flame speed [m/s] via Metghalchi & Keck 1982 correlation.

    S_L = S_L0 × (T / T_ref)^α × (P / P_ref)^β × (1 − 2.1 × Y_d)

    where S_L0 is the speed at reference conditions for the given φ,
    approximated here by a parabolic fit centred on φ = 1.

    Args:
        fuel: Fuel kinetics with S_L0 (at φ = 1, T_ref, P_ref).
        equivalence_ratio: φ (1.0 = stoichiometric).
        temperature_K: Unburned mixture temperature [K].
        pressure_Pa: Pressure [Pa].
        diluent_volume_fraction: Volume fraction of inert diluent (N₂, CO₂).

    Returns:
        Laminar flame speed [m/s]. Clamped to ≥ 0.
    """
    if equivalence_ratio <= 0.0:
        return 0.0
    # Parabolic φ dependence: S_L0(φ) ≈ S_L0_stoich × (1 − 4 × (φ−1)²) clamped
    phi_factor = max(0.0, 1.0 - 4.0 * (equivalence_ratio - 1.0) ** 2)
    S_L0_phi = fuel.S_L0_m_s * phi_factor
    T_factor = (temperature_K / T_REF_K) ** fuel.alpha_SL
    P_factor = (pressure_Pa / P_REF_PA) ** fuel.beta_SL
    diluent_factor = max(0.0, 1.0 - 2.1 * diluent_volume_fraction)
    return S_L0_phi * T_factor * P_factor * diluent_factor


def is_above_loi(
    fuel: FuelKinetics,
    o2_mole_fraction: float,
) -> bool:
    """True if O₂ fraction exceeds the Limiting Oxygen Index for this fuel.

    The LOI (ASTM D2863) is the minimum O₂ fraction required to sustain
    downward flame propagation. Used by NASA-STD-6001B for material
    flammability screening.

    Args:
        fuel: Fuel with LOI value.
        o2_mole_fraction: Ambient O₂ mole fraction.

    Returns:
        True if flame propagation is possible (O₂ ≥ LOI).
    """
    return o2_mole_fraction >= fuel.loi


def stoichiometric_o2_mass_fraction(fuel: FuelKinetics) -> float:
    """Stoichiometric O₂ mass per unit fuel mass (Air-Fuel Ratio O₂ side).

    O₂ required = stoich_O2 × M_O2 / M_fuel

    Args:
        fuel: Fuel kinetics.

    Returns:
        kg O₂ per kg fuel (stoichiometric).
    """
    M_O2_KG_MOL = 0.031998   # O₂ molar mass (IUPAC 2021)
    return fuel.stoich_O2_mol_per_mol_fuel * M_O2_KG_MOL / fuel.M_fuel_kg_mol


# ── Microgravity corrections ──────────────────────────────────────────────────

# Ronney 1985 Combust Flame 62:121 — flame speed reduction in microgravity
# At 0 g, buoyancy is absent; S_L measured in drop towers is ~15–30% lower
# than 1 g for near-stoichiometric mixtures.
MICROGRAVITY_FLAME_SPEED_FACTOR: float = 0.80  # Ronney 1985; Olson 1991

# Olson 1991 Combust Flame 83:129 — radiative extinction limit
# In microgravity, thin flames lose heat by radiation to the environment;
# below S_L_ext flame extinguishes.
RADIATIVE_EXTINCTION_FLAME_SPEED_M_S: float = 0.05  # Olson 1991 Table 1


def microgravity_flame_speed_m_s(
    fuel: FuelKinetics,
    equivalence_ratio: float,
    temperature_K: float,
    pressure_Pa: float = P_REF_PA,
    g_fraction: float = 0.0,
) -> float:
    """Laminar flame speed corrected for reduced gravity [m/s].

    Linearly interpolates between the 1-g and 0-g factors, then checks
    the radiative extinction limit. Returns 0 if extinction applies.

    Args:
        fuel: Fuel kinetics.
        equivalence_ratio: φ.
        temperature_K: Unburned temperature [K].
        pressure_Pa: Pressure [Pa].
        g_fraction: Gravity fraction (0.0 = microgravity, 1.0 = 1 g).

    Returns:
        Effective laminar flame speed [m/s] at reduced gravity.
    """
    S_L_1g = laminar_flame_speed_m_s(fuel, equivalence_ratio, temperature_K, pressure_Pa)
    g_factor = MICROGRAVITY_FLAME_SPEED_FACTOR + (1.0 - MICROGRAVITY_FLAME_SPEED_FACTOR) * g_fraction
    S_L_g = S_L_1g * g_factor
    # Radiative extinction: if S_L_g < extinction limit in microgravity, flame cannot sustain
    if g_fraction < 0.01 and S_L_g < RADIATIVE_EXTINCTION_FLAME_SPEED_M_S:
        return 0.0
    return max(0.0, S_L_g)


# ── Flashover criterion ───────────────────────────────────────────────────────

def flashover_hrr_threshold_W(
    room_floor_area_m2: float,
    opening_area_m2: float,
    opening_height_m: float,
) -> float:
    """Minimum heat release rate for cabin flashover [W].

    Quintiere 1995 correlation:

        Q_fo = 750 × (h_k × A_T × A_o √h_o)^0.5

    where A_T ≈ 6 × A_floor (total surface area estimate for a cube),
    h_k is the effective heat transfer coefficient to walls (set to
    a nominal 0.04 kW/m²/K for typical spacecraft composite panels),
    A_o = opening area [m²], h_o = opening height [m].

    Reference: Quintiere 1995 Fire Mater 19:179.

    Args:
        room_floor_area_m2: Floor area [m²] (room/module area).
        opening_area_m2: Door/vent opening area [m²].
        opening_height_m: Opening height [m].

    Returns:
        Flashover threshold HRR [W].
    """
    A_T = 6.0 * room_floor_area_m2          # total enclosure surface area
    h_k = 0.04e3                             # 0.04 kW/m²/K → 40 W/m²/K (spacecraft composite)
    # Quintiere 1995 eq. (coefficients in kW; convert to W)
    Q_fo_kW = 750.0 * math.sqrt(h_k * A_T * opening_area_m2 * math.sqrt(opening_height_m)) / 1000.0
    return Q_fo_kW * 1000.0


def is_flashover_risk(
    heat_release_rate_W: float,
    room_floor_area_m2: float,
    opening_area_m2: float,
    opening_height_m: float,
) -> bool:
    """True when actual HRR ≥ flashover threshold.

    Args:
        heat_release_rate_W: Actual HRR [W].
        room_floor_area_m2: Room floor area [m²].
        opening_area_m2: Opening area [m²].
        opening_height_m: Opening height [m].

    Returns:
        True if flashover is imminent.
    """
    return heat_release_rate_W >= flashover_hrr_threshold_W(
        room_floor_area_m2, opening_area_m2, opening_height_m
    )
