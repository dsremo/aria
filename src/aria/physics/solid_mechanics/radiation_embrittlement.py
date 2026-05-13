"""Radiation embrittlement physics for irradiated structural metals.

Implements three linked models used in fission/fusion structural analysis,
now applied to the ARIA hull and reactor vessel under century-scale GCR:

1. **DBTT shift** — Ductile-to-Brittle Transition Temperature shift from
   neutron fluence, using the Odette-Lucas (1998) / ASTM E900 empirical
   correlation.  ΔDBTT ∝ A_mat × f^(0.28 - 0.10·log₁₀f) where f is the
   fast-neutron fluence in 10¹⁹ n/cm² units.

2. **Yield strength hardening** — DPA-induced defect cluster hardening
   saturates following Zinkle & Busby (2009):
       ΔYS(Φ) = ΔYS_sat × (1 − exp(−DPA / DPA_sat))

3. **Fracture toughness** — ASTM E1921 Master Curve:
       K_JC(T) = 30 + 70 × exp(0.019 × (T − T₀))  [MPa√m]
   The reference temperature T₀ shifts with ΔDBTT.

4. **GCR displacement per atom** — species-dependent DPA rate from GCR
   ions, using displacement cross-sections from Zinkle (1994) NIMB 91.
   This links the HZE dose model (hze_sep.py) to structural damage.

References:
    Odette, G. R. & Lucas, G. E. (1998) "Recent progress in
        understanding reactor pressure vessel steel embrittlement,"
        Radiation Effects & Defects 144, 189–231.
    Zinkle, S. J. & Busby, J. T. (2009) "Structural materials for
        fission & fusion energy," Materials Today 12(11), 12–19.
    ASTM E1921-21 "Standard Test Method for the Determination of
        Reference Temperature T0 for Ferritic Steels."
    ASTM E900-15 "Standard Guide for Predicting Radiation-Induced
        Transition Temperature Shift in Reactor Vessel Materials."
    Zinkle, S. J. (1994) "Production efficiency and annealing of
        ion-induced point defects," Nucl. Instr. Meth. Phys. Res. B
        91(1-4), 234–246.
    Stoller, R. E. & Toloczko, M. B. et al. (2013) "On the use of SRIM
        for computing radiation damage exposure," Nucl. Instr. Meth.
        Phys. Res. B 310, 75–80.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict


# ── Material embrittlement parameters ────────────────────────────────────────

@dataclass(frozen=True)
class EmbrittlementParams:
    """Radiation embrittlement parameters for a structural metal.

    All DBTT and yield-shift parameters are for fast-neutron irradiation
    (E > 1 MeV) unless noted; GCR protons/HZE use the same model but with
    a species-specific displacement cross-section.
    """
    name: str

    # DBTT shift coefficient [°C per (fluence / 10^19 n/cm²)^0.5]
    # Units: °C / (normalized fluence)^0.5
    # Source: ASTM E900 Table 1; Odette-Lucas 1998 Table 2
    A_dbtt: float

    # Initial DBTT at zero fluence [°C]
    # Source: material data for as-irradiated baseline condition
    T_dbtt_ref_c: float

    # Yield strength hardening at saturation [MPa] (ΔYS_sat)
    # Source: Zinkle-Busby 2009 Table 2; Stoller 2013
    delta_ys_sat_mpa: float

    # DPA at which 63% of saturation hardening is reached (DPA_sat)
    # Source: Zinkle-Busby 2009; typical for bcc metals ~0.5–2 DPA
    dpa_sat: float

    # Master Curve reference temperature at zero fluence [°C]
    # T0 from ASTM E1921 characterization at as-received condition
    T0_ref_c: float

    # Unirradiated fracture toughness plateau [MPa√m]
    # K_JC upper shelf (ASTM E1921 upper shelf transition)
    K_JC_upper_shelf_mpa_sqm: float


# Material parameters from published literature.
# Key: material name matches ARIA digital twin material_db keys.
EMBRITTLEMENT_DB: Dict[str, EmbrittlementParams] = {
    "EUROFER97": EmbrittlementParams(
        # Reduced-activation ferritic/martensitic steel for fusion blankets.
        # Best radiation-tolerant structural steel currently available.
        # A_dbtt = coefficient in ΔDBTT = A × DPA^0.5 [°C/DPA^0.5]
        # Calibrated to Rensman (2004) 2.4 DPA→55°C and Gaganidze (2006) 6.6 DPA→70°C.
        name="EUROFER97",
        A_dbtt=30.0,            # Rensman 2004 J. Nucl. Mater. 329–333; Gaganidze 2006
        T_dbtt_ref_c=-100.0,    # DBTT ≈ −100°C as-received (Lindau 2005)
        delta_ys_sat_mpa=250.0, # Zinkle-Busby 2009 (RAFM at ~1 DPA)
        dpa_sat=0.5,            # Zinkle-Busby 2009 Table 2
        T0_ref_c=-110.0,        # ASTM E1921 Master Curve for EUROFER97 (Odette 2003)
        K_JC_upper_shelf_mpa_sqm=200.0,  # Upper shelf ~200 MPa√m (Hähner 2008)
    ),
    "Ti-6Al-4V": EmbrittlementParams(
        # Alpha-beta titanium alloy; used for hull structure and pressure vessels.
        # Hexagonal close-packed; less susceptible to DBTT shift than bcc steels.
        name="Ti-6Al-4V",
        A_dbtt=20.0,            # HCP metals: lower DBTT shift (Zinkle-Busby 2009 estimate)
        T_dbtt_ref_c=-200.0,    # Ti alloys stay ductile to very low T
        delta_ys_sat_mpa=150.0, # Zinkle-Busby 2009; Ti saturation ~150 MPa
        dpa_sat=1.0,            # Ti saturation at ~1 DPA (Kiritani 1990 NIMB 33)
        T0_ref_c=-150.0,        # Estimated; Ti alloys very tough
        K_JC_upper_shelf_mpa_sqm=80.0,   # MMPDS-17 lower-bound K_IC for Ti-6Al-4V
    ),
    "Al-2219": EmbrittlementParams(
        # Al-Cu alloy; fcc, very radiation-tolerant at low DPA.
        # Used for cryogenic tanks and secondary structure.
        name="Al-2219",
        A_dbtt=8.0,             # fcc Al: low DBTT shift (Zinkle-Busby 2009 estimate)
        T_dbtt_ref_c=-250.0,    # Al remains ductile at 4 K
        delta_ys_sat_mpa=100.0, # Zinkle-Busby 2009 Al alloys ~100 MPa
        dpa_sat=1.5,            # fcc slower to saturate than bcc
        T0_ref_c=-200.0,        # Estimated
        K_JC_upper_shelf_mpa_sqm=35.0,   # MMPDS-17 Al-2219-T87 K_IC ~35 MPa√m
    ),
    "304-SS": EmbrittlementParams(
        # Austenitic stainless steel (fcc); piping and fittings.
        name="304-SS",
        A_dbtt=25.0,            # Austenitic SS: Was 2008 J. Nucl. Mater. estimate
        T_dbtt_ref_c=-200.0,    # fcc; ductile at cryogenic T
        delta_ys_sat_mpa=300.0, # Heavy hardening at low DPA (Was 2008 JNM)
        dpa_sat=0.3,            # Fast saturation for austenitic SS
        T0_ref_c=-150.0,        # Estimated
        K_JC_upper_shelf_mpa_sqm=150.0,
    ),
}


# ── DPA cross-sections by GCR species ────────────────────────────────────────

# Displacement cross-section σ_d [cm²/ion] for iron (Fe target), from
# Zinkle (1994) Nucl. Instr. Meth. B 91 Table 1, and Stoller (2013).
# Units: DPA per (ion/cm²) = σ_d / (number of Fe atoms per unit volume × V)
# Simplified: DPA/fluence ≈ σ_d × N_atoms_per_cm2 per cm² per ion
# For structural use: 1 ion/cm² gives σ_d DPA integrated over the layer.
#
# Note: these are representative values at ~1 GeV/nucleon typical GCR energy.
# Full energy-dependent tables are in Stoller 2013 Table A1.
GCR_DISPLACEMENT_XSEC_CM2: Dict[str, float] = {
    "Proton":   3.0e-24,   # proton p-Fe: Zinkle 1994; Stoller 2013 SRIM
    "Helium-4": 1.5e-23,   # He-4 (alpha): ~5× proton (Zinkle 1994)
    "CNO":      5.0e-22,   # C/N/O at 1 GeV/n: Zinkle 1994 Table 1
    "Mg-Si":    3.0e-21,   # Mg/Si: Zinkle 1994
    "Fe":       1.5e-20,   # Fe-56 GCR: Zinkle 1994; highest DPA per ion
}

# Number density of Fe atoms in iron-based steel [atoms/cm²] for normalization.
# For pure Fe: n = ρ·N_A/M = 7.87 g/cm³ × 6.022e23 / 55.85 = 8.49e22 atoms/cm³
# Per cm² through 1 cm: N_2D = n = 8.49e22  (for path-length normalized DPA)
# But ARIA uses fluence × σ_d directly for DPA rate per atom — no path length needed.
_FE_ATOM_DENSITY_PER_CM3 = 8.49e22  # atoms/cm³ (ρ_Fe·N_A/M_Fe)


def gcr_dpa_annual(
    species_flux_dict: Dict[str, float],
    target_material: str = "iron",
) -> float:
    """Annual DPA from GCR species in iron-like structural steel.

    Args:
        species_flux_dict: Dict mapping GCR species name → annual fluence
            (integrated flux) in particles/cm²/yr.  Species names must match
            keys in GCR_DISPLACEMENT_XSEC_CM2 ('Proton', 'Helium-4', ...).
        target_material: Currently only 'iron' (bcc Fe cross-sections used).
            Future: Al, Ti lookup tables.

    Returns:
        Annual DPA rate [DPA/yr] in the structural material.

    References:
        Zinkle 1994 NIMB 91; Stoller 2013 NIMB 310.
    """
    total_dpa = 0.0
    for species, fluence in species_flux_dict.items():
        sigma = GCR_DISPLACEMENT_XSEC_CM2.get(species)
        if sigma is None:
            continue
        # DPA = fluence [ion/cm²] × σ_d [cm²/ion]  (per target atom; no N factor)
        total_dpa += fluence * sigma
    return total_dpa


def reactor_dpa_annual(
    fast_neutron_flux_n_cm2_s: float,
    material: str = "EUROFER97",
) -> float:
    """Annual DPA from reactor fast-neutron flux in structural steel.

    Uses the standard displacement cross-section for Fe (NRT model).
    For a fusion blanket first wall: flux ~10^14 n/cm²/s → ~20 DPA/yr.
    For ARIA reactor vessel at distance: flux ~10^10-10^11 n/cm²/s → 0.02-0.2 DPA/yr.

    Args:
        fast_neutron_flux_n_cm2_s: Fast neutron flux (E > 1 MeV) [n/cm²/s].
        material: Material name (currently ignored; Fe σ_d used).

    Returns:
        DPA per year.

    References:
        Stoller 2013 NIMB 310 (SRIM NIEL); NRT model: Norgett 1975.
    """
    # NRT displacement cross-section for Fe, fast neutron (E > 1 MeV) average.
    # σ_d = 1e-21 cm²/n (Stoller 2013 NIMB 310, Table 1; Norgett 1975 NRT model).
    # DPA = flux [n/cm²/s] × σ_d [cm²/n] × time [s]  (per target atom; no N factor)
    sigma_d_neutron = 1.0e-21   # cm²/n
    seconds_per_year = 365.25 * 86400.0
    return fast_neutron_flux_n_cm2_s * sigma_d_neutron * seconds_per_year


# ── DBTT shift (Odette-Lucas / ASTM E900) ───────────────────────────────────

def dbtt_shift_c(
    dpa: float,
    params: EmbrittlementParams,
    fluence_n19: float | None = None,
) -> float:
    """DBTT shift from accumulated displacement damage.

    Uses a DPA-based power law fit to published fusion-material data:
        ΔDBTT = A_dbtt × DPA^0.5

    This is the standard form used in fusion materials databases and is
    preferred over the fission-RPV Odette-Lucas fluence formula for
    materials experiencing high DPA doses (>0.1 DPA).  Calibration
    against published EUROFER97 irradiation data:
      - Rensman (2004): 2.4 DPA → ~55°C
      - Gaganidze (2006): 6.6 DPA → ~70°C
    EUROFER97 A_dbtt = 30 gives: √2.4 × 30 = 46°C (lower bound) to
    √6.6 × 30 = 77°C (upper bound) — within the experimental scatter.

    Args:
        dpa: Accumulated displacement per atom [DPA].
        params: Material embrittlement parameters.
        fluence_n19: If provided, override DPA-based calculation with
            Odette-Lucas fluence formula (for RPV-style assessments using
            known neutron fluence in 10^19 n/cm² units).

    Returns:
        ΔDBTT [°C] — positive means DBTT shifted to higher temperature
        (material becomes more brittle).

    References:
        Zinkle-Busby 2009 Fig. 3; Rensman 2004 JNM 329–333;
        Gaganidze 2006 Fusion Eng. Des. 81 1557.
        Odette-Lucas 1998 (fluence_n19 path): Eq. (1) for RPV assessments.
    """
    if fluence_n19 is not None:
        # Odette-Lucas (1998) fluence-based path — kept for RPV assessments
        if fluence_n19 <= 0.0:
            return 0.0
        log_f = math.log10(fluence_n19)
        exponent = 0.28 - 0.10 * log_f
        return params.A_dbtt * (fluence_n19 ** exponent)

    # Default: DPA-based power-law (Zinkle-Busby 2009; fusion materials)
    if dpa <= 0.0:
        return 0.0
    return params.A_dbtt * math.sqrt(dpa)


def current_dbtt_c(dpa: float, params: EmbrittlementParams) -> float:
    """Current DBTT [°C] after accumulated DPA.

    Returns:
        DBTT(DPA) = T_dbtt_ref + ΔDBTT(DPA).
    """
    return params.T_dbtt_ref_c + dbtt_shift_c(dpa, params)


# ── Yield strength hardening (Zinkle-Busby saturation model) ─────────────────

def yield_strength_shift_mpa(dpa: float, params: EmbrittlementParams) -> float:
    """DPA-induced yield strength increase [MPa].

    Saturation model from Zinkle & Busby 2009:
        ΔYS(DPA) = ΔYS_sat × (1 − exp(−DPA / DPA_sat))

    Args:
        dpa: Accumulated displacement per atom.
        params: Material embrittlement parameters.

    Returns:
        Yield strength increase ΔYS [MPa]. Always ≥ 0.

    Reference:
        Zinkle-Busby 2009, Fig. 3 and Table 2.
    """
    return params.delta_ys_sat_mpa * (1.0 - math.exp(-dpa / max(params.dpa_sat, 1e-9)))


# ── ASTM E1921 Master Curve fracture toughness ───────────────────────────────

def master_curve_k_jc(test_temp_c: float, T0_c: float) -> float:
    """ASTM E1921 Master Curve median fracture toughness K_JC.

    K_JC(T) = 30 + 70 × exp(0.019 × (T − T₀))  [MPa√m]

    This is the statistical median of the lower-shelf to transition region
    for ferritic/martensitic steels. Valid for T ≤ T₀ + 50°C approximately
    (upper shelf requires separate Charpy energy correlation).

    Args:
        test_temp_c: Component operating temperature [°C].
        T0_c: Master Curve reference temperature [°C] (from ASTM E1921 testing
            or shifted by DBTT correction: T0 = T0_ref + ΔDBTT).

    Returns:
        Median K_JC [MPa√m] at the 50th percentile.

    Reference:
        ASTM E1921-21 Eq. (2).
    """
    return 30.0 + 70.0 * math.exp(0.019 * (test_temp_c - T0_c))


def fracture_toughness_after_irradiation(
    test_temp_c: float,
    dpa: float,
    params: EmbrittlementParams,
) -> float:
    """K_JC at given temperature after accumulated DPA.

    Combines Master Curve with DBTT shift:
        T0_irradiated = T0_ref + ΔDBTT(DPA)
        K_JC = min(master_curve(T, T0_irradiated), K_upper_shelf)

    Args:
        test_temp_c: Operating temperature [°C].
        dpa: Accumulated DPA.
        params: Material parameters.

    Returns:
        K_JC [MPa√m] (capped at upper shelf value).

    Reference:
        ASTM E1921-21; Odette-Lucas 1998 §3.
    """
    delta_dbtt = dbtt_shift_c(dpa, params)
    T0_irr = params.T0_ref_c + delta_dbtt
    k_jc = master_curve_k_jc(test_temp_c, T0_irr)
    return min(k_jc, params.K_JC_upper_shelf_mpa_sqm)


# ── Embrittlement budget function ────────────────────────────────────────────

@dataclass
class EmbrittlementBudget:
    """Full radiation embrittlement state for a structural component."""
    material: str
    dpa: float
    dbtt_ref_c: float
    dbtt_shift_c: float
    dbtt_current_c: float
    delta_ys_mpa: float
    k_jc_at_operating_temp: float   # K_JC at component operating temperature
    k_jc_ref: float                 # K_JC unirradiated for comparison
    margin_fraction: float          # K_JC_current / K_JC_ref
    brittle_risk: bool              # True if DBTT > operating temperature


def embrittlement_budget(
    material_name: str,
    dpa: float,
    operating_temp_c: float = 20.0,
) -> EmbrittlementBudget:
    """Compute full radiation embrittlement state for a named material.

    Args:
        material_name: Key in EMBRITTLEMENT_DB.
        dpa: Accumulated displacement per atom.
        operating_temp_c: Component service temperature [°C].

    Returns:
        EmbrittlementBudget with all computed properties.

    Raises:
        KeyError: If material_name not in EMBRITTLEMENT_DB.
    """
    params = EMBRITTLEMENT_DB[material_name]
    d_dbtt = dbtt_shift_c(dpa, params)
    dbtt_now = params.T_dbtt_ref_c + d_dbtt
    delta_ys = yield_strength_shift_mpa(dpa, params)
    k_jc_now = fracture_toughness_after_irradiation(operating_temp_c, dpa, params)
    k_jc_ref = fracture_toughness_after_irradiation(operating_temp_c, 0.0, params)
    margin = k_jc_now / max(k_jc_ref, 1.0)

    return EmbrittlementBudget(
        material=material_name,
        dpa=dpa,
        dbtt_ref_c=params.T_dbtt_ref_c,
        dbtt_shift_c=d_dbtt,
        dbtt_current_c=dbtt_now,
        delta_ys_mpa=delta_ys,
        k_jc_at_operating_temp=k_jc_now,
        k_jc_ref=k_jc_ref,
        margin_fraction=margin,
        brittle_risk=(dbtt_now >= operating_temp_c),
    )
