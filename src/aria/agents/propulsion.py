"""PropulsionAgent — thruster management and maneuver execution.

Responsibilities:
  - Monitor propellant levels, tank pressure, thruster health
  - Execute approved maneuver plans (from NavigationAgent via DecisionEngine)
  - Track delta-V budget and fuel margins
  - Detect thruster faults (stuck-on, stuck-off, underperformance)
  - Emergency collision avoidance burns (Level 0 authority)

Sensor topics:
  - aria.sensor.propulsion.tank: pressure_psi, temperature_c, propellant_kg
  - aria.sensor.propulsion.thruster.*: chamber_pressure_psi, temperature_c, valve_state
  - aria.command.propulsion.*: fire_thruster, plan_burn, abort

Integration:
  - Receives maneuver plans from NavigationAgent
  - Routes through DecisionEngine for captain approval (IRREVERSIBLE)
  - Reports fuel status to coordinator for mission planning
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

# Thruster configuration
DEFAULT_ISP_S = 220.0  # Specific impulse (hydrazine-class)
G0 = 9.80665  # Standard gravity m/s^2
# Default maximum thrust for the commanding-path surrogate. Matches
# the Aerojet Rocketdyne MR-107T 22 N monopropellant hydrazine
# thruster class (MIL-STD datasheet, 2021 product catalog). The
# mass flow rate derives from the rocket equation:
#     m_dot = F / (Isp · g₀)
DEFAULT_MAX_THRUST_N = 22.0


class PropulsionAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Manages propulsion subsystem — thrusters, fuel, and maneuver execution.

    Dual-layer anomaly detection:
      Layer 1: Threshold rules — low fuel, high chamber pressure, stuck valve
      Layer 2: Dsremo ML — subtle leak detection, thruster degradation trends
    """

    name = "propulsion"
    description = "Thruster management, maneuver execution, fuel budget tracking"
    subscriptions = [
        "aria.sensor.propulsion.*",
        "aria.command.propulsion.*",
        "aria.nav.maneuver.execute",
    ]
    heartbeat_interval_s = 15.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Tank state
        self._propellant_kg: float = 100.0
        self._initial_propellant_kg: float = 100.0
        self._tank_pressure_psi: float = 250.0
        self._tank_temperature_c: float = 20.0

        # Thruster state
        self._thrusters: dict[str, dict[str, Any]] = {
            f"thruster_{i}": {
                "chamber_pressure_psi": 0.0,
                "temperature_c": 20.0,
                "valve_state": "closed",
                "total_fire_time_s": 0.0,
                "fire_count": 0,
                "healthy": True,
            }
            for i in range(1, 5)  # 4 thrusters
        }

        # Delta-V tracking
        self._delta_v_used_ms: float = 0.0
        self._delta_v_budget_ms: float = 200.0
        self._spacecraft_mass_kg: float = 5000.0

        # Delta-V efficiency tracking
        self._total_fuel_used_kg: float = 0.0
        self._theoretical_dv_ms: float = 0.0  # What we should have got from fuel used

        # Active maneuver
        self._active_maneuver: dict[str, Any] | None = None
        self._maneuver_history: list[dict[str, Any]] = []
        # Fuel consumption rate tracking
        self._prev_propellant_kg: float = self._propellant_kg

        # Wiring audit Pass 2 (F5.3) — persist fuel-budget bookkeeping
        # so a process bounce does not silently reset
        # ``_delta_v_used_ms`` to 0 and reopen the entire mission Δv
        # budget. Mirror PowerAgent's P-23 atomic-write pattern + the
        # ``ARIA_RUNTIME_DIR`` override so tests can use a temporary
        # location.
        import os as _os
        from pathlib import Path as _Path
        env = _os.environ.get("ARIA_RUNTIME_DIR")
        base = (
            _Path(env) if env
            else _Path(__file__).resolve().parents[3] / "data" / "runtime"
        )
        self._state_path: _Path = base / "propulsion_agent.json"
        self._load_persistent_state()

    def _load_persistent_state(self) -> None:
        try:
            if not self._state_path.is_file():
                return
            import json as _json
            data = _json.loads(self._state_path.read_text(encoding="utf-8"))
            self._propellant_kg = float(data.get("propellant_kg", self._propellant_kg))
            self._delta_v_used_ms = float(data.get("delta_v_used_ms", 0.0))
            self._total_fuel_used_kg = float(data.get("total_fuel_used_kg", 0.0))
            self._theoretical_dv_ms = float(data.get("theoretical_dv_ms", 0.0))
            for thruster_id, thruster_state in data.get("thrusters", {}).items():
                if thruster_id in self._thrusters:
                    self._thrusters[thruster_id]["fire_count"] = int(
                        thruster_state.get("fire_count", 0)
                    )
                    self._thrusters[thruster_id]["total_fire_time_s"] = float(
                        thruster_state.get("total_fire_time_s", 0.0)
                    )
        except Exception as exc:    # noqa: BLE001
            logger.warning("propulsion_agent.state_load_failed", error=str(exc))

    def _save_persistent_state(self) -> None:
        import json as _json
        import os as _os
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            payload = {
                "schema_version": 1,
                "propellant_kg": self._propellant_kg,
                "delta_v_used_ms": self._delta_v_used_ms,
                "total_fuel_used_kg": self._total_fuel_used_kg,
                "theoretical_dv_ms": self._theoretical_dv_ms,
                "thrusters": {
                    thruster_id: {
                        "fire_count": int(thruster["fire_count"]),
                        "total_fire_time_s": float(thruster["total_fire_time_s"]),
                    }
                    for thruster_id, thruster in self._thrusters.items()
                },
            }
            with open(tmp, "w", encoding="utf-8") as fp:
                _json.dump(payload, fp)
                fp.flush()
                try:
                    _os.fsync(fp.fileno())
                except OSError:
                    pass
            _os.replace(tmp, self._state_path)
        except OSError as exc:
            logger.error("propulsion_agent.state_save_failed", error=str(exc))

    async def on_start(self) -> None:
        logger.info(
            "propulsion_agent.started",
            propellant_kg=self._propellant_kg,
            thrusters=len(self._thrusters),
        )
        # Pre-flight valve test: verify all thruster valves respond
        test_result = await self._tools.invoke("diagnostic_run_subsystem_test", {
            "subsystem": "propulsion",
            "test_level": "quick",
        })
        if test_result.success and test_result.data and test_result.data.get("result") != "PASS":
            logger.warning("propulsion_agent.self_test_failed", result=test_result.data)

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.propulsion.tank":
            await self._update_tank(payload)
        elif topic.startswith("aria.sensor.propulsion.thruster"):
            thruster_id = topic.split(".")[-1]
            await self._update_thruster(thruster_id, payload)
        elif topic == "aria.command.propulsion.fire_thruster":
            await self._fire_thruster(payload, message.correlation_id)
        elif topic == "aria.command.propulsion.abort":
            await self._abort_maneuver(payload)
        elif topic == "aria.nav.maneuver.execute":
            await self._execute_maneuver(payload, message.correlation_id)

    async def _update_tank(self, payload: dict[str, Any]) -> None:
        """Update propellant tank state."""
        self._prev_propellant_kg = self._propellant_kg
        self._propellant_kg = payload.get("propellant_kg", self._propellant_kg)
        self._tank_pressure_psi = payload.get("pressure_psi", self._tank_pressure_psi)
        self._tank_temperature_c = payload.get("temperature_c", self._tank_temperature_c)

        # Unexpected fuel consumption (no active maneuver but fuel dropping)
        # Only alert on small unexpected drops (not initial readings which may differ greatly)
        fuel_drop = self._prev_propellant_kg - self._propellant_kg
        if 0.1 < fuel_drop < 5.0 and self._active_maneuver is None:
            await self._raise_alert(
                Severity.WARNING,
                f"Unexpected fuel loss: {fuel_drop:.2f} kg without active maneuver — possible leak",
                {"fuel_drop_kg": fuel_drop, "event": "unexpected_consumption"},
            )

        # Threshold checks
        fuel_fraction = self._propellant_kg / max(self._initial_propellant_kg, 1.0)

        if fuel_fraction < 0.05:
            await self._raise_alert(
                Severity.EMERGENCY,
                f"Propellant critically low: {self._propellant_kg:.1f} kg ({fuel_fraction:.0%})",
                {"propellant_kg": self._propellant_kg, "fraction": fuel_fraction},
            )
        elif fuel_fraction < 0.15:
            await self._raise_alert(
                Severity.WARNING,
                f"Propellant low: {self._propellant_kg:.1f} kg ({fuel_fraction:.0%})",
                {"propellant_kg": self._propellant_kg, "fraction": fuel_fraction},
            )

        if self._tank_pressure_psi < 50.0:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Tank pressure critically low: {self._tank_pressure_psi:.1f} psi",
                {"tank_pressure_psi": self._tank_pressure_psi},
            )

        # Dsremo ML scoring
        scores = await self.dsremo_score_batch([
            {"subsystem": "propulsion", "component": "tank", "metric": "propellant_kg", "value": self._propellant_kg},
            {"subsystem": "propulsion", "component": "tank", "metric": "pressure_psi", "value": self._tank_pressure_psi},
            {"subsystem": "propulsion", "component": "tank", "metric": "temperature_c", "value": self._tank_temperature_c},
        ])
        for channel_id, score in scores.items():
            if score >= 0.65:
                await self._raise_alert(
                    Severity[self.dsremo_classify(score)],
                    f"[Dsremo] Propulsion tank anomaly: {channel_id} score={score:.2f}",
                    {"channel_id": channel_id, "dsremo_score": score},
                )

    async def _update_thruster(self, thruster_id: str, payload: dict[str, Any]) -> None:
        """Update thruster state and check for faults."""
        if thruster_id not in self._thrusters:
            self._thrusters[thruster_id] = {
                "chamber_pressure_psi": 0.0, "temperature_c": 20.0,
                "valve_state": "closed", "total_fire_time_s": 0.0,
                "fire_count": 0, "healthy": True,
            }

        thruster = self._thrusters[thruster_id]
        thruster["chamber_pressure_psi"] = payload.get("chamber_pressure_psi", 0.0)
        thruster["temperature_c"] = payload.get("temperature_c", thruster["temperature_c"])
        thruster["valve_state"] = payload.get("valve_state", thruster["valve_state"])

        # Stuck-on detection: valve open but no commanded fire
        if thruster["valve_state"] == "open" and self._active_maneuver is None:
            thruster["healthy"] = False
            await self._raise_alert(
                Severity.EMERGENCY,
                f"Thruster {thruster_id} valve stuck OPEN — no active maneuver!",
                {"thruster_id": thruster_id, "valve_state": "open"},
            )

        # Dsremo ML scoring for thruster health trends
        score = await self.dsremo_score(
            "propulsion", thruster_id, "chamber_pressure_psi", thruster["chamber_pressure_psi"]
        )
        if score and score >= 0.65:
            await self._raise_alert(
                Severity[self.dsremo_classify(score)],
                f"[Dsremo] Thruster {thruster_id} anomaly: score={score:.2f}",
                {"thruster_id": thruster_id, "dsremo_score": score},
            )

        # Over-temperature
        if thruster["temperature_c"] > 300.0:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Thruster {thruster_id} over-temperature: {thruster['temperature_c']:.0f}C",
                {"thruster_id": thruster_id, "temperature_c": thruster["temperature_c"]},
            )

    async def _fire_thruster(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Execute a thruster firing command."""
        thruster_id = payload.get("thruster_id", "")
        duration_ms = payload.get("duration_ms", 0)
        thrust_pct = payload.get("thrust_level_pct", 100.0)

        if thruster_id not in self._thrusters:
            return

        thruster = self._thrusters[thruster_id]
        if not thruster["healthy"]:
            await self.publish(
                topic="aria.propulsion.fire.response",
                payload={"success": False, "error": f"Thruster {thruster_id} unhealthy"},
                correlation_id=correlation_id,
            )
            return

        # Wiring audit Pass 2 (F2.2) — consult the inrush guard before
        # firing. An ion arc-jet ignition / cold-gas pulse during a
        # low-SoC eclipse can drag the bus below cutoff; the guard
        # encapsulates the SoC + bus-voltage check the documentation
        # advertises but only comms.HGA was actually using.
        try:
            from aria.agents.inrush_guard import check_burst_allowed
            pred = (
                self._scratchpad.read("power.prediction")
                if self._scratchpad else None
            )
            # Steady-state thruster-electronics current draw — solenoid
            # valve drivers + igniter at peak. The default MR-107T-class
            # 22 N hydrazine thruster's electrical interface draws about
            # 30 W during a fire (Aerojet Rocketdyne MR-107T data sheet,
            # 2019).  An ion arc-jet would override this via payload.
            burst_w = float(payload.get("burst_steady_state_w", 30.0))
            bus_v = (pred or {}).get("bus_voltage_v", 28.0) or 28.0
            burst_verdict = check_burst_allowed(
                burst_steady_state_w=burst_w,
                bus_voltage_v=float(bus_v),
                power_prediction=pred,
            )
        except (ImportError, AttributeError, TypeError) as exc:
            logger.warning(
                "propulsion.inrush_guard_unavailable",
                thruster=thruster_id, error=str(exc),
            )
            burst_verdict = None

        if burst_verdict is not None and not burst_verdict.allowed:
            await self.publish(
                topic="aria.propulsion.fire.response",
                payload={
                    "success": False,
                    "error": f"inrush_guard refused: {burst_verdict.reason}",
                    "thruster_id": thruster_id,
                },
                correlation_id=correlation_id,
            )
            await self._raise_alert(
                Severity.WARNING,
                f"Thruster {thruster_id} firing refused by inrush guard: "
                f"{burst_verdict.reason}",
                {"thruster_id": thruster_id, "reason": burst_verdict.reason},
            )
            return

        # Record firing + check for ISP degradation
        duration_s = duration_ms / 1000.0
        thruster["fire_count"] += 1
        thruster["total_fire_time_s"] += duration_s

        # ISP degradation warning: thrusters with >100 firings may lose efficiency
        if thruster["fire_count"] > 100:
            degradation_pct = min(thruster["fire_count"] / 1000 * 5, 15)  # Up to 15% loss
            logger.info(
                "propulsion.isp_degradation_estimate",
                thruster=thruster_id,
                fire_count=thruster["fire_count"],
                estimated_degradation_pct=round(degradation_pct, 1),
            )

        # Mass flow rate from the rocket equation
        #     m_dot = F / (Isp · g₀)
        # scaled by thrust percentage. For the default
        # MR-107T-class 22 N thruster at 220 s Isp and 100 %
        # throttle this gives ~0.0102 kg/s — the old hard-coded
        # placeholder was within 2 % of the correct value.
        thrust_fraction = thrust_pct / 100.0
        mass_flow_rate = (
            DEFAULT_MAX_THRUST_N * thrust_fraction / (DEFAULT_ISP_S * G0)
        )
        fuel_used = mass_flow_rate * duration_s
        if fuel_used > self._propellant_kg:
            fuel_used = self._propellant_kg

        self._propellant_kg -= fuel_used
        self._total_fuel_used_kg += fuel_used
        dv = DEFAULT_ISP_S * G0 * math.log(
            self._spacecraft_mass_kg / (self._spacecraft_mass_kg - fuel_used)
        ) if fuel_used > 0 else 0.0
        self._delta_v_used_ms += dv
        self._theoretical_dv_ms += dv  # Track for efficiency comparison

        # Wiring audit Pass 2 (F7.7) — commit the real-rocket-equation
        # Δv to the external budget gate at the moment fuel is
        # actually consumed. The schedule_maneuver LLM intent path
        # used to commit the *intended* Δv before the burn, which
        # opened a slow-drain attack via repeated plan_burn publishes
        # to a topic with no subscriber.
        if dv > 0:
            try:
                from aria.safety.resource_budget import get_budget_gate
                get_budget_gate().commit("delta_v_mps", dv)
            except Exception as exc:    # noqa: BLE001
                logger.warning(
                    "propulsion.budget_commit_failed",
                    thruster=thruster_id, dv=dv, error=str(exc),
                )

        # Wiring audit Pass 2 (F5.3) — persist fuel-budget bookkeeping.
        self._save_persistent_state()

        await self.publish(
            topic="aria.propulsion.fire.response",
            payload={
                "success": True,
                "thruster_id": thruster_id,
                "duration_ms": duration_ms,
                "delta_v_ms": round(dv, 4),
                "fuel_used_kg": round(fuel_used, 4),
                "remaining_propellant_kg": round(self._propellant_kg, 2),
            },
            correlation_id=correlation_id,
        )

        logger.info(
            "propulsion.thruster_fired",
            thruster=thruster_id,
            duration_ms=duration_ms,
            dv_ms=round(dv, 4),
            fuel_remaining_kg=round(self._propellant_kg, 2),
        )

    async def _execute_maneuver(self, payload: dict[str, Any], correlation_id: str) -> None:
        """Execute a maneuver plan received from NavigationAgent.

        Checks power availability before firing — don't burn during low-power eclipse.
        """
        maneuver_id = payload.get("maneuver_id", "unknown")

        # Check power state before executing burn
        if self._scratchpad:
            power_pred = self._scratchpad.read("power.prediction")
            if power_pred:
                hours_left = power_pred.get("hours_to_depletion")
                if hours_left is not None and hours_left < 1.0:
                    await self._raise_alert(
                        Severity.WARNING,
                        f"Deferring maneuver {maneuver_id}: battery depletion in {hours_left:.1f}h",
                        {"maneuver_id": maneuver_id, "hours_to_depletion": hours_left},
                    )
                    await self.publish(
                        topic="aria.propulsion.maneuver.deferred",
                        payload={"maneuver_id": maneuver_id, "reason": "low_power"},
                        correlation_id=correlation_id,
                    )
                    return

        self._active_maneuver = payload

        await self.publish(
            topic="aria.propulsion.maneuver.started",
            payload={"maneuver_id": maneuver_id, "plan": payload},
        )

        # Simulate executing each burn in the plan
        burns = payload.get("burns", [])
        for burn in burns:
            await self._fire_thruster(burn, correlation_id)

        self._maneuver_history.append(payload)
        # Prune old maneuvers to prevent unbounded growth over multi-year missions
        if len(self._maneuver_history) > 200:
            self._maneuver_history = self._maneuver_history[-100:]
        self._active_maneuver = None

        # Post-maneuver verification: check conjunction Pc decreased
        event_id = payload.get("event_id", "")
        if event_id:
            pc_result = await self._tools.invoke("conjwatch_compute_pc", {
                "event_id": event_id,
                "methods": ["FOSTER", "CHAN"],
            })
            post_pc = None
            if pc_result.success and pc_result.data:
                post_pc = pc_result.data.get("pc_foster", pc_result.data.get("pc_chan"))

            if post_pc and post_pc > 1e-5:
                await self._raise_alert(
                    Severity.WARNING,
                    f"Post-maneuver Pc still elevated: {post_pc:.2e} — may need additional burn",
                    {"post_maneuver_pc": post_pc, "maneuver_id": maneuver_id},
                )

        await self.publish(
            topic="aria.propulsion.maneuver.completed",
            payload={
                "maneuver_id": maneuver_id,
                "delta_v_total_ms": self._delta_v_used_ms,
                "remaining_propellant_kg": self._propellant_kg,
            },
            correlation_id=correlation_id,
        )

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Act on LLM directives, every dispatch gated through
        safe_dispatch_check (kill switch + constitution + budget +
        approval queue for vent_tank / schedule_maneuver). Each call
        also threads `_resource_id`/`_resource_qty` so the cumulative
        Δv budget catches slow-drain attacks."""
        await super().on_reasoning_response(payload)
        from aria.cognitive.action_executor import parse_recommendation
        from aria.cognitive.safe_dispatch import safe_dispatch_check, DispatchKind
        intents = parse_recommendation(payload.get("response", "") or "")
        for intent in intents:
            if intent.action == "throttle_engine":
                fraction = max(0.0, min(1.0, float(intent.params.get("fraction", 0.0))))
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="throttle_engine",
                    params={"fraction": fraction},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Wiring audit Pass 2 (F1.5/F1.6) — route through
                # dispatch_command for safety-layer wrap.
                throttle_params = {
                    "fraction": fraction, "reason": "llm_directive",
                }
                seq = self.dispatch_command(
                    topic="aria.actuator.propulsion.throttle",
                    params=throttle_params, timeout_s=10.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.propulsion.throttle",
                        payload=throttle_params,
                        priority=EventPriority.P2_WARNING,
                    )
                await self.publish(
                    topic="aria.propulsion.llm_action.executed",
                    payload={"action": "throttle_engine", "fraction": fraction},
                    priority=EventPriority.P2_WARNING,
                )
                self._log_action_executed("throttle_engine", {"fraction": fraction})
            elif intent.action == "vent_tank":
                tank_id = intent.params.get("tank_id", "")
                if not tank_id:
                    continue
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="vent_tank",
                    params={"tank_id": tank_id},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    # vent_tank is gated → proposal queued. Operator
                    # console will surface it; we skip the immediate
                    # publish.
                    continue
                # Wiring audit Pass 2 (F1.5/F1.6).
                vent_params = {"reason": "llm_directive"}
                vent_topic = f"aria.actuator.propulsion.vent_tank.{tank_id}"
                seq = self.dispatch_command(
                    topic=vent_topic, params=vent_params, timeout_s=30.0,
                )
                if seq is None:
                    await self.publish(
                        topic=vent_topic,
                        payload=vent_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                await self.publish(
                    topic="aria.propulsion.llm_action.executed",
                    payload={"action": "vent_tank", "tank_id": tank_id},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("vent_tank", {"tank_id": tank_id})
            elif intent.action == "schedule_maneuver":
                dv_mps = float(intent.params.get("dv_mps", 0.0))
                # Thread Δv into the budget gate via the params. The
                # constitution will DENY anything that would exceed the
                # 200 m/s/hour hard cap.
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="schedule_maneuver",
                    params={"dv_mps": dv_mps,
                            "_resource_id": "delta_v_mps",
                            "_resource_qty": dv_mps},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                # Wiring audit Pass 2 (F7.7) — DO NOT commit the Δv to
                # the budget gate here.  ``aria.command.propulsion.
                # plan_burn`` has no subscriber that actually fires
                # thrusters, so an LLM (or attacker) repeatedly calling
                # schedule_maneuver would drain the Δv budget without
                # ever expending fuel.  Budget commit now lives inside
                # ``_fire_thruster`` and is keyed off the real
                # rocket-equation Δv computed from fuel burned, so the
                # budget tracks hardware effect, not LLM intent.
                await self.publish(
                    topic="aria.command.propulsion.plan_burn",
                    payload={"dv_mps": dv_mps, "reason": "llm_directive"},
                    priority=EventPriority.P2_WARNING,
                )
                await self.publish(
                    topic="aria.propulsion.llm_action.executed",
                    payload={"action": "schedule_maneuver", "dv_mps": dv_mps},
                    priority=EventPriority.P2_WARNING,
                )
                self._log_action_executed("schedule_maneuver", {"dv_mps": dv_mps})
            elif intent.action == "safe_mode":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="safe_mode", params={},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                await self._abort_maneuver({"reason": "llm_safe_mode"})
                # Wiring audit Pass 2 (F1.5/F1.6).
                safe_throttle_params = {
                    "fraction": 0.0, "reason": "llm_safe_mode",
                }
                seq = self.dispatch_command(
                    topic="aria.actuator.propulsion.throttle",
                    params=safe_throttle_params, timeout_s=5.0,
                )
                if seq is None:
                    await self.publish(
                        topic="aria.actuator.propulsion.throttle",
                        payload=safe_throttle_params,
                        priority=EventPriority.P1_CRITICAL,
                    )
                await self.publish(
                    topic="aria.propulsion.llm_action.executed",
                    payload={"action": "safe_mode"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("safe_mode", {})

    async def _abort_maneuver(self, payload: dict[str, Any]) -> None:
        """Emergency abort of active maneuver."""
        if self._active_maneuver:
            maneuver_id = self._active_maneuver.get("maneuver_id", "unknown")
            self._active_maneuver = None
            await self.publish(
                topic="aria.propulsion.maneuver.aborted",
                payload={"maneuver_id": maneuver_id, "reason": payload.get("reason", "commanded")},
                priority=EventPriority.P0_EMERGENCY,
            )
            logger.warning("propulsion.maneuver_aborted", maneuver_id=maneuver_id)

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
            topic="aria.anomaly.propulsion",
            payload={
                "severity": severity.name,
                "message": message,
                "subsystem": "propulsion",
                **(details or {}),
            },
            priority=priority,
        )

        # Wiring audit Pass 2 (F2.1) — promote WARNING+ propulsion
        # alerts (fuel margin, post-maneuver Pc, thruster stuck-on)
        # into a structured Fault on the operator ack/shelve queue.
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_str = (
                "critical"
                if severity in (Severity.CRITICAL, Severity.EMERGENCY)
                else "warning"
            )
            self.report_fault(message, severity=sev_str)

    async def periodic_task(self) -> None:
        """Periodic: compute delta-V remaining, fuel margin alerts, publish status."""
        dv_remaining = self._delta_v_budget_ms - self._delta_v_used_ms
        fuel_fraction = self._propellant_kg / max(self._initial_propellant_kg, 1.0)

        # Staged fuel margin alerts (30%, 20%, 10%)
        if fuel_fraction < 0.10:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Fuel reserve critical: {fuel_fraction:.0%} remaining ({self._propellant_kg:.1f} kg) — "
                "conservation mode recommended",
                {"fuel_fraction": fuel_fraction, "propellant_kg": self._propellant_kg},
            )
        elif fuel_fraction < 0.20:
            await self._raise_alert(
                Severity.WARNING,
                f"Fuel reserve low: {fuel_fraction:.0%} remaining — restrict non-essential maneuvers",
                {"fuel_fraction": fuel_fraction, "propellant_kg": self._propellant_kg},
            )
        elif fuel_fraction < 0.30:
            await self._raise_alert(
                Severity.WATCH,
                f"Fuel at {fuel_fraction:.0%} — approaching reserve threshold",
                {"fuel_fraction": fuel_fraction, "propellant_kg": self._propellant_kg},
            )

        # Store fuel status for coordinator
        await self.publish(
            topic="aria.propulsion.status",
            payload={
                "propellant_kg": round(self._propellant_kg, 2),
                "fuel_fraction": round(fuel_fraction, 3),
                "delta_v_used_ms": round(self._delta_v_used_ms, 3),
                "delta_v_remaining_ms": round(dv_remaining, 3),
                "tank_pressure_psi": self._tank_pressure_psi,
                "active_maneuver": self._active_maneuver is not None,
                "thrusters_healthy": sum(1 for t in self._thrusters.values() if t["healthy"]),
                "thrusters_total": len(self._thrusters),
            },
            priority=EventPriority.P4_BULK,
        )

        # Periodic thruster health self-test
        unhealthy = [tid for tid, t in self._thrusters.items() if not t["healthy"]]
        if unhealthy:
            await self._raise_alert(
                Severity.WARNING,
                f"Unhealthy thrusters: {unhealthy} — reduced redundancy",
                {"unhealthy_thrusters": unhealthy, "total": len(self._thrusters)},
            )

        # Post fuel status to scratchpad for other agents
        if self._scratchpad:
            self._scratchpad.write("propulsion.fuel_status", {
                "propellant_kg": round(self._propellant_kg, 2),
                "fuel_fraction": round(fuel_fraction, 3),
                "delta_v_remaining_ms": round(dv_remaining, 3),
            }, "propulsion", ttl_s=120)

            # Read conjunction data from NavigationAgent's scratchpad
            conj = self._scratchpad.read("nav.next_conjunction")
            if conj:
                pc = conj.get("collision_probability", 0.0)
                tca_hours = conj.get("time_to_tca_hours", float("inf"))

                # If conjunction is high-risk and within 24h, verify fuel readiness
                if pc > 1e-4 and tca_hours < 24.0:
                    # Estimate fuel needed for avoidance (rough: 0.5 m/s burn)
                    fuel_needed_kg = 0.5 * self._spacecraft_mass_kg / (DEFAULT_ISP_S * G0)
                    if self._propellant_kg < fuel_needed_kg * 2:
                        await self._raise_alert(
                            Severity.WARNING,
                            f"Low fuel for avoidance: need ~{fuel_needed_kg:.1f} kg, "
                            f"have {self._propellant_kg:.1f} kg — Pc={pc:.2e} in {tca_hours:.1f}h",
                            {"fuel_needed_kg": fuel_needed_kg, "fuel_available_kg": self._propellant_kg,
                             "conjunction_pc": pc, "tca_hours": tca_hours},
                        )
