"""Atomic Clock Timekeeping & Quantum Physics Systems for Interstellar Spacecraft.

Hard physics models for generation-ship timekeeping and quantum technology:

PART 1 — ATOMIC CLOCKS & TIMEKEEPING (VERIFIED)
  1. Deep Space Atomic Clock (DSAC) — NASA/JPL Mercury-199 ion trap
     Drift: 3.0×10⁻¹⁶/day (measured in orbit, Burt et al., Nature 2021)
     Stability: 3×10⁻¹⁵ at 23 days (Allan deviation)
     Error: <1 μs in 10 years
     DSAC-2: 10 kg, 10 L, 34 W — launching on VERITAS ~2028
  2. Optical Lattice Clock — Accuracy: 10⁻¹⁸ (100× better than DSAC)
     Laboratory only as of 2026 (JILA/NIST, PTB, RIKEN)
     NOT space-qualified — mark as PROJECTED technology
  3. Clock ensemble with Byzantine fault tolerance (3-clock voting)
  4. Relativistic time tracking (proper time τ vs coordinate time t)
  5. Pulsar timing cross-check (leverages relativistic_physics.py XNAV)

PART 2 — QUANTUM PHYSICS (VERIFIED vs SPECULATIVE clearly labeled)
  6. Quantum Key Distribution — VERIFIED (Micius satellite, Yin et al. Science 2017)
  7. Quantum Random Number Generator — VERIFIED (vacuum fluctuation based)
  8. Quantum Gravitational Sensor — VERIFIED principle (atom interferometry)
  9. Entanglement communication — DEBUNKED (no-communication theorem)
  10. Quantum vacuum thrusters — DEBUNKED (no confirmed thrust)

PART 3 — LATEST PHYSICS (2025-2026 findings, advisory only)
  11. DESI: dark energy may be weakening (Adame et al. 2024)
  12. Vera Rubin Observatory: 20 billion galaxy survey starting 2025
  13. LIGO O4: improved gravitational wave detection sensitivity

All constants SI.  Physics equations exact where possible.
Speculative items are clearly marked [SPECULATIVE] in docstrings and code.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()

# ══════════════════════════════════════════════════════════════════
# Physical constants (CODATA 2018 + clock-specific)
# ══════════════════════════════════════════════════════════════════
C = 299_792_458.0               # Speed of light [m/s]
YEAR_SECONDS = 365.25 * 86_400  # Julian year [s]
DAY_SECONDS = 86_400.0          # One day [s]
PLANCK_CONSTANT = 6.626_070_15e-34   # [J·s] (exact, 2019 SI)
BOLTZMANN_CONSTANT = 1.380_649e-23   # [J/K] (exact, 2019 SI)
HBAR = PLANCK_CONSTANT / (2.0 * math.pi)  # Reduced Planck [J·s]


# ══════════════════════════════════════════════════════════════════
# Verification status labels
# ══════════════════════════════════════════════════════════════════
class TechReadiness(Enum):
    """Technology readiness classification."""
    VERIFIED_FLIGHT = "verified_flight"        # Flown and measured in space
    VERIFIED_LAB = "verified_lab"              # Demonstrated in laboratory
    PROJECTED = "projected"                    # Solid physics, not yet built
    SPECULATIVE = "speculative"                # Theoretical, no confirmation
    DEBUNKED = "debunked"                      # Disproven or no evidence


# ══════════════════════════════════════════════════════════════════
# 1.  DEEP SPACE ATOMIC CLOCK (DSAC) — NASA/JPL
# ══════════════════════════════════════════════════════════════════
# Reference: Burt et al., "Demonstration of a trapped-ion atomic
# clock in space," Nature 595, 43-47 (2021).

# DSAC-1 measured parameters (from Nature 2021 paper):
DSAC_DRIFT_PER_DAY = 3.0e-16       # Fractional frequency drift [1/day]
DSAC_STABILITY_23DAY = 3.0e-15     # Allan deviation at 23 days
DSAC_ERROR_10YR_MICROSECONDS = 1.0 # Upper bound: <1 μs in 10 years

# DSAC-2 specifications (VERITAS mission, ~2028):
DSAC2_MASS_KG = 10.0
DSAC2_VOLUME_LITERS = 10.0
DSAC2_POWER_WATTS = 34.0

# Mercury-199 ion trap frequency:
HG199_HYPERFINE_HZ = 40.507_347_996_841_898e9  # ~40.5 GHz


@dataclass
class DSACClock:
    """Deep Space Atomic Clock (Mercury-199 trapped ion).

    [VERIFIED — FLIGHT HERITAGE]
    DSAC flew on the Orbital Test Bed satellite (June 2019 — Sept 2021).
    Achieved 3×10⁻¹⁶/day drift, the most stable clock ever in space.

    The generation ship carries 3 DSAC units for Byzantine fault tolerance.
    """
    readiness: TechReadiness = TechReadiness.VERIFIED_FLIGHT
    clock_id: int = 0
    drift_per_day: float = DSAC_DRIFT_PER_DAY
    mass_kg: float = DSAC2_MASS_KG
    power_watts: float = DSAC2_POWER_WATTS
    volume_liters: float = DSAC2_VOLUME_LITERS

    # State tracking
    cumulative_error_s: float = 0.0     # Accumulated time error [seconds]
    operational_days: float = 0.0       # Total days in operation
    degradation_factor: float = 1.0     # 1.0 = nominal, increases with age
    # Cumulative contribution from the Pod M3 Webb 2011 α̇/α upper
    # bound, tracked separately from the instrument-drift
    # cumulative_error_s so that regression tests anchored on the
    # measured DSAC drift remain exact. For any realistic mission
    # this is ~1e-17 per day and is buried under DSAC's 3e-16/day
    # instrument floor, but the bookkeeping row is still reported.
    m3_alpha_drift_cumulative_s: float = 0.0
    _rng: random.Random = field(default_factory=lambda: random.Random(42))
    is_operational: bool = True
    last_calibration_day: float = 0.0

    def tick(self, days: float = 1.0) -> float:
        """Advance clock by `days` and return accumulated error in seconds.

        Two drift contributions:
          1. Instrument drift: `drift_per_day × t × DAY_SECONDS ×
             degradation_factor` — the DSAC measured systematic.
          2. Fundamental-constant drift: the Pod M3 Webb 2011 /
             Dzuba-Flambaum-Webb 1999 contribution `K_α × (α̇/α) × t`
             where DSAC is the Cs-133 hyperfine class with
             K_α ≈ 2.83. At the Webb bound 3.17e-24 /s this adds
             ~9e-24 per second of fractional-frequency error —
             utterly negligible vs the DSAC 3.5e-21 /s instrument
             floor but tracked for bookkeeping.
        """
        if not self.is_operational:
            return self.cumulative_error_s

        from aria.physics.dark_sector import clock_frequency_drift_from_alpha

        self.operational_days += days
        daily_error_s = self.drift_per_day * days * DAY_SECONDS * self.degradation_factor
        self.cumulative_error_s += daily_error_s

        # Track the Pod M3 Webb 2011 α̇/α upper-bound contribution
        # separately. Cs-133 hyperfine K_α ≈ 2.83 gives an M3 time
        # error of ~8e-18 s per day at the Webb bound — well below
        # the instrument floor but tracked for M3 bookkeeping.
        tick_seconds = days * DAY_SECONDS
        m3_frac_shift = clock_frequency_drift_from_alpha(
            mission_duration_s=tick_seconds,
            clock_name="Cs-133-hfs",
        )
        self.m3_alpha_drift_cumulative_s += m3_frac_shift * self.degradation_factor

        return self.cumulative_error_s

    def simulate_year(self) -> dict[str, Any]:
        """Simulate one year of operation.  Returns status dict."""
        if not self.is_operational:
            return self._status("offline")

        error_before = self.cumulative_error_s
        self.tick(365.25)

        # Degradation: ~0.1% per year in drift performance
        self.degradation_factor *= 1.001

        # Random failure probability: 0.01%/year for space-qualified hardware
        if self._rng.random() < 0.0001:
            self.is_operational = False
            logger.warning("dsac_clock_failure",
                           clock_id=self.clock_id,
                           days=self.operational_days)
            return self._status("failed")

        return self._status("nominal", error_before)

    def calibrate(self, reference_error_s: float = 0.0) -> None:
        """Calibrate clock against external reference (e.g., pulsar timing).

        In practice, XNAV pulsar fixes provide time transfer accuracy
        of ~100 ns (NASA SEXTANT, 2018).
        """
        self.cumulative_error_s = reference_error_s
        self.last_calibration_day = self.operational_days

    def error_after_days(self, days: float) -> float:
        """Predict accumulated error [seconds] after `days` from now.

        Pure calculation — does not modify state.
        """
        return self.drift_per_day * days * DAY_SECONDS * self.degradation_factor

    def error_after_years(self, years: float) -> float:
        """Predict accumulated error [seconds] after `years`."""
        return self.error_after_days(years * 365.25)

    def _status(self, status: str, error_before: float = 0.0) -> dict[str, Any]:
        return {
            "clock_type": "DSAC",
            "clock_id": self.clock_id,
            "readiness": self.readiness.value,
            "status": status,
            "operational_days": self.operational_days,
            "cumulative_error_s": self.cumulative_error_s,
            "error_gained_s": self.cumulative_error_s - error_before,
            "degradation_factor": self.degradation_factor,
            "mass_kg": self.mass_kg,
            "power_watts": self.power_watts,
        }


# ══════════════════════════════════════════════════════════════════
# 2.  OPTICAL LATTICE CLOCK  (next-generation)
# ══════════════════════════════════════════════════════════════════
# Reference: Bothwell et al., JILA, "Resolving the gravitational
# redshift across a millimetre-scale atomic sample," Nature 602,
# 420-424 (2022).  Accuracy: 10⁻¹⁸ demonstrated in lab.

OPTICAL_LATTICE_ACCURACY = 1.0e-18  # Fractional accuracy
OPTICAL_LATTICE_DRIFT_PER_DAY = 1.0e-18  # Conservative estimate


@dataclass
class OpticalLatticeClock:
    """Optical Lattice Clock (Strontium-87 or Ytterbium-171).

    [VERIFIED — LABORATORY ONLY]
    As of 2026, optical lattice clocks achieve 10⁻¹⁸ accuracy in
    laboratory settings (JILA, NIST, PTB, RIKEN).  NOT space-qualified.
    For generation ship: secondary reference if technology matures for
    flight during the construction phase.

    100× more accurate than DSAC, but requires:
    - Ultra-high vacuum (10⁻¹¹ mbar)
    - Laser cooling system (~200 W total)
    - Vibration isolation
    """
    readiness: TechReadiness = TechReadiness.VERIFIED_LAB
    clock_id: int = 0
    drift_per_day: float = OPTICAL_LATTICE_DRIFT_PER_DAY
    accuracy: float = OPTICAL_LATTICE_ACCURACY
    mass_kg: float = 50.0       # ESTIMATE — spaceflight-hardened version (lab: 200 kg; NIST SrI clock: Bloom 2014 Nature 506 71)
    power_watts: float = 200.0  # ESTIMATE — laser cooling system (Bloom 2014 Nature 506 71 lab power ~1 kW; projected reduction)
    volume_liters: float = 80.0  # ESTIMATE — miniaturized volume for flight

    cumulative_error_s: float = 0.0
    operational_days: float = 0.0
    degradation_factor: float = 1.0
    is_operational: bool = True
    _rng: random.Random = field(default_factory=lambda: random.Random(43))

    def tick(self, days: float = 1.0) -> float:
        """Advance clock.  Same drift model as DSAC but 100× better."""
        if not self.is_operational:
            return self.cumulative_error_s

        self.operational_days += days
        daily_error_s = self.drift_per_day * days * DAY_SECONDS * self.degradation_factor
        self.cumulative_error_s += daily_error_s
        return self.cumulative_error_s

    def simulate_year(self) -> dict[str, Any]:
        """Simulate one year.  Higher failure rate than DSAC (not space-hardened)."""
        if not self.is_operational:
            return self._status("offline")

        error_before = self.cumulative_error_s
        self.tick(365.25)

        # Faster degradation: laser diodes degrade ~0.5%/year
        self.degradation_factor *= 1.005

        # Higher failure probability: 0.5%/year (not space-qualified)
        if self._rng.random() < 0.005:
            self.is_operational = False
            logger.warning("optical_clock_failure",
                           clock_id=self.clock_id,
                           days=self.operational_days)
            return self._status("failed")

        return self._status("nominal", error_before)

    def _status(self, status: str, error_before: float = 0.0) -> dict[str, Any]:
        return {
            "clock_type": "OpticalLattice",
            "clock_id": self.clock_id,
            "readiness": self.readiness.value,
            "status": status,
            "operational_days": self.operational_days,
            "cumulative_error_s": self.cumulative_error_s,
            "error_gained_s": self.cumulative_error_s - error_before,
            "degradation_factor": self.degradation_factor,
        }


# ══════════════════════════════════════════════════════════════════
# 3.  CLOCK ENSEMBLE — Byzantine Fault Tolerance
# ══════════════════════════════════════════════════════════════════

def clock_ensemble_average(clock_readings: list[float],
                           weights: list[float] | None = None) -> float:
    """Weighted average of multiple clock readings.

    For N clocks, the ensemble stability improves by ~1/√N over a
    single clock (assuming uncorrelated noise).  With 3 DSAC clocks:
    ensemble stability ≈ DSAC_stability / √3.

    Args:
        clock_readings: list of time readings [seconds] from each clock.
        weights: optional weights (default: equal weighting).

    Returns:
        Ensemble-averaged time [seconds].
    """
    n = len(clock_readings)
    if n == 0:
        raise ValueError("Need at least one clock reading")
    if weights is None:
        weights = [1.0 / n] * n
    else:
        total = sum(weights)
        weights = [w / total for w in weights]

    return sum(r * w for r, w in zip(clock_readings, weights))


def byzantine_clock_vote(readings: list[float],
                         max_deviation_s: float = 1e-6) -> tuple[float, list[int]]:
    """Byzantine fault-tolerant clock voting.

    With 3 clocks, tolerates 1 faulty clock (Byzantine generals: need
    3f+1 to tolerate f faults, so 3 clocks tolerates 0 Byzantine faults
    but 1 crash fault via majority vote).

    Algorithm:
    1. Compute median of all readings.
    2. Reject any reading deviating more than max_deviation_s from median.
    3. Average the remaining readings.

    Args:
        readings: clock time readings [seconds].
        max_deviation_s: maximum acceptable deviation from median.

    Returns:
        (voted_time, list of rejected clock indices).
    """
    if len(readings) < 2:
        return readings[0] if readings else 0.0, []

    sorted_readings = sorted(readings)
    median = sorted_readings[len(sorted_readings) // 2]

    rejected = []
    accepted = []
    for i, r in enumerate(readings):
        if abs(r - median) > max_deviation_s:
            rejected.append(i)
        else:
            accepted.append(r)

    if not accepted:
        # All clocks disagree — fall back to median
        return median, rejected

    voted_time = sum(accepted) / len(accepted)
    return voted_time, rejected


def ensemble_stability_improvement(n_clocks: int,
                                   single_clock_stability: float) -> float:
    """Ensemble stability: σ_ensemble = σ_single / √N.

    Valid when clock noise is uncorrelated (different trap instances).

    Args:
        n_clocks: number of clocks in ensemble.
        single_clock_stability: Allan deviation of one clock.

    Returns:
        Ensemble Allan deviation.
    """
    if n_clocks < 1:
        raise ValueError("Need at least 1 clock")
    return single_clock_stability / math.sqrt(n_clocks)


# ══════════════════════════════════════════════════════════════════
# 4.  RELATIVISTIC TIME TRACKING
# ══════════════════════════════════════════════════════════════════

def lorentz_gamma(v: float) -> float:
    """Lorentz factor γ = 1/√(1 - v²/c²).

    Args:
        v: velocity [m/s], must be < c.

    Returns:
        Dimensionless γ ≥ 1.0.
    """
    beta = v / C
    if beta >= 1.0:
        raise ValueError(f"Velocity {v:.3e} m/s >= c — unphysical")
    return 1.0 / math.sqrt(1.0 - beta * beta)


def proper_time_elapsed(coordinate_time_s: float, v: float) -> float:
    """Ship proper time τ for a given Earth coordinate time t.

    dτ = dt/γ = dt × √(1 - v²/c²)

    At 0.1c for 1000 Earth years:
        γ = 1/√(1-0.01) ≈ 1.00504
        τ = 1000/1.00504 ≈ 994.987 years
        Crew ages ~5 years less than Earth observers.

    Args:
        coordinate_time_s: Earth coordinate time [seconds].
        v: ship velocity [m/s].

    Returns:
        Proper time [seconds] experienced by crew.
    """
    gamma = lorentz_gamma(v)
    return coordinate_time_s / gamma


def coordinate_time_from_proper(proper_time_s: float, v: float) -> float:
    """Earth coordinate time t from ship proper time τ.

    t = τ × γ
    """
    gamma = lorentz_gamma(v)
    return proper_time_s * gamma


@dataclass
class RelativisticTimeTracker:
    """Tracks ship proper time vs Earth coordinate time continuously.

    Maintains running totals as the ship accelerates/decelerates.
    Navigation requires BOTH time references:
    - Proper time τ: for onboard systems, crew schedules, biology
    - Coordinate time t: for star chart positions, communication windows

    The tracker accumulates corrections over discrete velocity steps,
    handling arbitrary acceleration profiles.
    """
    cumulative_proper_time_s: float = 0.0
    cumulative_coordinate_time_s: float = 0.0
    current_velocity_ms: float = 0.0
    cumulative_time_difference_s: float = 0.0  # t - τ

    def advance(self, coordinate_dt_s: float, velocity_ms: float) -> dict[str, float]:
        """Advance by coordinate_dt_s at given velocity.

        Args:
            coordinate_dt_s: Earth time step [seconds].
            velocity_ms: ship velocity during this step [m/s].

        Returns:
            Dict with proper_dt_s, coordinate_dt_s, gamma, difference_s.
        """
        gamma = lorentz_gamma(velocity_ms)
        proper_dt_s = coordinate_dt_s / gamma

        self.cumulative_coordinate_time_s += coordinate_dt_s
        self.cumulative_proper_time_s += proper_dt_s
        self.current_velocity_ms = velocity_ms
        self.cumulative_time_difference_s = (
            self.cumulative_coordinate_time_s - self.cumulative_proper_time_s
        )

        return {
            "proper_dt_s": proper_dt_s,
            "coordinate_dt_s": coordinate_dt_s,
            "gamma": gamma,
            "difference_s": coordinate_dt_s - proper_dt_s,
            "cumulative_proper_s": self.cumulative_proper_time_s,
            "cumulative_coordinate_s": self.cumulative_coordinate_time_s,
            "cumulative_difference_s": self.cumulative_time_difference_s,
        }

    def advance_years(self, coordinate_years: float,
                      velocity_ms: float) -> dict[str, float]:
        """Convenience: advance by years."""
        return self.advance(coordinate_years * YEAR_SECONDS, velocity_ms)

    def proper_time_years(self) -> float:
        """Current ship proper time in years."""
        return self.cumulative_proper_time_s / YEAR_SECONDS

    def coordinate_time_years(self) -> float:
        """Current Earth coordinate time in years."""
        return self.cumulative_coordinate_time_s / YEAR_SECONDS

    def time_difference_years(self) -> float:
        """Accumulated time dilation difference in years."""
        return self.cumulative_time_difference_s / YEAR_SECONDS


# ══════════════════════════════════════════════════════════════════
# 5.  1000-YEAR TIMEKEEPING ANALYSIS
# ══════════════════════════════════════════════════════════════════

def dsac_error_over_duration(days: float,
                             drift_per_day: float = DSAC_DRIFT_PER_DAY) -> float:
    """Calculate accumulated time error for DSAC over a given duration.

    Error = drift_rate × duration × seconds_per_day
    At 3×10⁻¹⁶/day over 1000 years (365,250 days):
        error = 3e-16 × 365250 × 86400 ≈ 0.00947 seconds

    Note: the 0.11 second figure sometimes cited uses a more
    conservative drift model including random walk. Our calculation
    uses the measured systematic drift only.

    Args:
        days: duration in days.
        drift_per_day: fractional frequency drift per day.

    Returns:
        Accumulated time error [seconds].
    """
    return drift_per_day * days * DAY_SECONDS


def dsac_error_1000_years() -> float:
    """Shortcut: DSAC error over 1000 years with nominal drift."""
    return dsac_error_over_duration(1000.0 * 365.25)


def optical_lattice_error_1000_years() -> float:
    """Optical lattice clock error over 1000 years."""
    return dsac_error_over_duration(1000.0 * 365.25,
                                    drift_per_day=OPTICAL_LATTICE_DRIFT_PER_DAY)


def time_dilation_correction_1000yr(velocity_fraction_c: float) -> dict[str, float]:
    """Calculate relativistic correction needed over 1000 Earth years.

    At 0.1c: γ ≈ 1.00504, τ ≈ 994.987 years, Δ ≈ 5.013 years.

    Args:
        velocity_fraction_c: velocity as fraction of c (e.g. 0.1 for 0.1c).

    Returns:
        Dict with gamma, proper_time_years, difference_years.
    """
    v = velocity_fraction_c * C
    gamma = lorentz_gamma(v)
    proper_years = 1000.0 / gamma
    diff_years = 1000.0 - proper_years
    return {
        "velocity_fraction_c": velocity_fraction_c,
        "gamma": gamma,
        "earth_years": 1000.0,
        "proper_time_years": proper_years,
        "difference_years": diff_years,
        "difference_seconds": diff_years * YEAR_SECONDS,
    }


# ══════════════════════════════════════════════════════════════════
# 6.  QUANTUM KEY DISTRIBUTION — [VERIFIED — FLIGHT HERITAGE]
# ══════════════════════════════════════════════════════════════════
# Reference: Yin et al., "Satellite-based entanglement distribution
# over 1200 kilometers," Science 356, 1140-1144 (2017).
# Micius satellite demonstrated QKD at 1,200 km, key rate ~1 kbps.

QKD_MICIUS_RANGE_KM = 1200.0          # Demonstrated range
QKD_MICIUS_KEY_RATE_BPS = 1000.0      # ~1 kbit/s at 1200 km
QKD_PHOTON_LOSS_DB_PER_KM = 0.2       # Fiber loss (space: diffraction limited)


@dataclass
class QuantumKeyDistribution:
    """Quantum Key Distribution system for secure ship communications.

    [VERIFIED — FLIGHT HERITAGE]
    Based on BB84 protocol (Bennett & Brassard, 1984) with decoy states.
    Demonstrated in space by Micius satellite (2017).

    For generation ship: internal secure communication between ship
    sections. NOT useful for Earth-ship communication beyond ~1 AU
    due to photon loss (inverse square law).

    HONEST NOTE: QKD does NOT use entanglement for FTL communication.
    It uses quantum states to detect eavesdropping on a classical
    channel. The key is established at the speed of light, not faster.
    """
    readiness: TechReadiness = TechReadiness.VERIFIED_FLIGHT
    range_km: float = QKD_MICIUS_RANGE_KM
    key_rate_bps: float = QKD_MICIUS_KEY_RATE_BPS
    detector_efficiency: float = 0.85     # ESTIMATE — 85% InGaAs SPAD efficiency (Yin 2017 Science 356 1140: Micius QKD)
    error_rate: float = 0.01              # QBER <1% in satellite QKD (Liao 2018 PRL 120 030501: Micius QBER ~3%)

    # Degradation state
    operational_years: float = 0.0
    detector_degradation: float = 1.0     # 1.0 = nominal
    is_operational: bool = True
    _rng: random.Random = field(default_factory=lambda: random.Random(44))

    def key_rate_at_distance(self, distance_km: float) -> float:
        """Estimate secure key rate at given distance.

        Free-space QKD: loss follows inverse-square law (diffraction).
        Key rate scales approximately as (range_ref / distance)^2.

        Below a threshold key rate, QKD becomes unusable.

        Args:
            distance_km: distance between communicating parties [km].

        Returns:
            Estimated key rate [bits/second].
        """
        if distance_km <= 0:
            raise ValueError("Distance must be positive")
        ratio = (self.range_km / distance_km) ** 2
        return self.key_rate_bps * ratio * self.detector_degradation

    def simulate_year(self) -> dict[str, Any]:
        """Simulate one year of QKD operation.

        Single-photon detectors degrade ~1%/year from radiation damage
        (dark count rate increases in InGaAs APDs).
        """
        if not self.is_operational:
            return {
                "system": "QKD",
                "readiness": self.readiness.value,
                "status": "offline",
                "operational_years": self.operational_years,
            }

        self.operational_years += 1.0

        # Detector degradation: 1% efficiency loss per year
        self.detector_degradation *= 0.99

        # Failure: 0.2%/year (detector burnout, laser aging)
        if self._rng.random() < 0.002:
            self.is_operational = False
            return {
                "system": "QKD",
                "readiness": self.readiness.value,
                "status": "failed",
                "operational_years": self.operational_years,
            }

        return {
            "system": "QKD",
            "readiness": self.readiness.value,
            "status": "nominal",
            "operational_years": self.operational_years,
            "detector_degradation": self.detector_degradation,
            "current_key_rate_bps": self.key_rate_bps * self.detector_degradation,
        }


# ══════════════════════════════════════════════════════════════════
# 7.  QUANTUM RANDOM NUMBER GENERATOR — [VERIFIED]
# ══════════════════════════════════════════════════════════════════
# Reference: Herrero-Collantes & Garcia-Escartin, "Quantum random
# number generators," Rev. Mod. Phys. 89, 015004 (2017).

QRNG_RATE_MBPS = 1000.0  # Modern QRNG: ~1 Gbps achievable


@dataclass
class QuantumRandomNumberGenerator:
    """Quantum Random Number Generator (vacuum fluctuation based).

    [VERIFIED — COMMERCIAL TECHNOLOGY]
    QRNGs exploit quantum vacuum fluctuations or photon arrival times
    to produce truly random bits (not pseudo-random).

    For generation ship: cryptographic key material, Monte Carlo
    simulations for navigation, unbiased governance decisions.

    ID Quantique, QuintessenceLabs, and others sell commercial QRNGs.
    Space-qualified versions exist for satellite applications.
    """
    readiness: TechReadiness = TechReadiness.VERIFIED_FLIGHT
    rate_mbps: float = QRNG_RATE_MBPS
    entropy_quality: float = 1.0          # 1.0 = perfect entropy per bit
    power_watts: float = 5.0              # ESTIMATE — commercial QRNG (ID Quantique Quantis: 2-3 W; ID Quantique 2022 datasheet)
    mass_kg: float = 1.0                  # ESTIMATE — space-grade QRNG module (ID Quantique QRNG ~0.5 kg; ID Quantique 2022)

    operational_years: float = 0.0
    degradation_factor: float = 1.0
    is_operational: bool = True
    _rng: random.Random = field(default_factory=lambda: random.Random(45))

    def generate_bits(self, n_bits: int) -> float:
        """Time [seconds] to generate n_bits of true random data.

        Args:
            n_bits: number of random bits requested.

        Returns:
            Time in seconds to generate.
        """
        effective_rate = self.rate_mbps * 1e6 * self.degradation_factor
        if effective_rate <= 0:
            return float('inf')
        return n_bits / effective_rate

    def entropy_per_bit(self) -> float:
        """Shannon entropy per output bit.  1.0 = perfectly random.

        Degrades as laser source ages and classical noise creeps in.
        """
        return min(1.0, self.entropy_quality * self.degradation_factor)

    def simulate_year(self) -> dict[str, Any]:
        """Simulate one year of operation.

        Laser diode aging reduces output rate by ~0.2%/year.
        """
        if not self.is_operational:
            return {
                "system": "QRNG",
                "readiness": self.readiness.value,
                "status": "offline",
            }

        self.operational_years += 1.0
        self.degradation_factor *= 0.998  # 0.2%/year degradation

        if self._rng.random() < 0.001:  # 0.1%/year failure
            self.is_operational = False
            return {
                "system": "QRNG",
                "readiness": self.readiness.value,
                "status": "failed",
                "operational_years": self.operational_years,
            }

        return {
            "system": "QRNG",
            "readiness": self.readiness.value,
            "status": "nominal",
            "operational_years": self.operational_years,
            "effective_rate_mbps": self.rate_mbps * self.degradation_factor,
            "entropy_per_bit": self.entropy_per_bit(),
        }


# ══════════════════════════════════════════════════════════════════
# 8.  QUANTUM GRAVITATIONAL SENSOR — [VERIFIED PRINCIPLE]
# ══════════════════════════════════════════════════════════════════
# Reference: Bongs et al., "Taking atom interferometric quantum
# sensors from the laboratory to real-world applications,"
# Nature Reviews Physics 1, 731-739 (2019).

ATOM_INTERFEROMETER_SENSITIVITY_M_S2 = 1e-9  # ~1 nano-g demonstrated


@dataclass
class QuantumGravitationalSensor:
    """Atom interferometry-based gravitational field mapper.

    [VERIFIED — LABORATORY, APPROACHING FLIGHT]
    Cold atom interferometers measure gravitational acceleration to
    ~10⁻⁹ m/s² (nano-g level). Used for:
    - Gravitational field mapping at destination star system
    - Detecting massive objects (asteroids, planets) during approach
    - Measuring ship's own acceleration precisely

    NASA CAL (Cold Atom Laboratory) on ISS since 2018 demonstrates
    cold atom manipulation in microgravity.
    """
    readiness: TechReadiness = TechReadiness.VERIFIED_LAB
    sensitivity_m_s2: float = ATOM_INTERFEROMETER_SENSITIVITY_M_S2
    measurement_time_s: float = 1.0   # ESTIMATE — 1 s integration (Canuel 2018 STE-QUEST design uses 10 s; conservative)
    power_watts: float = 100.0         # ESTIMATE — laser + vacuum system (NASA CAL ISS: ~100 W; Elliott 2018 npj Microgravity 4 16)
    mass_kg: float = 30.0              # ESTIMATE — flight-grade AI (NASA CAL: 23 kg; Elliott 2018)

    operational_years: float = 0.0
    degradation_factor: float = 1.0
    is_operational: bool = True
    _rng: random.Random = field(default_factory=lambda: random.Random(46))

    def gravitational_anomaly_detectable(self, mass_kg: float,
                                         distance_m: float) -> bool:
        """Can this sensor detect a gravitational anomaly from mass at distance?

        Gravitational acceleration: a = G × M / r²
        Detectable if a > sensitivity (adjusted for degradation).

        Args:
            mass_kg: mass of the object [kg].
            distance_m: distance to the object [m].

        Returns:
            True if detectable.
        """
        G = 6.674_30e-11  # Gravitational constant [m³ kg⁻¹ s⁻²]
        a = G * mass_kg / (distance_m ** 2)
        threshold = self.sensitivity_m_s2 / self.degradation_factor
        return a >= threshold

    def detection_range_m(self, mass_kg: float) -> float:
        """Maximum detection range for given mass.

        r_max = √(G × M / sensitivity)
        """
        G = 6.674_30e-11
        threshold = self.sensitivity_m_s2 / self.degradation_factor
        return math.sqrt(G * mass_kg / threshold)

    def simulate_year(self) -> dict[str, Any]:
        """Simulate one year.  Atom source degrades slowly."""
        if not self.is_operational:
            return {
                "system": "QuantumGravSensor",
                "readiness": self.readiness.value,
                "status": "offline",
            }

        self.operational_years += 1.0
        # Rubidium/Cesium source depletion: ~0.3%/year
        self.degradation_factor *= 0.997

        if self._rng.random() < 0.003:  # 0.3%/year failure
            self.is_operational = False
            return {
                "system": "QuantumGravSensor",
                "readiness": self.readiness.value,
                "status": "failed",
                "operational_years": self.operational_years,
            }

        return {
            "system": "QuantumGravSensor",
            "readiness": self.readiness.value,
            "status": "nominal",
            "operational_years": self.operational_years,
            "effective_sensitivity_m_s2": (
                self.sensitivity_m_s2 / self.degradation_factor
            ),
            "degradation_factor": self.degradation_factor,
        }


# ══════════════════════════════════════════════════════════════════
# 9.  DEBUNKED / SPECULATIVE QUANTUM TECH — Honest Assessment
# ══════════════════════════════════════════════════════════════════

class QuantumMythStatus(Enum):
    """Status of commonly claimed quantum technologies."""
    DEBUNKED = "debunked"
    NO_EVIDENCE = "no_evidence"
    VIOLATES_KNOWN_PHYSICS = "violates_known_physics"
    THEORETICALLY_POSSIBLE = "theoretically_possible"


# Each entry: (claim, status, explanation, references)
QUANTUM_MYTHS: list[dict[str, Any]] = [
    {
        "claim": "Quantum entanglement enables FTL communication",
        "status": QuantumMythStatus.VIOLATES_KNOWN_PHYSICS,
        "explanation": (
            "The no-communication theorem (Ghirardi et al., 1980) and "
            "no-cloning theorem (Wootters & Zurek, 1982) together prove "
            "that entanglement CANNOT transmit information faster than light. "
            "Entanglement produces CORRELATIONS, not communication. Measuring "
            "one particle of an entangled pair gives a random result — the "
            "correlation is only visible when the two parties compare notes "
            "via a classical (light-speed) channel."
        ),
        "references": [
            "Ghirardi et al., Lett. Nuovo Cim. 27, 293 (1980)",
            "Wootters & Zurek, Nature 299, 802 (1982)",
        ],
    },
    {
        "claim": "EmDrive / Quantum Vacuum Thruster produces thrust",
        "status": QuantumMythStatus.NO_EVIDENCE,
        "explanation": (
            "The EmDrive (Shawyer) and Quantum Vacuum Plasma Thruster "
            "(White, NASA Eagleworks) claim thrust without propellant, "
            "violating conservation of momentum. All positive results have "
            "been attributed to thermal artifacts, electromagnetic interference, "
            "or measurement error. Tajmar's SpaceDrive project at TU Dresden "
            "found artifacts. IVO Quantum Drive launched to orbit in 2025 but "
            "NO thrust was measured. No peer-reviewed replication exists."
        ),
        "references": [
            "Tajmar et al., AIAA 2017-5072 (SpaceDrive results)",
            "IVO Ltd., Rogue Space Systems Barry-1 mission (2025, no thrust confirmed)",
        ],
    },
    {
        "claim": "Dark energy can be harnessed for propulsion",
        "status": QuantumMythStatus.NO_EVIDENCE,
        "explanation": (
            "Dark energy (cosmological constant or quintessence) is observed "
            "only through its effect on cosmic expansion. Its energy density "
            "is ~6×10⁻¹⁰ J/m³ — far too diffuse to extract. We do not "
            "understand its fundamental nature. DESI (2024) suggests it may "
            "be time-varying (w₀ ≈ -0.55, wa ≈ -1.6) but this is preliminary. "
            "No mechanism to 'collect' or 'focus' dark energy is known."
        ),
        "references": [
            "DESI Collaboration, Adame et al., arXiv:2404.03002 (2024)",
            "Planck 2018 results VI, A&A 641, A6 (2020)",
        ],
    },
    {
        "claim": "Alcubierre warp drive is feasible",
        "status": QuantumMythStatus.THEORETICALLY_POSSIBLE,
        "explanation": (
            "The Alcubierre metric (1994) is a valid solution to Einstein's "
            "field equations that allows effective FTL travel by contracting "
            "space ahead and expanding it behind. However, it requires exotic "
            "matter with negative energy density — not known to exist in bulk. "
            "Bobrick & Martire (2021) showed subluminal warp solutions don't "
            "need exotic matter but provide no speed advantage. Lentz (2021) "
            "proposed positive-energy solutions but they remain unverified."
        ),
        "references": [
            "Alcubierre, Class. Quantum Grav. 11, L73 (1994)",
            "Bobrick & Martire, Class. Quantum Grav. 38, 105009 (2021)",
            "Lentz, Class. Quantum Grav. 38, 075015 (2021)",
        ],
    },
]


def assess_quantum_claim(claim_keyword: str) -> dict[str, Any] | None:
    """Look up the honest assessment of a quantum technology claim.

    Args:
        claim_keyword: keyword to search (e.g. "entanglement", "EmDrive").

    Returns:
        Assessment dict or None if not found.
    """
    keyword_lower = claim_keyword.lower()
    for myth in QUANTUM_MYTHS:
        if keyword_lower in myth["claim"].lower():
            return myth
    return None


# ══════════════════════════════════════════════════════════════════
# 10.  LATEST PHYSICS FINDINGS (2025-2026) — Advisory
# ══════════════════════════════════════════════════════════════════

LATEST_PHYSICS_2025_2026: list[dict[str, Any]] = [
    {
        "finding": "DESI: Dark energy may be weakening over time",
        "year": 2024,
        "impact": (
            "If dark energy is time-varying (not a cosmological constant), "
            "the universe expansion rate is changing. For navigation over "
            "1000+ year missions: cosmic expansion correction factors in "
            "star catalog positions may need revision."
        ),
        "reference": "DESI Collaboration, arXiv:2404.03002",
        "confidence": "preliminary — 2-3σ significance",
    },
    {
        "finding": "LIGO O4: Improved gravitational wave detection",
        "year": 2025,
        "impact": (
            "LIGO O4 run detecting more binary mergers with higher SNR. "
            "For generation ship: gravitational wave astronomy provides "
            "alternative navigation beacons (if detectors are miniaturized)."
        ),
        "reference": "LIGO/Virgo/KAGRA O4 results (ongoing)",
        "confidence": "high — direct detection",
    },
    {
        "finding": "Vera Rubin Observatory: 20 billion galaxy survey",
        "year": 2025,
        "impact": (
            "LSST will map the entire southern sky repeatedly for 10 years. "
            "For generation ship: most comprehensive star/galaxy catalog "
            "for deep space navigation reference."
        ),
        "reference": "Rubin Observatory, LSST Science Book v2.0",
        "confidence": "high — operational telescope",
    },
    {
        "finding": "Quantum gravity: unified spacetime ripple detector proposed",
        "year": 2025,
        "impact": (
            "First proposal for a detector that could sense both gravitational "
            "waves and quantum gravity effects. If realized: fundamental physics "
            "discovery, but no practical navigation impact for decades."
        ),
        "reference": "Various theoretical groups (2025)",
        "confidence": "theoretical — no experimental verification",
    },
]


# ══════════════════════════════════════════════════════════════════
# 11.  INTEGRATED SHIP TIMEKEEPING SYSTEM
# ══════════════════════════════════════════════════════════════════

@dataclass
class ShipTimekeepingSystem:
    """Integrated timekeeping system for generation ship.

    Architecture:
    - 3× DSAC clocks (primary, Byzantine voting)
    - 1× Optical lattice clock (secondary, if available)
    - Relativistic time tracker (proper vs coordinate time)
    - Pulsar timing cross-check interface

    The system provides:
    - Consensus ship time (from clock ensemble)
    - Earth coordinate time (from relativistic corrections)
    - Time quality metric (agreement between clocks)
    - Degradation tracking over centuries
    """
    dsac_clocks: list[DSACClock] = field(default_factory=list)
    optical_clock: OpticalLatticeClock | None = None
    time_tracker: RelativisticTimeTracker = field(
        default_factory=RelativisticTimeTracker
    )
    mission_year: float = 0.0
    total_clock_failures: int = 0
    _rng: random.Random = field(default_factory=lambda: random.Random(42))

    def __post_init__(self):
        if not self.dsac_clocks:
            # Default: 3 DSAC clocks for Byzantine fault tolerance
            self.dsac_clocks = [DSACClock(clock_id=i) for i in range(3)]
        if self.optical_clock is None:
            self.optical_clock = OpticalLatticeClock(clock_id=10)

    def simulate_year(self, velocity_ms: float = 0.0) -> dict[str, Any]:
        """Simulate one year of the timekeeping system.

        Args:
            velocity_ms: current ship velocity [m/s] for relativistic correction.

        Returns:
            Comprehensive status dict.
        """
        self.mission_year += 1.0

        # Advance all clocks
        dsac_results = []
        for clock in self.dsac_clocks:
            result = clock.simulate_year()
            dsac_results.append(result)
            if result["status"] == "failed":
                self.total_clock_failures += 1

        optical_result = None
        if self.optical_clock and self.optical_clock.is_operational:
            optical_result = self.optical_clock.simulate_year()
            if optical_result["status"] == "failed":
                self.total_clock_failures += 1

        # Relativistic time tracking
        rel_result = self.time_tracker.advance_years(1.0, velocity_ms)

        # Clock ensemble voting
        operational_errors = [
            c.cumulative_error_s for c in self.dsac_clocks if c.is_operational
        ]
        n_operational = len(operational_errors)

        consensus_error = 0.0
        rejected_clocks: list[int] = []
        if n_operational >= 2:
            consensus_error, rejected_clocks = byzantine_clock_vote(
                operational_errors
            )
        elif n_operational == 1:
            consensus_error = operational_errors[0]

        # Ensemble stability
        if n_operational > 0:
            ens_stability = ensemble_stability_improvement(
                n_operational, DSAC_STABILITY_23DAY
            )
        else:
            ens_stability = float('inf')

        return {
            "mission_year": self.mission_year,
            "dsac_clocks": dsac_results,
            "optical_clock": optical_result,
            "relativistic": rel_result,
            "consensus_error_s": consensus_error,
            "rejected_clocks": rejected_clocks,
            "n_operational_dsac": n_operational,
            "ensemble_stability": ens_stability,
            "total_failures": self.total_clock_failures,
            "proper_time_years": self.time_tracker.proper_time_years(),
            "coordinate_time_years": self.time_tracker.coordinate_time_years(),
            "time_dilation_difference_years": self.time_tracker.time_difference_years(),
        }

    def get_consensus_time_s(self) -> float:
        """Get current consensus proper time from clock ensemble."""
        readings = [
            c.cumulative_error_s for c in self.dsac_clocks if c.is_operational
        ]
        if not readings:
            return 0.0
        voted, _ = byzantine_clock_vote(readings)
        return self.time_tracker.cumulative_proper_time_s + voted


# ══════════════════════════════════════════════════════════════════
# 12.  INTEGRATED QUANTUM SYSTEMS SUITE
# ══════════════════════════════════════════════════════════════════

@dataclass
class ShipQuantumSuite:
    """All quantum systems aboard the generation ship.

    Manages lifecycle, degradation, and status for:
    - QKD (internal secure comms)
    - QRNG (crypto + simulation)
    - Quantum gravitational sensor (destination mapping)
    """
    qkd: QuantumKeyDistribution = field(
        default_factory=QuantumKeyDistribution
    )
    qrng: QuantumRandomNumberGenerator = field(
        default_factory=QuantumRandomNumberGenerator
    )
    grav_sensor: QuantumGravitationalSensor = field(
        default_factory=QuantumGravitationalSensor
    )
    mission_year: float = 0.0

    def simulate_year(self) -> dict[str, Any]:
        """Simulate one year for all quantum systems."""
        self.mission_year += 1.0
        return {
            "mission_year": self.mission_year,
            "qkd": self.qkd.simulate_year(),
            "qrng": self.qrng.simulate_year(),
            "grav_sensor": self.grav_sensor.simulate_year(),
            "all_operational": (
                self.qkd.is_operational
                and self.qrng.is_operational
                and self.grav_sensor.is_operational
            ),
        }
