"""Post-Newtonian correction to the tidal tensor (§4.2 of A2 scope).

In GR, for a Schwarzschild source of mass `M` observed at distance
`r ≫ r_s = 2GM/c²`, the "electric" part of the Weyl curvature tensor
reduces to the Newtonian form plus a leading correction of order
`r_s / r`:

    E^r_r = −(2GM/r³) · (1 + (3/2)(r_s/r) + …)           [1/s²]
    E^θ_θ = E^φ_φ = +(GM/r³) · (1 + (3/2)(r_s/r) + …)

(Hartle *Gravity* §9.3, ISBN 978-0805386622). For any perturber the
ship realistically encounters — Jupiter `r_s ≈ 2.82 m`, Sun `r_s ≈
2953 m` — the fractional PN correction at the closest planned approach
is `< 10⁻⁸`, so the Newtonian tensor from `tidal_tensor.py` is
effectively exact.

This module supplies the fractional multiplier so the caller can
either (a) apply it for high-PN-scrutiny segments of the mission or
(b) simply log it alongside the Newtonian tensor as a diagnostic.
"""

from __future__ import annotations

from .tidal_tensor import radial_tidal_acceleration  # re-export check-usage

# Exact SI speed of light (SI 2019 base-unit redefinition).
_SPEED_OF_LIGHT_M_S: float = 2.99792458e8


def schwarzschild_radius_m(perturber_gm_m3_s2: float) -> float:
    """Schwarzschild radius `r_s = 2 G M / c²` [m].

    Note we use `GM` (not `M` explicitly) because mission-design
    databases (DE440, WGS-84, etc.) publish `GM` directly to far higher
    accuracy than `M` alone.
    """
    if perturber_gm_m3_s2 <= 0.0:
        raise ValueError("perturber_gm_m3_s2 must be positive")
    return 2.0 * perturber_gm_m3_s2 / (_SPEED_OF_LIGHT_M_S**2)


def schwarzschild_pn_correction(
    perturber_gm_m3_s2: float, distance_to_perturber_m: float
) -> float:
    """Fractional PN multiplier `(1 + (3/2)(r_s / r))` − 1 [dimensionless].

    Returns the *correction* to the Newtonian tidal tensor, not the
    full multiplier. Values below ~1e-8 are effectively zero and should
    be logged as "Newtonian exact" by the caller.

    Example:
        >>> schwarzschild_pn_correction(1.267e17, 1.1 * 7.1492e7)  # Jupiter, 1.1 R_J
        5.4e-9  # negligible
    """
    if distance_to_perturber_m <= 0.0:
        raise ValueError("distance_to_perturber_m must be positive")
    r_s = schwarzschild_radius_m(perturber_gm_m3_s2)
    return 1.5 * r_s / distance_to_perturber_m


__all__ = [
    "schwarzschild_radius_m",
    "schwarzschild_pn_correction",
    "radial_tidal_acceleration",
]
