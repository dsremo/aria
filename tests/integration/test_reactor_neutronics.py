"""Integration tests for the fusion reactor neutronics simulator,
including the Phase-4 Bosch-Hale cross-check and Abdou 2015 TBR
gate wiring.
"""

from __future__ import annotations

import pytest

from aria.physics.fusion_xsec import REQUIRED_TBR_ABDOU_2015
from aria.simulation.reactor_neutronics import ReactorNeutronicsSimulator


def test_bosch_hale_cross_check_populated_on_init() -> None:
    """After __init__ the simulator should expose the
    ``bosch_hale_cross_check_ratio`` attribute — proof that the
    Phase-4 Pod E1 bridge was called at least once."""
    sim = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    assert hasattr(sim, "bosch_hale_cross_check_ratio")
    assert sim.bosch_hale_cross_check_ratio > 0.0


def test_bosch_hale_ratio_finite_at_declared_operating_point() -> None:
    """At T_i = 15 keV, n = 1e20 m⁻³, V = 40 m³ the pure Maxwellian
    Bosch-Hale power prediction should be within ~2 orders of
    magnitude of the declared 200 MW. ITER-scale reactors only
    hit their design power with a combination of hot-spot peaking
    and α-heating, so a pure Maxwellian fit at these parameters is
    not expected to match exactly — the ratio is a sanity check,
    not a strict gate."""
    sim = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    ratio = sim.bosch_hale_cross_check_ratio
    assert 0.01 < ratio < 100.0, f"Bosch-Hale ratio = {ratio:.3e}"


def test_default_blanket_tbr_clears_abdou_gate() -> None:
    """Default blanket TBR = 1.15 clears Abdou 2015 1.10 gate."""
    sim = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    assert sim.tbr_meets_abdou is True
    assert sim.state.tritium_breeding_ratio >= REQUIRED_TBR_ABDOU_2015


def test_damaged_blanket_fails_abdou_gate() -> None:
    """A reactor with blanket TBR set below the Abdou 2015 1.10
    threshold must report the gate as failed."""
    sim = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    sim.state.tritium_breeding_ratio = 1.05
    sim._cross_check_fusion_power_against_bosch_hale()
    assert sim.tbr_meets_abdou is False


def test_bosch_hale_ratio_scales_with_temperature() -> None:
    """Higher plasma T_i → higher Bosch-Hale power → larger ratio."""
    low = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    low.state.plasma_temperature_kev = 10.0
    low._cross_check_fusion_power_against_bosch_hale()

    hi = ReactorNeutronicsSimulator(fusion_power_mw=200.0)
    hi.state.plasma_temperature_kev = 20.0
    hi._cross_check_fusion_power_against_bosch_hale()

    assert hi.bosch_hale_cross_check_ratio > low.bosch_hale_cross_check_ratio
