"""V3-M5: reaction-wheel bearing-degradation proxy via slow-time torque residuals.

Martin panel §M-5 (V3 audit): bearing defects produce vibration at
characteristic frequencies (BPFO, BPFI, FTF) detectable months before
catastrophic failure — but only with high-rate angular-rate telemetry.
On most LEO missions the bus only downlinks wheel state at 1 Hz, which
is below twice the spin frequency of a 6 000 RPM wheel and therefore
cannot resolve bearing fault frequencies directly.

This module ships the *platform-compatible* fallback from the user's
S-1/M-5 scoping note: use slow-time *torque residuals* (observed minus
linearly-expected torque at a given speed) as a bearing-stress proxy.
Bearing degradation raises the apparent rolling friction, shifting the
expected torque curve and raising residual variance even at 1 Hz
sampling.  Coupled with a trend test on rolling residual RMS, this
yields a weak-but-nonzero early-warning signal on platforms that lack
the high-rate telemetry demanded by the full M-5 spectral approach.

Bearing-fault-frequency formulas are also provided as pure helpers
(`ball_pass_frequency_outer`, `ball_pass_frequency_inner`,
`fundamental_train_frequency`) so downstream integrations that DO have
high-rate telemetry can plug a FFT-based detector in alongside this
proxy without rederiving the geometry math.

References
  * Harris & Kotzalas 2007, "Rolling Bearing Analysis" §5.4 — geometry
    of BPFO / BPFI / FTF for standard rolling-element bearings.
  * Randall 2011, "Vibration-based Condition Monitoring" §4.5 — proxy
    bearing indicators via slow-time residuals when spectral data is
    unavailable.
  * Wang et al. 2017 Mech Syst Signal Process 97 §2.2 — torque-vs-speed
    residual used as a rolling-friction proxy.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np


# Two-stage linear fit assumes torque ≈ a·RPM + b.  For reaction wheels
# dominated by motor back-EMF this is accurate to ~1 % across the nominal
# band (Wang et al. 2017 §2.2).  Full Coulomb-friction models need
# bearing lubricant viscosity; beyond platform telemetry.
MIN_BASELINE_SAMPLES = 64         # ESTIMATE — 64 (rpm,torque) pairs gives least-squares slope with σ < 5% on typical RW telemetry
MIN_RMS_WINDOW_SAMPLES = 32       # ESTIMATE — 32-sample rolling RMS — longest slew is ~20 s at 1 Hz, so 32 s straddles slew + settle
DEFAULT_RMS_HISTORY = 128         # ESTIMATE — 128 rolling-RMS snapshots ≈ ~1 hour of 1 Hz telemetry for trend regression
DEFAULT_RMS_RATIO_WATCH   = 1.5   # ESTIMATE — 50 % rise over baseline = early bearing wear (Randall 2011 §4.5 — "elevated friction" band)
DEFAULT_RMS_RATIO_WARNING = 2.0   # ESTIMATE — 2× baseline = sustained friction rise (Randall 2011 §4.5)
DEFAULT_RMS_RATIO_CRITICAL = 3.0  # ESTIMATE — 3× baseline = pre-failure binding territory per Randall 2011 §4.5 (bearing "rough running" onset)
DEFAULT_TREND_SLOPE_WARNING = 0.01  # ESTIMATE — ≥1 %/sample relative rise in rolling RMS is a sustained upward trend at 1 Hz


# ── Bearing-fault-frequency geometry helpers (pure, unit-less) ────────────────


def fundamental_train_frequency(
    rpm_shaft: float,
    n_balls: int,
    ball_diameter: float,
    pitch_diameter: float,
    contact_angle_rad: float = 0.0,
) -> float:
    """Fundamental train (cage) frequency, Hz.

    FTF = 0.5 · rps · (1 − D_b/D_p · cos(α))
    Harris & Kotzalas 2007 §5.4.
    """
    if pitch_diameter <= 0.0:
        raise ValueError(f"pitch_diameter must be positive, got {pitch_diameter!r}")
    if n_balls <= 0:
        raise ValueError(f"n_balls must be positive, got {n_balls!r}")
    if ball_diameter <= 0.0 or ball_diameter >= pitch_diameter:
        raise ValueError(
            f"ball_diameter must be in (0, pitch_diameter); "
            f"got ball={ball_diameter!r}, pitch={pitch_diameter!r}"
        )
    rps = rpm_shaft / 60.0
    return 0.5 * rps * (1.0 - (ball_diameter / pitch_diameter) * math.cos(contact_angle_rad))


def ball_pass_frequency_outer(
    rpm_shaft: float,
    n_balls: int,
    ball_diameter: float,
    pitch_diameter: float,
    contact_angle_rad: float = 0.0,
) -> float:
    """Ball-pass frequency outer race (BPFO), Hz.

    BPFO = n · FTF = 0.5 · n · rps · (1 − D_b/D_p · cos α)
    """
    return n_balls * fundamental_train_frequency(
        rpm_shaft, n_balls, ball_diameter, pitch_diameter, contact_angle_rad
    )


def ball_pass_frequency_inner(
    rpm_shaft: float,
    n_balls: int,
    ball_diameter: float,
    pitch_diameter: float,
    contact_angle_rad: float = 0.0,
) -> float:
    """Ball-pass frequency inner race (BPFI), Hz.

    BPFI = 0.5 · n · rps · (1 + D_b/D_p · cos α)
    """
    if pitch_diameter <= 0.0:
        raise ValueError(f"pitch_diameter must be positive, got {pitch_diameter!r}")
    if n_balls <= 0:
        raise ValueError(f"n_balls must be positive, got {n_balls!r}")
    if ball_diameter <= 0.0 or ball_diameter >= pitch_diameter:
        raise ValueError(
            f"ball_diameter must be in (0, pitch_diameter); "
            f"got ball={ball_diameter!r}, pitch={pitch_diameter!r}"
        )
    rps = rpm_shaft / 60.0
    return 0.5 * n_balls * rps * (1.0 + (ball_diameter / pitch_diameter) * math.cos(contact_angle_rad))


# ── Torque-residual proxy monitor ─────────────────────────────────────────────


@dataclass
class BearingProxyReport:
    """Per-wheel bearing-proxy report."""

    satellite_id:       str
    wheel_id:           str
    tier:               str             # NOMINAL / WATCH / WARNING / CRITICAL
    current_rms:        float
    baseline_rms:       float
    rms_ratio:          float
    trend_slope_per_s:  float
    sample_count:       int
    details:            dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "satellite_id":      self.satellite_id,
            "wheel_id":          self.wheel_id,
            "tier":              self.tier,
            "current_rms":       self.current_rms,
            "baseline_rms":      self.baseline_rms,
            "rms_ratio":         self.rms_ratio,
            "trend_slope_per_s": self.trend_slope_per_s,
            "sample_count":      self.sample_count,
            "details":           dict(self.details),
        }


@dataclass
class _WheelState:
    rpm_baseline:     list[float]    = field(default_factory=list)
    torque_baseline:  list[float]    = field(default_factory=list)
    slope:            float          = 0.0
    intercept:        float          = 0.0
    baseline_rms:     float          = 0.0
    fitted:           bool           = False
    residual_buffer:  deque          = field(default_factory=lambda: deque(maxlen=MIN_RMS_WINDOW_SAMPLES))
    rms_history:      deque          = field(default_factory=lambda: deque(maxlen=DEFAULT_RMS_HISTORY))
    last_update_ts:   float | None   = None


class RWBearingProxyMonitor:
    """Per-(satellite, wheel) reaction-wheel bearing-stress proxy monitor.

    Usage
    -----
    mon = RWBearingProxyMonitor()
    # Calibration phase — feed MIN_BASELINE_SAMPLES nominal pairs
    for rpm, tau in nominal_samples:
        mon.record_sample("SAT-A", "rw_x", rpm=rpm, torque=tau, epoch=ts)
    mon.fit_baseline("SAT-A", "rw_x")
    # Runtime: keep recording; poll for a report
    for rpm, tau, ts in live_stream:
        mon.record_sample("SAT-A", "rw_x", rpm=rpm, torque=tau, epoch=ts)
    report = mon.evaluate("SAT-A", "rw_x")
    """

    def __init__(
        self,
        *,
        min_baseline_samples:    int   = MIN_BASELINE_SAMPLES,
        rms_window_samples:      int   = MIN_RMS_WINDOW_SAMPLES,
        rms_history_samples:     int   = DEFAULT_RMS_HISTORY,
        rms_ratio_watch:         float = DEFAULT_RMS_RATIO_WATCH,
        rms_ratio_warning:       float = DEFAULT_RMS_RATIO_WARNING,
        rms_ratio_critical:      float = DEFAULT_RMS_RATIO_CRITICAL,
        trend_slope_warning:     float = DEFAULT_TREND_SLOPE_WARNING,
    ) -> None:
        if min_baseline_samples < 16:
            raise ValueError(f"min_baseline_samples too small, got {min_baseline_samples!r}")
        if not (
            1.0 < rms_ratio_watch <= rms_ratio_warning <= rms_ratio_critical
        ):
            raise ValueError(
                f"rms_ratio thresholds must be non-decreasing and >1, got "
                f"({rms_ratio_watch}, {rms_ratio_warning}, {rms_ratio_critical})"
            )
        self.min_baseline_samples   = int(min_baseline_samples)
        self.rms_window_samples     = int(rms_window_samples)
        self.rms_history_samples    = int(rms_history_samples)
        self.rms_ratio_watch        = float(rms_ratio_watch)
        self.rms_ratio_warning      = float(rms_ratio_warning)
        self.rms_ratio_critical     = float(rms_ratio_critical)
        self.trend_slope_warning    = float(trend_slope_warning)
        self._states: dict[tuple[str, str], _WheelState] = {}

    # ── Ingest ────────────────────────────────────────────────────────────────

    def record_sample(
        self,
        satellite_id: str,
        wheel_id: str,
        *,
        rpm: float,
        torque: float,
        epoch: float | None = None,
    ) -> None:
        key = (satellite_id, wheel_id)
        st = self._states.setdefault(key, _WheelState(
            residual_buffer=deque(maxlen=self.rms_window_samples),
            rms_history=deque(maxlen=self.rms_history_samples),
        ))
        if not st.fitted:
            st.rpm_baseline.append(float(rpm))
            st.torque_baseline.append(float(torque))
            return

        predicted = st.slope * rpm + st.intercept
        residual = float(torque - predicted)
        st.residual_buffer.append(residual)
        if len(st.residual_buffer) >= self.rms_window_samples:
            rms = float(np.sqrt(np.mean(np.asarray(st.residual_buffer) ** 2)))
            st.rms_history.append((epoch, rms))
        st.last_update_ts = epoch

    # ── Calibration ───────────────────────────────────────────────────────────

    def fit_baseline(self, satellite_id: str, wheel_id: str) -> None:
        key = (satellite_id, wheel_id)
        st = self._states.get(key)
        if st is None:
            raise KeyError(f"no samples recorded for ({satellite_id!r}, {wheel_id!r})")
        if len(st.rpm_baseline) < self.min_baseline_samples:
            raise ValueError(
                f"need ≥{self.min_baseline_samples} baseline samples for "
                f"({satellite_id!r}, {wheel_id!r}), have {len(st.rpm_baseline)}"
            )

        rpm = np.asarray(st.rpm_baseline, dtype=np.float64)
        tau = np.asarray(st.torque_baseline, dtype=np.float64)
        if rpm.std() < 1e-6:
            # Degenerate: all samples at one RPM — fall back to mean intercept.
            slope = 0.0
            intercept = float(tau.mean())
        else:
            slope, intercept = np.polyfit(rpm, tau, 1)
        residuals = tau - (slope * rpm + intercept)
        baseline_rms = float(np.sqrt(np.mean(residuals ** 2)))
        st.slope         = float(slope)
        st.intercept     = float(intercept)
        st.baseline_rms  = max(baseline_rms, 1e-9)
        st.fitted        = True
        st.residual_buffer.clear()
        st.rms_history.clear()

    # ── Scoring ───────────────────────────────────────────────────────────────

    def evaluate(self, satellite_id: str, wheel_id: str) -> BearingProxyReport | None:
        key = (satellite_id, wheel_id)
        st = self._states.get(key)
        if st is None or not st.fitted:
            return None
        if len(st.rms_history) < 2:
            return None

        epochs = np.asarray([e for e, _ in st.rms_history if e is not None], dtype=np.float64)
        rmss   = np.asarray([r for e, r in st.rms_history if e is not None], dtype=np.float64)
        current_rms = float(rmss[-1])
        ratio = current_rms / st.baseline_rms

        # Trend slope of rolling RMS vs wallclock time.
        if len(epochs) >= 2 and epochs[-1] != epochs[0]:
            slope, _ = np.polyfit(epochs - epochs[0], rmss, 1)
            trend = float(slope / max(st.baseline_rms, 1e-9))   # relative slope / s
        else:
            trend = 0.0

        tier = self._tier(ratio, trend)
        return BearingProxyReport(
            satellite_id=satellite_id,
            wheel_id=wheel_id,
            tier=tier,
            current_rms=current_rms,
            baseline_rms=st.baseline_rms,
            rms_ratio=ratio,
            trend_slope_per_s=trend,
            sample_count=len(st.rms_history),
            details={
                "slope_torque_per_rpm": st.slope,
                "intercept_torque":     st.intercept,
            },
        )

    def _tier(self, ratio: float, trend_per_s: float) -> str:
        if ratio >= self.rms_ratio_critical:
            return "CRITICAL"
        if ratio >= self.rms_ratio_warning or trend_per_s >= self.trend_slope_warning:
            return "WARNING"
        if ratio >= self.rms_ratio_watch:
            return "WATCH"
        return "NOMINAL"

    def reset(self, satellite_id: str | None = None) -> None:
        if satellite_id is None:
            self._states.clear()
            return
        for key in list(self._states.keys()):
            if key[0] == satellite_id:
                del self._states[key]


__all__ = [
    "BearingProxyReport",
    "DEFAULT_RMS_RATIO_WATCH",
    "DEFAULT_RMS_RATIO_WARNING",
    "DEFAULT_RMS_RATIO_CRITICAL",
    "MIN_BASELINE_SAMPLES",
    "RWBearingProxyMonitor",
    "ball_pass_frequency_inner",
    "ball_pass_frequency_outer",
    "fundamental_train_frequency",
]
