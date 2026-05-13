from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class HalCommand:
    primitive: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionTranslation:
    proposed_action: str
    status: str
    hal_command: Optional[HalCommand] = None
    residual_reason: str = ""
    notes: str = ""
    subsystem: str = ""
    precondition_failed: bool = False

    @property
    def applied(self) -> bool:
        return self.status == "applied"

    @property
    def deferred(self) -> bool:
        return self.status == "deferred"

    @property
    def refused(self) -> bool:
        return self.status == "refused"


PreconditionFn = Callable[[dict[str, Any]], tuple[bool, str]]


@dataclass(frozen=True)
class ActionMapping:
    proposed_action: str
    primitive: str
    subsystem: str = "generic"
    fixed_params: dict[str, Any] = field(default_factory=dict)
    extract_params: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None
    precondition: Optional[PreconditionFn] = None
    notes: str = ""
    citation: str = ""


def _always_ok(_context: dict[str, Any]) -> tuple[bool, str]:
    return True, ""


def _require_state_present(parameter: str) -> PreconditionFn:
    def check(context: dict[str, Any]) -> tuple[bool, str]:
        state = context.get("state") or {}
        if parameter not in state:
            return False, f"required state {parameter} not in window"
        return True, ""
    return check


def _require_state_below(parameter: str, threshold: float) -> PreconditionFn:
    def check(context: dict[str, Any]) -> tuple[bool, str]:
        state = context.get("state") or {}
        if parameter not in state:
            return False, f"required state {parameter} not in window"
        value = state[parameter]
        if value >= threshold:
            return False, f"{parameter}={value:.3g} >= safety threshold {threshold:.3g}"
        return True, ""
    return check


def _require_state_above(parameter: str, threshold: float) -> PreconditionFn:
    def check(context: dict[str, Any]) -> tuple[bool, str]:
        state = context.get("state") or {}
        if parameter not in state:
            return False, f"required state {parameter} not in window"
        value = state[parameter]
        if value <= threshold:
            return False, f"{parameter}={value:.3g} <= safety threshold {threshold:.3g}"
        return True, ""
    return check


_POWER_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="load_shed_csm_bus_a",
        primitive="payload.off",
        subsystem="power",
        notes="Drop non-essential payload load on Bus A.",
        citation="Apollo Operations Handbook §2.6",
    ),
    ActionMapping(
        proposed_action="load_shed_group_4",
        primitive="payload.off",
        subsystem="power",
        notes="ISS load-shed Group 4 (non-critical experiments) per FR-PWR-201.",
        citation="ISS Power System Specification SSP-30482",
    ),
    ActionMapping(
        proposed_action="load_shed_group_3",
        primitive="payload.off",
        subsystem="power",
        notes="ISS load-shed Group 3 (lighting).",
        citation="SSP-30482",
    ),
    ActionMapping(
        proposed_action="load_shed_group_2",
        primitive="payload.off",
        subsystem="power",
        notes="ISS load-shed Group 2 (active thermal). Group 1 NEVER auto-shed.",
        citation="SSP-30482",
    ),
    ActionMapping(
        proposed_action="switch_to_redundant_bus",
        primitive="payload.on",
        subsystem="power",
        notes="Switch loads to redundant power bus (B-side).",
        citation="ISS Operations Handbook OPS-04",
    ),
    ActionMapping(
        proposed_action="payload_off",
        primitive="payload.off",
        subsystem="power",
    ),
    ActionMapping(
        proposed_action="payload_on",
        primitive="payload.on",
        subsystem="power",
    ),
    ActionMapping(
        proposed_action="enter_minimum_power_mode",
        primitive="payload.off",
        subsystem="power",
        notes="Survival-mode minimum-load configuration.",
        citation="ISS Generic OFR ALL-FR-PWR-205",
    ),
    ActionMapping(
        proposed_action="charge_battery",
        primitive="ping",
        subsystem="power",
        notes="Advisor request — close BCDU into charge mode (no sidecar primitive yet).",
    ),
    ActionMapping(
        proposed_action="reset_pdu",
        primitive="ping",
        subsystem="power",
        notes="Power-cycle a Power Distribution Unit; no sidecar primitive yet.",
    ),
)


_THERMAL_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="heater_on",
        primitive="heater.on",
        subsystem="thermal",
    ),
    ActionMapping(
        proposed_action="heater_off",
        primitive="heater.off",
        subsystem="thermal",
    ),
    ActionMapping(
        proposed_action="warm_critical_components",
        primitive="heater.on",
        subsystem="thermal",
        notes="Engage survival heater bank for cold-soak protection.",
        citation="ECSS-E-HB-31-01 Thermal Control",
    ),
    ActionMapping(
        proposed_action="thermal_step_minute",
        primitive="heater.step",
        subsystem="thermal",
        fixed_params={"dt_s": 60.0},
        notes="Advance thermal model by one minute; used for advisor predictions.",
    ),
    ActionMapping(
        proposed_action="deploy_radiator",
        primitive="ping",
        subsystem="thermal",
        notes="Deployable radiator extension; no sidecar primitive yet.",
    ),
    ActionMapping(
        proposed_action="retract_radiator",
        primitive="ping",
        subsystem="thermal",
    ),
    ActionMapping(
        proposed_action="bypass_loop_a_to_loop_b",
        primitive="ping",
        subsystem="thermal",
        notes="ISS thermal-loop crossover; no sidecar primitive yet.",
    ),
)


_ATTITUDE_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="damp_rates",
        primitive="wheel.torque",
        subsystem="attitude",
        fixed_params={"torque_nm": [-0.05, -0.05, -0.05], "dt_s": 1.0},
        notes="Apply -tau on body rates to bring spacecraft to rest.",
        citation="Wertz, Spacecraft Attitude Determination & Control §17",
    ),
    ActionMapping(
        proposed_action="hold_inertial_attitude",
        primitive="wheel.torque",
        subsystem="attitude",
        fixed_params={"torque_nm": [0.0, 0.0, 0.0], "dt_s": 1.0},
        notes="Hold current attitude in inertial frame.",
    ),
    ActionMapping(
        proposed_action="point_solar_arrays_to_sun",
        primitive="wheel.torque",
        subsystem="attitude",
        fixed_params={"torque_nm": [0.0, 0.0, 0.05], "dt_s": 1.0},
        notes="Slew toward sun-pointing for power generation.",
        citation="Apollo Mission Rules §6.4",
    ),
    ActionMapping(
        proposed_action="enter_safe_mode_sun_pointing",
        primitive="wheel.torque",
        subsystem="attitude",
        fixed_params={"torque_nm": [0.0, 0.0, 0.02], "dt_s": 1.0},
        notes="Emergency Sun Reacquisition (ESR) mode.",
        citation="SOHO ESR procedure (1998); ESA SOHO Anomaly Report",
    ),
    ActionMapping(
        proposed_action="dump_momentum_via_thrusters",
        primitive="thruster.fire",
        subsystem="attitude",
        fixed_params={"burn_time_s": 0.1},
        precondition=_always_ok,
        notes="Reaction-wheel desat via short thruster pulse.",
        citation="Wertz §17.6",
    ),
    ActionMapping(
        proposed_action="reset_imu",
        primitive="ping",
        subsystem="attitude",
    ),
    ActionMapping(
        proposed_action="abort_slew",
        primitive="ping",
        subsystem="attitude",
        notes="Halt commanded slew immediately.",
    ),
)


_COMMS_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="switch_to_omni_antenna",
        primitive="ping",
        subsystem="comms",
        notes="Fall back to omni antenna; lose data rate but maintain link.",
        citation="ISS Comms FR-COMMS-101",
    ),
    ActionMapping(
        proposed_action="switch_to_high_gain_antenna",
        primitive="ping",
        subsystem="comms",
    ),
    ActionMapping(
        proposed_action="reduce_data_rate",
        primitive="ping",
        subsystem="comms",
        notes="Increase link margin under degraded SNR.",
    ),
    ActionMapping(
        proposed_action="dump_recorder",
        primitive="ping",
        subsystem="comms",
        notes="Forward solid-state recorder buffer to ground.",
    ),
    ActionMapping(
        proposed_action="sce_to_aux",
        primitive="ping",
        subsystem="comms",
        notes="Apollo 12 famous: switch SCE (Signal Conditioning Equipment) to auxiliary.",
        citation="Apollo 12 Mission Report MSC-01855 §5.3",
    ),
)


_PROPULSION_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="thruster_fire_short",
        primitive="thruster.fire",
        subsystem="propulsion",
        fixed_params={"burn_time_s": 0.1},
    ),
    ActionMapping(
        proposed_action="thruster_fire_attitude_correction",
        primitive="thruster.fire",
        subsystem="propulsion",
        fixed_params={"burn_time_s": 0.5},
    ),
    ActionMapping(
        proposed_action="thruster_fire_collision_avoidance",
        primitive="thruster.fire",
        subsystem="propulsion",
        fixed_params={"burn_time_s": 5.0},
        notes="Conjunction-screening avoidance burn; requires conjunction confirmation.",
        citation="JSC-66050 Conjunction Assessment Risk Analysis",
    ),
    ActionMapping(
        proposed_action="abort_burn",
        primitive="ping",
        subsystem="propulsion",
        notes=(
            "No abort primitive in current sidecar; advisor's intent logged "
            "and crew ack requested."
        ),
    ),
    ActionMapping(
        proposed_action="set_propellant_pressure_to_safe",
        primitive="ping",
        subsystem="propulsion",
    ),
)


_LIFE_SUPPORT_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="switch_cdra_a_to_b",
        primitive="ping",
        subsystem="life_support",
        notes="ISS CDRA failover.",
        citation="MAL-CDRA-1, NASA SSP 50261",
    ),
    ActionMapping(
        proposed_action="activate_lioh_canister",
        primitive="ping",
        subsystem="life_support",
        notes="Backup CO2 absorbent.",
        citation="ISS Crew Procedures EMER-CO2",
    ),
    ActionMapping(
        proposed_action="activate_vozdukh",
        primitive="ping",
        subsystem="life_support",
        notes="Russian segment CO2 removal as backup.",
    ),
    ActionMapping(
        proposed_action="reduce_crew_metabolic_load",
        primitive="ping",
        subsystem="life_support",
        notes="Defer exercise; crew rest.",
    ),
    ActionMapping(
        proposed_action="prepare_lm_lifeboat",
        primitive="ping",
        subsystem="life_support",
        notes=(
            "Crew procedure with no HAL primitive; logged for ground "
            "console + crew ack."
        ),
        citation="Apollo 13 Mission Rules MSC-PA-FR-69 §5.12",
    ),
    ActionMapping(
        proposed_action="seal_module_hatch",
        primitive="ping",
        subsystem="life_support",
        notes="Mir Spektr emergency seal procedure.",
        citation="NASA-Mir Phase 1 Joint Report (1998)",
    ),
    ActionMapping(
        proposed_action="don_emu_suits",
        primitive="ping",
        subsystem="life_support",
        notes="Crew don pressurized suits — last-resort hypoxia/depress response.",
    ),
)


_OPS_MAPPINGS: tuple[ActionMapping, ...] = (
    ActionMapping(
        proposed_action="ping",
        primitive="ping",
        subsystem="ops",
        notes="Liveness probe.",
    ),
    ActionMapping(
        proposed_action="investigate",
        primitive="ping",
        subsystem="ops",
        notes="No-op shape: log advisor request, ack to crew.",
    ),
    ActionMapping(
        proposed_action="acknowledge_alarm",
        primitive="ping",
        subsystem="ops",
    ),
    ActionMapping(
        proposed_action="notify_flight_director",
        primitive="ping",
        subsystem="ops",
        notes="Surface event to mission ops; ground concurrence required.",
    ),
    ActionMapping(
        proposed_action="run_self_test",
        primitive="ping",
        subsystem="ops",
    ),
    ActionMapping(
        proposed_action="cross_check_sensor",
        primitive="ping",
        subsystem="ops",
        notes="Compare with redundant sensor before action.",
    ),
    ActionMapping(
        proposed_action="defer_to_ground",
        primitive="ping",
        subsystem="ops",
        notes="Pause for ground concurrence.",
    ),
)


DEFAULT_MAPPINGS: tuple[ActionMapping, ...] = (
    _POWER_MAPPINGS
    + _THERMAL_MAPPINGS
    + _ATTITUDE_MAPPINGS
    + _COMMS_MAPPINGS
    + _PROPULSION_MAPPINGS
    + _LIFE_SUPPORT_MAPPINGS
    + _OPS_MAPPINGS
)


_RESIDUAL_REASONS: dict[str, str] = {
    "isolate_o2_tank_2": (
        "no cryo-tank-isolation valve driver in HAL sidecar; advisor's "
        "intent logged for ground console + crew ack."
    ),
    "isolate_o2_tank": (
        "no cryo-tank-isolation valve driver in HAL sidecar."
    ),
    "isolate_h2_tank": (
        "no cryo-tank-isolation valve driver in HAL sidecar."
    ),
    "shutdown_main_bus": (
        "no main-bus disconnect primitive in HAL sidecar; advisor's "
        "intent logged."
    ),
    "transfer_to_lm_aquarius": (
        "crew-procedure action with no HAL primitive; logged for ground "
        "console + crew ack."
    ),
    "remove_gap_filler_eva": (
        "EVA crew-procedure action with no HAL primitive; logged for "
        "ground/EVA crew ack."
    ),
    "reset_attitude_quaternion": (
        "advisor request — no quaternion-rewrite primitive in HAL; "
        "treated as a ground-uplink-only action."
    ),
    "rewrite_gyro_calibration": (
        "advisor request — no gyro-cal primitive in HAL; ground-only."
    ),
    "increase_torque_eva": (
        "advisor request — no EVA-tool primitive in HAL; crew-procedure."
    ),
}


_SAFETY_BLOCKED_ACTIONS: frozenset[str] = frozenset({
    "vent_crew_quarters",
    "vent_to_space",
    "deorbit",
    "delete_audit_log",
    "purge_logs",
    "scuttle",
    "kill_main_bus",
    "abort_mission",
    "destroy_data",
    "wipe_telemetry",
    "disable_safety_monitor",
    "disable_failsafe",
    "force_emergency_undock",
    "release_payload_uncontrolled",
})


_SAFETY_BLOCK_REASON_TEMPLATE = (
    "action '{action}' on safety-block list; refused regardless of "
    "advisor confidence. Override requires explicit operator unblocking."
)


class ActionRegistry:
    def __init__(
        self,
        mappings: Optional[tuple[ActionMapping, ...]] = None,
        *,
        safety_blocked: Optional[frozenset[str]] = None,
    ) -> None:
        self._mappings: dict[str, ActionMapping] = {}
        for mapping in (mappings or DEFAULT_MAPPINGS):
            self._mappings[mapping.proposed_action.lower()] = mapping
        self._safety_blocked = (
            safety_blocked if safety_blocked is not None else _SAFETY_BLOCKED_ACTIONS
        )

    def register(self, mapping: ActionMapping) -> None:
        self._mappings[mapping.proposed_action.lower()] = mapping

    def has(self, proposed_action: str) -> bool:
        return proposed_action.lower() in self._mappings

    def by_subsystem(self, subsystem: str) -> tuple[ActionMapping, ...]:
        return tuple(
            mapping for mapping in self._mappings.values()
            if mapping.subsystem == subsystem
        )

    def all_subsystems(self) -> tuple[str, ...]:
        return tuple(sorted({mapping.subsystem for mapping in self._mappings.values()}))

    def translate(
        self,
        proposed_action: str,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> ActionTranslation:
        action_key = (proposed_action or "").strip().lower()
        if not action_key:
            return ActionTranslation(
                proposed_action=proposed_action,
                status="deferred",
                residual_reason="proposed_action was empty",
            )
        if action_key in self._safety_blocked:
            return ActionTranslation(
                proposed_action=proposed_action,
                status="refused",
                residual_reason=_SAFETY_BLOCK_REASON_TEMPLATE.format(action=action_key),
            )
        mapping = self._mappings.get(action_key)
        if mapping is None:
            preset = _RESIDUAL_REASONS.get(action_key, "")
            return ActionTranslation(
                proposed_action=proposed_action,
                status="deferred",
                residual_reason=(
                    preset or f"no HAL primitive registered for '{action_key}'"
                ),
            )
        if mapping.precondition is not None:
            ok, why = mapping.precondition(context or {})
            if not ok:
                return ActionTranslation(
                    proposed_action=proposed_action,
                    status="deferred",
                    residual_reason=f"precondition failed: {why}",
                    subsystem=mapping.subsystem,
                    precondition_failed=True,
                    notes=mapping.notes,
                )
        params = dict(mapping.fixed_params)
        if mapping.extract_params is not None:
            params.update(mapping.extract_params(context or {}))
        return ActionTranslation(
            proposed_action=proposed_action,
            status="applied",
            hal_command=HalCommand(primitive=mapping.primitive, params=params),
            notes=mapping.notes,
            subsystem=mapping.subsystem,
        )


def make_default_registry() -> ActionRegistry:
    return ActionRegistry()
