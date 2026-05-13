"""Gravitational time dilation — clock rate from Newtonian potential
(§4.4 of docs/pods/A2_tidal_tensor.md).

The weak-field Schwarzschild line element (Carroll §5.2, ISBN
978-0805387322) is

    ds² = −(1 + 2Φ/c²) c² dt² + (1 − 2Φ/c²)(dx² + dy² + dz²)

with `Φ` the Newtonian potential. For a stationary observer
(dx = dy = dz = 0),

    dτ² = −ds²/c² = (1 + 2Φ/c²) dt²
    dτ/dt = √(1 + 2Φ/c²) ≈ 1 + Φ/c²                     [dimensionless]

So a clock deeper in a potential well (more negative Φ) ticks *slower*
than a clock farther out. This is the effect measured by Pound & Rebka
(1960 PRL 4 337) and by GPS (Ashby 2003 Living Rev Relativity 6 1,
DOI 10.12942/lrr-2003-1) and by optical clocks at 1 m height differences
(Chou 2010 Science 329 1630, DOI 10.1126/science.1192720).

For the ARIA ship on cruise, Φ is dominated by whatever external body
is nearby; the ship's own self-gravity is ~10⁻²⁰ and is recorded but
flagged negligible.
"""

from __future__ import annotations

import numpy as np

# Exact speed of light (SI 2019).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8


def gravitational_potential(
    position_m: np.ndarray,
    perturbers: list[tuple[np.ndarray, float]],
) -> float:
    """Newtonian gravitational potential `Φ = −Σ GM_i / |r − R_i|` [m²/s²].

    Args:
        position_m: (3,) field point (m).
        perturbers: list of ``(R_i_m, GM_i_m3_s2)`` pairs.

    Returns:
        Signed Newtonian potential Φ at ``position_m`` in m²/s². Φ is
        negative everywhere except at infinity (where it is zero).
    """
    r = np.asarray(position_m, dtype=float).reshape(3)
    phi = 0.0
    for R_i, gm_i in perturbers:
        if gm_i <= 0.0:
            raise ValueError("perturber GM must be positive")
        sep = r - np.asarray(R_i, dtype=float).reshape(3)
        dist = float(np.linalg.norm(sep))
        if dist == 0.0:
            raise ValueError("position coincides with a perturber (Φ → −∞)")
        phi -= gm_i / dist
    return phi


def gravitational_time_dilation_rate(phi_m2_s2: float) -> float:
    """Clock rate `dτ/dt` in the weak-field limit.

    dτ/dt = 1 + Φ/c²                                      [dimensionless]

    Returns the *rate* itself (close to 1), not the fractional offset.
    The fractional offset is `(dτ/dt) − 1 = Φ/c²`.

    Note: uses the linearised (Φ/c² small) form, valid when
    |Φ|/c² ≪ 1. For Φ = −GM_sun/r at 1 AU, Φ/c² ≈ −9.9e-9, well within
    the linear regime.
    """
    return 1.0 + phi_m2_s2 / (SPEED_OF_LIGHT_M_S**2)


def uniform_field_time_dilation(
    g_m_s2: float, height_above_reference_m: float
) -> float:
    """Clock-rate fractional offset for a uniform gravitational field.

    For a small height difference `h` in a field of strength `g`, the
    potential difference is approximately `Φ = +g·h` (taking the
    reference at h=0 as Φ=0, higher points have higher Φ), so the
    fractional clock rate at height `h` relative to the reference is

        (dτ/dt) − 1 = g h / c²                           [dimensionless]

    Clocks at higher altitude run faster. This is the formula used by
    Pound & Rebka, Hafele-Keating (gravitational piece), and the
    altitude correction on atomic clocks.

    Args:
        g_m_s2: magnitude of the gravitational field (m/s²). Positive.
        height_above_reference_m: signed height of the clock relative
            to the reference (m). Positive = higher altitude = faster.

    Returns:
        ``(dτ/dt) − 1``, the dimensionless fractional rate offset.
    """
    if g_m_s2 < 0.0:
        raise ValueError("g_m_s2 must be non-negative")
    return g_m_s2 * height_above_reference_m / (SPEED_OF_LIGHT_M_S**2)
