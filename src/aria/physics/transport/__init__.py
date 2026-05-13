"""Pod E2 — Neutron and high-energy nucleon transport (P0 subset).

Implements audit items §1.3.6 (spallation from HZE cosmic rays),
§4.4 (secondary neutron flux in shield), §4.5 (secondary pion/muon
cascades).

See `docs/pods/E2_neutron_transport.md` for the full scope note
(derivations, citations, verification test cases).

**P0 scope (this commit):** self-contained closed-form primitives
that don't require external MCNP / FLUKA / INCL4.6 / ENDF libraries:

  - GCR differential and integral flux per Cucinotta 2014
    (NASA/TP-2013-217375) with solar modulation
  - Exponential attenuation and macroscopic cross section
  - Inelastic proton-nucleus cross section per Letaw 1983
    (parameterization; used as order-of-magnitude pion/neutron
    source estimate)
  - Pion/muon decay chain kinematics and PDG lifetimes
  - Muon CSDA range per Groom 2001
  - Cucinotta 2014 shielded-dose calculation that reproduces the
    ARIA baseline (~65 % reduction with 20 g/cm² Al)

**Deferred to a follow-up commit**: full S_N discrete-ordinates
solver, Monte Carlo kernel, CADIS variance reduction, INCL4.6
wrapper, ABLA evaporation — all of which need external libraries
and/or ENDF/B-VIII.0 tabulated cross sections that ARIA does not yet
ship.

Public API:
    CUCINOTTA_2014_CONSTANTS       — solar modulation and proton flux
    GCR_PROTON_FLUX_1AU_SOLAR_MIN  — 4 p/cm²/s above 10 MeV
    gcr_total_proton_flux          — integral flux Φ(>E_min, φ_SM)
    gcr_annual_unshielded_dose     — 0.42 Sv/yr solar-min baseline
    cucinotta_shielded_dose        — shielded crew dose for Al depth
    solar_modulation_exp_factor    — exp(−E₀/E) roll-off
    mean_free_path                 — 1 / (ρ (N_A / M) σ)
    macroscopic_cross_section      — Σ = n σ
    attenuation_exponential        — I / I₀ = exp(−Σ x)
    letaw_1983_inelastic           — p-A inelastic σ(A, E)
    pion_to_muon_decay_fraction    — fraction surviving time t
    muon_to_electron_decay_fraction
    muon_csda_range_water          — Groom 2001 range table
    CUCINOTTA_2014_GCR_DOSE_SV_YR
    GROOM_2001_MUON_RANGE_TABLE
    PDG_PION_LIFETIME_S, PDG_MUON_LIFETIME_S
"""

from .hze_sep import (
    GCR_SPECIES_SOLAR_MIN,
    GCRSpecies,
    SEP_EXTREME_EVENT,
    SEP_LARGE_EVENT,
    SEP_SMALL_EVENT,
    SEPEventModel,
    hze_dose_breakdown,
    hze_shielded_dose,
    icrp60_quality_factor,
    sep_annual_expected_dose_sv,
    sep_proton_dose_sv,
    sep_single_event_probability,
    total_annual_dose_sv,
)
from .gcr_source import (
    CUCINOTTA_2014_CONSTANTS,
    CUCINOTTA_2014_GCR_DOSE_SV_YR,
    GCR_PROTON_FLUX_1AU_SOLAR_MIN,
    cucinotta_shielded_dose,
    gcr_annual_unshielded_dose,
    gcr_total_proton_flux,
    solar_modulation_exp_factor,
)
from .attenuation import (
    attenuation_exponential,
    macroscopic_cross_section,
    mean_free_path,
)
from .cascade_scaling import letaw_1983_inelastic
from .secondary_neutrons import (
    SecondaryNeutronBudget,
    albedo_neutron_dose_sv_yr,
    dose_buildup_factor_gcr_al,
    icrp74_neutron_dose_coeff_psv_cm2,
    secondary_neutron_dose_budget,
    secondary_neutron_exit_flux,
    spallation_neutron_yield_per_interaction,
)
from .pion_muon_chain import (
    GROOM_2001_MUON_RANGE_TABLE,
    PDG_MUON_LIFETIME_S,
    PDG_PION_LIFETIME_S,
    muon_csda_range_water,
    muon_to_electron_decay_fraction,
    pion_to_muon_decay_fraction,
)

__all__ = [
    # HZE quality weighting + SEP events
    "icrp60_quality_factor",
    "GCRSpecies",
    "GCR_SPECIES_SOLAR_MIN",
    "hze_dose_breakdown",
    "hze_shielded_dose",
    "SEPEventModel",
    "SEP_SMALL_EVENT",
    "SEP_LARGE_EVENT",
    "SEP_EXTREME_EVENT",
    "sep_proton_dose_sv",
    "sep_annual_expected_dose_sv",
    "sep_single_event_probability",
    "total_annual_dose_sv",
    # GCR
    "CUCINOTTA_2014_CONSTANTS",
    "CUCINOTTA_2014_GCR_DOSE_SV_YR",
    "GCR_PROTON_FLUX_1AU_SOLAR_MIN",
    "gcr_annual_unshielded_dose",
    "gcr_total_proton_flux",
    "solar_modulation_exp_factor",
    "cucinotta_shielded_dose",
    # Attenuation
    "attenuation_exponential",
    "macroscopic_cross_section",
    "mean_free_path",
    # Cascade
    "letaw_1983_inelastic",
    # Secondary neutrons (gap #7)
    "SecondaryNeutronBudget",
    "albedo_neutron_dose_sv_yr",
    "dose_buildup_factor_gcr_al",
    "icrp74_neutron_dose_coeff_psv_cm2",
    "secondary_neutron_dose_budget",
    "secondary_neutron_exit_flux",
    "spallation_neutron_yield_per_interaction",
    # Pion/muon
    "PDG_PION_LIFETIME_S",
    "PDG_MUON_LIFETIME_S",
    "GROOM_2001_MUON_RANGE_TABLE",
    "muon_csda_range_water",
    "muon_to_electron_decay_fraction",
    "pion_to_muon_decay_fraction",
]
