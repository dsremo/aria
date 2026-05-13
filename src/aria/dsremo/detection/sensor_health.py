"""V3-M1: Sensor health model — separates sensor degradation from physical anomalies.

Problem
-------
Spacecraft sensors degrade progressively under the space radiation environment.
Three degradation mechanisms dominate on multi-year missions:

  1. ADC offset drift (zero-code error grows with Total Ionizing Dose)
  2. Gain error (sensor sensitivity decreases with TID accumulation)
  3. Reference voltage drift (bandgap reference under proton fluence)

A sensor with 2 % gain error reports a 28.56 V battery voltage when the true
voltage is 29.14 V.  Without a sensor health model, this looks like a gradual
voltage drop and triggers CUSUM — misclassifying sensor degradation as a
subsystem fault.

Solution
--------
Track per-channel `SensorCalibration` state:
    gain_error_estimate, offset_error_estimate, last_calibration_epoch,
    noise_floor_sigma

Each periodic ground calibration (commandable built-in test, BIT) produces a
fresh set of coefficients.  Between calibrations the coefficients are held
constant; the estimate ages with time elapsed since `last_calibration_epoch`.

Apply the correction BEFORE the raw value enters the detection pipeline:
    corrected_value = (raw_value − offset_estimate) / (1 + gain_error_estimate)

Readings from sensors with high estimated errors receive a reduced `quality`
score so downstream detectors weight them appropriately (NASA/TM-2010-216260
§4.3).

Reference
---------
NASA/TM-2010-216260 (2010) "Model-Based Prognostics With Concurrent Damage
Progression Processes", §4.3: sensor model decomposition.

ECSS-E-ST-10-09C (2008) Appendix B: sensor calibration traceability.

ECSS-Q-ST-60-02C (2013) §4.2: TID-dependent parameter drift for space
electronics.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum, unique
from typing import TYPE_CHECKING, Iterable

import structlog

if TYPE_CHECKING:
    from aria.dsremo.core.models import TelemetryPoint

logger = structlog.get_logger()


# ── Sensor health thresholds (ECSS-Q-ST-60-02C §4.2) ─────────────────────────
# A 1 % gain error is the industry-standard acceptance limit for analog
# telemetry channels (ECSS-E-ST-20C §5.3.2: instrument conditioning chain
# accuracy).  Above this the reading is considered degraded.
GAIN_ERROR_DEGRADED:        float = 0.01   # 1 % gain error (ECSS-E-ST-20C §5.3.2)
# At 5 % the reading is untrustworthy; quality floors at 0.5.
GAIN_ERROR_UNTRUSTWORTHY:   float = 0.05   # 5 % gain error (ESTIMATE — Goebel 2011 PHM §3.2)

# Typical ADC zero-code error at launch is ≤ 0.1 % of full-scale range
# (MIL-STD-750E §4047).  Use 1 % of full-scale as the degraded threshold
# and 5 % as untrustworthy.
OFFSET_ERROR_DEGRADED_FRAC:      float = 0.01   # 1 % of range (MIL-STD-750E §4047)
OFFSET_ERROR_UNTRUSTWORTHY_FRAC: float = 0.05   # 5 % of range (ESTIMATE — consistent with gain tiers)

# Quality penalties applied when sensor is in each health tier.
# Normal ingestion defaults quality=1.0; penalised values reduce the weight
# of that reading in the ensemble confidence calculation.
QUALITY_NOMINAL:      float = 1.0   # healthy sensor
QUALITY_DEGRADED:     float = 0.8   # NASA/TM-2010-216260 §4.3: degraded sensor weight
QUALITY_UNTRUSTWORTHY: float = 0.5  # ESTIMATE — halves detector confidence

# Maximum age (seconds) before a calibration is considered stale.
# ISS uses monthly sensor calibration; LEO missions typically use quarterly
# (90 days) BIT commands.  ECSS-E-ST-10-09C §4.1.3 recommends re-calibration
# at least once per quarter for mission-critical telemetry chains.
CALIBRATION_STALE_S: float = 90.0 * 86400.0  # 90 days (ECSS-E-ST-10-09C §4.1.3)


@unique
class SensorHealthTier(str, Enum):
    """Health tier of one telemetry channel's sensor chain."""

    NOMINAL       = "nominal"
    DEGRADED      = "degraded"
    UNTRUSTWORTHY = "untrustworthy"
    STALE         = "stale"        # calibration expired


@dataclass
class SensorCalibration:
    """Current calibration + health estimate for one (satellite, parameter) pair.

    Fields
    ------
    gain_error_estimate:   Fractional gain error.  0.0 = perfect, 0.02 = +2 %.
                           True = raw / (1 + gain_error_estimate).
    offset_error_estimate: Absolute offset error in engineering units.
                           True = raw − offset_error_estimate.
    noise_floor_sigma:     Estimated per-sample noise σ (engineering units).
    last_calibration_epoch: Unix seconds of the last BIT calibration.
    range_full_scale:      Full-scale range used to normalise the offset for
                           the "% of range" thresholds.  0 → offset tier
                           disabled (only gain error is used).
    tier:                  Computed health tier; updated on every refresh.
    """

    satellite_id:           str
    parameter:              str
    gain_error_estimate:    float = 0.0
    offset_error_estimate:  float = 0.0
    noise_floor_sigma:      float = 0.0
    last_calibration_epoch: float = 0.0
    range_full_scale:       float = 0.0
    tier:                   SensorHealthTier = SensorHealthTier.NOMINAL
    # Append-only history of (epoch, gain_error, offset_error) for trend analysis.
    history: list[tuple[float, float, float]] = field(default_factory=list, repr=False)

    def corrected_value(self, raw_value: float) -> float:
        """Apply the sensor model to map raw → corrected (engineering units).

        Two-stage correction (NASA/TM-2010-216260 §4.3 eq. 7):
            corrected = (raw − offset_estimate) / (1 + gain_estimate)

        Gracefully degrades when gain_estimate approaches −1 (which would
        divide by zero).  Any gain error below −50 % is treated as pathological
        and returns the raw value unchanged to avoid sign flips.
        """
        g = self.gain_error_estimate
        if g <= -0.5:
            return raw_value
        return (raw_value - self.offset_error_estimate) / (1.0 + g)

    def quality_factor(self, now_epoch: float | None = None) -> float:
        """Quality weight in [0, 1] combining tier + calibration freshness.

        Stale calibrations are compounded with the tier penalty: a sensor that
        was marginally degraded but has missed its BIT cycle for 90 days is
        trusted less than one freshly calibrated at the same error level.
        """
        base = {
            SensorHealthTier.NOMINAL:       QUALITY_NOMINAL,
            SensorHealthTier.DEGRADED:      QUALITY_DEGRADED,
            SensorHealthTier.UNTRUSTWORTHY: QUALITY_UNTRUSTWORTHY,
            SensorHealthTier.STALE:         QUALITY_DEGRADED,
        }[self.tier]

        if now_epoch is None or self.last_calibration_epoch <= 0:
            return base
        age = now_epoch - self.last_calibration_epoch
        if age <= CALIBRATION_STALE_S:
            return base
        # Linear decay past the stale threshold, floored at 0.25.
        decay = max(0.25, base * (CALIBRATION_STALE_S / age))  # noqa: PLR2004
        return decay


class SensorHealthMonitor:
    """Per-process registry of sensor calibration state.

    Populate via `record_calibration` after each ground BIT cycle.  The
    ingestion pipeline calls `apply_correction(satellite_id, parameter, raw,
    quality)` to transform raw telemetry before it reaches the detectors.

    All per-channel state is in memory.  Persistence to the database is the
    responsibility of the caller (insert_calibration / load_calibrations).
    """

    def __init__(self) -> None:
        self._cal: dict[tuple[str, str], SensorCalibration] = {}

    # --------------------------------------------------------------------- #
    # Lookup / mutation                                                      #
    # --------------------------------------------------------------------- #

    def get(self, satellite_id: str, parameter: str) -> SensorCalibration | None:
        return self._cal.get((satellite_id, parameter))

    def get_or_create(
        self, satellite_id: str, parameter: str, range_full_scale: float = 0.0
    ) -> SensorCalibration:
        key = (satellite_id, parameter)
        cal = self._cal.get(key)
        if cal is None:
            cal = SensorCalibration(
                satellite_id=satellite_id,
                parameter=parameter,
                range_full_scale=range_full_scale,
            )
            self._cal[key] = cal
        return cal

    def record_calibration(
        self,
        satellite_id: str,
        parameter: str,
        gain_error: float,
        offset_error: float,
        noise_floor_sigma: float = 0.0,
        range_full_scale: float = 0.0,
        epoch: float | None = None,
    ) -> SensorCalibration:
        """Record a new BIT (built-in-test) result for this channel.

        Callers provide the measured gain error (fractional, e.g. 0.012 for
        +1.2 %) and offset error (absolute, engineering units).  The monitor
        stores the values, stamps with the current time, appends to the
        history, and recomputes the health tier.
        """
        now = epoch if epoch is not None else datetime.now(timezone.utc).timestamp()
        cal = self.get_or_create(satellite_id, parameter, range_full_scale)
        if range_full_scale > 0.0:
            cal.range_full_scale = range_full_scale
        cal.gain_error_estimate    = float(gain_error)
        cal.offset_error_estimate  = float(offset_error)
        cal.noise_floor_sigma      = float(noise_floor_sigma)
        cal.last_calibration_epoch = float(now)
        cal.history.append((now, float(gain_error), float(offset_error)))
        cal.tier = self._compute_tier(cal, now)
        logger.info(
            "sensor_calibration_recorded",
            satellite_id=satellite_id,
            parameter=parameter,
            gain_error=gain_error,
            offset_error=offset_error,
            tier=cal.tier.value,
        )
        return cal

    def refresh_tier(
        self, satellite_id: str, parameter: str, now_epoch: float | None = None
    ) -> SensorHealthTier:
        """Recompute the health tier from stored state.  Returns the new tier."""
        cal = self.get(satellite_id, parameter)
        if cal is None:
            return SensorHealthTier.NOMINAL
        now = now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()
        cal.tier = self._compute_tier(cal, now)
        return cal.tier

    # --------------------------------------------------------------------- #
    # Ingestion hook                                                         #
    # --------------------------------------------------------------------- #

    def apply_correction(
        self,
        satellite_id: str,
        parameter: str,
        raw_value: float,
        quality: float = 1.0,
        now_epoch: float | None = None,
    ) -> tuple[float, float, SensorHealthTier]:
        """Map (raw_value, quality) → (corrected_value, adjusted_quality, tier).

        Called by the ingestion pipeline for every telemetry sample.  When
        no calibration record exists for the channel, the raw value is
        returned unchanged and the quality is unaltered — this preserves
        backward compatibility with channels that have never been calibrated.
        """
        cal = self.get(satellite_id, parameter)
        if cal is None:
            return raw_value, quality, SensorHealthTier.NOMINAL

        now = now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp()
        cal.tier = self._compute_tier(cal, now)
        corrected = cal.corrected_value(raw_value)
        q_factor  = cal.quality_factor(now)
        # Multiplicative combination: a half-quality input on a half-quality
        # sensor emerges at quality 0.25 — both penalties compound.
        return corrected, quality * q_factor, cal.tier

    def channels_in_tier(self, tier: SensorHealthTier) -> list[tuple[str, str]]:
        """Return all (satellite_id, parameter) pairs currently in `tier`."""
        return [k for k, cal in self._cal.items() if cal.tier == tier]

    def iter_calibrations(self) -> Iterable[SensorCalibration]:
        """Iterate every stored calibration (for persistence / reporting)."""
        return self._cal.values()

    # --------------------------------------------------------------------- #
    # Tier classifier                                                        #
    # --------------------------------------------------------------------- #

    @staticmethod
    def _compute_tier(cal: SensorCalibration, now_epoch: float) -> SensorHealthTier:
        """Classify sensor health from gain, offset, and calibration age."""
        g = abs(cal.gain_error_estimate)
        # Offset threshold scales with the channel's full-scale range when
        # it is known; otherwise use an absolute fallback of 1 e-3 (ESTIMATE —
        # a conservative default for channels with unknown range).
        if cal.range_full_scale > 0.0:
            off_deg = OFFSET_ERROR_DEGRADED_FRAC      * cal.range_full_scale
            off_unt = OFFSET_ERROR_UNTRUSTWORTHY_FRAC * cal.range_full_scale
        else:
            off_deg = 1.0e-3  # ESTIMATE — absolute fallback when range unknown
            off_unt = 5.0e-3  # ESTIMATE — absolute fallback when range unknown
        o = abs(cal.offset_error_estimate)

        # Stale calibration overrides all other conditions.
        if (
            cal.last_calibration_epoch > 0
            and (now_epoch - cal.last_calibration_epoch) > CALIBRATION_STALE_S
        ):
            return SensorHealthTier.STALE

        if g >= GAIN_ERROR_UNTRUSTWORTHY or o >= off_unt:
            return SensorHealthTier.UNTRUSTWORTHY
        if g >= GAIN_ERROR_DEGRADED or o >= off_deg:
            return SensorHealthTier.DEGRADED
        return SensorHealthTier.NOMINAL


# ── Process-wide singleton ────────────────────────────────────────────────── #

_monitor: SensorHealthMonitor | None = None


def get_monitor() -> SensorHealthMonitor:
    """Return the process-wide SensorHealthMonitor, creating it on first call."""
    global _monitor
    if _monitor is None:
        _monitor = SensorHealthMonitor()
    return _monitor


def reset_monitor() -> None:
    """Discard the process-wide monitor. Test/harness helper."""
    global _monitor
    _monitor = None


def apply_sensor_corrections(
    points: list["TelemetryPoint"],
    monitor: SensorHealthMonitor | None = None,
    now_epoch: float | None = None,
) -> list["TelemetryPoint"]:
    """Apply sensor health correction to every TelemetryPoint in the batch.

    For each point we look up the channel's SensorCalibration.  When the
    channel is unknown the point is returned unchanged — the monitor is a
    pure enrichment layer, never a gate.  The returned list preserves order
    and length so callers can swap `points = apply_sensor_corrections(points)`
    with no other wiring changes.

    Args
    ----
    points:    List of TelemetryPoint to correct.  Points are immutable
               (frozen=True) so corrected copies are produced via `replace`.
    monitor:   Optional explicit monitor (dependency-injected in tests);
               falls back to the process-wide singleton.
    now_epoch: Optional override for the current time — used for deterministic
               stale-tier computation in tests.

    Returns
    -------
    A new list with each point's `value` and `quality` replaced by the
    corrected values.  Subsystem, parameter, timestamp and other fields
    are preserved.
    """
    mon = monitor if monitor is not None else get_monitor()
    out: list[TelemetryPoint] = []
    for p in points:
        corrected_value, corrected_quality, _tier = mon.apply_correction(
            p.satellite_id, p.parameter, p.value, p.quality, now_epoch
        )
        if (
            corrected_value == p.value
            and corrected_quality == p.quality
        ):
            out.append(p)
        else:
            out.append(replace(p, value=corrected_value, quality=corrected_quality))
    return out
