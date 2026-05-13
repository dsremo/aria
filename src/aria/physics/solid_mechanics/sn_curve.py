"""Basquin stress-life and Morrow mean-stress corrections (§4.1-§4.3 of F2).

Basquin 1910 stress-amplitude-to-life relation (Suresh 1998
*Fatigue of Materials* 2nd ed §7.2, ISBN 978-0521578479):

    σ_a = σ_f' · (2 N_f)^b                               [Pa]

where
    σ_a   = applied stress amplitude (Pa)
    σ_f'  = fatigue strength coefficient (Pa), material property
    b     = Basquin exponent (dimensionless, negative, ~−0.05 to −0.15)
    2 N_f = reversals to failure (two per cycle)

Inverting gives the life at a given amplitude:

    N_f = (1/2) · (σ_a / σ_f')^(1/b)                     [cycles]

Morrow 1968 mean-stress correction (SAE J1099):

    σ_a = (σ_f' − σ_m) · (2 N_f)^b                       [Pa]

which is equivalent to replacing σ_f' by (σ_f' − σ_m) in Basquin.

Typical values for Ti-6Al-4V (Boyer 1994 ASM Titanium Handbook
Table F2): σ_f' = 2030 MPa, b = −0.104. This predicts a fatigue
strength of ~460 MPa at 10⁶ cycles and ~260 MPa at 10⁸ cycles,
consistent with MIL-HDBK-5 S-N data.
"""

from __future__ import annotations

import math


def basquin_life(
    stress_amplitude_pa: float,
    sigma_f_prime_pa: float,
    basquin_b_exponent: float,
) -> float:
    """Cycles to failure from Basquin's law.

    N_f = (1/2) · (σ_a / σ_f')^(1/b)                     [cycles]

    Args:
        stress_amplitude_pa: σ_a (Pa), strictly positive.
        sigma_f_prime_pa: σ_f' (Pa), material fatigue-strength
            coefficient.
        basquin_b_exponent: b (dimensionless, must be negative for
            a physically sensible S-N curve).

    Returns:
        Cycles to failure N_f (dimensionless, positive).

    Raises:
        ValueError: for non-physical inputs.
    """
    if stress_amplitude_pa <= 0.0:
        raise ValueError("stress_amplitude_pa must be positive")
    if sigma_f_prime_pa <= 0.0:
        raise ValueError("sigma_f_prime_pa must be positive")
    if basquin_b_exponent >= 0.0:
        raise ValueError("basquin_b_exponent must be negative")
    ratio = stress_amplitude_pa / sigma_f_prime_pa
    two_n_f = ratio ** (1.0 / basquin_b_exponent)
    return 0.5 * two_n_f


def basquin_stress_amplitude(
    cycles_to_failure: float,
    sigma_f_prime_pa: float,
    basquin_b_exponent: float,
) -> float:
    """Stress amplitude at a given life from Basquin's law.

    σ_a = σ_f' · (2 N_f)^b                               [Pa]

    Inverse of ``basquin_life``. Useful for allowable-stress
    computations and for plotting the S-N curve.
    """
    if cycles_to_failure <= 0.0:
        raise ValueError("cycles_to_failure must be positive")
    if sigma_f_prime_pa <= 0.0:
        raise ValueError("sigma_f_prime_pa must be positive")
    if basquin_b_exponent >= 0.0:
        raise ValueError("basquin_b_exponent must be negative")
    return sigma_f_prime_pa * (2.0 * cycles_to_failure) ** basquin_b_exponent


def morrow_life(
    stress_amplitude_pa: float,
    mean_stress_pa: float,
    sigma_f_prime_pa: float,
    basquin_b_exponent: float,
) -> float:
    """Life under non-zero mean stress via Morrow's correction.

    σ_a = (σ_f' − σ_m) · (2 N_f)^b                       [Pa]

    Solve for N_f:
        N_f = (1/2) · (σ_a / (σ_f' − σ_m))^(1/b)

    Args:
        stress_amplitude_pa: σ_a (Pa).
        mean_stress_pa: σ_m (Pa). Positive = tensile mean.
        sigma_f_prime_pa: σ_f' (Pa). Must exceed σ_m.
        basquin_b_exponent: b (dimensionless, negative).

    Returns:
        N_f in cycles.

    Raises:
        ValueError: if σ_m ≥ σ_f' (the material is already above its
            fatigue-strength coefficient and any alternating stress
            would cause immediate failure — the Morrow model breaks
            down).
    """
    if sigma_f_prime_pa <= mean_stress_pa:
        raise ValueError(
            "Morrow correction requires sigma_f_prime_pa > mean_stress_pa"
        )
    effective_sigma_f = sigma_f_prime_pa - mean_stress_pa
    return basquin_life(stress_amplitude_pa, effective_sigma_f, basquin_b_exponent)
