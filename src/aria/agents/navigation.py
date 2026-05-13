"""NavigationAgent — spatial awareness and conjunction monitoring.

Responsibilities:
  - Consume IMU, GPS, star tracker data
  - Maintain current orbital state estimate
  - Interface with ConjunctionWatch for collision avoidance
  - Publish navigation updates and conjunction alerts
  - Support maneuver planning requests
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()

# Constants
MU_EARTH = 3.986004418e14  # m^3/s^2
R_EARTH = 6371000.0  # meters


class NavigationAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Maintains spacecraft navigation state and collision awareness.

    Dual-layer anomaly detection:
      Layer 1: Threshold rules (tumble detection >5 deg/s, GPS fix loss)
      Layer 2: Dsremo ML — catches subtle orbital decay, attitude drift,
               GPS multipath errors, IMU bias drift before they become critical
    """

    name = "navigation"
    description = "Orbital state estimation, conjunction monitoring via ConjunctionWatch"
    subscriptions = [
        "aria.sensor.nav.*",
        "aria.command.nav.*",
        "aria.conjunction.*",
    ]
    heartbeat_interval_s = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Orbital state
        self._altitude_km: float = 400.0  # ISS-like default
        self._velocity_ms: float = 7660.0
        self._inclination_deg: float = 51.6
        self._latitude_deg: float = 0.0
        self._longitude_deg: float = 0.0

        # Attitude
        self._quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
        self._angular_rate_dps: tuple[float, float, float] = (0.0, 0.0, 0.0)

        # GPS status
        self._gps_fix: bool = False
        self._gps_satellites: int = 0
        self._tle_age_hours: float = 0.0  # How stale is our TLE data

        # Conjunction tracking
        self._active_conjunctions: list[dict[str, Any]] = []
        self._next_conjunction_hours: float | None = None

    async def on_start(self) -> None:
        logger.info("navigation_agent.started", altitude_km=self._altitude_km)
        # Self-test: ADCS + navigation sensors
        test_result = await self._tools.invoke("diagnostic_run_subsystem_test", {
            "subsystem": "adcs",
            "test_level": "quick",
        })
        if test_result.success and test_result.data and test_result.data.get("result") != "PASS":
            logger.warning("navigation_agent.self_test_failed", result=test_result.data)

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.nav.gps":
            await self._update_gps(payload)
        elif topic == "aria.sensor.nav.imu":
            await self._update_imu(payload)
        elif topic == "aria.sensor.nav.star_tracker":
            await self._update_star_tracker(payload)
        elif topic == "aria.conjunction.alert":
            await self._handle_conjunction(payload)
        elif topic == "aria.command.nav.status":
            await self._publish_nav_state(message.correlation_id)
        elif topic == "aria.command.nav.plan_maneuver":
            await self._plan_maneuver(payload, message.correlation_id)

    async def _update_gps(self, payload: dict[str, Any]) -> None:
        prev_alt = self._altitude_km
        self._gps_fix = payload.get("fix", False)
        self._gps_satellites = payload.get("satellites", 0)
        if self._gps_fix:
            self._altitude_km = payload.get("altitude_km", self._altitude_km)

            # Orbit decay monitoring — altitude dropping faster than expected
            alt_drop = prev_alt - self._altitude_km
            if alt_drop > 0.5 and prev_alt > 100:  # >500m drop per reading
                await self.publish(
                    topic="aria.anomaly.navigation",
                    payload={
                        "severity": Severity.WATCH.name,
                        "message": f"Orbit decay: altitude dropped {alt_drop:.2f} km "
                        f"({prev_alt:.1f}→{self._altitude_km:.1f} km) — may need orbit raise",
                        "altitude_drop_km": alt_drop,
                        "subsystem": "navigation",
                    },
                    priority=EventPriority.P3_ROUTINE,
                )
            self._latitude_deg = payload.get("latitude_deg", self._latitude_deg)
            self._longitude_deg = payload.get("longitude_deg", self._longitude_deg)
            self._velocity_ms = payload.get("velocity_ms", self._velocity_ms)

        # GPS constellation health — degraded accuracy with few satellites
        if self._gps_fix and self._gps_satellites < 6:
            await self.publish(
                topic="aria.anomaly.navigation",
                payload={
                    "severity": Severity.WATCH.name,
                    "message": f"GPS constellation degraded: only {self._gps_satellites} satellites tracked (optimal: 8+)",
                    "gps_satellites": self._gps_satellites,
                    "subsystem": "gps",
                },
                priority=EventPriority.P3_ROUTINE,
            )

        if not self._gps_fix and self._gps_satellites < 4:
            await self.publish(
                topic="aria.anomaly.navigation",
                payload={
                    "severity": Severity.WATCH.name,
                    "message": f"GPS fix lost — only {self._gps_satellites} satellites",
                    "subsystem": "gps",
                },
                priority=EventPriority.P2_WARNING,
            )

    async def _update_imu(self, payload: dict[str, Any]) -> None:
        ax = payload.get("angular_rate_x_dps", 0.0)
        ay = payload.get("angular_rate_y_dps", 0.0)
        az = payload.get("angular_rate_z_dps", 0.0)
        self._angular_rate_dps = (ax, ay, az)

        # Layer 1: Threshold check for tumbling
        total_rate = math.sqrt(ax**2 + ay**2 + az**2)
        if total_rate > 5.0:  # degrees per second
            tumble_message = f"High angular rate detected: {total_rate:.1f} deg/s — possible tumble"
            await self.publish(
                topic="aria.anomaly.navigation",
                payload={
                    "severity": Severity.CRITICAL.name,
                    "message": tumble_message,
                    "angular_rate_dps": total_rate,
                    "subsystem": "adcs",
                },
                priority=EventPriority.P1_CRITICAL,
            )
            # Wiring audit Pass 2 (F2.1) — open a structured Fault so
            # the operator console gets an ack/shelve entry, not just
            # a transient anomaly event.
            self.report_fault(tumble_message, severity="critical")
            # FDIR: activate ADCS safe-point mode (sun-pointing for power)
            if total_rate > 10.0:
                await self._tools.invoke("adcs_desaturate_wheels", {})
                await self._tools.invoke("emergency_safe_mode", {
                    "level": 1,
                    "affected_subsystem": "adcs",
                    "reason": f"Tumble detected: {total_rate:.1f} deg/s",
                })

        # Layer 2: Dsremo ML — catch subtle IMU drift / bias anomalies
        scores = await self.dsremo_score_batch([
            {"subsystem": "nav", "component": "imu", "metric": "angular_rate_x_dps", "value": ax},
            {"subsystem": "nav", "component": "imu", "metric": "angular_rate_y_dps", "value": ay},
            {"subsystem": "nav", "component": "imu", "metric": "angular_rate_z_dps", "value": az},
        ])
        for channel_id, score in scores.items():
            if score >= 0.65 and total_rate <= 5.0:
                await self.publish(
                    topic="aria.anomaly.navigation",
                    payload={
                        "severity": self.dsremo_classify(score),
                        "message": f"[Dsremo] IMU anomaly on {channel_id}: score={score:.2f}",
                        "channel_id": channel_id,
                        "dsremo_score": score,
                        "subsystem": "adcs",
                    },
                    priority=EventPriority.P2_WARNING,
                )

    async def _update_star_tracker(self, payload: dict[str, Any]) -> None:
        q = payload.get("quaternion")
        if q and len(q) == 4:
            self._quaternion = tuple(q)  # type: ignore[assignment]

    async def _handle_conjunction(self, payload: dict[str, Any]) -> None:
        """Process conjunction alert from ConjunctionWatch integration."""
        pc = payload.get("collision_probability", 0.0)
        tca_hours = payload.get("time_to_tca_hours", float("inf"))
        object_name = payload.get("object_name", "UNKNOWN")

        self._next_conjunction_hours = tca_hours
        self._active_conjunctions.append(payload)
        # Keep only most recent 20
        self._active_conjunctions = self._active_conjunctions[-20:]

        # Post to scratchpad for PropulsionAgent
        if self._scratchpad:
            self._scratchpad.write("nav.next_conjunction", {
                "object_name": object_name,
                "collision_probability": pc,
                "time_to_tca_hours": tca_hours,
            }, "navigation", ttl_s=3600)

        if pc > 1e-3:
            severity = Severity.CRITICAL
            priority = EventPriority.P0_EMERGENCY
        elif pc > 1e-4:
            severity = Severity.WARNING
            priority = EventPriority.P1_CRITICAL
        else:
            severity = Severity.WATCH
            priority = EventPriority.P2_WARNING

        conjunction_message = (
            f"Conjunction with {object_name}: Pc={pc:.2e}, TCA in {tca_hours:.1f}h"
        )
        await self.publish(
            topic="aria.anomaly.conjunction",
            payload={
                "severity": severity.name,
                "message": conjunction_message,
                "collision_probability": pc,
                "time_to_tca_hours": tca_hours,
                "object_name": object_name,
            },
            priority=priority,
        )

        # Wiring audit Pass 2 (F2.1) — promote WARNING+ conjunction
        # alerts into a structured Fault. The post-maneuver Pc
        # workflow needs operator ack/shelve.
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = (
                "critical"
                if severity in (Severity.CRITICAL, Severity.EMERGENCY)
                else "warning"
            )
            self.report_fault(conjunction_message, severity=sev_str)
        logger.warning(
            "navigation_agent.conjunction",
            object=object_name,
            pc=pc,
            tca_hours=tca_hours,
        )

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Act on LLM directives for navigation, gated through
        safe_dispatch_check (kill switch + constitution + budget)."""
        await super().on_reasoning_response(payload)
        from aria.cognitive.action_executor import parse_recommendation
        from aria.cognitive.safe_dispatch import safe_dispatch_check, DispatchKind
        intents = parse_recommendation(payload.get("response", "") or "")
        for intent in intents:
            if intent.action == "attitude_hold":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="attitude_hold", params={},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Wiring audit Pass 2 (F1.5/F1.6) — route through
                # dispatch_command for safety-layer wrap.
                hold_params = {"reason": "llm_directive"}
                seq = self.dispatch_command(
                    topic="aria.actuator.nav.attitude_hold",
                    params=hold_params, timeout_s=20.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.nav.attitude_hold",
                        payload=hold_params,
                        priority=EventPriority.P2_WARNING,
                    )
                await self.publish(
                    topic="aria.nav.llm_action.executed",
                    payload={"action": "attitude_hold"},
                    priority=EventPriority.P2_WARNING,
                )
                self._log_action_executed("attitude_hold", {})
            elif intent.action == "safe_mode":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="safe_mode", params={},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Wiring audit Pass 2 (F1.5/F1.6) — safe-mode actuator
                # commands route through dispatch_command.
                safe_hold_params = {"reason": "llm_safe_mode"}
                seq = self.dispatch_command(
                    topic="aria.actuator.nav.attitude_hold",
                    params=safe_hold_params, timeout_s=20.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.nav.attitude_hold",
                        payload=safe_hold_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                rcs_params = {"reason": "llm_safe_mode"}
                seq = self.dispatch_command(
                    topic="aria.actuator.nav.rcs_minimum",
                    params=rcs_params, timeout_s=20.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.nav.rcs_minimum",
                        payload=rcs_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                await self.publish(
                    topic="aria.nav.llm_action.executed",
                    payload={"action": "safe_mode"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("safe_mode", {})

    async def _plan_maneuver(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Request maneuver planning from ConjunctionWatch."""
        result = await self._tools.invoke(
            "conjunction_watch_plan_maneuver",
            payload,
        )
        await self.publish(
            topic="aria.nav.maneuver.plan.response",
            payload={"plan": result.data if result.success else None, "error": result.error},
            correlation_id=correlation_id,
        )

    async def _publish_nav_state(self, correlation_id: str) -> None:
        """Publish current navigation state."""
        # Compute orbital period
        r = (R_EARTH + self._altitude_km * 1000)
        period_min = 2 * math.pi * math.sqrt(r**3 / MU_EARTH) / 60.0

        await self.publish(
            topic="aria.nav.state.response",
            payload={
                "altitude_km": self._altitude_km,
                "velocity_ms": self._velocity_ms,
                "inclination_deg": self._inclination_deg,
                "latitude_deg": self._latitude_deg,
                "longitude_deg": self._longitude_deg,
                "orbital_period_min": round(period_min, 2),
                "quaternion": self._quaternion,
                "angular_rate_dps": self._angular_rate_dps,
                "gps_fix": self._gps_fix,
                "gps_satellites": self._gps_satellites,
                "active_conjunctions": len(self._active_conjunctions),
                "next_conjunction_hours": self._next_conjunction_hours,
            },
            correlation_id=correlation_id,
        )

    async def periodic_task(self) -> None:
        """Periodic: conjunction screening, orbit determination, TLE staleness check."""
        # TLE staleness check — stale TLEs degrade conjunction screening accuracy
        self._tle_age_hours += self.heartbeat_interval_s / 3600.0
        if self._tle_age_hours > 72.0:
            await self.publish(
                topic="aria.anomaly.navigation",
                payload={
                    "severity": Severity.WARNING.name,
                    "message": f"TLE data stale: {self._tle_age_hours:.0f}h old (max 72h). "
                    "Conjunction screening accuracy degraded. Request TLE update from ground.",
                    "tle_age_hours": self._tle_age_hours,
                    "subsystem": "navigation",
                },
                priority=EventPriority.P2_WARNING,
            )

        # Trigger conjunction screening via ConjunctionWatch
        result = await self._tools.invoke(
            "conjunction_watch_run_screening",
            {"screening_period_hours": 72},
        )
        if result.success and result.data:
            events = result.data.get("high_risk_events", [])
            if events:
                for event in events[:3]:  # Process top 3
                    await self._handle_conjunction(event)

        # Run orbit determination for state update
        od_result = await self._tools.invoke("navigation_orbit_determination", {})
        if od_result.success and od_result.data:
            converged = od_result.data.get("converged", False)
            if not converged:
                await self.publish(
                    topic="aria.anomaly.navigation",
                    payload={
                        "severity": Severity.WATCH.name,
                        "message": "Orbit determination did not converge — GPS data may be stale",
                        "subsystem": "navigation",
                    },
                    priority=EventPriority.P3_ROUTINE,
                )

        # Post orbital state + ground track prediction to scratchpad
        if self._scratchpad:
            # Compute orbital period for ground track prediction
            r = (R_EARTH + self._altitude_km * 1000)
            period_min = 2 * math.pi * math.sqrt(r**3 / MU_EARTH) / 60.0

            self._scratchpad.write("nav.orbital_state", {
                "altitude_km": self._altitude_km,
                "velocity_ms": self._velocity_ms,
                "latitude_deg": self._latitude_deg,
                "longitude_deg": self._longitude_deg,
                "gps_fix": self._gps_fix,
                "orbital_period_min": round(period_min, 1),
                "active_conjunctions": len(self._active_conjunctions),
                "next_conjunction_hours": self._next_conjunction_hours,
            }, "navigation", ttl_s=120)

            # Read fuel status — affects maneuver planning feasibility
            fuel = self._scratchpad.read("propulsion.fuel_status")
            if fuel and fuel.get("delta_v_remaining_ms", 999) < 10.0:
                await self.publish(
                    topic="aria.anomaly.navigation",
                    payload={
                        "severity": Severity.WARNING.name,
                        "message": f"Low delta-V budget: {fuel['delta_v_remaining_ms']:.1f} m/s — "
                        "collision avoidance capability limited",
                        "delta_v_remaining_ms": fuel["delta_v_remaining_ms"],
                        "subsystem": "navigation",
                    },
                    priority=EventPriority.P2_WARNING,
                )
