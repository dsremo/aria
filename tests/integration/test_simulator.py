"""Integration tests for the sensor simulator."""

import asyncio

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.simulator import SensorSimulator, SimulatedSensor


@pytest.fixture
async def bus():
    b = MessageBus(max_history=1000)
    await b.start()
    yield b
    await b.stop()


async def test_simulator_produces_telemetry(bus: MessageBus):
    """Simulator generates sensor readings on the bus."""
    received: list[Message] = []

    async def capture(msg: Message) -> None:
        received.append(msg)

    bus.subscribe("aria.sensor.*", capture)

    sim = SensorSimulator(bus)
    sim.add_sensor(SimulatedSensor(
        topic="aria.sensor.test.temp",
        base_value=25.0,
        noise_std=0.1,
        sample_interval_s=0.1,
        payload_key="temperature_c",
    ))
    await sim.start()
    await asyncio.sleep(0.5)
    await sim.stop()

    assert len(received) >= 3  # Should have ~5 samples in 0.5s at 0.1s interval
    for msg in received:
        temp = msg.payload["temperature_c"]
        assert 20.0 < temp < 30.0  # Within reasonable range


async def test_default_sensors_produce_data(bus: MessageBus):
    """Default sensor set produces data on expected topics."""
    topics_seen: set[str] = set()

    async def capture(msg: Message) -> None:
        topics_seen.add(msg.topic)

    bus.subscribe("aria.sensor.*", capture)

    sim = SensorSimulator(bus)
    sim.add_default_sensors()
    await sim.start()
    await asyncio.sleep(1.5)  # Let sensors produce at least 1 sample each
    await sim.stop()

    # Should see power, thermal, nav, eclss, telemetry topics
    assert any("power" in t for t in topics_seen)
    assert any("thermal" in t for t in topics_seen)
    assert any("nav" in t for t in topics_seen)
    assert any("eclss" in t for t in topics_seen)


async def test_fault_injection(bus: MessageBus):
    """Fault injection modifies sensor output."""
    received: list[Message] = []

    async def capture(msg: Message) -> None:
        received.append(msg)

    bus.subscribe("aria.sensor.test.*", capture)

    sim = SensorSimulator(bus)
    sim.add_sensor(SimulatedSensor(
        topic="aria.sensor.test.voltage",
        base_value=28.0,
        noise_std=0.01,
        sample_interval_s=0.1,
        payload_key="voltage",
    ))

    # Inject offset fault
    sim.inject_fault("aria.sensor.test.voltage", "offset", offset=10.0)

    await sim.start()
    await asyncio.sleep(0.5)
    await sim.stop()

    # All values should be around 38.0 (28.0 + 10.0 offset)
    voltages = [m.payload["voltage"] for m in received]
    avg = sum(voltages) / len(voltages)
    assert 37.0 < avg < 39.0


async def test_clear_fault(bus: MessageBus):
    """Clearing a fault restores normal sensor behavior."""
    sim = SensorSimulator(bus)
    sim.add_sensor(SimulatedSensor(
        topic="aria.sensor.test.v",
        base_value=28.0, noise_std=0.01, sample_interval_s=0.1, payload_key="v",
    ))
    sim.inject_fault("aria.sensor.test.v", "stuck", stuck_value=0.0)
    sim.clear_fault("aria.sensor.test.v")

    received: list[Message] = []
    bus.subscribe("aria.sensor.test.*", lambda m: received.append(m))

    await sim.start()
    await asyncio.sleep(0.3)
    await sim.stop()

    # Values should be around 28.0, not 0.0
    voltages = [m.payload["v"] for m in received]
    assert all(v > 20.0 for v in voltages)
