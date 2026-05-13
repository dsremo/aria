"""Oberth effect — kinetic-energy gain from a burn deep in a gravity well
(§4.3 of docs/pods/A3_oberth_departure.md).

Consider a ship on a highly eccentric orbit about a central body with
gravitational parameter `μ`, perihelion `r_p`, and speed at perihelion
`v_p` (from vis-viva). An impulsive Δv applied parallel to `v_p` at
perihelion changes the kinetic energy by

    ΔKE = (1/2) m [(v_p + Δv)² − v_p²]
        = m v_p Δv + (1/2) m Δv²                   [J]

The same burn "at infinity" (where v ≈ 0) gives only (1/2) m Δv². The
ratio — the Oberth multiplier — is

    ΔKE(r_p) / ΔKE(∞) = 1 + 2 v_p / Δv             [dimensionless]

The post-burn hyperbolic excess is obtained from energy conservation
(v_∞² / 2 = v² / 2 − μ/r_p):

    v_∞² = (v_p + Δv)² − 2 μ / r_p                 [m²/s²]

For Δv ≪ v_p this linearises to

    v_∞² ≈ v_∞,initial² + 2 v_p Δv                 [m²/s²]

so the gain in v_∞² scales with v_p, not with Δv alone — the canonical
Oberth result.

Primary source: Oberth 1929 *Wege zur Raumschiffahrt* (Oldenbourg,
reprinted 1984 ISBN 978-3486230505). Modern derivation: Vallado 4th ed
§6.3 (ISBN 978-1881883180); Curtis 3rd ed §8.10 (ISBN 978-0080977478).
"""

from __future__ import annotations

import math


def oberth_multiplier(v_perihelion_m_s: float, burn_delta_v_m_s: float) -> float:
    """Oberth multiplier 1 + 2 v_p / Δv (dimensionless).

    The ratio of the kinetic-energy gain from a Δv burn at perihelion
    speed `v_p` to the KE gain from the same Δv at infinity (v ≈ 0).

    Raises:
        ValueError: if `v_perihelion_m_s < 0` or `burn_delta_v_m_s <= 0`.
    """
    if v_perihelion_m_s < 0.0:
        raise ValueError("v_perihelion_m_s must be non-negative")
    if burn_delta_v_m_s <= 0.0:
        raise ValueError("burn_delta_v_m_s must be positive")
    return 1.0 + 2.0 * v_perihelion_m_s / burn_delta_v_m_s


def oberth_v_infinity_after_burn(
    v_perihelion_m_s: float,
    burn_delta_v_m_s: float,
    perihelion_radius_m: float,
    gravitational_parameter_m3_s2: float,
) -> float:
    """Hyperbolic excess speed `v_∞` after an impulsive parallel burn at
    perihelion.

    v_∞² = (v_p + Δv)² − 2 μ / r_p

    Raises:
        ValueError: if the post-burn energy is still bound (`v_∞² < 0`).
    """
    if perihelion_radius_m <= 0.0:
        raise ValueError("perihelion_radius_m must be positive")
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    post_burn_speed = v_perihelion_m_s + burn_delta_v_m_s
    v_inf_sq = (
        post_burn_speed * post_burn_speed
        - 2.0 * gravitational_parameter_m3_s2 / perihelion_radius_m
    )
    if v_inf_sq < 0.0:
        raise ValueError(
            "post-burn orbit is still bound (v_inf² < 0): need a larger "
            "burn or a smaller perihelion"
        )
    return math.sqrt(v_inf_sq)


def oberth_v_infinity_gain_squared(
    v_perihelion_m_s: float, burn_delta_v_m_s: float
) -> float:
    """Leading-order gain in v_∞² from an Oberth burn at perihelion.

    Derived by expanding the exact expression `(v_p + Δv)² − 2μ/r_p`
    and subtracting the pre-burn `v_∞_initial² = v_p² − 2μ/r_p`:

        Δ(v_∞²) = 2 v_p Δv + Δv²                    [m²/s²]

    For Δv ≪ v_p the leading term is `2 v_p Δv`. This function returns
    the exact `2 v_p Δv + Δv²` sum (units m²/s²). Positive by construction.
    """
    if v_perihelion_m_s < 0.0:
        raise ValueError("v_perihelion_m_s must be non-negative")
    if burn_delta_v_m_s <= 0.0:
        raise ValueError("burn_delta_v_m_s must be positive")
    return 2.0 * v_perihelion_m_s * burn_delta_v_m_s + burn_delta_v_m_s * burn_delta_v_m_s
