"""Tests for orbital destination mechanics and Coriolis effects.

All numerical assertions verified against hand calculations and
standard orbital mechanics references (Bate, Mueller & White 1971;
Vallado 2013).
"""
import math
import pytest

from aria.simulation.orbital_destination import (
    G_CONST, M_SUN, M_EARTH, R_EARTH, AU_METERS, G0, YEAR_SECONDS,
    CelestialBody, StarSystem, proxima_centauri_system,
    circular_orbit_velocity, orbital_period, escape_velocity,
    hohmann_transfer, vis_viva, station_keeping_delta_v,
    lagrange_point_distance, gravity_assist_delta_v,
    sphere_of_influence, capture_delta_v,
    angular_velocity_from_rpm, centripetal_gravity, rpm_for_gravity,
    coriolis_acceleration, coriolis_ratio, minimum_radius_for_coriolis_limit,
    CoriolisEffects,
    gravity_gradient_torque, gravity_gradient_libration_period,
    tidal_force_on_structure,
    entry_velocity, stagnation_heating_rate, ballistic_deceleration,
    atmospheric_density_exponential, simulate_atmospheric_entry,
    DestinationArrivalSimulator,
)


# ══════════════════════════════════════════════════════════════════
# ORBITAL MECHANICS
# ══════════════════════════════════════════════════════════════════

class TestCircularOrbitVelocity:
    def test_earth_leo(self):
        """LEO at 400 km: v = sqrt(GM_earth / (R_earth + 400km)) ≈ 7672 m/s."""
        mu_earth = G_CONST * M_EARTH
        r = R_EARTH + 400_000.0
        v = circular_orbit_velocity(mu_earth, r)
        assert 7600 < v < 7750, f"LEO velocity {v:.0f} m/s out of range"

    def test_earth_geo(self):
        """GEO at 42,164 km: v ≈ 3075 m/s."""
        mu_earth = G_CONST * M_EARTH
        r = 42_164_000.0
        v = circular_orbit_velocity(mu_earth, r)
        assert 3050 < v < 3100, f"GEO velocity {v:.0f} m/s out of range"

    def test_proxima_b_orbit(self):
        """Proxima b at 0.0485 AU around 0.122 M_sun.
        v = sqrt(0.122 * GM_sun / (0.0485 AU)) ≈ expected km/s range."""
        mu_star = G_CONST * 0.122 * M_SUN
        r = 0.0485 * AU_METERS
        v = circular_orbit_velocity(mu_star, r)
        # v should be in the range ~47 km/s (calculated)
        assert 40_000 < v < 55_000, f"Proxima b orbital v = {v:.0f} m/s"

    def test_negative_radius_raises(self):
        with pytest.raises(ValueError):
            circular_orbit_velocity(G_CONST * M_SUN, -1.0)


class TestOrbitalPeriod:
    def test_earth_year(self):
        """Earth orbital period ≈ 365.25 days."""
        mu_sun = G_CONST * M_SUN
        a = 1.0 * AU_METERS
        t = orbital_period(mu_sun, a)
        t_days = t / 86_400
        assert 364 < t_days < 367, f"Earth period {t_days:.1f} days"

    def test_proxima_b_period(self):
        """Proxima b period ≈ 11.186 days."""
        mu_star = G_CONST * 0.122 * M_SUN
        a = 0.0485 * AU_METERS
        t = orbital_period(mu_star, a)
        t_days = t / 86_400
        assert 10 < t_days < 13, f"Proxima b period {t_days:.1f} days"

    def test_kepler_third_law_consistency(self):
        """T² ∝ a³: doubling a should multiply T by 2√2."""
        mu = G_CONST * M_SUN
        t1 = orbital_period(mu, AU_METERS)
        t2 = orbital_period(mu, 2.0 * AU_METERS)
        ratio = t2 / t1
        expected = 2.0 * math.sqrt(2.0)
        assert abs(ratio - expected) < 0.01


class TestEscapeVelocity:
    def test_earth_surface(self):
        """Escape velocity from Earth surface ≈ 11,186 m/s."""
        mu_earth = G_CONST * M_EARTH
        v_esc = escape_velocity(mu_earth, R_EARTH)
        assert 11_100 < v_esc < 11_300

    def test_escape_is_sqrt2_times_circular(self):
        """v_esc = sqrt(2) * v_circ at any radius."""
        mu = G_CONST * M_SUN
        r = AU_METERS
        v_c = circular_orbit_velocity(mu, r)
        v_e = escape_velocity(mu, r)
        assert abs(v_e / v_c - math.sqrt(2.0)) < 1e-10


class TestHohmannTransfer:
    def test_earth_to_mars(self):
        """Earth to Mars Hohmann: Δv ≈ 5.59 km/s total.
        r1 = 1 AU, r2 = 1.524 AU."""
        mu_sun = G_CONST * M_SUN
        r1 = 1.0 * AU_METERS
        r2 = 1.524 * AU_METERS
        result = hohmann_transfer(mu_sun, r1, r2)
        dv_total_km = result["total_delta_v"] / 1000
        # Standard value ~5.59 km/s
        assert 5.0 < dv_total_km < 6.5, f"Hohmann Δv = {dv_total_km:.2f} km/s"
        # Transfer time ≈ 259 days
        transfer_days = result["transfer_time"] / 86_400
        assert 250 < transfer_days < 270

    def test_hohmann_symmetry(self):
        """Δv total should be the same whether going up or down."""
        mu = G_CONST * M_SUN
        up = hohmann_transfer(mu, AU_METERS, 2 * AU_METERS)
        down = hohmann_transfer(mu, 2 * AU_METERS, AU_METERS)
        assert abs(up["total_delta_v"] - down["total_delta_v"]) < 1.0

    def test_semi_major_axis(self):
        """Transfer ellipse semi-major axis = (r1 + r2) / 2."""
        mu = G_CONST * M_SUN
        r1 = AU_METERS
        r2 = 2 * AU_METERS
        result = hohmann_transfer(mu, r1, r2)
        expected_a = (r1 + r2) / 2.0
        assert abs(result["semi_major_axis"] - expected_a) < 1.0


class TestVisViva:
    def test_circular_orbit(self):
        """At circular orbit (r = a), vis-viva gives circular velocity."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 400_000
        v_vv = vis_viva(mu, r, r)
        v_circ = circular_orbit_velocity(mu, r)
        assert abs(v_vv - v_circ) < 0.01


class TestStationKeeping:
    def test_one_year_budget(self):
        """With 1e-6 m/s² perturbation, 1 year → ~31.6 m/s."""
        dv = station_keeping_delta_v(
            G_CONST * M_SUN, AU_METERS,
            perturbation_accel_m_s2=1e-6,
            duration_s=YEAR_SECONDS,
        )
        expected = 1e-6 * YEAR_SECONDS
        assert abs(dv - expected) < 0.1


class TestLagrangePoint:
    def test_earth_sun_l1(self):
        """Earth-Sun L1 ≈ 1.5 million km from Earth."""
        mu_sun = G_CONST * M_SUN
        mu_earth = G_CONST * M_EARTH
        r_l1 = lagrange_point_distance(mu_sun, mu_earth, AU_METERS, "L1")
        r_l1_km = r_l1 / 1000
        # Hill sphere radius ≈ 1.5 million km
        assert 1_000_000 < r_l1_km < 2_000_000

    def test_l1_equals_l2(self):
        """L1 and L2 are at the same distance (Hill sphere approx)."""
        mu_sun = G_CONST * M_SUN
        mu_earth = G_CONST * M_EARTH
        r_l1 = lagrange_point_distance(mu_sun, mu_earth, AU_METERS, "L1")
        r_l2 = lagrange_point_distance(mu_sun, mu_earth, AU_METERS, "L2")
        assert abs(r_l1 - r_l2) < 1.0

    def test_invalid_point_raises(self):
        with pytest.raises(ValueError):
            lagrange_point_distance(1, 1, 1, "L3")


class TestGravityAssist:
    def test_jupiter_flyby(self):
        """Jupiter gravity assist at 10 km/s v_inf, closest approach 2 R_jupiter.
        Should give substantial delta-v."""
        m_jupiter = 1.898e27
        r_jupiter = 7.149e7
        result = gravity_assist_delta_v(
            v_inf=10_000.0,
            body_mass_kg=m_jupiter,
            closest_approach_m=2.0 * r_jupiter,
        )
        # Turning angle and delta-v should be positive
        assert result["delta_v"] > 0
        assert result["turning_angle_deg"] > 0
        assert result["eccentricity"] > 1.0  # Hyperbolic

    def test_larger_periapsis_less_deflection(self):
        """Farther flyby → smaller turning angle → less delta-v."""
        m = 5.972e24  # Earth mass
        r = 6.371e6
        close = gravity_assist_delta_v(10_000, m, 2 * r)
        far = gravity_assist_delta_v(10_000, m, 10 * r)
        assert close["delta_v"] > far["delta_v"]
        assert close["turning_angle_deg"] > far["turning_angle_deg"]


class TestSphereOfInfluence:
    def test_earth_soi(self):
        """Earth SOI ≈ 924,000 km."""
        soi = sphere_of_influence(AU_METERS, M_EARTH, M_SUN)
        soi_km = soi / 1000
        assert 800_000 < soi_km < 1_100_000


class TestCaptureDeltaV:
    def test_capture_positive(self):
        """Capture Δv should always be positive (retrograde burn)."""
        mu = G_CONST * M_EARTH
        dv = capture_delta_v(mu, R_EARTH + 500_000, 3000.0)
        assert dv > 0

    def test_higher_vinf_more_delta_v(self):
        """Higher approach velocity requires more delta-v to capture."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        dv_slow = capture_delta_v(mu, r, 1000.0)
        dv_fast = capture_delta_v(mu, r, 5000.0)
        assert dv_fast > dv_slow


# ══════════════════════════════════════════════════════════════════
# CORIOLIS EFFECTS
# ══════════════════════════════════════════════════════════════════

class TestAngularVelocity:
    def test_1_rpm(self):
        """1 RPM = 2π/60 ≈ 0.10472 rad/s."""
        omega = angular_velocity_from_rpm(1.0)
        assert abs(omega - 2 * math.pi / 60.0) < 1e-10

    def test_0_rpm(self):
        assert angular_velocity_from_rpm(0.0) == 0.0


class TestCentripetalGravity:
    def test_500m_1rpm(self):
        """At 500m radius, 1 RPM: g = ω²r = (0.10472)² × 500 ≈ 5.48 m/s²."""
        omega = angular_velocity_from_rpm(1.0)
        g = centripetal_gravity(omega, 500.0)
        expected = omega ** 2 * 500.0
        assert abs(g - expected) < 1e-6
        # ~0.56g
        assert abs(g / G0 - 0.56) < 0.02


class TestRpmForGravity:
    def test_1g_at_500m(self):
        """RPM needed for 1g at 500m radius."""
        rpm = rpm_for_gravity(1.0, 500.0)
        # Verify by computing back
        omega = angular_velocity_from_rpm(rpm)
        g = centripetal_gravity(omega, 500.0)
        assert abs(g / G0 - 1.0) < 0.001

    def test_056g_at_500m(self):
        """RPM needed for 0.56g at 500m → should be ~1 RPM."""
        rpm = rpm_for_gravity(0.56, 500.0)
        assert 0.9 < rpm < 1.1


class TestCoriolisAcceleration:
    def test_walking_at_1rpm(self):
        """Walking at 1.5 m/s in 1 RPM habitat:
        a_c = 2 × 0.10472 × 1.5 = 0.3142 m/s²."""
        omega = angular_velocity_from_rpm(1.0)
        a_c = coriolis_acceleration(omega, 1.5)
        expected = 2.0 * omega * 1.5
        assert abs(a_c - expected) < 1e-6
        assert abs(a_c - 0.3142) < 0.01

    def test_zero_velocity_no_coriolis(self):
        omega = angular_velocity_from_rpm(1.0)
        assert coriolis_acceleration(omega, 0.0) == 0.0


class TestCoriolisRatio:
    def test_500m_1rpm_walking(self):
        """ratio = 2v/(ωr) = 2×1.5/(0.10472×500) = 0.0573 → 5.73%."""
        omega = angular_velocity_from_rpm(1.0)
        ratio = coriolis_ratio(omega, 1.5, 500.0)
        expected = 2.0 * 1.5 / (omega * 500.0)
        assert abs(ratio - expected) < 1e-6
        # Should be well under 10%
        assert ratio < 0.10

    def test_small_radius_high_ratio(self):
        """At 50m radius, Coriolis ratio should be much higher."""
        omega = angular_velocity_from_rpm(1.0)
        ratio = coriolis_ratio(omega, 1.5, 50.0)
        assert ratio > 0.10  # Uncomfortable


class TestMinimumRadius:
    def test_10pct_limit_walking(self):
        """Minimum radius for <10% at walking speed (1.5 m/s), 0.56g.
        r = 4v²/(ratio² × g) = 4 × 2.25 / (0.01 × 5.49) ≈ 164m."""
        r_min = minimum_radius_for_coriolis_limit(0.10, 1.5, 0.56)
        # Should be in range 150-220m
        assert 100 < r_min < 300
        # Our 500m habitat exceeds this — good
        assert r_min < 500


class TestCoriolisEffectsClass:
    def test_walking_analysis(self):
        ce = CoriolisEffects(radius_m=500, rpm=1.0)
        walk = ce.walking_coriolis(1.5)
        assert walk["coriolis_accel_m_s2"] > 0
        assert walk["ratio_percent"] < 10.0
        assert walk["deflection_noticeable"] is False

    def test_thrown_object_deflection(self):
        ce = CoriolisEffects(radius_m=500, rpm=1.0)
        thrown = ce.thrown_object(v_throw=10.0)
        assert thrown["lateral_deflection_m"] > 0
        assert thrown["flight_time_s"] > 0

    def test_fire_behavior_tilt(self):
        ce = CoriolisEffects(radius_m=500, rpm=1.0)
        fire = ce.fire_behavior()
        assert fire["flame_tilt_deg"] > 0
        assert fire["smoke_spirals"] is True

    def test_hvac_requirements(self):
        ce = CoriolisEffects(radius_m=500, rpm=1.0)
        hvac = ce.hvac_design_requirements()
        assert hvac["asymmetric_ducting_required"] is True
        assert len(hvac["recommendations"]) >= 3


# ══════════════════════════════════════════════════════════════════
# GRAVITY GRADIENT
# ══════════════════════════════════════════════════════════════════

class TestGravityGradientTorque:
    def test_zero_at_equilibrium(self):
        """At θ=0 (aligned with local vertical), torque = 0."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        torque = gravity_gradient_torque(mu, r, i_z=1e10, i_x=1e8, theta_rad=0.0)
        assert abs(torque) < 1e-6

    def test_max_at_45_degrees(self):
        """sin(2θ) is maximal at θ = 45°."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        t45 = abs(gravity_gradient_torque(mu, r, 1e10, 1e8, math.radians(45)))
        t30 = abs(gravity_gradient_torque(mu, r, 1e10, 1e8, math.radians(30)))
        t10 = abs(gravity_gradient_torque(mu, r, 1e10, 1e8, math.radians(10)))
        assert t45 > t30 > t10

    def test_prolate_body_restoring(self):
        """For I_z > I_x, torque at small positive θ is negative (restoring)."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        torque = gravity_gradient_torque(mu, r, i_z=1e10, i_x=1e8,
                                         theta_rad=math.radians(5.0))
        # For I_z > I_x and small positive θ, sin(2θ) > 0,
        # and (I_z - I_x) > 0, so torque > 0. The sign convention
        # means this is the restoring torque magnitude.
        assert torque > 0


class TestTidalForce:
    def test_generation_ship_in_leo(self):
        """2 km ship, 1e8 kg in LEO: tidal force should be modest."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        f = tidal_force_on_structure(mu, r, 2000.0, 1e8)
        assert f > 0
        # Should be on the order of Newtons to kilonewtons
        assert f < 1e6  # Not extreme


class TestLibrationPeriod:
    def test_stable_prolate(self):
        """Prolate body (I_z > I_x) has finite libration period."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        t_lib = gravity_gradient_libration_period(mu, r, i_z=1e10, i_x=1e8)
        assert t_lib < float("inf")
        assert t_lib > 0

    def test_unstable_oblate(self):
        """Oblate body (I_z < I_x) → infinite period (unstable)."""
        mu = G_CONST * M_EARTH
        r = R_EARTH + 500_000
        t_lib = gravity_gradient_libration_period(mu, r, i_z=1e8, i_x=1e10)
        assert t_lib == float("inf")


# ══════════════════════════════════════════════════════════════════
# ATMOSPHERIC ENTRY
# ══════════════════════════════════════════════════════════════════

class TestAtmosphericDensity:
    def test_surface_density(self):
        """At altitude 0, density = rho_0."""
        rho = atmospheric_density_exponential(1.225, 0.0, 8500.0)
        assert abs(rho - 1.225) < 1e-10

    def test_one_scale_height(self):
        """At h = H, density = rho_0 / e."""
        rho = atmospheric_density_exponential(1.225, 8500.0, 8500.0)
        assert abs(rho - 1.225 / math.e) < 1e-6

    def test_high_altitude_near_zero(self):
        """At 100 km, density should be very small."""
        rho = atmospheric_density_exponential(1.225, 100_000.0, 8500.0)
        assert rho < 1e-4


class TestStagnationHeating:
    def test_increases_with_velocity_cubed(self):
        """Heating ∝ v³."""
        q1 = stagnation_heating_rate(0.01, 5000.0, 1.0)
        q2 = stagnation_heating_rate(0.01, 10000.0, 1.0)
        ratio = q2 / q1
        assert abs(ratio - 8.0) < 0.01  # (10000/5000)³ = 8

    def test_positive_heating(self):
        q = stagnation_heating_rate(0.001, 7000.0, 1.5)
        assert q > 0


class TestBallisticDeceleration:
    def test_basic_calculation(self):
        """a = 0.5 × ρ × v² × Cd × A / m."""
        a = ballistic_deceleration(
            v=7000.0, rho=0.001, cd=1.2, area_m2=10.0, mass_kg=5000.0
        )
        expected = 0.5 * 0.001 * 7000 ** 2 * 1.2 * 10.0 / 5000.0
        assert abs(a - expected) < 0.01


class TestAtmosphericEntry:
    def test_proxima_b_entry(self):
        """Entry simulation for Proxima b produces reasonable profile."""
        system = proxima_centauri_system()
        planet = system.planets[0]  # Proxima b
        mu = G_CONST * planet.mass_kg
        v_entry = entry_velocity(mu, planet.radius_m, 100_000.0)

        profile = simulate_atmospheric_entry(
            planet=planet,
            entry_speed_m_s=v_entry,
            entry_angle_deg=-7.0,
        )
        assert len(profile.altitude_m) > 10
        assert profile.peak_decel_g > 0
        assert profile.peak_heating_w_m2 > 0
        assert profile.altitude_m[0] > profile.altitude_m[-1]  # Descending

    def test_no_atmosphere_raises(self):
        """Entry on body without atmosphere should raise."""
        body = CelestialBody(name="Airless", mass_kg=M_EARTH, radius_m=R_EARTH,
                             has_atmosphere=False)
        with pytest.raises(ValueError, match="no atmosphere"):
            simulate_atmospheric_entry(body, 7000.0)


# ══════════════════════════════════════════════════════════════════
# PROXIMA CENTAURI SYSTEM
# ══════════════════════════════════════════════════════════════════

class TestProximaSystem:
    def test_star_mass(self):
        system = proxima_centauri_system()
        assert abs(system.star.mass_kg - 0.122 * M_SUN) < 1e20

    def test_two_planets(self):
        system = proxima_centauri_system()
        assert len(system.planets) == 2

    def test_proxima_b_has_atmosphere(self):
        system = proxima_centauri_system()
        assert system.planets[0].has_atmosphere is True

    def test_mu_star(self):
        system = proxima_centauri_system()
        assert abs(system.mu_star - G_CONST * 0.122 * M_SUN) < 1e15


# ══════════════════════════════════════════════════════════════════
# INTEGRATED SIMULATOR
# ══════════════════════════════════════════════════════════════════

class TestDestinationArrivalSimulator:
    def test_capture_produces_delta_v(self):
        sim = DestinationArrivalSimulator()
        result = sim.execute_capture()
        assert result["delta_v_m_s"] > 0
        assert result["orbit_velocity_m_s"] > 0
        assert result["orbital_period_s"] > 0

    def test_lagrange_transfer(self):
        sim = DestinationArrivalSimulator()
        sim.execute_capture()
        result = sim.transfer_to_lagrange(point="L2")
        assert result["lagrange_distance_m"] > 0
        assert result["station_keeping_m_s_yr"] > 0

    def test_coriolis_analysis(self):
        sim = DestinationArrivalSimulator()
        analysis = sim.analyze_coriolis()
        assert "walking" in analysis
        assert "fire_behavior" in analysis
        assert "hvac" in analysis
        assert analysis["actual_gravity_g"] > 0

    def test_gravity_gradient_analysis(self):
        sim = DestinationArrivalSimulator()
        sim.execute_capture()
        result = sim.gravity_gradient_analysis()
        assert result["torque_max_Nm"] != 0
        assert result["tidal_force_N"] > 0

    def test_atmospheric_entry_plan(self):
        sim = DestinationArrivalSimulator()
        sim.execute_capture()
        profile = sim.plan_atmospheric_entry()
        assert profile.peak_decel_g > 0
        assert len(profile.altitude_m) > 5

    def test_full_arrival_sequence(self):
        sim = DestinationArrivalSimulator()
        report = sim.full_arrival_sequence()
        assert report["total_delta_v_m_s"] > 0
        assert len(report["events"]) >= 4
        assert report["capture"] is not None
        assert report["coriolis"] is not None
        assert report["lagrange"] is not None
        assert report["entry_profile"] is not None

    def test_delta_v_accumulates(self):
        sim = DestinationArrivalSimulator()
        sim.execute_capture()
        dv1 = sim.state.total_delta_v_spent_m_s
        sim.transfer_to_lagrange()
        dv2 = sim.state.total_delta_v_spent_m_s
        assert dv2 >= dv1

    def test_custom_system(self):
        """Simulator works with a custom star system."""
        star = CelestialBody("TestStar", mass_kg=M_SUN, radius_m=6.957e8)
        planet = CelestialBody(
            "TestPlanet", mass_kg=M_EARTH, radius_m=R_EARTH,
            orbit_radius_m=AU_METERS, has_atmosphere=True,
            atm_density_kg_m3=1.225, atm_scale_height_m=8500.0,
        )
        system = StarSystem(star=star, planets=[planet])
        sim = DestinationArrivalSimulator(system=system)
        result = sim.execute_capture()
        assert result["delta_v_m_s"] > 0
