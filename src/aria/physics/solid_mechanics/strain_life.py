"""Coffin-Manson and Manson-Hirschberg strain-life relations
(§4.2 of F2 scope).

For low-cycle fatigue (LCF) where the plastic strain dominates, the
elastic Basquin formulation breaks down. Coffin 1954 and Manson 1953
independently observed that plastic strain amplitude follows a power
law in cycles to failure:

    Δε_p / 2 = ε_f' (2 N_f)^c                            [-]

where
    ε_f' = fatigue ductility coefficient (dimensionless, ~0.1-1)
    c    = fatigue ductility exponent (dimensionless, ~−0.5 to −0.8)
    2 N_f = reversals to failure

Combining the elastic Basquin term and the plastic Coffin-Manson term
gives the Manson-Hirschberg total-strain-life relation (Suresh 1998
*Fatigue of Materials* 2nd ed §7.3, ISBN 978-0521578479):

    Δε / 2 = (σ_f' / E)(2 N_f)^b + ε_f' (2 N_f)^c        [-]

The two terms cross over at the *transition life* `2 N_t`:

    2 N_t = (ε_f' E / σ_f')^(1 / (b − c))                [reversals]

Below `N_t` the response is plastic-dominated (LCF); above it is
elastic-dominated (HCF). For Ti-6Al-4V the transition life is
roughly 10^4-10^5 cycles depending on heat treatment.

Inverting `Δε / 2 = f(N_f)` to recover `N_f` is implicit and
requires a numerical root-find. We use scipy.optimize.brentq via a
hand-rolled bisection so that this module has no scipy dependency.
"""

from __future__ import annotations

import math


def coffin_manson_plastic_strain(
    cycles_to_failure: float,
    epsilon_f_prime: float,
    coffin_c_exponent: float,
) -> float:
    """Plastic strain amplitude `Δε_p / 2 = ε_f' (2 N_f)^c` [-].

    Args:
        cycles_to_failure: N_f (reversals to failure / 2). Positive.
        epsilon_f_prime: ε_f' fatigue ductility coefficient
            (dimensionless, positive, typically 0.1-1.5 for ductile
            metals).
        coffin_c_exponent: c (dimensionless, must be negative).

    Returns:
        Plastic strain amplitude (dimensionless, non-negative).
    """
    if cycles_to_failure <= 0.0:
        raise ValueError("cycles_to_failure must be positive")
    if epsilon_f_prime <= 0.0:
        raise ValueError("epsilon_f_prime must be positive")
    if coffin_c_exponent >= 0.0:
        raise ValueError("coffin_c_exponent must be negative")
    return epsilon_f_prime * (2.0 * cycles_to_failure) ** coffin_c_exponent


def manson_hirschberg_total_strain(
    cycles_to_failure: float,
    sigma_f_prime_pa: float,
    basquin_b_exponent: float,
    epsilon_f_prime: float,
    coffin_c_exponent: float,
    youngs_modulus_pa: float,
) -> float:
    """Total strain amplitude `Δε / 2` [dimensionless] vs life.

    Δε / 2 = (σ_f' / E)(2 N_f)^b + ε_f' (2 N_f)^c

    The first term is the elastic Basquin contribution; the second
    is the plastic Coffin-Manson contribution.
    """
    if cycles_to_failure <= 0.0:
        raise ValueError("cycles_to_failure must be positive")
    if sigma_f_prime_pa <= 0.0:
        raise ValueError("sigma_f_prime_pa must be positive")
    if basquin_b_exponent >= 0.0:
        raise ValueError("basquin_b_exponent must be negative")
    if epsilon_f_prime <= 0.0:
        raise ValueError("epsilon_f_prime must be positive")
    if coffin_c_exponent >= 0.0:
        raise ValueError("coffin_c_exponent must be negative")
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    two_n_f = 2.0 * cycles_to_failure
    elastic = (sigma_f_prime_pa / youngs_modulus_pa) * (two_n_f**basquin_b_exponent)
    plastic = epsilon_f_prime * (two_n_f**coffin_c_exponent)
    return elastic + plastic


def transition_life_reversals(
    sigma_f_prime_pa: float,
    basquin_b_exponent: float,
    epsilon_f_prime: float,
    coffin_c_exponent: float,
    youngs_modulus_pa: float,
) -> float:
    """Transition life `2 N_t` where elastic and plastic strain
    contributions are equal.

    From `(σ_f'/E)(2 N_t)^b = ε_f' (2 N_t)^c`:

        2 N_t = (ε_f' E / σ_f')^(1 / (b − c))            [reversals]

    Below this life the response is plastic-dominated (LCF); above
    it the response is elastic-dominated (HCF). Suresh 1998 §7.3
    eq. 7.20.
    """
    if basquin_b_exponent >= 0.0 or coffin_c_exponent >= 0.0:
        raise ValueError("both b and c must be negative")
    ratio = epsilon_f_prime * youngs_modulus_pa / sigma_f_prime_pa
    return ratio ** (1.0 / (basquin_b_exponent - coffin_c_exponent))


def manson_hirschberg_life(
    total_strain_amplitude: float,
    sigma_f_prime_pa: float,
    basquin_b_exponent: float,
    epsilon_f_prime: float,
    coffin_c_exponent: float,
    youngs_modulus_pa: float,
    tol: float = 1.0e-12,
    max_iter: int = 200,
) -> float:
    """Solve `Manson-Hirschberg(N_f) = Δε / 2` for N_f via bisection.

    The right-hand side is monotone-decreasing in N_f (both b and c
    are negative), so a sign-changing bisection on
    ``g(N_f) = M-H(N_f) − Δε/2`` is unconditionally convergent.

    Args:
        total_strain_amplitude: Δε / 2 (dimensionless, positive).
        sigma_f_prime_pa, basquin_b_exponent: elastic Basquin pair.
        epsilon_f_prime, coffin_c_exponent: plastic C-M pair.
        youngs_modulus_pa: E (Pa).
        tol: relative bracket tolerance for the bisection.
        max_iter: maximum bisection iterations.

    Returns:
        Cycles to failure N_f.

    Raises:
        ValueError: if the requested strain amplitude is so large
            that even a half-cycle to failure cannot reach it, or if
            the iteration fails to bracket.
    """
    if total_strain_amplitude <= 0.0:
        raise ValueError("total_strain_amplitude must be positive")

    def rhs(n_f: float) -> float:
        return manson_hirschberg_total_strain(
            cycles_to_failure=n_f,
            sigma_f_prime_pa=sigma_f_prime_pa,
            basquin_b_exponent=basquin_b_exponent,
            epsilon_f_prime=epsilon_f_prime,
            coffin_c_exponent=coffin_c_exponent,
            youngs_modulus_pa=youngs_modulus_pa,
        )

    target = total_strain_amplitude

    # Bracket: rhs is monotone-decreasing. Start at very few cycles
    # (0.5 = one reversal) and very many (1e12). Both b and c are
    # negative so rhs(0.5) is the largest possible value.
    n_lo = 0.5
    n_hi = 1.0e12
    if rhs(n_lo) < target:
        raise ValueError(
            "requested total_strain_amplitude exceeds the half-cycle "
            "limit; the material cannot survive even one reversal"
        )
    if rhs(n_hi) > target:
        # The strain is so small that infinite-life is appropriate.
        return float("inf")

    for _ in range(max_iter):
        n_mid = math.sqrt(n_lo * n_hi)  # geometric midpoint (log scale)
        v_mid = rhs(n_mid)
        if abs(v_mid - target) < tol * target:
            return n_mid
        if v_mid > target:
            n_lo = n_mid
        else:
            n_hi = n_mid
        if n_hi / n_lo < 1.0 + tol:
            return math.sqrt(n_lo * n_hi)
    return math.sqrt(n_lo * n_hi)
