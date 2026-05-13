"""ScienceAgent — scientific instruments and GenAstra integration.

Responsibilities:
  - Manage scientific instrument operations
  - Interface with GenAstra for biosignature detection and gene expression
  - Schedule and execute observation campaigns
  - Monitor radiation environment for crew and experiments
  - Track science data collection and downlink priority

Sensor topics:
  - aria.sensor.science.spectrometer: wavelength data, integration status
  - aria.sensor.science.radiation: dose_rate_usv_hr, cumulative_dose_msv
  - aria.sensor.science.sample.*: sample status, analysis results
  - aria.command.science.*: observe, analyze, schedule

Integration:
  - GenAstra tools for biosignature + radiation + gene expression
  - Coordinates with CommsAgent for science data downlink
  - Coordinates with PowerAgent for instrument power budget
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()

# Radiation limits (crew)
DOSE_RATE_WATCH_USV_HR = 50.0      # μSv/hr - elevated
DOSE_RATE_WARNING_USV_HR = 200.0   # μSv/hr - seek shelter advisory
DOSE_RATE_CRITICAL_USV_HR = 1000.0 # μSv/hr - solar particle event
CUMULATIVE_DOSE_WARNING_MSV = 100.0  # Career limit check
CUMULATIVE_DOSE_CRITICAL_MSV = 500.0


class ScienceAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Manages scientific instruments and GenAstra integration.

    Dual-layer anomaly detection:
      Layer 1: Threshold rules — radiation spikes, instrument faults
      Layer 2: Dsremo ML — subtle instrument drift, radiation trend analysis
    """

    name = "science"
    description = "Scientific instruments, GenAstra biosignature/radiation analysis"
    subscriptions = [
        "aria.sensor.science.*",
        "aria.command.science.*",
    ]
    heartbeat_interval_s = 30.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Radiation monitoring — LEO background dose rate at ISS
        # altitude (ICRP 123 eq. 8.3; measured ISS average ~0.5
        # µSv/hr, ~4 mSv/yr integrated, matching Wu et al. 2009
        # Health Phys 97 62 Table 2).
        self._dose_rate_usv_hr: float = 0.5
        self._cumulative_dose_msv: float = 0.0
        self._radiation_shelter_active: bool = False

        # Instrument state
        self._instruments: dict[str, dict[str, Any]] = {
            "spectrometer": {"status": "idle", "power_w": 0.0, "last_obs": ""},
            "radiation_monitor": {"status": "active", "power_w": 5.0, "last_reading": ""},
            "microscope": {"status": "idle", "power_w": 0.0, "last_obs": ""},
        }

        # Science data
        self._observations_count: int = 0
        self._samples_analyzed: int = 0
        self._data_collected_mb: float = 0.0

    async def on_start(self) -> None:
        logger.info("science_agent.started", instruments=len(self._instruments))

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.science.radiation":
            await self._update_radiation(payload)
        elif topic.startswith("aria.sensor.science.spectrometer"):
            await self._update_spectrometer(payload)
        elif topic.startswith("aria.sensor.science.sample"):
            await self._update_sample(payload)
        elif topic == "aria.command.science.observe":
            await self._start_observation(payload, message.correlation_id)
        elif topic == "aria.command.science.analyze":
            await self._analyze_sample(payload, message.correlation_id)
        elif topic == "aria.command.science.radiation_report":
            await self._publish_radiation_report(message.correlation_id)

    async def _update_radiation(self, payload: dict[str, Any]) -> None:
        """Update radiation environment and check crew safety."""
        self._dose_rate_usv_hr = payload.get("dose_rate_usv_hr", self._dose_rate_usv_hr)
        self._cumulative_dose_msv = payload.get("cumulative_dose_msv", self._cumulative_dose_msv)

        # Post to scratchpad for MedicalAgent
        if self._scratchpad:
            self._scratchpad.write("science.radiation", {
                "dose_rate_usv_hr": self._dose_rate_usv_hr,
                "cumulative_dose_msv": self._cumulative_dose_msv,
                "shelter_active": self._radiation_shelter_active,
            }, "science", ttl_s=300)

        # Threshold checks — crew radiation safety
        if self._dose_rate_usv_hr >= DOSE_RATE_CRITICAL_USV_HR:
            await self._raise_alert(
                Severity.EMERGENCY,
                f"RADIATION EMERGENCY: {self._dose_rate_usv_hr:.0f} μSv/hr — "
                "possible solar particle event. Crew to radiation shelter immediately!",
                {"dose_rate_usv_hr": self._dose_rate_usv_hr, "event": "spe"},
            )
            if not self._radiation_shelter_active:
                self._radiation_shelter_active = True
                await self.publish(
                    topic="aria.emergency.radiation.shelter",
                    payload={
                        "actions": ["crew_to_shelter", "reduce_exposure", "alert_ground"],
                        "dose_rate_usv_hr": self._dose_rate_usv_hr,
                    },
                    priority=EventPriority.P0_EMERGENCY,
                )
        elif self._dose_rate_usv_hr >= DOSE_RATE_WARNING_USV_HR:
            await self._raise_alert(
                Severity.WARNING,
                f"Elevated radiation: {self._dose_rate_usv_hr:.0f} μSv/hr — monitor crew exposure",
                {"dose_rate_usv_hr": self._dose_rate_usv_hr},
            )
        elif self._dose_rate_usv_hr >= DOSE_RATE_WATCH_USV_HR:
            await self._raise_alert(
                Severity.WATCH,
                f"Radiation uptick: {self._dose_rate_usv_hr:.0f} μSv/hr",
                {"dose_rate_usv_hr": self._dose_rate_usv_hr},
            )

        # Reset shelter if dose rate drops
        if self._radiation_shelter_active and self._dose_rate_usv_hr < DOSE_RATE_WARNING_USV_HR:
            self._radiation_shelter_active = False
            await self.publish(
                topic="aria.science.radiation.all_clear",
                payload={"dose_rate_usv_hr": self._dose_rate_usv_hr},
            )

        # Cumulative dose career limit check
        if self._cumulative_dose_msv >= CUMULATIVE_DOSE_CRITICAL_MSV:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Cumulative radiation dose: {self._cumulative_dose_msv:.0f} mSv — approaching career limit",
                {"cumulative_dose_msv": self._cumulative_dose_msv},
            )

        # Dsremo ML — catch subtle radiation environment shifts
        score = await self.dsremo_score("science", "radiation", "dose_rate_usv_hr", self._dose_rate_usv_hr)
        if score and score >= 0.65:
            await self._raise_alert(
                Severity[self.dsremo_classify(score)],
                f"[Dsremo] Radiation anomaly: score={score:.2f} — unusual dose rate pattern",
                {"dsremo_score": score, "dose_rate_usv_hr": self._dose_rate_usv_hr},
            )

    async def _update_spectrometer(self, payload: dict[str, Any]) -> None:
        """Update spectrometer instrument state."""
        self._instruments["spectrometer"]["status"] = payload.get("status", "idle")
        if payload.get("observation_complete"):
            self._observations_count += 1
            data_mb = payload.get("data_size_mb", 0.0)
            self._data_collected_mb += data_mb

    async def _update_sample(self, payload: dict[str, Any]) -> None:
        """Update biological sample analysis state."""
        if payload.get("analysis_complete"):
            self._samples_analyzed += 1

    async def _start_observation(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Start a scientific observation campaign.

        Checks power availability via scratchpad before powering on instruments.
        """
        target = payload.get("target", "")
        instrument = payload.get("instrument", "spectrometer")

        # Check power state before starting — don't observe during eclipse/low power
        if self._scratchpad:
            power_state = self._scratchpad.read("power.eclipse_state")
            power_pred = self._scratchpad.read("power.prediction")

            # Defer if in eclipse with low battery
            if power_state and power_state.get("in_eclipse") and power_state.get("battery_soc", 100) < 50:
                await self.publish(
                    topic="aria.science.observation.deferred",
                    payload={
                        "target": target, "instrument": instrument,
                        "reason": "Eclipse with low battery — deferring observation",
                    },
                    correlation_id=correlation_id,
                )
                return

            # Defer if battery depletion predicted within 2 hours
            if power_pred:
                hours_left = power_pred.get("hours_to_depletion")
                if hours_left is not None and hours_left < 2.0:
                    await self.publish(
                        topic="aria.science.observation.deferred",
                        payload={
                            "target": target, "instrument": instrument,
                            "reason": f"Battery depletion in {hours_left:.1f}h — deferring observation",
                        },
                        correlation_id=correlation_id,
                    )
                    return

        if instrument in self._instruments:
            self._instruments[instrument]["status"] = "observing"
            self._instruments[instrument]["last_obs"] = target

        await self.publish(
            topic="aria.science.observation.started",
            payload={"target": target, "instrument": instrument},
            correlation_id=correlation_id,
        )

    async def _analyze_sample(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Trigger GenAstra analysis on a sample."""
        sample_id = payload.get("sample_id", "")
        analysis_type = payload.get("analysis_type", "biosignature")

        # Use GenAstra tools
        if analysis_type == "biosignature":
            result = await self._tools.invoke(
                "genastra_analyze_biosignature",
                {"sample_data": payload.get("data", {}), "target": sample_id},
            )
        elif analysis_type == "radiation_dose":
            result = await self._tools.invoke(
                "genastra_crew_radiation_dose",
                {"crew_member": payload.get("crew_member", ""), "dose_msv": self._cumulative_dose_msv},
            )
        else:
            result = None

        # Check for biosignature detection — trigger discovery protocol
        if analysis_type == "biosignature" and result and result.success and result.data:
            detection = result.data.get("detection", False)
            confidence = result.data.get("confidence", 0.0)
            if detection and confidence > 0.5:
                await self._biosignature_discovery_protocol(sample_id, result.data)

        await self.publish(
            topic="aria.science.analysis.result",
            payload={
                "sample_id": sample_id,
                "analysis_type": analysis_type,
                "result": result.data if result and result.success else None,
                "error": result.error if result and not result.success else None,
            },
            correlation_id=correlation_id,
        )

    async def _biosignature_discovery_protocol(
        self, sample_id: str, analysis_data: dict[str, Any]
    ) -> None:
        """Execute biosignature discovery escalation protocol.

        Per master plan: discoveries are escalated through a formal protocol
        before any announcement — prevents false positive embarrassment.
        """
        confidence = analysis_data.get("confidence", 0.0)

        # Step 1: Log the detection
        logger.warning(
            "science.biosignature_candidate",
            sample_id=sample_id,
            confidence=confidence,
        )

        # Step 2: Publish discovery event for cognitive engine analysis
        await self.publish(
            topic="aria.science.discovery.candidate",
            payload={
                "type": "biosignature",
                "sample_id": sample_id,
                "confidence": confidence,
                "analysis_data": analysis_data,
                "status": "candidate",  # candidate → verified → confirmed
            },
            priority=EventPriority.P1_CRITICAL,
        )

        # Step 3: Alert captain
        await self._raise_alert(
            Severity.WARNING,
            f"BIOSIGNATURE CANDIDATE detected in {sample_id} (confidence={confidence:.0%}). "
            "Verification analysis required before confirmation.",
            {"sample_id": sample_id, "confidence": confidence, "event": "discovery_candidate"},
        )

        # Step 4: Queue immediate data downlink via comms
        await self.publish(
            topic="aria.command.comms.send",
            payload={
                "message_type": "science_data",
                "priority": "HIGH",
                "data": f"BIOSIGNATURE_CANDIDATE sample={sample_id} confidence={confidence:.4f}",
            },
        )

    async def _publish_radiation_report(self, correlation_id: str) -> None:
        """Publish comprehensive radiation environment report."""
        await self.publish(
            topic="aria.science.radiation.report",
            payload={
                "dose_rate_usv_hr": self._dose_rate_usv_hr,
                "cumulative_dose_msv": self._cumulative_dose_msv,
                "shelter_active": self._radiation_shelter_active,
                "dose_rate_status": (
                    "EMERGENCY" if self._dose_rate_usv_hr >= DOSE_RATE_CRITICAL_USV_HR
                    else "WARNING" if self._dose_rate_usv_hr >= DOSE_RATE_WARNING_USV_HR
                    else "WATCH" if self._dose_rate_usv_hr >= DOSE_RATE_WATCH_USV_HR
                    else "NOMINAL"
                ),
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
            topic="aria.anomaly.science",
            payload={
                "severity": severity.name,
                "message": message,
                "subsystem": "science",
                **(details or {}),
            },
            priority=priority,
        )

        # Wiring audit Pass 2 (F2.1) — open a structured Fault for
        # WARNING+ science alerts (radiation hazard, instrument
        # failure, biosignature candidate that needs operator review).
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = (
                "critical"
                if severity in (Severity.CRITICAL, Severity.EMERGENCY)
                else "warning"
            )
            self.report_fault(message, severity=sev_str)

    async def periodic_task(self) -> None:
        """Periodic: radiation assessment, instrument calibration, science data posting."""
        # Check instrument calibration status — schedule if overdue
        for inst_name, inst in self._instruments.items():
            if inst["status"] == "active":
                await self._tools.invoke("learning_calibrate_sensor", {
                    "sensor_id": f"science.{inst_name}",
                    "calibration_type": "span",
                })

        # Radiation environment prediction — use dose rate trend for crew scheduling
        if self._dose_rate_usv_hr > 0 and self._scratchpad:
            # Simple trend: if dose rate is rising, predict when it'll hit WARNING level
            prev_rate = getattr(self, "_prev_dose_rate", self._dose_rate_usv_hr)
            rate_change = self._dose_rate_usv_hr - prev_rate
            self._prev_dose_rate = self._dose_rate_usv_hr

            if rate_change > 5.0:  # Rising rapidly
                hours_to_warning = max(0, (DOSE_RATE_WARNING_USV_HR - self._dose_rate_usv_hr) / rate_change) if rate_change > 0 else float("inf")
                if hours_to_warning < 4.0 and hours_to_warning > 0:
                    await self._raise_alert(
                        Severity.WATCH,
                        f"Radiation rising: may reach WARNING level in {hours_to_warning:.1f}h. "
                        "Consider pre-positioning crew near shelter.",
                        {"hours_to_warning": hours_to_warning, "rate_change": rate_change},
                    )

        # Request radiation assessment from GenAstra
        if self._cumulative_dose_msv > 0:
            result = await self._tools.invoke(
                "genastra_crew_radiation_dose",
                {"dose_msv": self._cumulative_dose_msv, "crew_member": "all"},
            )
            if result.success and result.data:
                logger.debug(
                    "science.radiation_assessment",
                    cumulative_msv=self._cumulative_dose_msv,
                    assessment=result.data,
                )

    @property
    def stats(self) -> dict[str, Any]:
        base = super().stats
        base.update({
            "dose_rate_usv_hr": self._dose_rate_usv_hr,
            "cumulative_dose_msv": self._cumulative_dose_msv,
            "observations": self._observations_count,
            "samples_analyzed": self._samples_analyzed,
            "data_collected_mb": round(self._data_collected_mb, 1),
        })
        return base
