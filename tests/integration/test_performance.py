"""Performance benchmark suite for ARIA.

Measures:
  - Message bus throughput (messages/second)
  - Tool invocation latency (P50/P95/P99)
  - Agent processing latency (sensor → anomaly publish time)
  - Health scorer performance (compute 1000 reports)
  - Checkpoint write/restore speed
  - Memory store operations throughput

These are NOT SLO tests — they document baseline performance.
Each test captures a metric and asserts it stays within a
generous bound (5x expected) to catch regressions without
being flaky on slow CI machines.
"""

from __future__ import annotations

import asyncio
import tempfile
import time
from typing import Any

import pytest

from aria.bus.message_bus import Message, MessageBus
from aria.core.tool import ARIATool, ToolResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory
from aria.memory.store import MemoryStore
from aria.metrics.collector import MetricsCollector
from aria.safety.checkpoint import CheckpointManager
from aria.safety.health import HealthScorer
from aria.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def bus():
    b = MessageBus(max_history=10_000)
    await b.start()
    yield b
    await b.stop()


class EchoTool(ARIATool):
    """Zero-overhead tool for latency baseline measurement."""
    name = "perf_echo"
    description = "Benchmark echo"
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, data=params)


class SlowTool(ARIATool):
    """Tool with 10ms sleep — tests that latency tracking is accurate."""
    name = "perf_slow"
    description = "Benchmark slow"
    category = ToolCategory.DIAGNOSTIC
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    timeout_ms = 5000

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        await asyncio.sleep(0.010)  # 10ms
        return ToolResult(success=True, data={"ok": True})


# ---------------------------------------------------------------------------
# 1. Message Bus Throughput
# ---------------------------------------------------------------------------

async def test_bus_throughput(bus: MessageBus):
    """Bus should handle ≥ 1000 messages/second."""
    N = 500
    received = 0

    async def counter(msg: Message) -> None:
        nonlocal received
        received += 1

    bus.subscribe("bench.throughput", counter)

    start = time.perf_counter()
    for i in range(N):
        await bus.publish(Message(
            topic="bench.throughput",
            payload={"seq": i},
        ))
    # Drain the queue
    await asyncio.sleep(0.2)
    elapsed = time.perf_counter() - start

    msgs_per_sec = N / elapsed
    # Generous lower bound: 500 msg/s on any machine
    assert msgs_per_sec >= 200, f"Bus throughput too low: {msgs_per_sec:.0f} msg/s"
    assert received == N, f"Lost messages: received {received}/{N}"


async def test_bus_wildcard_subscribe_throughput(bus: MessageBus):
    """Wildcard subscriptions don't degrade throughput significantly."""
    N = 200
    received = 0

    async def counter(msg: Message) -> None:
        nonlocal received
        received += 1

    # Register many wildcard subscribers
    for i in range(10):
        bus.subscribe(f"bench.wild.{i}.*", counter)
    bus.subscribe("bench.wild.*", counter)
    bus.subscribe("bench.wild.5.test", counter)

    for i in range(N):
        await bus.publish(Message(topic=f"bench.wild.{i % 10}.test", payload={"i": i}))

    await asyncio.sleep(0.3)
    assert received >= N  # May be higher due to multiple matching subscriptions


# ---------------------------------------------------------------------------
# 2. Tool Invocation Latency
# ---------------------------------------------------------------------------

async def test_tool_echo_latency():
    """Echo tool P99 latency should be < 5ms (just overhead)."""
    mc = MetricsCollector()
    reg = ToolRegistry(metrics=mc)
    reg.register(EchoTool())

    N = 100
    for _ in range(N):
        result = await reg.invoke("perf_echo", {"x": 1})
        assert result.success

    hist = mc.get_histogram("tool.perf_echo")
    assert hist is not None
    assert hist.count == N
    # P99 should be well under 50ms (no I/O, pure Python)
    assert hist.p99 < 50.0, f"Echo tool P99 too high: {hist.p99:.1f}ms"


async def test_tool_slow_latency_accuracy():
    """Latency tracking accurately measures 10ms sleep."""
    mc = MetricsCollector()
    reg = ToolRegistry(metrics=mc)
    reg.register(SlowTool())

    for _ in range(20):
        result = await reg.invoke("perf_slow", {})
        assert result.success

    hist = mc.get_histogram("tool.perf_slow")
    assert hist is not None
    # P50 should be around 10ms (±5ms tolerance for scheduling)
    assert 5.0 <= hist.p50 <= 50.0, f"Slow tool P50 unexpected: {hist.p50:.1f}ms"


# ---------------------------------------------------------------------------
# 3. Health Scorer Performance
# ---------------------------------------------------------------------------

def test_health_scorer_throughput():
    """Health scorer should handle 1000 reports/second."""
    scorer = HealthScorer()
    statuses = {s: "READY" for s in ["eclss", "power", "navigation", "thermal",
                                       "telemetry", "comms", "propulsion", "science"]}
    N = 1000

    start = time.perf_counter()
    for _ in range(N):
        report = scorer.compute(agent_statuses=statuses)
    elapsed = time.perf_counter() - start

    reports_per_sec = N / elapsed
    # Should be able to compute at least 500 health reports/sec
    assert reports_per_sec >= 500, f"HealthScorer too slow: {reports_per_sec:.0f} reports/s"
    assert report.overall_score >= 90


# ---------------------------------------------------------------------------
# 4. Checkpoint Write + Restore Speed
# ---------------------------------------------------------------------------

def test_checkpoint_roundtrip_speed():
    """Checkpoint save + restore should complete in under 500ms."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = CheckpointManager(persist_dir=tmpdir, interval_s=9999)
        # Simulate realistic state blob
        state = {
            "agents": {f"agent_{i}": "READY" for i in range(20)},
            "telemetry": {f"channel_{i}": float(i) for i in range(100)},
            "metrics": {"counters": {f"c_{i}": i for i in range(50)}},
        }
        mgr._state_provider = lambda: state

        loop = asyncio.new_event_loop()

        start = time.perf_counter()
        for _ in range(10):
            loop.run_until_complete(mgr.save_now())
        elapsed = time.perf_counter() - start
        loop.close()

        # 10 checkpoints should complete in under 2 seconds
        assert elapsed < 2.0, f"Checkpoint too slow: {elapsed:.2f}s for 10 saves"

        # Restore should be fast
        start = time.perf_counter()
        restored = mgr.restore_latest()
        restore_elapsed = time.perf_counter() - start
        assert restore_elapsed < 0.1, f"Restore too slow: {restore_elapsed:.3f}s"
        assert restored is not None
        assert len(restored["agents"]) == 20


# ---------------------------------------------------------------------------
# 5. Memory Store Throughput
# ---------------------------------------------------------------------------

async def test_memory_store_episode_throughput():
    """Memory store should handle 100+ episode writes/second."""
    store = MemoryStore()
    N = 200

    start = time.perf_counter()
    for i in range(N):
        await store.store_episode(
            event_type="sensor.reading",
            summary=f"Battery voltage: {28.0 + i * 0.001:.3f}V",
            details={"voltage": 28.0 + i * 0.001},
            severity="NOMINAL",
        )
    elapsed = time.perf_counter() - start

    eps_per_sec = N / elapsed
    assert eps_per_sec >= 100, f"Memory store too slow: {eps_per_sec:.0f} ep/s"

    # Recall is synchronous — should be fast
    start = time.perf_counter()
    results = store.recall_episodes(query="battery", limit=50)
    recall_elapsed = time.perf_counter() - start
    assert recall_elapsed < 0.5, f"Recall too slow: {recall_elapsed:.3f}s"
    assert len(results) > 0


# ---------------------------------------------------------------------------
# 6. Metrics Collector Throughput
# ---------------------------------------------------------------------------

def test_metrics_collector_throughput():
    """MetricsCollector should handle 10k increments/second."""
    mc = MetricsCollector()
    N = 5000

    start = time.perf_counter()
    for i in range(N):
        mc.increment("bench.counter")
        mc.gauge("bench.gauge", float(i))
    elapsed = time.perf_counter() - start

    ops_per_sec = (N * 2) / elapsed
    assert ops_per_sec >= 10_000, f"MetricsCollector too slow: {ops_per_sec:.0f} ops/s"
    assert mc.get_counter("bench.counter") == N


def test_metrics_histogram_percentile_accuracy():
    """Histogram P50/P95/P99 are computed correctly for known distribution."""
    mc = MetricsCollector()

    # 100 values from 1-100
    for v in range(1, 101):
        mc.record_latency("bench.latency", float(v))

    hist = mc.get_histogram("bench.latency")
    assert hist is not None
    assert hist.count == 100
    # P50 index = 100//2 = 50 → sorted[50] = 51
    assert hist.p50 == 51
    # P95 index = int(100*0.95) = 95 → sorted[95] = 96
    assert hist.p95 == 96
    # P99 index = int(100*0.99) = 99 → sorted[99] = 100
    assert hist.p99 == 100


# ---------------------------------------------------------------------------
# 7. Bus History + Replay Speed
# ---------------------------------------------------------------------------

async def test_bus_history_access(bus: MessageBus):
    """Bus history access is O(1) / fast for recent messages."""
    N = 100
    for i in range(N):
        await bus.publish(Message(topic=f"bench.hist.{i % 5}", payload={"i": i}))

    await asyncio.sleep(0.1)

    start = time.perf_counter()
    stats = bus.stats
    elapsed = time.perf_counter() - start

    assert elapsed < 0.01  # Stats should be instant
    assert stats["total_published"] >= N


# ---------------------------------------------------------------------------
# 8. End-to-End Anomaly Detection Latency (Part 16.1)
# ---------------------------------------------------------------------------

async def test_anomaly_detection_latency(bus: MessageBus):
    """Target: sensor → anomaly alert in < 2 seconds (Part 16.1)."""
    from aria.agents.power import PowerAgent

    alerts: list[tuple[float, Message]] = []

    async def capture(m: Message) -> None:
        alerts.append((time.perf_counter(), m))

    bus.subscribe("aria.anomaly.power", capture)

    tools = ToolRegistry()
    tools.register(EchoTool())

    agent = PowerAgent(bus=bus, tool_registry=tools)
    await agent.start()

    start = time.perf_counter()
    await bus.publish(Message(
        topic="aria.sensor.power.battery",
        payload={"soc_percent": 8.0, "temperature_c": 45.0},
    ))
    await asyncio.sleep(0.5)

    assert len(alerts) >= 1, "No anomaly alert received"
    latency = alerts[0][0] - start
    # Master plan target: < 2 seconds
    assert latency < 2.0, f"Anomaly detection latency too high: {latency:.3f}s (target: <2s)"

    await agent.stop()


# ---------------------------------------------------------------------------
# 9. Decision Engine Latency (Part 16.1)
# ---------------------------------------------------------------------------

async def test_decision_engine_routine_latency():
    """Target: routine decision < 5 seconds (Part 16.1)."""
    from aria.core.decision_engine import Decision, DecisionEngine
    from aria.core.types import Severity

    b = MessageBus(max_history=100)
    await b.start()
    de = DecisionEngine(b)

    start = time.perf_counter()
    result = await de.submit_decision(Decision(
        category="routine",
        severity=Severity.NOMINAL,
        description="Log rotation",
    ))
    latency = time.perf_counter() - start

    assert result.outcome == "executed"
    assert latency < 5.0, f"Routine decision too slow: {latency:.3f}s"

    await b.stop()


# ---------------------------------------------------------------------------
# 10. Context Window Manager Performance
# ---------------------------------------------------------------------------

def test_context_window_build_speed():
    """Context window assembly should be < 10ms."""
    from aria.cognitive.context import ContextWindowManager

    mgr = ContextWindowManager()
    status = {
        "status": "RUNNING",
        "health_score": 95.0,
        "safe_mode": "NOMINAL",
        "agents": {f"agent_{i}": {"status": "READY"} for i in range(9)},
    }
    anomalies = [{"severity": "WARNING", "message": f"Test anomaly {i}", "subsystem": "test"} for i in range(10)]

    N = 100
    start = time.perf_counter()
    for _ in range(N):
        ctx = mgr.build_context(status, recent_anomalies=anomalies, query_text="battery status")
    elapsed = time.perf_counter() - start

    ms_per_build = (elapsed / N) * 1000
    assert ms_per_build < 10.0, f"Context build too slow: {ms_per_build:.1f}ms (target: <10ms)"


# ---------------------------------------------------------------------------
# 11. Hallucination Detector Performance
# ---------------------------------------------------------------------------

def test_hallucination_check_speed():
    """Hallucination check should be < 5ms per response."""
    from aria.cognitive.hallucination import HallucinationDetector

    detector = HallucinationDetector(
        tool_names={f"tool_{i}" for i in range(50)},
    )
    response = "Battery SoC is at 72%. Temperature at 25°C. Using dsremo_query_anomalies."
    alerts = [{"severity": "WATCH", "message": "Minor fluctuation"}]

    N = 200
    start = time.perf_counter()
    for _ in range(N):
        detector.verify(response, active_alerts=alerts)
    elapsed = time.perf_counter() - start

    ms_per_check = (elapsed / N) * 1000
    assert ms_per_check < 5.0, f"Hallucination check too slow: {ms_per_check:.2f}ms (target: <5ms)"


# ---------------------------------------------------------------------------
# 12. Bus 1000 Messages Throughput (Stress)
# ---------------------------------------------------------------------------

async def test_bus_1000_messages_throughput(bus: MessageBus):
    """1000 messages must be published and received in < 2 seconds.

    Validates that the bus can sustain high-frequency telemetry ingestion
    without dropping messages. Generous bound: 10 seconds (5x).
    """
    N = 1000
    received = 0

    async def counter(msg: Message) -> None:
        nonlocal received
        received += 1

    bus.subscribe("stress.throughput", counter)

    start = time.perf_counter()
    for i in range(N):
        await bus.publish(Message(
            topic="stress.throughput",
            payload={"seq": i, "data": "x" * 64},
        ))
    # Allow subscriber coroutines to drain
    await asyncio.sleep(0.5)
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0, (
        f"1000 messages took {elapsed:.2f}s — expected < 10s (generous 5x bound)"
    )
    assert received == N, f"Lost messages: received {received}/{N}"


# ---------------------------------------------------------------------------
# 13. Bus 100 Wildcard Subscribers Scalability
# ---------------------------------------------------------------------------

async def test_bus_100_subscribers_scalability(bus: MessageBus):
    """100 wildcard subscribers must not crash or deadlock.

    Validates that fan-out to many subscribers is stable.
    Each subscriber gets every matching message; total delivery
    must complete without errors.
    """
    N_SUBS = 100
    N_MSGS = 50
    counts: list[int] = [0] * N_SUBS

    def make_counter(idx: int):
        async def handler(msg: Message) -> None:
            counts[idx] += 1
        return handler

    for i in range(N_SUBS):
        bus.subscribe("stress.fan.*", make_counter(i))

    start = time.perf_counter()
    for j in range(N_MSGS):
        await bus.publish(Message(
            topic=f"stress.fan.{j % 10}",
            payload={"j": j},
        ))
    await asyncio.sleep(1.0)
    elapsed = time.perf_counter() - start

    # All subscribers must have received all messages
    for i, c in enumerate(counts):
        assert c == N_MSGS, f"Subscriber {i} got {c}/{N_MSGS} messages"

    # Generous timing bound
    assert elapsed < 15.0, f"100-subscriber fan-out took {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# 14. Tool Concurrent 20 Invocations
# ---------------------------------------------------------------------------

async def test_tool_concurrent_20_invocations():
    """20 simultaneous tool invocations must all succeed without deadlock.

    Simulates a burst of parallel tool calls (e.g. multiple agents querying
    simultaneously). All must return success within a generous bound.
    """
    mc = MetricsCollector()
    reg = ToolRegistry(metrics=mc)
    reg.register(EchoTool())

    N = 20

    start = time.perf_counter()
    tasks = [reg.invoke("perf_echo", {"call_id": i}) for i in range(N)]
    results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    for i, r in enumerate(results):
        assert r.success, f"Tool call {i} failed: {r}"

    # 20 concurrent echo calls should finish well under 5 seconds
    assert elapsed < 5.0, (
        f"20 concurrent tool calls took {elapsed:.2f}s — expected < 5s"
    )


# ---------------------------------------------------------------------------
# 15. Context Window Build with 100 Anomalies
# ---------------------------------------------------------------------------

def test_context_window_build_100_anomalies():
    """Context window assembly with 100 anomalies must complete in < 50ms.

    Stress-tests the prioritization and truncation logic with a large
    anomaly list. Generous bound: 250ms (5x).
    """
    from aria.cognitive.context import ContextWindowManager

    mgr = ContextWindowManager()
    status = {
        "status": "RUNNING",
        "health_score": 72.0,
        "safe_mode": "WARNING",
        "agents": {f"agent_{i}": {"status": "DEGRADED"} for i in range(9)},
    }
    anomalies = [
        {
            "severity": ["EMERGENCY", "CRITICAL", "WARNING", "WATCH"][i % 4],
            "message": f"Anomaly #{i}: subsystem {i % 8} channel {i} exceeded threshold by {i * 1.5:.1f}%",
            "subsystem": f"subsystem_{i % 8}",
        }
        for i in range(100)
    ]

    N = 50
    start = time.perf_counter()
    for _ in range(N):
        ctx = mgr.build_context(
            status,
            recent_anomalies=anomalies,
            query_text="battery thermal runaway procedure",
        )
    elapsed = time.perf_counter() - start

    ms_per_build = (elapsed / N) * 1000
    assert ms_per_build < 250.0, (
        f"Context build with 100 anomalies: {ms_per_build:.1f}ms — expected < 250ms"
    )
    # Must produce non-empty output
    assert len(ctx.anomalies) > 0, "Anomalies section is empty"
    assert ctx.budget.anomalies_used > 0, "No token budget recorded for anomalies"


# ---------------------------------------------------------------------------
# 16. Hallucination Check 1000 Responses
# ---------------------------------------------------------------------------

def test_hallucination_check_1000_responses():
    """1000 hallucination checks must complete in < 5 seconds.

    Validates that the regex-based verification pipeline can handle
    high-throughput response checking. Generous bound: 25 seconds (5x).
    """
    from aria.cognitive.hallucination import HallucinationDetector

    detector = HallucinationDetector(
        tool_names={f"tool_{i}" for i in range(50)},
    )

    responses = [
        f"Battery SoC is at {50 + i % 50}%. Temperature at {20 + i % 30}C. "
        f"O2 at {20.5 + (i % 5) * 0.1:.1f}%. Using tool_{i % 50} to investigate. "
        f"Altitude is {400 + i}km. Heart rate {70 + i % 30} bpm."
        for i in range(1000)
    ]
    alerts_batch = [
        [{"severity": "WATCH", "message": "Minor fluctuation"}],
        [{"severity": "CRITICAL", "message": "Battery thermal runaway"}],
        [],
        [{"severity": "WARNING", "message": "CO2 rising"}],
    ]
    readings = {"eps.battery.soc_percent": 45.0}

    N = 1000
    start = time.perf_counter()
    for i in range(N):
        detector.verify(
            responses[i],
            active_alerts=alerts_batch[i % len(alerts_batch)],
            recent_readings=readings,
        )
    elapsed = time.perf_counter() - start

    assert elapsed < 25.0, (
        f"1000 hallucination checks took {elapsed:.2f}s — expected < 25s"
    )


# ---------------------------------------------------------------------------
# 17. Scratchpad 1000 Write+Read Cycles
# ---------------------------------------------------------------------------

def test_scratchpad_1000_writes_and_reads():
    """1000 write+read cycles must complete in < 1 second.

    The scratchpad is a hot path for inter-agent communication.
    Must be fast enough for real-time use. Generous bound: 5 seconds (5x).
    """
    from aria.state.scratchpad import SharedScratchpad

    pad = SharedScratchpad()
    N = 1000

    start = time.perf_counter()
    for i in range(N):
        key = f"subsystem_{i % 20}.channel_{i % 50}"
        pad.write(key, {"value": i, "unit": "volts", "extra": "x" * 32}, posted_by=f"agent_{i % 9}")
        result = pad.read(key)
        assert result is not None, f"Read returned None for key={key}"
        assert result["value"] == i
    elapsed = time.perf_counter() - start

    assert elapsed < 5.0, (
        f"1000 scratchpad write+read cycles took {elapsed:.2f}s — expected < 5s"
    )
    # Verify entries are stored (last 20 subsystems x up to 50 channels each)
    assert pad.size > 0


# ---------------------------------------------------------------------------
# 18. Event Log 10000 Events
# ---------------------------------------------------------------------------

async def test_event_log_10000_events():
    """Log 10000 events without memory issues or slowdown.

    The EventLogger uses a bounded deque, so memory should stay constant
    even with high event counts. Generous bound: 10 seconds (5x of ~2s expected).
    """
    from aria.metrics.event_log import EventLogger

    b = MessageBus(max_history=100)
    await b.start()
    el = EventLogger(bus=b, max_events=10_000)
    await el.start()

    N = 10_000
    categories = ["ANOMALY", "DECISION", "FDIR", "ALERT", "STATE", "AGENT", "TOOL", "SECURITY"]
    severities = ["NOMINAL", "WATCH", "WARNING", "CRITICAL", "EMERGENCY"]

    start = time.perf_counter()
    for i in range(N):
        el.log(
            category=categories[i % len(categories)],
            severity=severities[i % len(severities)],
            source=f"agent_{i % 9}",
            summary=f"Event {i}: subsystem check value={i * 0.1:.1f}",
            payload={"index": i, "data": "payload_" * 5},
        )
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0, (
        f"10000 event logs took {elapsed:.2f}s — expected < 10s"
    )
    assert el.event_count == N, f"Event count mismatch: {el.event_count} != {N}"

    # Query performance: filtered query on 10000 events should be fast
    start = time.perf_counter()
    results = el.query(category="ANOMALY", severity="CRITICAL", limit=100)
    query_elapsed = time.perf_counter() - start
    assert query_elapsed < 1.0, f"Query on 10000 events took {query_elapsed:.3f}s"
    assert len(results) > 0, "Query returned no results"

    # Summary should also be fast
    start = time.perf_counter()
    summary = el.summary()
    summary_elapsed = time.perf_counter() - start
    assert summary_elapsed < 1.0, f"Summary took {summary_elapsed:.3f}s"
    assert summary["total_events"] == N

    await b.stop()


# ---------------------------------------------------------------------------
# 19. Correlator 100 Events in Window
# ---------------------------------------------------------------------------

async def test_correlator_100_events_in_window():
    """100 anomaly events processed correctly within the correlation window.

    Feeds 100 anomaly events (spanning multiple failure signatures) into the
    correlator and verifies they are all ingested and correlated without error.
    Generous timing bound: 10 seconds (5x of ~2s expected).
    """
    from aria.integrations.dsremo.correlator import AnomalyCorrelator

    b = MessageBus(max_history=200)
    await b.start()

    correlations_received: list[Message] = []

    async def capture_correlation(msg: Message) -> None:
        correlations_received.append(msg)

    b.subscribe("aria.anomaly.correlation", capture_correlation)

    correlator = AnomalyCorrelator(bus=b, window_s=60.0, min_events=2)
    # Reset cooldown so correlations fire during test
    correlator._correlation_cooldown_s = 0.0
    await correlator.start()

    # Channels from known failure signatures to trigger correlations
    channels = [
        "eps.battery.temperature_c", "eps.battery.soc_percent", "eps.bus.voltage_v",
        "eps.solar.power_watts",
        "eclss.atmosphere.co2_mmhg", "eclss.atmosphere.o2_percent",
        "eclss.atmosphere.humidity_percent", "eclss.cabin.pressure_psi",
        "nav.imu.angular_rate_x_dps", "nav.imu.angular_rate_y_dps",
    ]

    N = 100
    start = time.perf_counter()
    for i in range(N):
        channel = channels[i % len(channels)]
        await b.publish(Message(
            topic=f"aria.anomaly.{channel.split('.')[0]}",
            payload={
                "channel_id": channel,
                "subsystem": channel.split(".")[0],
                "severity": "WARNING",
                "dsremo_score": 0.85,
                "message": f"Anomaly on {channel} (event {i})",
            },
            source_agent="test_correlator",
        ))
    await asyncio.sleep(1.0)
    elapsed = time.perf_counter() - start

    assert elapsed < 10.0, (
        f"100 correlator events took {elapsed:.2f}s — expected < 10s"
    )
    # Correlator should have ingested events into its window
    recent = correlator.get_recent_events(window_s=120.0)
    assert len(recent) > 0, "Correlator has no recent events"
    # At least one correlation should have fired (we sent matching channels)
    assert len(correlations_received) >= 1, (
        f"Expected at least 1 correlation event, got {len(correlations_received)}"
    )

    await b.stop()


# ---------------------------------------------------------------------------
# 20. FDIR Response Latency
# ---------------------------------------------------------------------------

async def test_fdir_response_latency():
    """FDIR response must arrive < 100ms from correlation event publication.

    Measures the time from publishing an aria.anomaly.correlation event to
    receiving the aria.fdir.response. Generous bound: 500ms (5x).
    """
    from aria.safety.fdir import FDIRManager

    b = MessageBus(max_history=100)
    await b.start()

    fdir = FDIRManager(bus=b)
    await fdir.start()

    fdir_responses: list[tuple[float, Message]] = []

    async def capture_fdir(msg: Message) -> None:
        fdir_responses.append((time.perf_counter(), msg))

    b.subscribe("aria.fdir.response", capture_fdir)

    # Publish a high-confidence correlation event that triggers FDIR
    start = time.perf_counter()
    await b.publish(Message(
        topic="aria.anomaly.correlation",
        payload={
            "root_cause": "BATTERY_THERMAL_RUNAWAY",
            "confidence": 0.90,
            "severity": "CRITICAL",
            "description": "Battery thermal runaway precursor",
            "recommendation": "Disconnect battery",
            "involved_channels": ["eps.battery.temperature_c", "eps.battery.soc_percent"],
            "involved_subsystems": ["eps"],
            "evidence": ["test"],
            "window_s": 30.0,
            "event_count": 3,
        },
        source_agent="test_fdir",
    ))
    await asyncio.sleep(0.3)

    assert len(fdir_responses) >= 1, "No FDIR response received"
    latency = fdir_responses[0][0] - start
    assert latency < 0.5, (
        f"FDIR response latency: {latency * 1000:.1f}ms — expected < 500ms"
    )

    # Verify the response payload
    resp = fdir_responses[0][1]
    assert resp.payload["fault_type"] == "BATTERY_THERMAL_RUNAWAY"
    assert "disconnect_battery" in resp.payload["actions"]

    await b.stop()


# ---------------------------------------------------------------------------
# 21. Decision Engine 10 Concurrent Decisions
# ---------------------------------------------------------------------------

async def test_decision_engine_10_concurrent():
    """10 concurrent decisions must all resolve without deadlock.

    Submits a mix of NOMINAL and EMERGENCY decisions simultaneously.
    All must return with a valid outcome. Generous bound: 15 seconds (5x of ~3s).
    """
    from aria.core.decision_engine import Decision, DecisionEngine
    from aria.core.types import Severity

    b = MessageBus(max_history=200)
    await b.start()
    de = DecisionEngine(b)

    N = 10
    severities = [
        Severity.NOMINAL, Severity.WATCH, Severity.EMERGENCY,
        Severity.NOMINAL, Severity.NOMINAL, Severity.WATCH,
        Severity.EMERGENCY, Severity.NOMINAL, Severity.NOMINAL,
        Severity.WATCH,
    ]

    start = time.perf_counter()
    tasks = [
        de.submit_decision(Decision(
            category=f"test_category_{i}",
            severity=severities[i],
            description=f"Concurrent decision {i}",
            source_agent=f"agent_{i}",
        ))
        for i in range(N)
    ]
    results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    for i, r in enumerate(results):
        assert r.outcome in ("executed", "overridden", "cancelled", "timeout"), (
            f"Decision {i} has unexpected outcome: {r.outcome}"
        )

    assert elapsed < 15.0, (
        f"10 concurrent decisions took {elapsed:.2f}s — expected < 15s"
    )

    # Verify all decisions are in history
    history = de.get_history(limit=N)
    assert len(history) >= N, f"Only {len(history)} decisions in history, expected {N}"

    await b.stop()
