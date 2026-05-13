"""Tests for ARIA Health Dashboard — comprehensive system health aggregation."""

import time

import pytest

from aria.dashboard.health_dashboard import DashboardSnapshot, HealthDashboard, SubsystemHealth


class TestDashboardBasics:
    """Basic dashboard operations."""

    def test_create_dashboard(self) -> None:
        dash = HealthDashboard(mission_name="Test")
        snap = dash.snapshot()
        assert snap.mission_name == "Test"
        assert snap.overall_status == "NOMINAL"

    def test_uptime_tracking(self) -> None:
        dash = HealthDashboard()
        time.sleep(0.05)
        snap = dash.snapshot()
        assert snap.uptime_s >= 0.04

    def test_timestamp_populated(self) -> None:
        dash = HealthDashboard()
        snap = dash.snapshot()
        assert snap.timestamp > 0


class TestOrbitUpdates:
    def test_update_orbit(self) -> None:
        dash = HealthDashboard()
        dash.update_orbit(altitude_km=400, velocity_m_s=7673, latitude_deg=25.5, in_eclipse=False)
        snap = dash.snapshot()
        assert snap.altitude_km == 400
        assert snap.velocity_m_s == 7673
        assert snap.latitude_deg == 25.5
        assert not snap.in_eclipse


class TestPowerUpdates:
    def test_update_power(self) -> None:
        dash = HealthDashboard()
        dash.update_power(battery_soc=85, solar_w=2722, load_w=200, bus_v=28.0)
        snap = dash.snapshot()
        assert snap.battery_soc_pct == 85
        assert snap.solar_power_w == 2722

    def test_low_battery_warning(self) -> None:
        dash = HealthDashboard()
        dash.update_power(battery_soc=20)
        snap = dash.snapshot()
        assert snap.overall_status == "WARNING"

    def test_critical_battery(self) -> None:
        dash = HealthDashboard()
        dash.update_power(battery_soc=10)
        snap = dash.snapshot()
        assert snap.overall_status == "CRITICAL"

    def test_emergency_battery(self) -> None:
        dash = HealthDashboard()
        dash.update_power(battery_soc=3)
        snap = dash.snapshot()
        assert snap.overall_status == "EMERGENCY"


class TestECLSSUpdates:
    def test_update_eclss(self) -> None:
        dash = HealthDashboard()
        dash.update_eclss(o2_pct=20.9, co2_ppm=400, pressure_psi=14.7)
        snap = dash.snapshot()
        assert snap.o2_percent == 20.9
        assert snap.co2_ppm == 400

    def test_low_o2_critical(self) -> None:
        dash = HealthDashboard()
        dash.update_eclss(o2_pct=18.5)
        snap = dash.snapshot()
        assert snap.overall_status == "CRITICAL"

    def test_emergency_o2(self) -> None:
        dash = HealthDashboard()
        dash.update_eclss(o2_pct=17)
        snap = dash.snapshot()
        assert snap.overall_status == "EMERGENCY"

    def test_high_co2_warning(self) -> None:
        dash = HealthDashboard()
        dash.update_eclss(co2_ppm=6000)
        snap = dash.snapshot()
        assert snap.overall_status == "WARNING"


class TestSubsystemHealth:
    def test_update_subsystem(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("power", status="NOMINAL", alerts=0, dsremo_score=0.1)
        snap = dash.snapshot()
        assert "power" in snap.subsystems
        assert snap.subsystems["power"].status == "NOMINAL"

    def test_multiple_subsystems(self) -> None:
        dash = HealthDashboard()
        for name in ["power", "thermal", "eclss", "navigation", "propulsion"]:
            dash.update_subsystem(name, status="NOMINAL")
        snap = dash.snapshot()
        assert len(snap.subsystems) == 5

    def test_critical_subsystem_escalates(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("power", status="CRITICAL")
        snap = dash.snapshot()
        assert snap.overall_status == "CRITICAL"
        assert snap.active_critical == 1

    def test_two_critical_is_emergency(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("power", status="CRITICAL")
        dash.update_subsystem("thermal", status="CRITICAL")
        snap = dash.snapshot()
        assert snap.overall_status == "EMERGENCY"

    def test_warning_subsystem(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("comms", status="WARNING")
        snap = dash.snapshot()
        assert snap.overall_status == "WARNING"
        assert snap.active_warnings == 1

    def test_dsremo_score_warning(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("power", dsremo_score=0.6)
        snap = dash.snapshot()
        assert snap.dsremo_max_score == 0.6
        assert snap.overall_status == "WARNING"

    def test_dsremo_score_critical(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("thermal", dsremo_score=0.85)
        snap = dash.snapshot()
        assert snap.overall_status == "CRITICAL"


class TestAlerts:
    def test_record_alert(self) -> None:
        dash = HealthDashboard()
        dash.record_alert("WARNING", "power", "Battery low")
        snap = dash.snapshot()
        assert snap.total_alerts == 1
        assert snap.severity_distribution["WARNING"] == 1

    def test_multiple_alerts(self) -> None:
        dash = HealthDashboard()
        for _ in range(10):
            dash.record_alert("WARNING", "power")
        for _ in range(3):
            dash.record_alert("CRITICAL", "thermal")
        snap = dash.snapshot()
        assert snap.total_alerts == 13
        assert snap.severity_distribution["WARNING"] == 10
        assert snap.severity_distribution["CRITICAL"] == 3

    def test_recent_alerts(self) -> None:
        dash = HealthDashboard()
        for i in range(30):
            dash.record_alert("WARNING", f"sub_{i}")
        recent = dash.recent_alerts(limit=10)
        assert len(recent) == 10

    def test_alert_history_capped(self) -> None:
        dash = HealthDashboard()
        for i in range(600):
            dash.record_alert("WATCH", "test")
        recent = dash.recent_alerts(limit=1000)
        assert len(recent) <= 500


class TestOverallStatus:
    def test_nominal_default(self) -> None:
        dash = HealthDashboard()
        assert dash.snapshot().overall_status == "NOMINAL"

    def test_caution_eclipse_low_battery(self) -> None:
        dash = HealthDashboard()
        dash.update_orbit(in_eclipse=True)
        dash.update_power(battery_soc=50)
        snap = dash.snapshot()
        assert snap.overall_status == "CAUTION"

    def test_caution_dsremo_moderate(self) -> None:
        dash = HealthDashboard()
        dash.update_subsystem("nav", dsremo_score=0.35)
        snap = dash.snapshot()
        assert snap.overall_status == "CAUTION"

    def test_voltage_warning(self) -> None:
        dash = HealthDashboard()
        dash.update_power(battery_soc=90, bus_v=23)
        snap = dash.snapshot()
        assert snap.overall_status == "WARNING"

    def test_priority_highest_wins(self) -> None:
        """EMERGENCY should win even if other things are nominal."""
        dash = HealthDashboard()
        dash.update_power(battery_soc=2)  # EMERGENCY
        dash.update_eclss(o2_pct=20.9)    # NOMINAL
        snap = dash.snapshot()
        assert snap.overall_status == "EMERGENCY"


class TestSnapshotSerialization:
    def test_to_dict(self) -> None:
        dash = HealthDashboard(mission_name="Test-Serialize")
        dash.update_orbit(altitude_km=400, velocity_m_s=7673)
        dash.update_power(battery_soc=80, solar_w=2722)
        dash.update_subsystem("power", status="NOMINAL", dsremo_score=0.1)
        dash.record_alert("WARNING", "test")

        d = dash.snapshot().to_dict()
        assert d["mission"]["name"] == "Test-Serialize"
        assert d["orbit"]["altitude_km"] == 400
        assert d["power"]["battery_soc_pct"] == 80
        assert d["alerts"]["total"] == 1
        assert "power" in d["subsystems"]
        assert d["overall_status"] == "NOMINAL"

    def test_to_dict_complete(self) -> None:
        """All expected top-level keys exist."""
        d = DashboardSnapshot().to_dict()
        expected = {"timestamp", "uptime_s", "mission", "orbit", "power",
                    "eclss", "subsystems", "alerts", "system", "challenges", "overall_status"}
        assert expected == set(d.keys())


class TestBasiliskFrameIntegration:
    def test_update_from_frame(self) -> None:
        """Test Basilisk frame → dashboard update."""
        try:
            from aria.simulation.basilisk_runner import TelemetryFrame
        except ImportError:
            pytest.skip("Basilisk not available")

        dash = HealthDashboard()
        frame = TelemetryFrame(
            timestamp_s=100.0,
            altitude_km=400.5,
            orbital_velocity_m_s=7673.0,
            ground_track_lat_deg=25.0,
            ground_track_lon_deg=50.0,
            in_eclipse=False,
            battery_soc=0.85,
            solar_power_w=2722.0,
            power_draw_w=200.0,
        )
        dash.update_from_basilisk_frame(frame)

        snap = dash.snapshot()
        assert snap.altitude_km == 400.5
        assert snap.velocity_m_s == 7673.0
        assert snap.battery_soc_pct == 85.0
        assert snap.solar_power_w == 2722.0
        assert snap.overall_status == "NOMINAL"
