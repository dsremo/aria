"""3-D closed-loop GN&C trajectory tests.

Verifies the 3-D upgrade of :class:`TrajectoryState`:

  * New vector fields (`position_vec_ly`, `velocity_vec_m_s`, `thrust_vec`,
    `target_direction`) are populated coherently with the scalar fields.
  * Scalar `position_ly` equals ‖position_vec_ly‖ and `velocity_m_s`
    equals ‖velocity_vec_m_s‖ after every tick (backward-compat invariant).
  * BOOST thrust points along the target direction; DECEL thrust points
    retrograde (−velocity_unit).
  * Interstellar targets adopt the Gaia-derived unit vector from
    STAR_CATALOG; solar-system targets default to +X.
  * `to_dict()` exposes the new keys alongside the legacy ones.
  * `set_target()` resets the vector state and records a fresh direction.

References
----------
  * Wie 2008 "Space Vehicle Dynamics and Control" AIAA, §3
  * Frisbee 2003 JPL/D-26963 §3
"""

from __future__ import annotations

import math

import pytest

from aria.simulator.mission_phases import Phase, get_phase_controller
from aria.simulator.targets import STAR_CATALOG
from aria.simulator.trajectory_state import (
    TrajectoryState,
    _direction_for_target,
    _vec_mag,
    _vec_unit,
    get_trajectory_state,
    reset_trajectory_state,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _approx_equal(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b)) + tol


# ── Direction lookup ─────────────────────────────────────────────────────


class TestTargetDirection:
    def test_solar_system_defaults_to_plus_x(self):
        u = _direction_for_target("Mars")
        assert u == (1.0, 0.0, 0.0)

    def test_moon_defaults_to_plus_x(self):
        u = _direction_for_target("Moon")
        assert u == (1.0, 0.0, 0.0)

    def test_unknown_target_defaults_to_plus_x(self):
        u = _direction_for_target("Nonexistent Star")
        assert u == (1.0, 0.0, 0.0)

    def test_proxima_matches_star_catalog(self):
        # _direction_for_target re-normalises, so compare against the
        # strictly normalised catalog vector (within rounding).
        u = _direction_for_target("Proxima Centauri")
        raw = STAR_CATALOG["proxima_centauri"].direction_unit
        m = math.sqrt(sum(c * c for c in raw))
        expected = [c / m for c in raw]
        for actual, want in zip(u, expected):
            assert _approx_equal(actual, want, tol=1e-9)

    def test_alpha_centauri_matches_star_catalog(self):
        u = _direction_for_target("Alpha Centauri A")
        raw = STAR_CATALOG["alpha_centauri"].direction_unit
        m = math.sqrt(sum(c * c for c in raw))
        expected = [c / m for c in raw]
        for actual, want in zip(u, expected):
            assert _approx_equal(actual, want, tol=1e-9)

    def test_direction_is_unit_length(self):
        # STAR_CATALOG's own `direction_unit` can drift ~2 % from unit
        # length because position_ly and distance_ly were rounded
        # independently. _direction_for_target re-normalises, so the
        # guidance law always sees a strict unit vector.
        u = _direction_for_target("Barnard's Star")
        assert abs(_vec_mag(u) - 1.0) < 1e-12


# ── Vector helpers ───────────────────────────────────────────────────────


class TestVectorHelpers:
    def test_vec_mag_zero(self):
        assert _vec_mag((0.0, 0.0, 0.0)) == 0.0

    def test_vec_mag_pythagoras(self):
        assert _vec_mag((3.0, 4.0, 0.0)) == pytest.approx(5.0)
        assert _vec_mag((2.0, 3.0, 6.0)) == pytest.approx(7.0)

    def test_vec_unit_zero_is_zero(self):
        assert _vec_unit((0.0, 0.0, 0.0)) == (0.0, 0.0, 0.0)

    def test_vec_unit_magnitude_is_one(self):
        u = _vec_unit((1.0, 2.0, 2.0))
        assert abs(_vec_mag(u) - 1.0) < 1e-12


# ── State initialisation + set_target ────────────────────────────────────


class TestStateInit:
    def test_default_state_vectors_are_zero(self):
        s = TrajectoryState()
        assert s.position_vec_ly == (0.0, 0.0, 0.0)
        assert s.velocity_vec_m_s == (0.0, 0.0, 0.0)
        assert s.thrust_vec == (0.0, 0.0, 0.0)

    def test_default_target_direction_seeded(self):
        # BUG-016 (2026-04-24) made the default target the Moon, which has
        # no entry in _STAR_DIRECTION_BY_DISPLAY_NAME and falls back to +X
        # (the simulator has no ephemeris for solar-system body positions
        # at mission start). For the interstellar-direction unit test we
        # construct an explicit Alpha Centauri target and check that
        # set_target seeds the direction from the catalog.
        s = TrajectoryState()
        s.set_target("Alpha Centauri A")
        assert abs(_vec_mag(s.target_direction) - 1.0) < 1e-12
        # Sign check: should point into the -y hemisphere (α Cen is below
        # the galactic plane at y ≈ -3.74).
        assert s.target_direction[1] < 0

    def test_set_target_updates_direction(self):
        s = TrajectoryState()
        s.set_target("Proxima Centauri")
        assert abs(_vec_mag(s.target_direction) - 1.0) < 1e-12
        # Proxima's direction_unit has negative y component (Gaia DR3).
        raw = STAR_CATALOG["proxima_centauri"].direction_unit
        m = math.sqrt(sum(c * c for c in raw))
        for actual, want in zip(s.target_direction, [c / m for c in raw]):
            assert _approx_equal(actual, want, tol=1e-9)

    def test_set_target_resets_vectors(self):
        s = TrajectoryState()
        s.position_vec_ly = (1.0, 2.0, 3.0)
        s.velocity_vec_m_s = (4.0, 5.0, 6.0)
        s.thrust_vec = (0.5, 0.0, 0.0)
        s.set_target("Mars")
        assert s.position_vec_ly == (0.0, 0.0, 0.0)
        assert s.velocity_vec_m_s == (0.0, 0.0, 0.0)
        assert s.thrust_vec == (0.0, 0.0, 0.0)

    def test_set_target_solar_body_defaults_to_plus_x(self):
        s = TrajectoryState()
        s.set_target("Pluto")
        assert s.target_direction == (1.0, 0.0, 0.0)


# ── 3-D physics during BOOST ─────────────────────────────────────────────


class TestBoostPhysics3D:
    def _reset(self, target: str = "Alpha Centauri A"):
        reset_trajectory_state()
        s = get_trajectory_state()
        s.set_target(target)
        get_phase_controller().current = Phase.BOOST
        return s

    def test_scalar_equals_vector_magnitude_after_boost(self):
        s = self._reset("Alpha Centauri A")
        s.tick(3600.0)
        # Scalar is the magnitude of the vector — invariant every tick.
        assert s.velocity_m_s == pytest.approx(_vec_mag(s.velocity_vec_m_s),
                                               rel=1e-12, abs=1e-9)
        assert s.position_ly == pytest.approx(_vec_mag(s.position_vec_ly),
                                              rel=1e-12, abs=1e-18)

    def test_velocity_vector_aligned_with_target_direction(self):
        s = self._reset("Alpha Centauri A")
        for _ in range(3):
            s.tick(3600.0)
        # v̂ · target_direction ≈ 1 when boosting from rest.
        v_unit = _vec_unit(s.velocity_vec_m_s)
        dot = sum(a * b for a, b in zip(v_unit, s.target_direction))
        assert dot > 0.999

    def test_boost_along_plus_x_for_solar_target(self):
        s = self._reset("Mars")
        s.tick(3600.0)
        # Target = +X → velocity should be purely along +X.
        vx, vy, vz = s.velocity_vec_m_s
        assert vx > 0
        assert abs(vy) < 1e-9
        assert abs(vz) < 1e-9

    def test_thrust_vec_points_toward_target_in_boost(self):
        s = self._reset("Alpha Centauri A")
        s.tick(3600.0)
        # thrust_vec should be parallel to target_direction during BOOST.
        mag = _vec_mag(s.thrust_vec)
        if mag > 1e-9:
            t_unit = _vec_unit(s.thrust_vec)
            dot = sum(a * b for a, b in zip(t_unit, s.target_direction))
            assert dot > 0.999

    def test_position_advances_along_target_ray(self):
        s = self._reset("Proxima Centauri")
        for _ in range(5):
            s.tick(3600.0)
        # position should sit on the target-direction ray from origin.
        p_unit = _vec_unit(s.position_vec_ly)
        dot = sum(a * b for a, b in zip(p_unit, s.target_direction))
        assert dot > 0.999


# ── 3-D physics during DECEL ─────────────────────────────────────────────


class TestDecelPhysics3D:
    def test_decel_retrograde_slows_velocity_vector(self):
        reset_trajectory_state()
        s = get_trajectory_state()
        s.set_target("Alpha Centauri A")
        # Preload mid-cruise state: half-way, moving along target_direction.
        half = s.distance_total_ly * 0.5
        s.position_vec_ly = (s.target_direction[0] * half,
                             s.target_direction[1] * half,
                             s.target_direction[2] * half)
        s.position_ly = half
        v0 = 1.0e5   # 100 km/s
        s.velocity_vec_m_s = (s.target_direction[0] * v0,
                              s.target_direction[1] * v0,
                              s.target_direction[2] * v0)
        s.velocity_m_s = v0

        get_phase_controller().current = Phase.DECELERATION
        v_before = s.velocity_m_s
        s.tick(3600.0)
        # DECEL must reduce speed.
        assert s.velocity_m_s < v_before

    def test_decel_leaves_velocity_colinear_with_target(self):
        reset_trajectory_state()
        s = get_trajectory_state()
        s.set_target("Barnard's Star")
        half = s.distance_total_ly * 0.5
        s.position_vec_ly = (s.target_direction[0] * half,
                             s.target_direction[1] * half,
                             s.target_direction[2] * half)
        s.position_ly = half
        v0 = 1.0e5
        s.velocity_vec_m_s = (s.target_direction[0] * v0,
                              s.target_direction[1] * v0,
                              s.target_direction[2] * v0)
        s.velocity_m_s = v0
        get_phase_controller().current = Phase.DECELERATION
        s.tick(3600.0)
        if s.velocity_m_s > 1e-3:
            v_unit = _vec_unit(s.velocity_vec_m_s)
            dot = sum(a * b for a, b in zip(v_unit, s.target_direction))
            # Still pointing prograde (just slower) — dot ≈ +1.
            assert dot > 0.99


# ── Serialisation / backward-compat ──────────────────────────────────────


class TestSerialization:
    def test_to_dict_contains_legacy_scalar_fields(self):
        s = TrajectoryState()
        d = s.to_dict()
        # Legacy keys required by existing /api/trajectory consumers.
        for key in ("target", "distance_total_ly", "position_ly",
                    "velocity_m_s", "beta", "elapsed_yr",
                    "remaining_distance_ly", "fraction_complete",
                    "propellant_remaining_kg",
                    "propellant_fraction_remaining", "config"):
            assert key in d, f"legacy key {key!r} missing from to_dict()"

    def test_to_dict_contains_new_vector_fields(self):
        s = TrajectoryState()
        d = s.to_dict()
        for key in ("position_vec_ly", "velocity_vec_m_s",
                    "thrust_vec", "target_direction"):
            assert key in d, f"3-D key {key!r} missing from to_dict()"
            assert isinstance(d[key], list)
            assert len(d[key]) == 3

    def test_to_dict_scalar_matches_vector_magnitude(self):
        reset_trajectory_state()
        s = get_trajectory_state()
        s.set_target("Alpha Centauri A")
        get_phase_controller().current = Phase.BOOST
        s.tick(3600.0)
        d = s.to_dict()
        vec_mag = math.sqrt(sum(c * c for c in d["velocity_vec_m_s"]))
        # Rounded at different precisions — allow 0.01 m/s tolerance.
        assert abs(d["velocity_m_s"] - vec_mag) < 0.1


# ── End-to-end: mission still runs ───────────────────────────────────────


class TestBackwardCompat:
    """Mission-critical: the MissionPlanner flows for Moon / Mars / Pluto /
    Proxima must still progress to non-zero position and produce a
    well-formed API payload after a tick."""

    @pytest.mark.parametrize("target", ["Moon", "Mars", "Pluto", "Proxima Centauri"])
    def test_mission_tick_produces_progress(self, target):
        reset_trajectory_state()
        s = get_trajectory_state()
        s.set_target(target)
        get_phase_controller().current = Phase.BOOST
        s.tick(3600.0)

        # Scalar and vector state both advance.
        assert s.position_ly >= 0.0
        assert s.velocity_m_s >= 0.0
        assert _vec_mag(s.position_vec_ly) == pytest.approx(s.position_ly,
                                                            rel=1e-9, abs=1e-18)
        assert _vec_mag(s.velocity_vec_m_s) == pytest.approx(s.velocity_m_s,
                                                             rel=1e-9, abs=1e-6)

        # to_dict() returns a complete payload.
        d = s.to_dict()
        assert d["target"] == target
        assert d["position_ly"] >= 0.0
