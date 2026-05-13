"""Tests for aria.digital_twin.radiation_geometry — shield config bridge."""

from __future__ import annotations

import pytest

from aria.digital_twin.parameters import ShipParameters
from aria.digital_twin.radiation_geometry import (
    create_shield_config_from_geometry,
    run_radiation_analysis,
)


# ════════════════════════════════════════════════════════════════
#  FIXTURES
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def params() -> ShipParameters:
    return ShipParameters()


@pytest.fixture
def shield_config(params: ShipParameters) -> list:
    return create_shield_config_from_geometry(params)


# ════════════════════════════════════════════════════════════════
#  SHIELD CONFIG
# ════════════════════════════════════════════════════════════════

class TestShieldConfig:

    def test_seven_layers(self, shield_config):
        """Default ShipParameters has exactly 7 shield layers."""
        assert len(shield_config) == 7

    def test_areal_densities_positive(self, shield_config):
        """Every layer with nonzero thickness must have positive areal density."""
        for layer in shield_config:
            if layer["thickness_m"] > 0:
                assert layer["areal_density_g_cm2"] > 0.0, (
                    f"Layer {layer['name']} has non-positive areal density"
                )

    def test_areal_density_formula(self, shield_config):
        """areal_density = thickness_m * density * 100."""
        for layer in shield_config:
            expected = layer["thickness_m"] * layer["density_g_cm3"] * 100.0
            assert layer["areal_density_g_cm2"] == pytest.approx(expected, rel=1e-6)

    def test_ablation_ice_thickest(self, shield_config):
        """Ablation ice (5.45 m) should dominate areal density."""
        ablation = [l for l in shield_config if "ablation" in l["name"]]
        assert len(ablation) == 1
        assert ablation[0]["areal_density_g_cm2"] > 100.0

    def test_layer_names_match_params(self, params, shield_config):
        """Config layer names should match ShipParameters layer names."""
        expected_names = [l.name for l in params.shield_layers]
        actual_names = [l["name"] for l in shield_config]
        assert actual_names == expected_names

    def test_all_layers_have_required_keys(self, shield_config):
        """Each layer dict must contain all required keys."""
        required = {"name", "thickness_m", "material", "density_g_cm3", "areal_density_g_cm2"}
        for layer in shield_config:
            assert required.issubset(layer.keys()), (
                f"Layer {layer.get('name', '?')} missing keys: "
                f"{required - set(layer.keys())}"
            )


# ════════════════════════════════════════════════════════════════
#  RADIATION ANALYSIS
# ════════════════════════════════════════════════════════════════

class TestRadiationAnalysis:

    def test_returns_dose(self, params):
        """run_radiation_analysis should return a dict with total_dose_msv."""
        result = run_radiation_analysis(params, velocity_c=0.1, n_particles=50)
        assert "total_dose_msv" in result
        assert result["total_dose_msv"] >= 0.0

    def test_dose_by_organ_present(self, params):
        result = run_radiation_analysis(params, velocity_c=0.1, n_particles=50)
        assert "dose_by_organ" in result
        assert isinstance(result["dose_by_organ"], dict)
        assert len(result["dose_by_organ"]) > 0

    def test_particles_simulated_matches(self, params):
        n = 80
        result = run_radiation_analysis(params, velocity_c=0.1, n_particles=n)
        assert result["particles_simulated"] == n

    def test_shield_config_included(self, params):
        result = run_radiation_analysis(params, velocity_c=0.1, n_particles=50)
        assert "shield_config" in result
        assert len(result["shield_config"]) == 7
