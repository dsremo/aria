"""Tests for the API endpoints — uses TestClient (no real DB needed for schema tests)."""

import pytest
from datetime import datetime, timezone

from aria.dsremo.api.schemas import (
    TelemetryIn,
    TelemetryBatchIn,
    InjectRequest,
    SimulateRequest,
    AnomalyOut,
)
from pydantic import ValidationError


class TestTelemetrySchemas:
    def test_valid_telemetry_in(self):
        t = TelemetryIn(
            satellite_id="SAT-01",
            timestamp="2025-06-15T12:00:00Z",
            subsystem="eps",
            parameter="battery_voltage",
            value=7.4,
            unit="V",
        )
        assert t.satellite_id == "SAT-01"

    def test_rejects_empty_satellite_id(self):
        with pytest.raises(ValidationError):
            TelemetryIn(
                satellite_id="",
                timestamp="2025-06-15T12:00:00Z",
                subsystem="eps",
                parameter="battery_voltage",
                value=7.4,
            )

    def test_rejects_control_chars(self):
        with pytest.raises(ValidationError):
            TelemetryIn(
                satellite_id="SAT\x00-01",
                timestamp="2025-06-15T12:00:00Z",
                subsystem="eps",
                parameter="battery_voltage",
                value=7.4,
            )

    def test_quality_range(self):
        with pytest.raises(ValidationError):
            TelemetryIn(
                satellite_id="SAT-01",
                timestamp="2025-06-15T12:00:00Z",
                subsystem="eps",
                parameter="battery_voltage",
                value=7.4,
                quality=5.0,  # > 1.0
            )

    def test_batch_max_size(self):
        with pytest.raises(ValidationError):
            TelemetryBatchIn(points=[
                TelemetryIn(
                    satellite_id="SAT-01",
                    timestamp="2025-06-15T12:00:00Z",
                    subsystem="eps",
                    parameter="v",
                    value=1.0,
                )
            ] * 501)

    def test_batch_min_size(self):
        with pytest.raises(ValidationError):
            TelemetryBatchIn(points=[])


class TestSimulatorSchemas:
    def test_valid_simulate_request(self):
        r = SimulateRequest(satellite_id="SAT-01", duration_seconds=60, rate_hz=1.0)
        assert r.satellite_id == "SAT-01"

    def test_duration_bounds(self):
        with pytest.raises(ValidationError):
            SimulateRequest(duration_seconds=5)  # too short

    def test_rate_bounds(self):
        with pytest.raises(ValidationError):
            SimulateRequest(rate_hz=100.0)  # too fast

    def test_inject_request(self):
        r = InjectRequest(
            fault_type="drift",
            subsystem="eps",
            parameter="battery_voltage",
            intensity=0.5,
        )
        assert r.fault_type == "drift"


class TestAnomalySchema:
    def test_anomaly_out(self):
        a = AnomalyOut(
            id="abc123",
            satellite_id="SAT-01",
            timestamp=datetime.now(timezone.utc),
            subsystem="eps",
            parameter="battery_voltage",
            value=5.8,
            severity="warning",
            confidence=0.72,
            detectors_triggered=["statistical", "isolation_forest"],
            explanation="test explanation",
            root_cause_group="INC-abc",
            contributing_params={"solar_array_current": -0.3},
        )
        assert a.severity == "warning"
        assert len(a.detectors_triggered) == 2
