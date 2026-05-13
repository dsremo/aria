"""EclssAgent — Environmental Control and Life Support System.

The most safety-critical agent. Monitors and controls:
  - O2 concentration (target: 20.9% ± 0.5%)
  - CO2 concentration (target: < 5.3 mmHg)
  - Cabin pressure (target: 14.7 ± 0.3 psi)
  - Temperature and humidity
  - Water quality
  - Fire detection

Integrates with GenAstra for crew radiation monitoring.
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()

# CO2 toxicity thresholds (mmHg partial pressure)
CO2_THRESHOLDS = {
    "nominal": 3.0,
    "watch": 5.3,    # Mild headache
    "warning": 7.6,  # Cognitive impairment
    "critical": 10.0, # Serious impairment
    "emergency": 15.0, # Life-threatening
}

# Cabin pressure limits (psi)
PRESSURE_NOMINAL = 14.7
PRESSURE_WARNING_LOW = 14.0
PRESSURE_CRITICAL_LOW = 13.5
PRESSURE_LEAK_RATE = 0.17  # psi/hour max acceptable


class EclssAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Environmental Control and Life Support System agent.

    Dual-layer anomaly detection:
      Layer 1: Life-safety thresholds (CO2, O2, pressure) — hardcoded, non-negotiable
      Layer 2: Dsremo ML — detects slow CO2 drift, pressure micro-leaks,
               O2 depletion precursors that threshold rules miss until too late
    """

    name = "eclss"
    description = "Life support monitoring: O2, CO2, pressure, temperature, fire detection"
    subscriptions = [
        "aria.sensor.eclss.*",
        "aria.command.eclss.*",
        "aria.sensor.fire.*",
    ]
    heartbeat_interval_s = 5.0  # More frequent — life-critical

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Atmosphere state
        self._o2_percent: float = 20.9
        self._co2_mmhg: float = 2.5
        self._cabin_pressure_psi: float = 14.7
        self._humidity_percent: float = 45.0
        self._temperature_c: float = 22.0

        # Pressure history for leak detection
        self._pressure_history: list[tuple[float, float]] = []  # (timestamp, pressure)

        # Nitrogen management (cabin atmosphere is ~79% N2 + 21% O2)
        self._n2_percent: float = 78.1

        # Fire detection
        self._smoke_detected: bool = False
        self._co_ppm: float = 0.0

        # Water recycling
        # ISS WRS achieves 98% recovery as of 2024 (NASA validated)
        # Source: ISS Brine Processor Assembly + Urine Processor Assembly
        self._water_recycling_rate: float = 98.0  # % recovery (ISS-validated)

    async def on_start(self) -> None:
        logger.info("eclss_agent.started")
        # Self-test: verify atmosphere sensors and scrubber status
        test_result = await self._tools.invoke("diagnostic_run_subsystem_test", {
            "subsystem": "eclss",
            "test_level": "quick",
        })
        if test_result.success and test_result.data and test_result.data.get("result") != "PASS":
            logger.warning("eclss_agent.self_test_failed", result=test_result.data)

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.eclss.atmosphere":
            await self._update_atmosphere(payload)
        elif topic == "aria.sensor.eclss.pressure":
            await self._update_pressure(payload)
        elif topic == "aria.sensor.eclss.water":
            await self._update_water(payload)
        elif topic == "aria.sensor.fire.smoke":
            await self._handle_smoke(payload)
        elif topic == "aria.sensor.fire.co":
            await self._handle_co(payload)
        elif topic == "aria.command.eclss.status":
            await self._publish_status(message.correlation_id)

    async def _update_atmosphere(self, payload: dict[str, Any]) -> None:
        self._o2_percent = payload.get("o2_percent", self._o2_percent)
        self._co2_mmhg = payload.get("co2_mmhg", self._co2_mmhg)
        self._humidity_percent = payload.get("humidity_percent", self._humidity_percent)
        prev_temp = self._temperature_c
        self._temperature_c = payload.get("temperature_c", self._temperature_c)

        # Temperature rate-of-change — rapid change indicates fire or cooling failure
        temp_delta = abs(self._temperature_c - prev_temp)
        if temp_delta > 3.0:  # > 3°C change in one reading cycle
            await self._raise_alert(
                Severity.WARNING,
                f"Rapid cabin temperature change: {prev_temp:.1f}→{self._temperature_c:.1f}°C "
                f"(delta={temp_delta:.1f}°C) — possible fire or cooling system failure",
                {"temp_delta_c": temp_delta, "prev_temp_c": prev_temp, "subsystem": "atmosphere"},
            )

        # Post atmosphere state to scratchpad for other agents (MedicalAgent, CognitiveEngine)
        if self._scratchpad:
            self._scratchpad.write("eclss.atmosphere", {
                "o2_percent": self._o2_percent,
                "co2_mmhg": self._co2_mmhg,
                "humidity_percent": self._humidity_percent,
                "temperature_c": self._temperature_c,
                "pressure_psi": self._cabin_pressure_psi,
                "n2_percent": self._n2_percent,
                "smoke_detected": self._smoke_detected,
                "co_ppm": self._co_ppm,
            }, "eclss", ttl_s=120)

        # Humidity checks (NASA comfort: 25-75%, limits: 20-80%)
        if self._humidity_percent < 20.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Cabin humidity critically low: {self._humidity_percent:.0f}% — mucosal irritation risk",
                {"humidity_percent": self._humidity_percent, "subsystem": "atmosphere"},
            )
        elif self._humidity_percent > 80.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Cabin humidity high: {self._humidity_percent:.0f}% — condensation/mold risk",
                {"humidity_percent": self._humidity_percent, "subsystem": "atmosphere"},
            )

        # Cabin temperature comfort check (18-27°C per crew_cabin thermal zone)
        if self._temperature_c > 30.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Cabin temperature high: {self._temperature_c:.1f}°C — crew comfort degraded",
                {"temperature_c": self._temperature_c, "subsystem": "atmosphere"},
            )
        elif self._temperature_c < 16.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Cabin temperature low: {self._temperature_c:.1f}°C — crew comfort degraded",
                {"temperature_c": self._temperature_c, "subsystem": "atmosphere"},
            )

        # O2 checks
        if self._o2_percent < 19.5:
            await self._raise_alert(
                Severity.CRITICAL,
                f"O2 concentration low: {self._o2_percent:.1f}% (min safe: 19.5%)",
                {"o2_percent": self._o2_percent, "subsystem": "atmosphere"},
            )
        elif self._o2_percent > 23.5:
            await self._raise_alert(
                Severity.WARNING,
                f"O2 concentration high: {self._o2_percent:.1f}% — fire risk elevated",
                {"o2_percent": self._o2_percent, "subsystem": "atmosphere"},
            )

        # CO2 checks (staged response)
        if self._co2_mmhg >= CO2_THRESHOLDS["emergency"]:
            await self._raise_alert(
                Severity.EMERGENCY,
                f"CO2 EMERGENCY: {self._co2_mmhg:.1f} mmHg — life-threatening!",
                {"co2_mmhg": self._co2_mmhg, "subsystem": "co2"},
            )
            await self._activate_backup_scrubber()
        elif self._co2_mmhg >= CO2_THRESHOLDS["critical"]:
            await self._raise_alert(
                Severity.CRITICAL,
                f"CO2 critical: {self._co2_mmhg:.1f} mmHg — cognitive impairment likely",
                {"co2_mmhg": self._co2_mmhg, "subsystem": "co2"},
            )
            # Increase O2 generation rate to help flush CO2
            await self._tools.invoke("eclss_set_o2_rate", {
                "rate_liters_per_hour": 80.0,
                "reason": f"CO2 critical at {self._co2_mmhg:.1f} mmHg",
            })
        elif self._co2_mmhg >= CO2_THRESHOLDS["warning"]:
            await self._raise_alert(
                Severity.WARNING,
                f"CO2 elevated: {self._co2_mmhg:.1f} mmHg — headache possible",
                {"co2_mmhg": self._co2_mmhg, "subsystem": "co2"},
            )
        elif self._co2_mmhg >= CO2_THRESHOLDS["watch"]:
            await self._raise_alert(
                Severity.WATCH,
                f"CO2 watch: {self._co2_mmhg:.1f} mmHg — approaching limit",
                {"co2_mmhg": self._co2_mmhg, "subsystem": "co2"},
            )

        # Layer 2: Dsremo ML — catch subtle atmosphere drift
        # (below threshold but trend is anomalous — early warning of scrubber failure)
        scores = await self.dsremo_score_batch([
            {"subsystem": "eclss", "component": "atmosphere", "metric": "co2_mmhg", "value": self._co2_mmhg},
            {"subsystem": "eclss", "component": "atmosphere", "metric": "o2_percent", "value": self._o2_percent},
            {"subsystem": "eclss", "component": "atmosphere", "metric": "humidity_percent", "value": self._humidity_percent},
        ])
        for channel_id, score in scores.items():
            # Only report if Dsremo detects something AND thresholds aren't already alerting
            if score >= 0.65 and self._co2_mmhg < CO2_THRESHOLDS["watch"]:
                await self._raise_alert(
                    Severity[self.dsremo_classify(score)],
                    f"[Dsremo] ECLSS atmosphere anomaly on {channel_id}: "
                    f"score={score:.2f} — check for scrubber pre-failure",
                    {"channel_id": channel_id, "dsremo_score": score, "subsystem": "atmosphere"},
                )

    async def _update_pressure(self, payload: dict[str, Any]) -> None:
        import time

        new_pressure = payload.get("pressure_psi", self._cabin_pressure_psi)
        self._cabin_pressure_psi = new_pressure

        # Record for leak detection
        self._pressure_history.append((time.time(), new_pressure))
        # Keep 1 hour of history at most
        cutoff = time.time() - 3600
        self._pressure_history = [(t, p) for t, p in self._pressure_history if t > cutoff]

        # Pressure checks
        if new_pressure < PRESSURE_CRITICAL_LOW:
            await self._raise_alert(
                Severity.EMERGENCY,
                f"Cabin pressure critical: {new_pressure:.2f} psi — possible depressurization!",
                {"pressure_psi": new_pressure, "subsystem": "pressure"},
            )
            # Invoke emergency depressurization response tool
            await self._tools.invoke("emergency_depressurization_response", {
                "compartment": "main_cabin",
                # Leak rate estimate: treat the (ΔP = p_nom - p_measured)
                # delta as the pressure drop accumulated over the
                # 5 minute ECLSS sample window that triggers the
                # emergency-depress alert. psi → kPa = × 6.895.
                "leak_rate_kpa_per_min": abs(new_pressure - 14.7) * 6.895 / 5.0,
            })
        elif new_pressure < PRESSURE_WARNING_LOW:
            await self._raise_alert(
                Severity.WARNING,
                f"Cabin pressure low: {new_pressure:.2f} psi",
                {"pressure_psi": new_pressure, "subsystem": "pressure"},
            )

        # Leak rate detection
        if len(self._pressure_history) >= 10:
            await self._check_leak_rate()

    async def _check_leak_rate(self) -> None:
        """Compute pressure change rate and detect leaks."""
        if len(self._pressure_history) < 2:
            return
        t0, p0 = self._pressure_history[0]
        t1, p1 = self._pressure_history[-1]
        dt_hours = (t1 - t0) / 3600.0
        if dt_hours < 0.01:
            return

        rate_psi_per_hour = (p1 - p0) / dt_hours

        # Predict time to critical if leaking
        if rate_psi_per_hour < 0:
            pressure_margin = self._cabin_pressure_psi - PRESSURE_CRITICAL_LOW
            if pressure_margin > 0 and abs(rate_psi_per_hour) > 0.01:
                hours_to_critical = pressure_margin / abs(rate_psi_per_hour)
                if hours_to_critical < 4.0:
                    await self._raise_alert(
                        Severity.WARNING,
                        f"Pressure trending to CRITICAL in {hours_to_critical:.1f}h at current rate "
                        f"({rate_psi_per_hour:.3f} psi/hr)",
                        {"hours_to_critical": hours_to_critical, "rate_psi_hr": rate_psi_per_hour},
                    )

        if rate_psi_per_hour < -PRESSURE_LEAK_RATE:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Possible cabin leak detected: pressure dropping at {abs(rate_psi_per_hour):.3f} psi/hr "
                f"(max acceptable: {PRESSURE_LEAK_RATE} psi/hr)",
                {"leak_rate_psi_hr": rate_psi_per_hour, "subsystem": "pressure"},
            )

    async def _handle_smoke(self, payload: dict[str, Any]) -> None:
        """FIRE DETECTION — highest priority response."""
        self._smoke_detected = payload.get("detected", False)
        if self._smoke_detected:
            zone = payload.get("zone", "unknown")

            # Post fire state to scratchpad for MedicalAgent + other agents
            if self._scratchpad:
                self._scratchpad.write("eclss.fire_state", {
                    "smoke_detected": True,
                    "zone": zone,
                    "co_ppm": self._co_ppm,
                }, "eclss", ttl_s=600)

            await self._raise_alert(
                Severity.EMERGENCY,
                f"SMOKE DETECTED in {zone} — initiating fire response!",
                {"zone": zone, "subsystem": "fire"},
            )
            # Automated fire response
            await self.publish(
                topic="aria.emergency.fire.response",
                payload={
                    "zone": zone,
                    "actions": [
                        "cut_o2_to_zone",
                        "activate_suppression",
                        "seal_zone",
                        "crew_evacuate_zone",
                    ],
                },
                priority=EventPriority.P0_EMERGENCY,
            )

            # Invoke fire suppression tool
            await self._tools.invoke("emergency_fire_suppression", {
                "compartment": zone,
                "agent_type": "co2",
            })

            # If CO is also elevated, this is a confirmed fire — escalate further
            if self._co_ppm > 25.0:
                await self._raise_alert(
                    Severity.EMERGENCY,
                    f"CONFIRMED FIRE: smoke + CO ({self._co_ppm:.0f} ppm) in {zone}",
                    {"zone": zone, "co_ppm": self._co_ppm, "event": "confirmed_fire"},
                )
                # Invoke evacuation alert
                await self._tools.invoke("emergency_evacuation_alert", {
                    "compartment": zone,
                    "reason": f"Confirmed fire: smoke + CO at {self._co_ppm:.0f} ppm",
                })

    async def _handle_co(self, payload: dict[str, Any]) -> None:
        """Carbon monoxide detection — fire indicator and crew hazard."""
        self._co_ppm = payload.get("co_ppm", 0.0)
        if self._co_ppm > 200.0:  # Immediately dangerous to life
            await self._raise_alert(
                Severity.EMERGENCY,
                f"CO EMERGENCY: {self._co_ppm:.0f} ppm — IDLH level! Evacuate and don masks!",
                {"co_ppm": self._co_ppm, "subsystem": "atmosphere", "event": "co_emergency"},
            )
            # Invoke crew alert for immediate evacuation
            await self._tools.invoke("crew_alert", {
                "recipients": ["all"],
                "priority": "EMERGENCY",
                "message": f"CO level {self._co_ppm:.0f} ppm — don breathing apparatus immediately!",
                "audio_alarm": True,
            })
        elif self._co_ppm > 50.0:  # NIOSH ceiling limit
            await self._raise_alert(
                Severity.CRITICAL,
                f"CO high: {self._co_ppm:.0f} ppm — don breathing apparatus, investigate source",
                {"co_ppm": self._co_ppm, "subsystem": "atmosphere"},
            )
        elif self._co_ppm > 25.0:  # OSHA 8-hour limit
            await self._raise_alert(
                Severity.WARNING,
                f"CO elevated: {self._co_ppm:.0f} ppm — possible fire/contamination",
                {"co_ppm": self._co_ppm, "subsystem": "atmosphere"},
            )

    async def _update_water(self, payload: dict[str, Any]) -> None:
        """Monitor water quality per operating procedure limits."""
        conductivity = payload.get("conductivity_us_cm", 0)
        ph = payload.get("ph", 7.0)
        toc_ug_l = payload.get("toc_ug_l", 0)
        microbial_cfu_ml = payload.get("microbial_cfu_ml", 0)

        # Water recycling rate (target: >93% recovery)
        recycling_rate = payload.get("recycling_rate_percent", self._water_recycling_rate)
        self._water_recycling_rate = recycling_rate
        if recycling_rate < 85.0:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Water recycling rate critical: {recycling_rate:.0f}% (target >93%) — "
                "WRS may need maintenance. Reduce water consumption.",
                {"recycling_rate_percent": recycling_rate, "subsystem": "water"},
            )
        elif recycling_rate < 93.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Water recycling rate below target: {recycling_rate:.0f}% (target >93%)",
                {"recycling_rate_percent": recycling_rate, "subsystem": "water"},
            )

        # Conductivity check (limit: 500 µS/cm)
        if conductivity > 500:
            await self._raise_alert(
                Severity.WARNING,
                f"Water quality degraded: conductivity {conductivity} µS/cm (limit: 500)",
                {"conductivity_us_cm": conductivity, "subsystem": "water"},
            )

        # pH check (acceptable: 6.0-8.5)
        if ph < 6.0 or ph > 8.5:
            await self._raise_alert(
                Severity.WARNING,
                f"Water pH out of range: {ph:.1f} (acceptable: 6.0-8.5)",
                {"ph": ph, "subsystem": "water"},
            )

        # Microbial count (limit: 50 CFU/mL)
        if microbial_cfu_ml > 50:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Water microbial contamination: {microbial_cfu_ml} CFU/mL (limit: 50)",
                {"microbial_cfu_ml": microbial_cfu_ml, "subsystem": "water"},
            )

        # Dsremo ML scoring on water quality parameters
        readings = []
        if conductivity > 0:
            readings.append({"subsystem": "eclss", "component": "water", "metric": "conductivity_us_cm", "value": float(conductivity)})
        if toc_ug_l > 0:
            readings.append({"subsystem": "eclss", "component": "water", "metric": "toc_ug_l", "value": float(toc_ug_l)})
        if readings:
            scores = await self.dsremo_score_batch(readings)
            for channel_id, score in scores.items():
                if score >= 0.65:
                    await self._raise_alert(
                        Severity[self.dsremo_classify(score)],
                        f"[Dsremo] Water quality anomaly: {channel_id} score={score:.2f}",
                        {"channel_id": channel_id, "dsremo_score": score, "subsystem": "water"},
                    )

    async def _activate_backup_scrubber(self) -> None:
        """Emergency: switch to backup CO2 scrubber.

        Wiring audit Pass 2 (F1.5/F1.6) — emergency scrubber activation
        routes through ``dispatch_command`` so ExecutionGuard +
        CommandTracker enforce preconditions and arm a timeout. Falls
        back to direct publish only when no safety context is wired.
        """
        scrubber_params = {"activate": True, "reason": "co2_emergency"}
        seq = self.dispatch_command(
            topic="aria.actuator.eclss.scrubber_backup",
            params=scrubber_params, timeout_s=10.0,
        )
        if seq is None:
            await self.publish(
                topic="aria.actuator.eclss.scrubber_backup",
                payload=scrubber_params,
                priority=EventPriority.P0_EMERGENCY,
            )
        logger.warning("eclss_agent.backup_scrubber_activated", seq=seq)

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Act on LLM directives that target ECLSS, gated through the
        full failsafe stack (safe_dispatch_check)."""
        await super().on_reasoning_response(payload)
        from aria.cognitive.action_executor import parse_recommendation
        from aria.cognitive.safe_dispatch import safe_dispatch_check, DispatchKind
        intents = parse_recommendation(payload.get("response", "") or "")
        for intent in intents:
            if intent.action == "boost_scrubber":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="boost_scrubber", params={},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                await self._activate_backup_scrubber()
                await self.publish(
                    topic="aria.eclss.llm_action.executed",
                    payload={"action": "boost_scrubber"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("boost_scrubber", {})
            elif intent.action == "pressurize_cabin":
                kpa = intent.params.get("kpa")
                if kpa is None:
                    continue
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="pressurize_cabin",
                    params={"kpa": float(kpa)},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Wiring audit Pass 2 (F1.5/F1.6) — route through
                # dispatch_command for the safety-layer wrap.
                pressure_params = {
                    "target_kpa": float(kpa), "reason": "llm_directive",
                }
                seq = self.dispatch_command(
                    topic="aria.actuator.eclss.cabin_pressure",
                    params=pressure_params, timeout_s=30.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.eclss.cabin_pressure",
                        payload=pressure_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                await self.publish(
                    topic="aria.eclss.llm_action.executed",
                    payload={"action": "pressurize_cabin", "kpa": kpa},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("pressurize_cabin", {"kpa": kpa})
            elif intent.action == "safe_mode":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="safe_mode", params={},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                await self._activate_backup_scrubber()
                # Wiring audit Pass 2 (F1.5/F1.6).
                vents_params = {"reason": "llm_safe_mode"}
                seq = self.dispatch_command(
                    topic="aria.actuator.eclss.close_non_essential_vents",
                    params=vents_params, timeout_s=15.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.eclss.close_non_essential_vents",
                        payload=vents_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                await self.publish(
                    topic="aria.eclss.llm_action.executed",
                    payload={"action": "safe_mode"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("safe_mode", {})

    async def _publish_status(self, correlation_id: str) -> None:
        await self.publish(
            topic="aria.eclss.status.response",
            payload={
                "o2_percent": self._o2_percent,
                "co2_mmhg": self._co2_mmhg,
                "cabin_pressure_psi": self._cabin_pressure_psi,
                "humidity_percent": self._humidity_percent,
                "temperature_c": self._temperature_c,
                "smoke_detected": self._smoke_detected,
                "co_ppm": self._co_ppm,
            },
            correlation_id=correlation_id,
        )

    async def periodic_task(self) -> None:
        """Periodic: CO2 trend analysis and air quality assessment."""
        # Track CO2 trend — rising CO2 indicates scrubber degradation
        co2_rate = getattr(self, "_co2_trend_rate", 0.0)
        prev_co2 = getattr(self, "_prev_co2", self._co2_mmhg)
        self._co2_trend_rate = self._co2_mmhg - prev_co2
        self._prev_co2 = self._co2_mmhg

        # Rising CO2 trend when already elevated = scrubber not keeping up
        if self._co2_trend_rate > 0.5 and self._co2_mmhg > 4.0:
            await self._raise_alert(
                Severity.WATCH,
                f"CO2 rising trend: +{self._co2_trend_rate:.1f} mmHg/cycle "
                f"at {self._co2_mmhg:.1f} mmHg — scrubber may be degrading",
                {"co2_rate": self._co2_trend_rate, "co2_mmhg": self._co2_mmhg},
            )

        # Request air quality analysis from GenAstra
        result = await self._tools.invoke("genastra_air_quality_analysis", {})
        if result.success and result.data:
            contaminants = result.data.get("contaminants_detected", [])
            if contaminants:
                await self._raise_alert(
                    Severity.WARNING,
                    f"Air contaminants detected: {contaminants}",
                    {"contaminants": contaminants},
                )

    async def _raise_alert(self, severity: Severity, message: str, details: dict[str, Any]) -> None:
        priority_map = {
            Severity.WATCH: EventPriority.P3_ROUTINE,
            Severity.WARNING: EventPriority.P2_WARNING,
            Severity.CRITICAL: EventPriority.P1_CRITICAL,
            Severity.EMERGENCY: EventPriority.P0_EMERGENCY,
        }
        await self.publish(
            topic="aria.anomaly.eclss",
            payload={"severity": severity.name, "message": message, **details},
            priority=priority_map.get(severity, EventPriority.P2_WARNING),
        )

        # Structured fault reporting via FaultManager
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = "critical" if severity in (Severity.CRITICAL, Severity.EMERGENCY) else "warning"
            self.report_fault(message, severity=sev_str)
