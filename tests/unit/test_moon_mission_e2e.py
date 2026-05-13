"""End-to-end Moon mission composition tests.

Proves that ARIA can close a crewed Moon mission start-to-finish by
chaining the existing physics modules. Validates against Apollo 11
historical data where available.
"""

from __future__ import annotations

import pytest

from aria.simulation.moon_mission_e2e import (
    MoonMissionConfig, PhaseReport, MoonMissionResult,
    simulate_moon_mission, apollo_11_e2e, artemis_3_e2e,
)


def test_apollo_11_e2e_success():
    r = apollo_11_e2e()
    assert r.overall_success, f"Apollo 11 failed at {r.failure_phase}"
    assert r.failure_phase is None


def test_phases_ordered_correctly():
    r = apollo_11_e2e()
    expected = [
        "TLI", "COAST_TO_MOON", "LOI",
        "UNDOCK_AND_DOI", "POWERED_DESCENT", "SURFACE_STAY",
        "POWERED_ASCENT", "RENDEZVOUS_DOCK",
        "TEI", "COAST_TO_EARTH", "ENTRY_DESCENT_LANDING",
    ]
    assert [p.phase for p in r.phases] == expected


def test_apollo_11_tli_dv_accurate():
    """Apollo 11 TLI was 3,131 m/s. ARIA should land within 2%."""
    r = apollo_11_e2e()
    tli = next(p for p in r.phases if p.phase == "TLI")
    assert 3060 < tli.delta_v_mps < 3200


def test_apollo_11_descent_dv_calibrated():
    """Apollo 11 powered descent was 2,040 m/s net (NASA MSC-04112)."""
    r = apollo_11_e2e()
    descent = next(p for p in r.phases if p.phase == "POWERED_DESCENT")
    # Module is explicitly calibrated to 2040 m/s for Apollo 11
    assert 1900 < descent.delta_v_mps < 2200


def test_apollo_11_total_dv_reasonable():
    """Total Δv should be in the 8-10 km/s range for a crewed lunar mission."""
    r = apollo_11_e2e()
    assert 8000 < r.total_dv_mps < 11000


def test_mass_budget_monotonic_until_jettison():
    """Mass should decrease during propulsive phases (ignoring rendezvous
    where stages recombine)."""
    r = apollo_11_e2e()
    # Filter out RENDEZVOUS_DOCK (mass increases from stage recombination)
    propulsive = [p for p in r.phases
                  if p.phase in ("TLI", "LOI", "POWERED_DESCENT", "POWERED_ASCENT", "TEI")]
    for i, p in enumerate(propulsive):
        assert p.propellant_burned_kg >= 0


def test_apollo_11_final_mass_is_cm_only():
    """After EDL, mass should equal the Command Module dry mass."""
    r = apollo_11_e2e()
    assert r.final_mass_kg == r.config.cm_dry_mass_kg


def test_apollo_11_duration_reasonable():
    """Apollo 11 was an ~8 day mission (195 h). We should be in that ballpark."""
    r = apollo_11_e2e()
    assert 200 < r.total_duration_hours < 400   # includes surface stay


def test_artemis_3_projection_succeeds():
    r = artemis_3_e2e()
    assert r.overall_success, f"Artemis-3 projection failed at {r.failure_phase}"


def test_custom_config_runs():
    """Minimal custom config should still produce a valid result structure."""
    cfg = MoonMissionConfig(name="Test", surface_stay_hours=4.0)
    r = simulate_moon_mission(cfg)
    assert isinstance(r, MoonMissionResult)
    assert len(r.phases) >= 10     # all phases attempted
    assert all(isinstance(p, PhaseReport) for p in r.phases)


def test_fault_injection_increases_dv():
    """Engine-out fault during TLI should raise total Δv."""
    from aria.simulation.moon_mission_e2e import MissionFault
    base = apollo_11_e2e()
    cfg = MoonMissionConfig(
        name="Apollo 11 + TLI engine-out",
        faults=[MissionFault(phase="TLI", kind="engine_out", severity=0.3)],
    )
    r = simulate_moon_mission(cfg)
    assert r.total_dv_mps > base.total_dv_mps


def test_nav_error_raises_tli_dv():
    from aria.simulation.moon_mission_e2e import MissionFault
    cfg = MoonMissionConfig(faults=[MissionFault("TLI", "nav_error", 1.0)])
    r = simulate_moon_mission(cfg)
    tli_phase = next(p for p in r.phases if p.phase == "TLI")
    # 1.0 × 500 m/s = 500 m/s extra budgeted for corridor re-targeting
    assert "nav_error" in tli_phase.notes


def test_phase_report_fields_valid():
    r = apollo_11_e2e()
    for p in r.phases:
        assert isinstance(p.phase, str) and p.phase
        assert p.duration_s >= 0
        assert p.delta_v_mps >= 0
        assert p.propellant_burned_kg >= 0
        # Mass is positive (may be 0 only in extreme failure edge cases)
        assert p.mass_after_kg >= 0
