"""Tests for real Basilisk spacecraft simulation runner.

Tests verify:
  - Basilisk simulation creates valid orbital mechanics
  - Telemetry extraction produces correct frames
  - ISS-like orbit parameters are physically correct
  - Ground track computation works
  - MRP to Euler conversion is accurate
"""

import math

import pytest

bsk = pytest.importorskip("Basilisk")

from aria.simulation.basilisk_runner import (
    BasiliskSimRunner,
    OrbitConfig,
    SimConfig,
    SpacecraftConfig,
    TelemetryFrame,
    eci_to_lla,
    mrp_to_euler_deg,
)


@pytest.fixture(scope="module")
def iss_runner() -> BasiliskSimRunner:
    """Create and setup an ISS-like orbit runner."""
    config = SimConfig(
        timestep_s=1.0,
        output_interval_s=60.0,
        orbit=OrbitConfig(altitude_km=400.0, inclination_deg=51.6),
    )
    runner = BasiliskSimRunner(config)
    runner.setup()
    return runner


class TestBasiliskSetup:
    """Verify Basilisk simulation initialization."""

    def test_runner_creates(self) -> None:
        config = SimConfig()
        runner = BasiliskSimRunner(config)
        assert runner is not None

    def test_setup_succeeds(self) -> None:
        config = SimConfig(orbit=OrbitConfig(altitude_km=400.0))
        runner = BasiliskSimRunner(config)
        runner.setup()
        assert runner._setup_done

    def test_different_orbits(self) -> None:
        """Can create LEO, MEO, and GEO orbits."""
        for alt in [400, 2000, 35786]:
            config = SimConfig(orbit=OrbitConfig(altitude_km=float(alt)))
            runner = BasiliskSimRunner(config)
            runner.setup()
            assert runner._setup_done


class TestOrbitalMechanics:
    """Verify Basilisk produces correct orbital mechanics."""

    def test_iss_altitude(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(60.0)
        assert len(frames) > 0
        # ISS orbit at ~400 km
        assert 390 < frames[0].altitude_km < 410

    def test_orbital_velocity(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(60.0)
        # LEO velocity: ~7.67 km/s
        v = frames[-1].orbital_velocity_m_s
        assert 7500 < v < 7800

    def test_position_changes(self, iss_runner: BasiliskSimRunner) -> None:
        """Satellite should move between frames."""
        frames = iss_runner.step(120.0)
        if len(frames) >= 2:
            p1 = frames[0].position_eci_m
            p2 = frames[-1].position_eci_m
            dist = sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
            assert dist > 1000  # Should move >1 km in 120s

    def test_ground_track_changes(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(300.0)
        if len(frames) >= 2:
            lat1 = frames[0].ground_track_lat_deg
            lat2 = frames[-1].ground_track_lat_deg
            assert lat1 != lat2 or frames[0].ground_track_lon_deg != frames[-1].ground_track_lon_deg

    def test_altitude_stable_circular_orbit(self, iss_runner: BasiliskSimRunner) -> None:
        """Circular orbit should maintain roughly constant altitude."""
        frames = iss_runner.step(600.0)
        alts = [f.altitude_km for f in frames]
        if alts:
            assert max(alts) - min(alts) < 20  # Very circular


class TestTelemetryFrames:
    """Verify telemetry frame structure and content."""

    def test_frame_has_all_fields(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(60.0)
        if frames:
            f = frames[0]
            assert hasattr(f, "altitude_km")
            assert hasattr(f, "orbital_velocity_m_s")
            assert hasattr(f, "roll_deg")
            assert hasattr(f, "solar_power_w")
            assert hasattr(f, "battery_soc")
            assert hasattr(f, "in_eclipse")

    def test_frame_to_dict(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(60.0)
        if frames:
            d = frames[0].to_dict()
            assert isinstance(d, dict)
            assert "altitude_km" in d
            assert "timestamp_s" in d

    def test_timestamps_increase(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(300.0)
        for i in range(1, len(frames)):
            assert frames[i].timestamp_s >= frames[i - 1].timestamp_s

    def test_solar_power_positive_when_sunlit(self, iss_runner: BasiliskSimRunner) -> None:
        frames = iss_runner.step(60.0)
        sunlit = [f for f in frames if not f.in_eclipse]
        if sunlit:
            assert sunlit[0].solar_power_w > 0


class TestMathUtilities:
    """Test coordinate conversion utilities."""

    def test_mrp_zero_gives_zero_euler(self) -> None:
        roll, pitch, yaw = mrp_to_euler_deg([0, 0, 0])
        assert roll == 0.0
        assert pitch == 0.0
        assert yaw == 0.0

    def test_mrp_small_values(self) -> None:
        roll, pitch, yaw = mrp_to_euler_deg([0.01, 0.02, 0.03])
        # Small MRP → small angles
        assert abs(roll) < 10
        assert abs(pitch) < 10
        assert abs(yaw) < 10

    def test_eci_to_lla_equator(self) -> None:
        # Point on equator, +X axis
        lat, lon, alt = eci_to_lla([6771000.0, 0.0, 0.0])
        assert abs(lat) < 1.0  # Should be near equator
        assert abs(alt - 400.0) < 10.0  # ~400 km altitude

    def test_eci_to_lla_north_pole(self) -> None:
        lat, lon, alt = eci_to_lla([0.0, 0.0, 6771000.0])
        assert lat > 80.0  # Should be near north pole

    def test_eci_to_lla_altitude(self) -> None:
        # LEO altitude
        lat, lon, alt = eci_to_lla([6771000.0, 0.0, 0.0])
        assert 350 < alt < 450


class TestDifferentConfigurations:
    """Test various spacecraft and orbit configurations."""

    def test_geo_orbit(self) -> None:
        config = SimConfig(
            timestep_s=10.0,
            output_interval_s=600.0,
            orbit=OrbitConfig(altitude_km=35786.0, inclination_deg=0.0),
        )
        runner = BasiliskSimRunner(config)
        runner.setup()
        frames = runner.step(600.0)
        if frames:
            assert 35700 < frames[0].altitude_km < 35900
            # GEO velocity: ~3.07 km/s
            assert 2900 < frames[0].orbital_velocity_m_s < 3200

    def test_polar_orbit(self) -> None:
        config = SimConfig(
            timestep_s=1.0,
            output_interval_s=60.0,
            orbit=OrbitConfig(altitude_km=600.0, inclination_deg=97.4),  # Sun-sync
        )
        runner = BasiliskSimRunner(config)
        runner.setup()
        frames = runner.step(120.0)
        if frames:
            assert 590 < frames[0].altitude_km < 610

    def test_heavy_spacecraft(self) -> None:
        config = SimConfig(
            spacecraft=SpacecraftConfig(mass_kg=420000.0),  # ISS mass
        )
        runner = BasiliskSimRunner(config)
        runner.setup()
        frames = runner.step(60.0)
        assert len(frames) > 0
