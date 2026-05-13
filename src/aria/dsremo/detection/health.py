"""Detection pipeline health check and graceful degradation.

Provides a health endpoint that reports per-detector status, overall
pipeline health, and memory usage.  When individual detectors fail,
the pipeline degrades gracefully rather than failing entirely.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class DetectorHealth:
    """Health status for a single detector."""
    name: str
    healthy: bool = True
    last_error: str | None = None
    last_error_at: float | None = None
    error_count: int = 0
    total_calls: int = 0
    avg_latency_ms: float = 0.0
    _latency_sum: float = field(default=0.0, repr=False)

    def record_success(self, latency_ms: float) -> None:
        self.total_calls += 1
        self._latency_sum += latency_ms
        self.avg_latency_ms = self._latency_sum / self.total_calls
        self.healthy = True

    def record_error(self, error: str) -> None:
        self.error_count += 1
        self.total_calls += 1
        self.last_error = error
        self.last_error_at = time.time()
        # Mark unhealthy if error rate > 50% in recent calls
        if self.total_calls > 10 and self.error_count / self.total_calls > 0.5:
            self.healthy = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "healthy": self.healthy,
            "error_count": self.error_count,
            "total_calls": self.total_calls,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "last_error": self.last_error,
        }


class PipelineHealth:
    """Aggregate health monitor for the detection pipeline."""

    def __init__(self) -> None:
        self._detectors: dict[str, DetectorHealth] = {}
        self._pipeline_start: float = time.time()
        self._total_cycles: int = 0
        self._total_anomalies: int = 0

    def get_detector(self, name: str) -> DetectorHealth:
        if name not in self._detectors:
            self._detectors[name] = DetectorHealth(name=name)
        return self._detectors[name]

    def record_cycle(self, n_anomalies: int) -> None:
        self._total_cycles += 1
        self._total_anomalies += n_anomalies

    def health_check(self) -> dict:
        """Return full pipeline health status."""
        detector_statuses = {
            name: dh.to_dict() for name, dh in self._detectors.items()
        }
        unhealthy = [name for name, dh in self._detectors.items() if not dh.healthy]

        return {
            "status": "degraded" if unhealthy else "healthy",
            "uptime_s": round(time.time() - self._pipeline_start, 1),
            "total_cycles": self._total_cycles,
            "total_anomalies": self._total_anomalies,
            "unhealthy_detectors": unhealthy,
            "detectors": detector_statuses,
        }

    def is_healthy(self) -> bool:
        return all(dh.healthy for dh in self._detectors.values())


# Singleton
_health = PipelineHealth()


def get_pipeline_health() -> PipelineHealth:
    return _health
