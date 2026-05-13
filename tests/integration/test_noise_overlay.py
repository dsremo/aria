from __future__ import annotations

import pytest

from aria.replay import (
    GET_MASTER_ALARM_S, GET_T0_S, generate_apollo13_cryo_stir_telemetry,
    list_scenarios, get_scenario,
)
from aria.replay.noise import (
    DEFAULT_SENSOR_NOISE_PROFILES,
    SensorNoiseProfile,
    overlay_noise,
)


class TestNoiseOverlay:
    def test_clean_input_remains_close_to_original(self):
        clean = generate_apollo13_cryo_stir_telemetry(
            get_start_s=GET_T0_S - 60.0,
            get_end_s=GET_T0_S - 50.0,
            sample_period_s=1.0,
        )
        noisy = overlay_noise(clean, rng_seed=1)
        assert len(noisy) == len(clean)
        for clean_sample, noisy_sample in zip(clean, noisy):
            assert abs(clean_sample.value - noisy_sample.value) < 5.0

    def test_unknown_parameter_passes_through(self):
        from aria.replay.apollo13_cryo_stir import TelemetrySample
        samples = (TelemetrySample(0.0, "UNKNOWN_PARAM", 100.0, "x"),)
        noisy = overlay_noise(samples)
        assert noisy[0].value == 100.0


class TestProfilesCoverage:
    def test_at_least_10_profiles(self):
        assert len(DEFAULT_SENSOR_NOISE_PROFILES) >= 10

    def test_apollo_profiles_have_citation(self):
        cited = [
            profile for profile in DEFAULT_SENSOR_NOISE_PROFILES
            if profile.citation
        ]
        assert len(cited) >= 4


class TestExpandedScenarios:
    def test_all_ten_scenarios_registered(self):
        ids = list_scenarios()
        for required in (
            "apollo_13_cryo_stir", "apollo_12_lightning", "sts_114_gap_filler",
            "soho_1998_attitude_loss", "mir_spektr_collision",
            "hubble_sm4_stuck_bolt", "apollo_1_fire", "iss_quest_leak",
            "dragon_dock_abort", "hayabusa_wheel_failures",
        ):
            assert required in ids

    @pytest.mark.parametrize("scenario_id", [
        "apollo_1_fire", "iss_quest_leak",
        "dragon_dock_abort", "hayabusa_wheel_failures",
    ])
    def test_factory_produces_samples(self, scenario_id: str):
        scenario = get_scenario(scenario_id)
        samples = scenario.samples_factory()
        assert samples
        param_names = set(scenario.parameters)
        assert all(sample.parameter in param_names for sample in samples)
