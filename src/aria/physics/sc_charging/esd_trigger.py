"""ESD trigger criterion and arc energy (§4.5, §4.6 of D2 scope).

An electrostatic discharge fires when the internal electric field in
a dielectric exceeds its intrinsic breakdown strength `E_BD`. On
breakdown the stored electrostatic energy in the charged volume
collapses in nanoseconds, and the bolt of current couples into
nearby cable harnesses via their transfer impedance (the EMC
simulator's problem, not D2's).

The stored energy in a parallel-plate capacitor of area `A`, plate
separation `d`, and uniform internal field `E` is

    U = (1/2) ε₀ ε_r E² · A d                              [J]

(standard electrostatics, any intro EM textbook; Chen 2016 eq. 8.42).
For Kapton with E = E_BD = 2.5×10⁸ V/m on a 1 cm² × 250 µm patch, this
gives U ≈ 2.4 mJ — squarely in the "harmless click → killer bolt"
range depending on the coupling path. Leach & Alexander 1995
NASA/TP-2003-212287 catalog on-orbit ESD events spanning 1 mJ → 1 J.

The ESD probability-per-hour model follows Koons et al. 2000
(Proc. 6th Spacecraft Charging Technology Conf., AFRL-VS-TR-20001578)
statistical regression of SCATHA/ATS-6/CRRES anomaly counts vs
field level: above 0.5·E_BD the event rate is zero; between
0.5·E_BD and E_BD it rises approximately linearly to ~1 per hour;
above E_BD it saturates to the breakdown-limited value (~1 per
charging time constant, which is always ≫ 1 per hour for bulk
charging).
"""

from __future__ import annotations

# Electrical permittivity of free space (CODATA 2018).
_EPSILON_0_F_M: float = 8.8541878128e-12


def esd_triggered(
    internal_field_v_m: float,
    breakdown_field_v_m: float,
) -> bool:
    """Return True iff |E_int| ≥ E_BD (Chen 2016 §8; NASA-HDBK-4002A §5).

    This is the deterministic trigger; for probabilistic rate
    estimation below the breakdown threshold, use
    ``esd_probability_per_hour``.
    """
    if breakdown_field_v_m <= 0.0:
        raise ValueError("breakdown_field_v_m must be positive")
    return abs(internal_field_v_m) >= breakdown_field_v_m


def arc_energy_parallel_plate(
    internal_field_v_m: float,
    area_m2: float,
    thickness_m: float,
    relative_permittivity: float,
    epsilon_0_f_m: float = _EPSILON_0_F_M,
) -> float:
    """Stored electrostatic energy in a parallel-plate dielectric.

    U = (1/2) · ε₀ ε_r · E² · A · d                       [J]

    On a breakdown event the entire U is dumped into the arc channel
    over ~nanoseconds; this is the "arc energy" reported to the
    downstream EMC coupling model. A more accurate model would include
    only the fraction of stored energy inside the break-down filament,
    but for handbook ESD survival estimation the full volumetric energy
    is the standard conservative upper bound (Leach & Alexander 1995
    NASA/TP-2003-212287 §3.4).
    """
    if area_m2 <= 0.0:
        raise ValueError("area_m2 must be positive")
    if thickness_m <= 0.0:
        raise ValueError("thickness_m must be positive")
    if relative_permittivity <= 0.0:
        raise ValueError("relative_permittivity must be positive")
    return (
        0.5
        * epsilon_0_f_m
        * relative_permittivity
        * internal_field_v_m * internal_field_v_m
        * area_m2
        * thickness_m
    )


def esd_probability_per_hour(
    internal_field_v_m: float,
    breakdown_field_v_m: float,
    saturated_rate_per_hour: float = 1.0,
) -> float:
    """Probabilistic ESD rate below the breakdown threshold.

    Piecewise-linear fit to Koons et al. 2000 (6th SCTC AFRL-VS-TR-
    20001578) on-orbit anomaly regression:

        rate(E) = 0                        for E < 0.5·E_BD
                = rate_sat · (E/E_BD − 0.5) / 0.5  for 0.5·E_BD ≤ E < E_BD
                = rate_sat                 for E ≥ E_BD

    with `rate_sat ≈ 1 per hour` — the asymptotic post-breakdown
    discharge cadence observed on SCATHA and CRRES. This is a
    conservative regression; handbook NASA-HDBK-4002A §5.5 warns
    that individual spacecraft can see higher or lower rates
    depending on cable-shield design.
    """
    if breakdown_field_v_m <= 0.0:
        raise ValueError("breakdown_field_v_m must be positive")
    if saturated_rate_per_hour < 0.0:
        raise ValueError("saturated_rate_per_hour must be non-negative")
    e = abs(internal_field_v_m)
    ratio = e / breakdown_field_v_m
    if ratio < 0.5:
        return 0.0
    if ratio >= 1.0:
        return saturated_rate_per_hour
    return saturated_rate_per_hour * (ratio - 0.5) / 0.5
