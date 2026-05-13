"""Saturn V launch-to-TLI replay validator.

Pins ARIA's Apollo 11 (AS-506) launch simulation against the
published flight-evaluation values in MSC-04112 (Apollo 11
Mission Report) and NASA SP-4206 (Bilstein 1980). When a future
refactor regresses the orbital-mechanics or propulsion stack,
these tests fail loudly instead of the simulator silently
drifting away from the historical record.

Tolerance bands are documented in
``saturn_v_launch.fly_apollo_11_to_tli`` docstring and below.
"""

from __future__ import annotations

import math

import pytest

from aria.simulation.saturn_v_reference import (
    SATURN_V_STAGES,
    APOLLO_11_LIFTOFF_MASS_KG,
    APOLLO_11_TLI_MASS_KG,
    APOLLO_11_LAUNCH_SEQUENCE,
    F1_ENGINE,
    J2_ENGINE,
    get_launch_event,
    get_stage,
    total_vehicle_mass_at_liftoff_kg,
)
from aria.simulation.saturn_v_launch import (
    fly_apollo_11_to_tli,
    LaunchSimResult,
)


# ── Reference dataset sanity ────────────────────────────────────


class TestSaturnVReferenceDataset:
    def test_three_stages_present(self) -> None:
        assert len(SATURN_V_STAGES) == 3
        names = {stage.name for stage in SATURN_V_STAGES}
        assert names == {"S-IC", "S-II", "S-IVB"}

    def test_s_ic_engine_is_f1_with_5_engines(self) -> None:
        s_ic = get_stage("S-IC")
        assert s_ic.engine.name == "F-1"
        assert s_ic.engine_count == 5

    def test_s_ii_engine_is_j2_with_5_engines(self) -> None:
        s_ii = get_stage("S-II")
        assert s_ii.engine.name == "J-2"
        assert s_ii.engine_count == 5

    def test_s_ivb_engine_is_j2_with_1_engine(self) -> None:
        s_ivb = get_stage("S-IVB")
        assert s_ivb.engine.name == "J-2"
        assert s_ivb.engine_count == 1

    def test_f1_engine_specs_within_published_band(self) -> None:
        # Rocketdyne R-3896-1: 1.522 Mlbf SL, 1.748 Mlbf vacuum,
        # ISP_SL = 263 s, ISP_vac = 304 s.
        assert F1_ENGINE.thrust_sl_n == pytest.approx(6_770_000.0, rel=0.01)
        assert F1_ENGINE.thrust_vac_n == pytest.approx(7_770_000.0, rel=0.01)
        assert F1_ENGINE.isp_sl_s == pytest.approx(263.0, abs=2)
        assert F1_ENGINE.isp_vac_s == pytest.approx(304.0, abs=2)

    def test_j2_engine_specs_within_published_band(self) -> None:
        # Rocketdyne R-3825-1: 232,250 lbf vac, ISP_vac = 421 s.
        assert J2_ENGINE.thrust_vac_n == pytest.approx(1_033_100.0, rel=0.01)
        assert J2_ENGINE.isp_vac_s == pytest.approx(421.0, abs=2)
        assert J2_ENGINE.thrust_sl_n is None  # vacuum-start engine

    def test_total_liftoff_mass_within_apollo_11_band(self) -> None:
        # Apollo 11 actual liftoff mass: 2,941,748 kg per MSC-04112.
        # Reference dataset is rounded — must match within 1 %.
        total = total_vehicle_mass_at_liftoff_kg()
        assert total == pytest.approx(APOLLO_11_LIFTOFF_MASS_KG, rel=0.01)


# ── Apollo 11 launch-sequence event timeline ────────────────────


class TestApollo11LaunchSequence:
    def test_sequence_starts_at_liftoff(self) -> None:
        liftoff = APOLLO_11_LAUNCH_SEQUENCE[0]
        assert liftoff.name == "liftoff"
        assert liftoff.t_plus_s == 0.0

    def test_max_q_around_t_plus_83_s(self) -> None:
        # Apollo 11 actual max-Q: T+1:23 (83 s) at ~13.7 km altitude.
        max_q = get_launch_event("max_q")
        assert max_q.t_plus_s == pytest.approx(83.0, abs=5)
        assert max_q.altitude_m == pytest.approx(13_700.0, rel=0.05)

    def test_s_ic_outboard_cutoff_around_162_s(self) -> None:
        # AS-506 measured: 161.7 s at 66.5 km, 2,390 m/s inertial.
        cutoff = get_launch_event("s_ic_outboard_cutoff")
        assert cutoff.t_plus_s == pytest.approx(161.7, abs=2)
        assert cutoff.inertial_velocity_mps == pytest.approx(2_390.0, abs=50)

    def test_s_ii_cutoff_around_549_s(self) -> None:
        # AS-506 measured: 549.0 s at 185.9 km, 6,840 m/s.
        cutoff = get_launch_event("s_ii_outboard_cutoff")
        assert cutoff.t_plus_s == pytest.approx(549.0, abs=5)
        assert cutoff.inertial_velocity_mps == pytest.approx(6_840.0, abs=100)

    def test_parking_orbit_insertion_at_t_plus_703_s(self) -> None:
        # AS-506 measured: 702.6 s, 190 km altitude.
        parking = get_launch_event("s_ivb_first_cutoff")
        assert parking.t_plus_s == pytest.approx(702.6, abs=5)
        assert parking.altitude_m == pytest.approx(190_400.0, rel=0.05)

    def test_tli_cutoff_velocity_above_10_8_kmps(self) -> None:
        # AS-506 measured: 10,834 m/s — escape vel from LEO is
        # ~11.1 km/s; TLI is sub-escape but on a transfer ellipse.
        tli = get_launch_event("s_ivb_second_cutoff")
        assert tli.inertial_velocity_mps == pytest.approx(10_834.0, abs=200)


# ── Launch simulator vs AS-506 ──────────────────────────────────


class TestSaturnVLaunchSimulator:
    """The simulator runs three propulsive phases + coast +
    fourth (TLI) phase. Each phase result is checked against
    the matching event in APOLLO_11_LAUNCH_SEQUENCE."""

    @pytest.fixture(scope="class")
    def sim_result(self) -> LaunchSimResult:
        return fly_apollo_11_to_tli()

    def test_s_ic_cutoff_velocity_within_5pct(self, sim_result) -> None:
        # AS-506 target: 2,390 m/s inertial at S-IC outboard cutoff.
        s_ic = sim_result.phases[0]
        target_mps = 2_390.0
        assert s_ic.final_velocity_mps == pytest.approx(target_mps, rel=0.05), (
            f"S-IC cutoff velocity {s_ic.final_velocity_mps:.1f} m/s, "
            f"AS-506 target {target_mps} m/s"
        )

    def test_s_ii_cutoff_velocity_within_5pct(self, sim_result) -> None:
        # AS-506 target: 6,840 m/s inertial at S-II outboard cutoff.
        s_ii = sim_result.phases[1]
        target_mps = 6_840.0
        assert s_ii.final_velocity_mps == pytest.approx(target_mps, rel=0.05), (
            f"S-II cutoff velocity {s_ii.final_velocity_mps:.1f} m/s, "
            f"AS-506 target {target_mps} m/s"
        )

    def test_parking_orbit_velocity_within_3pct(self, sim_result) -> None:
        # AS-506 target: 7,793 m/s inertial at parking-orbit insertion.
        s_ivb_1 = sim_result.phases[2]
        target_mps = 7_793.0
        assert s_ivb_1.final_velocity_mps == pytest.approx(target_mps, rel=0.03), (
            f"Parking-orbit velocity {s_ivb_1.final_velocity_mps:.1f} m/s, "
            f"AS-506 target {target_mps} m/s"
        )

    def test_parking_orbit_altitude_within_15pct(self, sim_result) -> None:
        # AS-506 target: 190 km. Single-DoF altitude integration is
        # approximate so tolerance is wider than velocity.
        target_m = 190_000.0
        assert sim_result.parking_orbit_altitude_m == pytest.approx(
            target_m, rel=0.15,
        ), (
            f"Parking-orbit altitude "
            f"{sim_result.parking_orbit_altitude_m / 1000:.1f} km, "
            f"AS-506 target {target_m / 1000} km"
        )

    def test_tli_velocity_within_5pct(self, sim_result) -> None:
        # AS-506 target: 10,834 m/s after TLI burn.
        target_mps = 10_834.0
        assert sim_result.tli_velocity_mps == pytest.approx(target_mps, rel=0.05), (
            f"TLI velocity {sim_result.tli_velocity_mps:.1f} m/s, "
            f"AS-506 target {target_mps} m/s"
        )

    def test_tli_mass_within_15pct(self, sim_result) -> None:
        # AS-506 target: 46,678 kg (CSM + LM) post-TLI.
        target_kg = APOLLO_11_TLI_MASS_KG
        assert sim_result.tli_mass_kg == pytest.approx(target_kg, rel=0.15), (
            f"TLI mass {sim_result.tli_mass_kg:.0f} kg, "
            f"AS-506 target {target_kg:.0f} kg"
        )

    def test_total_propellant_burned_under_total_loaded(self, sim_result) -> None:
        # Sanity: cannot burn more propellant than was loaded.
        loaded_total_kg = sum(
            stage.propellant_mass_kg for stage in SATURN_V_STAGES
        )
        assert sim_result.total_propellant_burned_kg <= loaded_total_kg

    def test_each_phase_burns_finite_positive_propellant(
        self, sim_result,
    ) -> None:
        for phase in sim_result.phases:
            assert phase.propellant_burned_kg > 0
            assert math.isfinite(phase.propellant_burned_kg)
            assert math.isfinite(phase.delta_v_mps)
            assert phase.delta_v_mps > 0

    def test_phase_velocity_monotonically_increases(self, sim_result) -> None:
        # Each propulsive phase MUST add velocity (no anti-acceleration bug).
        prev_v = 0.0
        for phase in sim_result.phases:
            assert phase.final_velocity_mps > prev_v, (
                f"{phase.phase} non-monotonic: prev={prev_v:.0f}, "
                f"now={phase.final_velocity_mps:.0f}"
            )
            prev_v = phase.final_velocity_mps


# ── Cross-check: simulator matches event timeline ───────────────


class TestSaturnVSimulatorVsEventTimeline:
    """Independent cross-check that the simulator output matches
    the published event timeline. If both agree, the simulator
    has reproduced the historical Saturn V record."""

    def test_simulator_matches_published_s_ic_cutoff(self) -> None:
        result = fly_apollo_11_to_tli()
        sim_v = result.phases[0].final_velocity_mps
        event_v = get_launch_event(
            "s_ic_outboard_cutoff",
        ).inertial_velocity_mps
        # Both must agree within 8 % (combined sim + reference uncertainty).
        assert sim_v == pytest.approx(event_v, rel=0.08)

    def test_simulator_matches_published_tli_cutoff(self) -> None:
        result = fly_apollo_11_to_tli()
        sim_v = result.tli_velocity_mps
        event_v = get_launch_event(
            "s_ivb_second_cutoff",
        ).inertial_velocity_mps
        assert sim_v == pytest.approx(event_v, rel=0.05)
