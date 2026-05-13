"""Rankine-Hugoniot jump conditions + linear U_s-u_p Hugoniot
(§4.2-§4.3 of F4 scope).

A steady planar shock moving into an unshocked medium satisfies the
Rankine-Hugoniot jump conditions (Meyers 1994 *Dynamic Behavior of
Materials* §4, ISBN 978-0471582625):

    mass:     ρ_0 U_s = ρ_1 (U_s − u_p)
    momentum: p_1 − p_0 = ρ_0 U_s u_p
    energy:   e_1 − e_0 = (1/2)(p_1 + p_0)(1/ρ_0 − 1/ρ_1)

where:
    U_s = shock velocity (m/s)
    u_p = particle velocity behind the shock (m/s)
    ρ_0, ρ_1 = unshocked and shocked density
    p_0, p_1 = unshocked and shocked pressure

For most metals over the 0.1-100 GPa range, the shock velocity is
very well described by a linear Hugoniot in the particle velocity
(Marsh 1980 *LASL Shock Hugoniot Data*, ISBN 978-0520040083):

    U_s = c_0 + s · u_p                                   [m/s]

with `c_0` the bulk sound speed at the initial state and `s` a
dimensionless slope. Canonical values for aerospace alloys:

  - Al 2024-T3: c_0 = 5380 m/s, s = 1.338 (Marsh 1980 p. 14)
  - Ti-6Al-4V:  c_0 = 4780 m/s, s = 1.017 (Marsh 1980)
  - Iron:       c_0 = 3630 m/s, s = 1.79  (Marsh 1980)

From the momentum jump with `p_0 = 0` (unshocked at ambient),

    p_H = ρ_0 U_s u_p                                     [Pa]

is the Hugoniot peak pressure at the particle speed `u_p`. The
shocked density follows from the mass jump:

    ρ_1 = ρ_0 · U_s / (U_s − u_p)                         [kg/m³]

For the normal-incidence symmetric impact of two identical
materials at relative velocity `v`, the particle velocity in each
body is `u_p = v/2` (impedance matching) and the peak pressure is

    p_H = ρ_0 (c_0 + s v/2)(v/2)                          [Pa]

For a 10 km/s Al-on-Al impact this gives `p_H ≈ 140 GPa`, well
above the von Mises yield stress of any engineering alloy — the
hydrodynamic regime.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HugoniotMaterial:
    """Linear U_s-u_p Hugoniot constants for a homogeneous material.

    Attributes:
        name: identifier.
        c_0_m_s: bulk sound speed at initial state (m/s).
        s: dimensionless slope of U_s vs u_p.
        gamma_0: Grüneisen parameter at initial state (dimensionless).
        rho_0_kg_m3: initial density (kg/m³).
        source: citation string.
    """

    name: str
    c_0_m_s: float
    s: float
    gamma_0: float
    rho_0_kg_m3: float
    source: str


# ──────────────────────────────────────────────────────────────────────
#  Canonical aerospace alloys (Marsh 1980 LASL Shock Hugoniot Data)
# ──────────────────────────────────────────────────────────────────────

HUGONIOT_AL_2024_T3: HugoniotMaterial = HugoniotMaterial(
    name="Al 2024-T3",
    c_0_m_s=5380.0,  # Marsh 1980 p. 14
    s=1.338,  # Marsh 1980 p. 14
    gamma_0=2.0,  # Marsh 1980 p. 14
    rho_0_kg_m3=2785.0,  # Marsh 1980 p. 14
    source="Marsh 1980 LASL Shock Hugoniot Data p. 14 (Al 2024-T3)",
)

HUGONIOT_TI_6AL_4V: HugoniotMaterial = HugoniotMaterial(
    name="Ti-6Al-4V",
    c_0_m_s=4780.0,  # Marsh 1980
    s=1.017,  # Marsh 1980
    gamma_0=1.23,  # Marsh 1980
    rho_0_kg_m3=4430.0,  # Marsh 1980
    source="Marsh 1980 LASL Shock Hugoniot Data (Ti-6Al-4V)",
)


def hugoniot_shock_velocity(
    particle_velocity_m_s: float, material: HugoniotMaterial
) -> float:
    """Linear Hugoniot shock velocity `U_s = c_0 + s · u_p` [m/s].

    Args:
        particle_velocity_m_s: u_p in m/s (non-negative).
        material: HugoniotMaterial with `(c_0, s)` populated.

    Returns:
        Shock speed `U_s` in m/s.
    """
    if particle_velocity_m_s < 0.0:
        raise ValueError("particle_velocity_m_s must be non-negative")
    return material.c_0_m_s + material.s * particle_velocity_m_s


def hugoniot_peak_pressure(
    particle_velocity_m_s: float, material: HugoniotMaterial
) -> float:
    """Rankine-Hugoniot peak pressure `p_H = ρ_0 · U_s · u_p` [Pa].

    Derived from the momentum jump with `p_0 = 0`:

        p_1 − p_0 = ρ_0 U_s u_p

    i.e. the shock pressure rises from ambient (0) to p_H as the
    front sweeps through. For a symmetric impact at relative
    velocity v, the caller should pass u_p = v/2 (impedance matching).

    Args:
        particle_velocity_m_s: u_p in m/s.
        material: HugoniotMaterial.

    Returns:
        p_H in Pa.
    """
    if particle_velocity_m_s < 0.0:
        raise ValueError("particle_velocity_m_s must be non-negative")
    u_s = hugoniot_shock_velocity(particle_velocity_m_s, material)
    return material.rho_0_kg_m3 * u_s * particle_velocity_m_s


def hugoniot_peak_density(
    particle_velocity_m_s: float, material: HugoniotMaterial
) -> float:
    """Shocked density from the Rankine-Hugoniot mass jump.

    ρ_1 = ρ_0 · U_s / (U_s − u_p)                         [kg/m³]

    The compression `ρ_1 / ρ_0` is bounded above by `(s+1)/(s−0)` in
    the strong-shock limit, giving an asymptotic compression ratio of
    about 4 for aerospace alloys — a well-known feature of shocked
    metals (Meyers 1994 eq. 4.31).
    """
    if particle_velocity_m_s < 0.0:
        raise ValueError("particle_velocity_m_s must be non-negative")
    u_s = hugoniot_shock_velocity(particle_velocity_m_s, material)
    denom = u_s - particle_velocity_m_s
    if denom <= 0.0:
        raise ValueError(
            "particle velocity equals or exceeds shock velocity — "
            "the Hugoniot linearisation has broken down at this u_p"
        )
    return material.rho_0_kg_m3 * u_s / denom
