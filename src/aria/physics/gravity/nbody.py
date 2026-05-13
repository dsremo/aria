"""N-body integrator primitives for Pod A1 (§4.1, §4.4, §4.5, §4.6).

ARIA's cruise phase crosses many orders of magnitude in distance and
timescale: minutes around a flyby, decades across the cruise. A1's
design calls for three integrators (§4.4–§4.6 of the scope):

  - Gauss-Jackson 8th order (cruise default, conservative forces)
  - Dormand-Prince 8(7) adaptive RK (close-approach, high-eccentricity)
  - Wisdom-Holman 2nd order symplectic (very-long cruise between 1000 AU
    and target star)

This P0-2 module implements the two that are lowest-risk and highest
coverage for verification testing:

  1. ``rk4_step``   — classical 4th-order Runge–Kutta (Runge 1895,
     Kutta 1901). Self-contained, no external deps; good for
     verification against analytic two-body orbits.
  2. ``rk78_adaptive_step`` — Dormand-Prince 8(7) embedded pair
     (Prince & Dormand 1981 J. Comput. Appl. Math. 7(1) 67–75,
     DOI 10.1016/0771-050X(81)90010-3) with PI step-size control.

Gauss-Jackson 8 is deferred; Wisdom-Holman symplectic is now
implemented below (``integrate_whfast``).

The equation of motion for a test particle (the ship) in the gravity
field of N perturbers at known positions ``R_i(t)`` is

    dr/dt = v
    dv/dt = −Σ_i  G M_i (r − R_i(t)) / |r − R_i(t)|³     [m/s²]

with the cited assumptions (point-mass perturbers, restricted N-body,
externally supplied perturber positions) in §4.1 of the scope.

All vector quantities are numpy arrays of shape (3,). All times are
seconds past a user-chosen epoch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


# ──────────────────────────────────────────────────────────────────────
#  Kahan compensated summation (from Rebound study — CRITICAL)
# ──────────────────────────────────────────────────────────────────────

def kahan_add(
    total: np.ndarray, increment: np.ndarray, compensation: np.ndarray
) -> None:
    """Kahan compensated summation: total += increment with error tracking.

    Prevents floating-point drift over millions of accumulations.
    Critical for multi-century N-body integrations where naive summation
    loses ~1 bit per 10^4 additions, destroying energy conservation.

    Algorithm studied from Rebound's gravity.c (GPL, lines 246-484)
    and reimplemented from the standard Kahan (1965) formulation.

    Args:
        total: running sum (modified in-place)
        increment: value to add
        compensation: error compensation vector (modified in-place)
    """
    y = increment - compensation
    t = total + y
    compensation[:] = (t - total) - y
    total[:] = t


# ──────────────────────────────────────────────────────────────────────
#  Shadow / eclipse detection (from Poliastro study)
# ──────────────────────────────────────────────────────────────────────


def line_of_sight(
    r_sat: np.ndarray, r_light_source: np.ndarray, R_body: float
) -> bool:
    """Check if a satellite has line-of-sight to a light source.

    Returns True if the satellite can see the light source (not eclipsed
    by the central body of radius R_body). Both position vectors are
    relative to the central body.

    Used to toggle SRP on/off during eclipse passages. The shadow model
    is a simple cylindrical umbra cone — adequate for SRP toggling,
    not for precise penumbra modeling.

    Algorithm studied from poliastro events.py line_of_sight() (MIT).
    Formulation from Escobal (1985) "Methods of Orbit Determination".

    Args:
        r_sat: (3,) satellite position relative to central body [m]
        r_light_source: (3,) light source position relative to central body [m]
        R_body: radius of the eclipsing body [m]

    Returns:
        True if line-of-sight exists (no eclipse), False if eclipsed.
    """
    r1_norm = np.linalg.norm(r_sat)
    r2_norm = np.linalg.norm(r_light_source)

    if r1_norm < 1e-10 or r2_norm < 1e-10:
        return True

    cos_theta = np.dot(r_sat, r_light_source) / (r1_norm * r2_norm)
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    theta = np.arccos(cos_theta)

    # Angular radii of the body as seen from each position
    if R_body >= r1_norm or R_body >= r2_norm:
        return True  # inside the body — degenerate
    theta_1 = np.arccos(R_body / r1_norm)
    theta_2 = np.arccos(R_body / r2_norm)

    # Line of sight exists if sum of half-angles exceeds separation angle
    return (theta_1 + theta_2) >= theta


# ──────────────────────────────────────────────────────────────────────
#  Newtonian acceleration
# ──────────────────────────────────────────────────────────────────────


def acceleration_nbody(
    ship_position_m: np.ndarray,
    perturbers: list[tuple[np.ndarray, float]],
    softening_m: float = 0.0,
) -> np.ndarray:
    """Σ Newtonian acceleration from a list of point-mass perturbers.

    Args:
        ship_position_m: (3,) ship position in the same frame as the
            perturber positions.
        perturbers: list of ``(R_i_m, GM_i_m3_s2)`` pairs. R_i is a
            (3,) position; GM is the standard gravitational parameter.
        softening_m: optional Plummer softening length to prevent
            1/r³ blow-up on close approach (used only when the solver
            steps into a body; default 0 = strict Newtonian).

    Returns:
        Acceleration vector (3,) in m/s².
    """
    a = np.zeros(3, dtype=float)
    r_s = np.asarray(ship_position_m, dtype=float).reshape(3)
    s2 = softening_m * softening_m
    for R_i, gm_i in perturbers:
        R = np.asarray(R_i, dtype=float).reshape(3)
        diff = r_s - R
        r2 = float(np.dot(diff, diff)) + s2
        if r2 == 0.0:
            raise ValueError("ship position coincides with perturber position")
        r3 = r2 * np.sqrt(r2)
        a -= gm_i * diff / r3
    return a


# ──────────────────────────────────────────────────────────────────────
#  Classical RK4
# ──────────────────────────────────────────────────────────────────────

State = tuple[np.ndarray, np.ndarray]  # (r_m, v_m_s)
RhsFn = Callable[[float, np.ndarray, np.ndarray], np.ndarray]


def rk4_step(
    rhs: RhsFn,
    t: float,
    r: np.ndarray,
    v: np.ndarray,
    dt: float,
) -> State:
    """One classical RK4 step for the 2nd-order system
    ``dr/dt = v``, ``dv/dt = rhs(t, r, v)``.

    Args:
        rhs: callable ``(t, r, v) → a`` returning the acceleration
            (3,) m/s².
        t: current time (s).
        r: current position (3,) (m).
        v: current velocity (3,) (m/s).
        dt: step size (s).

    Returns:
        ``(r_new, v_new)`` advanced by ``dt`` seconds.

    Reference: Runge 1895 Math. Ann. 46 167; Kutta 1901; modern form in
    Hairer, Nørsett, Wanner *Solving Ordinary Differential Equations I*
    2nd ed (Springer, ISBN 978-3540566700) §II.1.
    """
    r = np.asarray(r, dtype=float).reshape(3)
    v = np.asarray(v, dtype=float).reshape(3)

    k1v = rhs(t, r, v)
    k1r = v

    k2v = rhs(t + 0.5 * dt, r + 0.5 * dt * k1r, v + 0.5 * dt * k1v)
    k2r = v + 0.5 * dt * k1v

    k3v = rhs(t + 0.5 * dt, r + 0.5 * dt * k2r, v + 0.5 * dt * k2v)
    k3r = v + 0.5 * dt * k2v

    k4v = rhs(t + dt, r + dt * k3r, v + dt * k3v)
    k4r = v + dt * k3v

    r_new = r + (dt / 6.0) * (k1r + 2.0 * k2r + 2.0 * k3r + k4r)
    v_new = v + (dt / 6.0) * (k1v + 2.0 * k2v + 2.0 * k3v + k4v)
    return r_new, v_new


# ──────────────────────────────────────────────────────────────────────
#  Dormand-Prince 8(7) adaptive step
# ──────────────────────────────────────────────────────────────────────
#
#  Implementation uses the Fehlberg 7(8) coefficients as given in
#  Hairer, Nørsett, Wanner *Solving Ordinary Differential Equations I*
#  2nd ed (ISBN 978-3540566700) §II.5 — the 13-stage embedded pair of
#  order 8(7). We bundle position and velocity into a single 6-vector
#  and treat the problem as a first-order ODE
#
#      dy/dt = f(t, y)     with y = (r, v), f = (v, a(t, r))
#
#  The Dormand-Prince 8(7) "DOPRI87" tableau would give slightly better
#  FSAL behavior; we use Fehlberg 7(8) here because its coefficients are
#  more widely tabulated and the verification cases are polynomial.

# Fehlberg 7(8) tableau (Fehlberg 1968 NASA TR R-287 Table I).
_F78_C = (
    0.0,
    2.0 / 27.0,
    1.0 / 9.0,
    1.0 / 6.0,
    5.0 / 12.0,
    0.5,
    5.0 / 6.0,
    1.0 / 6.0,
    2.0 / 3.0,
    1.0 / 3.0,
    1.0,
    0.0,
    1.0,
)

# ``A`` is a lower-triangular list of stage coefficients (rows 1..12).
_F78_A: tuple[tuple[float, ...], ...] = (
    (2.0 / 27.0,),
    (1.0 / 36.0, 1.0 / 12.0),
    (1.0 / 24.0, 0.0, 1.0 / 8.0),
    (5.0 / 12.0, 0.0, -25.0 / 16.0, 25.0 / 16.0),
    (1.0 / 20.0, 0.0, 0.0, 1.0 / 4.0, 1.0 / 5.0),
    (-25.0 / 108.0, 0.0, 0.0, 125.0 / 108.0, -65.0 / 27.0, 125.0 / 54.0),
    (31.0 / 300.0, 0.0, 0.0, 0.0, 61.0 / 225.0, -2.0 / 9.0, 13.0 / 900.0),
    (2.0, 0.0, 0.0, -53.0 / 6.0, 704.0 / 45.0, -107.0 / 9.0, 67.0 / 90.0, 3.0),
    (
        -91.0 / 108.0,
        0.0,
        0.0,
        23.0 / 108.0,
        -976.0 / 135.0,
        311.0 / 54.0,
        -19.0 / 60.0,
        17.0 / 6.0,
        -1.0 / 12.0,
    ),
    (
        2383.0 / 4100.0,
        0.0,
        0.0,
        -341.0 / 164.0,
        4496.0 / 1025.0,
        -301.0 / 82.0,
        2133.0 / 4100.0,
        45.0 / 82.0,
        45.0 / 164.0,
        18.0 / 41.0,
    ),
    (
        3.0 / 205.0,
        0.0,
        0.0,
        0.0,
        0.0,
        -6.0 / 41.0,
        -3.0 / 205.0,
        -3.0 / 41.0,
        3.0 / 41.0,
        6.0 / 41.0,
        0.0,
    ),
    (
        -1777.0 / 4100.0,
        0.0,
        0.0,
        -341.0 / 164.0,
        4496.0 / 1025.0,
        -289.0 / 82.0,
        2193.0 / 4100.0,
        51.0 / 82.0,
        33.0 / 164.0,
        12.0 / 41.0,
        0.0,
        1.0,
    ),
)

# 7th-order solution weights.
_F78_B7 = (
    41.0 / 840.0, 0.0, 0.0, 0.0, 0.0, 34.0 / 105.0, 9.0 / 35.0,
    9.0 / 35.0, 9.0 / 280.0, 9.0 / 280.0, 41.0 / 840.0, 0.0, 0.0,
)
# 8th-order solution weights.
_F78_B8 = (
    0.0, 0.0, 0.0, 0.0, 0.0, 34.0 / 105.0, 9.0 / 35.0,
    9.0 / 35.0, 9.0 / 280.0, 9.0 / 280.0, 0.0, 41.0 / 840.0, 41.0 / 840.0,
)


def _f78_stages(
    rhs: RhsFn,
    t: float,
    y: np.ndarray,
    dt: float,
) -> list[np.ndarray]:
    """Evaluate the 13 Fehlberg stages at ``(t, y)``.

    ``y`` is a 6-vector ``[r, v]``; rhs wraps to return ``[v, a(t,r)]``.
    """
    dim = y.shape[0]
    k: list[np.ndarray] = []
    for i in range(13):
        y_stage = y.copy()
        for j in range(i):
            y_stage = y_stage + dt * _F78_A[i - 1][j] * k[j] if i >= 1 else y_stage
        t_stage = t + _F78_C[i] * dt
        r_stage = y_stage[:3]
        v_stage = y_stage[3:]
        a_stage = rhs(t_stage, r_stage, v_stage)
        k.append(np.concatenate([v_stage, a_stage]))
        _ = dim  # silence unused
    return k


def rk78_adaptive_step(
    rhs: RhsFn,
    t: float,
    r: np.ndarray,
    v: np.ndarray,
    dt: float,
    rtol: float = 1.0e-10,
    atol: float = 1.0e-12,
) -> tuple[State, float, float]:
    """Fehlberg 7(8) single adaptive step.

    Returns:
        ``((r_new, v_new), dt_used, dt_next_suggestion)``.

        The returned ``dt_used`` is the step actually taken (== ``dt``
        for a successful step; this routine does not automatically
        retry a rejected step — that's the caller's job). The
        ``dt_next_suggestion`` is based on the error estimate:

            h_next = h · (tol / err)^(1/8)

        capped at 5× expansion and 1/5 contraction (Hairer et al.
        §II.5 recipe).

    Reference: Fehlberg 1968 NASA TR R-287; Hairer, Nørsett, Wanner
    *Solving Ordinary Differential Equations I* 2nd ed §II.5
    (ISBN 978-3540566700).
    """
    r = np.asarray(r, dtype=float).reshape(3)
    v = np.asarray(v, dtype=float).reshape(3)
    y = np.concatenate([r, v])

    k = _f78_stages(rhs, t, y, dt)

    y7 = y.copy()
    y8 = y.copy()
    for i in range(13):
        y7 = y7 + dt * _F78_B7[i] * k[i]
        y8 = y8 + dt * _F78_B8[i] * k[i]

    # Error estimate: L2 norm of the difference.
    err_vec = y8 - y7
    # Scaled norm (Hairer §II.4 eq. 4.11).
    sc = atol + rtol * np.maximum(np.abs(y), np.abs(y8))
    err_scaled = float(np.sqrt(np.mean((err_vec / sc) ** 2)))

    # Step size suggestion.
    if err_scaled == 0.0:
        factor = 5.0
    else:
        factor = 0.9 * err_scaled ** (-1.0 / 8.0)
    factor = min(max(factor, 0.2), 5.0)
    dt_next = dt * factor

    r_new = y8[:3]
    v_new = y8[3:]
    return (r_new, v_new), dt, dt_next


# ──────────────────────────────────────────────────────────────────────
#  N-body system orchestrator
# ──────────────────────────────────────────────────────────────────────


@dataclass
class NBodySystem:
    """Orchestrator for an N-body gravity integration.

    The perturbers can be either:
      - *static*: a list of ``(R_i_fn, GM_i)`` where ``R_i_fn(t) → (3,)``
        is a callable that returns the perturber position at time t.
        This is the general case used for a planet at known ephemeris.
      - *fixed*: a list of ``(R_i, GM_i)`` with constant position — used
        for the Sun in a heliocentric two-body verification test.

    Usage:
        sys = NBodySystem()
        sys.add_fixed_perturber(np.zeros(3), GM_SUN_M3_S2)
        r, v = sys.integrate(
            r0=np.array([AU_M, 0.0, 0.0]),
            v0=np.array([0.0, 29.78e3, 0.0]),
            t0=0.0, t_end=365.25*86400.0,
            dt=3600.0,
        )
    """

    moving_perturbers: list[tuple[Callable[[float], np.ndarray], float]] = field(
        default_factory=list
    )
    fixed_perturbers: list[tuple[np.ndarray, float]] = field(default_factory=list)
    # Extra force functions: callable(t, r, v) → (3,) acceleration [m/s²]
    # Used for non-gravitational perturbations (SRP, drag, J2, etc.)
    extra_forces: list[Callable] = field(default_factory=list)

    def add_fixed_perturber(self, position_m: np.ndarray, gm_m3_s2: float) -> None:
        if gm_m3_s2 <= 0.0:
            raise ValueError("gm_m3_s2 must be positive")
        self.fixed_perturbers.append(
            (np.asarray(position_m, dtype=float).reshape(3), gm_m3_s2)
        )

    def add_moving_perturber(
        self, position_fn: Callable[[float], np.ndarray], gm_m3_s2: float
    ) -> None:
        if gm_m3_s2 <= 0.0:
            raise ValueError("gm_m3_s2 must be positive")
        self.moving_perturbers.append((position_fn, gm_m3_s2))

    def add_force(self, force_fn: Callable) -> None:
        """Add a non-gravitational force (SRP, drag, J2, etc.).

        The function signature must be: force_fn(t, r, v) → (3,) accel [m/s²]

        Usage:
            from aria.physics.gravity.perturbations import j2_perturbation
            sys.add_force(lambda t, r, v: j2_perturbation(r, mu, J2, R_earth))
        """
        self.extra_forces.append(force_fn)

    def acceleration(self, t: float, r: np.ndarray, v: np.ndarray | None = None) -> np.ndarray:
        """Sum of all accelerations on a test particle at (t, r, v)."""
        perturbers: list[tuple[np.ndarray, float]] = list(self.fixed_perturbers)
        for pos_fn, gm in self.moving_perturbers:
            perturbers.append((pos_fn(t), gm))
        a = acceleration_nbody(r, perturbers)
        # Add non-gravitational forces
        if v is None:
            v = np.zeros(3)
        for force_fn in self.extra_forces:
            try:
                a = a + force_fn(t, r, v)
            except TypeError:
                a = a + force_fn(t, r)  # some forces don't need velocity
        return a

    def _rhs(self, t: float, r: np.ndarray, v: np.ndarray) -> np.ndarray:
        return self.acceleration(t, r)

    def integrate_rk4(
        self,
        r0: np.ndarray,
        v0: np.ndarray,
        t0: float,
        t_end: float,
        dt: float,
    ) -> tuple[np.ndarray, np.ndarray, float]:
        """Fixed-step RK4 integration from ``t0`` to ``t_end``.

        Returns ``(r_final, v_final, t_final)``.
        """
        if dt <= 0.0:
            raise ValueError("dt must be positive")
        if t_end <= t0:
            raise ValueError("t_end must be strictly greater than t0")
        r = np.asarray(r0, dtype=float).reshape(3).copy()
        v = np.asarray(v0, dtype=float).reshape(3).copy()
        t = float(t0)
        while t < t_end:
            h = min(dt, t_end - t)
            r, v = rk4_step(self._rhs, t, r, v, h)
            t += h
        return r, v, t

    def integrate_rk78(
        self,
        r0: np.ndarray,
        v0: np.ndarray,
        t0: float,
        t_end: float,
        dt_initial: float,
        rtol: float = 1.0e-10,
        atol: float = 1.0e-12,
        max_steps: int = 1_000_000,
    ) -> tuple[np.ndarray, np.ndarray, float, int]:
        """Adaptive Fehlberg 7(8) integration from ``t0`` to ``t_end``.

        Returns ``(r_final, v_final, t_final, n_steps)``.
        """
        if dt_initial <= 0.0:
            raise ValueError("dt_initial must be positive")
        if t_end <= t0:
            raise ValueError("t_end must be strictly greater than t0")
        r = np.asarray(r0, dtype=float).reshape(3).copy()
        v = np.asarray(v0, dtype=float).reshape(3).copy()
        t = float(t0)
        dt = float(dt_initial)
        n = 0
        while t < t_end and n < max_steps:
            h = min(dt, t_end - t)
            (r_new, v_new), _h_used, dt_next = rk78_adaptive_step(
                self._rhs, t, r, v, h, rtol=rtol, atol=atol
            )
            r = r_new
            v = v_new
            t += h
            dt = dt_next
            n += 1
        return r, v, t, n

    def integrate_whfast(
        self,
        r0: np.ndarray,
        v0: np.ndarray,
        t0: float,
        t_end: float,
        dt: float,
        central_gm: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Symplectic Wisdom-Holman integrator for long-duration cruise.

        Splits the Hamiltonian into Kepler (dominant central body) +
        perturbation (all other forces). The Kepler part is solved exactly
        via the universal variable formulation; perturbations are applied
        as velocity kicks. This guarantees bounded energy error regardless
        of integration duration — critical for multi-century cruise.

        Uses the kick-drift-kick (KDK) leapfrog ordering:
          1. Half-kick: v += 0.5 * dt * a_perturb
          2. Drift: Kepler advance (r, v) by dt under central GM
          3. Half-kick: v += 0.5 * dt * a_perturb

        Args:
            r0, v0: Initial state vectors (m, m/s)
            t0, t_end: Time span (seconds)
            dt: Fixed step size (seconds). Symplectic integrators require
                constant dt for energy conservation.
            central_gm: GM of the dominant central body (m³/s²). If None,
                uses the first fixed perturber's GM (typically the Sun).

        Returns:
            (r_final, v_final, t_final, energy_error) where energy_error
            is the relative energy change |ΔE/E₀|.

        References:
            Wisdom & Holman (1991) AJ 102 1528
            Rein & Tamayo (2015) MNRAS 452 376 (WHFast)
        """
        r = np.asarray(r0, dtype=float).reshape(3).copy()
        v = np.asarray(v0, dtype=float).reshape(3).copy()
        t = float(t0)

        # Identify central body GM
        if central_gm is None:
            if self.fixed_perturbers:
                central_gm = self.fixed_perturbers[0][1]
            else:
                raise ValueError("central_gm required when no fixed perturbers")

        # Kahan compensated summation accumulators
        v_comp = np.zeros(3)  # velocity compensation vector

        # Initial energy for error tracking
        E0 = _kepler_energy(r, v, central_gm)

        while t < t_end:
            h = min(dt, t_end - t)

            # Perturbation acceleration (everything except central body)
            a_perturb = self._perturbation_accel(t, r, central_gm)

            # Half-kick with Kahan compensated summation
            kahan_add(v, 0.5 * h * a_perturb, v_comp)

            # Kepler drift (exact solution via universal variable)
            r, v = _kepler_drift(r, v, central_gm, h)

            # Perturbation acceleration at new position
            a_perturb = self._perturbation_accel(t + h, r, central_gm)

            # Half-kick with Kahan compensated summation
            kahan_add(v, 0.5 * h * a_perturb, v_comp)

            t += h

        E_final = _kepler_energy(r, v, central_gm)
        energy_error = abs((E_final - E0) / E0) if abs(E0) > 1e-30 else 0.0

        return r, v, t, energy_error

    def _perturbation_accel(
        self, t: float, r: np.ndarray, central_gm: float,
        v: np.ndarray | None = None,
    ) -> np.ndarray:
        """Acceleration from all perturbers EXCEPT the central body.

        Includes non-gravitational forces (SRP, drag, J2, etc.) if any
        are registered via add_force().
        """
        a = np.zeros(3)
        # Fixed perturbers (skip the central body = first one)
        for i, (pos, gm) in enumerate(self.fixed_perturbers):
            if i == 0 and gm == central_gm:
                continue  # skip central body
            dr = r - pos
            dist = np.linalg.norm(dr)
            if dist > 1e-10:
                a -= gm * dr / (dist ** 3)
        # Moving perturbers
        for pos_fn, gm in self.moving_perturbers:
            dr = r - pos_fn(t)
            dist = np.linalg.norm(dr)
            if dist > 1e-10:
                a -= gm * dr / (dist ** 3)
        # Non-gravitational forces
        if v is None:
            v = np.zeros(3)
        for force_fn in self.extra_forces:
            try:
                a = a + force_fn(t, r, v)
            except TypeError:
                a = a + force_fn(t, r)
        return a


# ──────────────────────────────────────────────────────────────────────
#  Kepler drift solver (universal variable formulation)
# ──────────────────────────────────────────────────────────────────────

def _stumpff_c(z: float) -> float:
    """Stumpff function c(z) = (1 - cos(sqrt(z))) / z."""
    if abs(z) < 1e-10:
        return 1.0 / 2.0 - z / 24.0 + z * z / 720.0
    if z > 0:
        sz = np.sqrt(z)
        return (1.0 - np.cos(sz)) / z
    sz = np.sqrt(-z)
    return (np.cosh(sz) - 1.0) / (-z)


def _stumpff_s(z: float) -> float:
    """Stumpff function s(z) = (sqrt(z) - sin(sqrt(z))) / z^(3/2)."""
    if abs(z) < 1e-10:
        return 1.0 / 6.0 - z / 120.0 + z * z / 5040.0
    if z > 0:
        sz = np.sqrt(z)
        return (sz - np.sin(sz)) / (z * sz)
    sz = np.sqrt(-z)
    return (np.sinh(sz) - sz) / ((-z) * sz)


def _kepler_drift(
    r0: np.ndarray, v0: np.ndarray, gm: float, dt: float
) -> tuple[np.ndarray, np.ndarray]:
    """Advance (r, v) by dt under pure Kepler motion (two-body).

    Uses the universal variable (chi) formulation with Newton-Raphson
    iteration. Works for all orbit types (elliptic, parabolic, hyperbolic).

    References:
        Bate, Mueller & White (1971) "Fundamentals of Astrodynamics" §4.4
        Battin (1999) "An Introduction to the Mathematics and Methods
        of Astrodynamics" §5.7
    """
    r0_mag = np.linalg.norm(r0)
    v0_mag = np.linalg.norm(v0)
    rdotv = np.dot(r0, v0)

    # Specific orbital energy → semi-major axis
    alpha = 2.0 / r0_mag - v0_mag ** 2 / gm  # = 1/a

    # Initial guess for universal variable chi
    if abs(alpha) < 1e-15:
        # Parabolic
        chi = np.sqrt(gm) * dt / r0_mag
    elif alpha > 0:
        # Elliptic
        chi = np.sqrt(gm) * dt * alpha
    else:
        # Hyperbolic
        a_hyp = 1.0 / alpha
        chi = np.sign(dt) * np.sqrt(-a_hyp) * np.log(
            (-2.0 * gm * alpha * dt) /
            (rdotv + np.sign(dt) * np.sqrt(-gm * a_hyp) * (1.0 - r0_mag * alpha))
        )

    # Newton-Raphson iteration on the universal Kepler equation
    sqrt_gm = np.sqrt(gm)
    for _ in range(50):
        chi2 = chi * chi
        z = alpha * chi2
        c_z = _stumpff_c(z)
        s_z = _stumpff_s(z)

        # Universal Kepler equation: F(chi) = 0
        r_chi = chi2 * c_z + (rdotv / sqrt_gm) * chi * (1.0 - z * s_z) + r0_mag * (1.0 - z * c_z)
        F = (rdotv / sqrt_gm) * chi2 * c_z + (1.0 - r0_mag * alpha) * chi * chi2 * s_z + r0_mag * chi - sqrt_gm * dt
        dF = chi2 * c_z + (rdotv / sqrt_gm) * chi * (1.0 - z * s_z) + r0_mag * (1.0 - z * c_z)

        if abs(dF) < 1e-30:
            break
        chi -= F / dF

        if abs(F) < 1e-14 * sqrt_gm * abs(dt):
            break

    # Compute f, g, fdot, gdot (Lagrange coefficients)
    chi2 = chi * chi
    z = alpha * chi2
    c_z = _stumpff_c(z)
    s_z = _stumpff_s(z)

    r_new_mag = chi2 * c_z + (rdotv / sqrt_gm) * chi * (1.0 - z * s_z) + r0_mag * (1.0 - z * c_z)

    f = 1.0 - chi2 * c_z / r0_mag
    g = dt - chi * chi2 * s_z / sqrt_gm
    gdot = 1.0 - chi2 * c_z / r_new_mag
    fdot = sqrt_gm / (r0_mag * r_new_mag) * chi * (z * s_z - 1.0)

    r_new = f * r0 + g * v0
    v_new = fdot * r0 + gdot * v0

    return r_new, v_new


def _kepler_energy(r: np.ndarray, v: np.ndarray, gm: float) -> float:
    """Specific orbital energy: E = v²/2 - GM/r."""
    return 0.5 * np.dot(v, v) - gm / np.linalg.norm(r)
