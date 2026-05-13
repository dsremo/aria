"""Smoke tests for the OpenTelemetry wiring.

We don't assert on exporter output (the Console exporter writes to a
file handle we don't want to own in tests); we verify that the span
context manager is safe when disabled, and that it becomes a real
OTel span when enabled.
"""
from __future__ import annotations

import pytest

from aria.simulator import telemetry_otel as otel


@pytest.fixture(autouse=True)
def _reset_otel_module():
    """Each test starts with an unconfigured OTel module."""
    otel._CONFIGURED = False
    otel._TRACER = None
    yield
    otel._CONFIGURED = False
    otel._TRACER = None


def test_span_noop_when_disabled():
    # is_enabled defaults to False — span() must be safe to use.
    assert not otel.is_enabled()
    with otel.span("test.noop", foo="bar") as s:
        s.set_attribute("baz", 1)
        s.add_event("something")


def test_configure_enables_tracer(tmp_path):
    otel.configure_otel(enabled=True, export_file=str(tmp_path / "spans.jsonl"))
    assert otel.is_enabled()
    tracer = otel.get_tracer()
    assert tracer is not None
    with otel.span("test.real", x=1) as s:
        s.set_attribute("y", 2)


def test_bus_bridge_attaches_without_error(tmp_path):
    otel.configure_otel(enabled=True, export_file=str(tmp_path / "spans.jsonl"))
    otel.attach_bus_to_spans()
    # Publishing an event under an active span should not raise.
    from aria.simulator.event_bus import get_event_bus
    with otel.span("test.under_span"):
        get_event_bus().publish("unit.test", severity="info", source="test",
                                sim_time_yr=0.0)


def test_configure_disabled_is_noop(tmp_path):
    otel.configure_otel(enabled=False, export_file=str(tmp_path / "spans.jsonl"))
    assert not otel.is_enabled()
    # attach_bus_to_spans must silently no-op
    otel.attach_bus_to_spans()


def test_exception_records_on_span(tmp_path):
    otel.configure_otel(enabled=True, export_file=str(tmp_path / "spans.jsonl"))
    with pytest.raises(RuntimeError):
        with otel.span("test.raises"):
            raise RuntimeError("boom")
