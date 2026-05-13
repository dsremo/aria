"""Metrics Collector — tracks latency, throughput, and resource usage.

Provides Prometheus-style counters, gauges, and histograms for:
  - Tool execution latency (per tool, P50/P95/P99)
  - Message bus throughput
  - Agent processing time
  - Cognitive engine reasoning duration
  - Memory usage
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatencyHistogram:
    """Tracks latency distribution for a metric."""

    name: str
    values: list[float] = field(default_factory=list)
    _max_samples: int = 1000

    def record(self, value_ms: float) -> None:
        self.values.append(value_ms)
        if len(self.values) > self._max_samples:
            self.values = self.values[-self._max_samples:]

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def p50(self) -> float:
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = len(sorted_vals) // 2
        return sorted_vals[idx]

    @property
    def p95(self) -> float:
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * 0.95)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    @property
    def p99(self) -> float:
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        idx = int(len(sorted_vals) * 0.99)
        return sorted_vals[min(idx, len(sorted_vals) - 1)]

    @property
    def mean(self) -> float:
        return statistics.mean(self.values) if self.values else 0.0

    def summary(self) -> dict[str, float]:
        return {
            "count": self.count,
            "mean_ms": round(self.mean, 2),
            "p50_ms": round(self.p50, 2),
            "p95_ms": round(self.p95, 2),
            "p99_ms": round(self.p99, 2),
        }


class MetricsCollector:
    """Centralized metrics collection for ARIA."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, LatencyHistogram] = {}
        self._start_time = time.time()

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a counter."""
        self._counters[name] += amount

    def gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        self._gauges[name] = value

    def record_latency(self, name: str, value_ms: float) -> None:
        """Record a latency sample."""
        if name not in self._histograms:
            self._histograms[name] = LatencyHistogram(name=name)
        self._histograms[name].record(value_ms)

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def get_gauge(self, name: str) -> float:
        return self._gauges.get(name, 0.0)

    def get_histogram(self, name: str) -> LatencyHistogram | None:
        return self._histograms.get(name)

    def snapshot(self) -> dict[str, Any]:
        """Full metrics snapshot."""
        return {
            "uptime_s": round(time.time() - self._start_time, 1),
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: hist.summary() for name, hist in self._histograms.items()
            },
        }

    def reset(self) -> None:
        """Reset all metrics (for testing)."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._start_time = time.time()
