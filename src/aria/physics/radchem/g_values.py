"""Water radiolysis G-values (§4.1, §4.2 of J2 scope).

A G-value is the number of product molecules formed per 100 eV of
absorbed energy (Spinks & Woods 1990 *An Introduction to Radiation
Chemistry* 3rd ed §2). The molar production rate under a dose rate
Ḋ (Gy/s) in a medium of density ρ is

    r_X = G(X)[molec/100 eV] · Ḋ · ρ · 1.0364×10⁻⁷ / N_A      [mol/(m³·s)]

The prefactor 1.0364×10⁻⁷ converts (molec/100 eV)·(J) to molecules.
Specifically: 100 eV = 1.602×10⁻¹⁷ J, so 1 J / 100 eV = 6.2415×10¹⁶
molecules at G=1; divided by Avogadro gives the mol conversion.

LET dependence (Pastina & LaVerne 2001 *J Phys Chem A* 105 9316):
G(H₂) rises and G(•OH) falls with increasing linear energy transfer
(LET). For 5 MeV protons LET ≈ 8 keV/µm and G(H₂) ≈ 1.0; at
⁶⁰Co γ LET ≈ 0.3 keV/µm and G(H₂) ≈ 0.45. We model G(H₂) with a
piecewise-linear interpolation on the Pastina–LaVerne Fig 4 anchor
points.
"""

from __future__ import annotations

import math

# CODATA 2018 / SI 2019.
N_A: float = 6.02214076e23  # mol⁻¹
ELEMENTARY_CHARGE_J_PER_EV: float = 1.602176634e-19

# 100 eV → J
_HUNDRED_EV_IN_JOULES: float = 100.0 * ELEMENTARY_CHARGE_J_PER_EV


# Low-LET water primary G-values (molecules per 100 eV) for ⁶⁰Co γ at
# 298 K, escape yields at ~1 µs. Values from Spinks & Woods 1990 ch. 7
# and Elliot & Bartels 2009 AECL-153-127160-450-001 Table 1.
G_VALUE_LOW_LET_WATER: dict[str, float] = {
    "e_aq": 2.63,  # Spinks & Woods 1990
    "OH": 2.72,  # Spinks & Woods 1990
    "H": 0.60,  # Spinks & Woods 1990
    "H2": 0.45,  # Spinks & Woods 1990
    "H2O2": 0.68,  # Elliot & Bartels 2009
    "H_plus": 2.76,  # Spinks & Woods 1990
}


def molar_production_rate(
    g_molec_per_100_ev: float,
    dose_rate_gy_s: float,
    density_kg_m3: float,
) -> float:
    """Volumetric molar production rate [mol/(m³·s)] from (G, Ḋ, ρ).

    r_X = G · Ḋ · ρ / (100 eV · N_A)                          [mol/(m³·s)]

    Units derivation:
        [G]       = molec / (100 eV)
        [Ḋ · ρ]   = (J/kg/s) · (kg/m³) = J/(m³·s)
        [G/100 eV · (Ḋ ρ)] = molec / (m³·s)
        divided by N_A → mol/(m³·s)
    """
    if g_molec_per_100_ev < 0.0:
        raise ValueError("g_molec_per_100_ev must be non-negative")
    if dose_rate_gy_s < 0.0:
        raise ValueError("dose_rate_gy_s must be non-negative")
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    return (
        g_molec_per_100_ev
        * dose_rate_gy_s
        * density_kg_m3
        / (_HUNDRED_EV_IN_JOULES * N_A)
    )


def species_molar_production_rate(
    species: str,
    dose_rate_gy_s: float,
    density_kg_m3: float,
    g_table: dict[str, float] = G_VALUE_LOW_LET_WATER,
) -> float:
    """Convenience wrapper that looks up G(species) from a table."""
    if species not in g_table:
        raise KeyError(f"Unknown species {species!r}. Known: {sorted(g_table)}")
    return molar_production_rate(
        g_molec_per_100_ev=g_table[species],
        dose_rate_gy_s=dose_rate_gy_s,
        density_kg_m3=density_kg_m3,
    )


# Pastina & LaVerne 2001 Fig 4 anchor points for G(H₂) vs LET.
# LET in keV/µm, G in molec/100 eV.
_PASTINA_LAVERNE_LET_ANCHORS: list[tuple[float, float]] = [
    (0.3, 0.45),  # Spinks & Woods ⁶⁰Co γ
    (8.0, 1.00),  # Pastina & LaVerne 5 MeV protons
    (100.0, 1.55),  # Pastina & LaVerne high-LET plateau
]


def g_value_hydrogen_let(let_kev_um: float) -> float:
    """Piecewise-linear G(H₂) as a function of LET (keV/µm).

    Anchor points from Pastina & LaVerne 2001 Fig 4:
        LET ≈ 0.3 keV/µm (⁶⁰Co γ)         → G(H₂) ≈ 0.45
        LET ≈ 8   keV/µm (5 MeV protons)  → G(H₂) ≈ 1.00
        LET ≈ 100 keV/µm (HZE plateau)    → G(H₂) ≈ 1.55

    Below the lowest LET we clamp to the low-LET value; above the
    highest LET we clamp to the plateau.
    """
    if let_kev_um < 0.0:
        raise ValueError("let_kev_um must be non-negative")
    anchors = _PASTINA_LAVERNE_LET_ANCHORS
    if let_kev_um <= anchors[0][0]:
        return anchors[0][1]
    if let_kev_um >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= let_kev_um <= x1:
            # Linear interpolation in log-LET / linear-G.
            t = (math.log(let_kev_um) - math.log(x0)) / (math.log(x1) - math.log(x0))
            return y0 + t * (y1 - y0)
    return anchors[-1][1]
