"""Paris-Erdogan fatigue crack growth law (§4.6 of F2 scope).

Paris & Erdogan 1963 *J. Basic Eng.* 85 528-534 noticed that fatigue
crack-growth rates per cycle obey a power law in the stress-intensity
range:

    da/dN = C (ΔK)^m                                     [m/cycle]

valid in the stable growth regime II, ΔK_th < ΔK < (1 − R) K_c.
Here:

  - ΔK = K_max − K_min                                    (Pa·m^½)
  - C  = material constant                                (m/cycle / (Pa·m^½)^m)
  - m  = Paris exponent (dimensionless, typically 2-4 for metals)

The Paris constants are tabulated in handbooks (ASTM E647 round-
robin database, Hudak 1984 Fatigue 84, NASGRO 9.0). Common
convention writes them in the engineering unit system
``(m/cycle)/(MPa·m^½)^m``; the conversion factor to SI is

    C_SI [(m/cycle)/(Pa·m^½)^m] = C_eng / (10^6)^m

since 1 MPa·m^½ = 10⁶ Pa·m^½ and the exponent m carries through.

For Ti-6Al-4V at R = 0.1, ASTM E647 gives C_eng ≈ 1.1×10⁻¹¹ and
m ≈ 3.5; converting to SI gives C_SI ≈ 1.1×10⁻¹¹ / 10²¹ = 1.1×10⁻³².

For variable R-ratio loading, Walker 1970 (Effects of Environment
and Complex Load History, ASTM STP 462) corrected the effective
ΔK as

    ΔK_eff = ΔK / (1 − R)^(1 − γ)                       [Pa·m^½]

with γ a material constant typically ~0.5 for steels and ~0.42 for
Ti alloys. This module returns ΔK_eff so the user can plug it into
the Paris law unchanged.

Block integration: for a load block of `n` constant-amplitude
cycles applied at fixed ΔK, the crack length advances by

    Δa = n · C (ΔK)^m                                    [m]

(true while a < critical). The block-by-block integrator
``integrate_paris_block`` walks through a list of blocks and stops
when either the crack length reaches the supplied critical value or
the block list is exhausted.
"""

from __future__ import annotations

import math
from typing import Iterable


def paris_crack_growth_rate(
    delta_k_pa_sqrt_m: float,
    paris_c_si: float,
    paris_m: float,
) -> float:
    """Paris-law crack growth rate `da/dN = C (ΔK)^m` [m/cycle].

    Args:
        delta_k_pa_sqrt_m: ΔK in Pa·m^½ (SI units, NOT MPa·m^½).
        paris_c_si: C in (m/cycle)/(Pa·m^½)^m (SI). For converting
            from engineering tables, divide the tabulated value by
            (10^6)^m.
        paris_m: m exponent (dimensionless, typically 2-4).

    Returns:
        Crack growth rate in m/cycle (non-negative).
    """
    if delta_k_pa_sqrt_m < 0.0:
        raise ValueError("delta_k_pa_sqrt_m must be non-negative")
    if paris_c_si <= 0.0:
        raise ValueError("paris_c_si must be positive")
    if paris_m <= 0.0:
        raise ValueError("paris_m must be positive")
    if delta_k_pa_sqrt_m == 0.0:
        return 0.0
    return paris_c_si * (delta_k_pa_sqrt_m**paris_m)


def walker_delta_k_effective(
    delta_k_pa_sqrt_m: float,
    r_ratio: float,
    walker_gamma: float = 0.5,
) -> float:
    """Walker 1970 R-ratio correction `ΔK_eff = ΔK / (1−R)^(1−γ)`.

    For R = 0 (zero-tension cycle) ΔK_eff = ΔK regardless of γ.
    For R > 0 (tension-tension), the correction increases ΔK_eff
    above the apparent ΔK, reflecting that the mean stress
    accelerates crack growth.

    Args:
        delta_k_pa_sqrt_m: ΔK = K_max − K_min (Pa·m^½, ≥ 0).
        r_ratio: R = K_min / K_max. Must satisfy R < 1. Negative R
            (compressive component) is allowed but the formula
            applies only to the tensile portion of the cycle.
        walker_gamma: γ exponent (dimensionless). Typical 0.4-0.5
            for steels and Ti alloys (Walker 1970).

    Returns:
        ΔK_eff in Pa·m^½.
    """
    if delta_k_pa_sqrt_m < 0.0:
        raise ValueError("delta_k_pa_sqrt_m must be non-negative")
    if r_ratio >= 1.0:
        raise ValueError("r_ratio must be < 1")
    if r_ratio < 0.0:
        # Compressive R: clamp to zero per ASTM E647 convention.
        r_ratio = 0.0
    if walker_gamma <= 0.0:
        raise ValueError("walker_gamma must be positive")
    return delta_k_pa_sqrt_m / (1.0 - r_ratio) ** (1.0 - walker_gamma)


def integrate_paris_block(
    initial_crack_length_m: float,
    blocks: Iterable[tuple[float, float]],
    paris_c_si: float,
    paris_m: float,
    geometry_factor: float = 1.12,
    critical_crack_length_m: float | None = None,
) -> tuple[float, float, bool]:
    """Block-by-block Paris integration with optional fracture stop.

    Each block is a tuple ``(stress_range_pa, n_cycles)`` describing
    a constant-amplitude span of the load history. The crack length
    is updated using the *current* ΔK at the start of each block:

        ΔK_block = Y · Δσ · √(π a)
        Δa_block = n · C ΔK^m

    For long blocks where Δa is large compared to a, this is a
    coarse approximation; for representative ARIA load blocks
    (block size << critical) the leading-order Δa = n · C ΔK^m is
    accurate. A more sophisticated integrator that tracks ΔK
    sub-cycle is in the deferred follow-up.

    Args:
        initial_crack_length_m: starting crack length a_0 (m).
        blocks: iterable of (Δσ_pa, n_cycles) pairs.
        paris_c_si: Paris C in SI.
        paris_m: Paris m exponent.
        geometry_factor: Y in K_I = Y σ √(πa). Default 1.12.
        critical_crack_length_m: optional fracture stop. If supplied
            and a exceeds this value mid-block, the integrator
            returns early with `failed=True`.

    Returns:
        ``(final_crack_length_m, total_cycles_applied, failed)``.
        `failed` is True if the crack reached the critical length
        before exhausting the block list.
    """
    if initial_crack_length_m < 0.0:
        raise ValueError("initial_crack_length_m must be non-negative")
    a = initial_crack_length_m
    total_cycles = 0.0
    failed = False
    for delta_sigma_pa, n_cycles in blocks:
        if delta_sigma_pa < 0.0:
            raise ValueError("stress range must be non-negative")
        if n_cycles < 0.0:
            raise ValueError("n_cycles must be non-negative")
        delta_k = geometry_factor * delta_sigma_pa * math.sqrt(math.pi * a)
        rate = paris_crack_growth_rate(delta_k, paris_c_si, paris_m)
        delta_a = rate * n_cycles
        a += delta_a
        total_cycles += n_cycles
        if (
            critical_crack_length_m is not None
            and a >= critical_crack_length_m
        ):
            failed = True
            break
    return a, total_cycles, failed
