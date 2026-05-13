"""Tests for NRLMSISE-00 atmospheric density model."""

from datetime import datetime

import pytest

try:
    from nrlmsise00 import msise_model  # noqa: F401
    _HAS_NRLMSISE = True
except ImportError:
    _HAS_NRLMSISE = False

from aria.conjunction.analysis.atmosphere import AtmosphereResult, AtmosphericDensityModel  # noqa: E402

pytestmark = pytest.mark.skipif(
    not _HAS_NRLMSISE,
    reason="nrlmsise00 package not installed"
)

DT_NOMINAL = datetime(2024, 6, 15, 12, 0, 0)


# ---------------------------------------------------------------------------
# Basic density computation
# ---------------------------------------------------------------------------

class TestAtmosphericDensityModel:

    def test_density_returns_result(self):
        model = AtmosphericDensityModel(f107=150.0, f107a=150.0, ap=4.0)
        result = model.density(400.0, dt=DT_NOMINAL)
        assert isinstance(result, AtmosphereResult)

    def test_density_positive(self):
        model = AtmosphericDensityModel()
        result = model.density(400.0, dt=DT_NOMINAL)
        assert result.total_mass_density_kg_m3 > 0.0

    def test_density_decreases_with_altitude(self):
        """Higher altitude → lower density (exponential atmosphere)."""
        model = AtmosphericDensityModel()
        low = model.density(300.0, dt=DT_NOMINAL)
        mid = model.density(500.0, dt=DT_NOMINAL)
        high = model.density(800.0, dt=DT_NOMINAL)
        assert low.total_mass_density_kg_m3 > mid.total_mass_density_kg_m3
        assert mid.total_mass_density_kg_m3 > high.total_mass_density_kg_m3

    def test_leo_density_order_of_magnitude(self):
        """LEO (~400 km) density should be ~1e-12 kg/m³ (rough NRLMSISE range)."""
        model = AtmosphericDensityModel()
        result = model.density(400.0, dt=DT_NOMINAL)
        rho = result.total_mass_density_kg_m3
        assert 1e-15 < rho < 1e-9, f"Density {rho:.2e} out of expected range"

    def test_density_with_lat_lon(self):
        """Density call with explicit lat/lon should work."""
        model = AtmosphericDensityModel()
        r1 = model.density(400.0, latitude_deg=0.0, longitude_deg=0.0, dt=DT_NOMINAL)
        r2 = model.density(400.0, latitude_deg=45.0, longitude_deg=90.0, dt=DT_NOMINAL)
        # Both should be positive (not equal due to solar flux angle)
        assert r1.total_mass_density_kg_m3 > 0.0
        assert r2.total_mass_density_kg_m3 > 0.0

    def test_density_default_dt(self):
        """When dt=None, should use default date without error."""
        model = AtmosphericDensityModel()
        result = model.density(400.0)
        assert result.total_mass_density_kg_m3 > 0.0

    def test_temperatures_positive(self):
        model = AtmosphericDensityModel()
        result = model.density(400.0, dt=DT_NOMINAL)
        assert result.temperature_exospheric_K > 0.0
        assert result.temperature_local_K > 0.0

    def test_number_densities_nonnegative(self):
        model = AtmosphericDensityModel()
        result = model.density(400.0, dt=DT_NOMINAL)
        assert result.n_He >= 0.0
        assert result.n_O >= 0.0
        assert result.n_N2 >= 0.0
        assert result.n_O2 >= 0.0


# ---------------------------------------------------------------------------
# Solar activity effect
# ---------------------------------------------------------------------------

class TestSolarActivityEffect:

    def test_solar_max_denser_than_solar_min(self):
        """Solar maximum → higher UV heating → expanded, denser upper atmosphere."""
        model_min = AtmosphericDensityModel(f107=70.0, f107a=70.0, ap=4.0)
        model_max = AtmosphericDensityModel(f107=250.0, f107a=250.0, ap=4.0)
        rho_min = model_min.density(500.0, dt=DT_NOMINAL).total_mass_density_kg_m3
        rho_max = model_max.density(500.0, dt=DT_NOMINAL).total_mass_density_kg_m3
        assert rho_max > rho_min

    def test_geomag_storm_increases_density(self):
        """Geomagnetic storm → Joule heating → higher density in thermosphere."""
        model_quiet = AtmosphericDensityModel(f107=150.0, f107a=150.0, ap=4.0)
        model_storm = AtmosphericDensityModel(f107=150.0, f107a=150.0, ap=200.0)
        rho_quiet = model_quiet.density(400.0, dt=DT_NOMINAL).total_mass_density_kg_m3
        rho_storm = model_storm.density(400.0, dt=DT_NOMINAL).total_mass_density_kg_m3
        assert rho_storm > rho_quiet


# ---------------------------------------------------------------------------
# Density profile
# ---------------------------------------------------------------------------

class TestDensityProfile:

    def test_profile_shape(self):
        model = AtmosphericDensityModel()
        alts, densities = model.density_profile(
            alt_min_km=200.0, alt_max_km=800.0, n_points=10, dt=DT_NOMINAL
        )
        assert len(alts) == 10
        assert len(densities) == 10

    def test_profile_monotonic_decrease(self):
        model = AtmosphericDensityModel()
        alts, densities = model.density_profile(
            alt_min_km=200.0, alt_max_km=800.0, n_points=20, dt=DT_NOMINAL
        )
        assert all(densities[i] >= densities[i + 1] for i in range(len(densities) - 1))

    def test_profile_all_positive(self):
        model = AtmosphericDensityModel()
        _, densities = model.density_profile(
            alt_min_km=200.0, alt_max_km=600.0, n_points=5, dt=DT_NOMINAL
        )
        assert all(d > 0 for d in densities)


# ---------------------------------------------------------------------------
# Drag acceleration
# ---------------------------------------------------------------------------

class TestDragAcceleration:

    def test_drag_acceleration_positive(self):
        model = AtmosphericDensityModel()
        a = model.drag_acceleration(
            altitude_km=400.0, velocity_km_s=7.66,
            cd=2.2, area_m2=10.0, mass_kg=1000.0, dt=DT_NOMINAL
        )
        assert a > 0.0

    def test_drag_higher_at_lower_altitude(self):
        model = AtmosphericDensityModel()
        a_low = model.drag_acceleration(300.0, 7.7, dt=DT_NOMINAL)
        a_high = model.drag_acceleration(600.0, 7.6, dt=DT_NOMINAL)
        assert a_low > a_high

    def test_drag_proportional_to_area_mass_ratio(self):
        """Drag ∝ A/m — doubling area/mass ratio doubles acceleration."""
        model = AtmosphericDensityModel()
        a1 = model.drag_acceleration(400.0, 7.66, cd=2.2, area_m2=5.0, mass_kg=500.0)
        a2 = model.drag_acceleration(400.0, 7.66, cd=2.2, area_m2=10.0, mass_kg=500.0)
        assert a2 == pytest.approx(a1 * 2.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Compare solar conditions
# ---------------------------------------------------------------------------

class TestCompareSolarConditions:

    def test_compare_returns_five_conditions(self):
        model = AtmosphericDensityModel()
        result = model.compare_solar_conditions(400.0)
        assert "solar_minimum" in result
        assert "solar_maximum" in result
        assert "geomag_storm" in result
        assert "extreme_storm" in result

    def test_solar_minimum_ratio_is_one(self):
        """Solar minimum is the baseline — ratio should be 1.0."""
        model = AtmosphericDensityModel()
        result = model.compare_solar_conditions(400.0)
        assert result["solar_minimum"] == pytest.approx(1.0)

    def test_solar_maximum_ratio_gt_one(self):
        """Solar maximum should give higher density than minimum."""
        model = AtmosphericDensityModel()
        result = model.compare_solar_conditions(400.0)
        assert result["solar_maximum"] > 1.0

    def test_extreme_storm_largest_ratio(self):
        """Extreme geomagnetic storm should give largest density."""
        model = AtmosphericDensityModel()
        result = model.compare_solar_conditions(400.0)
        assert result["extreme_storm"] >= result["solar_maximum"]


# ---------------------------------------------------------------------------
# Import error handling
# ---------------------------------------------------------------------------

class TestImportErrorHandling:

    def test_import_error_on_missing_package(self, monkeypatch):
        """AtmosphericDensityModel should raise ImportError if nrlmsise00 missing."""
        import aria.conjunction.analysis.atmosphere as atm_module
        monkeypatch.setattr(atm_module, "_HAS_NRLMSISE", False)
        with pytest.raises(ImportError, match="nrlmsise00"):
            AtmosphericDensityModel()
