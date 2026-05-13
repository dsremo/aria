"""Newtonian tidal (curvature) tensor (§4.1 of docs/pods/A2_tidal_tensor.md).

Starting from the Newtonian potential of a point mass `M` at position
`R`:

    Φ(r) = −GM / |r − R|                               [m²/s²]

Differentiating twice gives the tidal tensor — the quantity that
stretches and squeezes an extended body rigidly translated through the
field:

    E^i_j(r) = ∂²Φ/∂x^i ∂x^j
             = (GM / |r−R|³) · (δ^i_j − 3 n^i n_j)     [1/s²]

where `n̂ = (r − R) / |r − R|` is the unit vector from the perturber
to the field point. Derivation: Misner-Thorne-Wheeler §1.6 eq. 1.14
(ISBN 978-0716703440).

The eigenvalue of `(δ − 3 n̂n̂ᵀ)` along `n̂` is `−2` (radial stretch),
and `+1` along each perpendicular direction (transverse squeeze). The
magnitude of the radial tidal acceleration experienced by a hull point
at offset `L` along `n̂` is therefore

    |a_tide| = 2 G M L / r³                            [m/s²]

which is the familiar "2 G M L / r³" textbook result (MTW §1.6).

The tensor is traceless in vacuum — a consequence of Laplace's equation
`∇²Φ = 0` there. We monitor this as a correctness check in the solver.

Superposition: the total tidal tensor from `N` point-mass perturbers is
simply the sum of their individual contributions.
"""

from __future__ import annotations

import numpy as np


def tidal_tensor_single_perturber(
    ship_position_m: np.ndarray,
    perturber_position_m: np.ndarray,
    perturber_gm_m3_s2: float,
) -> np.ndarray:
    """Newtonian tidal tensor at ``ship_position_m`` due to one point
    mass at ``perturber_position_m``.

    E^i_j = (GM / r³) · (δ^i_j − 3 n^i n_j)              [1/s²]

    Args:
        ship_position_m: (3,) field point (m).
        perturber_position_m: (3,) perturber position (m).
        perturber_gm_m3_s2: μ = GM of the perturber (m³/s²).

    Returns:
        (3, 3) tidal tensor in units of 1/s². Symmetric and — in a
        vacuum with a single perturber — traceless.
    """
    if perturber_gm_m3_s2 <= 0.0:
        raise ValueError("perturber_gm_m3_s2 must be positive")
    r_ship = np.asarray(ship_position_m, dtype=float).reshape(3)
    r_pert = np.asarray(perturber_position_m, dtype=float).reshape(3)
    sep = r_ship - r_pert
    r = float(np.linalg.norm(sep))
    if r == 0.0:
        raise ValueError(
            "tidal tensor is singular: ship position coincides with perturber"
        )
    n_hat = sep / r
    delta = np.eye(3, dtype=float)
    outer = np.outer(n_hat, n_hat)
    return (perturber_gm_m3_s2 / (r**3)) * (delta - 3.0 * outer)


def tidal_tensor_total(
    ship_position_m: np.ndarray,
    perturbers: list[tuple[np.ndarray, float]],
) -> np.ndarray:
    """Sum of tidal tensors from a list of perturbers.

    Args:
        ship_position_m: (3,) field point (m).
        perturbers: list of ``(R_i_m, GM_i_m3_s2)`` pairs.

    Returns:
        (3, 3) total tidal tensor in 1/s².
    """
    E = np.zeros((3, 3), dtype=float)
    for R_i, gm_i in perturbers:
        E += tidal_tensor_single_perturber(ship_position_m, R_i, gm_i)
    return E


def tidal_tensor_trace(E: np.ndarray) -> float:
    """Trace of a tidal tensor — should be zero in vacuum.

    A non-zero trace in vacuum indicates either a missing perturber in
    the superposition or a sign error; the orchestrator uses this
    diagnostic to fire a CRITICAL event (§8 of A2 scope).
    """
    return float(np.trace(np.asarray(E, dtype=float).reshape(3, 3)))


def tidal_acceleration_on_point(
    tidal_tensor_1_s2: np.ndarray,
    offset_from_cm_m: np.ndarray,
) -> np.ndarray:
    """Tidal acceleration on a hull point offset by `L` from the ship
    center of mass:

        a^i_tide = −E^i_j L^j                            [m/s²]

    (The sign convention: a positive tidal tensor times a positive
    offset gives a force directed away from the CoM along the radial
    direction — the classical stretch.)
    """
    E = np.asarray(tidal_tensor_1_s2, dtype=float).reshape(3, 3)
    L = np.asarray(offset_from_cm_m, dtype=float).reshape(3)
    return -(E @ L)


def radial_tidal_acceleration(
    perturber_gm_m3_s2: float,
    distance_to_perturber_m: float,
    body_half_length_m: float,
) -> float:
    """Textbook radial tidal acceleration magnitude.

    |a_tide| = 2 G M L / r³                              [m/s²]

    This is the magnitude along the radial direction from perturber to
    ship, for a hull point at offset `L` along that same direction
    (the worst case — the +1 eigenvalue of the transverse directions
    gives half this magnitude).

    Derivation: the eigenvalue of `(δ − 3 n̂n̂ᵀ)` along n̂ is −2, so the
    radial component of `E^i_j L^j` with `L = L n̂` is `(GM/r³)(−2L)`,
    giving the factor of 2.
    """
    if perturber_gm_m3_s2 <= 0.0:
        raise ValueError("perturber_gm_m3_s2 must be positive")
    if distance_to_perturber_m <= 0.0:
        raise ValueError("distance_to_perturber_m must be positive")
    if body_half_length_m < 0.0:
        raise ValueError("body_half_length_m must be non-negative")
    return 2.0 * perturber_gm_m3_s2 * body_half_length_m / (distance_to_perturber_m**3)
