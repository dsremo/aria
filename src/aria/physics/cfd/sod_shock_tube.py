"""Exact Sod shock-tube solution (§4, Test case 9.4 of H1 scope).

The Sod 1978 test is the canonical 1-D compressible Euler benchmark:
a diaphragm at x = 0 separates a high-pressure left state
`(ρ_L, u_L, p_L) = (1, 0, 1)` from a low-pressure right state
`(ρ_R, u_R, p_R) = (0.125, 0, 0.1)` with γ = 1.4. When the diaphragm
ruptures, the solution consists of a left-moving rarefaction, a
contact discontinuity, and a right-moving shock.

The intermediate (star) pressure `p★` is the root of the Toro 2009
*Riemann Solvers and Numerical Methods for Fluid Dynamics* 3rd ed
§4.3 function f(p★) = f_L(p★) + f_R(p★) + (u_R − u_L) = 0, with

    f_K(p★) = (p★ − p_K) · √(A_K / (p★ + B_K))        (shock)
    f_K(p★) = (2 c_K / (γ − 1)) · [(p★ / p_K)^{(γ-1)/(2γ)} − 1]   (raref.)

and `A_K = 2 / ((γ + 1) ρ_K)`, `B_K = (γ − 1)/(γ + 1) · p_K`. We solve
by bisection on `p★ ∈ [1e-6, 10·max(p_L, p_R)]`.

For the canonical Sod state Toro 2009 Table 4.1 gives
    p★ = 0.30313, u★ = 0.92745, ρ★_L = 0.42632, ρ★_R = 0.26557.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SodExactSolution:
    """Intermediate star-state of the Sod Riemann problem.

    Attributes:
        p_star: pressure in the star region.
        u_star: velocity in the star region.
        rho_star_left: density on the left of the contact.
        rho_star_right: density on the right of the contact.
    """

    p_star: float
    u_star: float
    rho_star_left: float
    rho_star_right: float


def _speed_of_sound(gamma: float, pressure: float, density: float) -> float:
    return math.sqrt(gamma * pressure / density)


def _f_k(p_star: float, pk: float, rho_k: float, ck: float, gamma: float) -> float:
    """Toro 2009 eq. 4.5 (shock) / eq. 4.21 (rarefaction)."""
    if p_star > pk:  # shock
        a_k = 2.0 / ((gamma + 1.0) * rho_k)
        b_k = (gamma - 1.0) / (gamma + 1.0) * pk
        return (p_star - pk) * math.sqrt(a_k / (p_star + b_k))
    # rarefaction
    return (
        (2.0 * ck / (gamma - 1.0))
        * ((p_star / pk) ** ((gamma - 1.0) / (2.0 * gamma)) - 1.0)
    )


def sod_exact_post_shock_state(
    rho_left: float = 1.0,
    u_left: float = 0.0,
    p_left: float = 1.0,
    rho_right: float = 0.125,
    u_right: float = 0.0,
    p_right: float = 0.1,
    gamma: float = 1.4,
    tol: float = 1.0e-10,
    max_iter: int = 200,
) -> SodExactSolution:
    """Exact intermediate star-state of the Sod shock tube.

    Defaults reproduce the canonical Sod 1978 test (γ = 1.4; Toro 2009
    Table 4.1 reference p★ = 0.30313, u★ = 0.92745, ρ★_L = 0.42632,
    ρ★_R = 0.26557).

    Args:
        rho_left, u_left, p_left: left state (kg/m³, m/s, Pa).
        rho_right, u_right, p_right: right state.
        gamma: specific heat ratio.
        tol: relative tolerance on p★.
        max_iter: bisection cap.

    Returns:
        SodExactSolution.
    """
    if rho_left <= 0.0 or rho_right <= 0.0:
        raise ValueError("densities must be positive")
    if p_left <= 0.0 or p_right <= 0.0:
        raise ValueError("pressures must be positive")
    if gamma <= 1.0:
        raise ValueError("gamma must be > 1")

    c_l = _speed_of_sound(gamma, p_left, rho_left)
    c_r = _speed_of_sound(gamma, p_right, rho_right)

    def residual(p_star: float) -> float:
        return (
            _f_k(p_star, p_left, rho_left, c_l, gamma)
            + _f_k(p_star, p_right, rho_right, c_r, gamma)
            + (u_right - u_left)
        )

    lo = 1.0e-6
    hi = 10.0 * max(p_left, p_right)
    r_lo = residual(lo)
    r_hi = residual(hi)
    if r_lo * r_hi > 0.0:
        raise RuntimeError("Sod bracket failure — states may be unphysical")

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        r_mid = residual(mid)
        if abs(r_mid) < tol:
            p_star = mid
            break
        if r_mid * r_lo < 0.0:
            hi, r_hi = mid, r_mid
        else:
            lo, r_lo = mid, r_mid
    else:
        p_star = 0.5 * (lo + hi)

    u_star = 0.5 * (
        u_left
        + u_right
        + _f_k(p_star, p_right, rho_right, c_r, gamma)
        - _f_k(p_star, p_left, rho_left, c_l, gamma)
    )

    # Star-region densities (Toro 2009 eqs. 4.53, 4.60).
    if p_star > p_left:  # left shock
        ratio = p_star / p_left
        num = ratio + (gamma - 1.0) / (gamma + 1.0)
        den = (gamma - 1.0) / (gamma + 1.0) * ratio + 1.0
        rho_star_l = rho_left * num / den
    else:  # left rarefaction — isentropic
        rho_star_l = rho_left * (p_star / p_left) ** (1.0 / gamma)

    if p_star > p_right:  # right shock
        ratio = p_star / p_right
        num = ratio + (gamma - 1.0) / (gamma + 1.0)
        den = (gamma - 1.0) / (gamma + 1.0) * ratio + 1.0
        rho_star_r = rho_right * num / den
    else:
        rho_star_r = rho_right * (p_star / p_right) ** (1.0 / gamma)

    return SodExactSolution(
        p_star=p_star,
        u_star=u_star,
        rho_star_left=rho_star_l,
        rho_star_right=rho_star_r,
    )
