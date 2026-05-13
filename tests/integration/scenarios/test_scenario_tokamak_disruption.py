"""Scenario 2: tokamak disruption event on the fusion reactor.

A disruption flashes the plasma thermal-quench temperature from
10 keV down to below 100 eV in milliseconds; the loop voltage
spikes, Dreicer electrons escape the thermal distribution, and the
Rosenbluth-Putvinski avalanche amplifies a single seed into a
multi-MA runaway beam. Meanwhile the surrounding plasma sheath on
nearby dielectric surfaces is pushed into breakdown and fires a
deep-dielectric ESD event.

Pulls:
  - mhd_plasma.runaway (Dreicer + Rosenbluth-Putvinski)
  - mhd_plasma.limits (ITER geometric baseline)
  - sc_charging.surface_current_balance (SCATHA-class negative frame)
  - sc_charging.deep_dielectric (Kapton breakdown field)
  - sc_charging.esd_trigger (breakdown + arc energy)

Cross-pod invariants:
  1. Rosenbluth-Putvinski gain is catastrophic at ITER current.
  2. The Dreicer field at post-quench (100 eV, fixed n_e) is much
     larger than pre-quench (10 keV) — Dreicer scales as 1/T_e.
  3. A surface exposed to the disruption-driven flux reaches the
     Kapton E_BD and fires ESD.
  4. The arc energy is in the millijoule-to-joule ISS range cited
     in Leach & Alexander 1995.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.mhd_plasma.limits import ITER_BASELINE
from aria.physics.mhd_plasma.runaway import (
    dreicer_field,
    rosenbluth_putvinski_avalanche,
)
from aria.physics.sc_charging import (
    arc_energy_parallel_plate,
    esd_triggered,
    get_dielectric,
    peak_internal_field_parallel_plate,
    worst_case_eclipse_potential,
)


_ITER_N_E: float = 1.0e20  # ITER baseline line-averaged density [m-3]


def test_rp_avalanche_catastrophic_at_iter_baseline():
    """ITER I_p = 15 MA: seed 1 electron → N_final > 10¹⁶."""
    n_final = rosenbluth_putvinski_avalanche(
        plasma_current_ma=ITER_BASELINE.plasma_current_ma,
        seed_electrons=1.0,
    )
    assert n_final > 1.0e16, f"N_final = {n_final:.3e}"


def test_dreicer_field_post_quench_much_larger_than_prequench():
    """E_D ∝ 1/T_e, so the quench (10 keV → 100 eV = 100× cooler)
    raises the Dreicer threshold by exactly 100×. That's a
    necessary consistency check between the Dreicer formula and
    the runaway avalanche physics."""
    e_prequench = dreicer_field(
        electron_density_m3=_ITER_N_E, electron_temperature_ev=1.0e4
    )
    e_postquench = dreicer_field(
        electron_density_m3=_ITER_N_E, electron_temperature_ev=1.0e2
    )
    assert e_postquench / e_prequench == pytest.approx(100.0, rel=1.0e-12)
    # At n_e = 1e20 m⁻³, T_e = 10 keV → ~4.4 V/m (Wesson 2011 §2.16).
    # At 100 eV the Dreicer field rises 100× to ~443 V/m.
    assert 3.0e2 < e_postquench < 1.0e3


def test_scatha_eclipse_event_drives_surface_potential_negative_kv():
    """A nearby external surface in eclipse during the disruption
    (no photoemission, substorm-class plasma) reaches −10 to −50 kV
    — matching the historical SCATHA/CRRES events that were
    co-incident with magnetosphere plasma injections."""
    phi = worst_case_eclipse_potential(
        electron_temperature_ev=1.0e4, effective_se_yield=0.3
    )
    assert -5.0e4 < phi < -1.0e4


def test_kapton_internal_field_hits_breakdown_during_disruption():
    """When the trapped MeV-electron flux is elevated by the
    disruption, the deep-dielectric steady-state E = J / σ on a
    Kapton patch reaches (or exceeds) the 2.5×10⁸ V/m breakdown
    field. We pick an injected current density that just barely
    clears E_BD for a Kapton patch with RIC-boosted σ = 1e-17 S/m."""
    kapton = get_dielectric("Kapton-H")
    # Pick J so that E_internal = E_BD exactly
    e_peak = peak_internal_field_parallel_plate(
        injected_current_density_a_m2=kapton.breakdown_field_v_m * 1.0e-17,
        dielectric_thickness_m=2.5e-4,
        bulk_conductivity_s_m=1.0e-17,
    )
    assert e_peak == pytest.approx(kapton.breakdown_field_v_m, rel=1.0e-6)
    assert esd_triggered(e_peak, kapton.breakdown_field_v_m)


def test_arc_energy_in_iss_anomaly_catalogue_range():
    """Leach & Alexander 1995 NASA/TP-2003-212287 catalog of on-orbit
    ESD anomalies spans 1 mJ → 1 J arc energies. A Kapton patch of
    1 cm² × 250 µm at breakdown stores 24 mJ — squarely inside the
    cataloged band, consistent with historical SCATHA/CRRES hits."""
    kapton = get_dielectric("Kapton-H")
    u = arc_energy_parallel_plate(
        internal_field_v_m=kapton.breakdown_field_v_m,
        area_m2=1.0e-4,
        thickness_m=2.5e-4,
        relative_permittivity=kapton.relative_permittivity,
    )
    assert 1.0e-3 <= u <= 1.0, f"U_arc = {u*1000:.2f} mJ"
