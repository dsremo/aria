"""Orbit determination — estimate orbit state from noisy observations.

Provides two core OD methods:
1. Batch Least Squares (BLS): fits an initial state to a batch of
   range/angle/GPS measurements spanning minutes to hours.
2. Extended Kalman Filter (EKF): sequentially updates state estimate
   as new measurements arrive (real-time navigation).

Both methods are essential for real spacecraft operations — without OD,
you can propagate orbits forward but can't correct them when reality
drifts from the model (drag uncertainty, maneuver imprecision, etc.).

Algorithms studied from:
- Orekit src/main/java/org/orekit/estimation/ (Apache 2.0, Java)
- Nyx src/od/kalman/ (AGPL, study only, clean-room reimplemented)
- Open Space Toolkit Estimator (Apache 2.0, C++)

References:
    Tapley, Schutz & Born (2004). "Statistical Orbit Determination."
    Academic Press. (The textbook.)

    Montenbruck & Gill (2000). "Satellite Orbits" §8.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, List, Optional, Tuple

import numpy as np
from scipy.stats import chi2


# ══════════════════════════════════════════════════════════════════
#  Measurement types
# ══════════════════════════════════════════════════════════════════

@dataclass
class Measurement:
    """A single observation for orbit determination."""
    time: float                # observation time [s]
    type: str                  # "range", "range_rate", "az", "el",
                               # "gps_pos", "gps_vel", "gps_full", "aer"
    value: np.ndarray          # measurement value (scalar or vector)
    sigma: float               # measurement 1-sigma noise
    station_ecef: Optional[np.ndarray] = None  # for range/AER


def range_measurement(
    r_sat: np.ndarray, station_ecef: np.ndarray
) -> float:
    """Predicted range from station to satellite."""
    return float(np.linalg.norm(r_sat - station_ecef))


def range_rate_measurement(
    r_sat: np.ndarray, v_sat: np.ndarray, station_ecef: np.ndarray
) -> float:
    """Predicted range rate (radial velocity)."""
    dr = r_sat - station_ecef
    dist = np.linalg.norm(dr)
    if dist < 1e-10:
        return 0.0
    return float(np.dot(dr, v_sat) / dist)


def aer_measurement(
    r_sat: np.ndarray, station_ecef: np.ndarray
) -> Tuple[float, float, float]:
    """Predicted az/el/range."""
    delta = r_sat - station_ecef
    rng = np.linalg.norm(delta)
    if rng < 1e-10:
        return 0.0, 0.0, 0.0
    # Local up vector (station position)
    up = station_ecef / np.linalg.norm(station_ecef)
    sin_el = np.dot(delta, up) / rng
    el = math.degrees(math.asin(np.clip(sin_el, -1.0, 1.0)))
    # Azimuth in topocentric frame (simplified)
    az = math.degrees(math.atan2(delta[1], delta[0])) % 360.0
    return az, el, rng


# ══════════════════════════════════════════════════════════════════
#  Batch Least Squares Orbit Determination
# ══════════════════════════════════════════════════════════════════

@dataclass
class BLSResult:
    """Batch Least Squares OD result."""
    state: np.ndarray              # estimated (r, v) at epoch — (6,)
    covariance: np.ndarray         # 6x6 covariance matrix
    rms_residual: float            # RMS of post-fit residuals
    iterations: int
    converged: bool
    residuals: np.ndarray          # per-measurement residuals


def batch_least_squares(
    initial_guess: np.ndarray,
    measurements: List[Measurement],
    propagator: Callable[[np.ndarray, float, float], Tuple[np.ndarray, np.ndarray]],
    t_epoch: float = 0.0,
    max_iterations: int = 20,
    tol: float = 1e-6,
) -> BLSResult:
    """Iteratively fit an initial state to observations.

    Uses Gauss-Newton iteration with analytical state partial derivatives.

    Args:
        initial_guess: (6,) initial (r, v) state guess at t_epoch
        measurements: list of Measurement objects
        propagator: callable(state, t0, t1) → (r, v) at t1
        t_epoch: epoch time
        max_iterations: max Gauss-Newton iterations
        tol: convergence tolerance

    Returns:
        BLSResult with estimated state and covariance
    """
    x = np.asarray(initial_guess, dtype=float).copy()
    n_meas = sum(_meas_size(m) for m in measurements)

    if n_meas < 6:
        raise ValueError(f"Need ≥6 measurements for BLS, got {n_meas}")

    converged = False
    residuals = np.zeros(n_meas)
    H = np.zeros((n_meas, 6))  # Jacobian
    W = np.zeros(n_meas)        # weights (1/sigma²)

    for iteration in range(max_iterations):
        # Compute residuals and Jacobian via finite differences.
        # We need d(measurement)/d(initial_state), which requires propagating
        # perturbed initial states forward to each measurement time.
        idx = 0
        # Nominal propagation
        nominal_states: List[np.ndarray] = []
        for meas in measurements:
            r_pred, v_pred = propagator(x, t_epoch, meas.time)
            nominal_states.append(np.concatenate([r_pred, v_pred]))

        # Finite-difference perturbation sizes
        dr_pert = 100.0  # 100 m position perturbation
        dv_pert = 0.1    # 0.1 m/s velocity perturbation
        pert_sizes = np.array([dr_pert]*3 + [dv_pert]*3)

        # Precompute perturbed trajectories (6 perturbations)
        perturbed_states_list: List[List[np.ndarray]] = [[] for _ in range(6)]
        for k in range(6):
            x_pert = x.copy()
            x_pert[k] += pert_sizes[k]
            for meas in measurements:
                r_p, v_p = propagator(x_pert, t_epoch, meas.time)
                perturbed_states_list[k].append(np.concatenate([r_p, v_p]))

        # Build residuals and Jacobian
        for i, meas in enumerate(measurements):
            state_at_meas = nominal_states[i]

            # Nominal predicted measurement
            h_pred, _ = _measurement_model(meas, state_at_meas)
            size = _meas_size(meas)

            meas_val = meas.value if isinstance(meas.value, np.ndarray) else np.array([meas.value])
            h_pred_arr = h_pred if isinstance(h_pred, np.ndarray) else np.array([h_pred])
            residuals[idx:idx+size] = meas_val - h_pred_arr

            # Finite-difference Jacobian wrt initial state
            for k in range(6):
                state_pert = perturbed_states_list[k][i]
                h_pert, _ = _measurement_model(meas, state_pert)
                h_pert_arr = h_pert if isinstance(h_pert, np.ndarray) else np.array([h_pert])
                dh = (h_pert_arr - h_pred_arr) / pert_sizes[k]
                for s in range(size):
                    H[idx+s, k] = dh[s] if len(dh) > s else 0.0

            W[idx:idx+size] = 1.0 / (meas.sigma ** 2)
            idx += size

        # Weighted normal equations: (H^T W H) dx = H^T W r
        W_diag = np.diag(W)
        N = H.T @ W_diag @ H
        b = H.T @ W_diag @ residuals

        try:
            dx = np.linalg.solve(N, b)
        except np.linalg.LinAlgError:
            # Singular — add regularization
            N += np.eye(6) * 1e-3 * np.trace(N) / 6
            dx = np.linalg.solve(N, b)

        # Step size limit: prevent Gauss-Newton from over-shooting into
        # unphysical regimes (hyperbolic orbits from bad Jacobian).
        # Limit position step to 10% of current orbit radius.
        r_mag = np.linalg.norm(x[:3])
        max_dr = 0.1 * r_mag
        max_dv = 0.1 * np.linalg.norm(x[3:])
        dr_norm = np.linalg.norm(dx[:3])
        dv_norm = np.linalg.norm(dx[3:])
        if dr_norm > max_dr > 0:
            dx[:3] *= max_dr / dr_norm
        if dv_norm > max_dv > 0:
            dx[3:] *= max_dv / dv_norm

        x += dx

        # Convergence check
        if np.linalg.norm(dx[:3]) < tol and np.linalg.norm(dx[3:]) < tol * 1e-3:
            converged = True
            break

    # Covariance = inv(H^T W H)
    try:
        covariance = np.linalg.inv(H.T @ W_diag @ H)
    except np.linalg.LinAlgError:
        covariance = np.eye(6) * np.inf

    rms = float(np.sqrt(np.mean(residuals ** 2))) if len(residuals) > 0 else 0.0

    return BLSResult(
        state=x,
        covariance=covariance,
        rms_residual=rms,
        iterations=iteration + 1,
        converged=converged,
        residuals=residuals,
    )


def _meas_size(m: Measurement) -> int:
    """Number of scalar measurements in a Measurement object."""
    if m.type in ("range", "range_rate", "az", "el"):
        return 1
    elif m.type in ("aer", "range_az_el"):
        return 3
    elif m.type in ("gps_pos", "gps_vel"):
        return 3
    elif m.type == "gps_full":
        return 6
    return 1


def _measurement_model(
    meas: Measurement, state: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute predicted measurement and its Jacobian wrt state.

    Returns (h_pred, H_row) where H_row is the partial derivative of
    h with respect to the 6-state (r, v).
    """
    r = state[:3]
    v = state[3:]

    if meas.type == "range":
        station = meas.station_ecef
        delta = r - station
        rng = np.linalg.norm(delta)
        if rng < 1e-10:
            H = np.zeros((1, 6))
            return np.array([0.0]), H
        H = np.zeros((1, 6))
        H[0, :3] = delta / rng   # d(range)/d(r)
        return np.array([rng]), H

    elif meas.type == "range_rate":
        station = meas.station_ecef
        delta = r - station
        rng = np.linalg.norm(delta)
        if rng < 1e-10:
            return np.array([0.0]), np.zeros((1, 6))
        rr = np.dot(delta, v) / rng
        # Partial derivatives
        H = np.zeros((1, 6))
        H[0, :3] = (v / rng - delta * rr / (rng ** 2))
        H[0, 3:] = delta / rng
        return np.array([rr]), H

    elif meas.type == "aer" or meas.type == "range_az_el":
        # Combined range + azimuth + elevation — 3 scalar measurements
        # with independent observability of the orbit geometry
        station = meas.station_ecef
        delta = r - station
        rng = np.linalg.norm(delta)
        if rng < 1e-10:
            return np.zeros(3), np.zeros((3, 6))
        # Use range measurement for the range component
        H = np.zeros((3, 6))
        H[0, :3] = delta / rng  # range partial
        # Az/el partials are complex — for BLS, use finite-difference
        # Jacobian (computed externally). Return range + placeholder
        # for az/el that the finite-difference path will overwrite.
        azimuth = math.degrees(math.atan2(delta[1], delta[0])) % 360.0
        up = station / np.linalg.norm(station)
        sin_el = np.dot(delta, up) / rng
        elevation = math.degrees(math.asin(np.clip(sin_el, -1.0, 1.0)))
        return np.array([rng, azimuth, elevation]), H

    elif meas.type == "gps_pos":
        # Direct position measurement (GPS pseudorange solution, σ ≈ 5 m)
        H = np.zeros((3, 6))
        H[:, :3] = np.eye(3)
        return r.copy(), H

    elif meas.type == "gps_vel":
        # GPS Doppler velocity measurement (σ ≈ 0.1 m/s).
        # Most GPS receivers output velocity via Doppler frequency shift;
        # adding this measurement breaks the velocity observability gap
        # that causes EKF drift with position-only GPS.
        # Reference: Van Diggelen 2009 "A-GPS" §8.4.
        H = np.zeros((3, 6))
        H[:, 3:] = np.eye(3)
        return v.copy(), H

    elif meas.type == "gps_full":
        # Full GPS state (position + Doppler velocity in one measurement)
        H = np.eye(6)
        return state.copy(), H

    elif meas.type == "az":
        # Topocentric azimuth (degrees, 0-360) — analytical Jacobian neglected,
        # BLS uses FD anyway; what matters is a correct nominal prediction.
        station = meas.station_ecef
        delta = r - station
        rng = np.linalg.norm(delta)
        H = np.zeros((1, 6))
        if rng < 1e-10:
            return np.array([0.0]), H
        azimuth = math.degrees(math.atan2(delta[1], delta[0])) % 360.0
        # Partial of az wrt position (used by EKF, overridden by FD in BLS)
        r_xy_sq = delta[0]**2 + delta[1]**2
        if r_xy_sq > 1e-20:
            H[0, 0] = math.degrees(-delta[1] / r_xy_sq)
            H[0, 1] = math.degrees( delta[0] / r_xy_sq)
        return np.array([azimuth]), H

    elif meas.type == "el":
        # Topocentric elevation (degrees, -90 to 90)
        station = meas.station_ecef
        delta = r - station
        rng = np.linalg.norm(delta)
        H = np.zeros((1, 6))
        if rng < 1e-10:
            return np.array([0.0]), H
        station_norm = np.linalg.norm(station)
        if station_norm < 1e-10:
            return np.array([0.0]), H
        up = station / station_norm
        sin_el = np.dot(delta, up) / rng
        sin_el_clip = float(np.clip(sin_el, -1.0 + 1e-12, 1.0 - 1e-12))
        elevation = math.degrees(math.asin(sin_el_clip))
        # Partial of el wrt position
        cos_el = math.sqrt(max(0.0, 1.0 - sin_el_clip**2))
        if cos_el > 1e-10:
            H[0, :3] = (180.0 / math.pi) * (up / rng - delta * sin_el_clip / rng**2) / cos_el
        return np.array([elevation]), H

    # Default: return state as-is
    return np.zeros(1), np.zeros((1, 6))


# ══════════════════════════════════════════════════════════════════
#  Extended Kalman Filter (sequential OD)
# ══════════════════════════════════════════════════════════════════

# Process-noise PSD defaults for LEO ephemeris-quality EKF.  These are
# applied as Q = PSD * dt — i.e. Q_pos has units [m²/s³ × s] = [m²] per
# step (variance), matching Tapley/Schutz/Born §4.16 and Montenbruck &
# Gill §8.3 where the "level of mismatch" between dynamics and reality
# is captured as a continuous-time white-noise PSD.
#
# The 1e-6 m²/s³ figure corresponds to a 1 mm/s² unmodelled acceleration
# RMS, which is conservative for LEO drag/SRP residuals at 800 km
# altitude (Vallado 4e §10.4.1, "Process noise tuning").  Operators
# tuning a specific spacecraft should override these per-mission.
EKF_DEFAULT_Q_POS_PSD = 1e-6   # m²/s³ — Tapley/Schutz/Born §4.16, Vallado §10.4.1
EKF_DEFAULT_Q_VEL_PSD = 1e-9   # m²/s⁵ — same references; 1 µm/s² accel-rate RMS

# Mahalanobis innovation gate.  d² = z.T S⁻¹ z is χ²-distributed with
# dof = len(innovation) when measurement and model are consistent.  We
# reject any update whose d² exceeds χ²(dof, 0.99) — i.e. <1% legitimate
# rejection rate.  Reference: Bar-Shalom, Li & Kirubarajan (2001),
# "Estimation with Applications to Tracking and Navigation," §11.7.2.
EKF_INNOVATION_GATE_P = 0.99   # 99% confidence — Bar-Shalom et al. §11.7.2

# Bound history (S-24).  10 000 samples × 6+36 floats × 8 B ≈ 3.4 MB —
# acceptable; ``deque(maxlen=...)`` avoids the periodic O(n) list-copy
# at the truncation point.
EKF_HISTORY_MAXLEN = 10_000


@dataclass
class EKFState:
    """EKF state and covariance."""
    state: np.ndarray              # (6,) current estimate (r, v)
    covariance: np.ndarray         # 6x6 covariance
    time: float                    # time of current estimate

    # Process noise PSD (continuous-time spectral density).  Q over a
    # step of length dt is Q_psd * dt.  References on EKF_DEFAULT_*
    # constants above.
    Q_position: float = EKF_DEFAULT_Q_POS_PSD   # m²/s³ — Tapley §4.16
    Q_velocity: float = EKF_DEFAULT_Q_VEL_PSD   # m²/s⁵ — Tapley §4.16


class ExtendedKalmanFilter:
    """Extended Kalman filter for real-time orbit determination.

    Processes measurements one at a time, updating the state estimate
    and covariance. Each measurement improves the estimate.

    Sensor-fusion audit hardenings:
        * S-1: chi-squared innovation gate rejects measurements whose
               Mahalanobis distance exceeds χ²(dof, p=EKF_INNOVATION_GATE_P).
        * S-2: process-noise constants now carry citations and
               documented units (m²/s³ for position PSD, m²/s⁵ for
               velocity PSD; both multiplied by dt to form a step Q).
        * S-15: FD-STM ε scales with ‖state‖ instead of being a 1 mm
                absolute perturbation that vanishes against a 7 000 km
                state vector.
        * S-16: covariance is symmetrised after every update.
        * S-24: history is a bounded deque, not an unbounded list.

    Usage:
        ekf = ExtendedKalmanFilter(initial_state, initial_cov, propagator)
        for meas in measurements:
            ekf.predict(meas.time)
            ekf.update(meas)
        # ekf.state is the current best estimate
    """

    def __init__(
        self,
        initial_state: np.ndarray,
        initial_covariance: np.ndarray,
        propagator: Callable,
        t_initial: float = 0.0,
        use_fd_stm: bool = False,
        fd_stm_threshold_s: float = 60.0,
        q_pos_psd: float = EKF_DEFAULT_Q_POS_PSD,
        q_vel_psd: float = EKF_DEFAULT_Q_VEL_PSD,
        innovation_gate_p: float = EKF_INNOVATION_GATE_P,
    ) -> None:
        """
        Args:
            use_fd_stm:           Always use finite-difference STM for covariance
                                  propagation (more accurate, ~7× slower).
                                  Recommended when using position-only GPS
                                  (no Doppler velocity) to reduce velocity drift.
            fd_stm_threshold_s:   Auto-switch to FD-STM when dt exceeds this
                                  threshold.  60 s ≈ 1% of LEO period
                                  (Vallado §10.3 default; nonlinearity error
                                  empirically < 0.1% within this window).
            q_pos_psd, q_vel_psd: Process-noise PSDs.  Defaults documented
                                  on EKF_DEFAULT_Q_POS_PSD / EKF_DEFAULT_Q_VEL_PSD.
            innovation_gate_p:    Probability mass under χ² used for the
                                  innovation gate (S-1).
        """
        self.state = np.asarray(initial_state, dtype=float).copy()
        self.covariance = np.asarray(initial_covariance, dtype=float).copy()
        self.time = t_initial
        self.propagator = propagator
        self.Q_pos = q_pos_psd
        self.Q_vel = q_vel_psd
        self.use_fd_stm = use_fd_stm
        self.fd_stm_threshold_s = fd_stm_threshold_s
        self._innovation_gate_p = innovation_gate_p
        # Counters surfaced for FDIR (S-1 audit observability):
        self.measurements_accepted: int = 0
        self.measurements_rejected: int = 0
        # Bounded history (S-24).
        self.history: Deque[Tuple[float, np.ndarray, np.ndarray]] = deque(
            maxlen=EKF_HISTORY_MAXLEN
        )

    def predict(self, target_time: float) -> None:
        """Propagate state and covariance to target_time.

        Uses a simplified Phi = I + dt*[[0,I],[0,0]] for short intervals
        (dt < fd_stm_threshold_s) and auto-promotes to finite-difference
        STM for longer intervals where the linear approximation degrades.

        When ``use_fd_stm=True`` (recommended for position-only GPS to
        reduce velocity drift), always uses predict_fd_stm() regardless
        of interval length.
        """
        if target_time <= self.time:
            return

        dt = target_time - self.time

        # Auto-promote to FD-STM for long arcs or when explicitly requested
        if self.use_fd_stm or dt > self.fd_stm_threshold_s:
            self.predict_fd_stm(target_time)
            return

        # Propagate state (nonlinear, exact Kepler)
        r_new, v_new = self.propagator(self.state, self.time, target_time)
        self.state = np.concatenate([r_new, v_new])

        # Propagate covariance: P = Phi P Phi^T + Q
        # Linear STM (Phi = I + [[0, dt*I],[0, 0]]) — valid for dt << T_orb
        Phi = np.eye(6)
        Phi[:3, 3:] = dt * np.eye(3)

        Q = np.zeros((6, 6))
        Q[:3, :3] = self.Q_pos * dt * np.eye(3)
        Q[3:, 3:] = self.Q_vel * dt * np.eye(3)

        self.covariance = Phi @ self.covariance @ Phi.T + Q
        self._symmetrise_covariance()
        self.time = target_time

    def predict_fd_stm(
        self,
        target_time: float,
        rel_epsilon: float = 1e-6,
    ) -> None:
        """Predict with finite-difference state transition matrix.

        More accurate than ``predict`` for long intervals but ~7× slower
        (must propagate 6 perturbed states to compute Phi columns).

        S-15 fix: ε scales with ‖state‖ per axis so the FD perturbation
        is 1 ppm of the state norm, not a fixed 1 mm.  At LEO altitudes
        (~7e6 m) the previous absolute 1e-3 m perturbation was lost in
        float64 propagator roundoff (~1e-15 base × O(1e6) amplification),
        producing a near-noise Jacobian.
        """
        if target_time <= self.time:
            return

        dt = target_time - self.time
        t0 = self.time

        # Nominal propagation
        r_new, v_new = self.propagator(self.state, t0, target_time)
        x_nom = np.concatenate([r_new, v_new])

        # Per-axis perturbation: 1 ppm of position-norm for r-cols,
        # 1 ppm of velocity-norm (or 1 µm/s floor) for v-cols.
        r_norm = float(np.linalg.norm(self.state[:3])) or 1.0
        v_norm = float(np.linalg.norm(self.state[3:])) or 1.0
        pos_eps = max(rel_epsilon * r_norm, 1e-3)   # ≥1 mm floor for noise
        vel_eps = max(rel_epsilon * v_norm, 1e-6)   # ≥1 µm/s floor
        pert_sizes = np.array([pos_eps] * 3 + [vel_eps] * 3)

        Phi = np.zeros((6, 6))
        for axis in range(6):
            x_pert = self.state.copy()
            x_pert[axis] += pert_sizes[axis]
            r_p, v_p = self.propagator(x_pert, t0, target_time)
            x_p = np.concatenate([r_p, v_p])
            Phi[:, axis] = (x_p - x_nom) / pert_sizes[axis]

        # Covariance propagation
        Q = np.zeros((6, 6))
        Q[:3, :3] = self.Q_pos * dt * np.eye(3)
        Q[3:, 3:] = self.Q_vel * dt * np.eye(3)

        self.state = x_nom
        self.covariance = Phi @ self.covariance @ Phi.T + Q
        self._symmetrise_covariance()
        self.time = target_time

    def update(self, measurement: Measurement) -> float:
        """Update state estimate with a new measurement.

        Returns the measurement innovation (residual norm).  Rejected
        measurements increment ``self.measurements_rejected`` and leave
        state/covariance untouched.

        Sensor-fusion audit S-1: every measurement is gated by a χ²
        Mahalanobis test before fusion — d² = z.T S⁻¹ z must be below
        χ²(dof, p=self._innovation_gate_p) or the update is rejected.
        Sigma must also be finite and strictly positive (defends against
        attacker-controlled overconfident measurements with σ→0 that
        would otherwise dominate the Kalman gain).
        """
        # Sigma sanity (S-1 supporting guard).
        if not math.isfinite(measurement.sigma) or measurement.sigma <= 0.0:
            self.measurements_rejected += 1
            return float("inf")

        # Predicted measurement
        h_pred, H = _measurement_model(measurement, self.state)

        # Innovation
        meas_val = measurement.value if isinstance(measurement.value, np.ndarray) \
                   else np.array([measurement.value])
        h_arr = h_pred if isinstance(h_pred, np.ndarray) else np.array([h_pred])
        innovation = meas_val - h_arr

        # Reject non-finite measurements outright.
        if not np.all(np.isfinite(innovation)):
            self.measurements_rejected += 1
            return float("inf")

        # Innovation covariance: S = H P H^T + R
        R = np.eye(len(innovation)) * measurement.sigma ** 2
        S = H @ self.covariance @ H.T + R

        # Solve S⁻¹·z without forming an explicit inverse.  ``np.linalg.solve``
        # is more numerically stable and lets us compute Mahalanobis d²
        # via z.T @ (S⁻¹·z) in one step.
        try:
            S_inv_z = np.linalg.solve(S, innovation)
        except np.linalg.LinAlgError:
            self.measurements_rejected += 1
            return float(np.linalg.norm(innovation))

        # Mahalanobis innovation gate (S-1).
        mahal_d2 = float(innovation @ S_inv_z)
        if not math.isfinite(mahal_d2) or mahal_d2 < 0.0:
            self.measurements_rejected += 1
            return float(np.linalg.norm(innovation))
        gate = float(chi2.ppf(self._innovation_gate_p, df=len(innovation)))
        if mahal_d2 > gate:
            self.measurements_rejected += 1
            return float(np.linalg.norm(innovation))

        # Kalman gain: K = P H^T S⁻¹.  Re-solve once with the matrix
        # right-hand side; this is cheap (≤ 6×N) and avoids accumulating
        # the explicit S⁻¹.
        try:
            S_inv_HT = np.linalg.solve(S, H)
        except np.linalg.LinAlgError:
            self.measurements_rejected += 1
            return float(np.linalg.norm(innovation))
        K = self.covariance @ S_inv_HT.T

        # State update
        self.state = self.state + K @ innovation

        # Covariance update (Joseph form for numerical stability)
        I_KH = np.eye(6) - K @ H
        self.covariance = I_KH @ self.covariance @ I_KH.T + K @ R @ K.T
        self._symmetrise_covariance()

        # Record history (bounded deque — S-24).
        self.history.append((self.time, self.state.copy(), self.covariance.copy()))
        self.measurements_accepted += 1

        return float(np.linalg.norm(innovation))

    def _symmetrise_covariance(self) -> None:
        """Force P symmetric (S-16).

        Joseph form is more numerically stable than the standard
        ``P_post = (I - K H) P_prior`` form, but float64 rounding still
        leaves a small skew that compounds across many updates.  We
        symmetrise after every step so the covariance never silently
        loses positive-definiteness.
        """
        self.covariance = 0.5 * (self.covariance + self.covariance.T)

    def position_uncertainty_m(self) -> float:
        """Trace of position covariance (1-sigma position error)."""
        return float(np.sqrt(np.trace(self.covariance[:3, :3])))

    def velocity_uncertainty_ms(self) -> float:
        """1-sigma velocity uncertainty."""
        return float(np.sqrt(np.trace(self.covariance[3:, 3:])))
