"""Tests for the telemetry ingestion adapter — the security boundary."""

import math
from datetime import datetime, timezone

import pytest

from aria.dsremo.ingest.adapter import AdapterError, adapt_batch, adapt_single


class TestAdaptSingle:
    def test_valid_point(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": 7.4,
            "unit": "V",
        }
        point = adapt_single(raw)
        assert point.satellite_id == "SAT-01"
        assert point.subsystem == "eps"
        assert point.parameter == "battery_voltage"
        assert point.value == 7.4
        assert point.unit == "V"
        assert point.quality == 1.0

    def test_unix_timestamp(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": 1718452800,  # unix epoch
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": 7.4,
        }
        point = adapt_single(raw)
        assert isinstance(point.timestamp, datetime)

    def test_rejects_missing_fields(self):
        with pytest.raises(AdapterError, match="missing required fields"):
            adapt_single({"satellite_id": "SAT-01"})

    def test_rejects_invalid_subsystem(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "weapons",  # not a valid subsystem
            "parameter": "laser_power",
            "value": 9001,
        }
        with pytest.raises(AdapterError, match="invalid subsystem"):
            adapt_single(raw)

    def test_rejects_nan_value(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": float("nan"),
        }
        with pytest.raises(AdapterError, match="must be finite"):
            adapt_single(raw)

    def test_rejects_inf_value(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": float("inf"),
        }
        with pytest.raises(AdapterError, match="must be finite"):
            adapt_single(raw)

    def test_sanitizes_satellite_id(self):
        raw = {
            "satellite_id": "SAT<script>alert(1)</script>",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": 7.4,
        }
        point = adapt_single(raw)
        # sanitize_identifier strips <, >, (, ) and other non-alphanumeric chars
        assert "<" not in point.satellite_id
        assert ">" not in point.satellite_id
        assert "(" not in point.satellite_id

    def test_clamps_quality(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": 7.4,
            "quality": 5.0,  # exceeds range
        }
        point = adapt_single(raw)
        assert point.quality == 1.0

    def test_rejects_non_numeric_value(self):
        raw = {
            "satellite_id": "SAT-01",
            "timestamp": "2025-06-15T12:00:00Z",
            "subsystem": "eps",
            "parameter": "battery_voltage",
            "value": "not_a_number",
        }
        with pytest.raises(AdapterError, match="value must be numeric"):
            adapt_single(raw)


class TestAdaptBatch:
    def test_valid_batch(self):
        raw = [
            {"satellite_id": "SAT-01", "timestamp": "2025-06-15T12:00:00Z",
             "subsystem": "eps", "parameter": "battery_voltage", "value": 7.4},
            {"satellite_id": "SAT-01", "timestamp": "2025-06-15T12:00:01Z",
             "subsystem": "eps", "parameter": "battery_current", "value": 1.2},
        ]
        valid, errors = adapt_batch(raw)
        assert len(valid) == 2
        assert len(errors) == 0

    def test_partial_success(self):
        raw = [
            {"satellite_id": "SAT-01", "timestamp": "2025-06-15T12:00:00Z",
             "subsystem": "eps", "parameter": "battery_voltage", "value": 7.4},
            {"satellite_id": "SAT-01", "timestamp": "bad", "subsystem": "eps",
             "parameter": "x", "value": 1.0},  # bad timestamp
        ]
        valid, errors = adapt_batch(raw)
        assert len(valid) == 1
        assert len(errors) == 1

    def test_rejects_oversized_batch(self):
        raw = [{"satellite_id": "SAT", "timestamp": "2025-06-15T12:00:00Z",
                "subsystem": "eps", "parameter": "v", "value": 1.0}] * 501
        with pytest.raises(AdapterError, match="batch too large"):
            adapt_batch(raw)
