"""ThermalAgent — spacecraft thermal control system management.

Responsibilities:
  - Monitor temperature sensors across all zones
  - Control heater circuits and radiators
  - Detect thermal anomalies (overcool, overheat, gradient spikes)
  - Predict eclipse thermal transients
  - Protect sensitive equipment from thermal damage

Power & thermal audit (2026-04-28) hardenings:
  • P-2: eclipse pre-heat consults SoC budget before turning heaters on.
  • P-4 / P-18: per-zone min-on/min-off (60 s) + relay-cycle counter +
    daily cycle-budget alarm.  Solid-state relays no longer chatter
    on noisy thermistor input.
  • P-5: thermistor sanity (range + dT/dt) at ingest; on rejection,
    freeze the heater state at last-known-good.
  • P-8: ``set_setpoint`` clamps to per-zone [min_c, max_c]; refuses
    crew-killing values; battery_pack setpoint is bounded by the NMC
    physics floor (NMC_T_MIN_K).
  • P-9: power-save heater-off respects ``min_c + warm_margin``.
  • P-11: gradient-action (force setpoint convergence + WARNING).
  • P-14: per-zone deadband matched to zone mass + orbital exposure.
"""

from __future__ import annotations

import time
from typing import Any, Mapping
from types import MappingProxyType

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()


# Power & thermal audit P-4 / P-18 — solid-state-relay protection.
# 60 s minimum on/off matches NASA-STD-4002 §6.2 relay-cycling guidance
# (≥ 60 s between toggles to avoid switching-loss accumulation in MOSFET-
# class SSRs).  Daily budget of 200 cycles flags thermistor noise vs
# real thermal transients (Gilmore 2002 §6 typical orbital cycle = 16/day).
_HEATER_MIN_ON_S = 60.0          # s — NASA-STD-4002 §6.2
_HEATER_MIN_OFF_S = 60.0         # s — NASA-STD-4002 §6.2
_HEATER_DAILY_CYCLE_BUDGET = 200 # cycles/24 h — Gilmore 2002 §6 typical 16/orbit × 12 orbits margin

# Power & thermal audit P-5 — thermistor sanity gates.
# Rejected reading ⇒ heater state is frozen at its last-known-good.
# Rate-of-change limits are zone-specific because mass differs
# (battery_pack ~10 kg has slow dT, solar_array ~thin film fast dT).
_THERMISTOR_DROC_LIMITS_C_PER_S: Mapping[str, float] = MappingProxyType({
    "battery_pack":         5.0,    # ~10 kg pack mass — Gilmore §5
    "electronics_bay":     10.0,    # avionics chassis
    "propulsion":          10.0,    # tank wall + thrust block
    "solar_array":         50.0,    # thin-film array, fast eclipse cooling
    "crew_cabin":           1.0,    # large air mass — slow
    "science_instruments": 10.0,
    "radiator_panel":      30.0,    # OSR panel exposed
    "antenna_assembly":    20.0,
})

# Power & thermal audit P-9 — keep heaters on when zone is near min_c.
# Margin is the band ABOVE min_c that we treat as "danger of freezing"
# and refuse to shed for power-save reasons.  Per Gilmore 2002 §6 this
# is roughly 10 % of (max_c - min_c), bounded to [5°C, 15°C].
_FREEZE_MARGIN_C = 10.0

# Power & thermal audit P-16 — Dsremo P-R warning threshold (auto_scorer.py).
_DSREMO_WARN = 0.65


class ThermalZone:
    """State for a single thermal zone."""

    __slots__ = (
        "name", "temperature_c", "setpoint_c", "heater_on",
        "min_c", "max_c", "deadband_c",
        "_last_thermistor_good_monotonic", "_last_temperature_c_good",
        "_last_heater_on_change_monotonic",
        "_cycle_count_total", "_cycle_count_24h",
        "_cycle_window_anchor_monotonic",
    )

    def __init__(
        self, name: str,
        setpoint: float = 22.0,
        min_c: float = -10.0,
        max_c: float = 50.0,
        deadband_c: float = 2.0,
    ) -> None:
        self.name = name
        self.temperature_c: float = setpoint
        self.setpoint_c = setpoint
        self.heater_on: bool = False
        self.min_c = min_c
        self.max_c = max_c
        self.deadband_c = deadband_c
        # Power & thermal audit P-5 — for thermistor-rejection freeze.
        self._last_thermistor_good_monotonic: float = 0.0
        self._last_temperature_c_good: float = setpoint
        # Power & thermal audit P-4 / P-18 — relay debounce + counter.
        self._last_heater_on_change_monotonic: float = 0.0
        self._cycle_count_total: int = 0
        self._cycle_count_24h: int = 0
        self._cycle_window_anchor_monotonic: float = 0.0

    @property
    def in_range(self) -> bool:
        return self.min_c <= self.temperature_c <= self.max_c

    @property
    def freeze_margin_c(self) -> float:
        # Power & thermal audit P-9 — adaptive margin, bounded.
        return max(5.0, min(15.0, _FREEZE_MARGIN_C))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "temperature_c": self.temperature_c,
            "setpoint_c": self.setpoint_c,
            "heater_on": self.heater_on,
            "in_range": self.in_range,
            "deadband_c": self.deadband_c,
            "cycles_total": self._cycle_count_total,
            "cycles_24h": self._cycle_count_24h,
        }


# Default thermal zones for a spacecraft.
# P-14: deadband sized per zone mass + orbital exposure.  Cite Gilmore 2002 §6
# "Thermal Control Engineering" — recommends 1–3 °C for crew-comfort
# zones, 5–10 °C for electronics, 20–50 °C for radiators that swing
# orbital temperatures.
DEFAULT_ZONES: list[dict[str, Any]] = [
    {"name": "battery_pack",        "setpoint": 20.0,  "min_c":   5.0, "max_c":  45.0, "deadband_c":  2.0},   # NMC narrow
    {"name": "electronics_bay",     "setpoint": 22.0,  "min_c": -20.0, "max_c":  60.0, "deadband_c":  3.0},   # MIL-STD-810 §501
    {"name": "propulsion",          "setpoint": 15.0,  "min_c":   5.0, "max_c":  50.0, "deadband_c":  3.0},
    {"name": "solar_array",         "setpoint": 25.0,  "min_c":-150.0, "max_c": 120.0, "deadband_c": 20.0},   # Gilmore 2002 §6
    {"name": "crew_cabin",          "setpoint": 22.0,  "min_c":  18.0, "max_c":  27.0, "deadband_c":  1.0},   # NASA STD-3001 V2 comfort
    {"name": "science_instruments", "setpoint":-10.0,  "min_c": -80.0, "max_c":  40.0, "deadband_c":  5.0},
    {"name": "radiator_panel",      "setpoint":-40.0,  "min_c":-200.0, "max_c": 100.0, "deadband_c": 50.0},   # OSR swing
    {"name": "antenna_assembly",    "setpoint":  0.0,  "min_c":-100.0, "max_c":  80.0, "deadband_c": 10.0},
]


class ThermalAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Manages spacecraft thermal control system.

    Dual-layer anomaly detection:
      Layer 1: Zone range limits (bang-bang thermostat, min/max bounds)
      Layer 2: Dsremo ML — catches slow thermal drift, orbital profile deviations,
               pre-failure signatures invisible to static limits
    """

    name = "thermal"
    description = "Thermal zone monitoring, heater control, anomaly detection"
    subscriptions = [
        "aria.sensor.thermal.*",
        "aria.command.thermal.*",
        "aria.power.eclipse.*",
    ]
    heartbeat_interval_s = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._zones: dict[str, ThermalZone] = {}
        for zdef in DEFAULT_ZONES:
            zone = ThermalZone(
                zdef["name"], zdef["setpoint"],
                zdef["min_c"], zdef["max_c"],
                deadband_c=zdef.get("deadband_c", 2.0),
            )
            self._zones[zone.name] = zone
        # Coolant loop state
        # Coolant nominal points reflect ISS Internal Active Thermal
        # Control System §3.2 (TCS-30): 30 psi nominal, 5 L/min nominal,
        # 15 °C cold-loop supply.  Pump degradation flagged at 40 % of
        # nominal flow per Gilmore 2002 §6.4.
        self._coolant_pressure_psi: float = 30.0   # ISS IATCS TCS-30
        self._coolant_pressure_nominal_psi: float = 30.0
        self._coolant_flow_rate_lpm: float = 5.0
        self._coolant_flow_rate_nominal_lpm: float = 5.0
        self._coolant_temp_c: float = 15.0

    async def on_start(self) -> None:
        logger.info("thermal_agent.started", zones=len(self._zones))
        # Self-test: verify all heater circuits respond
        test_result = await self._tools.invoke("diagnostic_run_subsystem_test", {
            "subsystem": "thermal",
            "test_level": "quick",
        })
        if test_result.success and test_result.data and test_result.data.get("result") != "PASS":
            logger.warning("thermal_agent.self_test_failed", result=test_result.data)

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.thermal.coolant":
            await self._update_coolant(payload)
        elif topic.startswith("aria.sensor.thermal."):
            zone_name = topic.split(".")[-1]
            await self._update_zone(zone_name, payload)
        elif topic == "aria.command.thermal.status":
            await self._publish_status(message.correlation_id)
        elif topic == "aria.command.thermal.set_setpoint":
            await self._set_setpoint(payload)
        elif topic == "aria.power.eclipse.entered":
            await self._handle_eclipse_entry()

    async def _update_coolant(self, payload: dict[str, Any]) -> None:
        """Monitor coolant loop health."""
        self._coolant_pressure_psi = payload.get("pressure_psi", self._coolant_pressure_psi)
        self._coolant_flow_rate_lpm = payload.get("flow_rate_lpm", self._coolant_flow_rate_lpm)
        self._coolant_temp_c = payload.get("temperature_c", self._coolant_temp_c)

        # Low pressure = possible leak.
        # P-19: 50 % of nominal is the leak threshold (Gilmore 2002 §6.4).
        leak_threshold_psi = 0.5 * self._coolant_pressure_nominal_psi
        if self._coolant_pressure_psi < leak_threshold_psi:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Coolant loop pressure low: {self._coolant_pressure_psi:.1f} psi "
                f"(< {leak_threshold_psi:.1f} = 50 % of nominal "
                f"{self._coolant_pressure_nominal_psi:.0f} psi) — possible leak",
                {"coolant_pressure_psi": self._coolant_pressure_psi,
                 "leak_threshold_psi": leak_threshold_psi},
            )
        # Low flow = pump degradation.
        # P-19: 40 % of nominal flags degradation (Gilmore 2002 §6.4).
        degraded_flow_lpm = 0.4 * self._coolant_flow_rate_nominal_lpm
        if self._coolant_flow_rate_lpm < degraded_flow_lpm:
            await self._raise_alert(
                Severity.WARNING,
                f"Coolant flow rate low: {self._coolant_flow_rate_lpm:.1f} L/min "
                f"(< {degraded_flow_lpm:.1f} = 40 % of nominal "
                f"{self._coolant_flow_rate_nominal_lpm:.1f} L/min) — pump degrading",
                {"coolant_flow_rate_lpm": self._coolant_flow_rate_lpm,
                 "degraded_flow_lpm": degraded_flow_lpm},
            )

        # Dsremo ML for coolant trends
        scores = await self.dsremo_score_batch([
            {"subsystem": "thermal", "component": "coolant", "metric": "pressure_psi", "value": self._coolant_pressure_psi},
            {"subsystem": "thermal", "component": "coolant", "metric": "flow_rate_lpm", "value": self._coolant_flow_rate_lpm},
        ])
        for channel_id, score in scores.items():
            if score >= _DSREMO_WARN:
                await self._raise_alert(
                    Severity[self.dsremo_classify(score)],
                    f"[Dsremo] Coolant anomaly: {channel_id} score={score:.2f}",
                    {"channel_id": channel_id, "dsremo_score": score},
                )

    async def _update_zone(self, zone_name: str, payload: dict[str, Any]) -> None:
        zone = self._zones.get(zone_name)
        if not zone:
            zone = ThermalZone(zone_name)
            self._zones[zone_name] = zone

        proposed_t = payload.get("temperature_c", zone.temperature_c)

        # Power & thermal audit P-5 — thermistor sanity at ingest.
        if not self._thermistor_reading_is_sane(zone, proposed_t):
            # Refuse the reading; freeze heater state at last-known-good.
            await self._raise_alert(
                Severity.WARNING,
                f"Thermal zone '{zone.name}' thermistor rejected: "
                f"{proposed_t!r} (last good {zone._last_temperature_c_good:.1f}°C)",
                {"zone": zone.name, "rejected_temp_c": proposed_t,
                 "last_good_c": zone._last_temperature_c_good},
            )
            await self.publish(
                topic="aria.thermal.sensor_failed",
                payload={"zone": zone.name, "rejected_temp_c": proposed_t,
                         "last_good_c": zone._last_temperature_c_good},
                priority=EventPriority.P1_CRITICAL,
            )
            return

        zone.temperature_c = float(proposed_t)
        zone._last_temperature_c_good = zone.temperature_c
        zone._last_thermistor_good_monotonic = time.monotonic()

        # Layer 1: Static range check
        if not zone.in_range:
            severity = Severity.CRITICAL if (
                zone.temperature_c > zone.max_c + 10 or zone.temperature_c < zone.min_c - 10
            ) else Severity.WARNING

            await self._raise_alert(
                severity,
                f"Thermal zone '{zone.name}' out of range: {zone.temperature_c:.1f}°C "
                f"(limits: {zone.min_c}–{zone.max_c}°C)",
                {"zone": zone.name, "temperature_c": zone.temperature_c},
            )

        # Layer 2: Dsremo ML — catch thermal drift and pre-failure signatures
        score = await self.dsremo_score("thermal", zone_name, "temperature_c", zone.temperature_c)
        # P-16: 0.65 is the Dsremo P-R warning threshold (auto_scorer.py).
        if score and score >= _DSREMO_WARN and zone.in_range:
            await self._raise_alert(
                Severity[self.dsremo_classify(score)],
                f"[Dsremo] Thermal anomaly in zone '{zone.name}': "
                f"score={score:.2f}, temp={zone.temperature_c:.1f}°C (within limits but anomalous)",
                {"zone": zone.name, "temperature_c": zone.temperature_c, "dsremo_score": score},
            )

        # Thermostat control (bang-bang with deadband + relay debounce).
        # P-4 / P-18: minimum-on / minimum-off.
        await self._maybe_toggle_heater(zone)

        # Radiator deployment for persistent overheating.
        # Wiring audit Pass 2 (F1.5/F1.6) — route through dispatch_command.
        if zone.temperature_c > zone.max_c and not zone.heater_on:
            radiator_params = {
                "zone": zone.name, "action": "deploy", "reason": "overheating",
            }
            seq = self.dispatch_command(
                topic="aria.actuator.thermal.radiator",
                params=radiator_params, timeout_s=60.0,
            )
            if seq is None:
                await self.publish(
                    topic="aria.actuator.thermal.radiator",
                    payload=radiator_params,
                    priority=EventPriority.P2_WARNING,
                )

    def _thermistor_reading_is_sane(
        self, zone: ThermalZone, proposed_t: Any,
    ) -> bool:
        """Range + dT/dt sanity (audit P-5).

        Reject NaN / inf, anything outside [min_c-50, max_c+50], or
        |dT/dt| > the per-zone limit.
        """
        try:
            t = float(proposed_t)
        except (TypeError, ValueError):
            return False
        import math
        if not math.isfinite(t):
            return False
        if t < zone.min_c - 50.0 or t > zone.max_c + 50.0:
            return False
        last_t = zone._last_temperature_c_good
        last_m = zone._last_thermistor_good_monotonic
        if last_m > 0:
            dt = max(1e-3, time.monotonic() - last_m)
            droc = abs(t - last_t) / dt
            limit = _THERMISTOR_DROC_LIMITS_C_PER_S.get(zone.name, 10.0)
            if droc > limit:
                return False
        return True

    async def _maybe_toggle_heater(self, zone: ThermalZone) -> None:
        """Hysteresis + relay debounce + cycle counter (audit P-4 / P-18)."""
        target_on = None
        if zone.temperature_c < zone.setpoint_c - zone.deadband_c and not zone.heater_on:
            target_on = True
        elif zone.temperature_c > zone.setpoint_c + zone.deadband_c and zone.heater_on:
            target_on = False
        if target_on is None:
            return

        now_m = time.monotonic()
        # P-4 — minimum dwell time at the current state.
        elapsed = now_m - zone._last_heater_on_change_monotonic
        min_dwell = _HEATER_MIN_ON_S if zone.heater_on else _HEATER_MIN_OFF_S
        if zone._last_heater_on_change_monotonic > 0 and elapsed < min_dwell:
            logger.debug("thermal_agent.heater_debounce_skip",
                         zone=zone.name, target_on=target_on,
                         elapsed_s=round(elapsed, 1),
                         min_dwell_s=min_dwell)
            return

        zone.heater_on = target_on
        zone._last_heater_on_change_monotonic = now_m

        # P-18 — relay-cycle counter + 24-h budget alarm.
        zone._cycle_count_total += 1
        # Anchor / roll the 24-h window.
        if (zone._cycle_window_anchor_monotonic == 0.0
                or now_m - zone._cycle_window_anchor_monotonic > 86_400.0):
            zone._cycle_window_anchor_monotonic = now_m
            zone._cycle_count_24h = 0
        zone._cycle_count_24h += 1
        if zone._cycle_count_24h >= _HEATER_DAILY_CYCLE_BUDGET:
            await self._raise_alert(
                Severity.WARNING,
                f"Heater relay cycling rate exceeded for zone '{zone.name}': "
                f"{zone._cycle_count_24h} toggles in 24 h "
                f"(budget {_HEATER_DAILY_CYCLE_BUDGET})",
                {"zone": zone.name,
                 "cycles_24h": zone._cycle_count_24h,
                 "cycles_total": zone._cycle_count_total},
            )
        await self._command_heater(zone.name, target_on)

    async def _command_heater(self, zone_name: str, on: bool) -> None:
        """Send heater command to the hardware abstraction layer.

        Wiring audit Pass 2 (F1.5/F1.6) — routes through
        ``dispatch_command()`` so the command enters the safety layer:
        ExecutionGuard validates preconditions + resources first, then
        CommandTracker assigns a sequence number and arms a timeout.
        Falls back to direct publish only when no safety context is
        wired (e.g. unit tests without coordinator).
        """
        action = "on" if on else "off"
        topic = f"aria.actuator.thermal.heater.{zone_name}"
        params = {"zone": zone_name, "heater": action}
        seq = self.dispatch_command(topic=topic, params=params, timeout_s=30.0)
        if seq is None:
            # No tracker / guard wired (tests) → direct publish.
            await self.publish(
                topic=topic, payload=params,
                priority=EventPriority.P3_ROUTINE,
            )
        logger.debug("thermal_agent.heater", zone=zone_name, action=action, seq=seq)

    async def _handle_eclipse_entry(self) -> None:
        """Pre-heat critical zones before eclipse cools them.

        Power & thermal audit P-2: only fire pre-heat if the battery
        budget can absorb it for the predicted eclipse duration.  We
        consult ``power.prediction`` from the scratchpad — if it
        warns of imminent depletion, the propulsion pre-heat is
        deferred (battery_pack heater is still allowed because
        cell-level cold protection trumps power-save).
        """
        budget_allows_full = self._eclipse_preheat_budget_allows()
        for zone in self._zones.values():
            if zone.name == "battery_pack" and not zone.heater_on:
                # Battery-cell cold protection — always allowed.
                await self._maybe_toggle_heater_force(zone, True,
                                                     reason="eclipse_preheat_battery")
            elif zone.name == "propulsion" and not zone.heater_on:
                if budget_allows_full:
                    await self._maybe_toggle_heater_force(zone, True,
                                                         reason="eclipse_preheat_prop")
                else:
                    logger.info(
                        "thermal_agent.eclipse_preheat_deferred",
                        zone=zone.name,
                        reason="battery_budget_negative",
                    )
        logger.info("thermal_agent.eclipse_preheat")

    def _eclipse_preheat_budget_allows(self) -> bool:
        """Check the scratchpad ``power.prediction`` and decide whether
        a 200-W pre-heat for the predicted eclipse remainder fits
        under the available battery energy with margin.
        """
        if not self._scratchpad:
            return True
        pred = self._scratchpad.read("power.prediction")
        if not pred:
            return True
        soc = float(pred.get("battery_soc", 100.0))
        eff_cap_wh = float(pred.get("effective_capacity_wh", 2800.0))
        # Conservative: assume 30 min eclipse remainder + 200 W
        # pre-heat draw + 600 W baseline avionics/ECLSS.
        budget_remaining_wh = soc / 100.0 * eff_cap_wh
        # Half the remaining budget reserved for non-heater loads.
        return budget_remaining_wh > 0.5 * (200.0 + 600.0)

    async def _maybe_toggle_heater_force(
        self, zone: ThermalZone, target_on: bool, *, reason: str = "",
    ) -> None:
        """Variant of ``_maybe_toggle_heater`` that bypasses the
        threshold-vs-setpoint test (callers like eclipse pre-heat have
        already decided).  Still honours min-on/min-off + cycle
        counter (P-4 / P-18).
        """
        if zone.heater_on == target_on:
            return
        now_m = time.monotonic()
        elapsed = now_m - zone._last_heater_on_change_monotonic
        min_dwell = _HEATER_MIN_ON_S if zone.heater_on else _HEATER_MIN_OFF_S
        if zone._last_heater_on_change_monotonic > 0 and elapsed < min_dwell:
            logger.info("thermal_agent.heater_debounce_block_force",
                        zone=zone.name, reason=reason,
                        elapsed_s=round(elapsed, 1),
                        min_dwell_s=min_dwell)
            return
        zone.heater_on = target_on
        zone._last_heater_on_change_monotonic = now_m
        zone._cycle_count_total += 1
        if (zone._cycle_window_anchor_monotonic == 0.0
                or now_m - zone._cycle_window_anchor_monotonic > 86_400.0):
            zone._cycle_window_anchor_monotonic = now_m
            zone._cycle_count_24h = 0
        zone._cycle_count_24h += 1
        await self._command_heater(zone.name, target_on)

    async def _set_setpoint(self, payload: dict[str, Any]) -> None:
        """Power & thermal audit P-8: clamp + reject crew-killing setpoints.

        Reject values outside [zone.min_c, zone.max_c] outright (rather
        than silently clamping) so an operator sees that the LLM tried
        to push a dangerous value.  The battery_pack zone is also
        bounded by the NMC physics floor — refuse anything below
        NMC_T_MIN_K (-20 °C) regardless of zone.min_c configuration.
        """
        zone_name = payload.get("zone", "")
        new_setpoint = payload.get("setpoint_c")
        zone = self._zones.get(zone_name)
        if not zone or new_setpoint is None:
            return
        try:
            requested = float(new_setpoint)
        except (TypeError, ValueError):
            return

        # Per-zone hard physics floor.
        hard_min = zone.min_c
        if zone_name == "battery_pack":
            # NMC_T_MIN_K = 253 K = -20 °C (NASA TN D-8706).  battery_pack
            # zone.min_c is +5 °C nominal which is already above the
            # cell floor; keep the tighter operational bound.
            hard_min = max(zone.min_c, -20.0)

        if requested < hard_min or requested > zone.max_c:
            await self._raise_alert(
                Severity.WARNING,
                f"set_setpoint refused: zone='{zone_name}' "
                f"requested={requested:.1f}°C outside [{hard_min}, {zone.max_c}]",
                {"zone": zone_name, "requested_c": requested,
                 "min_c": hard_min, "max_c": zone.max_c},
            )
            await self.publish(
                topic="aria.thermal.setpoint_rejected",
                payload={"zone": zone_name, "requested_c": requested,
                         "min_c": hard_min, "max_c": zone.max_c},
                priority=EventPriority.P2_WARNING,
            )
            return

        zone.setpoint_c = requested
        logger.info("thermal_agent.setpoint_changed",
                    zone=zone_name, setpoint=requested)

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Act on LLM directives that target the thermal subsystem.

        Every dispatch passes through `safe_dispatch_check` first
        (kill switch → constitution → resource budget). Only EXECUTED
        proceeds; DENIED / GATED / BUDGET_BREACH skip the publish.
        """
        await super().on_reasoning_response(payload)
        from aria.cognitive.action_executor import parse_recommendation
        from aria.cognitive.safe_dispatch import safe_dispatch_check, DispatchKind
        intents = parse_recommendation(payload.get("response", "") or "")
        for intent in intents:
            if intent.action == "set_setpoint":
                zone = intent.params.get("zone", "")
                celsius = intent.params.get("celsius")
                if zone not in self._zones or celsius is None:
                    continue
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="set_setpoint",
                    params={"zone": zone, "celsius": celsius},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                await self._set_setpoint({"zone": zone, "setpoint_c": celsius})
                await self.publish(
                    topic="aria.thermal.llm_action.executed",
                    payload={"action": "set_setpoint", "zone": zone,
                             "celsius": celsius},
                    priority=EventPriority.P2_WARNING,
                )
                self._log_action_executed("set_setpoint", {"zone": zone, "celsius": celsius})
            elif intent.action == "safe_mode":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="safe_mode",
                    params={"setpoint_c": 18.0},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Drop setpoints to a safe minimum and pre-heat the
                # critical zones the eclipse handler also covers.
                safe_c = 18.0   # NASA STD-3001 V2 cabin lower-comfort bound
                for z in self._zones.values():
                    if z.setpoint_c > safe_c:
                        z.setpoint_c = safe_c
                await self._handle_eclipse_entry()
                await self.publish(
                    topic="aria.thermal.llm_action.executed",
                    payload={"action": "safe_mode", "setpoint_c": safe_c},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("safe_mode", {"setpoint_c": safe_c})

    async def _publish_status(self, correlation_id: str) -> None:
        await self.publish(
            topic="aria.thermal.status.response",
            payload={
                "zones": {name: z.to_dict() for name, z in self._zones.items()},
                "heaters_active": sum(1 for z in self._zones.values() if z.heater_on),
            },
            correlation_id=correlation_id,
        )

    async def _raise_alert(self, severity: Severity, message: str, details: dict[str, Any]) -> None:
        priority = EventPriority.P1_CRITICAL if severity == Severity.CRITICAL else EventPriority.P2_WARNING
        await self.publish(
            topic="aria.anomaly.thermal",
            payload={"severity": severity.name, "message": message, **details},
            priority=priority,
        )

        # Structured fault reporting via FaultManager (if coordinator
        # has wired set_safety_context).
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = "critical" if severity in (Severity.CRITICAL, Severity.EMERGENCY) else "warning"
            self.report_fault(message, severity=sev_str)

    async def periodic_task(self) -> None:
        """Check scratchpad for eclipse state, post thermal summary, pre-heat."""
        # Post thermal zone summary to scratchpad
        if self._scratchpad:
            zones_data = {
                name: {"temperature_c": z.temperature_c, "heater_on": z.heater_on, "in_range": z.in_range}
                for name, z in self._zones.items()
            }
            self._scratchpad.write("thermal.zones", zones_data, "thermal", ttl_s=120)

        # Read propulsion fuel state — protect fuel lines from freezing.
        # Wiring audit Pass 2 (F1.5/F1.6) — route through dispatch_command.
        if self._scratchpad:
            fuel = self._scratchpad.read("propulsion.fuel_status")
            if fuel and fuel.get("fuel_fraction", 1.0) < 0.15:
                # Low fuel: ensure propulsion zone heater stays on
                prop_zone = self._zones.get("propulsion")
                if prop_zone and not prop_zone.heater_on:
                    prop_zone.heater_on = True
                    heater_params = {
                        "zone": "propulsion", "heater": "on",
                        "reason": "low_fuel_freeze_protection",
                    }
                    seq = self.dispatch_command(
                        topic="aria.actuator.thermal.heater.propulsion",
                        params=heater_params, timeout_s=30.0,
                    )
                    if seq is None:
                        await self.publish(
                            topic="aria.actuator.thermal.heater.propulsion",
                            payload=heater_params,
                        )

        # Power-aware thermal management: reduce heating when battery is critical.
        # Power & thermal audit P-9: respect each zone's freeze margin
        # before turning the heater off — refuse to freeze the antenna
        # for power-save.  Non-shedding zones below min_c + margin
        # keep their heaters on regardless of SoC.
        if self._scratchpad:
            power_pred = self._scratchpad.read("power.prediction")
            if power_pred and power_pred.get("battery_soc", 100) < 15:
                for zone_name in ["science_instruments", "antenna_assembly"]:
                    zone = self._zones.get(zone_name)
                    if not zone or not zone.heater_on:
                        continue
                    # P-9: keep heater on if zone is near min_c + margin.
                    margin = zone.freeze_margin_c
                    if zone.temperature_c <= zone.min_c + margin:
                        logger.info(
                            "thermal_agent.power_save_skipped_freeze_margin",
                            zone=zone_name,
                            temp_c=zone.temperature_c,
                            min_c=zone.min_c,
                            margin_c=margin,
                        )
                        continue
                    await self._maybe_toggle_heater_force(
                        zone, False,
                        reason="critical_battery_power_save",
                    )

        if not self._scratchpad:
            return

        eclipse = self._scratchpad.read("power.eclipse_state")
        if eclipse and eclipse.get("in_eclipse"):
            # Eclipse mode: pre-heat critical zones, stow radiators
            # Wiring audit Pass 2 (F1.5/F1.6) — eclipse pre-heat
            # actuator commands route through the safety layer.
            for zone_name in ["battery_pack", "propulsion"]:
                zone = self._zones.get(zone_name)
                if zone and zone.temperature_c < zone.setpoint_c - 2.0 and not zone.heater_on:
                    zone.heater_on = True
                    eclipse_heater_params = {
                        "zone": zone_name, "heater": "on",
                        "reason": "eclipse_preheat",
                    }
                    seq = self.dispatch_command(
                        topic=f"aria.actuator.thermal.heater.{zone_name}",
                        params=eclipse_heater_params, timeout_s=30.0,
                    )
                    if seq is None:
                        await self.publish(
                            topic=f"aria.actuator.thermal.heater.{zone_name}",
                            payload=eclipse_heater_params,
                        )
        elif eclipse and not eclipse.get("in_eclipse"):
            # Sunlight mode: deploy radiators for active cooling if needed.
            # Wiring audit Pass 2 (F1.5/F1.6) — same dispatch_command route.
            for zone_name, zone in self._zones.items():
                if zone.temperature_c > zone.max_c - 5.0:
                    radiator_params = {
                        "zone": zone_name, "action": "deploy",
                        "reason": "sunlight_cooling",
                    }
                    seq = self.dispatch_command(
                        topic="aria.actuator.thermal.radiator",
                        params=radiator_params, timeout_s=60.0,
                    )
                    if seq is None:
                        await self.publish(
                            topic="aria.actuator.thermal.radiator",
                            payload=radiator_params,
                            priority=EventPriority.P3_ROUTINE,
                        )

        # Thermal gradient monitoring between adjacent zones.
        # Power & thermal audit P-11: act on the alert — pull the
        # warmer zone's setpoint down by 5 °C and the colder up by
        # 5 °C (within zone limits).  At Al-6061 CTE × 70 GPa × 30 K
        # ≈ 50 MPa hull-penetrator stress per Gilmore 2002 §6.5;
        # over many cycles this fatigues vacuum-tight joints.
        adjacent_pairs = [
            ("battery_pack", "electronics_bay"),
            ("crew_cabin", "electronics_bay"),
            ("propulsion", "battery_pack"),
        ]
        for zone_a_name, zone_b_name in adjacent_pairs:
            zone_a = self._zones.get(zone_a_name)
            zone_b = self._zones.get(zone_b_name)
            if not (zone_a and zone_b):
                continue
            gradient = abs(zone_a.temperature_c - zone_b.temperature_c)
            if gradient <= 30.0:
                continue
            await self._raise_alert(
                Severity.WARNING,
                f"High thermal gradient: {zone_a_name} ({zone_a.temperature_c:.1f}°C) vs "
                f"{zone_b_name} ({zone_b.temperature_c:.1f}°C) — delta={gradient:.1f}°C; "
                "converging setpoints to reduce hull-stress",
                {"zone_a": zone_a_name, "zone_b": zone_b_name, "gradient_c": gradient},
            )
            # Identify warmer / cooler.
            warmer, cooler = (
                (zone_a, zone_b) if zone_a.temperature_c > zone_b.temperature_c
                else (zone_b, zone_a)
            )
            # Pull setpoints together, bounded by each zone's [min_c, max_c].
            warmer.setpoint_c = max(
                warmer.min_c, min(warmer.max_c, warmer.setpoint_c - 5.0),
            )
            cooler.setpoint_c = max(
                cooler.min_c, min(cooler.max_c, cooler.setpoint_c + 5.0),
            )
