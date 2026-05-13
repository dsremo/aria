"""Pod F5 — Thermal expansion and thermal-stress coupling.

Implements audit items §5.14 (thermal expansion α·ΔT) and §5.15
(thermal stress from constrained expansion). Converts temperature
fields from the thermal pod (G1) into thermal strains and diagnostic
thermal stresses that the structural pod (F1) consumes as eigenstrains.

See `docs/pods/F5_thermal_stress.md` for the scope note (derivations,
citations, verification test cases). Primary references:

- Boley & Weiner 1960 *Theory of Thermal Stresses* (Dover reprint
  ISBN 978-0486695792)
- Timoshenko & Goodier 1970 *Theory of Elasticity* 3rd ed
  (ISBN 978-0070858053)
- Timoshenko 1925 *J. Opt. Soc. Am.* 11 233 (bimetallic strip)
- Kingery 1955 *J. Am. Ceram. Soc.* 38 3 (thermal shock FoM)
- MMPDS-17 (2022) — Ti-6Al-4V / Al 7075-T6 constants
- Lindau 2005 *Fusion Eng Des* 75-79 989 — EUROFER97

Public API:
    MATERIAL_CTE_TABLE            — canonical (α, E, ν) dataset
    linear_thermal_strain         — isotropic ε^θ = α ΔT
    thermal_strain_tensor         — 3×3 ε^θ_ij for isotropic material
    thermal_strain_anisotropic    — α_ij · ΔT for composites
    uniaxial_constrained_stress   — σ = −E α ΔT  (1D bar)
    plane_stress_constrained      — σ = −E α ΔT / (1−ν)
    triaxial_constrained_stress   — σ = −E α ΔT / (1−2ν)
    linear_gradient_peak_stress   — ±E α ΔT / (2(1−ν)) (Boley-Weiner)
    bimetallic_curvature          — Timoshenko 1925 κ(α, E, h, ΔT)
    thermal_shock_delta_t_crit    — Kingery 1955 σ_f(1−ν)/(E α)
    thermal_shock_margin          — ΔT_crit / ΔT_applied
"""

from .cte_tables import (
    MATERIAL_CTE_TABLE,
    MaterialThermalProperties,
    get_material_properties,
)
from .thermal_strain import (
    linear_thermal_strain,
    thermal_strain_anisotropic,
    thermal_strain_tensor,
)
from .constrained_stress import (
    plane_stress_constrained,
    triaxial_constrained_stress,
    uniaxial_constrained_stress,
)
from .gradient_stress import (
    linear_gradient_peak_stress,
    linear_gradient_stress_profile,
)
from .bimetallic import bimetallic_curvature
from .thermal_shock import (
    thermal_shock_delta_t_crit,
    thermal_shock_margin,
)

__all__ = [
    # Tables / metadata
    "MATERIAL_CTE_TABLE",
    "MaterialThermalProperties",
    "get_material_properties",
    # Strains
    "linear_thermal_strain",
    "thermal_strain_tensor",
    "thermal_strain_anisotropic",
    # Constrained stresses
    "uniaxial_constrained_stress",
    "plane_stress_constrained",
    "triaxial_constrained_stress",
    # Gradient stresses
    "linear_gradient_peak_stress",
    "linear_gradient_stress_profile",
    # Bimetallic
    "bimetallic_curvature",
    # Shock
    "thermal_shock_delta_t_crit",
    "thermal_shock_margin",
]
