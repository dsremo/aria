"""Reactive Oxygen Species (ROS) diffusion model for space radiation damage.

P1 FIX (Radiation biology critique): "Direct ionisation hits to proteins
are rare (Poisson, λ~0.009 per protein at 1 MGy). The dominant damage
mechanism is INDIRECT — ionising radiation creates OH• and O2•⁻ radicals
from water radiolysis. These diffuse and attack biomolecules over μm
distances. Ignoring diffusion underestimates actual protein damage by 10-100×."

Model:
  1. Radiation hits water → primary ROS production (G-value model)
  2. ROS diffuse from hit site via 3D random walk (diffusion equation)
  3. ROS encounter proteins and react (bimolecular rate constant k_rxn)
  4. Damage probability per protein = 1 - exp(-n_encounters × p_rxn)

G-value: mean number of ROS produced per 100 eV of energy deposited.
  - OH• G-value ≈ 2.7 per 100 eV (ICRU Report 31)
  - O2•⁻ G-value ≈ 0.6 per 100 eV
  - H2O2 G-value ≈ 0.7 per 100 eV

Diffusion coefficient (water, 37°C):
  - OH•: D ≈ 2.3 × 10⁻⁹ m²/s (very fast)
  - O2•⁻: D ≈ 1.0 × 10⁻⁹ m²/s

References:
  Spinks & Woods (1990), Introduction to Radiation Chemistry
  Hall & Giaccia (2018), Radiobiology for the Radiologist
  Roots & Okada (1975), Radiat Res 64(2):306-320
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger()


class ROSSpecies(str, Enum):  # noqa: UP042
    """Reactive oxygen species relevant to radiation biology."""
    HYDROXYL   = "OH"      # •OH  — most reactive, dominant DNA/protein damager
    SUPEROXIDE = "O2m"     # O2•⁻ — moderate reactivity, dismutates to H2O2
    PEROXIDE   = "H2O2"    # H2O2 — less reactive but longer-lived, diffuses further
    SINGLET_O2 = "1O2"     # ¹O2  — produced near photosensitisers, lipid damage


# G-values: ROS produced per 100 eV (ICRU Report 31, 1979 §3: sparsely ionising radiation)
G_VALUE_PER_100EV: dict[ROSSpecies, float] = {
    ROSSpecies.HYDROXYL:   2.73,  # ICRU Report 31 (1979) Table 3.1: G(•OH) = 2.73 per 100 eV
    ROSSpecies.SUPEROXIDE: 0.62,  # ICRU Report 31 Table 3.1: G(eaq−) ≈ 0.62 → generates O2•⁻ in O2-saturated medium
    ROSSpecies.PEROXIDE:   0.72,  # ICRU Report 31 Table 3.1: G(H2O2) = 0.72 per 100 eV
    ROSSpecies.SINGLET_O2: 0.10,  # ESTIMATE — singlet O2 from sensitized ROS; Hall & Giaccia 2018 §2.3 (no direct ICRU value)
}

# Diffusion coefficients in water at 37°C (m²/s)
DIFFUSION_COEFF_M2S: dict[ROSSpecies, float] = {
    ROSSpecies.HYDROXYL:   2.3e-9,  # Spinks & Woods 1990 Intro Radiation Chemistry §4.2: D(•OH) ≈ 2.3×10⁻⁹ m²/s
    ROSSpecies.SUPEROXIDE: 1.0e-9,  # Spinks & Woods 1990 §4.2: D(O2•⁻) ≈ 1.0×10⁻⁹ m²/s
    ROSSpecies.PEROXIDE:   2.3e-9,  # Spinks & Woods 1990 §4.2: D(H2O2) ≈ 2.3×10⁻⁹ m²/s (similar to OH•)
    ROSSpecies.SINGLET_O2: 2.0e-9,  # ESTIMATE — D(¹O2) ≈ D(O2) ≈ 2.0×10⁻⁹ m²/s (Wilke-Chang correlation)
}

# Biological half-lives in cellular environment (seconds)
# Limited by scavenging by glutathione, SOD, catalase
BIOLOGICAL_HALF_LIFE_S: dict[ROSSpecies, float] = {
    ROSSpecies.HYDROXYL:   1e-9,   # ~1 ns: Roots & Okada 1975 Radiat Res 64 306: •OH t½ ~0.5-4 ns intracellular
    ROSSpecies.SUPEROXIDE: 1e-6,   # ~1 μs: Fridovich 1978 Science 201 875: SOD dismutation t½ ~μs in cells
    ROSSpecies.PEROXIDE:   1e-3,   # ~1 ms: ESTIMATE — catalase/peroxidase turnover; Gaetani 1989 Blood 73 334
    ROSSpecies.SINGLET_O2: 3e-6,   # ~3 μs: Ogilby 2010 Chem Soc Rev 39 3181: ¹O2 t½ 3-4 μs in water
}

# Second-order rate constant k₂ for ROS + protein reaction (M⁻¹s⁻¹)
REACTION_RATE_CONST_M1S1: dict[ROSSpecies, float] = {
    ROSSpecies.HYDROXYL:   1e10,  # Buxton 1988 J Phys Chem Ref Data 17 513: k(•OH + protein) ≈ 10⁸-10¹⁰ M⁻¹s⁻¹ (diffusion-limited)
    ROSSpecies.SUPEROXIDE: 1e6,   # ESTIMATE — O2•⁻ less reactive; Finkel & Holbrook 2000 Nature 408 239 §2
    ROSSpecies.PEROXIDE:   1e3,   # ESTIMATE — H2O2 slow direct reaction; Stadman 1992 Science 257 1220
    ROSSpecies.SINGLET_O2: 1e8,   # ESTIMATE — ¹O2 + amino acids ~10⁷-10⁸ M⁻¹s⁻¹; Rougee & Bensasson 1986
}

# eV per ionisation event (W-value in water)
W_VALUE_EV = 33.0  # ICRU Report 31 (1979) §2.1: W(water) = 33.0 eV per ion pair


@dataclass(frozen=True)
class ROSDiffusionResult:
    """Result of ROS diffusion model for a protein in irradiated medium."""

    protein_damage_probability: float    # P(at least one ROS hit on protein)
    expected_ros_encounters: float       # mean number of ROS molecules reaching protein
    ros_breakdown: dict[str, float]      # per-species encounter count
    diffusion_radius_nm: dict[str, float]  # mean diffusion radius per species (nm)
    indirect_to_direct_ratio: float      # indirect / direct damage ratio
    dominant_species: str                # which ROS species causes most damage
    dose_mgy: float
    protein_radius_nm: float
    temperature_k: float


def mean_diffusion_radius_nm(
    species: ROSSpecies,
    temperature_k: float = 310.0,
) -> float:
    """Compute mean diffusion radius before ROS is quenched (nm).

    r_mean = √(6 × D × t_half / ln2)

    where D is temperature-corrected via Stokes-Einstein:
      D(T) = D(310K) × T/310K × η(310K)/η(T)
    Approximated as D(T) ≈ D₀ × (T/310).

    Args:
        species: ROS species.
        temperature_k: Temperature (K). Default: 37°C (310 K).

    Returns:
        RMS diffusion radius in nanometres.
    """
    d0 = DIFFUSION_COEFF_M2S[species]
    t_half = BIOLOGICAL_HALF_LIFE_S[species]

    # Temperature scaling (simplified Stokes-Einstein)
    d_t = d0 * (temperature_k / 310.0)

    # Mean diffusion distance from 3D random walk: r = √(6Dt)
    # At t = t_half/ln2, half the ROS have reacted
    t_effective = t_half / math.log(2)
    r_m = math.sqrt(6.0 * d_t * t_effective)

    return r_m * 1e9  # m → nm


def compute_ros_encounters(
    dose_mgy: float,
    protein_radius_nm: float,
    cell_volume_um3: float = 4000.0,  # ESTIMATE — 4000 μm³ typical mammalian cell (Milo & Phillips 2015 Cell Biology by the Numbers §1)
    temperature_k: float = 310.0,     # 37°C human/mammalian body temperature (NIST SRD 10)
    ros_species: list[ROSSpecies] | None = None,
) -> dict[ROSSpecies, float]:
    """Compute expected number of ROS molecules that reach the protein surface.

    Method:
    1. Dose → energy deposited in cell → ionisation events (W-value)
    2. Ionisation events → primary ROS (G-value)
    3. ROS diffuse in 3D. Fraction reaching protein = A_protein / (4π r²)
       integrated over survival time, accounting for exponential ROS decay.
       Simplified: f ≈ (r_protein / r_diffusion)² for r_protein << r_diffusion

    Args:
        dose_mgy: Absorbed radiation dose in milligray.
        protein_radius_nm: Approximate protein radius in nm.
        cell_volume_um3: Cell volume in μm³.
        temperature_k: Temperature in Kelvin.
        ros_species: Which ROS species to model. Default: all.

    Returns:
        Dict mapping ROSSpecies → expected number of ROS encounters.
    """
    if ros_species is None:
        ros_species = list(ROSSpecies)

    # Energy deposited in cell
    cell_mass_kg = cell_volume_um3 * 1e-18 * 1000  # μm³ → m³ → kg (water density)
    energy_joules = (dose_mgy * 1e-3) * cell_mass_kg  # Gy = J/kg
    energy_ev = energy_joules / 1.602e-19

    encounters: dict[ROSSpecies, float] = {}
    for sp in ros_species:
        # Primary ROS produced
        n_ros_primary = energy_ev / 100.0 * G_VALUE_PER_100EV[sp]

        # Mean diffusion radius
        r_diff_nm = mean_diffusion_radius_nm(sp, temperature_k)

        # Geometric capture fraction: (protein cross-section) / (4π r_diff²)
        # This is an upper-bound sphere approximation
        if r_diff_nm <= 0 or protein_radius_nm <= 0:
            capture_fraction = 0.0
        else:
            r_p = protein_radius_nm
            r_d = r_diff_nm
            # For r_p << r_d: fraction ≈ (r_p / r_d)²
            # For r_p ≈ r_d: saturates toward 1
            capture_fraction = min((r_p / r_d) ** 2, 1.0)

        encounters[sp] = n_ros_primary * capture_fraction

    return encounters


def compute_ros_damage(
    dose_mgy: float,
    protein_radius_nm: float = 2.0,   # ESTIMATE — 2 nm radius typical small protein (~250 residues); Erickson 2009 Biol Proced Online 11 32
    cell_volume_um3: float = 4000.0,  # ESTIMATE — 4000 μm³ typical mammalian cell (Milo & Phillips 2015 §1)
    temperature_k: float = 310.0,     # 37°C human body temperature (NIST SRD 10)
    direct_damage_lambda: float | None = None,
) -> ROSDiffusionResult:
    """Compute total radiation damage probability including indirect ROS effects.

    Combines:
    - Direct ionisation hits (Poisson model from fractionation.py)
    - Indirect ROS diffusion (this module)

    The combined damage probability:
      P_damage = 1 - (1 - P_direct) × prod_i(1 - P_i_indirect)

    For small probabilities: P_damage ≈ P_direct + Σ P_i_indirect

    Args:
        dose_mgy: Absorbed dose (milligray).
        protein_radius_nm: Effective protein radius (nm). Typical: 2-4 nm.
        cell_volume_um3: Cell volume (μm³). Default: typical mammalian cell.
        temperature_k: Temperature (K). Default: 37°C body temperature.
        direct_damage_lambda: Precomputed λ from Poisson direct-hit model.
            If None, computed from dose and protein geometry.

    Returns:
        ROSDiffusionResult with damage probability and diagnostics.
    """
    encounters = compute_ros_encounters(
        dose_mgy=dose_mgy,
        protein_radius_nm=protein_radius_nm,
        cell_volume_um3=cell_volume_um3,
        temperature_k=temperature_k,
    )

    # Protein concentration in cell (approximate)
    # Average cell has ~1e6 protein molecules, cell_volume = 4000 μm³
    # → protein concentration ≈ 4 μM
    protein_conc_m = 4e-6  # ESTIMATE — ~4 μM individual protein; Milo & Phillips 2015 §2: ~10⁶ proteins per mammalian cell

    # Reaction probability per encounter:
    # p_rxn = k₂ × [protein] × t_half_life  (competition with scavengers)
    # Simplified: p_rxn based on diffusion-limited reaction with protein
    indirect_p_total = 0.0
    ros_breakdown: dict[str, float] = {}
    diffusion_radii: dict[str, float] = {}

    for sp, n_enc in encounters.items():
        k2 = REACTION_RATE_CONST_M1S1[sp]
        BIOLOGICAL_HALF_LIFE_S[sp]
        # Probability per encounter that the ROS reacts with THIS protein
        # vs. being scavenged or reacting with a different molecule
        # p_rxn ≈ k₂[protein] / (k₂[protein] + k_scavenge)
        # Approximate k_scavenge for OH• ≈ 1e7 s⁻¹ (intracellular glutathione ~5 mM)
        # Intracellular scavenging pseudo-first-order rate (s⁻¹)
        k_scavenge = {
            ROSSpecies.HYDROXYL:   1e7,   # Roots & Okada 1975 Radiat Res 64 306: k_scav ~1e7 s⁻¹ (glutathione ~5 mM)
            ROSSpecies.SUPEROXIDE: 1e5,   # ESTIMATE — SOD-mediated ~1e5 s⁻¹ in cytoplasm
            ROSSpecies.PEROXIDE:   1e2,   # ESTIMATE — catalase ~1e2 s⁻¹ at physiological [H2O2]
            ROSSpecies.SINGLET_O2: 1e6,   # ESTIMATE — physical quenching + chemical ~1e6 s⁻¹ intracellular
        }.get(sp, 1e6)

        k_protein = k2 * protein_conc_m
        p_rxn = k_protein / (k_protein + k_scavenge)

        effective_encounters = n_enc * p_rxn
        # P(at least one encounter damages protein) = 1 - e^{-n_effective}
        p_indirect_species = 1.0 - math.exp(-effective_encounters)
        indirect_p_total = 1.0 - (1.0 - indirect_p_total) * (1.0 - p_indirect_species)

        ros_breakdown[sp.value] = effective_encounters
        diffusion_radii[sp.value] = mean_diffusion_radius_nm(sp, temperature_k)

    # Direct damage probability from Poisson model
    if direct_damage_lambda is None:
        # Quick estimate: direct hit requires ionisation within protein volume
        protein_volume_nm3 = (4.0 / 3.0) * math.pi * protein_radius_nm**3
        cell_volume_nm3 = cell_volume_um3 * 1e9  # μm³ → nm³
        cell_mass_kg = cell_volume_um3 * 1e-18 * 1000
        energy_j = dose_mgy * 1e-3 * cell_mass_kg
        n_ionizations = energy_j / (W_VALUE_EV * 1.602e-19)
        vf = protein_volume_nm3 / cell_volume_nm3
        direct_lambda = n_ionizations * vf
    else:
        direct_lambda = direct_damage_lambda

    p_direct = 1.0 - math.exp(-direct_lambda)

    # Combined damage probability
    p_combined = 1.0 - (1.0 - p_direct) * (1.0 - indirect_p_total)

    # Indirect/direct ratio
    indirect_to_direct = indirect_p_total / (p_direct + 1e-30)

    # Dominant ROS species
    dominant = max(ros_breakdown, key=lambda k: ros_breakdown[k]) if ros_breakdown else "none"

    logger.debug(
        "ros_diffusion_computed",
        dose_mgy=dose_mgy,
        p_direct=round(p_direct, 6),
        p_indirect=round(indirect_p_total, 6),
        p_combined=round(p_combined, 6),
        indirect_to_direct=round(indirect_to_direct, 2),
        dominant_species=dominant,
    )

    return ROSDiffusionResult(
        protein_damage_probability=p_combined,
        expected_ros_encounters=sum(ros_breakdown.values()),
        ros_breakdown=ros_breakdown,
        diffusion_radius_nm=diffusion_radii,
        indirect_to_direct_ratio=indirect_to_direct,
        dominant_species=dominant,
        dose_mgy=dose_mgy,
        protein_radius_nm=protein_radius_nm,
        temperature_k=temperature_k,
    )
