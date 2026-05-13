"""Physics-based sensor noise models for navigation simulation.

Provides realistic noise, bias, and drift models for the sensors used
in spacecraft navigation:

- **Star tracker**: attitude determination from star images (arcsec accuracy)
- **IMU**: 3-axis gyro + accelerometer with bias + random walk
- **Coarse sun sensor**: sun direction with FOV + quantization
- **Magnetometer**: magnetic field vector with bias + noise
- **GPS receiver**: position + velocity with noise + dropout

Without physics-based sensor models, navigation filters can't be tested
against realistic inputs. With these models, Kalman filter designs can
be validated in simulation before flight.

Models studied from Basilisk src/simulation/sensors/ (ISC license).

References:
    Wertz, J.R. (1978). "Spacecraft Attitude Determination and Control."
    Kluwer. §6-8 on sensor models.

    Markley & Crassidis (2014). "Fundamentals of Spacecraft Attitude
    Determination and Control." Springer. §5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# ══════════════════════════════════════════════════════════════════
#  Base noise model
# ══════════════════════════════════════════════════════════════════

@dataclass
class GaussMarkov:
    """First-order Gauss-Markov process for sensor bias drift.

    db/dt = -b/tau + sigma * white_noise

    Captures the slow drift of sensor biases over time that typical
    flight sensors exhibit (gyro bias drift, accelerometer zero shift).

    Parameters:
        tau_s: correlation time constant [s]
        sigma: steady-state RMS [units match the measurement]
    """
    tau_s: float = 3600.0        # 1 hour correlation
    sigma: float = 0.0            # bias magnitude
    _state: float = field(default=0.0, repr=False)

    def step(self, dt_s: float, rng: Optional[np.random.RandomState] = None) -> float:
        """Advance the bias state by dt_s. Returns current bias."""
        if rng is None:
            rng = np.random.RandomState()
        # Discrete Gauss-Markov update
        a = math.exp(-dt_s / self.tau_s)
        w = rng.randn() * self.sigma * math.sqrt(1.0 - a ** 2)
        self._state = a * self._state + w
        return self._state

    def reset(self, value: float = 0.0) -> None:
        self._state = value


# ══════════════════════════════════════════════════════════════════
#  Star Tracker
# ══════════════════════════════════════════════════════════════════

@dataclass
class StarTracker:
    """Star tracker attitude sensor.

    Produces a noisy measurement of the spacecraft attitude (as an MRP
    or quaternion). Typical flight hardware achieves 1-30 arcsec
    accuracy with star pattern matching.

    Noise: Gaussian in attitude angle with configurable sigma.
    """
    accuracy_arcsec: float = 10.0    # 1-sigma attitude error [arcsec]
    fov_deg: float = 20.0             # field of view half-angle
    update_rate_hz: float = 10.0      # measurement rate

    def measure(
        self, true_sigma: np.ndarray, rng: Optional[np.random.RandomState] = None
    ) -> np.ndarray:
        """Measure the true MRP attitude with realistic noise.

        Args:
            true_sigma: (3,) true MRP attitude
            rng: random state for reproducibility

        Returns:
            Noisy MRP measurement
        """
        if rng is None:
            rng = np.random.RandomState()
        # Convert accuracy to MRP units (small-angle approximation)
        # 1 arcsec = 4.848e-6 rad; sigma_mrp ~ sigma_angle / 4 for small angles
        sigma_rad = self.accuracy_arcsec * 4.848e-6
        sigma_mrp = sigma_rad / 4.0
        noise = rng.randn(3) * sigma_mrp
        return true_sigma + noise


# ══════════════════════════════════════════════════════════════════
#  IMU (Inertial Measurement Unit)
# ══════════════════════════════════════════════════════════════════

@dataclass
class IMU:
    """3-axis gyro + accelerometer with bias + angular random walk.

    Typical MEMS IMU: gyro bias 1-100 deg/hr, angle random walk 0.1-1 deg/sqrt(hr).
    Flight-grade: gyro bias <0.01 deg/hr, ARW <0.001 deg/sqrt(hr).

    Model: omega_meas = omega_true + bias_gyro + ARW * white_noise
           accel_meas = accel_true + bias_acc + VRW * white_noise
    """
    gyro_arw_deg_sqrt_hr: float = 0.1         # angle random walk
    gyro_bias_deg_hr: float = 1.0             # static bias
    gyro_bias_drift_tau_s: float = 3600.0     # bias drift time constant
    acc_vrw_ug_sqrt_hz: float = 100.0         # velocity random walk [µg/√Hz]
    acc_bias_ug: float = 50.0                 # accelerometer bias [µg]

    _gyro_bias: GaussMarkov = field(default_factory=GaussMarkov)
    _acc_bias: GaussMarkov = field(default_factory=GaussMarkov)
    _initialized: bool = field(default=False, repr=False)

    def _init_processes(self) -> None:
        """Initialize Gauss-Markov processes from config."""
        # Gyro: deg/hr → rad/s
        gyro_sigma_rad_s = self.gyro_bias_deg_hr * math.pi / 180.0 / 3600.0
        self._gyro_bias = GaussMarkov(tau_s=self.gyro_bias_drift_tau_s, sigma=gyro_sigma_rad_s)

        # Accel: µg → m/s²
        acc_sigma_ms2 = self.acc_bias_ug * 9.81e-6
        self._acc_bias = GaussMarkov(tau_s=3600.0, sigma=acc_sigma_ms2)
        self._initialized = True

    def measure_gyro(
        self, omega_true: np.ndarray, dt_s: float,
        rng: Optional[np.random.RandomState] = None,
    ) -> np.ndarray:
        """Measure angular velocity [rad/s] with noise + bias."""
        if rng is None:
            rng = np.random.RandomState()
        if not self._initialized:
            self._init_processes()

        # Update bias drift
        bias = self._gyro_bias.step(dt_s, rng)
        # Angle random walk: sigma_arw in rad/sqrt(s)
        arw_rad_sqrt_s = self.gyro_arw_deg_sqrt_hr * math.pi / 180.0 / 60.0
        white_noise = rng.randn(3) * arw_rad_sqrt_s / math.sqrt(max(dt_s, 1e-6))
        return omega_true + bias + white_noise

    def measure_accel(
        self, accel_true: np.ndarray, dt_s: float,
        rng: Optional[np.random.RandomState] = None,
    ) -> np.ndarray:
        """Measure specific force [m/s²] with noise + bias."""
        if rng is None:
            rng = np.random.RandomState()
        if not self._initialized:
            self._init_processes()

        bias = self._acc_bias.step(dt_s, rng)
        # Velocity random walk converted from µg/√Hz
        vrw_ms2_sqrt_s = self.acc_vrw_ug_sqrt_hz * 9.81e-6
        white_noise = rng.randn(3) * vrw_ms2_sqrt_s / math.sqrt(max(dt_s, 1e-6))
        return accel_true + bias + white_noise


# ══════════════════════════════════════════════════════════════════
#  Coarse Sun Sensor
# ══════════════════════════════════════════════════════════════════

@dataclass
class CoarseSunSensor:
    """Coarse sun sensor — photodiode measuring cosine of sun angle.

    Returns the dot product of sensor normal with sun unit vector,
    but only when sun is within the field of view. Otherwise returns 0.
    """
    normal: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))
    fov_half_angle_deg: float = 75.0
    noise_sigma: float = 0.01            # fractional noise on cos reading
    quantization_bits: int = 12

    def measure(
        self, sun_dir_body: np.ndarray,
        rng: Optional[np.random.RandomState] = None,
    ) -> float:
        """Returns cos(angle) clipped to [0, 1], or 0 if outside FOV."""
        if rng is None:
            rng = np.random.RandomState()
        n = self.normal / max(np.linalg.norm(self.normal), 1e-15)
        s = sun_dir_body / max(np.linalg.norm(sun_dir_body), 1e-15)
        cos_angle = float(np.dot(n, s))

        # Outside FOV
        if cos_angle < math.cos(math.radians(self.fov_half_angle_deg)):
            return 0.0

        # Add noise
        cos_angle += rng.randn() * self.noise_sigma

        # Clamp to [0, 1]
        cos_angle = max(0.0, min(1.0, cos_angle))

        # Quantize
        levels = 2 ** self.quantization_bits
        cos_angle = round(cos_angle * (levels - 1)) / (levels - 1)

        return cos_angle


# ══════════════════════════════════════════════════════════════════
#  Magnetometer
# ══════════════════════════════════════════════════════════════════

@dataclass
class Magnetometer:
    """Three-axis magnetometer with bias + noise.

    Typical flight: 10-100 nT bias, 1-10 nT random noise.
    """
    bias_nT: np.ndarray = field(default_factory=lambda: np.zeros(3))
    noise_sigma_nT: float = 5.0
    scale_factor_error: float = 0.001   # 0.1% per axis

    def measure(
        self, B_true_nT: np.ndarray,
        rng: Optional[np.random.RandomState] = None,
    ) -> np.ndarray:
        """Measure magnetic field vector [nT]."""
        if rng is None:
            rng = np.random.RandomState()
        # Scale factor errors + bias + white noise
        scale = 1.0 + rng.randn(3) * self.scale_factor_error
        noise = rng.randn(3) * self.noise_sigma_nT
        return B_true_nT * scale + self.bias_nT + noise


# ══════════════════════════════════════════════════════════════════
#  GPS receiver
# ══════════════════════════════════════════════════════════════════

@dataclass
class GPSReceiver:
    """Single-frequency GPS receiver (LEO only).

    Typical: 10m position accuracy, 0.1 m/s velocity accuracy.
    Experiences signal loss at high altitudes (>3000km) and above the
    GPS constellation altitude (~20000km).
    """
    position_sigma_m: float = 10.0
    velocity_sigma_ms: float = 0.1
    max_altitude_m: float = 3000e3   # cutoff for reliable GPS
    dropout_probability: float = 0.01  # per-measurement chance of no fix

    def measure(
        self, r_true: np.ndarray, v_true: np.ndarray,
        R_earth: float = 6378137.0,
        rng: Optional[np.random.RandomState] = None,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Returns (r_meas, v_meas) or (None, None) if no fix."""
        if rng is None:
            rng = np.random.RandomState()
        altitude = np.linalg.norm(r_true) - R_earth

        # No fix above max altitude or random dropout
        if altitude > self.max_altitude_m or rng.random() < self.dropout_probability:
            return None, None

        r_meas = r_true + rng.randn(3) * self.position_sigma_m
        v_meas = v_true + rng.randn(3) * self.velocity_sigma_ms
        return r_meas, v_meas
