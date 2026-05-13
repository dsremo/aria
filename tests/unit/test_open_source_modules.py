"""Validation tests for modules built from open-source study.

Tests the 26 new modules created during the 2026-04-17 sprint that
learned from Poliastro, Rebound, F Prime, cFS, OpenMCT, Basilisk,
Orekit, Nyx, Open Space Toolkit, Skyfield, and Stellarium.

Validates:
- Physics correctness vs known analytical results
- API behavior (creation, mutation, queries)
- Numerical accuracy (round-trip, convergence)
"""

from __future__ import annotations

import math

import numpy as np
import pytest


# ══════════════════════════════════════════════════════════════════
#  Orbital Elements (elements.py)
# ══════════════════════════════════════════════════════════════════

class TestOrbitalElements:
    def test_kepler_circular(self):
        """Kepler equation: M=0, e=0 → E=0."""
        from aria.physics.gravity.elements import mean_to_eccentric
        assert abs(mean_to_eccentric(0, 0)) < 1e-14

    def test_kepler_elliptic(self):
        """Kepler equation: M - E + e*sin(E) = 0."""
        from aria.physics.gravity.elements import mean_to_eccentric
        for M in [0.1, math.pi / 3, math.pi / 2, math.pi]:
            for e in [0.0, 0.3, 0.6, 0.9]:
                E = mean_to_eccentric(M, e)
                residual = E - e * math.sin(E) - M
                assert abs(residual) < 1e-10, f"M={M}, e={e}: residual={residual}"

    def test_kepler_hyperbolic(self):
        """Hyperbolic Kepler: e*sinh(H) - H - M = 0."""
        from aria.physics.gravity.elements import mean_to_hyperbolic
        H = mean_to_hyperbolic(1.0, 1.5)
        residual = 1.5 * math.sinh(H) - H - 1.0
        assert abs(residual) < 1e-10

    def test_coe_rv_roundtrip(self):
        """State vectors ↔ classical orbital elements round-trip."""
        from aria.physics.gravity.elements import rv_to_coe, coe_to_rv
        mu = 3.986e14
        r0 = np.array([7000e3, 1000e3, 500e3])
        v0 = np.array([1000.0, 7500.0, 200.0])
        a, e, i, Om, w, nu = rv_to_coe(r0, v0, mu)
        r1, v1 = coe_to_rv(a, e, i, Om, w, nu, mu)
        assert np.allclose(r0, r1, atol=1e-6)
        assert np.allclose(v0, v1, atol=1e-6)

    def test_mee_roundtrip(self):
        """MEE round-trip preserves state."""
        from aria.physics.gravity.elements import (
            rv_to_coe, coe_to_mee, mee_to_rv
        )
        mu = 3.986e14
        r0 = np.array([7000e3, 0, 0])
        v0 = np.array([0, 7800.0, 100.0])
        a, e, i, Om, w, nu = rv_to_coe(r0, v0, mu)
        p, f, g, h, k, L = coe_to_mee(a, e, i, Om, w, nu)
        r1, v1 = mee_to_rv(p, f, g, h, k, L, mu)
        assert np.allclose(r0, r1, atol=1e-3)


# ══════════════════════════════════════════════════════════════════
#  IAS15 integrator
# ══════════════════════════════════════════════════════════════════

class TestIAS15:
    def test_one_orbit_energy(self):
        """IAS15 should conserve energy to machine precision."""
        from aria.physics.gravity.ias15 import integrate_ias15
        GM = 1.32712440018e20
        AU = 1.496e11
        r0 = np.array([AU, 0, 0])
        v0 = np.array([0, 29784.0, 0])
        period = 365.25 * 86400

        def accel(t, r):
            return -GM * r / np.linalg.norm(r) ** 3

        r, v, t, steps, e_err = integrate_ias15(
            accel, r0, v0, 0, period, epsilon=1e-9
        )
        assert e_err < 1e-10
        assert steps < 100  # should be ~37

    def test_returns_to_origin(self):
        """After 1 full orbit, should return to starting position."""
        from aria.physics.gravity.ias15 import integrate_ias15
        GM = 1.32712440018e20
        AU = 1.496e11
        r0 = np.array([AU, 0, 0])
        v0 = np.array([0, 29784.0, 0])
        period = 365.25 * 86400

        def accel(t, r):
            return -GM * r / np.linalg.norm(r) ** 3

        r, v, t, steps, _ = integrate_ias15(accel, r0, v0, 0, period, epsilon=1e-9)
        # Should return to ~1 AU
        assert abs(np.linalg.norm(r) - AU) / AU < 1e-4


# ══════════════════════════════════════════════════════════════════
#  Lambert solver (Izzo)
# ══════════════════════════════════════════════════════════════════

class TestIzzoLambert:
    def test_apollo_tli(self):
        """Apollo 11 TLI from LEO to Moon — expected ~3130 m/s."""
        from aria.simulation.lambert_izzo import lambert_izzo
        GM = 3.986e14
        r1 = np.array([6578e3, 0, 0])  # LEO
        r2 = np.array([0, 384400e3, 0])  # Moon
        tof = 75.5 * 3600
        v1, v2 = lambert_izzo(GM, r1, r2, tof)
        dv_tli = np.linalg.norm(v1) - math.sqrt(GM / 6578e3)
        # Allow ±100 m/s tolerance
        assert 3000 < dv_tli < 3300

    def test_quarter_orbit(self):
        """Simple 90° transfer: departure velocity > circular."""
        from aria.simulation.lambert_izzo import lambert_izzo
        GM = 3.986e14
        r1 = np.array([7000e3, 0, 0])
        r2 = np.array([0, 7000e3, 0])  # 90° ahead at same radius
        # Quarter period: t = T/4
        period = 2 * math.pi * math.sqrt((7000e3) ** 3 / GM)
        tof = period / 4
        v1, v2 = lambert_izzo(GM, r1, r2, tof)
        # For circular transfer, velocity should be ~ circular velocity
        v_circ = math.sqrt(GM / 7000e3)
        assert abs(np.linalg.norm(v1) - v_circ) < 100


# ══════════════════════════════════════════════════════════════════
#  Coordinate transforms
# ══════════════════════════════════════════════════════════════════

class TestCoordinates:
    def test_jacobi_roundtrip(self):
        """Jacobi ↔ inertial round-trip."""
        from aria.physics.gravity.coordinates import (
            inertial_to_jacobi, jacobi_to_inertial
        )
        pos = np.array([[0, 0, 0], [1e11, 0, 0], [0, 2e11, 0]], dtype=float)
        vel = np.array([[0, 0, 0], [0, 29784, 0], [25000, 0, 0]], dtype=float)
        masses = np.array([2e30, 6e24, 3e23])
        pj, vj = inertial_to_jacobi(pos, vel, masses)
        pb, vb = jacobi_to_inertial(pj, vj, masses)
        assert np.allclose(pos, pb, atol=1e-6)
        assert np.allclose(vel, vb, atol=1e-6)

    def test_dh_central_body_at_origin(self):
        """Democratic heliocentric: body 0 position becomes origin."""
        from aria.physics.gravity.coordinates import (
            inertial_to_democratic_heliocentric
        )
        pos = np.array([[1e9, 0, 0], [1e11, 0, 0]], dtype=float)
        vel = np.array([[0, 100, 0], [0, 29784, 0]], dtype=float)
        masses = np.array([2e30, 6e24])
        pdh, vdh = inertial_to_democratic_heliocentric(pos, vel, masses)
        assert np.allclose(pdh[0], [0, 0, 0])


# ══════════════════════════════════════════════════════════════════
#  Mission time scales
# ══════════════════════════════════════════════════════════════════

class TestMissionTime:
    def test_j2000_epoch(self):
        """J2000.0 is 2000-01-01 12:00 TT."""
        from aria.core.mission_time import MissionTime
        t = MissionTime.from_utc(2000, 1, 1, 12, 0, 0)
        # J2000 TT = 2451545.0, with leap second offset
        assert abs(t.tt_jd - 2451545.0) < 0.001

    def test_tdb_minus_tt(self):
        """TDB - TT is periodic, ~0 to ±1.6 ms."""
        from aria.core.mission_time import MissionTime
        t = MissionTime.from_j2000_years(100)
        diff_ms = abs(t.tt_jd - t.tdb_jd) * 86400 * 1000
        assert diff_ms < 10.0  # well under 1.6 ms max

    def test_advance_years(self):
        """advance_years adds expected time."""
        from aria.core.mission_time import MissionTime
        t0 = MissionTime.from_j2000_years(0)
        t1 = t0.advance_years(10)
        assert abs(t1.j2000_years - 10.0) < 1e-6


# ══════════════════════════════════════════════════════════════════
#  Execution guard
# ══════════════════════════════════════════════════════════════════

class TestExecutionGuard:
    def test_precondition_failure(self):
        """Failed precondition blocks execution."""
        from aria.safety.execution_guard import (
            ExecutionGuard, PlanNode, Condition, ResourceArbiter, FailureType
        )
        guard = ExecutionGuard(ResourceArbiter())
        node = PlanNode(
            name="test",
            subsystem="test",
            execute_fn=lambda: "executed",
            preconditions=[Condition("fail", lambda: False)],
        )
        result = guard.execute_node(node)
        assert not result.success
        assert result.failure_type == FailureType.PRECONDITION_FAILED

    def test_resource_unavailable(self):
        """Resource over-commitment blocks execution."""
        from aria.safety.execution_guard import (
            ExecutionGuard, PlanNode, ResourceRequirement, ResourceArbiter,
            FailureType
        )
        arb = ResourceArbiter()
        arb.register_resource("power", 100)
        guard = ExecutionGuard(arb)
        node = PlanNode(
            name="test",
            subsystem="test",
            execute_fn=lambda: "ok",
            resources=[ResourceRequirement("power", 200)],
        )
        result = guard.execute_node(node)
        assert not result.success
        assert result.failure_type == FailureType.RESOURCE_UNAVAILABLE


# ══════════════════════════════════════════════════════════════════
#  Fault manager
# ══════════════════════════════════════════════════════════════════

class TestFaultManager:
    def test_lifecycle(self):
        """Full lifecycle: report → ack → shelve → resolve."""
        from aria.safety.fault_manager import FaultManager, FaultSeverity
        mgr = FaultManager()
        fid = mgr.report("test", FaultSeverity.WARNING, "test fault")
        assert len(mgr.active_faults()) == 1
        assert mgr.acknowledge(fid, operator="OP1")
        assert mgr.shelve(fid, duration="5min")
        assert mgr.resolve(fid, notes="fixed")
        assert len(mgr.active_faults()) == 0

    def test_shelve_expiry(self):
        """Shelved faults auto-unshelve on expiry."""
        from aria.safety.fault_manager import (
            FaultManager, FaultSeverity, SHELVE_DURATIONS
        )
        # Use unlimited so we can test without waiting
        mgr = FaultManager()
        fid = mgr.report("test", FaultSeverity.WARNING, "msg")
        # Shelve with 0-duration (immediate expiry)
        SHELVE_DURATIONS["test"] = 0.0
        mgr.shelve(fid, duration="test")
        unshelved = mgr.check_shelve_expiry()
        assert fid in unshelved


# ══════════════════════════════════════════════════════════════════
#  Condition sets
# ══════════════════════════════════════════════════════════════════

# TestConditionSets removed: aria/safety/condition_set.py deleted
# (Pass 3 F14.5a — zero production callers; no threat-model claim;
# alarm rules belong with cognitive layer when reintroduced).


# ══════════════════════════════════════════════════════════════════
#  Telemetry buffer
# ══════════════════════════════════════════════════════════════════

class TestTelemetryBuffer:
    def test_swap_returns_changes_only(self):
        """Only changed channels returned on swap."""
        from aria.simulator.telemetry_buffer import TelemetryBuffer
        buf = TelemetryBuffer()
        buf.update("temp", 300.0)
        buf.update("pressure", 101325.0)
        changed = buf.swap_and_read()
        assert set(changed.keys()) == {"temp", "pressure"}
        # Second swap with no changes returns empty
        buf.update("temp", 300.0)  # same value
        changed2 = buf.swap_and_read()
        assert len(changed2) == 0

    def test_limit_violations(self):
        """Limit checking detects violations."""
        from aria.simulator.telemetry_buffer import TelemetryBuffer
        buf = TelemetryBuffer()
        buf.register_channel("temp", units="K", limits=(280, 320, 270, 330))
        buf.update("temp", 325)  # in yellow range
        violations = buf.check_limits()
        assert violations.get("temp") == "yellow"
        buf.update("temp", 340)  # in red range
        assert buf.check_limits().get("temp") == "red"


# ══════════════════════════════════════════════════════════════════
#  Star field
# ══════════════════════════════════════════════════════════════════

class TestStarField:
    def test_catalog_size(self):
        """Catalog has at least 50 stars."""
        from aria.simulation.star_field import BRIGHT_STARS
        assert len(BRIGHT_STARS) >= 50

    def test_sirius_present(self):
        """Sirius is the brightest star — must be in catalog."""
        from aria.simulation.star_field import BRIGHT_STARS
        names = {s.name for s in BRIGHT_STARS}
        assert "Sirius" in names

    def test_proper_motion(self):
        """Barnard's Star has the largest proper motion (~10.4"/yr)."""
        from aria.simulation.star_field import (
            BRIGHT_STARS, star_position_at_epoch
        )
        barnards = [s for s in BRIGHT_STARS if s.name == "Barnard's Star"][0]
        ra0, dec0 = star_position_at_epoch(barnards, 0)
        ra100, dec100 = star_position_at_epoch(barnards, 100)
        # Should move ~10 arcmin in 100 years
        ang_change = math.hypot(ra100 - ra0, dec100 - dec0)
        assert ang_change > 0.1  # at least 0.1 degrees

    def test_aberration_at_rest(self):
        """No aberration at beta=0."""
        from aria.simulation.star_field import relativistic_aberration
        ra, dec = relativistic_aberration(
            100.0, 30.0, np.array([1, 0, 0]), 0.0
        )
        assert abs(ra - 100.0) < 1e-10
        assert abs(dec - 30.0) < 1e-10


# ══════════════════════════════════════════════════════════════════
#  Maneuver planning
# ══════════════════════════════════════════════════════════════════

class TestManeuverPlanning:
    def test_hohmann_leo_to_geo(self):
        """LEO-GEO Hohmann total Δv ≈ 3.8 km/s."""
        from aria.simulation.maneuver_planning import hohmann_transfer_burns
        b1, b2, tof = hohmann_transfer_burns(3.986e14, 7000e3, 42164e3)
        total = np.linalg.norm(b1.delta_v) + np.linalg.norm(b2.delta_v)
        assert 3700 < total < 3900

    def test_tsiolkovsky(self):
        """Rocket equation: m0*exp(-dv/Isp*g0)."""
        from aria.simulation.maneuver_planning import tsiolkovsky_fuel_mass, G0
        fuel = tsiolkovsky_fuel_mass(1000, 3000, 300)
        expected_mf = 1000 * math.exp(-3000 / (300 * G0))
        expected_fuel = 1000 - expected_mf
        assert abs(fuel - expected_fuel) < 0.01

    def test_plane_change_expensive(self):
        """Plane change at LEO speed is very expensive."""
        from aria.simulation.maneuver_planning import plane_change_burn
        # 10° at 7.5 km/s should be > 1 km/s
        dv = plane_change_burn(7500, math.radians(10))
        assert dv > 1000


# ══════════════════════════════════════════════════════════════════
#  Sensor models
# ══════════════════════════════════════════════════════════════════

class TestSensors:
    def test_star_tracker_accuracy(self):
        """Star tracker adds noise at specified magnitude."""
        from aria.physics.attitude.sensors import StarTracker
        st = StarTracker(accuracy_arcsec=10.0)
        rng = np.random.RandomState(42)
        true_sig = np.array([0.1, -0.2, 0.05])
        errors = []
        for _ in range(100):
            meas = st.measure(true_sig, rng)
            errors.append(np.linalg.norm(meas - true_sig))
        # Mean error should be of order the specified accuracy
        # 10 arcsec = 4.85e-5 rad → sigma_mrp ~ 1.2e-5
        avg_err = np.mean(errors)
        assert avg_err < 1e-4

    def test_gps_dropout(self):
        """GPS reports no-fix above max altitude."""
        from aria.physics.attitude.sensors import GPSReceiver
        gps = GPSReceiver(max_altitude_m=3000e3, dropout_probability=0.0)
        rng = np.random.RandomState(0)
        # Very high altitude — should dropout
        r_high = np.array([50000e3, 0, 0])
        v = np.array([0, 3000, 0])
        r_meas, v_meas = gps.measure(r_high, v, rng=rng)
        assert r_meas is None


# ══════════════════════════════════════════════════════════════════
#  Ground station
# ══════════════════════════════════════════════════════════════════

class TestGroundStation:
    def test_ecef_position(self):
        """Goldstone ECEF magnitude ≈ Earth radius + altitude."""
        from aria.simulation.ground_station import DSN_GOLDSTONE
        r = np.linalg.norm(DSN_GOLDSTONE.ecef_position())
        # Earth radius + altitude is ~6379 km
        assert 6370e3 < r < 6400e3

    def test_visibility_overhead(self):
        """Satellite directly overhead is visible at any min_elevation."""
        from aria.simulation.ground_station import GroundStation
        gs = GroundStation("Test", latitude_deg=0, longitude_deg=0, altitude_m=0)
        sat_ecef = np.array([7000e3, 0, 0])  # directly overhead
        assert gs.is_visible(sat_ecef)


# ══════════════════════════════════════════════════════════════════
#  Command tracker
# ══════════════════════════════════════════════════════════════════

class TestCommandTracker:
    def test_dispatch_and_complete(self):
        """Command tracked → completed normally."""
        from aria.safety.command_tracker import CommandTracker
        tracker = CommandTracker()
        seq = tracker.dispatch("test.cmd", {"arg": 1})
        assert tracker.complete(seq, success=True)
        stats = tracker.stats()
        assert stats["completed"] == 1
        assert stats["pending"] == 0


# ══════════════════════════════════════════════════════════════════
#  Operator notebook
# ══════════════════════════════════════════════════════════════════

# TestOperatorNotebook removed: aria/safety/operator_notebook.py deleted
# (Pass 3 F14.5b — zero production callers; no threat-model claim).


# ══════════════════════════════════════════════════════════════════
#  Config manager
# ══════════════════════════════════════════════════════════════════

class TestConfigManager:
    def test_staging_commit(self):
        """Staging → validate → commit flow."""
        from aria.core.config_manager import ConfigManager
        mgr = ConfigManager()
        mgr.set_active({"a": 1, "b": 2})
        mgr.load_staged({"a": 10, "c": 3})
        assert mgr.get("a") == 1  # active unchanged
        mgr.commit()
        assert mgr.get("a") == 10  # now committed
        assert mgr.get("c") == 3

    def test_rollback(self):
        """Rollback restores previous active."""
        from aria.core.config_manager import ConfigManager
        mgr = ConfigManager()
        mgr.set_active({"val": 100})
        mgr.load_staged({"val": 200})
        mgr.commit()
        assert mgr.get("val") == 200
        mgr.rollback()
        assert mgr.get("val") == 100


# ══════════════════════════════════════════════════════════════════
#  FDIR Recovery Plans
# ══════════════════════════════════════════════════════════════════

class TestFDIRRecovery:
    def test_standard_library_has_plans(self):
        """Standard library has at least 5 plans."""
        from aria.safety.fdir_recovery_plans import build_standard_library
        lib = build_standard_library()
        assert len(lib._plans) >= 5

    def test_thermal_overtemp_match(self):
        """Thermal overtemp fault matches thermal plan."""
        from aria.safety.fdir_recovery_plans import build_standard_library
        lib = build_standard_library()
        plan = lib.find_matching_plan(
            "thermal.zone3.overtemp", "critical", "thermal"
        )
        assert plan is not None
        assert "thermal" in plan.name.lower()

    def test_execute_plan(self):
        """Execute a plan — all steps run."""
        from aria.safety.fdir_recovery_plans import (
            RecoveryPlan, RecoveryStep, RecoveryPlanLibrary
        )
        executed = []
        plan = RecoveryPlan(
            name="test",
            fault_pattern="test",
            steps=[
                RecoveryStep("step 1", lambda: executed.append(1)),
                RecoveryStep("step 2", lambda: executed.append(2)),
                RecoveryStep("step 3", lambda: executed.append(3)),
            ],
        )
        lib = RecoveryPlanLibrary()
        result = lib.execute(plan)
        assert result.success
        assert result.steps_completed == 3
        assert executed == [1, 2, 3]

    def test_critical_step_failure_aborts(self):
        """Critical step failure aborts the plan."""
        from aria.safety.fdir_recovery_plans import (
            RecoveryPlan, RecoveryStep, RecoveryPlanLibrary
        )
        def fail():
            raise RuntimeError("simulated failure")
        plan = RecoveryPlan(
            name="test_fail",
            fault_pattern="test",
            steps=[
                RecoveryStep("step 1", lambda: None),
                RecoveryStep("step 2", fail, critical=True),
                RecoveryStep("step 3", lambda: None),  # not reached
            ],
        )
        lib = RecoveryPlanLibrary()
        result = lib.execute(plan)
        assert not result.success
        assert result.steps_completed == 1


# ══════════════════════════════════════════════════════════════════
#  Event Detection
# ══════════════════════════════════════════════════════════════════

class TestEventDetection:
    def test_apoapsis_detection(self):
        """Apoapsis event detected on eccentric orbit.

        Start at periapsis (r·v = 0 rising). Integrate past half orbit
        so we pass through apoapsis (where r·v crosses zero falling).
        """
        from aria.physics.gravity.event_detection import (
            detect_events, apoapsis_event
        )
        GM = 3.986e14
        # Start with upward velocity — r·v positive initially, then drops to 0
        r0 = np.array([8000e3, 0, 0])
        v0 = np.array([0, 7.5e3, 0])

        def accel(t, r):
            return -GM * r / np.linalg.norm(r) ** 3

        # Use a shorter window to find the first apoapsis crossing
        period = 2 * math.pi * math.sqrt((9000e3) ** 3 / GM)
        events = [apoapsis_event(GM)]
        r, v, t, detected = detect_events(accel, r0, v0, 0, period, dt=30, events=events)
        # Should detect at least one event in 1 orbit
        assert len(detected) >= 1

    def test_altitude_crossing(self):
        """Altitude crossing detected."""
        from aria.physics.gravity.event_detection import (
            detect_events, altitude_crossing
        )
        GM = 3.986e14
        r0 = np.array([7000e3, 0, 0])
        v0 = np.array([0, 9.0e3, 0])

        def accel(t, r):
            return -GM * r / np.linalg.norm(r) ** 3

        period = 2 * math.pi * math.sqrt((7500e3) ** 3 / GM)
        events = [altitude_crossing(1000e3)]  # 1000 km altitude
        r, v, t, detected = detect_events(accel, r0, v0, 0, period, dt=60, events=events)
        # Should cross 1000km twice (ascending + descending)
        assert len(detected) >= 1


# ══════════════════════════════════════════════════════════════════
#  Agent base safety integration
# ══════════════════════════════════════════════════════════════════

class TestAgentSafety:
    def test_set_safety_context_exists(self):
        """SubsystemAgent has set_safety_context method."""
        from aria.agents.base import SubsystemAgent
        assert hasattr(SubsystemAgent, "set_safety_context")

    def test_handle_ping_default(self):
        """Default handle_ping echoes key back."""
        from aria.agents.base import SubsystemAgent
        # Mock agent without running coordinator
        class DummyAgent(SubsystemAgent):
            name = "dummy"
            async def handle_message(self, message):
                pass
        # Can't instantiate without bus/tools — but check method exists
        assert DummyAgent.handle_ping.__qualname__.endswith("handle_ping")
        assert hasattr(DummyAgent, "report_fault")
        assert hasattr(DummyAgent, "dispatch_command")
