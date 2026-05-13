"""Canonical structural material constants (F1 §5 + F2 §5).

Combines the elastic, yield, ultimate, fracture, and fatigue
constants for the materials ARIA's structural pods test against.
Every row cites its primary source.

Sources:
  - MMPDS-17 (2022) — Metallic Materials Properties Development and
    Standardization. Battelle Memorial Institute.
  - Lindau et al. 2005 Fusion Eng Des 75-79 989-996 (EUROFER97).
  - Boyer 1994 *ASM Titanium Handbook* Table F2 (Ti-6Al-4V fatigue
    coefficients).
  - Hudak 1984 Fatigue 84 / ASTM E647 database (Ti-6Al-4V Paris
    law constants, R = 0.1).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StructuralMaterial:
    """Elastic + strength + fatigue + fracture properties (F1 + F2).

    Attributes:
        name: identifier.
        youngs_modulus_pa: E (Pa).
        poissons_ratio: ν (dimensionless).
        density_kg_m3: ρ (kg/m³).
        yield_strength_pa: σ_y (Pa).
        ultimate_strength_pa: σ_UTS (Pa).
        fracture_toughness_pa_sqrt_m: K_Ic (Pa·m^½).
        basquin_sigma_f_prime_pa: σ_f' stress-life coefficient (Pa).
        basquin_b_exponent: b (dimensionless, negative).
        paris_c: Paris-law C in m/cycle / (Pa·m^½)^m (SI units —
            see `paris_law.py` for unit audit). Set to None if
            unknown.
        paris_m: Paris-law m exponent (dimensionless).
        source: free-form citation.
    """

    name: str
    youngs_modulus_pa: float
    poissons_ratio: float
    density_kg_m3: float
    yield_strength_pa: float
    ultimate_strength_pa: float
    fracture_toughness_pa_sqrt_m: float
    basquin_sigma_f_prime_pa: float
    basquin_b_exponent: float
    paris_c: float | None
    paris_m: float | None
    source: str
    # Coffin-Manson strain-life pair (optional). Both must be set
    # for `manson_hirschberg_*` to work.
    coffin_epsilon_f_prime: float | None = None
    coffin_c_exponent: float | None = None


# ──────────────────────────────────────────────────────────────────────
#  Ti-6Al-4V — primary hull / ring alloy
#  MMPDS-17 §5.3 Table 5.3.1 (A-basis, annealed bar, room temperature)
#  Boyer 1994 ASM Titanium Handbook Table F2 (Basquin coefficients)
# ──────────────────────────────────────────────────────────────────────
TI_6AL_4V = StructuralMaterial(
    name="Ti-6Al-4V",
    youngs_modulus_pa=113.8e9,  # MMPDS-17 §5.3
    poissons_ratio=0.342,  # MMPDS-17 §5.3
    density_kg_m3=4430.0,  # MMPDS-17 §5.3
    yield_strength_pa=820e6,  # MMPDS-17 Table 5.3.1 A-basis RT
    ultimate_strength_pa=895e6,  # MMPDS-17 Table 5.3.1 A-basis RT
    fracture_toughness_pa_sqrt_m=55e6,  # MMPDS-17 Table 5.3.1 (range 50-70)
    basquin_sigma_f_prime_pa=2030e6,  # Boyer 1994 Table F2
    basquin_b_exponent=-0.104,  # Boyer 1994 Table F2
    # Paris-law constants for R = 0.1, ASTM E647 database (Hudak 1984
    # Fatigue 84 citation). Units: m/cycle per (MPa·m^½)^m.
    # Convert to SI internally: C_SI = C_eng × (1e6)^(-m) because
    # ΔK_SI [Pa·m^½] = 1e6 · ΔK_eng [MPa·m^½].
    paris_c=1.1e-11,  # (m/cycle)/(MPa·m^½)^m  (ASTM E647)
    paris_m=3.5,  # dimensionless (ASTM E647)
    # Coffin-Manson coefficients from Boyer 1994 Table F2 (annealed
    # bar, axial LCF data, R = -1).
    coffin_epsilon_f_prime=0.841,  # Boyer 1994 Table F2
    coffin_c_exponent=-0.688,  # Boyer 1994 Table F2
    source=(
        "MMPDS-17 §5.3 Table 5.3.1 (elastic + strength); "
        "Boyer 1994 ASM Titanium Handbook Table F2 (Basquin + Coffin-Manson); "
        "Hudak 1984 Fatigue 84 / ASTM E647 (Paris)"
    ),
)


# ──────────────────────────────────────────────────────────────────────
#  EUROFER97 — fusion blanket reduced-activation ferritic-martensitic
#  steel. Lindau 2005 Fusion Eng Des 75-79 989-996.
# ──────────────────────────────────────────────────────────────────────
EUROFER97 = StructuralMaterial(
    name="EUROFER97",
    youngs_modulus_pa=217e9,  # Lindau 2005
    poissons_ratio=0.30,  # Lindau 2005
    density_kg_m3=7798.0,  # Lindau 2005
    yield_strength_pa=550e6,  # Lindau 2005 RT
    ultimate_strength_pa=665e6,  # Lindau 2005 RT
    fracture_toughness_pa_sqrt_m=190e6,  # Lindau 2005 (upper-shelf ~190)
    basquin_sigma_f_prime_pa=1150e6,  # Aubert 2014 J Nucl Mater (estimate)
    basquin_b_exponent=-0.09,  # Aubert 2014
    paris_c=None,  # not included in P0 snapshot
    paris_m=None,
    source="Lindau 2005 Fusion Eng Des 75-79 989-996",
)


# ──────────────────────────────────────────────────────────────────────
#  Al 7075-T6
# ──────────────────────────────────────────────────────────────────────
AL_7075_T6 = StructuralMaterial(
    name="Al 7075-T6",
    youngs_modulus_pa=71.7e9,  # MMPDS-17 §3.7
    poissons_ratio=0.33,  # MMPDS-17 §3.7
    density_kg_m3=2810.0,  # MMPDS-17 §3.7
    yield_strength_pa=503e6,  # MMPDS-17 §3.7
    ultimate_strength_pa=572e6,  # MMPDS-17 §3.7
    fracture_toughness_pa_sqrt_m=29e6,  # MMPDS-17 §3.7 (L-T orientation)
    basquin_sigma_f_prime_pa=886e6,  # Dowling 2007 Table 14.1
    basquin_b_exponent=-0.14,  # Dowling 2007 Table 14.1
    paris_c=2.71e-11,  # ASTM E647 2024-T3 proxy — TODO: verify 7075
    paris_m=3.2,
    source="MMPDS-17 §3.7 + Dowling 2007 Mechanical Behavior of Materials",
)


MATERIAL_STRUCTURAL_TABLE: dict[str, StructuralMaterial] = {
    "Ti-6Al-4V": TI_6AL_4V,
    "EUROFER97": EUROFER97,
    "Al-7075-T6": AL_7075_T6,
}


def get_structural_material(name: str) -> StructuralMaterial:
    """Look up a canonical structural material by name."""
    try:
        return MATERIAL_STRUCTURAL_TABLE[name]
    except KeyError as e:
        raise KeyError(
            f"Unknown structural material {name!r}. "
            f"Known: {sorted(MATERIAL_STRUCTURAL_TABLE.keys())}"
        ) from e
