"""EWMA-STR: Exponentially Weighted Moving Average on STL Residuals.

Catches level shifts (sudden step changes in the process mean) faster than
CUSUM, which requires accumulation over multiple samples.

Algorithm:
    Z[t] = λ × x[t]  +  (1 - λ) × Z[t-1]     (exponential smoothing)
    UCL  = +L × σ_ref × sqrt(λ / (2 - λ))      (upper control limit)
    LCL  = -L × σ_ref × sqrt(λ / (2 - λ))      (lower control limit)
    Alarm fires when Z[t] > UCL  OR  Z[t] < LCL.

where:
    x[t]   — STL residual (centred at 0; μ_ref ≈ 0)
    λ      — smoothing factor: 0.2 (from CalibrationState / config)
              Lower λ = more memory = slower response = fewer false positives.
              0.2 is the standard choice for satellite telemetry.
    L      — sigma multiplier: 3.0  (±3σ ≈ 99.7% confidence under normality)
    UCL/LCL — per-channel, from CalibrationState.ewma_ucl / .ewma_lcl

EWMA vs CUSUM:
    CUSUM:  best for gradual drift (accumulates over many samples)
    EWMA:   best for sudden level shifts (responds within ~5 samples for λ=0.2)
    Together they cover the full spectrum of non-random anomaly patterns.

Score normalisation:
    score = |Z[t]| / |UCL|
    score = 0   → Z at zero (nominal)
    score = 1.0 → exactly at control limit
    score > 1.0 clipped to 1.0

Z[t] is NOT reset after an alarm — EWMA maintains continuous memory.
Persistent anomalies keep Z[t] elevated, giving sustained high scores.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.calibration import CalibrationState, EWMA_LAMBDA

logger = structlog.get_logger()

# Severity escalation: how far above the control limit Z must sit.
_WARN_RATIO:     float = 1.5   # ESTIMATE — |Z| > 1.5 × UCL → WARNING (NASA GSFC monitoring practice)
_CRITICAL_RATIO: float = 2.5   # ESTIMATE — |Z| > 2.5 × UCL → CRITICAL (NASA GSFC monitoring practice)


@dataclass
class _EWMAState:
    z: float = 0.0              # current EWMA value (Z[t])
    alarm_count: int = 0


class EWMADetector:
    """EWMA-STR detector.  One state entry per channel key."""

    def __init__(self, lam: float = EWMA_LAMBDA) -> None:
        self._lambda = lam
        self._states: dict[str, _EWMAState] = {}

    # ── detection ───────────────────────────────────────────────────────

    def detect(
        self,
        key: str,
        residual: float,
        calibration: CalibrationState,
    ) -> DetectorResult:
        """Run one EWMA step.

        Args:
            key:         Channel key.
            residual:    Latest STL residual (centred at 0).
            calibration: Calibration state with .ewma_ucl / .ewma_lcl set.

        Returns:
            DetectorResult.  is_anomaly=False during warm-up.
        """
        if not calibration.is_calibrated:
            return self._nominal(reason="warming_up")

        ucl = calibration.ewma_ucl
        lcl = calibration.ewma_lcl

        if abs(ucl) < 1e-9:
            return self._nominal(reason="zero_control_limit")

        state = self._states.setdefault(key, _EWMAState())

        # Update EWMA — one-liner, no Python loops.
        lam   = self._lambda
        state.z = lam * residual + (1.0 - lam) * state.z

        z         = state.z
        is_alarm  = z > ucl or z < lcl
        score     = min(1.0, abs(z) / abs(ucl))

        if is_alarm:
            state.alarm_count += 1
            severity = self._severity(z, ucl, lcl)
        else:
            severity = Severity.NOMINAL

        details = {
            "z_ewma":      round(z, 6),
            "ucl":         round(ucl, 6),
            "lcl":         round(lcl, 6),
            "lambda":      lam,
            "alarm_count": state.alarm_count,
            "residual":    round(residual, 6),
        }

        return DetectorResult(
            detector_name="ewma",
            is_anomaly=is_alarm,
            score=float(score),
            severity=severity,
            details=details,
        )

    # ── state persistence ────────────────────────────────────────────────

    def get_state(self, key: str) -> dict:
        s = self._states.get(key, _EWMAState())
        return {"z": s.z, "alarm_count": s.alarm_count}

    def load_state(self, key: str, data: dict) -> None:
        self._states[key] = _EWMAState(
            z=float(data.get("z", 0.0)),
            alarm_count=int(data.get("alarm_count", 0)),
        )

    def all_states(self) -> dict[str, dict]:
        return {k: self.get_state(k) for k in self._states}

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _severity(z: float, ucl: float, lcl: float) -> Severity:
        limit = ucl if z > 0 else abs(lcl)
        ratio = abs(z) / max(limit, 1e-9)
        if ratio >= _CRITICAL_RATIO:
            return Severity.CRITICAL
        if ratio >= _WARN_RATIO:
            return Severity.WARNING
        return Severity.WATCH

    @staticmethod
    def _nominal(reason: str) -> DetectorResult:
        return DetectorResult(
            detector_name="ewma",
            is_anomaly=False,
            score=0.0,
            severity=Severity.NOMINAL,
            details={"reason": reason},
        )
