"""PowerAgent — monitors and manages spacecraft electrical power.

Responsibilities:
  - Monitor battery SoC/SoH, solar array output, bus voltages
  - Detect power anomalies (undervoltage, overcurrent, thermal runaway precursors)
  - Execute load shedding when power is insufficient
  - Predict eclipse power budget
  - Integrate with Dsremo for power telemetry anomaly detection

Power & thermal audit (2026-04-28) hardenings:
  • P-1, P-13: ``_execute_load_shed`` now computes a deficit and sheds
    only the minimum lowest-priority subset that closes it.
  • P-6, P-7, P-22: SoH routed through aria.physics.electrical.battery
    (Schmalstieg 2014 sqrt-N + Millner 2010 Arrhenius); battery
    capacity parameterised; rolling-severity SoH alerts.
  • P-10, P-21: critical-SoC raised above NMC physics floor; cold-start
    requires N consecutive readings before triggering shedding.
  • P-12: ``LOAD_PRIORITY`` frozen via MappingProxyType + tuple wrapper.
  • P-15: continuous power-margin event (never silenced).
  • P-23: ``_load_shed_active`` + ``_charge_cycles`` persist across
    process restart.
  • P-24: shed_loads bus command requires a verified envelope.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import structlog

from aria.agents.base import SubsystemAgent
from aria.agents.dsremo_mixin import DsremoAnomalyMixin
from aria.bus.message_bus import Message
from aria.cognitive.action_executor import parse_recommendation
from aria.cognitive.safe_dispatch import safe_dispatch_check, DispatchKind
from aria.core.types import EventPriority, Severity

# Wiring audit Pass 2 (F6.7) — promoted from a wrapped per-call import
# inside ``_update_battery``. Previously a missing / renamed
# ``state_of_health`` silently dropped to the linear extrapolation
# ``100 - cycles * 0.015`` and operators saw a bogus SoH curve. Now
# ImportError is loud at boot. The linear fallback is still available
# but only when ``ARIA_BATTERY_SOH_FALLBACK=1`` is explicitly set.
from aria.physics.electrical.battery import BatteryCellConfig, state_of_health

logger = structlog.get_logger()


# Power & thermal audit P-12: LOAD_PRIORITY is now an immutable tuple of
# read-only mappings.  Mutation attempts raise ``TypeError`` at runtime.
# Inserts / deletes are impossible without explicit re-creation by the
# release process.
def _freeze_priority(rows: list[dict[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(MappingProxyType(dict(row)) for row in rows)


# Load priority table (P0 = never shed, P3 = first to shed).
# ECLSS and aria_core MUST stay sheddable=False; the constitution
# layer also forbids ``shed_load("eclss")`` via the post-condition
# predicate added in the TT&C audit (C-5).
LOAD_PRIORITY: tuple[Mapping[str, Any], ...] = _freeze_priority([
    {"name": "aria_core", "priority": 0, "min_watts": 20, "nominal_watts": 50, "sheddable": False},
    {"name": "eclss", "priority": 0, "min_watts": 500, "nominal_watts": 2000, "sheddable": False},
    {"name": "comms", "priority": 1, "min_watts": 30, "nominal_watts": 150, "sheddable": False},
    {"name": "adcs", "priority": 1, "min_watts": 30, "nominal_watts": 100, "sheddable": False},
    {"name": "navigation", "priority": 1, "min_watts": 20, "nominal_watts": 40, "sheddable": False},
    {"name": "propulsion_standby", "priority": 1, "min_watts": 30, "nominal_watts": 30, "sheddable": False},
    {"name": "crew_quarters", "priority": 2, "min_watts": 100, "nominal_watts": 500, "sheddable": True},
    {"name": "science_instruments", "priority": 3, "min_watts": 0, "nominal_watts": 300, "sheddable": True},
    {"name": "experiments", "priority": 3, "min_watts": 0, "nominal_watts": 200, "sheddable": True},
])


# Power & thermal audit P-10: critical SoC must sit above the NMC
# physics floor (NMC_SOC_MIN = 10 % per Plett 2015 §6).  10 % at the
# agent leaves zero margin for the BMS-level cutoff so we raise to
# 15 %; 20 % is the proactive load-shed threshold so we shed BEFORE
# reaching critical.  Citations:
#   Plett (2015) "Battery Management Systems" Vol.1 §4.4 — 10 % cell
#                                                          deep-discharge floor.
#   NASA TM-2009-215755 §3.1 — 5 % software-margin above BMS cutoff.
_DEFAULT_CRITICAL_SOC_PCT = 15.0     # %  (Plett 2015 §6 + NASA TM-2009-215755 margin)
_DEFAULT_LOW_SOC_PCT = 20.0          # %  (NASA TM-2009-215755 §3 proactive shedding)
_DEFAULT_RECOVER_SOC_PCT = 50.0      # %  (post-shed un-shed threshold; conservative)
_DEFAULT_RESERVE_W = 50.0            # W  (margin held back when sizing shed deficit)

# Power & thermal audit P-7: battery capacity is mission-specific.
# 2800 Wh corresponds to a 28 V × 100 Ah pack (ISS-class small sat).
# Operators with different pack geometry MUST override via
# ``ARIA_BATTERY_CAPACITY_WH`` env var so the depletion prediction
# matches the hardware.  The default below matches a CubeSat / small-
# sat reference per ESA SAVOIR §8.4 EPS bus profile.
_DEFAULT_BATTERY_CAPACITY_WH = 2800.0    # Wh — 28V × 100Ah ESA SAVOIR §8.4 ref EPS bus

# Power & thermal audit P-21: cold-start protection.  Wait for N
# consecutive readings before treating an SoC reading as truth.  Three
# samples at 1 Hz simulator cadence = ~3 s of warm-up before the
# critical-action ladder fires.  Reference: Plett 2015 §3 EKF
# convergence on first-boot battery model.
_COLD_START_SAMPLES = 3

# Power & thermal audit P-16: Dsremo z-score thresholds.  These come
# from the dsremo.yaml calibration set: WATCH @ 0.50, WARNING @ 0.65,
# CRITICAL @ 0.85 are the precision-recall optima reported in
# dsremo/eval/auto_scorer.py against the SatNOGS validation set.
_DSREMO_BATTERY_WATCH = 0.50    # Dsremo P-R calibration (auto_scorer.py)
_DSREMO_GENERIC_WARN = 0.65     # Dsremo P-R calibration (auto_scorer.py)


class PowerAgent(SubsystemAgent, DsremoAnomalyMixin):
    """Monitors spacecraft power systems and manages load budget.

    Dual-layer anomaly detection:
      Layer 1: Domain rules (voltage thresholds, SoC limits) — fast, deterministic
      Layer 2: Dsremo 12-detector ML ensemble — catches subtle power drift,
               cross-channel correlation, pre-failure signatures
    """

    name = "power"
    description = "Electrical power system monitoring, battery health, load management"
    subscriptions = [
        "aria.sensor.power.*",
        "aria.command.power.*",
    ]
    heartbeat_interval_s = 10.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._battery_soc: float = 100.0  # Percent
        self._solar_power_w: float = 0.0
        self._bus_voltage_v: float = 28.0
        self._total_load_w: float = 0.0
        self._in_eclipse: bool = False
        self._load_shed_active: bool = False
        self._shed_loads: set[str] = set()
        # Power & thermal audit P-21 — cold-start filter.
        self._soc_warmup_samples: int = 0
        self._cold_start_done: bool = False
        # Power & thermal audit P-23 — last load-shed clear / set monotonic.
        self._last_shed_change_monotonic: float = 0.0
        self._recover_streak: int = 0
        # Power & thermal audit P-22 — track which SoH band we last alerted
        # on so we don't spam at every reading.
        self._last_soh_alert_band: int = 100

        # Battery state-of-health (degrades over mission lifetime)
        # Validated: ISS Li-ion ORUs designed for 60,000 cycles, 16 cycles/day
        # Source: NASA NTRS 20160012048 — ISS Lithium-Ion Battery
        self._battery_soh: float = 100.0  # % of original capacity
        self._charge_cycles: float = 0.0

        # Power & thermal audit P-7 — battery capacity from env var or
        # the cited default.  Operators with different pack geometry
        # MUST set ARIA_BATTERY_CAPACITY_WH explicitly.
        cap_env = os.environ.get("ARIA_BATTERY_CAPACITY_WH", "")
        try:
            self._battery_capacity_wh = (
                float(cap_env) if cap_env else _DEFAULT_BATTERY_CAPACITY_WH
            )
        except ValueError:
            self._battery_capacity_wh = _DEFAULT_BATTERY_CAPACITY_WH

        # Power & thermal audit P-23 — persisted state for `_load_shed_active`
        # and `_charge_cycles`.  Default location lives next to ReplayGuard's
        # persisted state; configurable via ARIA_RUNTIME_DIR.
        env = os.environ.get("ARIA_RUNTIME_DIR")
        base = (
            Path(env) if env
            else Path(__file__).resolve().parents[3] / "data" / "runtime"
        )
        self._state_path = base / "power_agent.json"
        self._load_persistent_state()

        # Thresholds (citations on _DEFAULT_* constants above).
        self._bus_undervoltage_v: float = 24.0
        self._bus_overvoltage_v: float = 32.0
        self._battery_low_soc: float = _DEFAULT_LOW_SOC_PCT
        self._battery_critical_soc: float = _DEFAULT_CRITICAL_SOC_PCT
        self._battery_recover_soc: float = _DEFAULT_RECOVER_SOC_PCT

    async def on_start(self) -> None:
        logger.info("power_agent.started")
        # Self-test on startup
        test_result = await self._tools.invoke("diagnostic_run_subsystem_test", {
            "subsystem": "eps",
            "test_level": "quick",
        })
        if test_result.success and test_result.data:
            if test_result.data.get("result") != "PASS":
                logger.warning("power_agent.self_test_failed", result=test_result.data)

    async def handle_message(self, message: Message) -> None:
        topic = message.topic
        payload = message.payload

        if topic == "aria.sensor.power.battery":
            await self._update_battery(payload)
        elif topic == "aria.sensor.power.solar":
            await self._update_solar(payload)
        elif topic == "aria.sensor.power.bus":
            await self._update_bus(payload)
        elif topic == "aria.sensor.power.load":
            await self._update_load(payload)
        elif topic == "aria.command.power.shed_loads":
            # Power & thermal audit P-24: external shed_loads command
            # must carry a verified envelope (matching TT&C C-4 pattern).
            envelope = payload.get("_envelope") or {}
            if not envelope.get("verified"):
                logger.warning(
                    "power_agent.shed_loads_unverified_blocked",
                    source=payload.get("source", ""),
                )
                return
            await self._execute_load_shed(payload)
        elif topic == "aria.command.power.safe_mode":
            # Wiring audit Pass 2 (F7.6) — the LLM safe_mode intent
            # publishes to this topic from on_reasoning_response, but
            # there was no handler here so the command was silently
            # dropped (operators saw aria.power.llm_action.executed
            # without any load-shed effect).  Now we force the
            # load-shed ladder to its bottom by passing a deficit
            # large enough to drop every sheddable load — the
            # ordering inside ``_execute_load_shed`` already shed
            # only sheddable loads and stops at the floor, so this
            # produces the "P0 essentials only" posture without a
            # separate code path.
            await self._execute_load_shed({
                "deficit_watts": 1.0e9,    # force max shed
                "reason": payload.get("reason", "llm_safe_mode"),
            })
            logger.warning(
                "power_agent.safe_mode_entered",
                reason=payload.get("reason", "llm_safe_mode"),
                shed_count=len(self._shed_loads),
            )
        elif topic == "aria.command.power.status":
            await self._publish_status(message.correlation_id)

    async def _update_battery(self, payload: dict[str, Any]) -> None:
        prev_soc = self._battery_soc
        self._battery_soc = payload.get("soc_percent", self._battery_soc)
        temperature = payload.get("temperature_c", 25.0)

        # Power & thermal audit P-21 — cold-start filter.  Wait for
        # _COLD_START_SAMPLES consecutive readings before honouring the
        # critical-action ladder.  This prevents a single SoC=0 sample
        # at boot (before the BMS has warmed up) from immediately
        # tripping load-shed.
        if not self._cold_start_done:
            self._soc_warmup_samples += 1
            if self._soc_warmup_samples >= _COLD_START_SAMPLES:
                self._cold_start_done = True
                logger.info("power_agent.cold_start_complete",
                            samples=self._soc_warmup_samples)
            else:
                logger.debug("power_agent.cold_start_filter",
                             samples=self._soc_warmup_samples)
                return

        # Battery SoH degradation: track charge cycles.
        # Power & thermal audit P-6 — route through the physics module
        # (sqrt-N + Arrhenius) instead of a linear extrapolation.
        soc_delta = abs(self._battery_soc - prev_soc)
        self._charge_cycles += soc_delta / 100.0
        # Wiring audit Pass 2 (F6.7) — physics module is imported at
        # module-load. Only physics-internal failures (numerical edge
        # cases, NaN inputs) are caught here; the linear fallback is
        # gated behind an explicit env var so it cannot silently
        # activate for an unrelated bug.
        try:
            soh_fraction = state_of_health(
                BatteryCellConfig(),
                n_cycles=self._charge_cycles,
                calendar_years=0.0,                       # caller-provided in mission control
                temperature_K=temperature + 273.15,
            )
            self._battery_soh = float(soh_fraction) * 100.0
        except (ValueError, ArithmeticError, TypeError) as exc:
            logger.warning("power_agent.soh_physics_failed", error=str(exc))
            if os.environ.get("ARIA_BATTERY_SOH_FALLBACK", "0") == "1":
                # Linear fallback — explicit operator opt-in only.
                self._battery_soh = max(0.0, 100.0 - self._charge_cycles * 0.015)
                logger.warning("power_agent.soh_linear_fallback_applied",
                               cycles=self._charge_cycles,
                               soh=self._battery_soh)
            else:
                # Keep the previous SoH value rather than synthesising
                # a misleading linear curve. Operators see the warn.
                pass

        # Power & thermal audit P-22 — rolling-severity SoH alerting.
        # Bands: 80 / 65 / 50 / 35 % with escalating severity.  Once
        # tripped a band, do not re-fire until the SoH falls into the
        # next lower band.
        for band_pct, severity in (
            (35.0, Severity.CRITICAL),
            (50.0, Severity.WARNING),
            (65.0, Severity.WARNING),
            (80.0, Severity.WATCH),
        ):
            if (
                self._battery_soh < band_pct
                and self._last_soh_alert_band > band_pct
            ):
                self._last_soh_alert_band = int(band_pct)
                await self._raise_alert(
                    severity,
                    f"Battery SoH degraded below {band_pct:.0f}%: "
                    f"{self._battery_soh:.1f}% "
                    f"({self._charge_cycles:.0f} equivalent cycles)",
                    {"battery_soh": self._battery_soh,
                     "charge_cycles": self._charge_cycles,
                     "band_pct": band_pct},
                )
                break

        # Battery thermal runaway early warning: rising temp + dropping SoC
        if temperature > 40.0 and self._battery_soc < 30.0:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Battery thermal runaway risk: temp={temperature:.1f}°C + SoC={self._battery_soc:.1f}% — "
                "isolate battery if temperature continues rising",
                {"temperature_c": temperature, "soc": self._battery_soc, "event": "thermal_runaway_precursor"},
            )
        elif temperature > 35.0:
            await self._raise_alert(
                Severity.WATCH,
                f"Battery temperature elevated: {temperature:.1f}°C — monitor for thermal runaway",
                {"temperature_c": temperature, "subsystem": "battery"},
            )

        # Layer 1: Domain rules (fast, deterministic)
        if self._battery_soc <= self._battery_critical_soc:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Battery SoC critical: {self._battery_soc:.1f}%",
                {"soc": self._battery_soc, "subsystem": "battery"},
            )
            await self._execute_load_shed({"reason": "critical_soc"})

        elif self._battery_soc <= self._battery_low_soc:
            await self._raise_alert(
                Severity.WARNING,
                f"Battery SoC low: {self._battery_soc:.1f}%",
                {"soc": self._battery_soc, "subsystem": "battery"},
            )
            # Request AI reasoning for complex power management decision
            if self._in_eclipse and temperature > 35.0:
                await self.request_reasoning(
                    f"Battery SoC={self._battery_soc:.1f}% during eclipse with high temperature "
                    f"({temperature:.1f}C). Should we shed science loads or risk deeper discharge?",
                    context={"soc": self._battery_soc, "temperature_c": temperature, "in_eclipse": True},
                )

        # Thermal runaway precursor: rapid temperature rise
        if temperature > 55.0:
            await self._raise_alert(
                Severity.CRITICAL,
                f"Battery temperature high: {temperature:.1f}°C — thermal runaway risk",
                {"temperature_c": temperature, "subsystem": "battery"},
            )

        # Layer 2: Dsremo ML ensemble — catch subtle power anomalies
        scores = await self.dsremo_score_batch([
            {"subsystem": "eps", "component": "battery", "metric": "soc_percent", "value": self._battery_soc},
            {"subsystem": "eps", "component": "battery", "metric": "temperature_c", "value": temperature},
        ])
        for channel_id, score in scores.items():
            if score >= _DSREMO_BATTERY_WATCH and self._battery_soc > self._battery_low_soc:
                # Dsremo caught something the threshold didn't — report it
                severity_name = self.dsremo_classify(score)
                await self._raise_alert(
                    Severity[severity_name],
                    f"[Dsremo] Battery anomaly on {channel_id}: score={score:.2f}",
                    {"channel_id": channel_id, "dsremo_score": score, "subsystem": "battery"},
                )

    async def _update_solar(self, payload: dict[str, Any]) -> None:
        prev_solar = self._solar_power_w
        self._solar_power_w = payload.get("power_watts", 0.0)

        # Power & thermal audit P-3 — eclipse detection from orbit
        # position when available, with the legacy power-reading
        # threshold as a fallback.  Position predictor is authoritative;
        # power-reading is only consulted when the predictor isn't
        # wired in (e.g. tests, dev mode).  The hysteresis protects
        # against partial-shadow flicker.
        in_eclipse_position = payload.get("in_eclipse_predicted")
        if isinstance(in_eclipse_position, bool):
            self._in_eclipse = in_eclipse_position
        else:
            # Fallback: use the power-reading.  Threshold raised from
            # 1 W to 5 % of the spacecraft's nominal generation so a
            # partial-array failure doesn't masquerade as eclipse.
            nominal_w = max(prev_solar, payload.get("nominal_power_watts", 0.0))
            threshold_w = max(5.0, 0.05 * nominal_w)    # 5 W floor / 5 % of nominal
            self._in_eclipse = self._solar_power_w < threshold_w

        # Solar array degradation detection: >10% sudden drop (not eclipse)
        if prev_solar > 100.0 and self._solar_power_w > 100.0:
            drop_pct = (prev_solar - self._solar_power_w) / prev_solar * 100
            if drop_pct > 10.0:
                await self._raise_alert(
                    Severity.WARNING,
                    f"Solar power drop: {prev_solar:.0f}W → {self._solar_power_w:.0f}W "
                    f"({drop_pct:.0f}% decrease) — possible string failure",
                    {"prev_watts": prev_solar, "current_watts": self._solar_power_w,
                     "drop_percent": drop_pct, "subsystem": "solar"},
                )

        # Dsremo ML scoring for subtle degradation trends
        if self._solar_power_w > 0:
            score = await self.dsremo_score("eps", "solar", "power_watts", self._solar_power_w)
            if score and score >= _DSREMO_GENERIC_WARN:
                await self._raise_alert(
                    Severity[self.dsremo_classify(score)],
                    f"[Dsremo] Solar array anomaly: score={score:.2f}",
                    {"dsremo_score": score, "solar_power_w": self._solar_power_w, "subsystem": "solar"},
                )

        # Post eclipse state to scratchpad for other agents (ThermalAgent reads this)
        if self._scratchpad:
            self._scratchpad.write("power.eclipse_state", {
                "in_eclipse": self._in_eclipse,
                "solar_power_w": self._solar_power_w,
                "battery_soc": self._battery_soc,
            }, "power", ttl_s=600)

        if self._in_eclipse:
            await self.publish(
                topic="aria.power.eclipse.entered",
                payload={"solar_power_w": self._solar_power_w},
                priority=EventPriority.P3_ROUTINE,
            )

    async def _update_bus(self, payload: dict[str, Any]) -> None:
        self._bus_voltage_v = payload.get("voltage_v", self._bus_voltage_v)

        # Layer 1: Threshold check
        if self._bus_voltage_v < self._bus_undervoltage_v:
            await self._raise_alert(
                Severity.WARNING,
                f"Bus undervoltage: {self._bus_voltage_v:.1f}V (threshold: {self._bus_undervoltage_v}V)",
                {"voltage_v": self._bus_voltage_v, "subsystem": "bus"},
            )
        elif self._bus_voltage_v > self._bus_overvoltage_v:
            await self._raise_alert(
                Severity.WARNING,
                f"Bus overvoltage: {self._bus_voltage_v:.1f}V (threshold: {self._bus_overvoltage_v}V)",
                {"voltage_v": self._bus_voltage_v, "subsystem": "bus"},
            )

        # Layer 2: Dsremo ML check for bus voltage
        score = await self.dsremo_score("eps", "bus", "voltage_v", self._bus_voltage_v)
        if score and score >= _DSREMO_GENERIC_WARN:
            await self._raise_alert(
                Severity[self.dsremo_classify(score)],
                f"[Dsremo] Bus voltage anomaly: score={score:.2f}, v={self._bus_voltage_v:.2f}V",
                {"channel_id": "eps.bus.voltage_v", "dsremo_score": score, "subsystem": "bus"},
            )

    async def _update_load(self, payload: dict[str, Any]) -> None:
        self._total_load_w = payload.get("total_watts", self._total_load_w)

    async def on_reasoning_response(self, payload: dict[str, Any]) -> None:
        """Act on the LLM's recommendation, not just record it.

        Parses the engine's free-text response for action keywords (via the
        shared ActionExecutor regex set) and routes each parsed intent into a
        concrete simulator action with the agent's safety layer
        (ExecutionGuard + CommandTracker) already in place via dispatch_command.

        Recognised intents for the power subsystem:
          - shed_load <subsystem>   → _execute_load_shed (with reason)
          - safe_mode                → publish aria.command.power.safe_mode
          - throttle_engine          → published as advisory only (propulsion owns it)

        Every executed intent emits aria.power.llm_action.executed for
        traceability so operators see exactly what the AI changed.
        """
        await super().on_reasoning_response(payload)
        text = payload.get("response", "") or ""
        intents = parse_recommendation(text)
        if not intents:
            return
        for intent in intents:
            if intent.action == "shed_load":
                subsys = intent.params.get("subsystem", "any")
                # Failsafe stack pre-check (kill switch → constitution
                # → resource budget). Only EXECUTED means we may run.
                outcome = safe_dispatch_check(
                    agent_name=self.name,
                    action="shed_load",
                    params={"subsystem": subsys, "reason": f"llm_directive:{subsys}"},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    # Either DENIED (logged) or GATED (proposal created).
                    # Skip dispatch; operator console will surface it.
                    continue
                await self._execute_load_shed({"reason": f"llm_directive:{subsys}"})
                await self.publish(
                    topic="aria.power.llm_action.executed",
                    payload={"action": "shed_load", "subsystem": subsys,
                             "rationale": intent.rationale or "llm_recommendation"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("shed_load", {"subsystem": subsys}, intent.rationale)
            elif intent.action == "safe_mode":
                outcome = safe_dispatch_check(
                    agent_name=self.name, action="safe_mode",
                    params={"reason": "llm_directive"},
                    rationale=intent.rationale or "llm_recommendation",
                )
                if outcome.kind is not DispatchKind.EXECUTED:
                    continue
                await self.publish(
                    topic="aria.command.power.safe_mode",
                    payload={"reason": "llm_directive"},
                    priority=EventPriority.P1_CRITICAL,
                )
                await self.publish(
                    topic="aria.power.llm_action.executed",
                    payload={"action": "safe_mode",
                             "rationale": intent.rationale or "llm_recommendation"},
                    priority=EventPriority.P1_CRITICAL,
                )
                self._log_action_executed("safe_mode", {}, intent.rationale)
            # Other intents (throttle_engine, vent_tank, etc.) are surfaced
            # as advisories by the SubsystemAgent base class — no duplicate
            # publish needed here.

    async def _execute_load_shed(self, payload: dict[str, Any]) -> None:
        """Shed loads from P3 → P2 until the power budget balances.

        Power & thermal audit P-1 / P-13: shed only the *minimum*
        lowest-priority subset that closes the deficit, rather than
        flat-out shedding every sheddable load.  An explicit
        ``deficit_watts`` parameter overrides the computed value (used
        by the LLM directive path).
        """
        reason = payload.get("reason", "manual")
        explicit_deficit = payload.get("deficit_watts")

        if isinstance(explicit_deficit, (int, float)):
            deficit_w = max(0.0, float(explicit_deficit))
        else:
            # Compute deficit from current state.
            deficit_w = max(
                0.0,
                self._total_load_w - self._solar_power_w + _DEFAULT_RESERVE_W,
            )

        if deficit_w <= 0:
            logger.info("power_agent.load_shed_skip_no_deficit", reason=reason)
            return

        # Shed lowest-priority sheddable loads first; stop when deficit closed.
        shed_list: list[str] = []
        remaining = deficit_w
        # Sort by priority descending (P3 first → first to shed),
        # then by nominal_watts descending so we shed the largest load
        # first within a priority band.
        ordered = sorted(
            (entry for entry in LOAD_PRIORITY if entry["sheddable"]),
            key=lambda entry: (-int(entry["priority"]),
                               -float(entry["nominal_watts"])),
        )
        for entry in ordered:
            if remaining <= 0.0:
                break
            if entry["name"] in self._shed_loads:
                # Already shed; skip.
                continue
            shed_list.append(entry["name"])
            self._shed_loads.add(entry["name"])
            shed_w = float(entry["nominal_watts"]) - float(entry["min_watts"])
            remaining -= max(0.0, shed_w)
            logger.info("power_agent.shedding_load",
                        load=entry["name"], reason=reason,
                        shed_watts=shed_w)

        if shed_list:
            self._load_shed_active = True
            self._last_shed_change_monotonic = time.monotonic()
            self._save_persistent_state()

            # Invoke tool for formal load-shed action with the actual
            # deficit (P-13).  ``min_priority`` is set to the lowest
            # priority we actually shed so downstream consumers can
            # reproduce the shed list.
            min_priority_shed = min(
                int(entry["priority"]) for entry in LOAD_PRIORITY
                if entry["name"] in shed_list
            )
            await self._tools.invoke("eps_load_shed", {
                "shed_amount_watts": deficit_w,
                "reason": reason,
                "min_priority": min_priority_shed,
                "shed_loads": shed_list,
            })

            await self.publish(
                topic="aria.power.load_shed.executed",
                payload={"shed_loads": shed_list, "reason": reason,
                         "deficit_watts": deficit_w},
                priority=EventPriority.P1_CRITICAL,
            )

    async def _try_recover_load_shed(self) -> None:
        """Power & thermal audit P-1 / P-15 — un-shed when SoC + solar
        provide a stable surplus.  Anti-flap: require ``_DEFAULT_RECOVER_SOC_PCT``
        SoC for ≥ 5 monotonic minutes AND solar > total_load + reserve,
        AND at least 60 s since the last shed change.
        """
        if not self._load_shed_active or not self._shed_loads:
            return
        now_m = time.monotonic()
        if now_m - self._last_shed_change_monotonic < 60.0:
            return
        if self._battery_soc < self._battery_recover_soc:
            self._recover_streak = 0
            return
        if self._solar_power_w < self._total_load_w + _DEFAULT_RESERVE_W:
            self._recover_streak = 0
            return
        self._recover_streak += 1
        # Need ~5 minutes of stable surplus at the heartbeat cadence
        # (heartbeat_interval_s=10) → 30 ticks.
        if self._recover_streak < 30:
            return

        # Un-shed the *highest-priority* load first (P2 before P3) so
        # crew quarters return before science.
        ordered = sorted(
            (entry for entry in LOAD_PRIORITY if entry["sheddable"]),
            key=lambda entry: int(entry["priority"]),
        )
        for entry in ordered:
            if entry["name"] in self._shed_loads:
                self._shed_loads.discard(entry["name"])
                logger.info("power_agent.unshedding_load",
                            load=entry["name"])
                await self.publish(
                    topic="aria.power.load_shed.recovered",
                    payload={"unshed_load": entry["name"],
                             "remaining_shed": list(self._shed_loads)},
                    priority=EventPriority.P2_WARNING,
                )
                break  # one-at-a-time; wait another window before next
        if not self._shed_loads:
            self._load_shed_active = False
        self._last_shed_change_monotonic = now_m
        self._recover_streak = 0
        self._save_persistent_state()

    # ── Persistence (audit P-23) ────────────────────────────────

    def _load_persistent_state(self) -> None:
        try:
            if not self._state_path.is_file():
                return
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._load_shed_active = bool(data.get("load_shed_active", False))
            self._shed_loads = set(data.get("shed_loads", []))
            self._charge_cycles = float(data.get("charge_cycles", 0.0))
            self._last_soh_alert_band = int(data.get("last_soh_alert_band", 100))
        except Exception as exc:    # noqa: BLE001
            logger.warning("power_agent.state_load_failed", error=str(exc))

    def _save_persistent_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            payload = {
                "load_shed_active": self._load_shed_active,
                "shed_loads": sorted(self._shed_loads),
                "charge_cycles": self._charge_cycles,
                "last_soh_alert_band": self._last_soh_alert_band,
            }
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(payload, fp)
                fp.flush()
                try:
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp, self._state_path)
            try:
                os.chmod(self._state_path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("power_agent.state_save_failed", error=str(exc))

    async def _publish_status(self, correlation_id: str) -> None:
        await self.publish(
            topic="aria.power.status.response",
            payload={
                "battery_soc_percent": self._battery_soc,
                "solar_power_w": self._solar_power_w,
                "bus_voltage_v": self._bus_voltage_v,
                "total_load_w": self._total_load_w,
                "in_eclipse": self._in_eclipse,
                "load_shed_active": self._load_shed_active,
            },
            correlation_id=correlation_id,
        )

    async def _raise_alert(
        self, severity: Severity, message: str, details: dict[str, Any]
    ) -> None:
        priority = {
            Severity.WATCH: EventPriority.P3_ROUTINE,
            Severity.WARNING: EventPriority.P2_WARNING,
            Severity.CRITICAL: EventPriority.P1_CRITICAL,
            Severity.EMERGENCY: EventPriority.P0_EMERGENCY,
        }.get(severity, EventPriority.P3_ROUTINE)

        await self.publish(
            topic="aria.anomaly.power",
            payload={"severity": severity.name, "message": message, **details},
            priority=priority,
        )

        # Also report to the structured fault manager (if wired via
        # coordinator.register_agent → set_safety_context). Faults with
        # WARNING/CRITICAL severity require operator ack/resolve workflow.
        if severity in (Severity.WARNING, Severity.CRITICAL, Severity.EMERGENCY):
            sev_map = {
                Severity.WARNING: "warning",
                Severity.CRITICAL: "critical",
                Severity.EMERGENCY: "critical",
            }
            self.report_fault(message, severity=sev_map.get(severity, "warning"))

    async def periodic_task(self) -> None:
        """Check power balance and query power budget tool."""
        # Query power budget tool for detailed analysis
        budget_result = await self._tools.invoke("eps_get_power_budget", {})
        if budget_result.success and budget_result.data:
            margin = budget_result.data.get("margin_w", 0)
            if margin < 0:
                self._total_load_w = budget_result.data.get("consumption_w", self._total_load_w)

        power_margin = self._solar_power_w - self._total_load_w

        # Power & thermal audit P-15 — emit a continuous structured
        # margin event regardless of load-shed state.  Operators can
        # poll this on every heartbeat and graph it; the alert path
        # below escalates to WARNING only when the margin is
        # *worsening* (delta < 0) so we don't drown the audit log.
        await self.publish(
            topic="aria.power.margin",
            payload={
                "margin_w": power_margin,
                "solar_power_w": self._solar_power_w,
                "total_load_w": self._total_load_w,
                "battery_soc": self._battery_soc,
                "battery_soh": self._battery_soh,
                "in_eclipse": self._in_eclipse,
                "load_shed_active": self._load_shed_active,
            },
            priority=EventPriority.P3_ROUTINE,
        )
        if power_margin < 0:
            await self._raise_alert(
                Severity.WARNING,
                f"Negative power margin: {power_margin:.0f}W — consuming battery reserves",
                {"margin_w": power_margin,
                 "load_shed_active": self._load_shed_active},
            )

        # Eclipse battery margin check
        if self._in_eclipse and self._battery_soc < 60.0:
            await self._raise_alert(
                Severity.WATCH,
                f"Eclipse with low battery: SoC={self._battery_soc:.0f}% — monitor closely",
                {"battery_soc": self._battery_soc, "in_eclipse": True},
            )

        # Power & thermal audit P-1: try to recover from load shed
        # when SoC + solar are stable.
        await self._try_recover_load_shed()

        # Post power prediction to scratchpad.
        # P-7 audit: capacity is parameterised; SoH-derated.
        if self._scratchpad:
            drain_rate = self._total_load_w - self._solar_power_w  # watts over generation
            effective_capacity_wh = (
                self._battery_capacity_wh * (self._battery_soh / 100.0)
            )
            if drain_rate > 0 and self._battery_soc > 0:
                wh_remaining = (
                    self._battery_soc / 100.0 * effective_capacity_wh
                )
                hours_remaining = wh_remaining / drain_rate
            else:
                hours_remaining = float("inf")

            self._scratchpad.write("power.prediction", {
                "battery_soc": self._battery_soc,
                "battery_soh": self._battery_soh,
                "battery_capacity_wh": self._battery_capacity_wh,
                "effective_capacity_wh": effective_capacity_wh,
                "power_margin_w": power_margin,
                "hours_to_depletion": round(hours_remaining, 1) if hours_remaining < 1000 else None,
                "in_eclipse": self._in_eclipse,
                "load_shed_active": self._load_shed_active,
            }, "power", ttl_s=30)
            # P-20: tighter scratchpad TTL for eclipse_state (was 600 s).
            self._scratchpad.write("power.eclipse_state", {
                "in_eclipse": self._in_eclipse,
                "solar_power_w": self._solar_power_w,
                "battery_soc": self._battery_soc,
                "battery_soh": self._battery_soh,
            }, "power", ttl_s=30)
