"""Tests for artemis2_mission.py — End-to-end Artemis 2 simulation.

Validates the full mission chain: TLI → coast → reentry → GNC.
"""

import pytest

from aria.simulation.artemis2_mission import (
    simulate_artemis2, compare_with_actual,
    Artemis2MissionResult,
    A2_PEAK_DECEL_G, SLS_TLI_DV_MS,
)


class TestArtemis2EndToEnd:
    """Full end-to-end mission simulation."""

    @pytest.fixture(scope="class")
    def result(self):
        return simulate_artemis2()

    def test_returns_result(self, result):
        assert isinstance(result, Artemis2MissionResult)

    def test_all_nominal(self, result):
        """All phases should be nominal for a successful mission."""
        assert result.all_phases_nominal is True

    def test_tli_dv_within_5pct(self, result):
        """TLI ΔV should be within 5% of published 3,140 m/s."""
        error = abs(result.tli.burn.dv_tli_ms - SLS_TLI_DV_MS) / SLS_TLI_DV_MS
        assert error < 0.05

    def test_peak_decel_within_10pct(self, result):
        """Peak deceleration should be within 10% of published 3.9 g."""
        error = abs(result.reentry.peak_decel_g - A2_PEAK_DECEL_G) / A2_PEAK_DECEL_G
        assert error < 0.10

    def test_entry_speed_mach_33(self, result):
        """Entry speed should be ~11,000 m/s (Mach 33)."""
        assert 10_500 < result.entry_speed_ms < 11_500

    def test_gnc_safe(self, result):
        """GNC corridor probability should be > 0.999."""
        assert result.gnc.probability_in_corridor > 0.999

    def test_gnc_margin_high(self, result):
        """GNC margin should be > 5σ for crewed mission."""
        assert result.gnc_margin_sigma > 5.0

    def test_debris_risk_negligible(self, result):
        """Parking orbit debris risk should be < 1e-6."""
        assert result.parking_debris_risk.probability < 1e-6

    def test_parking_period_reasonable(self, result):
        """185 km parking orbit period should be ~88 min."""
        assert 85 < result.parking_orbit_period_min < 92

    def test_coast_propagation_ran(self, result):
        """N-body coast should have used > 100 RK evaluations."""
        assert result.coast_integrator_steps > 100

    def test_reentry_is_apollo_class(self, result):
        """Orion reentry at Mach 33 should be Apollo-class."""
        assert result.reentry.is_apollo_class is True

    def test_propellant_positive(self, result):
        assert result.tli.propellant_kg > 0


class TestCompareWithActual:
    """Comparison function validation."""

    def test_returns_dict(self):
        comp = compare_with_actual()
        assert isinstance(comp, dict)

    def test_all_errors_under_20pct(self):
        comp = compare_with_actual()
        for name, vals in comp.items():
            assert vals["error_pct"] < 20, (
                f"{name}: {vals['error_pct']:.1f}% error exceeds 20% threshold"
            )

    def test_tli_dv_under_2pct(self):
        comp = compare_with_actual()
        assert comp["TLI ΔV (m/s)"]["error_pct"] < 2.0

    def test_peak_decel_under_5pct(self):
        comp = compare_with_actual()
        assert comp["Peak decel (g)"]["error_pct"] < 5.0
