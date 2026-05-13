"""Secondary particle production: spallation neutrons, albedo neutrons, dose buildup.

Physics gap #7 from the 2026-04-18 audit: "Secondary particle production —
neutron spallation, (p,n), albedo neutrons missing; can add 30-50% to dose."

Without secondary neutron modeling, dose estimates behind thick shields are
systematically underestimated because:
  1. Primary GCR protons and HZE ions trigger inelastic nuclear reactions,
     producing secondary neutrons via spallation and nuclear evaporation.
  2. Secondary neutrons have long mean-free-paths (λ ≈ 120 g/cm² in Al)
     and high biological effectiveness (Q ≈ 5-20 for 1-100 MeV neutrons).
  3. Combined secondary production from all GCR species raises the effective
     dose by a dose buildup factor B ≈ 1.3-1.5 relative to the primary-only
     attenuation estimate.

Models implemented:
  1. ICRP 74 (1996) Table A.12 neutron fluence-to-effective-dose conversion
     (AP geometry, ICRP 60 tissue weighting), log-log interpolated.
  2. Alsmiller 1975 / Armstrong 1969 thin-target spallation neutron multiplicity:
     Y(T, A) = a₀ × (A/A_ref)^0.5 × (T_p/100)^α  [neutrons/interaction].
  3. Exact one-group slab transport integral for secondary neutron exit flux.
  4. GCR-weighted dose buildup factor B(x) fitted to HZETRN/NCRP 132 benchmarks.
  5. Albedo neutron dose for LEO (Preszler 1976 JGR 81 4953).
  6. SecondaryNeutronBudget composite result with primary + secondary breakdown.

References:
    ICRP 74 (1996) "Conversion Coefficients for use in Radiological Protection"
        Table A.12 (neutrons, AP geometry, effective dose).
    NCRP 132 (2000) "Radiation Protection Guidance for Activities in LEO" §4.4.
    Alsmiller, R.G. (1975) ORNL-5050 §3.3 (spallation neutron multiplicities).
    Armstrong, J.C. & Alsmiller, R.G. (1969) ORNL-TM-2887 (thick-target yields).
    Preszler, A.M. et al. (1976) JGR 81 4953 (albedo neutron spectrum/flux).
    Cucinotta, F.A. et al. (2002) NASA/TM-2002-210993 (HZETRN validation).
    Bertini, H.W. (1963) Phys Rev 131 1801 (intranuclear cascade).
    Lewis, E.E. & Miller, W.F. (1984) "Computational Methods of Neutron
        Transport." Wiley, §3.2 (slab transport integral).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .cascade_scaling import letaw_1983_inelastic


# ── Constants ──────────────────────────────────────────────────────────────────

_N_AVO = 6.02214076e23    # mol⁻¹  (CODATA 2018)
_SEC_PER_YR = 3.15576e7   # s/yr   (Julian year)

# ── ICRP 74 neutron fluence-to-effective-dose conversion table ─────────────────
# ICRP Publication 74 (1996) Table A.12, anterior-posterior (AP) irradiation.
# ICRP 60 tissue weighting factors; effective dose E per unit fluence.

_ICRP74_ENERGY_MEV = [
    1.0e-9,   # thermal (25 meV ≈ kT at 290 K; using 1 neV bin edge)
    1.0e-7,   # cold neutrons
    1.0e-6,   # epithermal
    1.0e-5,
    1.0e-4,
    1.0e-3,
    1.0e-2,   # 10 keV
    1.0e-1,   # 100 keV
    5.0e-1,   # 500 keV
    1.0e0,    # 1 MeV
    2.0e0,
    5.0e0,
    1.0e1,    # 10 MeV
    2.0e1,
    5.0e1,
    1.0e2,    # 100 MeV
    2.0e2,
    5.0e2,
    1.0e3,    # 1 GeV
]

_ICRP74_H_PHI_PSV_CM2 = [
    2.7,      # thermal     (ICRP 74 Table A.12)
    2.7,      # 0.1 neV
    2.7,      # 1 µeV
    2.7,      # 10 µeV
    2.7,      # 100 µeV
    3.0,      # 1 meV
    7.5,      # 10 keV
    20.0,     # 100 keV
    75.0,     # 500 keV
    133.0,    # 1 MeV
    212.0,    # 2 MeV
    286.0,    # 5 MeV
    310.0,    # 10 MeV
    353.0,    # 20 MeV
    430.0,    # 50 MeV
    500.0,    # 100 MeV
    540.0,    # 200 MeV
    569.0,    # 500 MeV
    580.0,    # 1 GeV
]

# Evaporation spectrum mean energy weighted h_Φ (two-component model):
# f_evap=0.70 at <E>=2×T_nuc=3 MeV → h_Φ≈250; f_high=0.30 at 500 MeV → h_Φ≈569
# Weisskopf (1937) T_nuc≈1.5 MeV; NCRP 132 §4.4 high-energy tail fraction.
_H_PHI_EVAP_PSV_CM2 = 250.0    # evaporation peak component (Weisskopf 1937)
_H_PHI_HIGH_PSV_CM2 = 569.0    # high-energy tail (500 MeV representative)
_F_EVAP = 0.70                  # fraction of secondaries in evaporation peak (NCRP 132)
_H_PHI_EFF_PSV_CM2 = _F_EVAP * _H_PHI_EVAP_PSV_CM2 + (1.0 - _F_EVAP) * _H_PHI_HIGH_PSV_CM2  # 340.7 pSv·cm²

# ── Spallation yield parameters (Alsmiller 1975 ORNL-5050 §3.3) ──────────────
# Y(T_p, A_targ) = _SPALL_A0 × (A/A_ref)^0.5 × (T_p/100)^alpha
# Calibrated to Armstrong 1969 ORNL-TM-2887 Table 5 for protons on Al.
# At T=1 GeV, Al: Y ≈ 1.25 n/interaction; Fe: Y ≈ 1.80 n/interaction.
_SPALL_A0 = 0.25        # yield at T_p=100 MeV, A_targ=A_ref  (Alsmiller 1975)
_SPALL_ALPHA = 0.70     # energy scaling exponent               (Alsmiller 1975)
_SPALL_A_REF = 27.0     # reference mass number (Al)            (Alsmiller 1975)

# ── Neutron transport mean free path in Al (fast neutrons) ───────────────────
_LAMBDA_N_AL_GCM2 = 120.0   # g/cm²; fast neutrons 1-100 MeV (NCRP 132 §4.4.4)

# ── GCR dose buildup factor empirical fit to HZETRN (NCRP 132 Fig. 4-9) ──────
# B(x) = 1 + b_max × (1 - exp(-x/λ_bld))
# Fitted to NCRP 132 benchmarks: B(20)≈1.30, B(40)≈1.40, B(100)≈1.50.
_B_MAX = 0.55           # maximum excess dose fraction (NCRP 132 §4.4 / HZETRN)
_LAMBDA_BLD_GCM2 = 30.0 # buildup saturation depth [g/cm²]     (NCRP 132 §4.4)

# ── Albedo neutron parameters (Preszler 1976 JGR 81 4953) ────────────────────
_ALBEDO_THERMAL_500KM_CM2_S = 0.50   # thermal neutron flux at 500 km altitude
_ALBEDO_FAST_500KM_CM2_S = 0.10      # fast neutron flux (0.5 eV–15 MeV) at 500 km
_ALBEDO_E_FAST_MEV = 2.0             # representative fast albedo neutron energy
_ALBEDO_ALT_REF_KM = 500.0           # reference altitude [km]   (Preszler 1976)
# Flux scales as R_E²/(R_E+h)² (geometric solid angle from Earth surface)
_R_EARTH_KM = 6371.0                 # Earth mean radius [km]


def icrp74_neutron_dose_coeff_psv_cm2(energy_mev: float) -> float:
    """ICRP 74 (1996) neutron fluence-to-effective-dose conversion coefficient.

    Log-log interpolation in ICRP Publication 74 Table A.12, anterior-
    posterior (AP) irradiation geometry, ICRP 60 tissue weighting factors.

    Args:
        energy_mev: Neutron kinetic energy [MeV]. Valid range: 1 neV – 1 GeV;
            values outside are clamped to the table endpoints.

    Returns:
        Effective dose per unit fluence h_Φ [pSv·cm²].

    Reference: ICRP Publication 74 (1996) Table A.12.
    """
    if energy_mev <= 0.0:
        raise ValueError("energy_mev must be positive")

    # Clamp to table range
    e_lo = _ICRP74_ENERGY_MEV[0]
    e_hi = _ICRP74_ENERGY_MEV[-1]
    if energy_mev <= e_lo:
        return _ICRP74_H_PHI_PSV_CM2[0]
    if energy_mev >= e_hi:
        return _ICRP74_H_PHI_PSV_CM2[-1]

    # Binary search for bracket
    lo, hi = 0, len(_ICRP74_ENERGY_MEV) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _ICRP74_ENERGY_MEV[mid] <= energy_mev:
            lo = mid
        else:
            hi = mid

    # Log-log interpolation (dose conversion varies over many decades)
    log_e = math.log(energy_mev)
    log_e_lo = math.log(_ICRP74_ENERGY_MEV[lo])
    log_e_hi = math.log(_ICRP74_ENERGY_MEV[hi])
    log_h_lo = math.log(_ICRP74_H_PHI_PSV_CM2[lo])
    log_h_hi = math.log(_ICRP74_H_PHI_PSV_CM2[hi])
    t = (log_e - log_e_lo) / (log_e_hi - log_e_lo)
    return math.exp(log_h_lo + t * (log_h_hi - log_h_lo))


def spallation_neutron_yield_per_interaction(
    projectile_energy_mev: float,
    target_mass_number: int = 27,
) -> float:
    """Thin-target spallation neutron multiplicity per inelastic interaction.

    Implements the Alsmiller 1975 power-law parameterization of intranuclear
    cascade calculations from Armstrong & Alsmiller (1969) ORNL-TM-2887:

        Y(T_p, A) = a₀ × (A/A_ref)^0.5 × (T_p/100 MeV)^α

    where a₀ = 0.25, α = 0.70 (calibrated to ORNL-TM-2887 Table 5 for Al).

    The A^0.5 scaling reflects the number of target nucleons available for
    the evaporation cascade; it saturates more slowly than the inelastic
    cross section (A^0.7) because deeply-bound nucleons are not accessible.

    Args:
        projectile_energy_mev: Proton kinetic energy [MeV]. Below 10 MeV,
            the threshold effect cuts the yield to near zero.
        target_mass_number: Target nucleus mass number A. Default 27 (Al).

    Returns:
        Mean number of secondary neutrons per inelastic interaction.

    Reference: Alsmiller 1975 ORNL-5050 §3.3; Armstrong & Alsmiller 1969
        ORNL-TM-2887 Table 5.
    """
    if projectile_energy_mev <= 0.0:
        raise ValueError("projectile_energy_mev must be positive")
    if target_mass_number < 1:
        raise ValueError("target_mass_number must be ≥ 1")

    a_fac = (float(target_mass_number) / _SPALL_A_REF) ** 0.5
    e_fac = (max(projectile_energy_mev, 1.0) / 100.0) ** _SPALL_ALPHA
    return _SPALL_A0 * a_fac * e_fac


def _primary_mfp_gcm2(target_mass_number: int, energy_mev: float) -> float:
    """Inelastic mean free path for a proton in target material [g/cm²].

    λ = A / (N_A × σ_inel_cm²)  where σ_inel is from Letaw 1983.
    """
    sigma_mb = letaw_1983_inelastic(target_mass_number, energy_mev)
    sigma_cm2 = sigma_mb * 1.0e-27
    # atoms per gram = N_A / A
    atoms_per_g = _N_AVO / float(target_mass_number)
    return 1.0 / (atoms_per_g * sigma_cm2)


def secondary_neutron_exit_flux(
    primary_flux_cm2_s: float,
    shield_thickness_gcm2: float,
    target_mass_number: int = 27,
    primary_energy_mev: float = 1000.0,
    neutron_mfp_gcm2: float = _LAMBDA_N_AL_GCM2,
) -> float:
    """Secondary neutron flux exiting the shield downstream face [cm⁻²s⁻¹].

    Solves the one-group slab production-transport integral exactly
    (Lewis & Miller 1984 §3.2):

        Φ_n(X) = (Y Φ₀/λ_p) ∫₀^X exp(-x'/λ_p) × exp(-(X-x')/λ_n) dx'
                = Y Φ₀ × λ_n/(λ_n − λ_p) × [exp(−X/λ_n) − exp(−X/λ_p)]

    where λ_p is the primary proton inelastic MFP (Letaw 1983) and λ_n
    is the secondary neutron transport MFP (120 g/cm² for fast n in Al,
    NCRP 132 §4.4.4).  The limiting form when λ_n = λ_p:
        Φ_n = Y Φ₀ × (X/λ) × exp(−X/λ).

    Args:
        primary_flux_cm2_s: Incident primary proton flux Φ₀ [cm⁻²s⁻¹].
        shield_thickness_gcm2: Shield areal density X [g/cm²].
        target_mass_number: Shield material mass number A (default 27 = Al).
        primary_energy_mev: Typical primary proton energy [MeV].
        neutron_mfp_gcm2: Secondary neutron transport MFP [g/cm²].

    Returns:
        Secondary neutron flux at shield exit [cm⁻²s⁻¹].

    Reference: Lewis & Miller 1984 §3.2; NCRP 132 §4.4; Alsmiller 1975.
    """
    if shield_thickness_gcm2 <= 0.0:
        return 0.0

    Y = spallation_neutron_yield_per_interaction(primary_energy_mev, target_mass_number)
    lam_p = _primary_mfp_gcm2(target_mass_number, primary_energy_mev)
    lam_n = neutron_mfp_gcm2
    x = shield_thickness_gcm2

    if abs(lam_n - lam_p) < 0.1:
        # L'Hôpital limiting form when λ_n ≈ λ_p
        return primary_flux_cm2_s * Y * (x / lam_n) * math.exp(-x / lam_n)

    # Exact one-group transport integral
    return (
        primary_flux_cm2_s * Y * lam_n / (lam_n - lam_p)
        * (math.exp(-x / lam_n) - math.exp(-x / lam_p))
    )


def dose_buildup_factor_gcr_al(shield_thickness_gcm2: float) -> float:
    """GCR dose buildup factor B(x) for aluminum shielding.

    B(x) = D_total(x) / D_primary_attenuated(x)

    Fitted to HZETRN benchmark calculations (Cucinotta 2002
    NASA/TM-2002-210993) and NCRP 132 §4.4 Figure 4-9:

        B(x) = 1 + b_max × (1 − exp(−x/λ_bld))

    where b_max = 0.55 (NCRP 132 §4.4) and λ_bld = 30 g/cm².

    Benchmark spot-checks (NCRP 132 Fig. 4-9):
        B(10) ≈ 1.15,  B(20) ≈ 1.27,  B(40) ≈ 1.40,  B(100) ≈ 1.52.

    Args:
        shield_thickness_gcm2: Aluminum areal density x [g/cm²].

    Returns:
        Dose buildup factor B ≥ 1.

    Reference: NCRP 132 (2000) §4.4 Fig. 4-9; Cucinotta et al. 2002
        NASA/TM-2002-210993 (HZETRN validation against ISS data).
    """
    if shield_thickness_gcm2 < 0.0:
        raise ValueError("shield_thickness_gcm2 must be ≥ 0")
    return 1.0 + _B_MAX * (1.0 - math.exp(-shield_thickness_gcm2 / _LAMBDA_BLD_GCM2))


def albedo_neutron_dose_sv_yr(
    altitude_km: float,
    shielding_gcm2: float = 5.0,
) -> float:
    """Annual effective dose from Earth albedo neutrons for a LEO vehicle.

    Earth albedo neutrons are produced by cosmic-ray spallation in the
    upper atmosphere and reflect back into LEO.  Preszler et al. (1976)
    measured at 500 km:
      - Thermal flux (< 0.5 eV): ~0.50 cm⁻²s⁻¹
      - Fast flux (0.5 eV–15 MeV): ~0.10 cm⁻²s⁻¹

    Flux scales geometrically as (R_E/(R_E+h))² with altitude (Preszler 1976).

    Note: Albedo neutrons are negligible on interstellar cruise (no Earth).
    Pass altitude_km to include them; return 0 if altitude_km > 36000 (beyond GEO).

    Args:
        altitude_km: Orbital altitude above Earth surface [km].
        shielding_gcm2: Vehicle wall shielding [g/cm²] (attenuates albedo).

    Returns:
        Annual effective dose contribution from albedo neutrons [Sv/yr].

    Reference: Preszler et al. (1976) JGR 81 4953; NCRP 132 §4.3.2.
    """
    if altitude_km > 36000.0:
        return 0.0   # beyond GEO; no significant albedo contribution

    # Geometric dilution: flux ∝ (R_E/(R_E+h))²  (Preszler 1976)
    geo_factor = (_R_EARTH_KM / (_R_EARTH_KM + altitude_km)) ** 2

    flux_thermal = _ALBEDO_THERMAL_500KM_CM2_S * geo_factor * (_ALBEDO_ALT_REF_KM / altitude_km) ** 0
    flux_fast = _ALBEDO_FAST_500KM_CM2_S * geo_factor

    # Shielding attenuation: thermal neutrons strongly attenuated by H-rich material;
    # fast neutrons use the same λ_n = 120 g/cm².
    # Thermal: exponential attenuation λ_thermal ≈ 5 g/cm² (H2O equivalent, NCRP 132)
    lam_thermal = 5.0   # g/cm²; thermal neutron MFP in typical shielding (NCRP 132)
    atten_thermal = math.exp(-shielding_gcm2 / lam_thermal)
    atten_fast = math.exp(-shielding_gcm2 / _LAMBDA_N_AL_GCM2)

    # ICRP 74 dose conversion
    h_thermal = icrp74_neutron_dose_coeff_psv_cm2(25e-9)  # 25 meV thermal
    h_fast = icrp74_neutron_dose_coeff_psv_cm2(_ALBEDO_E_FAST_MEV)

    dose_sv_s = (
        flux_thermal * atten_thermal * h_thermal * 1e-12
        + flux_fast * atten_fast * h_fast * 1e-12
    )
    return dose_sv_s * _SEC_PER_YR


@dataclass
class SecondaryNeutronBudget:
    """Dose breakdown: primary, secondary neutron, and albedo contributions.

    Attributes:
        primary_dose_sv_yr: Input primary dose [Sv/yr] (before secondary correction).
        secondary_spallation_sv_yr: Extra dose from shield-produced neutrons [Sv/yr].
        albedo_sv_yr: Albedo neutron dose (0 if not in LEO) [Sv/yr].
        buildup_factor: B(x) = total/primary. Equals 1 + secondary/primary.
        total_dose_sv_yr: Total effective dose [Sv/yr].
        secondary_fraction: D_secondary / D_total (0–1).
    """
    primary_dose_sv_yr: float
    secondary_spallation_sv_yr: float
    albedo_sv_yr: float
    buildup_factor: float
    total_dose_sv_yr: float
    secondary_fraction: float


def secondary_neutron_dose_budget(
    primary_dose_sv_yr: float,
    shield_thickness_gcm2: float,
    primary_flux_cm2_s: float = 4.0,
    primary_energy_mev: float = 1000.0,
    target_mass_number: int = 27,
    altitude_km: Optional[float] = None,
    shielding_for_albedo_gcm2: float = 5.0,
) -> SecondaryNeutronBudget:
    """Complete secondary neutron dose budget for a shielded crew member.

    Combines:
      1. GCR dose buildup factor (NCRP 132 §4.4 / HZETRN benchmark)
      2. Secondary spallation neutron dose from exit flux × ICRP 74 conversion
      3. Albedo neutron dose for LEO (Preszler 1976), if altitude_km is given

    The buildup factor B(x) captures the total secondary contribution from
    both proton- and HZE-induced neutron production (the Alsmiller thin-target
    yield applies to protons; heavier primaries are implicitly included via
    the HZETRN-fitted b_max = 0.55 that benchmarks the full GCR spectrum).

    Args:
        primary_dose_sv_yr: Primary GCR dose without secondary correction [Sv/yr].
        shield_thickness_gcm2: Shield areal density [g/cm²].
        primary_flux_cm2_s: GCR proton flux component [cm⁻²s⁻¹]. Default 4.0
            (solar-min baseline; Cucinotta 2014 NASA/TP-2013-217375).
        primary_energy_mev: Representative primary energy for spallation [MeV].
        target_mass_number: Shield material mass number (27 = Al).
        altitude_km: Orbital altitude [km], or None for interstellar cruise.
        shielding_for_albedo_gcm2: Separate albedo shielding depth [g/cm²].

    Returns:
        SecondaryNeutronBudget with full dose breakdown.

    Reference: NCRP 132 §4.4; ICRP 74 Table A.12; Cucinotta 2002.
    """
    # ── GCR buildup factor (includes full HZE spectrum via HZETRN fit) ────────
    B = dose_buildup_factor_gcr_al(shield_thickness_gcm2)
    D_buildup = primary_dose_sv_yr * B

    # ── Explicit proton-induced secondary flux and dose ────────────────────────
    phi_n = secondary_neutron_exit_flux(
        primary_flux_cm2_s,
        shield_thickness_gcm2,
        target_mass_number,
        primary_energy_mev,
    )
    D_n = phi_n * _H_PHI_EFF_PSV_CM2 * 1e-12 * _SEC_PER_YR  # Sv/yr

    # ── Albedo contribution (LEO only) ─────────────────────────────────────────
    D_albedo = 0.0
    if altitude_km is not None:
        D_albedo = albedo_neutron_dose_sv_yr(altitude_km, shielding_for_albedo_gcm2)

    # ── Total dose: use buildup factor as primary estimate; add explicit albedo ─
    # (Buildup factor already encodes spallation; D_n reported as a breakdown)
    D_total = D_buildup + D_albedo

    secondary = D_total - primary_dose_sv_yr
    secondary_fraction = secondary / D_total if D_total > 0.0 else 0.0

    return SecondaryNeutronBudget(
        primary_dose_sv_yr=primary_dose_sv_yr,
        secondary_spallation_sv_yr=D_n,
        albedo_sv_yr=D_albedo,
        buildup_factor=B,
        total_dose_sv_yr=D_total,
        secondary_fraction=secondary_fraction,
    )
