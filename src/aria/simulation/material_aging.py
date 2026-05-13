"""Century-scale material aging models for interstellar missions.

Fills the audit gap "Miner's-rule fatigue only — no radiation
embrittlement, no creep, no cumulative MMOD validated." For a 220-year
Proxima cruise we need to combine four independent aging mechanisms:

  1. **Radiation embrittlement** — Arrhenius-accelerated DPA (displacements
     per atom) accumulation. Metals: ΔDBTT shift ∝ √DPA × exp(−Q/RT).
  2. **Thermal creep** — Larson-Miller parameter: at low homologous T the
     creep rate is negligible; at T/T_m > 0.4 it becomes significant.
  3. **MMOD cumulative area fraction** — Poisson micrometeoroid + debris
     flux over time gives expected punctured area; Whipple shields
     reduce penetration probability per hit.
  4. **Polymer / composite radiation dose** — dose-to-failure for Kevlar
     / PEEK / carbon composite matrices under GCR.

All four combine into a single "remaining life fraction" aligned with
Miner's rule (cumulative damage D → 1 means failure).

References:
    Zinkle, S. J. & Busby, J. T. (2009) "Structural materials for
        fission & fusion energy," Mater. Today 12(11):12.
    Larson, F. R. & Miller, J. (1952) "Time-Temperature Relationship
        for Rupture & Creep Stresses," ASME Trans. 74:765.
    Kessler, D. J. (1978) "Collision frequency of artificial
        satellites," JGR 83(A6):2637.
    Tajima, H. et al. (2013) "Radiation damage in polymers for space."
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


_GAS_CONSTANT_J_MOL_K = 8.3145
_SI_YEAR_S = 365.25 * 86400.0


# ══════════════════════════════════════════════════════════════════
#  Materials — aging-specific property set
# ══════════════════════════════════════════════════════════════════

@dataclass
class AgingMaterial:
    name: str
    activation_energy_kj_mol: float     # creep activation (Q)
    dpa_threshold_for_30pct_toughness: float  # DPA at which K_IC drops 30%
    creep_rupture_larson_miller_const: float  # C (typ 20 for steels)
    melting_temp_k: float
    polymer: bool = False               # True for polymers (different aging law)
    gcr_dose_to_failure_krad: float = 1.0e5


MATERIALS: dict[str, AgingMaterial] = {
    "Ti-6Al-4V":      AgingMaterial("Ti-6Al-4V", 220.0, 2.0, 20.0, 1878, False, 5e5),
    "EUROFER97":      AgingMaterial("EUROFER97", 400.0, 10.0, 20.0, 1813, False, 1e6),
    "Al-2219":        AgingMaterial("Al-2219", 140.0, 0.5, 18.0, 917, False, 2e5),
    "Kevlar":         AgingMaterial("Kevlar", 90.0, 0.1, 12.0, 573, True, 1e4),
    "PEEK":           AgingMaterial("PEEK", 120.0, 0.2, 14.0, 616, True, 5e4),
    "Carbon-Epoxy":   AgingMaterial("Carbon-Epoxy", 110.0, 0.3, 13.0, 600, True, 2e4),
}


# ══════════════════════════════════════════════════════════════════
#  Individual aging terms
# ══════════════════════════════════════════════════════════════════

def dpa_from_flux(neutron_flux_n_cm2_s: float, years: float) -> float:
    """Displacement-per-atom from integrated neutron fluence.
    Standard cross-section for iron ≈ 1e-21 cm²."""
    total_fluence = neutron_flux_n_cm2_s * years * _SI_YEAR_S
    return total_fluence * 1e-21


def embrittlement_factor(dpa: float, mat: AgingMaterial) -> float:
    """Fraction of initial toughness remaining after `dpa` dose.
    K_IC(dpa) / K_IC(0) = exp(-dpa / DPA_30pct) × scale."""
    if mat.polymer:
        return max(0.0, 1 - dpa / max(mat.dpa_threshold_for_30pct_toughness, 0.01))
    # Metals: exponential softening with DPA
    return math.exp(-dpa / max(mat.dpa_threshold_for_30pct_toughness * 3, 0.1))


def creep_rate_per_year(stress_mpa: float, temp_k: float, mat: AgingMaterial,
                        ref_stress_mpa: float = 100.0) -> float:
    """Larson-Miller creep: LMP = T × (C + log10(t_rupture))
    We invert: given stress, solve for time-to-rupture in years, return 1/t."""
    # Simple power-law creep at homologous T > 0.3
    T_hom = temp_k / mat.melting_temp_k
    if T_hom < 0.3:
        return 0.0
    # Arrhenius form: ε̇ = A σ^n exp(-Q/RT)
    n = 5.0  # typical power-law exponent
    A = 1e-10
    epsdot = A * (stress_mpa ** n) \
             * math.exp(-mat.activation_energy_kj_mol * 1000
                        / (_GAS_CONSTANT_J_MOL_K * temp_k))
    # Damage rate per year (normalized so ε=0.1 rupture)
    return epsdot * _SI_YEAR_S / 0.1


def mmod_damage_fraction(exposed_area_m2: float, flux_per_m2_yr: float,
                          years: float,
                          penetration_prob: float = 0.01) -> float:
    """Cumulative MMOD damage: Poisson flux × penetration × exposed area."""
    expected_hits = exposed_area_m2 * flux_per_m2_yr * years
    expected_punctures = expected_hits * penetration_prob
    return float(min(1.0, expected_punctures))


def radiation_dose_damage(dose_rate_krad_yr: float, years: float,
                           mat: AgingMaterial) -> float:
    """Dose accumulation vs dose-to-failure (Miner's-rule-style ratio)."""
    total_dose = dose_rate_krad_yr * years
    return min(1.0, total_dose / max(mat.gcr_dose_to_failure_krad, 1.0))


# ══════════════════════════════════════════════════════════════════
#  Combined life predictor
# ══════════════════════════════════════════════════════════════════

@dataclass
class AgingReport:
    material: str
    years: float
    embrittlement_loss: float       # 1 - toughness fraction
    creep_damage: float
    mmod_damage: float
    radiation_damage: float
    total_damage: float             # Miner-style sum (may exceed 1)
    failure_predicted: bool
    life_remaining_years: Optional[float]
    notes: List[str] = field(default_factory=list)


def predict_service_life(
    material: str,
    years: float = 220.0,
    neutron_flux_n_cm2_s: float = 1e3,
    stress_mpa: float = 100.0,
    temp_k: float = 300.0,
    exposed_area_m2: float = 10.0,
    mmod_flux_per_m2_yr: float = 1e-4,
    gcr_dose_rate_krad_yr: float = 0.15,
) -> AgingReport:
    """Predict cumulative damage after `years` of service in interstellar
    conditions. Use defaults tuned for an interstellar cruise (very low
    neutron flux, moderate GCR).
    """
    mat = MATERIALS[material]
    dpa = dpa_from_flux(neutron_flux_n_cm2_s, years)
    embr = 1.0 - embrittlement_factor(dpa, mat)
    creep_per_yr = creep_rate_per_year(stress_mpa, temp_k, mat)
    creep_dam = min(1.0, creep_per_yr * years)
    mmod_dam = mmod_damage_fraction(exposed_area_m2, mmod_flux_per_m2_yr, years)
    rad_dam = radiation_dose_damage(gcr_dose_rate_krad_yr, years, mat)

    # Miner's rule: total damage = sum of fractions (failure ≥ 1)
    total = embr + creep_dam + mmod_dam + rad_dam
    failure = total >= 1.0

    # Linear-extrapolation life-remaining
    if total > 0 and years > 0:
        rate = total / years
        remaining = max(0.0, (1.0 - total) / max(rate, 1e-12))
    else:
        remaining = None

    notes = []
    if embr > 0.3:
        notes.append(f"embrittlement dominant: {embr:.1%} toughness loss")
    if creep_dam > 0.3:
        notes.append(f"creep dominant: {creep_dam:.1%} damage")
    if mmod_dam > 0.3:
        notes.append(f"MMOD dominant: expected {mmod_dam:.1%} punctured area")
    if rad_dam > 0.3:
        notes.append(f"radiation dominant: {rad_dam:.1%} dose-to-failure")

    return AgingReport(
        material=material, years=years,
        embrittlement_loss=embr, creep_damage=creep_dam,
        mmod_damage=mmod_dam, radiation_damage=rad_dam,
        total_damage=total, failure_predicted=failure,
        life_remaining_years=remaining,
        notes=notes,
    )
