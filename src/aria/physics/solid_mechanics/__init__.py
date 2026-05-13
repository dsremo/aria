"""Pod F1 + F2 — Elasticity, J2 plasticity, fatigue, and fracture.

Joint P0-8 implementation covering the closed-form primitives from
two pods:

  - **Pod F1** (`docs/pods/F1_fea_plasticity.md`) — elastic constants,
    stress tensor operations, principal stresses, von Mises,
    pressure-vessel closed forms (§5.1-§5.6).

  - **Pod F2** (`docs/pods/F2_fatigue_fracture.md`) — Basquin S-N
    life, mean-stress corrections (Goodman / Gerber / SWT), Miner's
    cumulative damage, Paris law crack growth, stress intensity
    factor K_I, Ti-6Al-4V K_Ic critical-crack length (§5.7-§5.8,
    §5.21).

**P0 scope (this commit):** closed-form analytic primitives only.
The full finite-element solver, rainflow cycle counting, plasticity
return-mapping integrator, and composite lamination theory are
deferred to follow-up commits.

Primary references:
  - Timoshenko & Goodier 1970 *Theory of Elasticity* (ISBN 978-0070858053)
  - Hill 1950 *Mathematical Theory of Plasticity* (ISBN 978-0198503675)
  - Simo & Hughes 1998 *Computational Inelasticity* (ISBN 978-0387975207)
  - Suresh 1998 *Fatigue of Materials* 2nd ed (ISBN 978-0521578479)
  - Anderson 2017 *Fracture Mechanics* 4th ed (ISBN 978-1498728133)
  - Paris & Erdogan 1963 J. Basic Eng. 85 528
  - MMPDS-17 §5.3 (Ti-6Al-4V); Lindau 2005 Fusion Eng Des 75-79 989
    (EUROFER97)
  - Boyer 1994 *ASM Titanium Handbook*

Public API:
    # F1 — elasticity and stress tensor
    lame_constants, shear_modulus, bulk_modulus
    deviatoric_stress, stress_invariants, j2_invariant
    von_mises_equivalent_stress, principal_stresses
    von_mises_yield_check, effective_plastic_strain_increment
    thin_wall_hoop_stress, thin_wall_axial_stress
    StructuralMaterial, MATERIAL_STRUCTURAL_TABLE

    # F2 — fatigue and fracture
    basquin_life, basquin_stress_amplitude
    goodman_equivalent_amplitude, gerber_equivalent_amplitude
    swt_parameter, morrow_life
    miner_cumulative_damage
    stress_intensity_edge_crack, stress_intensity_center_crack
    critical_crack_length, paris_crack_growth_rate
    walker_delta_k_effective, integrate_paris_block
"""

from .elasticity import (
    bulk_modulus,
    lame_constants,
    shear_modulus,
)
from .stress_tensor import (
    deviatoric_stress,
    j2_invariant,
    principal_stresses,
    stress_invariants,
    von_mises_equivalent_stress,
)
from .plasticity import (
    effective_plastic_strain_increment,
    von_mises_yield_check,
)
from .pressure_vessel import (
    thin_wall_axial_stress,
    thin_wall_hoop_stress,
)
from .materials import (
    MATERIAL_STRUCTURAL_TABLE,
    StructuralMaterial,
    get_structural_material,
)
from .sn_curve import (
    basquin_life,
    basquin_stress_amplitude,
    morrow_life,
)
from .mean_stress import (
    gerber_equivalent_amplitude,
    goodman_equivalent_amplitude,
    swt_parameter,
)
from .miner_rule import (
    miner_cumulative_damage,
)
from .fracture import (
    critical_crack_length,
    stress_intensity_center_crack,
    stress_intensity_edge_crack,
)
from .paris_law import (
    integrate_paris_block,
    paris_crack_growth_rate,
    walker_delta_k_effective,
)
from .rainflow import (
    RainflowCycle,
    extract_turning_points,
    rainflow_count,
    rainflow_total_damage,
)
from .strain_life import (
    coffin_manson_plastic_strain,
    manson_hirschberg_life,
    manson_hirschberg_total_strain,
    transition_life_reversals,
)
from .modal_analysis import (
    HullModalBudget,
    ResonanceAmplification,
    beam_axial_frequency_hz,
    beam_flexural_frequency_hz,
    critical_spin_speed_rpm,
    cylindrical_shell_flexural_frequency_hz,
    cylindrical_shell_ring_frequency_hz,
    dynamic_magnification_factor,
    hull_modal_budget,
    plate_natural_frequency_hz,
)
from .creep import (
    EUROFER97,
    INCONEL_718,
    MO_RE,
    TI_6AL_4V,
    CreepMaterial,
    creep_damage_fraction,
    creep_fatigue_damage,
    creep_rate_per_s,
    creep_strain,
    larson_miller_parameter,
    rupture_life_hr,
    stress_relaxation,
)
from .radiation_embrittlement import (
    EMBRITTLEMENT_DB,
    GCR_DISPLACEMENT_XSEC_CM2,
    EmbrittlementBudget,
    EmbrittlementParams,
    dbtt_shift_c,
    current_dbtt_c,
    embrittlement_budget,
    fracture_toughness_after_irradiation,
    gcr_dpa_annual,
    master_curve_k_jc,
    reactor_dpa_annual,
    yield_strength_shift_mpa,
)

__all__ = [
    # Elasticity / stress tensor (F1)
    "lame_constants",
    "shear_modulus",
    "bulk_modulus",
    "deviatoric_stress",
    "stress_invariants",
    "j2_invariant",
    "von_mises_equivalent_stress",
    "principal_stresses",
    "von_mises_yield_check",
    "effective_plastic_strain_increment",
    "thin_wall_hoop_stress",
    "thin_wall_axial_stress",
    # Creep
    "EUROFER97",
    "INCONEL_718",
    "MO_RE",
    "TI_6AL_4V",
    "CreepMaterial",
    "creep_damage_fraction",
    "creep_fatigue_damage",
    "creep_rate_per_s",
    "creep_strain",
    "larson_miller_parameter",
    "rupture_life_hr",
    "stress_relaxation",
    # Materials
    "StructuralMaterial",
    "MATERIAL_STRUCTURAL_TABLE",
    "get_structural_material",
    # Fatigue (F2)
    "basquin_life",
    "basquin_stress_amplitude",
    "morrow_life",
    "goodman_equivalent_amplitude",
    "gerber_equivalent_amplitude",
    "swt_parameter",
    "miner_cumulative_damage",
    # Fracture (F2)
    "stress_intensity_edge_crack",
    "stress_intensity_center_crack",
    "critical_crack_length",
    "paris_crack_growth_rate",
    "walker_delta_k_effective",
    "integrate_paris_block",
    # Rainflow + strain-life (P1-12)
    "RainflowCycle",
    "extract_turning_points",
    "rainflow_count",
    "rainflow_total_damage",
    "coffin_manson_plastic_strain",
    "manson_hirschberg_total_strain",
    "manson_hirschberg_life",
    "transition_life_reversals",
    # Modal analysis (P0-MA)
    "HullModalBudget",
    "ResonanceAmplification",
    "beam_axial_frequency_hz",
    "beam_flexural_frequency_hz",
    "critical_spin_speed_rpm",
    "cylindrical_shell_flexural_frequency_hz",
    "cylindrical_shell_ring_frequency_hz",
    "dynamic_magnification_factor",
    "hull_modal_budget",
    "plate_natural_frequency_hz",
    # Radiation embrittlement (P0-RE)
    "EMBRITTLEMENT_DB",
    "GCR_DISPLACEMENT_XSEC_CM2",
    "EmbrittlementBudget",
    "EmbrittlementParams",
    "dbtt_shift_c",
    "current_dbtt_c",
    "embrittlement_budget",
    "fracture_toughness_after_irradiation",
    "gcr_dpa_annual",
    "master_curve_k_jc",
    "reactor_dpa_annual",
    "yield_strength_shift_mpa",
]
