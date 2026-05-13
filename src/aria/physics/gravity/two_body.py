"""Two-body Kepler orbit analytics (§4.2–§4.3 of docs/pods/A1_ephemeris.md).

Reduction: one body of reduced mass in the gravitational field of a
central point mass with standard gravitational parameter `μ = G(m_1 + m_2)`.
The equation of motion for the relative position `r = r_1 − r_2` is

    d²r/dt² = −μ r / |r|³                               [m/s²]

(Bate-Mueller-White §1.5, ISBN 978-0486600611).

Conservation of energy → specific orbital energy
    ε = v² / 2 − μ / r                                   [m²/s²]
and on an orbit with semi-major axis `a`:
    ε = −μ / (2 a)                                       (bound, a > 0)
    ε = +μ / (2 |a|)                                     (hyperbolic, a < 0)
    ε = 0                                                (parabolic, a → ∞)

Combining gives the vis-viva equation:
    v² = μ ( 2/r − 1/a )                                 [m²/s²]
    (Vallado 4th ed eq. 1-22, ISBN 978-1881883180)

Kepler's third law (for a bound orbit of semi-major axis `a`):
    T = 2π √(a³ / μ)                                    [s]

Hohmann transfer (coplanar circular-to-circular, Curtis 3rd ed §6.3,
ISBN 978-0080977478):
    a_t = (r_1 + r_2) / 2                               [m]
    Δv_1 = √(μ/r_1) · ( √(2 r_2 / (r_1 + r_2)) − 1 )   [m/s]
    Δv_2 = √(μ/r_2) · ( 1 − √(2 r_1 / (r_1 + r_2)) )   [m/s]
    t_transfer = π √(a_t³ / μ)                          [s]
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def kepler_period(semi_major_axis_m: float, gravitational_parameter_m3_s2: float) -> float:
    """Kepler's third law: `T = 2π √(a³ / μ)` [s].

    Raises:
        ValueError: for non-positive inputs (only bound orbits have a
            finite period).
    """
    if semi_major_axis_m <= 0.0:
        raise ValueError("semi_major_axis_m must be positive for a bound orbit")
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    return 2.0 * math.pi * math.sqrt(
        semi_major_axis_m**3 / gravitational_parameter_m3_s2
    )


def vis_viva_speed(
    gravitational_parameter_m3_s2: float,
    radius_m: float,
    semi_major_axis_m: float,
) -> float:
    """Vis-viva equation `v² = μ (2/r − 1/a)` → `v` [m/s].

    Valid for any conic section:
      - ellipse: a > 0, 0 < r ≤ 2a
      - parabola: a → ∞, v² = 2μ/r
      - hyperbola: a < 0, any r > 0

    Raises:
        ValueError: on non-physical inputs or `r > 2 a` for an ellipse
            (point is outside the orbit).
    """
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    if radius_m <= 0.0:
        raise ValueError("radius_m must be positive")
    inner = gravitational_parameter_m3_s2 * (2.0 / radius_m - 1.0 / semi_major_axis_m)
    if inner < 0.0:
        raise ValueError(
            "vis-viva: inside the disallowed region (r > 2 a for an ellipse). "
            f"mu={gravitational_parameter_m3_s2}, r={radius_m}, a={semi_major_axis_m}"
        )
    return math.sqrt(inner)


def hohmann_transfer_delta_v(
    inner_radius_m: float,
    outer_radius_m: float,
    gravitational_parameter_m3_s2: float,
) -> tuple[float, float, float, float]:
    """Hohmann transfer between two coplanar circular orbits.

    Args:
        inner_radius_m: radius of the starting circular orbit (m).
        outer_radius_m: radius of the target circular orbit (m). Must be
            strictly greater than ``inner_radius_m``.
        gravitational_parameter_m3_s2: μ of the central body (m³/s²).

    Returns:
        ``(dv1, dv2, dv_total, t_transfer)`` in (m/s, m/s, m/s, s).

    Derivation: Curtis 3rd ed §6.3 eq. 6.2–6.5.
    """
    if inner_radius_m <= 0.0:
        raise ValueError("inner_radius_m must be positive")
    if outer_radius_m <= 0.0:
        raise ValueError("outer_radius_m must be positive")
    if outer_radius_m <= inner_radius_m:
        raise ValueError("outer_radius_m must be strictly greater than inner_radius_m")
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")

    mu = gravitational_parameter_m3_s2
    r1 = inner_radius_m
    r2 = outer_radius_m
    a_t = 0.5 * (r1 + r2)

    v_circ_1 = math.sqrt(mu / r1)
    v_circ_2 = math.sqrt(mu / r2)
    # Speed at perihelion of transfer ellipse (r = r_1, a = a_t).
    v_peri_t = math.sqrt(mu * (2.0 / r1 - 1.0 / a_t))
    # Speed at aphelion of transfer ellipse (r = r_2, a = a_t).
    v_apo_t = math.sqrt(mu * (2.0 / r2 - 1.0 / a_t))

    dv1 = v_peri_t - v_circ_1
    dv2 = v_circ_2 - v_apo_t
    dv_total = abs(dv1) + abs(dv2)
    t_transfer = math.pi * math.sqrt(a_t**3 / mu)
    return dv1, dv2, dv_total, t_transfer


def planetary_capture_delta_v(
    v_infinity_m_s: float,
    periapsis_radius_m: float,
    gravitational_parameter_m3_s2: float,
) -> float:
    """Vis-viva capture-orbit Δv at a planet (§1.1.8).

    The arriving ship has hyperbolic excess speed `v_∞` relative to the
    capturing body. At the periapsis of the chosen capture orbit the
    ship's instantaneous speed is
        v_hyp = √(v_∞² + 2 μ / r)                       [m/s]
    and the speed of a circular orbit at the same radius is
        v_circ = √(μ / r)                               [m/s]
    The impulsive Δv to circularize at periapsis is their difference:
        Δv = |v_hyp − v_circ|                           [m/s]

    References: Vallado 4th ed §6.3; Curtis 3rd ed §8.10.
    """
    if v_infinity_m_s < 0.0:
        raise ValueError("v_infinity_m_s must be non-negative")
    if periapsis_radius_m <= 0.0:
        raise ValueError("periapsis_radius_m must be positive")
    if gravitational_parameter_m3_s2 <= 0.0:
        raise ValueError("gravitational_parameter_m3_s2 must be positive")
    mu = gravitational_parameter_m3_s2
    r = periapsis_radius_m
    v_hyp = math.sqrt(v_infinity_m_s * v_infinity_m_s + 2.0 * mu / r)
    v_circ = math.sqrt(mu / r)
    return abs(v_hyp - v_circ)


@dataclass
class TwoBodyOrbit:
    """Analytic Kepler orbit container.

    Stores the four classical scalar orbit elements that are needed for
    the §4.2 primitives; the three angular elements (Ω, ω, ν) are not
    needed for energy/period/vis-viva work and are intentionally omitted.

    Attributes:
        semi_major_axis_m: a. Positive for ellipse, negative for hyperbola.
        eccentricity: e. 0 ≤ e < 1 ellipse, e = 1 parabola, e > 1 hyperbola.
        gravitational_parameter_m3_s2: μ of the central body.
    """

    semi_major_axis_m: float
    eccentricity: float
    gravitational_parameter_m3_s2: float

    @property
    def periapsis_radius_m(self) -> float:
        """r_p = a (1 − e). For a hyperbola use |a|(e − 1)."""
        if self.eccentricity < 1.0:
            return self.semi_major_axis_m * (1.0 - self.eccentricity)
        # hyperbola convention: a < 0, r_p = a(1 − e) is still correct
        # and positive.
        return self.semi_major_axis_m * (1.0 - self.eccentricity)

    @property
    def apoapsis_radius_m(self) -> float:
        """r_a = a (1 + e). Only defined for bound orbits (e < 1)."""
        if self.eccentricity >= 1.0:
            raise ValueError("apoapsis is undefined for unbound orbits (e ≥ 1)")
        return self.semi_major_axis_m * (1.0 + self.eccentricity)

    @property
    def period_s(self) -> float:
        """Orbital period by Kepler's third law."""
        if self.semi_major_axis_m <= 0.0:
            raise ValueError("period is undefined for unbound orbits (a ≤ 0)")
        return kepler_period(self.semi_major_axis_m, self.gravitational_parameter_m3_s2)

    @property
    def specific_energy_m2_s2(self) -> float:
        """ε = −μ / (2 a) (signed; negative for bound orbits)."""
        return -self.gravitational_parameter_m3_s2 / (2.0 * self.semi_major_axis_m)

    def speed_at_radius(self, radius_m: float) -> float:
        """Vis-viva: `v² = μ (2/r − 1/a)`."""
        return vis_viva_speed(
            self.gravitational_parameter_m3_s2, radius_m, self.semi_major_axis_m
        )
