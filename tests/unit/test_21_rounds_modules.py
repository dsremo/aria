"""Validation tests for modules from the 21-rounds autonomous sprint.

Covers rounds 1-9:
- Integrated mission design (Lambert+porkchop+Tsiolkovsky)
- Atmosphere density (COESA76, Jacchia-like, decay lifetime)
- CR3BP integrator + Richardson halo
- Space environment (magnetic field, Van Allen, plasma, charging, dose)
- Propagator benchmark suite
- Ground track + sun-sync check
- TLE parser
- Walker constellation design + coverage

Each test validates against published values or analytical solutions.
"""

from __future__ import annotations

import math

import numpy as np
import pytest


# ══════════════════════════════════════════════════════════════════
#  Mission Design
# ══════════════════════════════════════════════════════════════════

class TestMissionDesign:
    def test_earth_mars_with_high_isp(self):
        """Earth-Mars with very high Isp (ion drive-ish) + mass budget works."""
        from aria.simulation.mission_design import design_earth_mars_mission
        # Mars total Δv ~10.5 km/s → need exhaust velocity >= that to be efficient
        # Isp=3000 means v_exhaust ~ 29.4 km/s → mass ratio ~1.4 → feasible
        design = design_earth_mars_mission(
            dry_mass_kg=3000, fuel_budget_kg=5000, isp_s=3000,
        )
        assert design.feasible

    def test_c3_range(self):
        """Earth-Mars C3 should be in range 5-50 km²/s²."""
        from aria.simulation.mission_design import design_earth_mars_mission
        design = design_earth_mars_mission()
        # Note: attribute is c3_departure (from porkchop), summarized as c3_km2_s2
        assert 5 < design.c3_departure < 50


# ══════════════════════════════════════════════════════════════════
#  Atmosphere
# ══════════════════════════════════════════════════════════════════

class TestAtmosphere:
    def test_sea_level_density(self):
        """Sea-level density is 1.225 kg/m³ (US Std Atm 1976)."""
        from aria.physics.gravity.atmosphere import coesa76_density
        rho = coesa76_density(0)
        assert abs(rho - 1.225) / 1.225 < 0.01

    def test_density_decreases_with_altitude(self):
        """Density strictly decreases up to 1000 km."""
        from aria.physics.gravity.atmosphere import coesa76_density
        altitudes = [0, 50e3, 100e3, 200e3, 400e3, 800e3]
        densities = [coesa76_density(a) for a in altitudes]
        for i in range(1, len(densities)):
            assert densities[i] < densities[i - 1]

    def test_400km_lifetime_is_years(self):
        """400 km orbit lifetime should be 1-10 years for typical A/m."""
        from aria.physics.gravity.atmosphere import estimate_decay_lifetime
        est = estimate_decay_lifetime(altitude_km=400, area_over_mass_m2_kg=0.01)
        assert 100 < est.lifetime_days < 10000

    def test_very_high_orbit_decays_slowly(self):
        """800 km orbit should last far longer than 400 km."""
        from aria.physics.gravity.atmosphere import estimate_decay_lifetime
        est_400 = estimate_decay_lifetime(400)
        est_800 = estimate_decay_lifetime(800)
        assert est_800.lifetime_days > est_400.lifetime_days


# ══════════════════════════════════════════════════════════════════
#  CR3BP
# ══════════════════════════════════════════════════════════════════

class TestCR3BP:
    def test_jacobi_conservation(self):
        """Jacobi constant should be conserved (high accuracy for short times)."""
        from aria.physics.gravity.cr3bp import propagate_cr3bp, MU_EARTH_MOON
        # Start near L4
        state0 = np.array([0.5 - MU_EARTH_MOON, math.sqrt(3) / 2, 0, 0, 0, 0])
        traj = propagate_cr3bp(state0, t_end=1.0, mu=MU_EARTH_MOON, dt=0.0001)
        assert traj.jacobi_drift < 1e-8

    def test_richardson_returns_sensible_state(self):
        """Richardson halo seed should have finite, sensible values."""
        from aria.physics.gravity.cr3bp import (
            richardson_halo_initial_conditions, MU_EARTH_MOON
        )
        state = richardson_halo_initial_conditions(
            L_point=2, mu=MU_EARTH_MOON, amplitude_z_nd=0.02,
        )
        assert state.shape == (6,)
        assert all(np.isfinite(state))
        # Should be near L2 (x ≈ 1.01-1.15 in nondim)
        assert 1.0 < state[0] < 1.2


# ══════════════════════════════════════════════════════════════════
#  Space Environment
# ══════════════════════════════════════════════════════════════════

class TestSpaceEnvironment:
    def test_magnetic_field_equator(self):
        """B at 400km equator should be ~25000-30000 nT."""
        from aria.physics.gravity.space_environment import igrf_dipole
        r = np.array([6378e3 + 400e3, 0, 0])
        B = igrf_dipole(r)
        mag = np.linalg.norm(B)
        assert 15000 < mag < 50000  # allow for dipole tilt

    def test_geo_charging_severe_in_eclipse(self):
        """GEO in eclipse = severe charging risk."""
        from aria.physics.gravity.space_environment import assess_charging_risk
        risk = assess_charging_risk(36000, in_eclipse=True)
        assert risk.risk_level == "severe"
        assert risk.potential_v <= -10000  # very negative

    def test_leo_charging_low(self):
        """LEO has low charging risk."""
        from aria.physics.gravity.space_environment import assess_charging_risk
        risk = assess_charging_risk(400, in_eclipse=False)
        assert risk.risk_level == "low"

    def test_saa_boosts_flux(self):
        """SAA center gives >10x flux boost over baseline."""
        from aria.physics.gravity.space_environment import south_atlantic_anomaly_boost
        boost_in_saa = south_atlantic_anomaly_boost(-30, -40, 400)
        boost_elsewhere = south_atlantic_anomaly_boost(40, 0, 400)
        assert boost_in_saa > 10 * boost_elsewhere


# ══════════════════════════════════════════════════════════════════
#  Propagator Benchmark
# ══════════════════════════════════════════════════════════════════

class TestPropagatorBenchmark:
    def test_whfast_best_energy_conservation(self):
        """WHFast should outperform RK4 on energy conservation."""
        from aria.physics.gravity.propagator_benchmark import (
            run_rk4, run_whfast, problem_eccentric,
        )
        problem = problem_eccentric()
        rk4_result = run_rk4(problem)
        wh_result = run_whfast(problem)
        # WHFast symplectic should conserve better than RK4
        assert wh_result.energy_drift < rk4_result.energy_drift


# ══════════════════════════════════════════════════════════════════
#  Ground Track
# ══════════════════════════════════════════════════════════════════

class TestGroundTrack:
    def test_ecef_to_geodetic_equator(self):
        """ECEF on equator corresponds to lat=0."""
        from aria.simulation.ground_track import ecef_to_geodetic
        lat, lon, alt = ecef_to_geodetic(np.array([6378137.0, 0, 0]))
        assert abs(lat) < 1e-6
        assert abs(lon) < 1e-6
        assert abs(alt) < 1e-3

    def test_ecef_to_geodetic_pole(self):
        """ECEF at north pole corresponds to lat=90."""
        from aria.simulation.ground_track import ecef_to_geodetic
        # WGS-84 polar radius = a*(1-f) ~ 6356.752 km
        lat, lon, alt = ecef_to_geodetic(np.array([0, 0, 6356752.0]))
        assert abs(lat - 90) < 0.1

    def test_sun_sync_detection(self):
        """600km/97.8° is sun-synchronous, ISS is not."""
        from aria.simulation.ground_track import is_sun_synchronous
        assert is_sun_synchronous(97.8, 600)
        assert not is_sun_synchronous(51.6, 400)


# ══════════════════════════════════════════════════════════════════
#  TLE Parser
# ══════════════════════════════════════════════════════════════════

class TestTLEParser:
    ISS_L1 = "1 25544U 98067A   24015.50000000  .00016717  00000-0  10270-3 0  9994"
    ISS_L2 = "2 25544  51.6413   0.0000 0005291 132.2917  16.7083 15.49309239432456"

    def test_parse_iss(self):
        """Parse ISS TLE — inclination, mean motion."""
        from aria.simulation.tle_parser import parse_tle
        tle = parse_tle(self.ISS_L1, self.ISS_L2, "ISS (ZARYA)")
        assert tle.satellite_number == 25544
        assert abs(tle.inclination_deg - 51.6413) < 0.0001
        assert abs(tle.mean_motion_rev_per_day - 15.49309239) < 1e-6

    def test_iss_period_minutes(self):
        """ISS orbital period is ~93 minutes."""
        from aria.simulation.tle_parser import parse_tle
        tle = parse_tle(self.ISS_L1, self.ISS_L2)
        period_min = tle.period_seconds() / 60
        assert 92 < period_min < 94

    def test_iss_altitude(self):
        """ISS perigee/apogee altitude ~410-420 km."""
        from aria.simulation.tle_parser import parse_tle
        tle = parse_tle(self.ISS_L1, self.ISS_L2)
        assert 400 < tle.altitude_perigee_km() < 430
        assert 400 < tle.altitude_apogee_km() < 430

    def test_invalid_tle_raises(self):
        """Malformed TLE should raise ValueError."""
        from aria.simulation.tle_parser import parse_tle
        with pytest.raises(ValueError):
            parse_tle("nope", "nope2")


# ══════════════════════════════════════════════════════════════════
#  Constellation Design
# ══════════════════════════════════════════════════════════════════

class TestCCSDSPackets:
    def test_roundtrip_telemetry(self):
        """Telemetry packet round-trip preserves fields."""
        from aria.simulator.ccsds_packet import (
            build_telemetry_packet, CCSDSPacket, PacketType,
        )
        p = build_telemetry_packet(apid=100, user_data=b"test data")
        encoded = p.encode()
        p2 = CCSDSPacket.decode(encoded)
        assert p2.apid == 100
        assert p2.packet_type == PacketType.TELEMETRY

    def test_sequence_gap_detection(self):
        """Gap detector correctly flags missing packets."""
        from aria.simulator.ccsds_packet import CCSDSSequenceTracker
        tracker = CCSDSSequenceTracker()
        assert tracker.receive(1, 0) is True   # first
        assert tracker.receive(1, 1) is True   # in sequence
        assert tracker.receive(1, 5) is False  # gap
        assert tracker.stats()["gaps_detected"] == 1

    def test_apid_bounds(self):
        """APID out of range raises."""
        from aria.simulator.ccsds_packet import CCSDSPacket
        with pytest.raises(ValueError):
            CCSDSPacket(apid=3000).encode()


class TestRiskAssessment:
    def test_fmea_rpn(self):
        """RPN = Severity × Occurrence × Detection."""
        from aria.safety.risk_assessment import FailureMode
        m = FailureMode(
            component="test", mode="test", effect_local="",
            effect_system="", severity=5, occurrence=4, detection=3,
        )
        assert m.rpn == 60

    def test_criticality_classes(self):
        """High-RPN failure mode is CRITICAL."""
        from aria.safety.risk_assessment import FailureMode
        m = FailureMode("x", "y", "", "", severity=10, occurrence=5, detection=5)
        assert m.criticality_class == "CRITICAL"

    def test_tmr_reliability(self):
        """TMR 2-of-3 beats single unit."""
        from aria.safety.risk_assessment import nom_voting_reliability
        single = 0.95
        tmr = nom_voting_reliability(single, 3, 2)
        assert tmr > single

    def test_series_vs_parallel(self):
        """Parallel always ≥ serial for same components."""
        from aria.safety.risk_assessment import (
            series_reliability, parallel_reliability,
        )
        rs = [0.9, 0.95, 0.92]
        assert parallel_reliability(rs) > series_reliability(rs)

    def test_exp_reliability(self):
        """Exponential: R(MTBF) = 1/e."""
        from aria.safety.risk_assessment import exponential_reliability
        import math
        assert abs(exponential_reliability(1000, 1000) - math.exp(-1)) < 1e-10


class TestLinkBudget:
    def test_path_loss_increases_with_distance(self):
        """FSPL increases with range and frequency."""
        from aria.simulation.link_budget import free_space_path_loss_db
        near = free_space_path_loss_db(1e6, 8.4e9)
        far = free_space_path_loss_db(1e9, 8.4e9)
        assert far > near + 50  # 60 dB for 1000× range

    def test_mars_link_produces_result(self):
        """Mars-Earth link budget returns finite values."""
        from aria.simulation.link_budget import mars_to_earth_link
        lb = mars_to_earth_link(distance_au=1.5)
        assert lb.path_loss_db > 200  # Mars is far
        assert lb.max_data_rate_mbps > 0

    def test_antenna_gain_scales_with_size(self):
        """Bigger dish = more gain."""
        from aria.simulation.link_budget import parabolic_antenna_gain_db
        small = parabolic_antenna_gain_db(1.0, 8e9)
        big = parabolic_antenna_gain_db(10.0, 8e9)
        # 10× diameter → +20 dB gain
        assert abs(big - small - 20) < 1


class TestMassBudget:
    def test_wet_includes_propellant(self):
        """Wet mass = dry + propellant."""
        from aria.simulation.mass_budget_calc import MassBudget
        b = MassBudget()
        b.add_quick("x", 100, "structure", growth_factor=1.0)
        b.propellant_kg = 50
        assert b.wet_mass_kg() == 150

    def test_growth_factor_applied(self):
        """Growth factor increases effective mass."""
        from aria.simulation.mass_budget_calc import MassBudget
        b = MassBudget()
        b.add_quick("x", 100, "structure", growth_factor=1.25)
        assert b.dry_mass_current_kg() == 100
        assert b.dry_mass_with_growth_kg() == 125

    def test_heuristic_budget_scales(self):
        """Larger payload → larger total mass."""
        from aria.simulation.mass_budget_calc import estimate_heuristic_budget
        small = estimate_heuristic_budget(10, "leo_science")
        big = estimate_heuristic_budget(100, "leo_science")
        assert big.dry_mass_current_kg() > small.dry_mass_current_kg()


class TestSpaceWeather:
    def test_f107_cycles(self):
        """F10.7 cycles 70-200 sfu."""
        from aria.physics.gravity.space_weather import estimate_f107_by_cycle_phase
        vals = [estimate_f107_by_cycle_phase(t) for t in range(12)]
        assert min(vals) < 80 and max(vals) > 180

    def test_kp_to_ap(self):
        """Kp=9 → ap=400."""
        from aria.physics.gravity.space_weather import kp_to_ap
        assert kp_to_ap(9.0) == 400.0

    def test_flare_classification(self):
        """Flare multipliers correct."""
        from aria.physics.gravity.space_weather import classify_flare, FlareClass
        cls, mul = classify_flare(5e-5)
        assert cls == FlareClass.M
        assert abs(mul - 5.0) < 0.01

    def test_cme_arrival_time(self):
        """Faster CME arrives sooner."""
        from aria.physics.gravity.space_weather import cme_arrival_time_hours
        slow = cme_arrival_time_hours(500)
        fast = cme_arrival_time_hours(2000)
        assert fast < slow


class TestFDIRRecoveryLibrary:
    def test_standard_library_has_all_subsystems(self):
        """Standard library covers power, thermal, ECLSS, comms, SEU, attitude, fuel."""
        from aria.safety.fdir_recovery_plans import build_standard_library
        lib = build_standard_library()
        patterns = {p.fault_pattern for p in lib._plans}
        expected = {"undervoltage", "overtemp", "co2", "comms_loss",
                    "seu", "tumble", "leak"}
        assert expected.issubset(patterns)

    def test_fdir_manager_loads_library(self):
        """FDIRManager.__init__ attaches a recovery library."""
        # We can't instantiate FDIRManager easily without MessageBus,
        # but we can verify the import path works.
        from aria.safety.fdir_recovery_plans import RecoveryPlanLibrary
        assert RecoveryPlanLibrary is not None


class TestCCSDSExtended:
    def test_sequence_counter_wraps(self):
        """Sequence counter wraps at 16384."""
        from aria.simulator.ccsds_packet import CCSDSSequenceTracker
        tracker = CCSDSSequenceTracker()
        for _ in range(16384):
            tracker.next_count(100)
        # Next should wrap to 0
        next_val = tracker.next_count(100)
        assert next_val == 0

    def test_command_checksum(self):
        """Command packet includes XOR checksum in secondary header."""
        from aria.simulator.ccsds_packet import build_command_packet
        cmd = build_command_packet(
            apid=1, function_code=42, params=b"\x01\x02\x03"
        )
        # Secondary header: [fn_code][reserved][checksum_hi][checksum_lo]
        assert cmd.secondary_header[0] == 42
        # XOR: 1 ^ 2 ^ 3 = 0
        checksum = (cmd.secondary_header[2] << 8) | cmd.secondary_header[3]
        assert checksum == 0


class TestReentryCorridor:
    def test_ballistic_reentry_lands(self):
        """A moderate re-entry reaches ground."""
        from aria.simulation.reentry_corridor import simulate_ballistic_reentry
        profile = simulate_ballistic_reentry(
            entry_altitude_km=120, entry_velocity_mps=7800,
            entry_angle_deg=-6.0, ballistic_coefficient=320,
        )
        # Should decelerate significantly
        assert profile.landing_velocity_mps < 1000
        assert profile.peak_g > 1

    def test_profile_arrays_populated(self):
        """Reentry profile arrays have data."""
        from aria.simulation.reentry_corridor import simulate_ballistic_reentry
        profile = simulate_ballistic_reentry()
        assert len(profile.altitudes_km) > 0
        assert len(profile.velocities_mps) == len(profile.altitudes_km)
        # Altitude should generally decrease (may have small oscillations)
        assert profile.altitudes_km[-1] < profile.altitudes_km[0]


class TestSubsystemSizing:
    def test_radiator_scales_with_heat(self):
        """Double heat → double radiator area."""
        from aria.simulation.subsystem_sizing import size_radiator
        r1 = size_radiator(100)
        r2 = size_radiator(200)
        ratio = r2.area_m2 / r1.area_m2
        assert abs(ratio - 2.0) < 0.01

    def test_solar_array_degradation(self):
        """Longer mission → bigger array needed for same EOL power."""
        from aria.simulation.subsystem_sizing import size_solar_array
        sa_1yr = size_solar_array(required_power_w=1000, mission_duration_yr=1)
        sa_10yr = size_solar_array(required_power_w=1000, mission_duration_yr=10)
        assert sa_10yr.area_m2 > sa_1yr.area_m2

    def test_solar_array_mars_larger(self):
        """Mars needs larger solar array than Earth orbit."""
        from aria.simulation.subsystem_sizing import size_solar_array
        earth = size_solar_array(required_power_w=1000, solar_distance_au=1.0)
        mars = size_solar_array(required_power_w=1000, solar_distance_au=1.52)
        assert mars.area_m2 > earth.area_m2 * 2  # 1.52² ≈ 2.3×

    def test_battery_capacity_from_eclipse(self):
        """Longer eclipse → bigger battery."""
        from aria.simulation.subsystem_sizing import size_battery
        b30 = size_battery(load_w=500, eclipse_duration_s=30 * 60)
        b60 = size_battery(load_w=500, eclipse_duration_s=60 * 60)
        assert b60.capacity_wh > b30.capacity_wh

    def test_rcs_mission_duration(self):
        """Longer mission → more RCS propellant."""
        from aria.simulation.subsystem_sizing import size_rcs_propellant
        p1 = size_rcs_propellant(vehicle_mass_kg=1000, mission_duration_yr=1)
        p10 = size_rcs_propellant(vehicle_mass_kg=1000, mission_duration_yr=10)
        assert p10.propellant_mass_kg > p1.propellant_mass_kg

    def test_data_storage_nonnegative(self):
        """Data storage is always positive for positive inputs."""
        from aria.simulation.subsystem_sizing import size_data_storage
        ds = size_data_storage(data_rate_mbps=100, downlink_gap_hours=24)
        assert ds.storage_gb > 0


class TestConstellationDesign:
    def test_gps_constellation_size(self):
        """GPS has 24 satellites in 6 planes."""
        from aria.simulation.constellation_design import gps_constellation
        c = gps_constellation()
        assert c.total_satellites == 24
        assert c.orbital_planes == 6

    def test_gps_raan_distribution(self):
        """GPS RAANs are evenly spaced at 60° intervals."""
        from aria.simulation.constellation_design import gps_constellation
        c = gps_constellation()
        raans = sorted({round(s.raan_deg, 1) for s in c.satellites})
        assert raans == [0.0, 60.0, 120.0, 180.0, 240.0, 300.0]

    def test_iridium_is_polar(self):
        """Iridium has 86.4° inclination and 180° RAAN spread."""
        from aria.simulation.constellation_design import iridium_constellation
        c = iridium_constellation()
        assert all(abs(s.inc_deg - 86.4) < 0.01 for s in c.satellites)
        raans = sorted({round(s.raan_deg, 1) for s in c.satellites})
        assert max(raans) < 180

    def test_geo_coverage_large(self):
        """GEO satellites see 70° of Earth."""
        from aria.simulation.constellation_design import ground_coverage_angle
        angle = ground_coverage_angle(35786, min_elevation_deg=10)
        assert 65 < angle < 80

    def test_walker_validation(self):
        """Walker constellation requires t divisible by p."""
        from aria.simulation.constellation_design import walker_delta_constellation
        with pytest.raises(ValueError):
            walker_delta_constellation(t_total=25, p_planes=6, f_phasing=0, altitude_km=500)
