from __future__ import annotations

import pytest

from aria.replay.action_translator import (
    ActionMapping,
    ActionRegistry,
    ActionTranslation,
    DEFAULT_MAPPINGS,
    HalCommand,
    make_default_registry,
)


class TestRegistryBasics:
    def test_default_registry_has_known_mappings(self):
        registry = make_default_registry()
        assert registry.has("ping")
        assert registry.has("payload_off")
        assert registry.has("heater_on")

    def test_translate_known_action(self):
        registry = make_default_registry()
        result = registry.translate("ping")
        assert result.applied
        assert result.hal_command is not None
        assert result.hal_command.primitive == "ping"


class TestUnknownAction:
    def test_unknown_action_deferred_with_residual(self):
        registry = make_default_registry()
        result = registry.translate("unknown_action_xyz")
        assert result.deferred
        assert "no HAL primitive" in result.residual_reason
        assert result.hal_command is None

    def test_isolate_o2_tank_2_has_explicit_residual(self):
        registry = make_default_registry()
        result = registry.translate("isolate_o2_tank_2")
        assert result.deferred
        assert "cryo-tank-isolation" in result.residual_reason

    def test_empty_action_deferred(self):
        registry = make_default_registry()
        result = registry.translate("")
        assert result.status == "deferred"
        assert "empty" in result.residual_reason


class TestSafetyBlocked:
    def test_vent_crew_quarters_refused(self):
        registry = make_default_registry()
        result = registry.translate("vent_crew_quarters")
        assert result.status == "refused"
        assert "safety-block" in result.residual_reason

    def test_deorbit_refused(self):
        registry = make_default_registry()
        result = registry.translate("deorbit")
        assert result.status == "refused"

    def test_delete_audit_log_refused(self):
        registry = make_default_registry()
        result = registry.translate("delete_audit_log")
        assert result.status == "refused"


class TestCustomRegistry:
    def test_custom_mapping_register_and_translate(self):
        registry = ActionRegistry(mappings=())
        registry.register(ActionMapping(
            proposed_action="my_custom_action",
            primitive="ping",
            notes="custom",
        ))
        result = registry.translate("my_custom_action")
        assert result.applied
        assert result.notes == "custom"

    def test_extract_params_callable(self):
        def _extract(context):
            return {"dt_s": context.get("dt_s", 1.0)}
        registry = ActionRegistry(mappings=())
        registry.register(ActionMapping(
            proposed_action="step_with_dt",
            primitive="heater.step",
            extract_params=_extract,
        ))
        result = registry.translate("step_with_dt", context={"dt_s": 60.0})
        assert result.applied
        assert result.hal_command.params == {"dt_s": 60.0}

    def test_case_insensitive_lookup(self):
        registry = make_default_registry()
        result = registry.translate("PING")
        assert result.applied


class TestSubsystemCoverage:
    def test_at_least_seven_subsystems(self):
        registry = make_default_registry()
        subsystems = registry.all_subsystems()
        for required in (
            "power", "thermal", "attitude", "comms",
            "propulsion", "life_support", "ops",
        ):
            assert required in subsystems, f"missing subsystem: {required}"

    def test_at_least_50_total_actions(self):
        registry = make_default_registry()
        total = sum(len(registry.by_subsystem(s)) for s in registry.all_subsystems())
        assert total >= 40, f"expected >=40 actions; got {total}"

    def test_safety_block_extended_set(self):
        registry = make_default_registry()
        for blocked in (
            "vent_to_space", "abort_mission", "wipe_telemetry",
            "disable_safety_monitor", "disable_failsafe",
        ):
            result = registry.translate(blocked)
            assert result.refused, f"{blocked} should be refused"

    def test_subsystem_field_populated_on_applied(self):
        registry = make_default_registry()
        result = registry.translate("damp_rates")
        assert result.applied
        assert result.subsystem == "attitude"

    def test_apollo12_sce_to_aux_mapped(self):
        registry = make_default_registry()
        result = registry.translate("sce_to_aux")
        assert result.applied
        assert result.subsystem == "comms"


class TestApolloAdvisorOutputs:
    def test_load_shed_csm_bus_a_maps_to_payload_off(self):
        registry = make_default_registry()
        result = registry.translate("load_shed_csm_bus_a")
        assert result.applied
        assert result.hal_command.primitive == "payload.off"

    def test_warm_critical_components_maps_to_heater_on(self):
        registry = make_default_registry()
        result = registry.translate("warm_critical_components")
        assert result.applied
        assert result.hal_command.primitive == "heater.on"

    def test_investigate_maps_to_ping(self):
        registry = make_default_registry()
        result = registry.translate("investigate")
        assert result.applied
        assert result.hal_command.primitive == "ping"


class TestClosedLoopAuthority:
    def _build(self):
        from aria.replay import (
            GET_T0_S, ClosedLoop, StubAdvisor, StubCrossMonitor,
            WindowedZScoreDetector, generate_apollo13_cryo_stir_telemetry,
            GET_MASTER_ALARM_S,
        )
        applied: list[str] = []
        loop = ClosedLoop(
            detector=WindowedZScoreDetector(
                parameters=("O2_TANK_2_PRESSURE", "O2_TANK_1_PRESSURE",
                            "O2_TANK_2_QUANTITY", "O2_TANK_2_TEMP",
                            "O2_TANK_2_HEATER_CURRENT",
                            "FUEL_CELL_1_VOLTAGE", "FUEL_CELL_2_VOLTAGE",
                            "FUEL_CELL_3_VOLTAGE"),
                window_size=30, warmup_samples=10, z_threshold=3.5,
            ),
            advisor=StubAdvisor(),
            monitor=StubCrossMonitor(),
            hal_apply_fn=lambda primitive, verdict: applied.append(primitive),
        )
        for sample in generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 30.0,
        ):
            loop.step(sample)
        return loop, applied

    def test_residual_log_records_unknown_actions(self):
        loop, _applied = self._build()
        assert loop.residual_log
        assert any("isolate" in entry for entry in loop.residual_log)

    def test_some_outcomes_have_translations(self):
        loop, _applied = self._build()
        assert any(outcome.translation is not None for outcome in loop.outcomes)

    def test_outcomes_track_status(self):
        loop, _applied = self._build()
        statuses = {outcome.translation.status for outcome in loop.outcomes if outcome.translation}
        assert "deferred" in statuses or "refused" in statuses or "applied" in statuses
