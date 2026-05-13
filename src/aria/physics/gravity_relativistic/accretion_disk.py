"""R42 §2.5 — accretion-disk physics (Shakura-Sunyaev + ADAF + BZ).

For ARIA's deep-sky / generation-ship scenarios any close-approach
black hole (Sgr A*, M87*) shines through accretion.  This module gives
the radial temperature profile + bolometric luminosity bounds for the
two accretion regimes (thin-disk + advection-dominated) plus the
Blandford-Znajek (1977) jet-luminosity envelope so a navigation budget
can include radiation pressure / spallation dose around active BHs.

Equations
---------

Shakura-Sunyaev 1973 thin-disk midplane temperature:

    T(r) = [ 3 G M Ṁ / (8 π σ r³) · (1 − √(r_in / r)) ]^(1/4)

Bolometric luminosity = η Ṁ c²  with η ≈ 0.06 for Schwarzschild
(MTW §22), η ≈ 0.42 for max-spin Kerr (Bardeen 1970).

Narayan-Yi ADAF (advection-dominated; m_dot << Eddington):

    L_ADAF / L_Edd ≈ (m_dot / m_dot_crit)²  for m_dot < m_dot_crit ≈ 0.1

Blandford-Znajek 1977 jet luminosity envelope:

    L_BZ ≈ B² r_h² c · (a/M)²
         ≤ Ω_h² M² c³ / G    (with Ω_h ≤ c / (2 G M / c²))

Reference:
    Shakura & Sunyaev 1973 A&A 24, 337;
    Narayan & Yi 1994 ApJ 428, L13;
    Blandford & Znajek 1977 MNRAS 179, 433;
    Frank-King-Raine 2002 *Accretion Power in Astrophysics* 3e.
"""

from __future__ import annotations

import math

from aria.physics.gravity_relativistic.strong_field import (
    G, C, M_SUN, isco_schwarzschild_m, isco_kerr_m,
    schwarzschild_radius_m, kerr_horizon_m,
)


SIGMA_SB = 5.670_374_419e-8   # Stefan-Boltzmann (W/m²·K⁴)


# ── Eddington limits ───────────────────────────────────────────


def eddington_luminosity_w(M_kg: float) -> float:
    """L_Edd = 4π G M m_p c / σ_T  (Frank-King-Raine Eq 1.5).

    σ_T (Thomson) and m_p are CODATA values; the result for one solar
    mass is 1.26e31 W.
    """
    M_PROTON = 1.672_621_924e-27   # kg
    SIGMA_T = 6.652_458_732e-29    # m²
    return 4.0 * math.pi * G * M_kg * M_PROTON * C / SIGMA_T


def eddington_mdot_kg_s(M_kg: float, efficiency: float = 0.10) -> float:
    """Ṁ_Edd = L_Edd / (η c²)."""
    if efficiency <= 0.0:
        return float("inf")
    return eddington_luminosity_w(M_kg) / (efficiency * C ** 2)


# ── Shakura-Sunyaev thin disk ──────────────────────────────────


def thin_disk_temperature_k(
    M_kg: float,
    mdot_kg_s: float,
    r_m: float,
    r_in_m: float = 0.0,
) -> float:
    """T(r) of a Shakura-Sunyaev thin disk.

    ``r_in_m`` defaults to the Schwarzschild ISCO if not supplied.
    Returns 0 K outside the integration window (r ≤ r_in)."""
    if r_in_m <= 0.0:
        r_in_m = isco_schwarzschild_m(M_kg)
    if r_m <= r_in_m:
        return 0.0
    inner = max(1.0 - math.sqrt(r_in_m / r_m), 0.0)
    flux = (3.0 * G * M_kg * mdot_kg_s) / (8.0 * math.pi * SIGMA_SB * r_m ** 3)
    flux *= inner
    return flux ** 0.25 if flux > 0 else 0.0


def thin_disk_luminosity_w(
    M_kg: float, mdot_kg_s: float, efficiency: float = 0.10,
) -> float:
    """L = η Ṁ c² — bolometric, valid for thin disks.  ``efficiency``
    is the standard 0.06 (Schwarzschild) → 0.42 (max-spin Kerr) range."""
    return efficiency * mdot_kg_s * C ** 2


# ── ADAF (advection-dominated accretion flow) ──────────────────


def adaf_luminosity_w(
    M_kg: float, mdot_kg_s: float, alpha_visc: float = 0.1,
    mdot_crit_frac: float = 0.1,
) -> float:
    """Narayan-Yi ADAF stub.  Returns L scaled as

        L = L_Edd · (m_dot / m_dot_crit)²   when  m_dot < m_dot_crit.

    Above ``m_dot_crit`` ADAF transitions to thin-disk; we cap at the
    thin-disk result for continuity.
    """
    L_edd = eddington_luminosity_w(M_kg)
    mdot_edd = eddington_mdot_kg_s(M_kg, efficiency=0.10)
    mdot_crit = mdot_crit_frac * mdot_edd
    if mdot_kg_s >= mdot_crit:
        return min(thin_disk_luminosity_w(M_kg, mdot_kg_s), L_edd)
    return L_edd * (mdot_kg_s / mdot_crit) ** 2


# ── Blandford-Znajek jet ───────────────────────────────────────


def blandford_znajek_luminosity_envelope_w(
    M_kg: float, a_dimensionless: float, B_field_t: float,
) -> float:
    """L_BZ envelope per Blandford-Znajek 1977.

    Closed form (MacDonald-Thorne 1982, Eq 5.6):

        L_BZ = (1/96 π) · ω_h² · B² · r_h⁴ · c

    Returns watts.  ``B_field_t`` is the magnetic field at the horizon
    in tesla.  Sets a hard upper bound on jet luminosity; for inputs
    that exceed L_Edd, the result is what the spin would *allow* even
    if accretion couldn't deliver it."""
    if not (0.0 <= a_dimensionless <= 1.0):
        raise ValueError("a* must be in [0, 1]")
    r_h = kerr_horizon_m(M_kg, a_dimensionless)
    omega_h = C * a_dimensionless / (2.0 * r_h) if r_h > 0 else 0.0
    return (
        (1.0 / (96.0 * math.pi))
        * omega_h ** 2
        * B_field_t ** 2
        * r_h ** 4
        * C
    )


def isco_inner_edge_m(M_kg: float, a_dimensionless: float = 0.0,
                     prograde: bool = True) -> float:
    """Convenience: the inner edge of the disk.  Default is Schwarzschild
    ISCO; pass ``a_dimensionless > 0`` for Kerr."""
    if a_dimensionless == 0.0:
        return isco_schwarzschild_m(M_kg)
    return isco_kerr_m(M_kg, a_dimensionless, prograde=prograde)
