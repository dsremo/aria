"""Dose fractionation and repair kinetics model.

BUILD-F3 (Villani) + F11 (Costes critique v2):
"Space radiation is CHRONIC, not acute. Cellular repair happens between
radiation events. Your LNT model treats 100 mGy over 6 months the same
as 100 mGy in 1 second."

The Lea-Catcheside dose-rate effectiveness factor G(t):

    G = (2/D²) × ∫∫ D'(t₁) × D'(t₂) × exp(-λ|t₁-t₂|) dt₁ dt₂

For constant dose rate D' over time T:
    G = 2/(λT) × [1 - (1-exp(-λT))/(λT)]

where λ is the repair rate:
- DNA DSB repair: λ ≈ 0.5/hour (t₁/₂ ≈ 1.4 hours)
- Protein oxidation repair (proteasome): λ ≈ 2.0/hour (t₁/₂ ≈ 0.35 hours)
- Protein refolding (chaperone): λ ≈ 0.1/hour (t₁/₂ ≈ 7 hours)

The effective dose is D_eff = D × √G for linear-quadratic damage.
For chronic space radiation (months), G ≈ 2λ/D'_rate, giving D_eff << D_acute.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger()


class RepairEndpoint(Enum):
    """Biological repair endpoint with associated repair rate."""

    DNA_DSB = ("DNA double-strand break", 0.5)           # Cucinotta 2006 Lancet Oncol 7 431: DSB t½≈1.4 h → λ=0.5/h
    PROTEIN_OXIDATION = ("Protein sidechain oxidation", 2.0)   # ESTIMATE — proteasomal clearance t½≈0.35 h (Davies 2016 Biochem J 473 805)
    PROTEIN_REFOLDING = ("Protein refolding via chaperones", 0.1)  # ESTIMATE — chaperone refolding t½≈7 h (Tyedmers 2010 Nat Rev 11 777)
    PROTEIN_REPLACEMENT = ("Protein replacement via proteasome", 0.05)  # ESTIMATE — turnover t½≈14 h (Schwanhäusser 2011 Nature 473 337)

    def __init__(self, description: str, repair_rate: float) -> None:
        self.description = description
        self.repair_rate = repair_rate  # λ in per hour


@dataclass(frozen=True)
class FractionationResult:
    """Result of dose fractionation analysis."""

    dose_mgy: float  # total physical dose
    dose_rate_mgy_per_day: float
    exposure_hours: float
    g_factor: float  # Lea-Catcheside G ∈ (0, 1]
    effective_dose_mgy: float  # D × √G (for LQ model)
    repair_endpoint: str
    repair_rate_per_hour: float
    dose_reduction_factor: float  # effective/physical
    interpretation: str


def lea_catcheside_g(
    dose_rate_mgy_per_hour: float,  # noqa: ARG001
    exposure_hours: float,
    repair_rate_per_hour: float,
) -> float:
    """Compute the Lea-Catcheside dose-rate effectiveness factor G.

    For constant dose rate D' over time T with repair rate λ:

        G = (2/(λT)) × [1 - (1 - exp(-λT))/(λT)]

    G ranges from:
    - G → 1 for acute exposure (T → 0, all damage before any repair)
    - G → 0 for chronic exposure (T → ∞, repair keeps up with damage)

    The effective dose for the linear-quadratic model is:
        D_eff = α×D + β×G×D²  (α dominates at low dose, β×G at high dose)

    For our purposes (protein damage, linear model):
        P(damage) = 1 - exp(-α × D × √G × RBE)

    Args:
        dose_rate_mgy_per_hour: Constant dose rate (mGy/hour).
        exposure_hours: Total exposure duration (hours).
        repair_rate_per_hour: Biological repair rate λ (per hour).

    Returns:
        G factor ∈ (0, 1]. G=1 means acute (no repair), G→0 means fully repaired.
    """
    lam = repair_rate_per_hour
    t_exp = exposure_hours  # noqa: N806

    if t_exp <= 0 or lam <= 0:
        return 1.0  # acute: no time for repair

    lamT = lam * t_exp  # noqa: N806

    if lamT < 1e-6:
        # Very short exposure relative to repair → acute
        return 1.0

    if lamT > 100:
        # Very chronic → G ≈ 2/(λT) (asymptotic)
        return 2.0 / lamT

    # Full formula
    g = (2.0 / lamT) * (1.0 - (1.0 - math.exp(-lamT)) / lamT)

    return max(min(g, 1.0), 0.0)


def compute_fractionation(
    dose_mgy: float,
    dose_rate_mgy_per_day: float,
    duration_days: float | None = None,
    endpoint: RepairEndpoint = RepairEndpoint.PROTEIN_OXIDATION,
) -> FractionationResult:
    """Compute dose fractionation effect for a given exposure scenario.

    For chronic space radiation, the effective dose is much lower than
    the physical dose because biological repair mechanisms continuously
    fix damage between radiation events.

    Example:
        ISS 6 months: 90 mGy physical, but with protein oxidation repair
        (λ=2/hr), G ≈ 0.00046, D_eff = 90 × √0.00046 ≈ 1.9 mGy effective.
        This is a 47× reduction!
    """
    # Convert to hours
    dose_rate_per_hour = dose_rate_mgy_per_day / 24.0

    if duration_days is not None:
        exposure_hours = duration_days * 24.0
    else:
        # Compute from dose and rate
        exposure_hours = dose_mgy / dose_rate_per_hour if dose_rate_per_hour > 0 else 0

    g = lea_catcheside_g(dose_rate_per_hour, exposure_hours, endpoint.repair_rate)

    # Effective dose (√G scaling for linear-quadratic model)
    effective_dose = dose_mgy * math.sqrt(g)
    reduction = effective_dose / dose_mgy if dose_mgy > 0 else 1.0

    # Interpretation
    if g > 0.9:
        interp = (
            f"Near-acute exposure (G={g:.3f}). Repair cannot keep up with damage rate. "
            f"Effective dose ≈ physical dose."
        )
    elif g > 0.1:
        interp = (
            f"Moderate fractionation (G={g:.3f}). Partial repair between radiation events. "
            f"Effective dose = {effective_dose:.1f} mGy ({reduction:.0%} of physical)."
        )
    else:
        interp = (
            f"Strong fractionation (G={g:.4f}). Chronic exposure with significant repair. "
            f"Effective dose = {effective_dose:.2f} mGy ({reduction:.1%} of physical {dose_mgy:.0f} mGy). "
            f"Repair endpoint: {endpoint.description} (λ={endpoint.repair_rate}/hr, "
            f"t½={0.693/endpoint.repair_rate:.1f} hr)."
        )

    return FractionationResult(
        dose_mgy=dose_mgy,
        dose_rate_mgy_per_day=dose_rate_mgy_per_day,
        exposure_hours=exposure_hours,
        g_factor=g,
        effective_dose_mgy=effective_dose,
        repair_endpoint=endpoint.description,
        repair_rate_per_hour=endpoint.repair_rate,
        dose_reduction_factor=reduction,
        interpretation=interp,
    )


def poisson_radiation_hits(
    dose_mgy: float,
    protein_volume_nm3: float = 50.0,  # ESTIMATE — ~50 nm³ typical globular protein (Erickson 2009 Biol Proced Online 11 32)
    cell_volume_um3: float = 4000.0,   # ESTIMATE — ~4000 μm³ mammalian cell (Lemmon 1989 J Cell Biol 109 2283)
) -> dict[str, float]:
    """Compute Poisson statistics of radiation hits per protein molecule.

    BUILD-F3 (Villani): "At low doses, the NUMBER of radiation hits per
    protein follows Poisson(λ). Most proteins receive ZERO hits. The few
    that ARE hit receive clustered damage."

    λ = α × D × V_protein / V_cell

    where α is the macroscopic damage cross-section.

    Args:
        dose_mgy: Total dose in milliGray.
        protein_volume_nm3: Volume of the target protein (~50 nm³ typical).
        cell_volume_um3: Volume of the cell (~4000 μm³ for mammalian cell).

    Returns:
        Dict with Poisson statistics.
    """
    # Convert volumes to same units (nm³)
    cell_volume_nm3 = cell_volume_um3 * 1e9  # μm³ → nm³

    # Volume fraction of this protein in the cell
    volume_fraction = protein_volume_nm3 / cell_volume_nm3

    # Energy deposited per mGy per cell volume
    # 1 Gy = 1 J/kg, cell mass ≈ cell_volume × 1000 kg/m³ (water density)
    cell_mass_kg = cell_volume_um3 * 1e-18 * 1000  # μm³ → m³ → kg
    energy_per_mgy_j = dose_mgy * 1e-3 * cell_mass_kg  # mGy → Gy → J

    # Energy per ionization event ≈ 33 eV (W-value for water)
    w_value_ev = 33.0  # ICRU Report 31 (1979): W-value for water = 33.97 eV; 33 eV commonly used
    w_value_j = w_value_ev * 1.602e-19

    # Total ionization events in cell
    n_ionizations = energy_per_mgy_j / w_value_j

    # Ionization events hitting this protein (by volume fraction)
    lambda_hits = n_ionizations * volume_fraction

    # Poisson statistics
    p_zero_hits = math.exp(-lambda_hits) if lambda_hits < 700 else 0.0
    p_one_hit = lambda_hits * p_zero_hits
    p_two_plus = 1.0 - p_zero_hits - p_one_hit

    return {
        "lambda_mean_hits": lambda_hits,
        "p_zero_hits": p_zero_hits,
        "p_one_hit": p_one_hit,
        "p_two_plus_hits": p_two_plus,
        "expected_damaged_fraction": 1.0 - p_zero_hits,
        "dose_mgy": dose_mgy,
        "protein_volume_nm3": protein_volume_nm3,
    }
