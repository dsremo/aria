"""Tests for FDIR (Fault Detection, Isolation, and Recovery)."""

from __future__ import annotations

import asyncio
import time

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.safety.fdir import FDIRLevel, FDIRManager, FAULT_RESPONSES


@pytest.fixture
async def bus():
    b = MessageBus(max_history=100)
    await b.start()
    yield b
    await b.stop()


@pytest.fixture
async def fdir(bus: MessageBus) -> FDIRManager:
    mgr = FDIRManager(bus)
    await mgr.start()
    return mgr


async def test_fdir_responds_to_high_confidence_correlation(fdir: FDIRManager, bus: MessageBus):
    """FDIR triggers response on high-confidence correlation."""
    responses: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))

    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "BATTERY_THERMAL_RUNAWAY",
            "confidence": 0.85,
            "severity": "CRITICAL",
            "description": "Battery thermal runaway detected",
            "involved_channels": ["eps.battery.temperature_c", "eps.battery.soc_percent"],
        },
    ))
    await asyncio.sleep(0.1)

    assert len(responses) >= 1
    assert responses[0].payload["fault_type"] == "BATTERY_THERMAL_RUNAWAY"
    assert "disconnect_battery" in responses[0].payload["actions"]
    assert responses[0].payload["fdir_level"] == FDIRLevel.MISSION


async def test_fdir_ignores_low_confidence(fdir: FDIRManager, bus: MessageBus):
    """FDIR does not respond to low-confidence correlations."""
    responses: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))

    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "ECLIPSE_INDUCED_POWER_DROP",
            "confidence": 0.50,  # Below 0.70 threshold
            "severity": "WATCH",
            "involved_channels": ["eps.solar.power_watts"],
        },
    ))
    await asyncio.sleep(0.1)

    assert len(responses) == 0


async def test_fdir_deduplicates_active_faults(fdir: FDIRManager, bus: MessageBus):
    """Same fault type is not processed twice while active."""
    responses: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))

    for _ in range(3):
        await bus.publish(Message(
            topic="aria.anomaly.correlation",
            payload={
                "root_cause": "CO2_SCRUBBER_FAILURE",
                "confidence": 0.90,
                "severity": "CRITICAL",
                "involved_channels": ["eclss.atmosphere.co2_mmhg"],
            },
        ))
    await asyncio.sleep(0.2)

    assert len(responses) == 1  # Only first one triggers response
    assert len(fdir.active_faults) == 1


async def test_fdir_resolve_fault(fdir: FDIRManager, bus: MessageBus):
    """Resolving a fault moves it to history."""
    resolved: list[Message] = []
    bus.subscribe("aria.fdir.resolved", lambda m: resolved.append(m))

    # Trigger a fault
    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "PROPULSION_LEAK",
            "confidence": 0.82,
            "severity": "CRITICAL",
            "involved_channels": ["propulsion.tank.propellant_kg"],
        },
    ))
    await asyncio.sleep(0.1)
    assert len(fdir.active_faults) == 1

    # Resolve it
    success = await fdir.resolve_fault("PROPULSION_LEAK", recovery_method="valves_closed")
    await asyncio.sleep(0.1)

    assert success
    assert len(fdir.active_faults) == 0
    assert len(fdir.fault_history) == 1
    assert fdir.fault_history[0].recovery_method == "valves_closed"
    assert len(resolved) >= 1


async def test_fdir_all_master_plan_faults_have_responses():
    """All fault types in FAULT_RESPONSES have required fields."""
    required_keys = {"level", "actions", "timeout_s", "auto_recovery"}
    for fault_type, response in FAULT_RESPONSES.items():
        assert required_keys.issubset(response.keys()), f"{fault_type} missing {required_keys - response.keys()}"
        assert isinstance(response["actions"], list)
        assert len(response["actions"]) > 0
        assert response["timeout_s"] > 0


async def test_fdir_emergency_level_for_critical_faults(fdir: FDIRManager, bus: MessageBus):
    """CRITICAL severity faults get MISSION-level FDIR response."""
    responses: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))

    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "CABIN_DEPRESSURIZATION",
            "confidence": 0.92,
            "severity": "EMERGENCY",
            "involved_channels": ["eclss.cabin.pressure_psi"],
        },
    ))
    await asyncio.sleep(0.1)

    assert len(responses) >= 1
    assert responses[0].payload["fdir_level"] == FDIRLevel.MISSION
    assert "isolate_compartment" in responses[0].payload["actions"]


async def test_fdir_auto_recovery_flag(fdir: FDIRManager, bus: MessageBus):
    """Auto-recovery flag is correctly set per fault type."""
    responses: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))

    # ECLIPSE_INDUCED_POWER_DROP has auto_recovery=True
    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "ECLIPSE_INDUCED_POWER_DROP",
            "confidence": 0.80,
            "severity": "WATCH",
            "involved_channels": ["eps.solar.power_watts"],
        },
    ))
    await asyncio.sleep(0.1)

    assert len(responses) >= 1
    assert responses[0].payload["auto_recovery"] is True


async def test_fdir_unknown_fault_type_handled(fdir: FDIRManager, bus: MessageBus):
    """Unknown fault type still triggers a response with default actions."""
    responses: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))

    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "UNKNOWN_FAULT_TYPE",
            "confidence": 0.85,
            "severity": "WARNING",
            "involved_channels": ["some.channel"],
        },
    ))
    await asyncio.sleep(0.1)

    assert len(responses) >= 1
    # Should have default actions even for unknown faults
    assert "monitor" in responses[0].payload["actions"] or len(responses[0].payload["actions"]) > 0


async def test_fdir_auto_recovery_cycle(fdir: FDIRManager, bus: MessageBus):
    """Full FDIR cycle: fault detected → response → resolved → cleared."""
    responses: list[Message] = []
    resolved: list[Message] = []
    bus.subscribe("aria.fdir.response", lambda m: responses.append(m))
    bus.subscribe("aria.fdir.resolved", lambda m: resolved.append(m))

    # Trigger fault
    await bus.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "ATTITUDE_CONTROL_FAILURE",
            "confidence": 0.88,
            "severity": "CRITICAL",
            "involved_channels": ["nav.imu.angular_rate_x_dps"],
        },
    ))
    await asyncio.sleep(0.1)
    assert len(responses) >= 1
    assert len(fdir.active_faults) == 1

    # Resolve fault
    success = await fdir.resolve_fault("ATTITUDE_CONTROL_FAILURE", "backup_adcs_activated")
    await asyncio.sleep(0.1)
    assert success
    assert len(fdir.active_faults) == 0
    assert len(resolved) >= 1
    assert resolved[0].payload["recovery_method"] == "backup_adcs_activated"


async def test_fdir_multiple_simultaneous_faults(fdir: FDIRManager, bus: MessageBus):
    """FDIR handles multiple simultaneous faults."""
    for fault in ["CO2_SCRUBBER_FAILURE", "ATTITUDE_CONTROL_FAILURE"]:
        await bus.publish(Message(
            topic="aria.anomaly.correlation",
            payload={"root_cause": fault, "confidence": 0.85, "severity": "CRITICAL", "involved_channels": []},
        ))
    await asyncio.sleep(0.1)

    assert len(fdir.active_faults) == 2
    assert {f.fault_type for f in fdir.active_faults} == {"CO2_SCRUBBER_FAILURE", "ATTITUDE_CONTROL_FAILURE"}
