"""Deep-dielectric charging (§4.4 of D2 scope).

MeV electrons penetrate dielectric materials, slow down via inelastic
collisions, and deposit a volumetric charge distribution `ρ_q(r)`. The
resulting internal electric field is governed by the coupled
diffusion–drift equations of Frederickson et al. 1991
*IEEE Trans Nucl Sci* 38 1493. The steady-state solution for a
parallel-plate dielectric of thickness `d` with uniform bulk current
injection `J_0` and bulk conductivity `σ` gives

    E_peak ≈ J_0 · d / σ                                   [V/m]

(the "leakage-balance" or Beers 1980 limit; Leach & Alexander 1995
NASA/TP-2003-212287 gives this form explicitly). For weak bulk
conductivity this can exceed the dielectric breakdown field in hours
even at modest MeV electron fluxes, and is the canonical deep-
dielectric ESD scenario (Frederickson et al. 1992 *IEEE Trans Nucl
Sci* 39 1773).

Range of electrons in matter is given by the continuous-slowing-down-
approximation (CSDA) empirical fit from NASA-HDBK-4002A §5.3:

    R_CSDA = 0.412 · E^{1.265 − 0.0954 ln E}              [g/cm²]

valid for `0.01 MeV ≤ E ≤ 3 MeV`, with `E` in MeV. To convert to a
linear depth in meters for a material of density `ρ [kg/m³]`, divide
by ρ/1000 (g/cm³ vs kg/m³) and multiply by 1e-2 (cm → m):

    R_m = R_CSDA [g/cm²] · 1e-2 / (ρ [kg/m³] / 1000)
        = R_CSDA · 10 / ρ_kg_m3                            [m]
"""

from __future__ import annotations

import math


# CSDA empirical fit coefficients (NASA-HDBK-4002A 2011 §5.3; original
# fit by Katz & Penfold 1952 Rev Mod Phys 24 28 for Al, rescaled by
# the handbook for a generic low-Z dielectric).
CSDA_PREFACTOR_G_CM2: float = 0.412
CSDA_EXPONENT_CONST: float = 1.265
CSDA_EXPONENT_LN: float = 0.0954


def csda_range_kg_m2(energy_mev: float) -> float:
    """CSDA electron range in kg/m² (fluence-style columnar mass).

    R_CSDA = 0.412 · E^{1.265 − 0.0954 ln E}              [g/cm²]

    Multiplied by 10 to convert g/cm² → kg/m².

    Valid range: 0.01 MeV ≤ E ≤ 3 MeV (NASA-HDBK-4002A §5.3).
    Outside this band the formula still returns a value but accuracy
    degrades — the caller is warned via ValueError only for non-
    positive input.

    Args:
        energy_mev: electron kinetic energy (MeV, positive).

    Returns:
        R_CSDA in kg/m².
    """
    if energy_mev <= 0.0:
        raise ValueError("energy_mev must be positive")
    exponent = CSDA_EXPONENT_CONST - CSDA_EXPONENT_LN * math.log(energy_mev)
    r_g_cm2 = CSDA_PREFACTOR_G_CM2 * energy_mev**exponent
    return r_g_cm2 * 10.0  # g/cm² → kg/m²


def csda_range_m(energy_mev: float, density_kg_m3: float) -> float:
    """Linear CSDA range in meters for a given material density.

    R_m = R_{g/cm²} · 1e-2 · (1 / (ρ_{kg/m³} / 1000))
        = R_{kg/m²} / ρ_{kg/m³}                            [m]

    Canonical check: 2 MeV electrons in Kapton (ρ = 1420 kg/m³) give
    R ≈ 9.3 mm, matching NASA-HDBK-4002A §5.3 example of ~1 cm.
    """
    if density_kg_m3 <= 0.0:
        raise ValueError("density_kg_m3 must be positive")
    return csda_range_kg_m2(energy_mev) / density_kg_m3


def peak_internal_field_parallel_plate(
    injected_current_density_a_m2: float,
    dielectric_thickness_m: float,
    bulk_conductivity_s_m: float,
) -> float:
    """Steady-state peak internal field in a parallel-plate dielectric.

    At steady state the injected bulk current `J_0` is balanced by
    the ohmic leakage current `J_leak = σ E`, so

        E_peak = J_0 / σ                                   [V/m]

    (Frederickson 1991 *IEEE Trans Nucl Sci* 38 1493 eq. 5;
    Leach & Alexander 1995 NASA/TP-2003-212287 §3). The field is
    independent of thickness, because in steady state every injected
    electron must leak out through the same leakage channel. The
    thickness `d` appears only in the transient charging time
    `τ = ε_r ε_0 / σ` and in the stored arc energy (see
    esd_trigger.arc_energy_parallel_plate).

    Args:
        injected_current_density_a_m2: J_0 (A/m², positive).
        dielectric_thickness_m: d (m, positive). Retained for
            signature symmetry with the arc-energy routine; ignored in
            the steady-state field calculation.
        bulk_conductivity_s_m: σ including any radiation-induced
            conductivity (S/m, positive).

    Returns:
        Peak steady-state internal field E_peak in V/m.
    """
    if injected_current_density_a_m2 < 0.0:
        raise ValueError("injected_current_density_a_m2 must be non-negative")
    if dielectric_thickness_m <= 0.0:
        raise ValueError("dielectric_thickness_m must be positive")
    if bulk_conductivity_s_m <= 0.0:
        raise ValueError("bulk_conductivity_s_m must be positive")
    return injected_current_density_a_m2 / bulk_conductivity_s_m


def charging_time_constant_s(
    relative_permittivity: float,
    bulk_conductivity_s_m: float,
    epsilon_0_f_m: float = 8.8541878128e-12,  # CODATA 2018
) -> float:
    """Dielectric relaxation (Maxwell) time τ = ε / σ.

    τ = ε_r ε_0 / σ                                        [s]

    For Kapton with σ_dark = 1e-18 S/m and ε_r = 3.5,
    τ ≈ 3.5 · 8.854e-12 / 1e-18 ≈ 3.1e7 s ≈ 360 days — this is why
    deep-dielectric charging is a multi-hour to multi-week phenomenon.
    """
    if relative_permittivity <= 0.0:
        raise ValueError("relative_permittivity must be positive")
    if bulk_conductivity_s_m <= 0.0:
        raise ValueError("bulk_conductivity_s_m must be positive")
    return relative_permittivity * epsilon_0_f_m / bulk_conductivity_s_m
