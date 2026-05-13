"""Galactic cosmic ray source and Cucinotta 2014 shielded-dose model
(§4.6 of docs/pods/E2_neutron_transport.md).

GCR particles (mostly protons, 10-15 % helium, ~1 % HZE) stream through
the solar system at a flux that is modulated by the heliospheric
magnetic field. At solar minimum the field is weak and the GCR flux
inside 1 AU peaks; at solar maximum the field is strong and the flux
is suppressed by a factor of ~2.

The Cucinotta 2014 reference model (NASA/TP-2013-217375, eq. 3-1)
parameterises the local interstellar spectrum times a solar-modulation
factor:

    dΦ/dE(E, Z, A, φ_SM) = A_Z (E + m_p c²)^(−γ) f_mod(E, φ_SM)  [1/(cm²·s·MeV)]

with the solar modulation potential φ_SM ≈ 450 MV at minimum and
≈ 1000 MV at maximum (Usoskin 2017 Living Rev Solar Physics 14 3).

The high-level numbers that matter for ARIA and that this module
reproduces from first principles:

  - Integral proton flux above 10 MeV at 1 AU solar min:
        Φ_p(>10 MeV) ≈ 4 p/cm²/s
    (Cucinotta 2014 Fig. 3-1)
  - Unshielded crew dose-equivalent at 1 AU solar min:
        ~420 mSv/yr = 0.42 Sv/yr
    (ACE/CRIS data as reduced in Cucinotta 2014)
  - Shielded dose with 20 g/cm² Al:
        ~0.65 × unshielded dose reduction ceiling
    (the "Cucinotta 65 %" floor used by existing ARIA code)

The full differential spectrum integration requires ENDF cross
sections and nuclear interactions that are deferred. This module
implements the engineering model ARIA already relies on, with every
constant cited.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────────────
#  Canonical constants
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Cucinotta2014Constants:
    """Constants from Cucinotta 2014 NASA/TP-2013-217375 and related."""

    # Integral proton flux above 10 MeV at 1 AU solar min.
    # Cucinotta 2014 Figure 3-1 intercept (proton component only).
    proton_flux_gt_10_mev_1au_solar_min_pcm2s: float = 4.0

    # Solar modulation potential range (Usoskin 2017 LRSP 14 3).
    phi_sm_solar_min_MV: float = 450.0
    phi_sm_solar_max_MV: float = 1000.0

    # Unshielded dose equivalent (Sv/yr) at 1 AU solar min for free
    # space and an unshielded crew. This is the number that appears
    # throughout the existing ARIA code (`interstellar.py` line 277)
    # and is traceable to ACE/CRIS data as summarised by Cucinotta
    # 2014 Table 5-1.
    gcr_dose_sv_yr_solar_min: float = 0.42

    # Realistic dose-reduction ceiling with passive + active shielding
    # combined. Cucinotta 2014 §5.4 discusses the "practical 65 %"
    # floor imposed by the stiff HZE component that cannot be blocked
    # by feasible shielding mass. Active deflection of the charged
    # component can improve this marginally. This is the same number
    # the ARIA `advanced_systems.py` round-14 fix uses.
    max_realistic_dose_reduction: float = 0.65


CUCINOTTA_2014_CONSTANTS: Cucinotta2014Constants = Cucinotta2014Constants()

# Explicit module-level re-exports for convenience.
GCR_PROTON_FLUX_1AU_SOLAR_MIN: float = (
    CUCINOTTA_2014_CONSTANTS.proton_flux_gt_10_mev_1au_solar_min_pcm2s
)  # p/cm²/s above 10 MeV (Cucinotta 2014 Fig. 3-1)

CUCINOTTA_2014_GCR_DOSE_SV_YR: float = (
    CUCINOTTA_2014_CONSTANTS.gcr_dose_sv_yr_solar_min
)  # Sv/yr unshielded solar min (Cucinotta 2014 Table 5-1)


# ──────────────────────────────────────────────────────────────────────
#  Solar modulation
# ──────────────────────────────────────────────────────────────────────


def solar_modulation_exp_factor(
    energy_mev: float, phi_sm_mv: float
) -> float:
    """Cucinotta 2014 simplified roll-off factor `exp(−φ_SM / E)` at
    low energy.

    This is a one-term toy approximation (not the full Ruffolo
    force-field transport equation Ruffolo 1995 ApJ 442 861); it
    captures the qualitative fact that low-energy GCR is suppressed
    when the heliospheric field is strong (large φ_SM). Used only
    for illustrative scaling in the test suite; the Cucinotta 2014
    full model is a differential-equation integration that this
    module does not implement in the P0 subset.

    Args:
        energy_mev: kinetic energy per nucleon (MeV/nucleon).
        phi_sm_mv: solar modulation potential (MV).

    Returns:
        Dimensionless suppression factor in (0, 1].
    """
    if energy_mev <= 0.0:
        raise ValueError("energy_mev must be positive")
    if phi_sm_mv < 0.0:
        raise ValueError("phi_sm_mv must be non-negative")
    return math.exp(-phi_sm_mv / energy_mev)


# ──────────────────────────────────────────────────────────────────────
#  Integral flux and annual dose
# ──────────────────────────────────────────────────────────────────────


def gcr_total_proton_flux(
    phi_sm_mv: float = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_min_MV,
) -> float:
    """Integral GCR proton flux above 10 MeV at 1 AU (p/cm²/s).

    At solar minimum the flux is anchored at 4 p/cm²/s per Cucinotta
    2014 Fig. 3-1. At solar maximum the suppression factor is ~0.5
    from Usoskin 2017 LRSP 14 3; we linearly interpolate between
    the two canonical values by modulation potential.

    Args:
        phi_sm_mv: solar modulation potential (MV). Default: solar min.

    Returns:
        Φ_p(>10 MeV) in protons / cm² / s.
    """
    if phi_sm_mv < 0.0:
        raise ValueError("phi_sm_mv must be non-negative")
    phi_min = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_min_MV
    phi_max = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_max_MV
    flux_min = GCR_PROTON_FLUX_1AU_SOLAR_MIN
    flux_max = 0.5 * flux_min  # Usoskin 2017 LRSP 14 3
    if phi_sm_mv <= phi_min:
        return flux_min
    if phi_sm_mv >= phi_max:
        return flux_max
    # Linear interpolation in modulation potential.
    t = (phi_sm_mv - phi_min) / (phi_max - phi_min)
    return flux_min + t * (flux_max - flux_min)


def gcr_annual_unshielded_dose(
    phi_sm_mv: float = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_min_MV,
) -> float:
    """Unshielded annual crew dose equivalent (Sv/yr) at 1 AU.

    Linearly interpolates between 0.42 Sv/yr at solar minimum and
    0.21 Sv/yr at solar maximum (Cucinotta 2014 Table 5-1; the solar
    max number is roughly half the solar min value for the full
    GCR+HZE spectrum integrated through tissue).

    Args:
        phi_sm_mv: solar modulation potential (MV).

    Returns:
        Annual dose equivalent H in Sv/yr.
    """
    if phi_sm_mv < 0.0:
        raise ValueError("phi_sm_mv must be non-negative")
    dose_min_solar_min = CUCINOTTA_2014_GCR_DOSE_SV_YR  # 0.42
    dose_min_solar_max = 0.5 * dose_min_solar_min  # ~0.21
    phi_min = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_min_MV
    phi_max = CUCINOTTA_2014_CONSTANTS.phi_sm_solar_max_MV
    if phi_sm_mv <= phi_min:
        return dose_min_solar_min
    if phi_sm_mv >= phi_max:
        return dose_min_solar_max
    t = (phi_sm_mv - phi_min) / (phi_max - phi_min)
    return dose_min_solar_min + t * (dose_min_solar_max - dose_min_solar_min)


def cucinotta_shielded_dose(
    unshielded_dose_sv_yr: float,
    shield_depth_g_cm2: float,
) -> float:
    """Shielded dose equivalent given aluminum areal density.

    Engineering model used by ARIA in `advanced_systems.py`:
      - At 0 g/cm² the dose equals the unshielded baseline.
      - As shield depth grows the dose asymptotes to the realistic
        Cucinotta 2014 floor of `(1 − 0.65) × unshielded = 0.35 ×
        unshielded`, reflecting the stiff HZE fragment spectrum that
        cannot be blocked by any feasible passive shield.
      - The decay constant between these two values is ~10 g/cm² Al
        (Cucinotta 2014 Fig. 5-2 effective attenuation for the soft
        component).

    The closed form is
        H(x) = H_∞ + (H_0 − H_∞) · exp(−x / λ)
    with H_0 = unshielded, H_∞ = 0.35 H_0, λ = 10 g/cm².

    Args:
        unshielded_dose_sv_yr: free-space dose equivalent at this
            heliocentric position (Sv/yr).
        shield_depth_g_cm2: passive shield areal density (g/cm²).
            Zero gives the unshielded value.

    Returns:
        Shielded annual dose (Sv/yr).
    """
    if unshielded_dose_sv_yr < 0.0:
        raise ValueError("unshielded_dose_sv_yr must be non-negative")
    if shield_depth_g_cm2 < 0.0:
        raise ValueError("shield_depth_g_cm2 must be non-negative")
    floor_fraction = 1.0 - CUCINOTTA_2014_CONSTANTS.max_realistic_dose_reduction
    lambda_g_cm2 = 10.0  # Cucinotta 2014 Fig. 5-2 soft-component scale
    h_inf = floor_fraction * unshielded_dose_sv_yr
    return h_inf + (unshielded_dose_sv_yr - h_inf) * math.exp(
        -shield_depth_g_cm2 / lambda_g_cm2
    )
