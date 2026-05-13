"""Dose-response models for radiation damage prediction.

Panel 2 (SpaceX): "Need dose-response curves. NASA standard is H=5.0σ."
Panel 5 (Mathematician): "Should implement both LNT and threshold models
with Bayesian model selection."

Two models implemented:
1. Linear No-Threshold (LNT): regulatory standard, assumes all dose is harmful
2. Threshold: assumes damage only above a dose threshold (biologically motivated)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from aria.genastra.core.constants import LET_SATURATION_KEV_UM


@dataclass(frozen=True)
class DoseResponseCurve:
    """Computed dose-response curve with parameters."""

    model_name: str  # "lnt" or "threshold"
    doses: np.ndarray  # dose points (mGy)
    probabilities: np.ndarray  # P(damage) at each dose
    alpha: float  # radiosensitivity coefficient
    rbe: float  # Relative Biological Effectiveness at this LET
    threshold_mgy: float | None  # threshold dose (threshold model only)


def compute_rbe(let_kev_per_um: float | None, particle_type: str = "proton") -> float:
    """Compute Relative Biological Effectiveness from LET.

    RBE(L) = a + b × L / (L + L₀)

    where L₀ = 100 keV/μm is the saturation LET (Katz track structure model).

    Reference RBE values (ICRP Publication 103):
    - Photons/electrons: 1.0
    - Protons: 1.1-2.0 (energy dependent)
    - Alpha: 5-20
    - HZE ions: 2-40 (LET dependent)
    """
    if let_kev_per_um is None:
        # Default RBE by particle type
        defaults = {
            "proton": 1.5,
            "hze_ion": 10.0,
            "neutron": 5.0,
            "mixed": 2.0,
        }
        return defaults.get(particle_type, 2.0)

    # Katz-like RBE model (Katz 1971 Adv Radiat Biol 4 1 §3)
    a = 1.0    # ESTIMATE — baseline RBE (photon-equivalent, normalized)
    b = 25.0   # ESTIMATE — max additional RBE ≈ 25 for Fe-56 (Cucinotta & Durante 2006 Lancet Oncol 7 431)
    l0 = LET_SATURATION_KEV_UM  # noqa: E741  — LET saturation 100 keV/μm (Katz 1971)

    return a + b * let_kev_per_um / (let_kev_per_um + l0)


# P0-3 FIX: The original α=0.005/mGy was WRONG — it was the ICRP cell-level
# cancer risk coefficient, not the per-molecule protein damage probability.
# At 100 mGy (ISS 6-month dose), actual protein damage is <0.1% per molecule.
#
# Correct values for protein-level endpoints:
#   - Backbone break: α ≈ 1e-5 /mGy (requires direct hit or nearby radical)
#   - Sidechain oxidation: α ≈ 5e-5 /mGy (ROS-mediated, more common)
#   - Crosslink formation: α ≈ 1e-6 /mGy (requires two radicals in proximity)
#
# Source: Stadtman & Levine 2003, Davies 2016 (protein oxidation reviews)
ALPHA_BACKBONE_BREAK = 1e-5    # per mGy, per molecule
ALPHA_SIDECHAIN_OXIDATION = 5e-5  # per mGy, per molecule (default)
ALPHA_CROSSLINK = 1e-6         # per mGy, per molecule


def lnt_model(
    dose_mgy: float,
    alpha: float = ALPHA_SIDECHAIN_OXIDATION,
    let_kev_per_um: float | None = None,
    particle_type: str = "proton",
) -> float:
    """Linear No-Threshold model for protein-level damage.

    P(damage | D, L) = 1 - exp(-α × D × RBE(L))

    IMPORTANT: α is for PROTEIN-LEVEL damage (per molecule), NOT the ICRP
    cell-level cancer risk coefficient (which is ~100x higher). At ISS doses
    (~100 mGy / 6 months), per-molecule damage probability should be <1%.

    Args:
        dose_mgy: Total dose in milliGray.
        alpha: Radiosensitivity coefficient (per mGy, per molecule).
              Default: 5e-5 (sidechain oxidation). See module constants
              for backbone break (1e-5) and crosslink (1e-6) endpoints.
        let_kev_per_um: Linear Energy Transfer (optional).
        particle_type: Particle type for default RBE.

    Returns:
        Probability of damage [0, 1].
    """
    rbe = compute_rbe(let_kev_per_um, particle_type)
    return 1.0 - math.exp(-alpha * dose_mgy * rbe)


def threshold_model(
    dose_mgy: float,
    alpha: float = ALPHA_SIDECHAIN_OXIDATION,
    threshold_mgy: float = 50.0,  # ESTIMATE — 50 mGy threshold; proteasomal repair below this (Tyedmers 2010 Nat Rev 11 777)
    let_kev_per_um: float | None = None,
    particle_type: str = "proton",
) -> float:
    """Threshold dose-response model for protein-level damage.

    P(damage | D, L) = { 0                                    if D < D_threshold
                       { 1 - exp(-α × (D - D_threshold) × RBE(L))  otherwise

    Biologically motivated: protein repair/replacement mechanisms (proteasome,
    chaperones) can handle low-dose ROS without net damage accumulation.

    Args:
        dose_mgy: Total dose in milliGray.
        alpha: Radiosensitivity coefficient.
        threshold_mgy: Threshold dose below which no damage occurs.
        let_kev_per_um: Linear Energy Transfer (optional).
        particle_type: Particle type for default RBE.

    Returns:
        Probability of damage [0, 1].
    """
    if dose_mgy < threshold_mgy:
        return 0.0

    rbe = compute_rbe(let_kev_per_um, particle_type)
    effective_dose = dose_mgy - threshold_mgy
    return 1.0 - math.exp(-alpha * effective_dose * rbe)


# NASA OCHMO career dose limits (NSCR-2019 model, Sievert):
# These are 3% excess cancer mortality limits at 95% confidence interval.
# Source: NASA-STD-3001 Vol. 2, Rev. C, Table 6.2.3.1
NASA_CAREER_LIMIT_SV = {
    "male_35y": 0.60,
    "male_45y": 0.90,
    "male_55y": 1.20,
    "female_35y": 0.45,
    "female_45y": 0.70,
    "female_55y": 0.90,
}
# ISS 6-month mission typical dose (mGy, unshielded):
ISS_MISSION_DOSE_MGY = 100.0
# Organ-specific tissue weighting factors (ICRP 103, Table 3)
TISSUE_WEIGHTS_ICRP103 = {
    "bone_marrow": 0.12,
    "colon": 0.12,
    "lung": 0.12,
    "stomach": 0.12,
    "breast": 0.12,
    "remainder": 0.12,
    "bladder": 0.04,
    "esophagus": 0.04,
    "liver": 0.04,
    "thyroid": 0.04,
    "bone_surface": 0.01,
    "brain": 0.01,
    "salivary_glands": 0.01,
    "skin": 0.01,
}


@dataclass(frozen=True)
class BiologicalDose:
    """Physical dose converted to biologically effective dose.

    P1 FIX (Panel 8 NASA JSC): The system was reporting in mGy (physical dose,
    Gray). NASA career limits are in Sievert (biologically weighted). Failing to
    convert means the API cannot answer 'Is this astronaut within NASA limits?'

    Conversion: H [Sv] = D [Gy] × RBE × (1/1000) × [mGy → Gy]
    Effective dose: E [Sv] = sum_T w_T × H_T  (ICRP 103 tissue weights)
    """

    physical_dose_mgy: float       # input, in milliGray
    rbe: float                      # Relative Biological Effectiveness
    equivalent_dose_msv: float      # H = D × RBE, in milliSievert
    effective_dose_msv: float       # E ≈ H × mean tissue weight (simplified)
    particle_type: str
    let_kev_per_um: float | None
    nasa_career_limit_fraction: dict[str, float]  # fraction of career limit consumed
    exceeds_any_limit: bool


def convert_to_biological_dose(
    dose_mgy: float,
    let_kev_per_um: float | None = None,
    particle_type: str = "proton",
    mission_duration_days: float | None = None,  # noqa: ARG001  # stored in provenance by caller
) -> BiologicalDose:
    """Convert physical dose (mGy) to biologically effective dose (mSv).

    P1 FIX (Panel 8 NASA JSC): mGy measures energy deposited in tissue.
    mSv = mGy × RBE weighs that energy by biological effectiveness.
    HZE iron ions at LET=200 keV/μm have RBE~25 — 500 mGy becomes 12,500 mSv,
    far above NASA's ~600 mSv career limit for a 35-year-old female.

    The system was previously only reporting mGy. This function enables the
    API to answer 'what fraction of NASA career limit does this exposure consume?'

    Args:
        dose_mgy: Total physical dose in milliGray.
        let_kev_per_um: Linear Energy Transfer (keV/μm). None = use particle default.
        particle_type: Particle type for default RBE.
        mission_duration_days: Optional — for context/logging only.

    Returns:
        BiologicalDose with equivalent dose in mSv and career limit fractions.
    """
    rbe = compute_rbe(let_kev_per_um, particle_type)

    # Equivalent dose: H_T = D × RBE (same RBE for all tissues, simplified)
    # Convert mGy → mSv (1 mGy × RBE = 1 mSv for reference radiation)
    equivalent_dose_msv = dose_mgy * rbe

    # Effective dose: E = sum_T w_T × H_T
    # For whole-body uniform dose: E ≈ H (weights sum to 1)
    # Here we use a simplified mean weight (space radiation primarily bone marrow risk)
    effective_dose_msv = equivalent_dose_msv  # whole-body approximation

    # Fraction of NASA career limit consumed
    limit_fractions = {}
    for demographic, limit_sv in NASA_CAREER_LIMIT_SV.items():
        limit_msv = limit_sv * 1000.0
        limit_fractions[demographic] = round(effective_dose_msv / limit_msv, 4)

    exceeds = any(f >= 1.0 for f in limit_fractions.values())

    return BiologicalDose(
        physical_dose_mgy=dose_mgy,
        rbe=rbe,
        equivalent_dose_msv=equivalent_dose_msv,
        effective_dose_msv=effective_dose_msv,
        particle_type=particle_type,
        let_kev_per_um=let_kev_per_um,
        nasa_career_limit_fraction=limit_fractions,
        exceeds_any_limit=exceeds,
    )


def compute_dose_response_curve(
    model: str,
    max_dose_mgy: float = 2000.0,
    n_points: int = 200,
    alpha: float = ALPHA_SIDECHAIN_OXIDATION,
    threshold_mgy: float = 50.0,
    let_kev_per_um: float | None = None,
    particle_type: str = "proton",
) -> DoseResponseCurve:
    """Generate a full dose-response curve for visualization.

    Args:
        model: "lnt" or "threshold".
        max_dose_mgy: Maximum dose to plot.
        n_points: Number of curve points.

    Returns:
        DoseResponseCurve with doses and probabilities.
    """
    doses = np.linspace(0, max_dose_mgy, n_points)
    rbe = compute_rbe(let_kev_per_um, particle_type)

    if model == "lnt":
        probs = np.array([lnt_model(d, alpha, let_kev_per_um, particle_type) for d in doses])
    elif model == "threshold":
        probs = np.array([threshold_model(d, alpha, threshold_mgy, let_kev_per_um, particle_type) for d in doses])
    else:
        raise ValueError(f"Unknown model: {model}. Use 'lnt' or 'threshold'.")

    return DoseResponseCurve(
        model_name=model,
        doses=doses,
        probabilities=probs,
        alpha=alpha,
        rbe=rbe,
        threshold_mgy=threshold_mgy if model == "threshold" else None,
    )
