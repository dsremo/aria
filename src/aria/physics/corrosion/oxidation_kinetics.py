"""Corrosion and oxidation kinetics for spacecraft structural materials.

Models time-dependent mass gain / material loss for three kinetic regimes:

1. PARABOLIC OXIDATION (Wagner 1933, Pilling & Bedworth 1923)
   Diffusion-controlled; oxide layer thickens as √t:
       x² = k_p × t
   k_p [m²/s] is the parabolic rate constant, Arrhenius:
       k_p = A_p × exp(−Q_p / (R × T))

   Applicable when the oxide layer is protective (dense, adherent).
   Most common for stainless steels and Ti alloys above ~400°C.

2. LINEAR OXIDATION (bare-metal or spallation regime)
   Constant rate; oxide layer grows as x = k_l × t.
   Applicable when oxide spalls (non-protective) or at very short times.

3. LOGARITHMIC OXIDATION (thin-film, room temperature)
   x = k_log × ln(1 + t / t_0)
   Applicable for native oxide formation (Al, Ti at room temperature;
   Cabrera-Mott 1949).

4. PITTING CORROSION DEPTH (Godard 1967 / Szklarska-Smialowska 1999)
   In aqueous or high-humidity environments: maximum pit depth follows:
       d_pit = A_pit × t^n_pit
   where n_pit ≈ 1/3 (diffusion-limited) for aluminium alloys.

5. STRESS CORROSION CRACKING (SCC) THRESHOLD
   Compares K_I against K_ISCC for material/environment combination.
   Uses linear elastic fracture mechanics from LEFM (ASTM E1820).

SPACECRAFT CONTEXT
------------------
- Atomic oxygen (ATOX) erosion at LEO: ~8 eV O atoms at ~7.7 km/s flux
  erode polymers and unprotected surfaces (Brinza 2001 NASA TM-2001-210640).
- Galvanic corrosion at bolted joints: Ti/Al interfaces in humid cabin.
- High-temperature oxidation: reactor cladding (EUROFER97) and radiator
  fins (Mo-Re alloy) at 700–1200 K in trace O₂ environments.

References
----------
Wagner C. 1933 Z Elektrochem 63:772 — parabolic oxidation theory
Pilling & Bedworth 1923 J Inst Metals 29:529 — oxide layer growth
Cabrera N. & Mott N.F. 1949 Rep Prog Phys 12:163 — logarithmic kinetics
Brinza D.E. 2001 NASA TM-2001-210640 — ATOX erosion at LEO
Godard H.P. 1967 "Corrosion of Light Metals" Wiley — pitting kinetics
Szklarska-Smialowska Z. 1999 Corros Sci 41:1743 — pit depth power law
Joshi A.V. 1987 J Vac Sci Technol A5:1146 — EUROFER high-T oxidation proxy
Young D.J. 2008 "High Temperature Oxidation and Corrosion of Metals" — ref text
"""

from __future__ import annotations

import math
from dataclasses import dataclass

R_GAS: float = 8.314   # J/(mol·K) (NIST CODATA 2018)


# ── Oxidation material parameters ─────────────────────────────────────────────

@dataclass(frozen=True)
class OxidationMaterial:
    """Arrhenius parameters for parabolic high-temperature oxidation.

    k_p(T) = A_p × exp(−Q_p / (R × T))   [m²/s]

    Attributes:
        name: Material name.
        A_p: Pre-exponential for parabolic rate [m²/s].
        Q_p: Activation energy [J/mol].
        A_linear: Pre-exponential for linear (non-protective) rate [m/s].
        Q_linear: Activation energy for linear rate [J/mol].
        density_kg_m3: Bulk density [kg/m³] (for mass gain conversion).
        molar_mass_kg_mol: Molar mass of metal [kg/mol].
        oxide_density_kg_m3: Density of oxide layer [kg/m³].
        oxide_molar_mass_kg_mol: Molar mass of oxide [kg/mol].
    """
    name: str
    A_p: float           # m²/s
    Q_p: float           # J/mol
    A_linear: float      # m/s
    Q_linear: float      # J/mol
    density_kg_m3: float
    molar_mass_kg_mol: float
    oxide_density_kg_m3: float
    oxide_molar_mass_kg_mol: float


# Ti-6Al-4V: parabolic oxidation in air above 600°C
# Young 2008 Table 3.2; Coddet 1984 J Less-Common Met 97:289
TI_6AL_4V_OXIDATION = OxidationMaterial(
    name="Ti-6Al-4V",
    A_p=1.2e-7,             # Young 2008; Coddet 1984 regression
    Q_p=1.60e5,             # 160 kJ/mol (Coddet 1984; typical TiO₂ diffusion)
    A_linear=3.0e-8,        # breakaway oxidation at high T (>900°C)
    Q_linear=1.30e5,        # 130 kJ/mol (Stroosnijder 1998 Intermetallics 6:223)
    density_kg_m3=4430.0,   # MMPDS-17
    molar_mass_kg_mol=0.04788,  # Ti (IUPAC 2021; dominant alloy component)
    oxide_density_kg_m3=4230.0,   # TiO₂ (rutile, Young 2008)
    oxide_molar_mass_kg_mol=0.07988,  # TiO₂ (IUPAC 2021)
)

# EUROFER97 (reduced-activation ferritic-martensitic steel, 9% Cr)
# Proxy from 9Cr-1Mo steels; Joshi 1987 J Vac Sci Technol A5:1146;
# Shosmitsu 2002 Fusion Eng Des 61-62:165
EUROFER97_OXIDATION = OxidationMaterial(
    name="EUROFER97",
    A_p=8.0e-10,            # Joshi 1987 (9Cr-1Mo proxy, ~same Cr content)
    Q_p=1.67e5,             # 167 kJ/mol (Fe₂O₃/Cr₂O₃ scale diffusion; Young 2008)
    A_linear=1.0e-10,       # breakaway (spallation above 900°C)
    Q_linear=1.20e5,
    density_kg_m3=7750.0,   # EUROFER97 (Lindau 2005 Fusion Eng Des 75-79)
    molar_mass_kg_mol=0.05585,  # Fe (IUPAC 2021; dominant component)
    oxide_density_kg_m3=5200.0,   # Cr₂O₃ (Young 2008)
    oxide_molar_mass_kg_mol=0.15199,  # Cr₂O₃ (IUPAC 2021)
)

# Mo-Re alloy (radiator panel): oxidises rapidly in O₂ above 400°C (volatile MoO₃)
# Wadsworth & Ruano 1994 Mat Sci Eng A177:L1; Giggins 1969 Trans AIME 245:2509
MO_RE_OXIDATION = OxidationMaterial(
    name="Mo-Re",
    A_p=5.0e-8,             # Giggins 1969; MoO₃ is volatile → linear regime dominates
    Q_p=1.50e5,
    A_linear=4.0e-5,        # Giggins 1969 calibrated to ~1 mg/cm²/hr at 700°C; A = k_l/exp(-Q/RT@973K)
    Q_linear=9.0e4,         # 90 kJ/mol (Giggins 1969)
    density_kg_m3=10200.0,  # Mo-Re (Wadsworth & Ruano 1994)
    molar_mass_kg_mol=0.09596,   # Mo (IUPAC 2021)
    oxide_density_kg_m3=4700.0,  # MoO₃ (solid, below sublimation; Young 2008)
    oxide_molar_mass_kg_mol=0.14394,  # MoO₃ (IUPAC 2021)
)

# Aluminium 6061-T6: protective Al₂O₃ native film; very slow parabolic above 400°C
# Menzies 1979 Corros Sci 19:239
AL_6061_OXIDATION = OxidationMaterial(
    name="Al-6061",
    A_p=2.0e-11,            # Menzies 1979 (Al₂O₃ scale)
    Q_p=1.30e5,             # 130 kJ/mol (Al₂O₃ diffusion; Menzies 1979)
    A_linear=1.0e-12,       # negligible linear term (protective scale)
    Q_linear=1.00e5,
    density_kg_m3=2700.0,   # ASM Handbook vol 2
    molar_mass_kg_mol=0.02698,   # Al (IUPAC 2021)
    oxide_density_kg_m3=3950.0,  # Al₂O₃ corundum (Young 2008)
    oxide_molar_mass_kg_mol=0.10196,  # Al₂O₃ (IUPAC 2021)
)


# ── Kinetic rate constants ────────────────────────────────────────────────────

def parabolic_rate_constant_m2_s(
    material: OxidationMaterial,
    temperature_K: float,
) -> float:
    """Parabolic oxidation rate constant k_p [m²/s] via Arrhenius.

    k_p(T) = A_p × exp(−Q_p / (R × T))

    Args:
        material: OxidationMaterial with A_p, Q_p.
        temperature_K: Temperature [K].

    Returns:
        k_p [m²/s].
    """
    if temperature_K <= 0.0:
        raise ValueError("temperature_K must be > 0")
    return material.A_p * math.exp(-material.Q_p / (R_GAS * temperature_K))


def linear_rate_constant_m_s(
    material: OxidationMaterial,
    temperature_K: float,
) -> float:
    """Linear oxidation rate constant k_l [m/s] via Arrhenius.

    Args:
        material: OxidationMaterial with A_linear, Q_linear.
        temperature_K: Temperature [K].

    Returns:
        k_l [m/s].
    """
    if temperature_K <= 0.0:
        raise ValueError("temperature_K must be > 0")
    return material.A_linear * math.exp(-material.Q_linear / (R_GAS * temperature_K))


# ── Oxide layer thickness ─────────────────────────────────────────────────────

def oxide_thickness_parabolic_m(
    material: OxidationMaterial,
    temperature_K: float,
    time_s: float,
) -> float:
    """Oxide layer thickness via parabolic kinetics [m].

    x(t) = √(k_p × t)

    Args:
        material: Oxidation parameters.
        temperature_K: Temperature [K].
        time_s: Exposure time [s].

    Returns:
        Oxide thickness [m]. Non-negative.
    """
    if time_s <= 0.0:
        return 0.0
    k_p = parabolic_rate_constant_m2_s(material, temperature_K)
    return math.sqrt(k_p * time_s)


def oxide_thickness_linear_m(
    material: OxidationMaterial,
    temperature_K: float,
    time_s: float,
) -> float:
    """Oxide layer thickness via linear kinetics [m].

    x(t) = k_l × t

    Args:
        material: Oxidation parameters.
        temperature_K: Temperature [K].
        time_s: Exposure time [s].

    Returns:
        Oxide thickness [m]. Non-negative.
    """
    if time_s <= 0.0:
        return 0.0
    k_l = linear_rate_constant_m_s(material, temperature_K)
    return k_l * time_s


def oxide_thickness_logarithmic_m(
    k_log: float,
    t_0_s: float,
    time_s: float,
) -> float:
    """Oxide layer thickness via logarithmic kinetics (Cabrera-Mott 1949) [m].

    x(t) = k_log × ln(1 + t / t_0)

    Applicable at room temperature for thin native oxide on Al, Ti.

    Args:
        k_log: Logarithmic rate coefficient [m].
        t_0_s: Time constant [s] (typically ~1 s for rapid initial growth).
        time_s: Exposure time [s].

    Returns:
        Oxide thickness [m].
    """
    if time_s <= 0.0:
        return 0.0
    if t_0_s <= 0.0:
        raise ValueError("t_0_s must be > 0")
    return k_log * math.log1p(time_s / t_0_s)


# ── Mass gain ─────────────────────────────────────────────────────────────────

def pilling_bedworth_ratio(material: OxidationMaterial) -> float:
    """Pilling-Bedworth ratio (PBR): oxide volume / metal volume consumed.

    PBR = (ρ_metal × M_oxide) / (ρ_oxide × M_metal × n)

    where n is the number of metal atoms per formula unit of oxide.
    Approximated here as M_oxide / (2 × M_metal) for typical MₓOᵧ oxides.

    PBR > 1 → compressive stress in oxide → protective (Al₂O₃, Cr₂O₃).
    PBR < 1 → tensile stress → oxide cracks and spalls.

    Reference: Pilling & Bedworth 1923 J Inst Metals 29:529.

    Args:
        material: OxidationMaterial.

    Returns:
        Dimensionless PBR.
    """
    # n ≈ M_oxide / (2 × M_metal): heuristic for common binary oxides
    n = material.oxide_molar_mass_kg_mol / (2.0 * material.molar_mass_kg_mol)
    return (material.density_kg_m3 * material.oxide_molar_mass_kg_mol) / (
        material.oxide_density_kg_m3 * material.molar_mass_kg_mol * n
    )


def mass_gain_kg_m2_parabolic(
    material: OxidationMaterial,
    temperature_K: float,
    time_s: float,
) -> float:
    """Mass gain per unit surface area from parabolic oxidation [kg/m²].

    Δm = ρ_oxide × x_parabolic

    Args:
        material: Oxidation parameters.
        temperature_K: Temperature [K].
        time_s: Exposure time [s].

    Returns:
        Mass gain [kg/m²].
    """
    x = oxide_thickness_parabolic_m(material, temperature_K, time_s)
    return material.oxide_density_kg_m3 * x


# ── Pitting corrosion ─────────────────────────────────────────────────────────

# Al-2024 pitting kinetics in NaCl solution (0.6 M): Godard 1967 Table 4.3
# d_pit = A_pit × t^n_pit; A_pit calibrated to ~0.25 mm/yr (Godard 1967 Table 4.3)
# Back-calc: A_pit = 0.25e-3 m / (3.156e7 s)^(1/3) = 7.9e-7 m/s^(1/3)
AL_PITTING_A: float = 7.9e-7   # Godard 1967 Table 4.3 recalibrated to SI
AL_PITTING_N: float = 1.0 / 3  # Godard 1967 (diffusion-limited; 1/3 exponent)


def pitting_depth_m(
    time_s: float,
    A_pit: float = AL_PITTING_A,
    n_pit: float = AL_PITTING_N,
) -> float:
    """Maximum pit depth for aqueous pitting corrosion [m].

    d_pit(t) = A_pit × t^n_pit

    Reference: Godard 1967 Table 4.3 for Al alloys in NaCl.

    Args:
        time_s: Exposure time [s].
        A_pit: Pitting rate constant [m/s^n_pit].
        n_pit: Time exponent (≈1/3 for diffusion-limited pitting).

    Returns:
        Maximum pit depth [m]. Non-negative.
    """
    if time_s <= 0.0:
        return 0.0
    return A_pit * (time_s ** n_pit)


# ── Atomic oxygen (ATOX) erosion at LEO ───────────────────────────────────────

# ATOX erosion yield for Kapton (baseline polymer) at LEO:
# Brinza 2001 NASA TM-2001-210640; de Groh 2000 NASA/TM-2000-209919
ATOX_O_FLUX_LEO_PER_M2_S: float = 1.0e15  # atoms/m²/s (400 km LEO; Brinza 2001)
ATOX_EROSION_YIELD_KAPTON: float = 3.0e-30  # m³/O-atom (Kapton; de Groh 2000)
ATOX_EROSION_YIELD_AL_OXIDE: float = 0.0    # Al₂O₃ resistant to ATOX (de Groh 2000)


def atox_erosion_depth_m(
    time_s: float,
    erosion_yield_m3_per_O_atom: float = ATOX_EROSION_YIELD_KAPTON,
    o_flux_per_m2_s: float = ATOX_O_FLUX_LEO_PER_M2_S,
) -> float:
    """Surface erosion depth from atomic-oxygen bombardment [m].

    depth(t) = yield × flux × t

    Reference: Brinza 2001 NASA TM-2001-210640; de Groh 2000 NASA/TM-2000-209919.

    Args:
        time_s: Exposure time [s].
        erosion_yield_m3_per_O_atom: Erosion yield [m³ per O atom].
        o_flux_per_m2_s: ATOX flux [O atoms / m² / s].

    Returns:
        Erosion depth [m].
    """
    if time_s <= 0.0:
        return 0.0
    return erosion_yield_m3_per_O_atom * o_flux_per_m2_s * time_s


# ── SCC threshold check ───────────────────────────────────────────────────────

def is_scc_risk(
    stress_intensity_Pa_sqrt_m: float,
    k_iscc_Pa_sqrt_m: float,
) -> bool:
    """True if stress intensity K_I ≥ K_ISCC (stress corrosion cracking threshold).

    K_ISCC is the environment-specific threshold stress intensity below which
    SCC cracks do not propagate (per ASTM E1820).

    Args:
        stress_intensity_Pa_sqrt_m: Applied K_I [Pa·√m].
        k_iscc_Pa_sqrt_m: Material K_ISCC in the given environment [Pa·√m].

    Returns:
        True if SCC propagation is expected.
    """
    return stress_intensity_Pa_sqrt_m >= k_iscc_Pa_sqrt_m
