"""CUSUM (Cumulative Sum) detector — NASA's workhorse for drift detection.

Unlike z-score, CUSUM accumulates evidence over time.  A value that is 1σ
above the reference mean ten times in a row will trigger CUSUM; a memoryless
z-score will never see those as anomalous.

Algorithm — two-sided CUSUM on STL residuals:
    S_pos[t] = max(0,  S_pos[t-1] + (x[t] - k))   ← detects upward drift
    S_neg[t] = max(0,  S_neg[t-1] + (-x[t] - k))  ← detects downward drift
    Alarm fires when S_pos > H  OR  S_neg > H.

where:
    x[t] — STL residual (centred at 0 by calibration; μ_ref ≈ 0)
    k    — allowance  = 0.5 × σ_ref  (from CalibrationState.cusum_k)
    H    — threshold  = 5.0 × σ_ref  (from CalibrationState.cusum_h)

These values (k=0.5σ, H=5σ) are the NASA/ESA standard for spacecraft
telemetry monitoring.  k=0.5σ means "detect a shift of 1σ or larger".
H=5σ means "require enough accumulated evidence to be 5σ confident".

After alarm:
    Accumulators are reset to zero (standard CUSUM practice).
    The reset allows CUSUM to detect the NEXT event independently.

Score normalisation: score = max(S_pos, S_neg) / H
    score = 0   → accumulators at zero (nominal)
    score = 1.0 → exactly at threshold (alarm boundary)
    score > 1.0 clipped to 1.0

Per-channel state (S_pos, S_neg) is held in memory and flushed to the
detector_state DB table every STATE_FLUSH_EVERY detection cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from aria.dsremo.core.models import DetectorResult, Severity
from aria.dsremo.detection.calibration import CalibrationState

logger = structlog.get_logger()

# How far above the threshold S must be to escalate severity.
# ESTIMATE — 1.5H/2.5H ratios: NASA GSFC telemetry monitoring practice (no single published source)
_WARN_RATIO:     float = 1.5   # S > 1.5H → WARNING (ESTIMATE — NASA GSFC monitoring practice)
_CRITICAL_RATIO: float = 2.5   # S > 2.5H → CRITICAL (ESTIMATE — NASA GSFC monitoring practice)


@dataclass
class _CUSUMState:
    s_pos:       float = 0.0
    s_neg:       float = 0.0
    alarm_count: int   = 0


class CUSUMDetector:
    """Two-sided CUSUM on STL residuals.  One state entry per channel key."""

    def __init__(self) -> None:
        self._states: dict[str, _CUSUMState] = {}

    # ── detection ───────────────────────────────────────────────────────

    def detect(
        self,
        key: str,
        residual: float,
        calibration: CalibrationState,
    ) -> DetectorResult:
        """Run one CUSUM step.

        Args:
            key:         Channel key, e.g. "ESA-MISSION1:channel_047".
            residual:    Latest STL residual value (centred near 0).
            calibration: Calibration state with .cusum_k and .cusum_h set.

        Returns:
            DetectorResult.  is_anomaly=False during warm-up (calibration
            not yet ready).  score is always returned so the ensemble can
            use partial evidence even before full calibration.
        """
        if not calibration.is_calibrated:
            return self._nominal(key, reason="warming_up")

        k = calibration.cusum_k
        h = calibration.cusum_h

        if h < 1e-9:
            return self._nominal(key, reason="zero_threshold")

        state = self._states.setdefault(key, _CUSUMState())

        # Update both accumulators.
        state.s_pos = max(0.0, state.s_pos + (residual - k))
        state.s_neg = max(0.0, state.s_neg + (-residual - k))

        max_s   = max(state.s_pos, state.s_neg)
        score   = min(1.0, max_s / h)
        is_alarm = max_s > h

        if is_alarm:
            state.alarm_count += 1
            severity  = self._severity(max_s, h)
            direction = "positive" if state.s_pos >= state.s_neg else "negative"
            details   = {
                "s_pos":       round(state.s_pos, 6),
                "s_neg":       round(state.s_neg, 6),
                "k":           round(k, 6),
                "h":           round(h, 6),
                "direction":   direction,
                "alarm_count": state.alarm_count,
                "residual":    round(residual, 6),
            }
            # Reset after alarm — next event starts fresh accumulation.
            state.s_pos = 0.0
            state.s_neg = 0.0
        else:
            severity = Severity.NOMINAL
            direction = "positive" if state.s_pos >= state.s_neg else "negative"
            details   = {
                "s_pos":     round(state.s_pos, 6),
                "s_neg":     round(state.s_neg, 6),
                "k":         round(k, 6),
                "h":         round(h, 6),
                "direction": direction,
                "residual":  round(residual, 6),
            }

        return DetectorResult(
            detector_name="cusum",
            is_anomaly=is_alarm,
            score=float(score),
            severity=severity,
            details=details,
        )

    # ── state persistence ────────────────────────────────────────────────

    def get_state(self, key: str) -> dict:
        s = self._states.get(key, _CUSUMState())
        return {"s_pos": s.s_pos, "s_neg": s.s_neg, "alarm_count": s.alarm_count}

    def load_state(self, key: str, data: dict) -> None:
        self._states[key] = _CUSUMState(
            s_pos=float(data.get("s_pos", 0.0)),
            s_neg=float(data.get("s_neg", 0.0)),
            alarm_count=int(data.get("alarm_count", 0)),
        )

    def all_states(self) -> dict[str, dict]:
        return {k: self.get_state(k) for k in self._states}

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _severity(max_s: float, h: float) -> Severity:
        ratio = max_s / h
        if ratio >= _CRITICAL_RATIO:
            return Severity.CRITICAL
        if ratio >= _WARN_RATIO:
            return Severity.WARNING
        return Severity.WATCH

    @staticmethod
    def _nominal(key: str, reason: str) -> DetectorResult:
        return DetectorResult(
            detector_name="cusum",
            is_anomaly=False,
            score=0.0,
            severity=Severity.NOMINAL,
            details={"reason": reason},
        )
