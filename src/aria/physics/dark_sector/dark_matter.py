"""Dark-matter drag and Λ cosmological acceleration (§4.1, §4.2 M1).

M1 is a bookkeeping pod: it propagates *upper bounds* from null
results into an acceleration budget so downstream consumers can
confirm that residual perturbations sit below mission sensitivity.
No detection is claimed; the output is the XENONnT / PandaX-4T
worst-case that would still be consistent with published data.

References:
  - Aprile et al. 2023 *PRL* 131 041003 — XENONnT σ_SI.
  - Read 2014 *J Phys G* 41 063101 — local DM density.
  - Bland-Hawthorn & Gerhard 2016 *ARA&A* 54 529 — v_sun in halo.
  - Planck Collaboration 2020 *A&A* 641 A6 — cosmological Λ.
  - Aprile 2023 §1.3 formulation of σ_SI upper bound as worst case.
"""

from __future__ import annotations

import math

from .bounds_db import (
    DARK_MATTER_DENSITY_READ_2014_KG_M3,
    DARK_MATTER_LOCAL_VELOCITY_M_S,
    LAMBDA_COSMO_M2,
    SPEED_OF_LIGHT_M_S,
    XENONNT_SIGMA_SI_30GEV_M2,
)


def dark_matter_drag_upper_bound(
    ship_mass_kg: float,
    ship_velocity_through_halo_m_s: float = DARK_MATTER_LOCAL_VELOCITY_M_S,
    dm_density_kg_m3: float = DARK_MATTER_DENSITY_READ_2014_KG_M3,
    cross_section_m2_per_nucleon: float = XENONNT_SIGMA_SI_30GEV_M2,
    wimp_mass_gev: float = 30.0,
) -> float:
    """XENONnT-consistent worst-case DM drag acceleration on the ship.

    Scope-note §4.4 worked-example derivation, corrected:

        F = N_nucleons · σ · n_DM · v_rel · (m_DM · v_rel)
          = N_nucleons · σ · ρ_DM · v_rel²                     [N]

    (collision rate per nucleon × momentum per interaction), so

        |a|_max = σ · ρ_DM · v_rel² · N_nucleons / M_ship      [m/s²]

    with `N_nucleons ≈ M_ship · N_A · 1000` (1 mole of nucleons per
    gram of ordinary matter). Note that the WIMP mass cancels in the
    final expression because n_DM · m_DM = ρ_DM.

    This function returns the 90 % CL upper bound; any real DM drag
    is *strictly below* this number given current null-result
    constraints.

    Args:
        ship_mass_kg: total ship mass (kg, positive).
        ship_velocity_through_halo_m_s: |v_ship| relative to the
            galactic rest frame (default ≈ 232 km/s, Bland-Hawthorn
            & Gerhard 2016).
        dm_density_kg_m3: ρ_DM (default Read 2014 0.4 GeV/cm³ ≈
            7.13e-22 kg/m³).
        cross_section_m2_per_nucleon: σ_SI per nucleon (default
            XENONnT 2023 30 GeV bound 2.6×10⁻⁵¹ m²).
        wimp_mass_gev: assumed WIMP mass in GeV/c² (default 30).

    Returns:
        |a|_max in m/s² (non-negative).
    """
    if ship_mass_kg <= 0.0:
        raise ValueError("ship_mass_kg must be positive")
    if ship_velocity_through_halo_m_s < 0.0:
        raise ValueError("ship_velocity_through_halo_m_s must be non-negative")
    if dm_density_kg_m3 <= 0.0:
        raise ValueError("dm_density_kg_m3 must be positive")
    if cross_section_m2_per_nucleon < 0.0:
        raise ValueError("cross_section_m2_per_nucleon must be non-negative")
    if wimp_mass_gev <= 0.0:
        raise ValueError("wimp_mass_gev must be positive")

    # WIMP mass cancels in the final expression but is retained as
    # an explicit parameter so callers can document the experimental
    # bound they used (σ_SI depends on m_DM).
    _ = wimp_mass_gev

    # Number of nucleons in ship ≈ M_ship · N_A · 1000
    # (1 kg = 1000 g, ≈ 1 mole of nucleons per gram of ordinary matter).
    n_a = 6.02214076e23
    n_nucleons = ship_mass_kg * 1000.0 * n_a

    v = ship_velocity_through_halo_m_s
    return (
        cross_section_m2_per_nucleon
        * dm_density_kg_m3
        * v * v
        * n_nucleons
        / ship_mass_kg
    )


def cosmological_lambda_acceleration(
    separation_m: float,
    lambda_m2: float = LAMBDA_COSMO_M2,
    c_m_s: float = SPEED_OF_LIGHT_M_S,
) -> float:
    """de Sitter acceleration a_Λ = (Λ c² / 3) · d                [m/s²].

    From the Schwarzschild-de Sitter metric the tidal acceleration
    between two comoving points separated by `d` in a Λ-dominated
    universe is (Carroll 2004 *Spacetime and Geometry* eq. 8.55):

        a_Λ = (Λ c² / 3) · d                                  [m/s²]

    Canonical check: d = 100 Mpc ≈ 3.086×10²⁴ m with Planck 2018 Λ
    gives |a_Λ| ≈ 3.4×10⁻²⁴ m/s² (scope note §4.2 example).
    """
    if separation_m < 0.0:
        raise ValueError("separation_m must be non-negative")
    if lambda_m2 <= 0.0:
        raise ValueError("lambda_m2 must be positive")
    return (lambda_m2 * c_m_s * c_m_s / 3.0) * separation_m


def lambda_position_drift_over_transit(
    separation_m: float,
    transit_time_s: float,
    lambda_m2: float = LAMBDA_COSMO_M2,
) -> float:
    """Ballistic Δx ≈ (1/2) a_Λ · t² accumulated drift [m].

    Only the leading 1/2 a t² term is included; for
    non-cosmological transits this is an overestimate (the de Sitter
    expansion rate acts as a *tidal* perturbation, not a constant
    acceleration — see Carroll 2004 §8.4). For the M1 bookkeeping
    role the leading term is the conservative worst case.
    """
    if transit_time_s < 0.0:
        raise ValueError("transit_time_s must be non-negative")
    a = cosmological_lambda_acceleration(separation_m, lambda_m2)
    return 0.5 * a * transit_time_s * transit_time_s
