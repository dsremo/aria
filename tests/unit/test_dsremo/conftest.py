"""Shared test fixtures — no database required for unit tests.

Integration tests that need a real DB are marked with @pytest.mark.integration.
"""

from __future__ import annotations

import pytest
import numpy as np
from datetime import datetime, timezone

from aria.dsremo.core.models import TelemetryPoint, Anomaly, Severity
from aria.dsremo.simulate.spacecraft import SpacecraftSimulator
from aria.dsremo.features.engine import FeatureEngine


@pytest.fixture
def sample_point() -> TelemetryPoint:
    return TelemetryPoint(
        satellite_id="TEST-SAT-01",
        timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        subsystem="eps",
        parameter="battery_voltage",
        value=7.4,
        unit="V",
        quality=1.0,
    )


@pytest.fixture
def sample_anomaly() -> Anomaly:
    return Anomaly(
        satellite_id="TEST-SAT-01",
        timestamp=datetime(2025, 6, 15, 12, 5, 0, tzinfo=timezone.utc),
        subsystem="eps",
        parameter="battery_voltage",
        value=5.8,
        severity=Severity.WARNING,
        confidence=0.72,
        detectors_triggered=("statistical", "isolation_forest"),
        explanation="battery_voltage = 5.8V (rolling avg: 7.4V, std: 0.1V) | Z-score: 16.0",
        contributing_params={"solar_array_current": -0.3, "battery_current": 0.2},
    )


@pytest.fixture
def simulator() -> SpacecraftSimulator:
    return SpacecraftSimulator(
        satellite_id="TEST-SAT-01",
        rate_hz=1.0,
        noise_level=0.02,
        seed=42,
    )


@pytest.fixture
def feature_engine() -> FeatureEngine:
    return FeatureEngine(window_size=100)


@pytest.fixture
def normal_signal() -> np.ndarray:
    """A clean sinusoidal signal representing normal telemetry."""
    rng = np.random.default_rng(42)
    t = np.linspace(0, 10, 500)
    return 7.4 + 0.1 * np.sin(2 * np.pi * t / 5) + rng.normal(0, 0.02, 500)


@pytest.fixture
def anomalous_signal() -> np.ndarray:
    """A signal with an injected anomaly (sudden drop at index 300)."""
    rng = np.random.default_rng(42)
    signal = 7.4 + rng.normal(0, 0.05, 500)
    signal[300:] -= 1.5  # sudden voltage drop
    return signal
