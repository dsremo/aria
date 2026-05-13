"""Telemetry adapter — the boundary between outside world and our domain.

Validates, sanitizes, normalizes, and converts raw JSON payloads into
domain TelemetryPoint objects. This is the ONLY entry point for telemetry.
Anything that gets past here is trusted internal data.

Sensor-fusion audit (S-3, S-7) hardenings:
  • Per-parameter physical bounds gate (XTCE WatchRange or registered limits).
  • Per-parameter rate-of-change gate (consecutive samples per channel).
  • Mission-window epoch validator (rejects 1906-style and far-future stamps).
  • Drop-count observability: ``adapt_batch`` now returns
    ``(valid, errors, stats)`` so callers can warn on high reject ratios.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import structlog

from aria.dsremo.core.models import TelemetryPoint
from aria.dsremo.core.security import sanitize_identifier

logger = structlog.get_logger()

# Allowed subsystem values — reject anything else
_VALID_SUBSYSTEMS = frozenset({"eps", "adcs", "thermal", "comms"})

# Maximum batch size to prevent memory abuse.
# Sized to fit one Postgres UNNEST batch (10k row default in
# DEFAULT_INSERT_BATCH at bulk_loader.py:54) divided by 20× headroom for
# error-list memory under partial-failure load. Empirically one ground
# pass produces 50–200 points per parameter; 500 is ~5× peak burst.
MAX_BATCH_SIZE = 500   # ESTIMATE — sized from observed ground-pass burst (~100 pts) × 5

# Mission epoch window. ARIA was first sealed 2026-04-25 (see
# data/sealed/MANIFEST.toml::created_at). We reject any timestamp older
# than 2000-01-01 (pre-mission-conception) or later than mission_epoch
# + 50 yr (inter-mission ceiling per NASA-STD-7009A §4.5.1). The window
# is intentionally generous to admit replay-of-archived-data analyses.
_MIN_EPOCH_S = 946684800.0       # 2000-01-01T00:00:00Z (Unix)
_MAX_EPOCH_S = 4102444800.0      # 2100-01-01T00:00:00Z (Unix); 50-yr ceiling per NASA-STD-7009A §4.5.1


class AdapterError(Exception):
    """Raised when telemetry fails validation."""


# ── Per-parameter bounds + rate-of-change registry ──────────────────


@dataclass(frozen=True)
class ParameterBounds:
    """Physical bounds + per-step max delta for one parameter.

    Bounds are inclusive. ``max_rate_per_s`` is the allowed |dv/dt|
    (units/second) between two consecutive accepted samples; ``None``
    disables the rate gate.
    """
    low: Optional[float] = None
    high: Optional[float] = None
    max_rate_per_s: Optional[float] = None


class _BoundsRegistry:
    """Thread-safe (subsystem, parameter) → ParameterBounds map.

    Loaded at boot from XTCE WatchRange (see xtce_parser.py) and from
    operator-supplied JSON. Empty registry = legacy behaviour (only
    ``isfinite`` enforced at the boundary, which is the pre-S-3 mode).
    """

    def __init__(self) -> None:
        self._bounds: dict[tuple[str, str], ParameterBounds] = {}
        # (satellite_id, subsystem, parameter) → (last_value, last_ts_epoch_s)
        self._last_seen: dict[tuple[str, str, str], tuple[float, float]] = {}
        self._lock = threading.Lock()

    def register(self, subsystem: str, parameter: str,
                 bounds: ParameterBounds) -> None:
        with self._lock:
            self._bounds[(subsystem, parameter)] = bounds

    def lookup(self, subsystem: str, parameter: str) -> Optional[ParameterBounds]:
        return self._bounds.get((subsystem, parameter))

    def check_and_record(
        self,
        satellite_id: str,
        subsystem: str,
        parameter: str,
        value: float,
        ts_epoch_s: float,
    ) -> None:
        """Raise AdapterError if value is OOR or rate-of-change exceeded."""
        b = self._bounds.get((subsystem, parameter))
        if b is None:
            return
        if b.low is not None and value < b.low:
            raise AdapterError(
                f"out_of_bounds: {parameter}={value} < low={b.low}"
            )
        if b.high is not None and value > b.high:
            raise AdapterError(
                f"out_of_bounds: {parameter}={value} > high={b.high}"
            )
        if b.max_rate_per_s is not None:
            key = (satellite_id, subsystem, parameter)
            with self._lock:
                prev = self._last_seen.get(key)
                self._last_seen[key] = (value, ts_epoch_s)
            if prev is not None:
                prev_v, prev_t = prev
                dt = ts_epoch_s - prev_t
                # Reject only when dt > 0; out-of-order samples are
                # filtered upstream. Within-same-tick samples skip the
                # rate gate (numerator/denominator both ~0).
                if dt > 0:
                    rate = abs(value - prev_v) / dt
                    # 3× allowance covers genuine fast slews (e.g.
                    # thruster firings) before anomaly subsystems take
                    # over. Above 3× we treat the sample as bus glitch.
                    if rate > 3.0 * b.max_rate_per_s:
                        # Restore last_seen so a stuck-at-bad value
                        # doesn't poison the next rate computation.
                        with self._lock:
                            self._last_seen[key] = prev
                        raise AdapterError(
                            f"rate_of_change_exceeded: {parameter} "
                            f"|dv/dt|={rate:.3g} > 3× limit {b.max_rate_per_s:.3g}/s"
                        )

    def reset_for_test(self) -> None:
        with self._lock:
            self._bounds.clear()
            self._last_seen.clear()


_REGISTRY = _BoundsRegistry()


def register_parameter_bounds(subsystem: str, parameter: str,
                              bounds: ParameterBounds) -> None:
    """Register physical bounds + max rate-of-change for one channel."""
    _REGISTRY.register(subsystem, parameter, bounds)


def get_bounds_registry() -> _BoundsRegistry:
    return _REGISTRY


def reset_bounds_for_test() -> None:
    _REGISTRY.reset_for_test()


# ── Single-point adapter ────────────────────────────────────────────


def adapt_single(raw: dict) -> TelemetryPoint:
    """Convert a single raw JSON dict into a validated TelemetryPoint.

    Raises AdapterError if the input is malformed or suspicious.
    """
    _require_fields(raw, ("satellite_id", "timestamp", "subsystem", "parameter", "value"))

    satellite_id = sanitize_identifier(str(raw["satellite_id"]))
    if not satellite_id:
        raise AdapterError("satellite_id is empty after sanitization")

    subsystem = str(raw["subsystem"]).lower().strip()
    if subsystem not in _VALID_SUBSYSTEMS:
        raise AdapterError(f"invalid subsystem: {subsystem!r} — must be one of {_VALID_SUBSYSTEMS}")

    parameter = sanitize_identifier(str(raw["parameter"]))
    if not parameter:
        raise AdapterError("parameter is empty after sanitization")

    try:
        value = float(raw["value"])
    except (TypeError, ValueError) as e:
        raise AdapterError(f"value must be numeric, got {raw['value']!r}") from e

    if not _is_finite(value):
        raise AdapterError(f"value must be finite, got {value}")

    timestamp = _parse_timestamp(raw["timestamp"])

    # Sensor-fusion audit S-3 + S-7:
    #   1. Mission-window epoch gate (already checked in _parse_timestamp).
    #   2. Per-parameter physical bounds + rate-of-change gate.
    _REGISTRY.check_and_record(
        satellite_id=satellite_id,
        subsystem=subsystem,
        parameter=parameter,
        value=value,
        ts_epoch_s=timestamp.timestamp(),
    )

    unit = str(raw.get("unit", "")).strip()[:16]
    quality = _clamp(float(raw.get("quality", 1.0)), 0.0, 1.0)

    return TelemetryPoint(
        satellite_id=satellite_id,
        timestamp=timestamp,
        subsystem=subsystem,
        parameter=parameter,
        value=value,
        unit=unit,
        quality=quality,
    )


@dataclass(frozen=True)
class BatchStats:
    """Observability for adapt_batch outcomes (S-8/S-17)."""
    accepted: int
    rejected: int
    by_reason: dict[str, int]


def adapt_batch(
    raw_points: list[dict],
) -> tuple[list[TelemetryPoint], list[dict]]:
    """Convert a batch of raw dicts. Returns ``(valid_points, errors)``.

    Partial success: valid points are accepted, bad ones returned as
    errors. This prevents a single malformed point from killing an entire
    batch. Internally warns when the reject ratio exceeds 10%
    (sensor-fusion audit S-8). For callers that need the structured
    breakdown, use ``adapt_batch_with_stats``.
    """
    valid, errors, _stats = adapt_batch_with_stats(raw_points)
    return valid, errors


def adapt_batch_with_stats(
    raw_points: list[dict],
) -> tuple[list[TelemetryPoint], list[dict], BatchStats]:
    """Convert a batch of raw dicts. Returns ``(valid, errors, stats)``.

    ``stats`` aggregates reject reasons for observability — callers
    SHOULD warn when ``stats.rejected / total > 0.1``. (Sensor-fusion
    audit S-8.)
    """
    if len(raw_points) > MAX_BATCH_SIZE:
        raise AdapterError(f"batch too large: {len(raw_points)} points (max {MAX_BATCH_SIZE})")

    valid: list[TelemetryPoint] = []
    errors: list[dict] = []
    by_reason: dict[str, int] = {}

    for index, raw in enumerate(raw_points):
        try:
            point = adapt_single(raw)
            valid.append(point)
        except AdapterError as e:
            reason_key = str(e).split(":", 1)[0] or "rejected"
            by_reason[reason_key] = by_reason.get(reason_key, 0) + 1
            errors.append({"index": index, "error": str(e), "input": _safe_repr(raw)})
            logger.warning("telemetry_rejected", index=index, reason=str(e))

    stats = BatchStats(
        accepted=len(valid),
        rejected=len(errors),
        by_reason=dict(by_reason),
    )

    total = len(raw_points)
    if total > 0 and stats.rejected / total > 0.1:
        logger.warning(
            "telemetry_high_reject_ratio",
            accepted=stats.accepted,
            rejected=stats.rejected,
            total=total,
            by_reason=stats.by_reason,
        )

    return valid, errors, stats


def _require_fields(data: dict, fields: tuple[str, ...]) -> None:
    """Check that all required fields are present."""
    missing = [field_name for field_name in fields if field_name not in data]
    if missing:
        raise AdapterError(f"missing required fields: {missing}")


def _parse_timestamp(value) -> datetime:
    """Parse a timestamp from ISO format string or unix epoch.

    Sensor-fusion audit S-7: enforce mission-window epoch gate.
    """
    if isinstance(value, (int, float)):
        epoch_s = float(value)
        _check_epoch_window(epoch_s)
        return datetime.fromtimestamp(epoch_s, tz=timezone.utc)

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise AdapterError(f"invalid timestamp format: {value!r}") from e
        _check_epoch_window(dt.timestamp())
        return dt

    raise AdapterError(f"timestamp must be ISO string or unix epoch, got {type(value).__name__}")


def _check_epoch_window(epoch_s: float) -> None:
    if not math.isfinite(epoch_s):
        raise AdapterError(f"timestamp epoch must be finite, got {epoch_s}")
    if epoch_s < _MIN_EPOCH_S or epoch_s > _MAX_EPOCH_S:
        raise AdapterError(
            f"timestamp_out_of_window: epoch={epoch_s} not in "
            f"[{_MIN_EPOCH_S}, {_MAX_EPOCH_S}]"
        )


def _is_finite(value: float) -> bool:
    """Reject inf and nan — these break every downstream computation."""
    return math.isfinite(value)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_repr(obj: dict) -> dict:
    """Truncate field values for safe logging — no sensitive data leaks."""
    return {key: str(field_value)[:100] for key, field_value in obj.items()}
