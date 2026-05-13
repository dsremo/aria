"""CommsAgent — communication link management and ground relay.

Responsibilities:
  - Monitor RF link status (signal strength, data rate, BER)
  - Track ground station contact windows and blackout periods
  - Queue and prioritize outbound messages
  - Manage uplink command reception
  - Detect link anomalies (signal degradation, interference)
  - Coordinate data downlink during contact windows

Sensor topics:
  - aria.sensor.comms.link: signal_dbm, snr_db, ber, data_rate_kbps
  - aria.sensor.comms.antenna: pointing_error_deg, temperature_c
  - aria.command.comms.*: send, configure, antenna_point

Integration:
  - Queues telemetry/science data for downlink
  - Receives ground commands and routes to coordinator
  - Alerts crew when entering/exiting contact windows
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()


class CommsAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Manages spacecraft communication links and ground relay.

    Dual-layer anomaly detection:
      Layer 1: Threshold rules — signal loss, low SNR, high BER
      Layer 2: Dsremo ML — subtle interference patterns, link degradation trends
    """

    name = "comms"
    description = "RF link management, ground contact scheduling, data relay"
    subscriptions = [
        "aria.sensor.comms.*",
        "aria.command.comms.*",
        "aria.science.discovery.*",
    ]
    heartbeat_interval_s = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Link state
        self._signal_dbm: float = -85.0
        self._snr_db: float = 15.0
        self._ber: float = 1e-9
        self._data_rate_kbps: float = 256.0
        self._link_active: bool = True

        # Antenna state
        self._antenna_pointing_error_deg: float = 0.1
        self._antenna_temperature_c: float = 25.0

        # Signal loss tracking
        self._signal_loss_start: float | None = None
        self._beacon_active: bool = False

        # Contact windows
        self._in_contact: bool = True
        self._next_contact_utc: str = ""
        self._contact_duration_min: float = 0.0

        # Message queue
        self._outbound_queue: list[dict[str, Any]] = []
        self._messages_sent: int = 0
        self._messages_queued: int = 0
        self._bytes_downlinked: int = 0
        self._bytes_queued: int = 0

    async def on_start(self) -> None:
        logger.info("comms_agent.started", signal_dbm=self._signal_dbm)
        # Self-test: antenna + RF chain
        test_result = await self._tools.invoke("diagnostic_run_subsystem_test", {
            "subsystem": "comms",
            "test_level": "quick",
        })
        if test_result.success and test_result.data and test_result.data.get("result") != "PASS":
            logger.warning("comms_agent.self_test_failed", result=test_result.data)

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.comms.link":
            await self._update_link(payload)
        elif topic == "aria.sensor.comms.antenna":
            await self._update_antenna(payload)
        elif topic == "aria.command.comms.send":
            await self._queue_message(payload, message.correlation_id)
        elif topic == "aria.command.comms.status":
            await self._publish_comms_status(message.correlation_id)
        elif topic.startswith("aria.science.discovery."):
            # Auto-queue high-priority downlink for science discoveries
            await self._queue_message({
                "message_type": "science_data",
                "priority": "HIGH",
                "data": str(message.payload),
            }, "")

    async def _update_link(self, payload: dict[str, Any]) -> None:
        """Update RF link state and check for anomalies."""
        self._signal_dbm = payload.get("signal_dbm", self._signal_dbm)
        self._snr_db = payload.get("snr_db", self._snr_db)
        self._ber = payload.get("ber", self._ber)
        self._data_rate_kbps = payload.get("data_rate_kbps", self._data_rate_kbps)

        prev_link = self._link_active
        self._link_active = self._signal_dbm > -110.0 and self._snr_db > 3.0

        # Contact state change detection
        if prev_link and not self._link_active:
            self._signal_loss_start = time.time()
            await self._raise_alert(
                Severity.WARNING,
                f"Communication link lost: signal={self._signal_dbm:.1f} dBm, SNR={self._snr_db:.1f} dB",
                {"signal_dbm": self._signal_dbm, "snr_db": self._snr_db, "event": "link_lost"},
            )
            self._in_contact = False
        elif not prev_link and self._link_active:
            await self.publish(
                topic="aria.comms.contact.acquired",
                payload={"signal_dbm": self._signal_dbm, "snr_db": self._snr_db},
            )
            self._in_contact = True
            self._signal_loss_start = None
            self._beacon_active = False
            # Flush queued messages
            await self._flush_queue()

        # Threshold checks
        if self._link_active:
            if self._snr_db < 6.0:
                await self._raise_alert(
                    Severity.WATCH,
                    f"Low SNR: {self._snr_db:.1f} dB — link marginal",
                    {"snr_db": self._snr_db},
                )

            if self._ber > 1e-5:
                await self._raise_alert(
                    Severity.WARNING,
                    f"High BER: {self._ber:.2e} — data integrity at risk",
                    {"ber": self._ber},
                )

        # Dsremo ML scoring for subtle degradation
        scores = await self.dsremo_score_batch([
            {"subsystem": "comms", "component": "link", "metric": "signal_dbm", "value": self._signal_dbm},
            {"subsystem": "comms", "component": "link", "metric": "snr_db", "value": self._snr_db},
        ])
        for channel_id, score in scores.items():
            if score >= 0.65:
                await self._raise_alert(
                    Severity[self.dsremo_classify(score)],
                    f"[Dsremo] Comms anomaly: {channel_id} score={score:.2f}",
                    {"channel_id": channel_id, "dsremo_score": score},
                )

    async def _update_antenna(self, payload: dict[str, Any]) -> None:
        """Update antenna state."""
        self._antenna_pointing_error_deg = payload.get(
            "pointing_error_deg", self._antenna_pointing_error_deg
        )
        self._antenna_temperature_c = payload.get(
            "temperature_c", self._antenna_temperature_c
        )

        if self._antenna_pointing_error_deg > 2.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Antenna pointing error: {self._antenna_pointing_error_deg:.2f} deg — may affect link margin",
                {"pointing_error_deg": self._antenna_pointing_error_deg},
            )

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Act on LLM directives for comms, gated through safe_dispatch_check."""
        await super().on_reasoning_response(payload)
        from aria.cognitive.action_executor import parse_recommendation
        from aria.cognitive.safe_dispatch import safe_dispatch_check, DispatchKind
        intents = parse_recommendation(payload.get("response", "") or "")
        for intent in intents:
            if intent.action == "switch_antenna":
                antenna = intent.params.get("antenna", "hga")
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="switch_antenna",
                    params={"antenna": antenna},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Power & thermal audit P-17: HGA switch is a pulsed
                # load (TX amp keys at high duty cycle when active).
                # Refuse the switch if the inrush would brown out the
                # bus or if SoC is below the burst floor.
                if antenna == "hga":
                    from aria.agents.inrush_guard import check_burst_allowed
                    pred = (
                        self._scratchpad.read("power.prediction")
                        if self._scratchpad else None
                    )
                    burst_w = 80_000.0    # NASA DSN Telecom 810-005 — Ka-band 80 kW
                    bus_v = (pred or {}).get("bus_voltage_v", 28.0) or 28.0
                    verdict = check_burst_allowed(
                        burst_steady_state_w=burst_w,
                        bus_voltage_v=float(bus_v),
                        power_prediction=pred,
                    )
                    if not verdict.allowed:
                        await self._raise_alert(
                            Severity.WARNING,
                            f"HGA switch refused: {verdict.reason}",
                            {"antenna": antenna,
                             "predicted_post_v": verdict.predicted_post_v,
                             "reason": verdict.reason},
                        )
                        continue
                # Wiring audit Pass 2 (F1.5/F1.6) — route through
                # dispatch_command for safety-layer wrap.
                antenna_params = {"antenna": antenna, "reason": "llm_directive"}
                seq = self.dispatch_command(
                    topic="aria.actuator.comms.switch_antenna",
                    params=antenna_params, timeout_s=15.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.comms.switch_antenna",
                        payload=antenna_params,
                        priority=EventPriority.P2_WARNING,
                    )
                await self.publish(
                    topic="aria.comms.llm_action.executed",
                    payload={"action": "switch_antenna", "antenna": antenna},
                    priority=EventPriority.P2_WARNING,
                )
                self._log_action_executed("switch_antenna", {"antenna": antenna})
            elif intent.action == "safe_mode":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="safe_mode",
                    params={"antenna": "lga"},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Wiring audit Pass 2 (F1.5/F1.6).
                lga_params = {"antenna": "lga", "reason": "llm_safe_mode"}
                seq = self.dispatch_command(
                    topic="aria.actuator.comms.switch_antenna",
                    params=lga_params, timeout_s=15.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.comms.switch_antenna",
                        payload=lga_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                await self.publish(
                    topic="aria.comms.llm_action.executed",
                    payload={"action": "safe_mode", "antenna": "lga"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("safe_mode", {"antenna": "lga"})

    async def _queue_message(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Queue a message for downlink."""
        msg = {
            "type": payload.get("message_type", "telemetry"),
            "priority": payload.get("priority", "NORMAL"),
            "data": payload.get("data", ""),
            "queued_at": time.time(),
        }
        self._outbound_queue.append(msg)
        self._bytes_queued += len(msg.get("data", "").encode())
        self._messages_queued += 1

        # Sort by priority
        priority_order = {"EMERGENCY": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
        self._outbound_queue.sort(key=lambda m: priority_order.get(m["priority"], 2))

        if self._in_contact:
            await self._flush_queue()

        await self.publish(
            topic="aria.comms.message.queued",
            payload={"queue_depth": len(self._outbound_queue), "type": msg["type"]},
            correlation_id=correlation_id,
        )

    async def _flush_queue(self) -> None:
        """Send queued messages during contact window."""
        sent = 0
        while self._outbound_queue and self._link_active:
            msg = self._outbound_queue.pop(0)
            data_size = len(msg.get("data", "").encode())
            self._bytes_downlinked += data_size
            self._messages_sent += 1
            sent += 1

        if sent > 0:
            await self.publish(
                topic="aria.comms.downlink.batch",
                payload={"messages_sent": sent, "bytes": self._bytes_downlinked},
            )

    async def _publish_comms_status(self, correlation_id: str) -> None:
        """Publish current comms status."""
        await self.publish(
            topic="aria.comms.status.response",
            payload={
                "link_active": self._link_active,
                "in_contact": self._in_contact,
                "signal_dbm": self._signal_dbm,
                "snr_db": self._snr_db,
                "ber": self._ber,
                "data_rate_kbps": self._data_rate_kbps,
                "antenna_pointing_error_deg": self._antenna_pointing_error_deg,
                "queue_depth": len(self._outbound_queue),
                "messages_sent": self._messages_sent,
                "bytes_downlinked": self._bytes_downlinked,
            },
            correlation_id=correlation_id,
        )

    async def _raise_alert(
        self, severity: Severity, message: str, details: dict[str, Any] | None = None,
    ) -> None:
        priority = {
            Severity.WATCH: EventPriority.P3_ROUTINE,
            Severity.WARNING: EventPriority.P2_WARNING,
            Severity.CRITICAL: EventPriority.P1_CRITICAL,
            Severity.EMERGENCY: EventPriority.P0_EMERGENCY,
        }.get(severity, EventPriority.P3_ROUTINE)

        await self.publish(
            topic="aria.anomaly.comms",
            payload={
                "severity": severity.name,
                "message": message,
                "subsystem": "comms",
                **(details or {}),
            },
            priority=priority,
        )

        # Wiring audit Pass 2 (F2.1) — promote WARNING+ alerts into a
        # structured Fault on the operator ack/shelve queue. Without
        # this, signal-loss / antenna-failure events emit transient
        # anomaly Messages but never enter Pass 1's persistent
        # FaultManager workflow.
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = (
                "critical"
                if severity in (Severity.CRITICAL, Severity.EMERGENCY)
                else "warning"
            )
            self.report_fault(message, severity=sev_str)

    async def periodic_task(self) -> None:
        """Periodic: publish link health, manage buffer, check beacon activation."""
        # Auto-beacon: activate after 30 minutes of continuous signal loss
        if self._signal_loss_start and not self._beacon_active:
            loss_duration_s = time.time() - self._signal_loss_start
            if loss_duration_s > 1800:  # 30 minutes
                self._beacon_active = True
                await self._raise_alert(
                    Severity.CRITICAL,
                    f"Extended signal loss ({loss_duration_s/60:.0f} min) — activating emergency beacon",
                    {"loss_duration_s": loss_duration_s, "event": "beacon_activated"},
                )
                await self.publish(
                    topic="aria.comms.beacon.activated",
                    payload={"reason": "extended_signal_loss", "duration_s": loss_duration_s},
                    priority=EventPriority.P1_CRITICAL,
                )

        # Read orbital state from NavigationAgent for contact window prediction
        next_contact_min = None
        if self._scratchpad:
            nav_state = self._scratchpad.read("nav.orbital_state")
            if nav_state:
                period_min = nav_state.get("orbital_period_min", 90)
                # Rough estimate: contact window every half orbit (~45 min for LEO)
                next_contact_min = period_min / 2.0

        # Post comms status with contact prediction to scratchpad
        if self._scratchpad:
            self._scratchpad.write("comms.link_status", {
                "link_active": self._link_active,
                "signal_dbm": self._signal_dbm,
                "snr_db": self._snr_db,
                "queue_depth": len(self._outbound_queue),
                "beacon_active": self._beacon_active,
                "next_contact_est_min": next_contact_min,
                "bytes_queued": self._bytes_queued,
                "bytes_downlinked": self._bytes_downlinked,
            }, "comms", ttl_s=120)

            # Data volume forecast — warn if queue is growing faster than downlink
            if self._bytes_queued > 1_000_000 and not self._link_active:
                await self._raise_alert(
                    Severity.WATCH,
                    f"Data queue growing: {self._bytes_queued / 1024:.0f} KB queued with no active link",
                    {"bytes_queued": self._bytes_queued, "link_active": False},
                )

        # If link is active and queue has messages, flush them
        if self._link_active and self._outbound_queue:
            await self._flush_queue()
