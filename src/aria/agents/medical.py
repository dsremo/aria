"""MedicalAgent — crew health monitoring and medical response.

Per CENTRAL_AI_MASTER_PLAN Section 4.10 + Medical Panel 12:

Responsibilities:
  - Monitor crew vital signs from wearable biosensors
  - Track radiation exposure per crew member (integrates GenAstra)
  - Detect medical emergencies (cardiac, decompression sickness, etc.)
  - Manage medication schedules and exercise countermeasures
  - Monitor fatigue/sleep quality (Psychomotor Vigilance Task)
  - Psychological health indicators (activity patterns)
  - Telemedicine fallback when ground is unreachable

Sensor topics:
  - aria.sensor.medical.vitals.*: heart_rate_bpm, bp_systolic, bp_diastolic,
    spo2_percent, temperature_c, respiratory_rate
  - aria.sensor.medical.sleep: quality_score, duration_hours, rem_percent
  - aria.sensor.medical.exercise: type, duration_min, intensity
  - aria.command.medical.*: status, alert, schedule

Authority: AI_AUTONOMOUS for monitoring; AI_WITH_LOG for medication changes;
           CAPTAIN_CONSENT for major medical interventions
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()

# Vital sign thresholds (NASA-STD-3001 derived)
VITALS_THRESHOLDS = {
    "heart_rate_bpm": {"watch_low": 45, "watch_high": 100, "critical_low": 35, "critical_high": 150},
    "spo2_percent": {"watch_low": 94, "critical_low": 90},
    "bp_systolic": {"watch_high": 140, "critical_high": 180, "critical_low": 80},
    "temperature_c": {"watch_low": 35.5, "watch_high": 38.0, "critical_low": 34.0, "critical_high": 39.5},
    "respiratory_rate": {"watch_high": 25, "critical_high": 35, "critical_low": 8},
}


class MedicalAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Crew health monitoring and medical emergency detection.

    Dual-layer anomaly detection:
      Layer 1: Threshold rules — vital sign limits per NASA-STD-3001
      Layer 2: Dsremo ML — subtle vital sign trend changes, fatigue patterns
    """

    name = "medical"
    description = "Crew health monitoring, vital signs, radiation exposure, fatigue tracking"
    subscriptions = [
        "aria.sensor.medical.*",
        "aria.command.medical.*",
    ]
    heartbeat_interval_s = 15.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Per-crew vital signs (crew_id → vitals dict)
        self._crew_vitals: dict[str, dict[str, float]] = {}
        # Per-crew radiation exposure
        self._crew_radiation_msv: dict[str, float] = {}
        # Sleep/fatigue tracking
        self._crew_fatigue: dict[str, str] = {}  # crew_id → "low"|"medium"|"high"|"critical"
        self._crew_sleep_hours: dict[str, float] = {}
        # Exercise tracking
        self._crew_exercise_min_today: dict[str, float] = {}
        # Medication schedules
        self._medication_schedule: list[dict[str, Any]] = []
        # Bone density tracking (long-duration missions lose ~1-2% per month)
        self._crew_bone_density: dict[str, float] = {}  # crew_id → T-score
        # Alert state
        self._active_medical_alerts: dict[str, str] = {}  # crew_id → condition

    async def on_start(self) -> None:
        logger.info("medical_agent.started")

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic.startswith("aria.sensor.medical.vitals"):
            await self._update_vitals(payload)
        elif topic == "aria.sensor.medical.sleep":
            await self._update_sleep(payload)
        elif topic == "aria.sensor.medical.exercise":
            await self._update_exercise(payload)
        elif topic == "aria.sensor.medical.radiation":
            await self._update_crew_radiation(payload)
        elif topic == "aria.sensor.medical.bone_density":
            await self._update_bone_density(payload)
        elif topic == "aria.sensor.medical.vision":
            await self._update_vision(payload)
        elif topic == "aria.sensor.medical.psych":
            await self._update_psych(payload)
        elif topic == "aria.command.medical.status":
            await self._publish_medical_status(message.correlation_id)
        elif topic == "aria.command.medical.crew_report":
            await self._publish_crew_report(payload, message.correlation_id)

    async def _update_vitals(self, payload: dict[str, Any]) -> None:
        """Update crew member vital signs and check thresholds."""
        crew_id = payload.get("crew_id", "unknown")
        self._crew_vitals[crew_id] = {
            k: v for k, v in payload.items()
            if isinstance(v, (int, float)) and k != "crew_id"
        }

        # Check each vital against thresholds
        for vital, value in self._crew_vitals[crew_id].items():
            if vital not in VITALS_THRESHOLDS:
                continue

            limits = VITALS_THRESHOLDS[vital]
            severity = self._classify_vital(vital, value, limits)

            if severity == Severity.EMERGENCY:
                await self._medical_emergency(crew_id, vital, value)
            elif severity == Severity.CRITICAL:
                await self._raise_alert(
                    Severity.CRITICAL,
                    f"Crew {crew_id}: {vital}={value} — CRITICAL range",
                    {"crew_id": crew_id, "vital": vital, "value": value},
                )
            elif severity == Severity.WARNING:
                await self._raise_alert(
                    Severity.WARNING,
                    f"Crew {crew_id}: {vital}={value} — outside normal range",
                    {"crew_id": crew_id, "vital": vital, "value": value},
                )

        # Dsremo ML scoring for subtle vital sign trends
        readings = [
            {"subsystem": "medical", "component": crew_id, "metric": k, "value": v}
            for k, v in self._crew_vitals[crew_id].items()
            if isinstance(v, (int, float))
        ]
        if readings:
            scores = await self.dsremo_score_batch(readings)
            for channel_id, score in scores.items():
                if score >= 0.65:
                    await self._raise_alert(
                        Severity[self.dsremo_classify(score)],
                        f"[Dsremo] Crew {crew_id} vital anomaly: {channel_id} score={score:.2f}",
                        {"crew_id": crew_id, "channel_id": channel_id, "dsremo_score": score},
                    )

    def _classify_vital(self, vital: str, value: float, limits: dict[str, float]) -> Severity:
        """Classify vital sign value against thresholds."""
        if "critical_high" in limits and value >= limits["critical_high"]:
            return Severity.EMERGENCY
        if "critical_low" in limits and value <= limits["critical_low"]:
            return Severity.EMERGENCY
        if "watch_high" in limits and value >= limits["watch_high"]:
            return Severity.WARNING
        if "watch_low" in limits and value <= limits["watch_low"]:
            return Severity.WARNING
        return Severity.NOMINAL

    async def _medical_emergency(self, crew_id: str, vital: str, value: float) -> None:
        """Handle a medical emergency for a crew member."""
        self._active_medical_alerts[crew_id] = f"{vital}={value}"

        await self._raise_alert(
            Severity.EMERGENCY,
            f"MEDICAL EMERGENCY: Crew {crew_id} — {vital}={value}",
            {"crew_id": crew_id, "vital": vital, "value": value, "event": "medical_emergency"},
        )

        # Trigger medical alert tool
        await self._tools.invoke("crew_medical_alert", {
            "crew_member": crew_id,
            "condition": f"{vital} at {value}",
            "vital_signs": self._crew_vitals.get(crew_id, {}),
        })

        # Alert all crew via intercom
        await self._tools.invoke("crew_alert", {
            "recipients": ["all"],
            "priority": "EMERGENCY",
            "message": f"Medical emergency: {crew_id} — {vital} critical. Medical officer respond.",
            "audio_alarm": True,
            "require_acknowledgment": True,
        })

    async def _update_sleep(self, payload: dict[str, Any]) -> None:
        """Update crew sleep/fatigue tracking."""
        crew_id = payload.get("crew_id", "unknown")
        quality = payload.get("quality_score", 0.0)
        duration = payload.get("duration_hours", 0.0)

        self._crew_sleep_hours[crew_id] = duration

        # Fatigue classification
        if duration < 4.0 or quality < 30:
            self._crew_fatigue[crew_id] = "critical"
            await self._raise_alert(
                Severity.WARNING,
                f"Crew {crew_id}: critical fatigue — {duration:.1f}h sleep, quality={quality:.0f}",
                {"crew_id": crew_id, "sleep_hours": duration, "quality": quality},
            )
        elif duration < 6.0 or quality < 50:
            self._crew_fatigue[crew_id] = "high"
        elif duration < 7.0:
            self._crew_fatigue[crew_id] = "medium"
        else:
            self._crew_fatigue[crew_id] = "low"

    async def _update_exercise(self, payload: dict[str, Any]) -> None:
        """Track crew exercise for countermeasure compliance.

        Cardiovascular deconditioning is a major risk in microgravity.
        Crew must exercise ~2.5 hours/day to maintain fitness.
        """
        crew_id = payload.get("crew_id", "unknown")
        duration = payload.get("duration_min", 0.0)
        exercise_type = payload.get("type", "unknown")
        self._crew_exercise_min_today[crew_id] = (
            self._crew_exercise_min_today.get(crew_id, 0.0) + duration
        )

        # Track resting heart rate trend for cardiovascular deconditioning
        vitals = self._crew_vitals.get(crew_id, {})
        resting_hr = vitals.get("heart_rate_bpm", 0)
        if resting_hr > 0 and exercise_type == "rest_check":
            # Elevated resting HR (>85 bpm) suggests deconditioning
            if resting_hr > 85:
                await self._raise_alert(
                    Severity.WATCH,
                    f"Crew {crew_id}: elevated resting HR ({resting_hr} bpm) — "
                    "possible cardiovascular deconditioning. Increase exercise.",
                    {"crew_id": crew_id, "resting_hr": resting_hr, "event": "deconditioning"},
                )

    async def _update_crew_radiation(self, payload: dict[str, Any]) -> None:
        """Update per-crew radiation exposure."""
        crew_id = payload.get("crew_id", "unknown")
        dose_msv = payload.get("cumulative_dose_msv", 0.0)
        self._crew_radiation_msv[crew_id] = dose_msv

        # Career limit check (NASA-STD-3001: varies by age/sex, ~600 mSv effective)
        if dose_msv >= 500:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Crew {crew_id}: cumulative radiation {dose_msv:.0f} mSv — approaching career limit",
                {"crew_id": crew_id, "cumulative_dose_msv": dose_msv},
            )
        elif dose_msv >= 300:
            await self._raise_alert(
                Severity.WARNING,
                f"Crew {crew_id}: cumulative radiation {dose_msv:.0f} mSv — monitor exposure",
                {"crew_id": crew_id, "cumulative_dose_msv": dose_msv},
            )

    async def _update_bone_density(self, payload: dict[str, Any]) -> None:
        """Track crew bone density for long-duration mission countermeasures.

        Microgravity causes ~1-2% bone loss per month. ARED exercise
        and bisphosphonates mitigate but don't eliminate it.
        T-score < -1.0 = osteopenia, < -2.5 = osteoporosis risk.
        """
        crew_id = payload.get("crew_id", "unknown")
        t_score = payload.get("t_score", 0.0)
        self._crew_bone_density[crew_id] = t_score

        if t_score < -2.5:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Crew {crew_id}: bone density T-score={t_score:.1f} — osteoporosis range. "
                "Increase ARED resistance training. Consider bisphosphonate therapy.",
                {"crew_id": crew_id, "t_score": t_score, "event": "osteoporosis_risk"},
            )
        elif t_score < -1.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Crew {crew_id}: bone density T-score={t_score:.1f} — osteopenia range. "
                "Ensure ARED exercise compliance (2.5h/day).",
                {"crew_id": crew_id, "t_score": t_score, "event": "osteopenia"},
            )

    async def _update_vision(self, payload: dict[str, Any]) -> None:
        """Monitor crew vision for SANS (Spaceflight-Associated Neuro-ocular Syndrome).

        Intracranial pressure increase in microgravity can cause optic disc
        edema, globe flattening, and vision changes. Early detection is critical.
        """
        crew_id = payload.get("crew_id", "unknown")
        visual_acuity = payload.get("visual_acuity", 1.0)  # 1.0 = 20/20
        icp_estimate = payload.get("icp_estimate_mmhg", 15.0)  # Normal: 7-15 mmHg

        if icp_estimate > 20.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Crew {crew_id}: elevated ICP estimate ({icp_estimate:.0f} mmHg) — "
                "SANS risk. Schedule ophthalmology exam. Consider lower body negative pressure.",
                {"crew_id": crew_id, "icp_estimate_mmhg": icp_estimate, "event": "sans_risk"},
            )

        if visual_acuity < 0.8:  # Worse than 20/25
            await self._raise_alert(
                Severity.WARNING,
                f"Crew {crew_id}: degraded visual acuity ({visual_acuity:.2f}) — "
                "possible SANS progression or other ocular issue.",
                {"crew_id": crew_id, "visual_acuity": visual_acuity, "event": "vision_change"},
            )

    async def _update_psych(self, payload: dict[str, Any]) -> None:
        """Monitor crew psychological health indicators.

        Spaceflight isolation causes documented psychological stress.
        Track: communication frequency, sleep disruption, social withdrawal.
        """
        crew_id = payload.get("crew_id", "unknown")
        stress_score = payload.get("stress_score", 0.0)  # 0-10 scale
        isolation_hours = payload.get("isolation_hours", 0.0)

        if stress_score > 7.0:
            await self._raise_alert(
                Severity.WARNING,
                f"Crew {crew_id}: elevated stress score ({stress_score:.0f}/10) — "
                "schedule psychological support session",
                {"crew_id": crew_id, "stress_score": stress_score, "event": "psych_stress"},
            )

        if isolation_hours > 48.0:
            await self._raise_alert(
                Severity.WATCH,
                f"Crew {crew_id}: extended isolation ({isolation_hours:.0f}h) — "
                "encourage crew interaction activities",
                {"crew_id": crew_id, "isolation_hours": isolation_hours},
            )

    async def _publish_medical_status(self, correlation_id: str) -> None:
        """Publish overall medical status."""
        await self.publish(
            topic="aria.medical.status.response",
            payload={
                "crew_count": len(self._crew_vitals),
                "crew_vitals": self._crew_vitals,
                "fatigue_levels": self._crew_fatigue,
                "radiation_exposure_msv": self._crew_radiation_msv,
                "exercise_today_min": self._crew_exercise_min_today,
                "active_alerts": self._active_medical_alerts,
            },
            correlation_id=correlation_id,
        )

    async def _publish_crew_report(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Publish detailed report for a specific crew member."""
        crew_id = payload.get("crew_id", "")
        await self.publish(
            topic="aria.medical.crew_report.response",
            payload={
                "crew_id": crew_id,
                "vitals": self._crew_vitals.get(crew_id, {}),
                "fatigue": self._crew_fatigue.get(crew_id, "unknown"),
                "sleep_hours": self._crew_sleep_hours.get(crew_id, 0.0),
                "radiation_msv": self._crew_radiation_msv.get(crew_id, 0.0),
                "exercise_today_min": self._crew_exercise_min_today.get(crew_id, 0.0),
                "active_alert": self._active_medical_alerts.get(crew_id),
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
            topic="aria.anomaly.medical",
            payload={
                "severity": severity.name,
                "message": message,
                "subsystem": "medical",
                **(details or {}),
            },
            priority=priority,
        )

        # Wiring audit Pass 2 (F2.1) — crew-vital alarms (vitals
        # outside band, radiation dose breach, low exercise compliance
        # at extended-mission scale) deserve a structured Fault that
        # operators ack/shelve, not just a transient anomaly event.
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = (
                "critical"
                if severity in (Severity.CRITICAL, Severity.EMERGENCY)
                else "warning"
            )
            self.report_fault(message, severity=sev_str)

    async def periodic_task(self) -> None:
        """Periodic: check exercise compliance, read radiation from scratchpad."""
        # Post crew health summary to scratchpad
        if self._scratchpad and self._crew_vitals:
            self._scratchpad.write("medical.crew_health", {
                "crew_count": len(self._crew_vitals),
                "fatigue_levels": dict(self._crew_fatigue),
                "active_alerts": len(self._active_medical_alerts),
                "max_radiation_msv": max(self._crew_radiation_msv.values()) if self._crew_radiation_msv else 0,
            }, "medical", ttl_s=120)

        # Read radiation data from ScienceAgent's scratchpad
        if self._scratchpad:
            radiation = self._scratchpad.read("science.radiation")
            if radiation:
                dose_rate = radiation.get("dose_rate_usv_hr", 0.0)
                if dose_rate > 200.0:  # Elevated
                    for crew_id in self._crew_vitals:
                        current = self._crew_radiation_msv.get(crew_id, 0.0)
                        # Rough accumulation: dose_rate * hours since last check
                        hours = self.heartbeat_interval_s / 3600.0
                        self._crew_radiation_msv[crew_id] = current + dose_rate * hours / 1000.0

        # Read fire state — crew in fire zone may need medical attention
        if self._scratchpad:
            fire = self._scratchpad.read("eclss.fire_state")
            if fire and fire.get("smoke_detected"):
                zone = fire.get("zone", "unknown")
                # Crew in fire zone may have smoke inhalation
                for crew_id in self._crew_vitals:
                    if crew_id not in self._active_medical_alerts:
                        await self._raise_alert(
                            Severity.WARNING,
                            f"Crew {crew_id}: monitor for smoke inhalation — fire in {zone}",
                            {"crew_id": crew_id, "fire_zone": zone, "event": "smoke_inhalation_risk"},
                        )

        # Read ECLSS atmosphere data — high CO2 affects crew cognition
        if self._scratchpad:
            atmo = self._scratchpad.read("eclss.atmosphere")
            if atmo:
                co2 = atmo.get("co2_mmhg", 0.0)
                if co2 > 7.0:  # Above 7 mmHg = cognitive degradation risk
                    await self._raise_alert(
                        Severity.WATCH,
                        f"CO2 at {co2:.1f} mmHg may affect crew cognitive performance",
                        {"co2_mmhg": co2, "source": "eclss_scratchpad"},
                    )

        # Check exercise compliance — crew should do 2.5 hours/day (150 min)
        for crew_id, minutes in self._crew_exercise_min_today.items():
            if minutes < 60.0 and self._crew_fatigue.get(crew_id) in ("high", "critical"):
                await self._raise_alert(
                    Severity.WATCH,
                    f"Crew {crew_id}: low exercise ({minutes:.0f} min) with {self._crew_fatigue[crew_id]} fatigue",
                    {"crew_id": crew_id, "exercise_min": minutes},
                )
                # Send a reminder via crew alert tool
                await self._tools.invoke("crew_alert", {
                    "recipients": [crew_id],
                    "priority": "CAUTION",
                    "message": f"Exercise reminder: {minutes:.0f} of 150 min completed today. "
                    f"Current fatigue level: {self._crew_fatigue[crew_id]}.",
                })

    @property
    def stats(self) -> dict[str, Any]:
        base = super().stats
        base.update({
            "crew_monitored": len(self._crew_vitals),
            "active_medical_alerts": len(self._active_medical_alerts),
            "fatigue_levels": dict(self._crew_fatigue),
        })
        return base
