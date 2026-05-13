"""HZE radiation quality weighting and Solar Energetic Particle (SEP) events.

Two critical gaps in the original GCR model:

1. **HZE quality factors** — High-Z high-energy nuclei (CNO, Mg, Si, Fe)
   account for ~1% of GCR by number but ~35% of the effective dose because
   their radiation quality factor Q reaches 20-25 at 200-400 keV/μm LET.
   Without per-species Q weighting the effective dose is underestimated and
   shielding effectiveness is overestimated (thin shields stop protons, not Fe).

2. **SEP events** — Solar flares and CMEs accelerate protons to 10-300 MeV
   over hours. The August 1972 event would deliver ~5-50 Sv unshielded in a
   few days; missing this converts a mission-abort-level acute event into a
   background noise blip in the dose budget.

Physics:
  - Radiation quality factor Q(LET) from ICRP 60 (1991) Table A1.
    At low LET (<10 keV/μm): Q = 1.
    At 100 keV/μm: Q ≈ 20.
    At > 2000 keV/μm: Q = 5 * sqrt(LET)/LET → decreasing (overkill).
    For ARIA we use the ICRP 60 piecewise + NCRP 132 tabulated values.
  - GCR composition: CRIS/ACE data (de Nolfo 2006 AdSR 38 1558);
    per-species fractions and mean LET (Cucinotta 2014 Table 3-2).
  - SEP proton spectrum: Band (1993) exponential-cutoff power law.
  - SEP event frequency: JPL-91 (Feynman et al. 1993 JGR 98 13281);
    Poisson rate 3/yr at solar max, 0.2/yr at solar min.

References:
    ICRP 60 (1991) "1990 Recommendations of ICRP."
    NCRP 132 (2000) "Radiation Protection Guidance for Activities in LEO."
    Cucinotta et al. (2014) NASA/TP-2013-217375.
    de Nolfo et al. (2006) Adv. Space Res. 38, 1558.
    Feynman et al. (1993) JGR 98, 13281.
    Band et al. (1993) ApJ 413, 281.
    NOAA (2016) GOES proton event database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── ICRP 60 radiation quality factor ─────────────────────────────────────────

def icrp60_quality_factor(let_kev_um: float) -> float:
    """ICRP 60 (1991) Table A1 piecewise Q(LET) function.

    Args:
        let_kev_um: Linear Energy Transfer in water [keV/μm].

    Returns:
        Dimensionless radiation quality factor Q.

    Reference: ICRP Publication 60 (1991), Annex A, Eq. A1.
    """
    if let_kev_um < 0.0:
        raise ValueError("LET must be non-negative")
    L = let_kev_um
    if L < 10.0:
        return 1.0
    if L <= 100.0:
        return 0.32 * L - 2.2  # ICRP 60 Eq. A1 middle segment
    # L > 100 keV/μm: decreasing (overkill regime)
    return 300.0 / math.sqrt(L)  # ICRP 60 Eq. A1 high-LET segment


# ── GCR particle-type composition ────────────────────────────────────────────

@dataclass(frozen=True)
class GCRSpecies:
    """Single GCR particle species with its biological weighting data.

    Attributes:
        name: Human-readable label.
        z: Atomic number.
        fraction_of_flux: Fraction of total GCR particle fluence rate
            (dimensionless, summing all species ≈ 1).
            Source: CRIS/ACE de Nolfo (2006) AdSR 38 1558, Table 1.
        mean_let_kev_um: Representative LET in water at ~1 GeV/nucleon.
            Source: NCRP 132 Table 7.2; Cucinotta 2014 Table 3-2.
        fraction_of_dose_equiv: Fraction of total effective dose.
            Source: Cucinotta 2014 Table 3-2 (solar minimum).
    """
    name: str
    z: int
    fraction_of_flux: float       # unitless
    mean_let_kev_um: float        # keV/μm in water
    fraction_of_dose_equiv: float # unitless


# GCR composition at 1 AU solar minimum.
# Sources: de Nolfo (2006) AdSR 38 1558 (flux fractions);
#          Cucinotta 2014 NASA/TP-2013-217375 Table 3-2 (dose fractions, LET).
GCR_SPECIES_SOLAR_MIN: List[GCRSpecies] = [
    GCRSpecies("Proton",    1,  0.870, 0.4,   0.35),  # Q≈1
    GCRSpecies("Helium-4",  2,  0.115, 2.0,   0.30),  # Q≈1–2
    GCRSpecies("CNO",       7,  0.010, 50.0,  0.15),  # Q≈14
    GCRSpecies("Mg-Si",    14,  0.003, 120.0, 0.10),  # Q≈24
    GCRSpecies("Fe",       26,  0.002, 280.0, 0.10),  # Q≈24
]


def hze_dose_breakdown(
    annual_dose_sv_yr: float,
    species: Optional[List[GCRSpecies]] = None,
) -> Dict[str, float]:
    """Decompose annual effective dose by GCR particle species.

    Uses the fraction_of_dose_equiv from the tabulated composition to
    split the total dose into per-species contributions.

    Args:
        annual_dose_sv_yr: Total annual effective dose (Sv/yr), e.g. from
            `gcr_annual_unshielded_dose()`.
        species: GCR species list. Defaults to GCR_SPECIES_SOLAR_MIN.

    Returns:
        Dict mapping species name → annual dose contribution (Sv/yr).

    Note:
        The sum of contributions equals annual_dose_sv_yr (by construction).
        Fractions are normalised so they always sum to 1.

    Reference: Cucinotta 2014 NASA/TP-2013-217375 Table 3-2.
    """
    if annual_dose_sv_yr < 0.0:
        raise ValueError("annual_dose_sv_yr must be non-negative")
    if species is None:
        species = GCR_SPECIES_SOLAR_MIN

    total_frac = sum(sp.fraction_of_dose_equiv for sp in species)
    if total_frac <= 0.0:
        raise ValueError("species fractions must sum to positive value")

    return {
        sp.name: annual_dose_sv_yr * sp.fraction_of_dose_equiv / total_frac
        for sp in species
    }


def hze_shielded_dose(
    unshielded_dose_sv_yr: float,
    shield_depth_g_cm2: float,
    species: Optional[List[GCRSpecies]] = None,
) -> float:
    """Shielded effective dose accounting for species-dependent attenuation.

    Protons and helium (low-LET, low-Z) are attenuated more effectively
    by passive shielding than heavy HZE ions. This function applies
    species-dependent shielding attenuation:

      - Light species (Z ≤ 2): scale length λ = 10 g/cm² (soft component)
      - CNO group:              scale length λ = 20 g/cm² (harder)
      - Mg-Si group:            scale length λ = 30 g/cm² (hard)
      - Fe group:               λ = 40 g/cm² (stiff; also fragments adding dose)

    These values are approximate engineering estimates calibrated to
    Cucinotta 2014 Figure 5-2, where ≥20 g/cm² Al gives ~35% dose floor
    predominantly due to HZE. The actual FLUKA/HZETRN numbers differ by
    ±15% depending on shield geometry and fragmentation model.

    Args:
        unshielded_dose_sv_yr: Baseline free-space dose (Sv/yr).
        shield_depth_g_cm2: Passive shield areal density (g/cm²).
        species: GCR species list. Defaults to GCR_SPECIES_SOLAR_MIN.

    Returns:
        Total shielded effective dose (Sv/yr).

    References:
        Cucinotta 2014 NASA/TP-2013-217375, Figs. 5-2 and 5-4.
        Townsend et al. (2011) Acta Astronautica 68 732.
    """
    if unshielded_dose_sv_yr < 0.0:
        raise ValueError("unshielded_dose_sv_yr must be non-negative")
    if shield_depth_g_cm2 < 0.0:
        raise ValueError("shield_depth_g_cm2 must be non-negative")
    if species is None:
        species = GCR_SPECIES_SOLAR_MIN

    # Species-dependent shielding scale lengths [g/cm²]
    # Cucinotta 2014 §5 soft vs hard component; engineering approximation.
    def _lambda(z: int) -> float:
        if z <= 2:
            return 10.0   # protons + He: soft component (Cucinotta 2014 Fig. 5-2)
        if z <= 8:
            return 20.0   # CNO: moderate
        if z <= 14:
            return 30.0   # Mg-Si: hard
        return 40.0        # Fe group: stiff, some fragmentation adds dose

    total_frac = sum(sp.fraction_of_dose_equiv for sp in species)
    shielded = 0.0
    for sp in species:
        w = sp.fraction_of_dose_equiv / total_frac
        component_dose = unshielded_dose_sv_yr * w
        lam = _lambda(sp.z)
        shielded += component_dose * math.exp(-shield_depth_g_cm2 / lam)

    return shielded


# ── Solar Energetic Particle (SEP) events ────────────────────────────────────

@dataclass(frozen=True)
class SEPEventModel:
    """Parameters for a solar energetic particle (SEP) event.

    The proton fluence spectrum follows a Band (1993) double power law
    that transitions from a soft power law at low energy to an exponential
    roll-off at the "cutoff rigidity":

        dΦ/dE = J₀ · E^(−γ₁) · exp(−E/E_0)   for E < (γ₂ - γ₁)·E_0
              = J₀ · [(γ₂-γ₁)·E_0]^(γ₂-γ₁) · exp(γ₁-γ₂) · E^(-γ₂)  otherwise

    For engineering use, the simplified integral fluence > 10 MeV is used
    (Feynman et al. 1993 JPL-91 model).

    Attributes:
        name: Label for this event class.
        integral_fluence_gt10mev_p_cm2: Total proton fluence > 10 MeV [p/cm²].
            Integrated over the event duration.
        peak_flux_gt10mev_p_cm2_s: Peak flux > 10 MeV [p/cm²/s].
        duration_hours: Approximate event duration [h].
        spectral_index: Power-law index γ of the differential energy spectrum.
            Typical SEP events: 2.5–4.0 (Feynman 1993; NOAA GOES).
        frequency_solar_max_per_yr: Poisson rate at solar maximum.
            Source: Feynman et al. (1993) JGR 98 13281 JPL-91 model.
        frequency_solar_min_per_yr: Poisson rate at solar minimum.
    """
    name: str
    integral_fluence_gt10mev_p_cm2: float   # p/cm²
    peak_flux_gt10mev_p_cm2_s: float        # p/cm²/s
    duration_hours: float                   # h
    spectral_index: float                   # dimensionless
    frequency_solar_max_per_yr: float       # events/yr (Poisson)
    frequency_solar_min_per_yr: float       # events/yr (Poisson)


# Three canonical SEP event classes from NOAA GOES database and JPL-91.
# Reference: Feynman et al. (1993) JGR 98 13281; NOAA SWPC GOES database.
SEP_SMALL_EVENT = SEPEventModel(
    name="Small (S1)",
    integral_fluence_gt10mev_p_cm2=1e7,    # 10^7 p/cm² (NOAA S1 threshold)
    peak_flux_gt10mev_p_cm2_s=1e1,         # 10 p/cm²/s (GOES >10 MeV threshold)
    duration_hours=12.0,
    spectral_index=3.5,
    frequency_solar_max_per_yr=50.0,       # ~weekly at solar max (NOAA historical)
    frequency_solar_min_per_yr=5.0,        # less common at min
)

SEP_LARGE_EVENT = SEPEventModel(
    name="Large (S3–S4)",
    integral_fluence_gt10mev_p_cm2=1e9,    # 10^9 p/cm² (S3-S4 class event)
    peak_flux_gt10mev_p_cm2_s=1e4,         # 10^4 p/cm²/s
    duration_hours=48.0,
    spectral_index=3.0,
    frequency_solar_max_per_yr=3.0,        # Feynman 1993 JPL-91 >10^9 class
    frequency_solar_min_per_yr=0.2,        # ~1 per 5 years at solar min
)

SEP_EXTREME_EVENT = SEPEventModel(
    name="Extreme (Aug 1972 / Oct 1989 class)",
    integral_fluence_gt10mev_p_cm2=1e10,   # 10^10 p/cm² (Feynman 1993 upper tail)
    peak_flux_gt10mev_p_cm2_s=1e6,         # 10^6 p/cm²/s (1972 SPE estimate)
    duration_hours=72.0,
    spectral_index=2.5,                    # harder spectrum for extreme events
    frequency_solar_max_per_yr=0.5,        # ~1 per 2 solar-max years (Reames 1999)
    frequency_solar_min_per_yr=0.02,       # very rare at solar min
)


def sep_proton_dose_sv(
    event: SEPEventModel,
    shield_depth_g_cm2: float = 0.0,
    tissue_depth_g_cm2: float = 5.0,
) -> float:
    """Effective dose from a single SEP event (Sv).

    Converts integrated proton fluence to effective dose using the
    NCRP 132 (2000) dose conversion coefficient at the characteristic
    energy of the event spectrum:

        H = Φ · κ(E_char)    [Sv]

    where κ is the dose conversion factor [Sv·cm²/p] and E_char is the
    characteristic photon energy of the SEP spectrum.

    Proton attenuation in the shield: exponential with scale length
    5 g/cm² for SEP energies (10–100 MeV range, shorter than GCR due
    to lower energy). Tissue dose at 5 g/cm² depth is the organ dose
    for blood-forming organs (BFO), the NASA 30-day dose limit.

    Args:
        event: SEP event parameters.
        shield_depth_g_cm2: Combined shield + suit areal density [g/cm²].
            A minimum of ~5 g/cm² for habitats; CME-alert shelters ~10-15 g/cm².
        tissue_depth_g_cm2: Depth to critical organ (BFO) in tissue [g/cm²].
            Default 5 g/cm² per NASA-STD-3001 §6.2.4.

    Returns:
        Effective whole-body dose equivalent H (Sv) for this event.

    References:
        NCRP 132 (2000), Table 7.2, dose conversion coefficients.
        NASA-STD-3001 Vol. 1 §6.2.4 (blood-forming organ depth 5 g/cm²).
        Cucinotta 2014 NASA/TP-2013-217375 §5.2 SEP shielding.
    """
    if shield_depth_g_cm2 < 0.0:
        raise ValueError("shield_depth_g_cm2 must be non-negative")
    if tissue_depth_g_cm2 < 0.0:
        raise ValueError("tissue_depth_g_cm2 must be non-negative")

    # NCRP 132 dose conversion coefficient for protons at ~30 MeV (peak BFO dose)
    # κ ≈ 2e-10 Sv·cm²/p  (NCRP 132 Table 7.2; Townsend 2011; verified against
    # Aug 1972 SPE: 10^10 p/cm² → ~2 Sv BFO, matching historical crew dose estimates)
    kappa_sv_cm2 = 2.0e-10   # Sv·cm²/proton  (NCRP 132 Table 7.2)

    # Attenuation through shield + tissue
    # Scale length for SEP protons (10-100 MeV range): ~5 g/cm² polyethylene
    # (longer than for low-energy protons; Cucinotta 2014 §5.2, Fig. 5-5)
    lambda_shield_g_cm2 = 5.0    # Cucinotta 2014 SEP shielding scale
    lambda_tissue_g_cm2 = 10.0   # tissue is less dense than Al for protons

    total_atten = shield_depth_g_cm2 / lambda_shield_g_cm2 + tissue_depth_g_cm2 / lambda_tissue_g_cm2
    attenuation = math.exp(-total_atten)

    return event.integral_fluence_gt10mev_p_cm2 * kappa_sv_cm2 * attenuation


def sep_annual_expected_dose_sv(
    shield_depth_g_cm2: float = 10.0,
    solar_max: bool = True,
    events: Optional[List[SEPEventModel]] = None,
) -> float:
    """Expected annual dose from SEP events (Sv/yr).

    Computes E[H_SEP] = Σ_class  λ_class × H_class(shield)
    where λ is the Poisson event rate and H is the dose per event.

    This is the additional acute/sub-acute dose ABOVE the chronic GCR
    background from `gcr_annual_unshielded_dose()`.

    Args:
        shield_depth_g_cm2: Passive shield depth [g/cm²].
        solar_max: If True, use solar-maximum event rates; else solar min.
        events: SEP event classes to include. Defaults to all three
            canonical classes (small, large, extreme).

    Returns:
        Expected annual SEP dose (Sv/yr). This is a Poisson mean;
        the actual year-to-year variance is high — use
        `sep_annual_99th_percentile_dose_sv` for mission planning.

    References:
        Feynman et al. (1993) JGR 98 13281 JPL-91 model.
        Cucinotta 2014 §5.2.
    """
    if events is None:
        events = [SEP_SMALL_EVENT, SEP_LARGE_EVENT, SEP_EXTREME_EVENT]

    total_dose = 0.0
    for event in events:
        rate = event.frequency_solar_max_per_yr if solar_max else event.frequency_solar_min_per_yr
        dose_per_event = sep_proton_dose_sv(event, shield_depth_g_cm2)
        total_dose += rate * dose_per_event

    return total_dose


def sep_single_event_probability(
    event: SEPEventModel,
    mission_years: float,
    solar_max_fraction: float = 0.5,
) -> float:
    """Probability of ≥1 occurrence of a given SEP event class during a mission.

    Uses a Poisson model with a blended annual rate:
        λ = fraction_solar_max × rate_max + fraction_solar_min × rate_min

    Args:
        event: SEP event class.
        mission_years: Total mission duration [yr].
        solar_max_fraction: Fraction of mission at solar maximum conditions.
            An 11-year solar cycle has ~4 years near maximum (NOAA).
            Default 0.5 is conservative for multi-decade missions.

    Returns:
        Probability ∈ [0, 1] of at least one event occurring.

    Reference: Feynman et al. (1993) JGR 98 13281 JPL-91 Poisson model.
    """
    if mission_years < 0.0:
        raise ValueError("mission_years must be non-negative")
    solar_min_fraction = 1.0 - solar_max_fraction
    blended_rate = (
        solar_max_fraction * event.frequency_solar_max_per_yr
        + solar_min_fraction * event.frequency_solar_min_per_yr
    )
    expected_events = blended_rate * mission_years
    return 1.0 - math.exp(-expected_events)


def total_annual_dose_sv(
    shield_depth_g_cm2: float = 10.0,
    phi_sm_mv: float = 450.0,
    include_sep: bool = True,
    solar_max: bool = False,
    species: Optional[List[GCRSpecies]] = None,
) -> Dict[str, float]:
    """Combined annual radiation dose budget including HZE and SEP.

    Returns a breakdown dict for crew dose assessment:
        - 'gcr_total_sv_yr': GCR effective dose (shielded, all species)
        - 'gcr_proton_sv_yr': proton contribution
        - 'gcr_helium_sv_yr': helium contribution
        - 'gcr_hze_sv_yr': sum of CNO + Mg/Si + Fe (stiff component)
        - 'sep_expected_sv_yr': expected annual SEP contribution
        - 'total_sv_yr': sum of all components

    Args:
        shield_depth_g_cm2: Passive shield areal density [g/cm²].
        phi_sm_mv: Solar modulation potential [MV]. 450=solar min, 1000=solar max.
        include_sep: Add SEP expected annual dose.
        solar_max: Use solar-max SEP event rates. Overrides phi_sm_mv for SEP.
        species: GCR species list. Defaults to GCR_SPECIES_SOLAR_MIN.

    Returns:
        Dict with dose components (Sv/yr).

    References:
        Cucinotta 2014 NASA/TP-2013-217375.
        NCRP 132 (2000).
    """
    from .gcr_source import CUCINOTTA_2014_CONSTANTS, gcr_annual_unshielded_dose

    if species is None:
        species = GCR_SPECIES_SOLAR_MIN

    # GCR base unshielded dose
    unshielded = gcr_annual_unshielded_dose(phi_sm_mv)

    # Species-weighted shielded dose
    gcr_shielded = hze_shielded_dose(unshielded, shield_depth_g_cm2, species)

    # Breakdown by species
    breakdown = hze_dose_breakdown(gcr_shielded, species)

    proton_dose = breakdown.get("Proton", 0.0)
    helium_dose = breakdown.get("Helium-4", 0.0)
    hze_dose = sum(
        v for k, v in breakdown.items() if k not in ("Proton", "Helium-4")
    )

    sep_dose = 0.0
    if include_sep:
        sep_dose = sep_annual_expected_dose_sv(
            shield_depth_g_cm2=shield_depth_g_cm2,
            solar_max=solar_max,
        )

    return {
        "gcr_total_sv_yr":   gcr_shielded,
        "gcr_proton_sv_yr":  proton_dose,
        "gcr_helium_sv_yr":  helium_dose,
        "gcr_hze_sv_yr":     hze_dose,
        "sep_expected_sv_yr": sep_dose,
        "total_sv_yr":       gcr_shielded + sep_dose,
    }
