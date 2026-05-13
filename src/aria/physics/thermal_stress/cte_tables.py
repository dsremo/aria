"""Temperature-dependent CTE and elastic constants for common
materials (§5 of docs/pods/F5_thermal_stress.md).

Every entry carries an inline published citation per CLAUDE.md. The
values collected here are the ones that the F5 test cases and the
ARIA mission critical-path structural pieces need:

- **Ti-6Al-4V**: primary hull / first wall alloy, two CTE segments
  (20–200 °C and 200–600 °C) from MMPDS-17 §5.3 Table 5.3.0.3.
- **EUROFER97**: fusion blanket structural steel, Lindau 2005.
- **Al 7075-T6**: lightweight structures, MMPDS-17 §3.7.
- **IM7/8552 (carbon/epoxy)**: orthotropic composite for non-
  pressure-vessel parts, NCAMP NPS 81220.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class MaterialThermalProperties:
    """Isotropic thermal/elastic properties used by F5 solvers.

    Attributes:
        name: identifier.
        cte_k_inv: linear coefficient of thermal expansion (1/K).
        youngs_modulus_pa: Young's modulus E (Pa).
        poissons_ratio: ν (dimensionless).
        yield_strength_pa: σ_y for plasticity margin checks (Pa).
            Set to None if the solver should not compute a margin.
        ultimate_strength_pa: σ_UTS for fracture margin (Pa).
        source: free-form citation string; every instance has one.
    """

    name: str
    cte_k_inv: float
    youngs_modulus_pa: float
    poissons_ratio: float
    source: str
    yield_strength_pa: float | None = None
    ultimate_strength_pa: float | None = None


@dataclass(frozen=True)
class AnisotropicThermalProperties:
    """Orthotropic laminate properties for composites.

    Attributes:
        name: identifier.
        cte_11_k_inv: fiber-direction CTE (1/K).
        cte_22_k_inv: transverse CTE (1/K).
        e_11_pa: fiber-direction Young's modulus (Pa).
        e_22_pa: transverse modulus (Pa).
        source: citation.
    """

    name: str
    cte_11_k_inv: float
    cte_22_k_inv: float
    e_11_pa: float
    e_22_pa: float
    source: str


# ──────────────────────────────────────────────────────────────────────
#  Canonical isotropic materials
# ──────────────────────────────────────────────────────────────────────

# Ti-6Al-4V — primary titanium alloy for hull, ring, propellant tanks.
# Ultimate strength 895 MPa, yield 828 MPa from MMPDS-17 §5.3.0.3
# (typical annealed bar, L direction, room temperature).
# CTE 8.6e-6 /K valid 20-200 °C per MMPDS-17 Table 5.3.0.3.
TI_6AL_4V_LOW_TEMP = MaterialThermalProperties(
    name="Ti-6Al-4V (20-200°C)",
    cte_k_inv=8.6e-6,  # MMPDS-17 §5.3 Table 5.3.0.3
    youngs_modulus_pa=113.8e9,  # MMPDS-17 §5.3 (293 K)
    poissons_ratio=0.342,  # MMPDS-17 §5.3
    yield_strength_pa=828e6,  # MMPDS-17 §5.3.0.3 (annealed bar, L)
    ultimate_strength_pa=895e6,  # MMPDS-17 §5.3.0.3
    source="MMPDS-17 §5.3 Table 5.3.0.3 (Ti-6Al-4V annealed bar, L)",
)

# Ti-6Al-4V at 200-600 °C.
TI_6AL_4V_HIGH_TEMP = MaterialThermalProperties(
    name="Ti-6Al-4V (200-600°C)",
    cte_k_inv=9.7e-6,  # MMPDS-17 Table 5.3.0.3 elevated-T segment
    youngs_modulus_pa=91e9,  # MMPDS-17 at 773 K
    poissons_ratio=0.342,
    yield_strength_pa=620e6,  # MMPDS-17 elevated-T bar (approximate)
    ultimate_strength_pa=730e6,  # MMPDS-17 elevated-T bar
    source="MMPDS-17 §5.3 Table 5.3.0.3 (Ti-6Al-4V, elevated T segment)",
)

# EUROFER97 — fusion blanket reduced-activation ferritic-martensitic
# steel. Values from Lindau et al. 2005 Fusion Eng Des 75-79 989-996.
EUROFER97 = MaterialThermalProperties(
    name="EUROFER97",
    cte_k_inv=10.6e-6,  # Lindau 2005 (293 K)
    youngs_modulus_pa=217e9,  # Lindau 2005
    poissons_ratio=0.30,  # Lindau 2005
    yield_strength_pa=550e6,  # Lindau 2005 RT YS
    ultimate_strength_pa=660e6,  # Lindau 2005 RT UTS
    source="Lindau 2005 Fusion Eng Des 75-79 989-996",
)

# Al 7075-T6 — lightweight structural aluminum.
# CTE 23.4e-6 /K (20-100 °C), E 71.7 GPa, ν 0.33 per MMPDS-17 §3.7
# (Table 3.7.4.0(b)).
AL_7075_T6 = MaterialThermalProperties(
    name="Al 7075-T6",
    cte_k_inv=23.4e-6,  # MMPDS-17 §3.7
    youngs_modulus_pa=71.7e9,  # MMPDS-17 §3.7
    poissons_ratio=0.33,  # MMPDS-17 §3.7
    yield_strength_pa=503e6,  # MMPDS-17 §3.7 typical
    ultimate_strength_pa=572e6,  # MMPDS-17 §3.7 typical
    source="MMPDS-17 §3.7 Al 7075-T6 bar",
)


MATERIAL_CTE_TABLE: dict[str, MaterialThermalProperties] = {
    "Ti-6Al-4V": TI_6AL_4V_LOW_TEMP,  # default = 20-200 °C segment
    "Ti-6Al-4V-low-temp": TI_6AL_4V_LOW_TEMP,
    "Ti-6Al-4V-high-temp": TI_6AL_4V_HIGH_TEMP,
    "EUROFER97": EUROFER97,
    "Al-7075-T6": AL_7075_T6,
}


# ──────────────────────────────────────────────────────────────────────
#  Canonical orthotropic composite
# ──────────────────────────────────────────────────────────────────────

# IM7/8552 carbon/epoxy — standard aerospace composite. Negative
# fiber-direction CTE is a characteristic signature of carbon fiber
# composites and is a necessary ingredient for CTE-matched joints.
IM7_8552 = AnisotropicThermalProperties(
    name="IM7/8552",
    cte_11_k_inv=-0.5e-6,  # NCAMP NPS 81220 fiber direction
    cte_22_k_inv=28.0e-6,  # NCAMP NPS 81220 transverse
    e_11_pa=161e9,  # NCAMP NPS 81220
    e_22_pa=11.4e9,  # NCAMP NPS 81220
    source=(
        "NCAMP NPS 81220 IM7/8552 laminate qualification; "
        "Hexcel HexPly 8552 product datasheet (2016)"
    ),
)


# ──────────────────────────────────────────────────────────────────────
#  Lookup helper
# ──────────────────────────────────────────────────────────────────────


def get_material_properties(name: str) -> MaterialThermalProperties:
    """Return the :class:`MaterialThermalProperties` entry for ``name``.

    Raises:
        KeyError: if ``name`` is not in ``MATERIAL_CTE_TABLE``.
    """
    try:
        return MATERIAL_CTE_TABLE[name]
    except KeyError as e:
        raise KeyError(
            f"Unknown material {name!r}. "
            f"Known: {sorted(MATERIAL_CTE_TABLE.keys())}"
        ) from e
