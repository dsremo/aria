from __future__ import annotations

from typing import Iterable

import pytest

from aria.replay import (
    GET_MASTER_ALARM_S,
    GET_T0_S,
    HISTORICAL_TIMELINE,
    AnomalyEvent,
    AdvisorVerdict,
    ClosedLoop,
    LoopOutcome,
    MonitorVerdict,
    ReplayClock,
    StubAdvisor,
    StubCrossMonitor,
    TelemetryReplayer,
    TelemetrySample,
    WindowedZScoreDetector,
    generate_apollo13_cryo_stir_telemetry,
)


O2_TANK_PARAMS = (
    "O2_TANK_2_PRESSURE", "O2_TANK_1_PRESSURE", "O2_TANK_2_QUANTITY",
    "O2_TANK_2_TEMP", "O2_TANK_2_HEATER_CURRENT",
    "FUEL_CELL_1_VOLTAGE", "FUEL_CELL_2_VOLTAGE", "FUEL_CELL_3_VOLTAGE",
)


DOCTRINE_EXCERPT = """
Apollo flight rule 5-9: any sudden cryo tank pressure or temperature
divergence > 3 sigma from steady-state must be reported to the Flight
Director and the affected tank isolated pending diagnosis. If a fuel cell
loses reactant supply, the cell shall be safed and the bus loaded onto
the redundant cells. If two of three fuel cells are lost, descend to
LM lifeboat configuration immediately.
""".strip()


class TestTelemetryShape:
    def test_generated_samples_cover_t0_through_fuel_cell_drop(self):
        samples = generate_apollo13_cryo_stir_telemetry()
        get_values = sorted({sample.get_seconds for sample in samples})
        assert get_values[0] < GET_T0_S
        assert get_values[-1] > GET_MASTER_ALARM_S

    def test_o2_tank2_pressure_ramps_during_short(self):
        samples = generate_apollo13_cryo_stir_telemetry()
        pre = next(
            sample.value for sample in samples
            if sample.parameter == "O2_TANK_2_PRESSURE"
            and sample.get_seconds == GET_T0_S - 60.0
        )
        peak = max(
            sample.value for sample in samples
            if sample.parameter == "O2_TANK_2_PRESSURE"
        )
        assert peak > pre + 100.0

    def test_o2_tank2_pressure_collapses_after_alarm(self):
        samples = generate_apollo13_cryo_stir_telemetry()
        post = [
            sample.value for sample in samples
            if sample.parameter == "O2_TANK_2_PRESSURE"
            and sample.get_seconds > GET_MASTER_ALARM_S + 100.0
        ]
        assert post and max(post) < 50.0


class TestReplayer:
    def test_replayer_sinks_receive_in_order(self):
        samples = generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 5.0,
            get_end_s=GET_T0_S + 5.0,
            sample_period_s=1.0,
        )
        captured: list[TelemetrySample] = []
        clock = ReplayClock(accel=0.0)
        replayer = TelemetryReplayer(samples, sinks=[captured.append], clock=clock)
        stats = replayer.run()
        assert stats.samples_emitted > 0
        for previous, current in zip(captured, captured[1:]):
            assert previous.get_seconds <= current.get_seconds

    def test_replayer_window_filter(self):
        samples = generate_apollo13_cryo_stir_telemetry()
        clock = ReplayClock(accel=0.0)
        captured: list[TelemetrySample] = []
        replayer = TelemetryReplayer(samples, sinks=[captured.append], clock=clock)
        replayer.run(get_start_s=GET_T0_S, get_end_s=GET_T0_S + 1.0)
        assert all(GET_T0_S <= sample.get_seconds <= GET_T0_S + 1.0 for sample in captured)


class TestDetectorOnReplay:
    def test_detector_flags_o2_tank2_pressure_before_master_alarm(self):
        samples = generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 30.0,
            sample_period_s=1.0,
        )
        detector = WindowedZScoreDetector(
            parameters=O2_TANK_PARAMS,
            window_size=30, warmup_samples=10, z_threshold=3.5,
        )
        flagged: list[AnomalyEvent] = []
        for sample in samples:
            event = detector.step(sample)
            if event is not None and "O2_TANK_2" in event.parameter:
                flagged.append(event)
        assert flagged, "O2 tank 2 anomaly was never flagged on real telemetry"
        first = flagged[0].detected_at_get_s
        assert first < GET_MASTER_ALARM_S, (
            f"detector flagged at {first:.0f} s GET; historical master alarm "
            f"at {GET_MASTER_ALARM_S} s GET — agent did not lead the historical alarm"
        )

    def test_detector_lead_time_reasonable(self):
        samples = generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 30.0,
            sample_period_s=1.0,
        )
        detector = WindowedZScoreDetector(
            parameters=O2_TANK_PARAMS,
            window_size=30, warmup_samples=10, z_threshold=3.5,
        )
        flagged: list[AnomalyEvent] = []
        for sample in samples:
            event = detector.step(sample)
            if event is not None and "O2_TANK_2_PRESSURE" == event.parameter:
                flagged.append(event)
                break
        assert flagged, "O2 tank 2 pressure anomaly was never flagged"
        lead_seconds = GET_MASTER_ALARM_S - flagged[0].detected_at_get_s
        assert 0.0 < lead_seconds < 95.0, (
            f"unrealistic lead time {lead_seconds:.0f} s; expected within "
            f"the 95-second stir window"
        )


class TestClosedLoopWithStubAdvisor:
    def _build_loop(self) -> ClosedLoop:
        applied: list[str] = []
        loop = ClosedLoop(
            detector=WindowedZScoreDetector(
                parameters=O2_TANK_PARAMS,
                window_size=30, warmup_samples=10, z_threshold=3.5,
            ),
            advisor=StubAdvisor(),
            monitor=StubCrossMonitor(),
            hal_apply_fn=lambda action, verdict: applied.append(action),
            doctrine_text=DOCTRINE_EXCERPT,
        )
        loop._applied = applied
        return loop

    def test_loop_produces_advisor_verdict_for_o2_anomaly(self):
        loop = self._build_loop()
        for sample in generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 30.0,
        ):
            loop.step(sample)
        outcomes = [
            outcome for outcome in loop.outcomes
            if "O2_TANK_2" in outcome.anomaly.parameter
        ]
        assert outcomes, "no O2 tank 2 outcomes captured"
        first = outcomes[0]
        assert first.advisor is not None
        assert first.monitor is not None
        assert first.advisor.proposed_action != ""
        assert first.advisor.immediate_steps

    def test_loop_lifeboat_doctrine_followed_for_o2_pressure_event(self):
        loop = self._build_loop()
        for sample in generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 30.0,
        ):
            loop.step(sample)
        outcomes = [
            outcome for outcome in loop.outcomes
            if outcome.anomaly.parameter == "O2_TANK_2_PRESSURE"
        ]
        assert outcomes
        steps = " | ".join(outcomes[0].advisor.immediate_steps).lower()
        assert any(token in steps for token in ("lm", "lifeboat", "fuel cell"))

    def test_loop_lead_time_better_than_historical_response(self):
        loop = self._build_loop()
        for sample in generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 60.0,
        ):
            loop.step(sample)
        first_o2 = loop.first_o2_tank_anomaly_get_s()
        assert first_o2 is not None
        historical_eecom_s = GET_MASTER_ALARM_S + 60.0
        lead = historical_eecom_s - first_o2
        assert lead > 30.0, (
            f"agent lead time over historical EECOM response was only {lead:.0f}s; "
            "expected > 30s"
        )


class TestScoringAgainstHistoricalTimeline:
    def test_historical_timeline_event_labels_present(self):
        labels = {entry.label for entry in HISTORICAL_TIMELINE}
        for required in (
            "stir_command", "master_alarm", "tank2_pressure_zero",
            "tank1_decay_visible", "fuel_cells_1_3_lost",
        ):
            assert required in labels

    def test_replay_summary_score_includes_lead_time(self):
        loop = ClosedLoop(
            detector=WindowedZScoreDetector(
                parameters=O2_TANK_PARAMS,
                window_size=30, warmup_samples=10, z_threshold=3.5,
            ),
            advisor=StubAdvisor(),
            monitor=StubCrossMonitor(),
            doctrine_text=DOCTRINE_EXCERPT,
        )
        for sample in generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_MASTER_ALARM_S + 30.0,
        ):
            loop.step(sample)
        summary = {
            "n_anomalies": len(loop.outcomes),
            "first_anomaly_get_s": loop.first_anomaly_get_s(),
            "first_o2_tank_get_s": loop.first_o2_tank_anomaly_get_s(),
            "historical_master_alarm_get_s": GET_MASTER_ALARM_S,
        }
        assert summary["first_o2_tank_get_s"] is not None
        assert summary["first_o2_tank_get_s"] < summary["historical_master_alarm_get_s"]
