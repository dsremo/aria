"""Surface current balance (§4.1, §4.2 of D2 scope).

The equilibrium potential `φ_s` of an isolated conducting surface in a
plasma is set by ΣI(φ_s) = 0, summing the ambient electron and ion
currents (modulated by the potential), secondary-electron emission,
backscatter, and photoemission under sunlight. For a Maxwellian
plasma, the ambient electron current to a repelling (negative)
surface is

    J_e(φ) = e n_e v_{th,e}/4 · exp(eφ/k_B T_e)           (φ < 0)

with v_{th,e} = √(8 k_B T_e / π m_e) — Lai 2012 eq. 2.19. Ions arriving
at a negative surface are *accelerated* (orbital-motion-limited), and
at the thin-sheath Bohm limit the flux is fixed at the thermal
one-sided value:

    J_i ≈ e n_i (k_B T_i / 2π m_i)^{1/2}

Photoemission adds a *positive* leaving current J_ph that only fires
on the sunlit side; at 1 AU with typical spacecraft materials Lai 2012
Table 3.1 gives j_ph ≈ 2.0×10⁻⁵ A/m², and it scales as r⁻² with
heliocentric distance. In eclipse J_ph vanishes, and the frame can
charge very negative — the SCATHA-class kilovolt event.

References:
  - Lai, S.T. (2012) *Fundamentals of Spacecraft Charging* eqs. 2.19,
    2.21, 2.26, Table 3.1 (ISBN 978-0691129471).
  - Whipple, E.C. (1981) *Rep Prog Phys* 44 1197 (review of surface
    current balance).
  - Mullen et al. 1986 *J Spacecr Rockets* 23 593 (SCATHA eclipse
    benchmark).
"""

from __future__ import annotations

import math

from ..mhd_plasma.constants import PLASMA_CONSTANTS, PlasmaConstants


def _electron_thermal_speed(t_e_ev: float, constants: PlasmaConstants) -> float:
    """Mean electron thermal speed v̄ = √(8 k_B T_e / π m_e)."""
    t_e_joules = t_e_ev * constants.e_c
    return math.sqrt(8.0 * t_e_joules / (math.pi * constants.m_e_kg))


def ambient_electron_current_density(
    electron_density_m3: float,
    electron_temperature_ev: float,
    surface_potential_v: float,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Maxwellian electron current density to a surface at φ_s.

    For `φ_s ≤ 0` (electrons repelled):
        J_e = (1/4) e n_e v̄_e · exp(eφ_s / k_B T_e)      [A/m²]
    For `φ_s > 0` (electrons attracted, orbital-motion-limited sphere
    or thin sheath planar):
        J_e = (1/4) e n_e v̄_e · (1 + eφ_s / k_B T_e)      [A/m²]

    Both cases follow Lai 2012 eq. 2.19–2.21. Sign convention: positive
    means electrons flow *to* the surface (conventional current
    *leaving* the surface, but here we return the carrier flux times e
    without further sign manipulation — the caller reconciles signs in
    the balance).
    """
    if electron_density_m3 <= 0.0:
        raise ValueError("electron_density_m3 must be positive")
    if electron_temperature_ev <= 0.0:
        raise ValueError("electron_temperature_ev must be positive")
    v_bar = _electron_thermal_speed(electron_temperature_ev, constants)
    j_thermal = 0.25 * constants.e_c * electron_density_m3 * v_bar
    phi_over_t = surface_potential_v / electron_temperature_ev
    if surface_potential_v <= 0.0:
        return j_thermal * math.exp(phi_over_t)
    return j_thermal * (1.0 + phi_over_t)


def ambient_ion_current_density(
    ion_density_m3: float,
    ion_temperature_ev: float,
    ion_mass_kg: float,
    surface_potential_v: float,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Thermal ion current density to a surface at φ_s.

    J_i = (1/4) e n_i v̄_i with v̄_i = √(8 k_B T_i / π m_i). For
    strongly negative φ_s the ions are attracted and the current is
    enhanced by the orbital-motion-limited planar factor
    `(1 − eφ_s / k_B T_i)` (Lai 2012 eq. 2.21). For φ_s > 0 (ions
    repelled) the exponential Boltzmann factor applies.
    """
    if ion_density_m3 <= 0.0:
        raise ValueError("ion_density_m3 must be positive")
    if ion_temperature_ev <= 0.0:
        raise ValueError("ion_temperature_ev must be positive")
    if ion_mass_kg <= 0.0:
        raise ValueError("ion_mass_kg must be positive")
    t_i_joules = ion_temperature_ev * constants.e_c
    v_bar = math.sqrt(8.0 * t_i_joules / (math.pi * ion_mass_kg))
    j_thermal = 0.25 * constants.e_c * ion_density_m3 * v_bar
    phi_over_t = surface_potential_v / ion_temperature_ev
    if surface_potential_v < 0.0:
        return j_thermal * (1.0 - phi_over_t)
    return j_thermal * math.exp(-phi_over_t)


# Photoemission current density at 1 AU averaged over typical
# spacecraft materials (Al, Au, indium-tin-oxide). Lai 2012 Table 3.1.
PHOTOEMISSION_1AU_A_M2: float = 2.0e-5


def photoemission_current_density(
    sunlit: bool,
    solar_distance_au: float = 1.0,
    j_ph_1au_a_m2: float = PHOTOEMISSION_1AU_A_M2,
) -> float:
    """Photoemission current density leaving a sunlit surface.

    J_ph = j_ph(1 AU) · (1 AU / r)²                       [A/m²]

    Returns zero for shadowed surfaces. The 1 AU value comes from
    Lai 2012 Table 3.1 (ISBN 978-0691129471).
    """
    if solar_distance_au <= 0.0:
        raise ValueError("solar_distance_au must be positive")
    if not sunlit:
        return 0.0
    return j_ph_1au_a_m2 / (solar_distance_au * solar_distance_au)


def worst_case_eclipse_potential(
    electron_temperature_ev: float,
    effective_se_yield: float = 0.3,
    ion_mass_kg: float | None = None,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
) -> float:
    """Worst-case eclipse equilibrium potential (Lai 2012 §4.1).

    When photoemission vanishes (eclipse) and the secondary-electron
    yield δ_eff < 1, the current-balance has a closed-form negative
    root:

        φ_s ≈ − (k_B T_e / e) · ln( (1 − δ_eff) · √(m_i / (2π m_e)) )

    which for T_e = 10 keV and δ_eff = 0.3 with m_i = m_p reproduces
    the historical SCATHA -20 kV level (Mullen et al. 1986
    *J Spacecr Rockets* 23 593).

    Args:
        electron_temperature_ev: T_e (eV, positive).
        effective_se_yield: δ_eff (dimensionless, 0 ≤ δ_eff < 1).
            δ_eff ≥ 1 means net positive yield and the formula no
            longer applies (the surface charges positive); this case
            raises ValueError.
        ion_mass_kg: m_i. Defaults to proton mass.
        constants: override for testing.

    Returns:
        φ_s in volts (negative).
    """
    if electron_temperature_ev <= 0.0:
        raise ValueError("electron_temperature_ev must be positive")
    if not (0.0 <= effective_se_yield < 1.0):
        raise ValueError("effective_se_yield must be in [0, 1)")
    m_i = ion_mass_kg if ion_mass_kg is not None else constants.m_p_kg
    mass_ratio = m_i / (2.0 * math.pi * constants.m_e_kg)
    factor = (1.0 - effective_se_yield) * math.sqrt(mass_ratio)
    return -electron_temperature_ev * math.log(factor)


def equilibrium_surface_potential(
    electron_density_m3: float,
    electron_temperature_ev: float,
    ion_density_m3: float,
    ion_temperature_ev: float,
    ion_mass_kg: float,
    sunlit: bool,
    solar_distance_au: float = 1.0,
    effective_se_yield: float = 0.0,
    j_ph_1au_a_m2: float = PHOTOEMISSION_1AU_A_M2,
    constants: PlasmaConstants = PLASMA_CONSTANTS,
    tol_a_m2: float = 1.0e-12,
    max_iter: int = 200,
) -> float:
    """Solve ΣJ(φ_s) = 0 by bisection (Lai 2012 eq. 2.26).

    The residual

        R(φ) = (1 − δ_eff) J_e(φ) − J_i(φ) − J_ph(φ)

    is monotone in φ for the Maxwellian model (attracted species'
    currents grow with their attractive potential, repelled currents
    exponentially decay). Bisection on `R(φ) = 0` on
    `[−100 kV, +100 V]` is unconditionally convergent.

    Args:
        electron_density_m3: n_e (m⁻³).
        electron_temperature_ev: T_e (eV).
        ion_density_m3: n_i (m⁻³).
        ion_temperature_ev: T_i (eV).
        ion_mass_kg: m_i (kg).
        sunlit: True iff the surface sees the Sun.
        solar_distance_au: heliocentric distance (AU), default 1.
        effective_se_yield: δ_eff for the surface (0 by default — no
            secondaries).
        j_ph_1au_a_m2: override photoemission reference value.
        constants: override for testing.
        tol_a_m2: residual tolerance (A/m²).
        max_iter: bisection cap.

    Returns:
        φ_s in volts.
    """
    j_ph = photoemission_current_density(sunlit, solar_distance_au, j_ph_1au_a_m2)

    def residual(phi: float) -> float:
        j_e = ambient_electron_current_density(
            electron_density_m3, electron_temperature_ev, phi, constants
        )
        j_i = ambient_ion_current_density(
            ion_density_m3, ion_temperature_ev, ion_mass_kg, phi, constants
        )
        # Positive residual means too much electron influx; surface
        # becomes more negative.
        return (1.0 - effective_se_yield) * j_e - j_i - j_ph

    lo = -1.0e5  # −100 kV
    hi = 1.0e3  # +1 kV
    r_lo = residual(lo)
    r_hi = residual(hi)
    if r_lo * r_hi > 0.0:
        # Degenerate: both ends have the same sign. Fall back to the
        # end with smaller magnitude (saturation case).
        return lo if abs(r_lo) < abs(r_hi) else hi

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        r_mid = residual(mid)
        if abs(r_mid) < tol_a_m2:
            return mid
        if r_mid * r_lo < 0.0:
            hi = mid
            r_hi = r_mid
        else:
            lo = mid
            r_lo = r_mid
        if hi - lo < 1.0e-6:
            return 0.5 * (lo + hi)
    return 0.5 * (lo + hi)
