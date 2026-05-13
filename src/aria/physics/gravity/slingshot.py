"""Full vector gravitational slingshot (§4.8 of docs/pods/A1_ephemeris.md).

The A3 `patched_conic.slingshot_delta_v` routine returns the scalar Δv
magnitude `2 v_∞ sin δ` for an aligned flyby. Here we do the full
3-D vector treatment needed by A1's patched-conic hand-off:

  1. Transform the ship velocity into the planet's rest frame:
         u_in = v_ship_helio − v_planet_helio            [m/s]

  2. In the planet frame, the magnitude |u_in| is the hyperbolic excess
     speed `v_∞` and is invariant across the encounter (energy
     conservation). The direction is rotated by twice the half-turning
     angle δ, with

         sin δ = 1 / (1 + r_p v_∞² / μ_p)               [dim-less]

     (Vallado 4th ed §12.3, ISBN 978-1881883180).

  3. The rotation axis is perpendicular to the pre-encounter velocity
     (the trajectory plane is set by the impact parameter). Without
     loss of generality we assume the rotation keeps the ship in the
     plane defined by `u_in` and the planet's heliocentric velocity,
     consistent with a planar flyby.

  4. Transform back to the heliocentric frame:
         v_out_helio = u_out + v_planet_helio            [m/s]

  5. The heliocentric Δv magnitude is
         |Δv_helio| = |v_out_helio − v_ship_helio|       [m/s]

Unit audit: every term is m/s. The result matches the scalar formula
`2 v_∞ sin δ` in the special case where the planet's heliocentric
velocity is anti-parallel to the incoming ship velocity.

Reference: Vallado 4th ed §12.3 "Planetary flyby"; Curtis 3rd ed §8.10
(ISBN 978-0080977478); Dessler 1983 *Physics of the Jovian
Magnetosphere* Appendix A (ISBN 978-0521285320) for the Voyager
reconstruction used as test case.
"""

from __future__ import annotations

import math

import numpy as np


def _rodrigues_rotate(vec: np.ndarray, axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate ``vec`` by ``angle_rad`` about ``axis`` (Rodrigues' formula)."""
    k = axis / np.linalg.norm(axis)
    cos_t = math.cos(angle_rad)
    sin_t = math.sin(angle_rad)
    return (
        vec * cos_t
        + np.cross(k, vec) * sin_t
        + k * np.dot(k, vec) * (1.0 - cos_t)
    )


def slingshot_vector_delta_v(
    v_ship_helio_m_s: np.ndarray,
    v_planet_helio_m_s: np.ndarray,
    periapsis_radius_m: float,
    planet_gm_m3_s2: float,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Compute a 3-D gravitational slingshot in the planet's rest frame.

    Args:
        v_ship_helio_m_s: ship's heliocentric velocity vector (3,) [m/s].
        v_planet_helio_m_s: planet's heliocentric velocity vector (3,)
            [m/s].
        periapsis_radius_m: flyby periapsis (m). Must be > planet radius
            in practice; this routine only checks > 0.
        planet_gm_m3_s2: μ of the planet (m³/s²).

    Returns:
        Tuple ``(v_out_helio, delta_v_vec_helio, delta_v_mag, turning_angle_2delta)``:
          - ``v_out_helio``: post-flyby heliocentric velocity vector (3,).
          - ``delta_v_vec_helio``: ``v_out_helio − v_ship_helio`` (3,).
          - ``delta_v_mag``: magnitude of ``delta_v_vec_helio`` in m/s.
          - ``turning_angle_2delta``: full deflection angle in radians.

    The trajectory plane is taken to be the span of the ship's planet-
    frame incoming velocity `u_in` and the planet's heliocentric velocity
    — the standard "coplanar powered flyby" approximation valid when the
    ship's impact parameter is small compared to the planet's orbital
    radius.
    """
    if periapsis_radius_m <= 0.0:
        raise ValueError("periapsis_radius_m must be positive")
    if planet_gm_m3_s2 <= 0.0:
        raise ValueError("planet_gm_m3_s2 must be positive")

    v_ship = np.asarray(v_ship_helio_m_s, dtype=float).reshape(3)
    v_planet = np.asarray(v_planet_helio_m_s, dtype=float).reshape(3)

    u_in = v_ship - v_planet
    v_inf_sq = float(np.dot(u_in, u_in))
    v_inf = math.sqrt(v_inf_sq)
    if v_inf == 0.0:
        # Ship is stationary in the planet frame; no flyby.
        return v_ship.copy(), np.zeros(3), 0.0, 0.0

    # Half-turning angle δ
    sin_delta = 1.0 / (1.0 + periapsis_radius_m * v_inf_sq / planet_gm_m3_s2)
    sin_delta = min(max(sin_delta, -1.0), 1.0)  # clip numerical noise
    delta = math.asin(sin_delta)
    two_delta = 2.0 * delta

    # Rotation axis: perpendicular to both u_in and v_planet (the
    # orbital plane of the flyby).
    axis = np.cross(u_in, v_planet)
    axis_norm = np.linalg.norm(axis)
    if axis_norm == 0.0:
        # u_in parallel to v_planet (degenerate); pick an arbitrary
        # perpendicular — this is the planar-retrograde case where the
        # scalar formula 2 v_∞ sin δ collapses to the maximum.
        # Use any unit vector perpendicular to u_in.
        helper = np.array([1.0, 0.0, 0.0])
        if abs(u_in[0]) > 0.9 * v_inf:
            helper = np.array([0.0, 1.0, 0.0])
        axis = np.cross(u_in, helper)
    axis = axis / np.linalg.norm(axis)

    # Rotate u_in by 2δ to get u_out (same magnitude).
    u_out = _rodrigues_rotate(u_in, axis, two_delta)

    v_out_helio = u_out + v_planet
    delta_v_vec = v_out_helio - v_ship
    delta_v_mag = float(np.linalg.norm(delta_v_vec))
    return v_out_helio, delta_v_vec, delta_v_mag, two_delta
