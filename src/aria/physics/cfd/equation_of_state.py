"""Ideal-gas equation of state for multi-species habitat air (§4.4 of
H1 scope).

The habitat air is treated as an ideal gas throughout because even at
2 % CO₂ enrichment the compressibility factor Z stays within 0.1 % of
unity at ISS pressures (Incropera et al. 2011 *Fundamentals of Heat
and Mass Transfer* 7th ed Appendix A Table A.4). Sources for species
molar masses: NIST periodic table 2021; for the universal gas constant
CODATA 2018 (Tiesinga et al. 2021 Rev Mod Phys 93 025010).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Universal gas constant (CODATA 2018).
R_UNIVERSAL_J_MOL_K: float = 8.314462618

# Species molar masses (NIST periodic table 2021, g/mol).
MOLAR_MASS_G_MOL: dict[str, float] = {
    "N2": 28.0134,  # NIST
    "O2": 31.9988,  # NIST
    "CO2": 44.0095,  # NIST
    "H2O": 18.01528,  # NIST
    "Ar": 39.948,  # NIST
}


@dataclass(frozen=True)
class GasMixture:
    """Mass-fraction based ideal-gas mixture.

    Attributes:
        mass_fractions: {species: y_k} with Σ y_k = 1 (within 1e-6).
        gamma: specific-heat ratio c_p / c_v. Defaults to the dry-air
            value 1.4005 at 293 K (NIST WebBook).
    """

    mass_fractions: dict[str, float]
    gamma: float = 1.4005  # NIST WebBook dry air @ 293 K

    def __post_init__(self) -> None:
        total = sum(self.mass_fractions.values())
        if abs(total - 1.0) > 1.0e-6:
            raise ValueError(f"mass fractions must sum to 1; got {total}")
        for name in self.mass_fractions:
            if name not in MOLAR_MASS_G_MOL:
                raise KeyError(f"unknown species {name!r}; add to MOLAR_MASS_G_MOL")
        if self.gamma <= 1.0:
            raise ValueError("gamma must be > 1")

    @property
    def molar_mass_kg_mol(self) -> float:
        """M_mix = (Σ y_k / M_k)⁻¹                              [kg/mol].

        Eq. 4.4 of the H1 scope note.
        """
        inv = sum(
            y / (MOLAR_MASS_G_MOL[name] * 1.0e-3)
            for name, y in self.mass_fractions.items()
        )
        return 1.0 / inv


# Standard dry-air mixture (NIST WebBook, 293 K, 1 atm).
AIR_STANDARD: GasMixture = GasMixture(
    mass_fractions={
        "N2": 0.7553,  # NIST WebBook dry air
        "O2": 0.2314,  # NIST WebBook dry air
        "Ar": 0.0128,  # NIST WebBook dry air
        "CO2": 0.0005,  # NIST WebBook dry air
    },
    gamma=1.4005,
)


def specific_gas_constant(mixture: GasMixture) -> float:
    """R_specific = R_u / M_mix                               [J/(kg·K)].

    For dry air this should return ≈ 287.05 J/(kg·K) (NIST WebBook).
    """
    return R_UNIVERSAL_J_MOL_K / mixture.molar_mass_kg_mol


def ideal_gas_density(
    pressure_pa: float, temperature_k: float, mixture: GasMixture = AIR_STANDARD
) -> float:
    """ρ = p / (R_specific T)                                  [kg/m³]."""
    if pressure_pa <= 0.0:
        raise ValueError("pressure_pa must be positive")
    if temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive")
    return pressure_pa / (specific_gas_constant(mixture) * temperature_k)


def ideal_gas_pressure(
    density_kg_m3: float, temperature_k: float, mixture: GasMixture = AIR_STANDARD
) -> float:
    """p = ρ R_specific T                                      [Pa]."""
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    if temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive")
    return density_kg_m3 * specific_gas_constant(mixture) * temperature_k


def speed_of_sound(
    temperature_k: float, mixture: GasMixture = AIR_STANDARD
) -> float:
    """c = √(γ R_specific T)                                   [m/s].

    Landau & Lifshitz 1987 *Fluid Mechanics* eq. 64.1. For dry air at
    293.15 K this returns ≈ 343 m/s (standard textbook value).
    """
    if temperature_k <= 0.0:
        raise ValueError("temperature_k must be positive")
    return math.sqrt(mixture.gamma * specific_gas_constant(mixture) * temperature_k)
