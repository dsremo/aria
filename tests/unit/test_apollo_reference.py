"""Apollo reference data tests — sanity checks on historical data."""
from __future__ import annotations
import pytest
from aria.simulation.apollo_reference import (
    APOLLO_MISSIONS, get_mission, landed_missions, average_dv_budget,
)


def test_all_landed_missions_present():
    nums = {m.number for m in landed_missions()}
    assert nums == {11, 12, 14, 15, 16, 17}


def test_apollo_11_tranquility():
    a11 = get_mission(11)
    assert a11.landing_site == "Sea of Tranquility"
    assert abs(a11.lat_deg - 0.67) < 0.01
    assert abs(a11.lon_deg - 23.49) < 0.01
    assert a11.tli_dv_mps == 3131.0


def test_dv_budget_averages_sensible():
    avg = average_dv_budget()
    # Apollo averages should all be within their known published ranges
    assert 3100 < avg["tli_mean_mps"] < 3200
    assert 880 < avg["loi_mean_mps"] < 910
    assert 2040 < avg["descent_mean_mps"] < 2070
    assert 1840 < avg["ascent_mean_mps"] < 1870


def test_surface_stays_increase_apollo_12_to_17():
    """Mission planning gradually extended surface stay as confidence grew."""
    stays = [get_mission(n).surface_stay_h for n in [11, 12, 14, 15, 16, 17]]
    assert all(isinstance(s, (int, float)) for s in stays)
    # Later J-missions stayed much longer than early H-missions
    assert get_mission(17).surface_stay_h > get_mission(11).surface_stay_h


def test_aria_matches_apollo_11_tli_within_2pct():
    """Cross-check against ARIA's end-to-end moon mission simulator."""
    from aria.simulation.moon_mission_e2e import apollo_11_e2e
    a11_ref = get_mission(11)
    a11_aria = apollo_11_e2e()
    tli_phase = next(p for p in a11_aria.phases if p.phase == "TLI")
    err = abs(tli_phase.delta_v_mps - a11_ref.tli_dv_mps) / a11_ref.tli_dv_mps
    assert err < 0.02, f"TLI Δv drift {err:.1%} exceeds 2% tolerance"


def test_aria_matches_apollo_11_descent_within_5pct():
    from aria.simulation.moon_mission_e2e import apollo_11_e2e
    a11 = get_mission(11)
    aria = apollo_11_e2e()
    descent = next(p for p in aria.phases if p.phase == "POWERED_DESCENT")
    err = abs(descent.delta_v_mps - a11.descent_dv_mps) / a11.descent_dv_mps
    assert err < 0.05
