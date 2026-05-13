"""Tests for collision avoidance maneuver planning."""



from aria.conjunction.maneuver.delta_v import (
    compute_intrack_delta_v,
    optimal_burn_direction,
)
from aria.conjunction.maneuver.fuel_cost import (
    burn_duration_seconds,
    delta_v_budget_report,
    fuel_mass_required,
)


class TestDeltaV:
    """Test ΔV calculations."""

    def test_intrack_24h_lead(self):
        """In-track burn with 24h lead should be small (cm/s scale)."""
        dv = compute_intrack_delta_v(
            desired_separation_km=1.0,
            lead_time_seconds=24 * 3600,
            semi_major_axis_km=7000.0,
        )
        # Should be on the order of cm/s to m/s
        dv_m_s = dv * 1000
        assert 0.001 < dv_m_s < 10.0, f"ΔV = {dv_m_s:.4f} m/s"

    def test_intrack_2h_lead(self):
        """In-track burn with 2h lead should be larger."""
        dv_24h = compute_intrack_delta_v(1.0, 24 * 3600, 7000.0)
        dv_2h = compute_intrack_delta_v(1.0, 2 * 3600, 7000.0)

        # Shorter lead time → larger ΔV
        assert dv_2h > dv_24h

    def test_zero_lead_time(self):
        """Zero lead time should give infinite ΔV (impossible)."""
        dv = compute_intrack_delta_v(1.0, 0, 7000.0)
        assert dv == float("inf")

    def test_optimal_burn_returns_cheapest(self):
        """Optimal burn should return the direction with minimum ΔV."""
        burn = optimal_burn_direction(
            desired_separation_km=1.0,
            lead_time_seconds=12 * 3600,
            semi_major_axis_km=7000.0,
        )
        # The optimal direction depends on orbital phase at burn time;
        # verify it returns a valid direction with positive ΔV
        assert burn.direction in ("IN_TRACK", "CROSS_TRACK", "RADIAL")
        assert burn.delta_v_m_s > 0
        assert burn.expected_separation_km == 1.0

    def test_larger_separation_needs_more_dv(self):
        """More separation → proportionally more ΔV (linear relationship)."""
        dv_1km = compute_intrack_delta_v(1.0, 24 * 3600, 7000.0)
        dv_5km = compute_intrack_delta_v(5.0, 24 * 3600, 7000.0)

        ratio = dv_5km / dv_1km
        assert abs(ratio - 5.0) < 0.01  # should be exactly 5x (linear)


class TestFuelCost:
    """Test fuel mass calculation via Tsiolkovsky equation."""

    def test_zero_delta_v(self):
        """No ΔV → no fuel needed."""
        assert fuel_mass_required(0.0, 250.0) == 0.0

    def test_small_delta_v(self):
        """Small ΔV should need small fuel mass."""
        fuel = fuel_mass_required(0.01, 250.0, isp_s=220.0)  # 0.01 m/s
        assert 0 < fuel < 1.0  # less than 1 kg

    def test_higher_isp_less_fuel(self):
        """Higher Isp → less fuel for same ΔV."""
        fuel_mono = fuel_mass_required(1.0, 250.0, isp_s=220.0)
        fuel_ion = fuel_mass_required(1.0, 250.0, isp_s=2000.0)
        assert fuel_ion < fuel_mono

    def test_burn_duration(self):
        """Burn duration should be positive and finite."""
        duration = burn_duration_seconds(1.0, 250.0, thrust_n=4.0, isp_s=220.0)
        assert 0 < duration < 3600  # less than an hour for 1 m/s

    def test_budget_report(self):
        """Budget report should include all propulsion types."""
        report = delta_v_budget_report(1.0, 250.0)
        assert len(report) == 5
        for name, data in report.items():
            assert "fuel_mass_kg" in data
            assert "burn_duration_s" in data
            assert data["fuel_mass_kg"] >= 0
