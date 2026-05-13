"""Tests for the structured-logging + bus-bridge module."""

from __future__ import annotations

import io
import json
import logging

import pytest

from aria.simulator import telemetry
from aria.simulator.event_bus import get_event_bus


@pytest.fixture(autouse=True)
def _reset_telemetry_module():
    """Each test gets a clean `aria` logger + un-configured telemetry."""
    telemetry._CONFIGURED = False
    # Tear down any listener installed by a prior test.
    if telemetry._bus_listener is not None:
        get_event_bus().unsubscribe("*", telemetry._bus_listener)
        telemetry._bus_listener = None
    root = logging.getLogger("aria")
    for h in list(root.handlers):
        root.removeHandler(h)
    yield


def _capture_logger() -> tuple[logging.Logger, io.StringIO]:
    """Install a StringIO stream handler + JSON formatter and return both."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(telemetry._JsonFormatter())
    root = logging.getLogger("aria")
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    return root, buf


def test_json_formatter_emits_valid_json():
    logger, buf = _capture_logger()
    logger.info("hello", extra={"sim_yr": 1.5, "topic": "reactor.ignition"})
    out = buf.getvalue().strip()
    obj = json.loads(out)
    assert obj["msg"] == "hello"
    assert obj["lvl"] == "info"
    assert obj["sim_yr"] == 1.5
    assert obj["topic"] == "reactor.ignition"


def test_configure_is_idempotent(tmp_path):
    telemetry.configure_logging(level="INFO", log_dir=str(tmp_path),
                                bridge_event_bus=False)
    n1 = len(logging.getLogger("aria").handlers)
    telemetry.configure_logging(level="DEBUG", log_dir=str(tmp_path),
                                bridge_event_bus=False)
    n2 = len(logging.getLogger("aria").handlers)
    assert n1 == n2, "configure_logging should be a no-op on the 2nd call"


def test_bus_bridge_mirrors_published_events(tmp_path):
    log_file = tmp_path / "aria_events.log"
    telemetry.configure_logging(level="DEBUG", log_dir=str(tmp_path),
                                log_filename=log_file.name,
                                bridge_event_bus=True)
    bus = get_event_bus()
    bus.publish("reactor.scram", severity="critical", source="reactor",
                payload={"reason": "overtemp"}, sim_time_yr=2.5)
    # Drain handlers
    for h in logging.getLogger("aria").handlers:
        h.flush()
    data = log_file.read_text().strip().splitlines()
    assert any(
        json.loads(line).get("topic") == "reactor.scram"
        for line in data if line
    ), f"reactor.scram missing from log; got {data[-3:]}"


def test_severity_maps_to_log_level(tmp_path):
    log_file = tmp_path / "events.log"
    telemetry.configure_logging(level="WARNING", log_dir=str(tmp_path),
                                log_filename=log_file.name,
                                bridge_event_bus=True)
    bus = get_event_bus()
    bus.publish("chatty.debug", severity="debug", source="test", sim_time_yr=0)
    bus.publish("real.warning", severity="warning", source="test",
                payload={"x": 1}, sim_time_yr=0)
    for h in logging.getLogger("aria").handlers:
        h.flush()
    lines = [json.loads(l) for l in log_file.read_text().splitlines() if l]
    topics = {l.get("topic") for l in lines}
    assert "real.warning" in topics
    assert "chatty.debug" not in topics, "debug events must be filtered at WARNING"
