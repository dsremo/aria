"""Izzo Lambert solver — quartic Householder convergence.

Solves Lambert's problem: given two position vectors r1, r2 and a
time of flight, find the transfer orbit velocity vectors v1, v2.

This implementation uses the Izzo (2015) algorithm with Householder
iteration (quartic convergence, 3-5 iterations) instead of Brent's
method (linear convergence, up to 300 iterations). Supports
multi-revolution transfers (M > 0).

References:
    Izzo, D. (2015). "Revisiting Lambert's problem."
    Celestial Mechanics and Dynamical Astronomy, 121(1), 1-15.
    DOI: 10.1007/s10569-014-9587-y

    Algorithm studied from poliastro (MIT license, poliastro/core/iod.py)
    and reimplemented from the published paper.
"""

from __future__ import annotations

import math

import numpy as np


def lambert_izzo(
    mu: float,
    r1: np.ndarray,
    r2: np.ndarray,
    tof: float,
    M: int = 0,
    prograde: bool = True,
    lowpath: bool = True,
    maxiter: int = 35,
    rtol: float = 1e-8,
) -> tuple[np.ndarray, np.ndarray]:
    """Solve Lambert's problem using the Izzo-Householder method.

    Parameters
    ----------
    mu : float
        Gravitational parameter (m^3/s^2 or km^3/s^2, consistent with r).
    r1 : (3,) array
        Initial position vector.
    r2 : (3,) array
        Final position vector.
    tof : float
        Time of flight (seconds or consistent time unit).
    M : int
        Number of complete revolutions (0 = direct transfer).
    prograde : bool
        True for prograde transfer, False for retrograde.
    lowpath : bool
        For multi-rev, selects low or high energy path.
    maxiter : int
        Maximum Householder iterations.
    rtol : float
        Convergence tolerance.

    Returns
    -------
    v1 : (3,) array — departure velocity
    v2 : (3,) array — arrival velocity

    Raises
    ------
    ValueError
        If inputs are degenerate or no solution exists.
    """
    r1 = np.asarray(r1, dtype=float)
    r2 = np.asarray(r2, dtype=float)

    if tof <= 0:
        raise ValueError("Time of flight must be positive")
    if mu <= 0:
        raise ValueError("Gravitational parameter must be positive")

    # Chord and norms
    c = r2 - r1
    c_norm = np.linalg.norm(c)
    r1_norm = np.linalg.norm(r1)
    r2_norm = np.linalg.norm(r2)

    if c_norm < 1e-15 * r1_norm:
        raise ValueError("Position vectors are identical")

    # Semiperimeter
    s = 0.5 * (r1_norm + r2_norm + c_norm)

    # Unit vectors
    ir1 = r1 / r1_norm
    ir2 = r2 / r2_norm
    ih = np.cross(ir1, ir2)
    ih_norm = np.linalg.norm(ih)

    if ih_norm < 1e-15:
        raise ValueError("Collinear position vectors — Lambert undefined")
    ih = ih / ih_norm

    # Geometry parameter lambda
    ll = math.sqrt(max(0.0, 1.0 - min(1.0, c_norm / s)))

    # Tangential unit vectors
    if ih[2] < 0:
        ll = -ll
        it1 = np.cross(ir1, ih)
        it2 = np.cross(ir2, ih)
    else:
        it1 = np.cross(ih, ir1)
        it2 = np.cross(ih, ir2)

    if not prograde:
        ll = -ll
        it1 = -it1
        it2 = -it2

    # Non-dimensional time of flight
    T = math.sqrt(2.0 * mu / s ** 3) * tof

    # Solve for x using Householder iteration
    x0 = _initial_guess(T, ll, M, lowpath)
    x = _householder(x0, T, ll, M, rtol, maxiter)
    y = math.sqrt(max(0.0, 1.0 - ll ** 2 * (1.0 - x ** 2)))

    # Reconstruct velocity components
    gamma = math.sqrt(mu * s / 2.0)
    rho = (r1_norm - r2_norm) / c_norm
    sigma = math.sqrt(max(0.0, 1.0 - rho ** 2))

    vr1 = gamma * ((ll * y - x) - rho * (ll * y + x)) / r1_norm
    vr2 = -gamma * ((ll * y - x) + rho * (ll * y + x)) / r2_norm
    vt1 = gamma * sigma * (y + ll * x) / r1_norm
    vt2 = gamma * sigma * (y + ll * x) / r2_norm

    v1 = vr1 * ir1 + vt1 * it1
    v2 = vr2 * ir2 + vt2 * it2

    return v1, v2


# ── Internal helpers ──────────────────────────────────────────────

def _compute_y(x: float, ll: float) -> float:
    return math.sqrt(max(0.0, 1.0 - ll ** 2 * (1.0 - x ** 2)))


def _compute_psi(x: float, y: float, ll: float) -> float:
    if -1 <= x < 1:
        return math.acos(max(-1.0, min(1.0, x * y + ll * (1.0 - x ** 2))))
    elif x > 1:
        return math.asinh((y - x * ll) * math.sqrt(x ** 2 - 1.0))
    return 0.0


def _tof_equation(x: float, T0: float, ll: float, M: int) -> float:
    """Time-of-flight equation F(x) = T(x) - T0."""
    y = _compute_y(x, ll)

    if M == 0 and math.sqrt(0.6) < x < math.sqrt(1.4):
        eta = y - ll * x
        S1 = 0.5 * (1.0 - ll - x * eta)
        Q = _hyp2f1b(S1)
        T_ = 0.5 * (eta ** 3 * Q + 4.0 * ll * eta)
    else:
        psi = _compute_psi(x, y, ll)
        T_ = (psi + M * math.pi) / math.sqrt(abs(1.0 - x ** 2)) - x + ll * y
        T_ = T_ / (1.0 - x ** 2)

    return T_ - T0


def _tof_p(x: float, y: float, T: float, ll: float) -> float:
    """First derivative dT/dx."""
    return (3.0 * T * x - 2.0 + 2.0 * ll ** 3 * x / y) / (1.0 - x ** 2)


def _tof_p2(x: float, y: float, T: float, dT: float, ll: float) -> float:
    """Second derivative d²T/dx²."""
    return (3.0 * T + 5.0 * x * dT + 2.0 * (1.0 - ll ** 2) * ll ** 3 / y ** 3) / (1.0 - x ** 2)


def _tof_p3(x: float, y: float, _T: float, dT: float, ddT: float, ll: float) -> float:
    """Third derivative d³T/dx³."""
    return (7.0 * x * ddT + 8.0 * dT - 6.0 * (1.0 - ll ** 2) * ll ** 5 * x / y ** 5) / (1.0 - x ** 2)


def _hyp2f1b(x: float) -> float:
    """Hypergeometric function 2F1(3, 1, 5/2, x) used near x~1.

    Series expansion for numerical stability in the parabolic regime.
    Izzo (2015) Eq. (22).
    """
    if abs(x) > 0.999:
        return float('inf')
    result = 1.0
    term = 1.0
    for i in range(1, 100):
        term *= x * (3.0 + i - 1) * (1.0 + i - 1) / (2.5 + i - 1) / i
        result += term
        if abs(term) < 1e-15:
            break
    return result


def _initial_guess(T: float, ll: float, M: int, lowpath: bool) -> float:
    """Smart initial guess for the Householder iteration.

    Izzo (2015) Section 3.2, with corrected piecewise formula.
    """
    if M == 0:
        T_0 = math.acos(ll) + ll * math.sqrt(1.0 - ll ** 2)
        T_1 = 2.0 * (1.0 - ll ** 3) / 3.0

        if T >= T_0:
            return (T_0 / T) ** (2.0 / 3.0) - 1.0
        elif T < T_1:
            return 2.5 * T_1 / T * (T_1 - T) / (1.0 - ll ** 5) + 1.0
        else:
            return math.exp(math.log(2.0) * math.log(T / T_0) / math.log(T_1 / T_0)) - 1.0
    else:
        # Multi-revolution initial guess
        x_0l = (((M * math.pi + math.pi) / (8.0 * T)) ** (2.0 / 3.0) - 1.0) / (
            ((M * math.pi + math.pi) / (8.0 * T)) ** (2.0 / 3.0) + 1.0
        )
        x_0r = (((8.0 * T) / (M * math.pi)) ** (2.0 / 3.0) - 1.0) / (
            ((8.0 * T) / (M * math.pi)) ** (2.0 / 3.0) + 1.0
        )
        return max(x_0l, x_0r) if lowpath else min(x_0l, x_0r)


def _householder(x0: float, T0: float, ll: float, M: int, tol: float, maxiter: int) -> float:
    """Householder iteration (quartic convergence) for Lambert's TOF equation.

    Izzo (2015) Section 3.3.
    """
    p = x0
    for _ in range(maxiter):
        y = _compute_y(p, ll)
        fval = _tof_equation(p, T0, ll, M)
        T = fval + T0
        fder = _tof_p(p, y, T, ll)
        fder2 = _tof_p2(p, y, T, fder, ll)
        fder3 = _tof_p3(p, y, T, fder, fder2, ll)

        # Householder step (quartic convergence)
        denom = fder * (fder ** 2 - fval * fder2) + fder3 * fval ** 2 / 6.0
        if abs(denom) < 1e-30:
            break
        dp = fval * (fder ** 2 - fval * fder2 / 2.0) / denom
        p -= dp

        if abs(dp) < tol:
            return p

    return p  # return best estimate even if not fully converged
