"""Mean-stress corrections: Goodman, Gerber, Smith-Watson-Topper
(§4.3 of F2 scope).

Under non-zero mean stress `σ_m`, the allowable alternating stress
amplitude `σ_a` at a given life is reduced. Classical corrections
(Suresh 1998 *Fatigue of Materials* 2nd ed §7.4, ISBN 978-0521578479):

**Goodman line** (conservative linear — preferred for brittle metals):

    σ_a / σ_a0 + σ_m / σ_UTS = 1

    → σ_a0_eq = σ_a / (1 − σ_m / σ_UTS)                  [Pa]

**Gerber parabola** (less conservative — preferred for ductile metals):

    σ_a / σ_a0 + (σ_m / σ_UTS)² = 1

    → σ_a0_eq = σ_a / (1 − (σ_m / σ_UTS)²)               [Pa]

**Smith-Watson-Topper 1970 parameter** (incorporates σ_max):

    P_SWT = √( σ_max · σ_a · E )                         [Pa]
          = √( (σ_a + σ_m) · σ_a · E )

with E the Young's modulus. The SWT approach folds mean stress in
via σ_max = σ_m + σ_a and is typically paired with strain-life
coefficients rather than stress-life.

All three forms return an **equivalent zero-mean amplitude** that
can then be fed into the standard Basquin S-N curve — so a
Goodman-corrected fatigue calculation is one call to this module
followed by one call to `basquin_life`.
"""

from __future__ import annotations

import math


def goodman_equivalent_amplitude(
    stress_amplitude_pa: float,
    mean_stress_pa: float,
    ultimate_strength_pa: float,
) -> float:
    """Convert (σ_a, σ_m) to an equivalent zero-mean amplitude using
    the Goodman line.

    σ_a_eq = σ_a / (1 − σ_m / σ_UTS)                     [Pa]

    Compressive mean stress (σ_m < 0) is typically beneficial and is
    *conservatively* treated as zero in this implementation (a
    common engineering choice; Suresh 1998 §7.4 warns that
    compressive means are beneficial but difficult to quantify).

    Args:
        stress_amplitude_pa: σ_a (Pa, positive).
        mean_stress_pa: σ_m (Pa). Must satisfy σ_m < σ_UTS.
        ultimate_strength_pa: σ_UTS (Pa, positive).

    Returns:
        Equivalent zero-mean amplitude (Pa).

    Raises:
        ValueError: if σ_m ≥ σ_UTS (static failure before any cyclic
            stress).
    """
    if stress_amplitude_pa <= 0.0:
        raise ValueError("stress_amplitude_pa must be positive")
    if ultimate_strength_pa <= 0.0:
        raise ValueError("ultimate_strength_pa must be positive")
    if mean_stress_pa >= ultimate_strength_pa:
        raise ValueError("mean_stress_pa must be less than ultimate_strength_pa")
    # Conservative treatment of compressive mean: clamp to zero.
    effective_mean = max(0.0, mean_stress_pa)
    return stress_amplitude_pa / (1.0 - effective_mean / ultimate_strength_pa)


def gerber_equivalent_amplitude(
    stress_amplitude_pa: float,
    mean_stress_pa: float,
    ultimate_strength_pa: float,
) -> float:
    """Gerber-parabola equivalent zero-mean amplitude.

    σ_a_eq = σ_a / (1 − (σ_m / σ_UTS)²)                  [Pa]
    """
    if stress_amplitude_pa <= 0.0:
        raise ValueError("stress_amplitude_pa must be positive")
    if ultimate_strength_pa <= 0.0:
        raise ValueError("ultimate_strength_pa must be positive")
    if abs(mean_stress_pa) >= ultimate_strength_pa:
        raise ValueError("|mean_stress_pa| must be less than ultimate_strength_pa")
    ratio = mean_stress_pa / ultimate_strength_pa
    return stress_amplitude_pa / (1.0 - ratio * ratio)


def swt_parameter(
    stress_amplitude_pa: float,
    mean_stress_pa: float,
    youngs_modulus_pa: float,
) -> float:
    """Smith-Watson-Topper mean-stress parameter.

    P_SWT = √( σ_max · σ_a · E )                         [Pa]

    with σ_max = σ_m + σ_a. For σ_max ≤ 0 (fully compressive cycle)
    the SWT formulation is non-physical and we return zero (a common
    convention: compressive-only cycles don't contribute to tensile
    crack growth).

    Args:
        stress_amplitude_pa: σ_a (Pa).
        mean_stress_pa: σ_m (Pa).
        youngs_modulus_pa: Young's modulus E (Pa).

    Returns:
        P_SWT in Pa (non-negative).
    """
    if stress_amplitude_pa <= 0.0:
        raise ValueError("stress_amplitude_pa must be positive")
    if youngs_modulus_pa <= 0.0:
        raise ValueError("youngs_modulus_pa must be positive")
    sigma_max = mean_stress_pa + stress_amplitude_pa
    if sigma_max <= 0.0:
        return 0.0
    return math.sqrt(sigma_max * stress_amplitude_pa * youngs_modulus_pa)
