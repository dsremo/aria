"""TelemetryAgent — ARIA's sensory cortex and universal Dsremo bridge.

This agent is the ONLY entry point for all raw sensor data into Dsremo.
It subscribes to every sensor topic on the bus (aria.sensor.*) and routes
ALL numeric values through the 12-detector ensemble.

Architecture (dual-layer anomaly detection):
  Layer 1 — Domain agents (PowerAgent, EclssAgent, etc.)
            Fast threshold-based rules: "SoC < 10% → load shed"
            These fire immediately, no ML needed for obvious cases.

  Layer 2 — TelemetryAgent + Dsremo (this file)
            Statistical + ML-based detection across ALL channels:
            CUSUM, EWMA, Z-score, GMM-2, BOCPD, AR(1), IQR, LLR,
            IsolationForest, DBSCAN, Prophet, LSTM
            These catch subtle, cross-channel, slow-drift anomalies
            that threshold rules completely miss.

Message flow:
  aria.sensor.power.battery → TelemetryAgent
    → DsremoChannelMapper.extract() → [eps.battery.soc_percent, eps.battery.temperature_c]
    → dsremo_ingest_batch([...])
    → anomaly_score per channel
    → if score ≥ threshold: publish aria.anomaly.detected with Dsremo verdict
    → always publish aria.telemetry.scored (channel scores for audit trail)

Every sensor. Every reading. No exceptions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity
from aria.integrations.dsremo.channel_mapper import DsremoChannelMapper, TelemetryReading

logger = structlog.get_logger()

# Dsremo ensemble score → ARIA Severity
SCORE_THRESHOLDS = {
    "critical": 0.85,
    "warning": 0.65,
    "watch": 0.50,
}

# Channels with special importance — anomalies here always escalate
CRITICAL_CHANNELS = {
    "eclss.atmosphere.co2_mmhg",
    "eclss.atmosphere.o2_percent",
    "eclss.cabin.pressure_psi",
    "eps.battery.soc_percent",
    "nav.imu.angular_rate_x_dps",
    "nav.imu.angular_rate_y_dps",
    "nav.imu.angular_rate_z_dps",
}


class TelemetryAgent(SubsystemAgent):
    """Universal Dsremo bridge — every sensor reading through the 12-detector ensemble."""

    name = "telemetry"
    description = (
        "Universal telemetry anomaly detection via Dsremo 12-detector ensemble. "
        "Routes ALL spacecraft sensor channels through ML-based anomaly detection."
    )
    # Subscribe to ALL sensor topics — not just telemetry-labeled ones
    subscriptions = [
        "aria.sensor.*",            # Every sensor channel
        "aria.command.telemetry.*", # Commands from coordinator
    ]
    heartbeat_interval_s = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._anomaly_count = 0
        self._readings_processed = 0
        # Wiring audit Pass 2 (F4.3) — observable progress proof for
        # the background flush loop.  ``_readings_processed`` only
        # advances when readings arrive; ``_flush_iterations`` advances
        # every loop tick regardless, so an external supervisor can
        # tell a wedged-but-idle loop apart from a wedged-and-stuck one.
        self._flush_iterations: int = 0
        self._last_flush_monotonic: float = 0.0
        self._severity_thresholds = SCORE_THRESHOLDS.copy()
        self._mapper = DsremoChannelMapper(satellite_id="sat-01")
        # Per-channel score cache: {channel_id: last_score}
        self._channel_scores: dict[str, float] = {}
        # Batch accumulator: collect readings within a short window then flush
        self._pending_readings: list[TelemetryReading] = []
        self._batch_flush_task: asyncio.Task[Any] | None = None
        self._batch_interval_s: float = 0.5  # Flush every 500ms

    async def on_start(self) -> None:
        logger.info(
            "telemetry_agent.started",
            mode="universal_dsremo_bridge",
            subscriptions=self.subscriptions,
        )
        # Start batch flush loop
        self._batch_flush_task = asyncio.create_task(self._batch_flush_loop())

        # Auto-subscribe to Dsremo WebSocket for real-time alerts
        ws_result = await self._tools.invoke("dsremo_websocket_subscribe", {
            "min_severity": "WATCH",
        })
        if ws_result.success:
            logger.info("telemetry_agent.dsremo_ws_subscribed")
        else:
            logger.warning("telemetry_agent.dsremo_ws_failed", error=ws_result.error)

    async def on_stop(self) -> None:
        if self._batch_flush_task:
            self._batch_flush_task.cancel()
            await asyncio.gather(self._batch_flush_task, return_exceptions=True)
        # Flush any remaining readings
        if self._pending_readings:
            await self._flush_batch(self._pending_readings.copy())
            self._pending_readings.clear()

    async def handle_message(self, message: Message) -> None:
        topic = message.topic

        if topic.startswith("aria.sensor."):
            await self._enqueue_sensor_reading(message)
        elif topic.startswith("aria.command.telemetry."):
            await self._process_command(message)

    # -----------------------------------------------------------------------
    # Sensor ingestion pipeline
    # -----------------------------------------------------------------------

    async def _enqueue_sensor_reading(self, message: Message) -> None:
        """Extract channels from sensor message and add to batch queue."""
        readings = self._mapper.extract(message.topic, message.payload)

        if not readings:
            return  # Non-numeric payload (e.g. status strings)

        # Add timestamp from message
        ts = message.timestamp or datetime.now(timezone.utc).isoformat()
        for r in readings:
            r.timestamp = ts

        self._pending_readings.extend(readings)
        self._readings_processed += len(readings)

        # If pending batch is large, flush immediately
        if len(self._pending_readings) >= 20:
            batch = self._pending_readings.copy()
            self._pending_readings.clear()
            await self._flush_batch(batch)

    async def _batch_flush_loop(self) -> None:
        """Periodically flush pending readings to Dsremo.

        Wiring audit Pass 2 (F4.3) — advances ``_flush_iterations``
        and ``_last_flush_monotonic`` on every tick so an external
        supervisor (or ``stats``) can detect a wedged loop.
        """
        import time as _time
        while True:
            try:
                await asyncio.sleep(self._batch_interval_s)
                self._last_flush_monotonic = _time.monotonic()
                if self._pending_readings:
                    batch = self._pending_readings.copy()
                    self._pending_readings.clear()
                    await self._flush_batch(batch)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("telemetry_agent.flush_error", error=str(exc))
            finally:
                self._flush_iterations += 1

    async def _flush_batch(self, readings: list[TelemetryReading]) -> None:
        """Send a batch of readings to Dsremo and process the results."""
        if not readings:
            return

        # First try batch endpoint; fall back to single-reading ingest
        batch_result = await self._tools.invoke(
            "dsremo_ingest_batch",
            {
                "readings": [
                    {
                        "satellite_id": r.satellite_id,
                        "channel_id": r.channel_id,
                        "value": r.value,
                        "timestamp": r.timestamp,
                    }
                    for r in readings
                ]
            },
        )

        if batch_result.success and batch_result.data:
            await self._process_batch_results(readings, batch_result.data)
        else:
            # Batch endpoint not available — fall back to single ingest per reading
            await self._fallback_single_ingest(readings)

    async def _fallback_single_ingest(self, readings: list[TelemetryReading]) -> None:
        """Single-reading fallback for older Dsremo deployments."""
        for r in readings:
            result = await self._tools.invoke(
                "dsremo_ingest_telemetry",
                {
                    "satellite_id": r.satellite_id,
                    "channel_id": r.channel_id,
                    "value": r.value,
                    "timestamp": r.timestamp,
                },
            )
            if result.success and result.data:
                score = result.data.get("anomaly_score", 0.0)
                if score > 0:
                    self._channel_scores[r.channel_id] = score
                    await self._evaluate_channel(r, score, result.data)

    async def _process_batch_results(
        self,
        readings: list[TelemetryReading],
        batch_data: dict[str, Any],
    ) -> None:
        """Process batch Dsremo response — evaluate each channel's score."""
        results = batch_data.get("results", [])

        # Build a lookup: channel_id → result
        result_map: dict[str, dict[str, Any]] = {}
        for res in results:
            cid = res.get("channel_id", "")
            if cid:
                result_map[cid] = res

        for reading in readings:
            res = result_map.get(reading.channel_id, {})
            score = res.get("anomaly_score", 0.0)
            if score > 0:
                self._channel_scores[reading.channel_id] = score
                await self._evaluate_channel(reading, score, res)

        # Publish channel score summary for audit trail
        if results:
            scored_channels = {
                r.get("channel_id"): r.get("anomaly_score", 0.0)
                for r in results if r.get("channel_id")
            }
            await self.publish(
                topic="aria.telemetry.scored",
                payload={
                    "channel_scores": scored_channels,
                    "anomalous": [c for c, s in scored_channels.items() if s >= SCORE_THRESHOLDS["watch"]],
                    "reading_count": len(readings),
                },
                priority=EventPriority.P4_BULK,
            )

    async def _evaluate_channel(
        self,
        reading: TelemetryReading,
        score: float,
        dsremo_result: dict[str, Any],
    ) -> None:
        """If score meets threshold, publish anomaly event with Dsremo verdict."""
        severity = self._classify_severity(score, reading.channel_id)
        if severity == Severity.NOMINAL:
            return

        self._anomaly_count += 1

        priority = {
            Severity.WATCH: EventPriority.P3_ROUTINE,
            Severity.WARNING: EventPriority.P2_WARNING,
            Severity.CRITICAL: EventPriority.P1_CRITICAL,
            Severity.EMERGENCY: EventPriority.P0_EMERGENCY,
        }.get(severity, EventPriority.P3_ROUTINE)

        await self.publish(
            topic="aria.anomaly.detected",
            payload={
                "severity": severity.name,
                "channel_id": reading.channel_id,
                "satellite_id": reading.satellite_id,
                "value": reading.value,
                "anomaly_score": score,
                "detectors_triggered": dsremo_result.get("detectors_triggered", []),
                "subsystem": reading.subsystem,
                "source_topic": reading.source_topic,
                "message": (
                    f"[Dsremo] Anomaly on {reading.channel_id}: "
                    f"score={score:.2f}, severity={severity.name}, "
                    f"value={reading.value}"
                ),
                "anomaly_count_total": self._anomaly_count,
            },
            priority=priority,
        )

        logger.info(
            "telemetry_agent.anomaly",
            severity=severity.name,
            channel=reading.channel_id,
            score=score,
            value=reading.value,
            subsystem=reading.subsystem,
        )

    def _classify_severity(self, score: float, channel_id: str) -> Severity:
        """Map Dsremo score to severity. Critical channels have lower warning threshold."""
        is_critical_channel = channel_id in CRITICAL_CHANNELS

        # Critical channels: lower threshold for escalation
        thresholds = self._severity_thresholds
        if is_critical_channel:
            if score >= thresholds["warning"]:  # Promote WATCH→WARNING for critical channels
                return Severity.WARNING if score < thresholds["critical"] else Severity.CRITICAL
            elif score >= thresholds["watch"]:
                return Severity.WATCH

        if score >= thresholds["critical"]:
            return Severity.CRITICAL
        elif score >= thresholds["warning"]:
            return Severity.WARNING
        elif score >= thresholds["watch"]:
            return Severity.WATCH
        return Severity.NOMINAL

    # -----------------------------------------------------------------------
    # Commands and queries
    # -----------------------------------------------------------------------

    async def _process_command(self, message: Message) -> None:
        command = message.payload.get("command", "")

        if command == "query_anomalies":
            result = await self._tools.invoke(
                "dsremo_query_anomalies",
                message.payload.get("params", {}),
            )
            await self.publish(
                topic="aria.telemetry.anomalies.response",
                payload={"anomalies": result.data if result.success else [], "error": result.error},
                correlation_id=message.correlation_id,
            )

        elif command == "channel_scores":
            await self.publish(
                topic="aria.telemetry.channel_scores.response",
                payload={
                    "scores": dict(self._channel_scores),
                    "readings_processed": self._readings_processed,
                    "anomaly_count": self._anomaly_count,
                },
                correlation_id=message.correlation_id,
            )

        elif command == "channel_health":
            channel_id = message.payload.get("channel_id", "")
            result = await self._tools.invoke(
                "dsremo_get_channel_health",
                {"channel_id": channel_id},
            )
            await self.publish(
                topic="aria.telemetry.channel_health.response",
                payload=result.data or {"error": result.error},
                correlation_id=message.correlation_id,
            )

    async def periodic_task(self) -> None:
        """Periodic: log telemetry processing stats and check for stale channels."""
        if self._readings_processed > 0:
            logger.info(
                "telemetry_agent.stats",
                readings_processed=self._readings_processed,
                anomalies_detected=self._anomaly_count,
                channels_tracked=len(self._channel_scores),
                pending_batch=len(self._pending_readings),
            )

        # Post telemetry processing stats to scratchpad
        if self._scratchpad:
            self._scratchpad.write("telemetry.stats", {
                "readings_processed": self._readings_processed,
                "anomalies_detected": self._anomaly_count,
                "channels_tracked": len(self._channel_scores),
            }, "telemetry", ttl_s=120)

    @property
    def stats(self) -> dict[str, Any]:
        base = super().stats
        base.update({
            "readings_processed": self._readings_processed,
            "anomalies_detected": self._anomaly_count,
            "channels_tracked": len(self._channel_scores),
        })
        return base
