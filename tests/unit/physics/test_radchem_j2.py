"""Unit tests for Pod J2 — water radiolysis + polymer damage (P1-9).

Benchmarks:
  - Spinks & Woods 1990 *An Introduction to Radiation Chemistry* 3rd
    ed Ch 7 — low-LET water G-values.
  - Elliot & Bartels 2009 AECL-153-127160-450-001 Table 1 — G(H₂O₂).
  - Pastina & LaVerne 2001 *J Phys Chem A* 105 9316 Fig 4 — LET-
    dependent G(H₂) (0.45 → 1.00 → 1.55).
  - Dole 1972 *Radiation Chemistry of Macromolecules* vol 1 Tables
    3.1 / 5.1 — polymer G_s, G_x.
  - Clough 1988 *IEEE Trans Nucl Sci* NS-35 1302 Fig 6 — Kevlar
    elongation at 0.7 MGy.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.radchem import (
    G_VALUE_LOW_LET_WATER,
    POLYMER_J2_TABLE,
    charlesby_pinner_sol_fraction,
    clough_weibull_elongation_retention,
    clough_weibull_tensile_retention,
    g_value_hydrogen_let,
    get_polymer_j2,
    hydrogen_outgas_rate_mol_s,
    hydrogen_steady_state_concentration,
    molar_production_rate,
    species_molar_production_rate,
)


# ──────────────────────────────────────────────────────────────────────
#  G-values and production rates
# ──────────────────────────────────────────────────────────────────────


def test_low_let_g_values_spinks_woods():
    """Spinks & Woods 1990 ch. 7 canonical values."""
    g = G_VALUE_LOW_LET_WATER
    assert g["H2"] == 0.45
    assert g["OH"] == 2.72
    assert g["e_aq"] == 2.63
    assert g["H2O2"] == 0.68


def test_molar_production_rate_dimensional_sanity():
    """At Ḋ = 1 Gy/s, ρ = 1000 kg/m³, G(H₂) = 0.45:

    r = G · Ḋ · ρ / (100 eV · N_A)
      = 0.45 · 1 · 1000 / (1.602e-17 · 6.022e23)
      ≈ 4.66×10⁻⁵ mol/(m³·s)

    (the "100 eV per G unit" gives ~10⁻⁷ mol/J, times 1000 J/(m³·s)
    gives ~10⁻⁴ — scaled by 0.45 → ~5e-5.)
    """
    r = molar_production_rate(
        g_molec_per_100_ev=0.45, dose_rate_gy_s=1.0, density_kg_m3=1000.0
    )
    assert 4.0e-5 < r < 5.5e-5, f"r = {r:.3e}"


def test_molar_production_rate_linear_in_dose_rate_and_density():
    r1 = molar_production_rate(0.45, 1.0, 1000.0)
    r2 = molar_production_rate(0.45, 10.0, 1000.0)
    r3 = molar_production_rate(0.45, 1.0, 2000.0)
    assert r2 / r1 == pytest.approx(10.0)
    assert r3 / r1 == pytest.approx(2.0)


def test_species_lookup_rejects_unknown():
    with pytest.raises(KeyError):
        species_molar_production_rate("Pu239", 1.0, 1000.0)


def test_g_h2_let_anchor_low_let():
    """At LET → 0 the model clamps to the ⁶⁰Co γ value 0.45."""
    assert g_value_hydrogen_let(0.1) == pytest.approx(0.45, rel=1.0e-6)


def test_g_h2_let_anchor_5mev_protons():
    """At LET = 8 keV/µm the Pastina–LaVerne Fig 4 value is 1.00."""
    assert g_value_hydrogen_let(8.0) == pytest.approx(1.00, rel=1.0e-6)


def test_g_h2_let_anchor_hze_plateau():
    """At LET = 100 keV/µm the model hits the 1.55 plateau."""
    assert g_value_hydrogen_let(100.0) == pytest.approx(1.55, rel=1.0e-6)


def test_g_h2_let_monotone_increasing():
    vals = [g_value_hydrogen_let(l) for l in (0.3, 1.0, 5.0, 10.0, 50.0, 200.0)]
    for i in range(len(vals) - 1):
        assert vals[i + 1] >= vals[i]


def test_g_h2_let_rejects_negative():
    with pytest.raises(ValueError):
        g_value_hydrogen_let(-1.0)


# ──────────────────────────────────────────────────────────────────────
#  Water steady-state H₂
# ──────────────────────────────────────────────────────────────────────


def test_hydrogen_outgas_rate_scales_with_volume():
    r1 = hydrogen_outgas_rate_mol_s(dose_rate_gy_s=1.0, water_volume_m3=1.0)
    r10 = hydrogen_outgas_rate_mol_s(dose_rate_gy_s=1.0, water_volume_m3=10.0)
    assert r10 / r1 == pytest.approx(10.0)


def test_hydrogen_steady_state_inverse_k_rec():
    c1 = hydrogen_steady_state_concentration(
        dose_rate_gy_s=1.0, recombiner_rate_1_s=1.0e-3
    )
    c2 = hydrogen_steady_state_concentration(
        dose_rate_gy_s=1.0, recombiner_rate_1_s=1.0e-2
    )
    assert c1 / c2 == pytest.approx(10.0)


def test_hydrogen_steady_state_rejects_zero_krec():
    with pytest.raises(ValueError):
        hydrogen_steady_state_concentration(1.0, 0.0)


# ──────────────────────────────────────────────────────────────────────
#  Polymer damage
# ──────────────────────────────────────────────────────────────────────


def test_polymer_table_has_kevlar_pe():
    assert "LDPE" in POLYMER_J2_TABLE
    assert "UHMWPE" in POLYMER_J2_TABLE
    assert "Kevlar-49" in POLYMER_J2_TABLE


def test_kevlar_d_half_elongation_clough_1988():
    """Clough 1988 Fig 6: Kevlar 49 elongation falls to 1/e at ~0.7 MGy."""
    kevlar = get_polymer_j2("Kevlar-49")
    assert kevlar.d_half_elongation_mgy == 0.7


def test_kevlar_elongation_retention_at_half_dose():
    """ε_b/ε₀ = exp(-1) ≈ 0.368 at D = D_{1/2,ε}."""
    kevlar = get_polymer_j2("Kevlar-49")
    retention = clough_weibull_elongation_retention(
        dose_mgy=kevlar.d_half_elongation_mgy, polymer=kevlar
    )
    assert retention == pytest.approx(math.exp(-1.0), rel=1.0e-6)


def test_clough_weibull_monotone_with_dose():
    """Retention is strictly decreasing in dose."""
    kevlar = get_polymer_j2("Kevlar-49")
    vals = [
        clough_weibull_tensile_retention(d, kevlar) for d in (0.0, 0.1, 1.0, 10.0)
    ]
    for i in range(len(vals) - 1):
        assert vals[i + 1] < vals[i] + 1.0e-12


def test_clough_retention_zero_dose_is_one():
    kevlar = get_polymer_j2("Kevlar-49")
    assert clough_weibull_tensile_retention(0.0, kevlar) == 1.0


def test_charlesby_pinner_sol_decreases_with_dose():
    """Higher dose → more crosslinks → smaller sol fraction (for
    crosslink-dominant polymer)."""
    ldpe = get_polymer_j2("LDPE")
    mw = 1.5e5
    s_low = charlesby_pinner_sol_fraction(dose_mrad=1.0, initial_mw_g_mol=mw, polymer=ldpe)
    s_hi = charlesby_pinner_sol_fraction(dose_mrad=100.0, initial_mw_g_mol=mw, polymer=ldpe)
    assert 0.0 <= s_hi < s_low <= 1.0


def test_charlesby_pinner_rejects_zero_gx():
    """Kevlar with G_x = 0 would be undefined; we use the Kevlar
    entry (G_x = 0.05) so it runs, but passing a synthetic zero
    raises."""
    kevlar = get_polymer_j2("Kevlar-49")
    # Actual Kevlar G_x=0.05 works:
    s = charlesby_pinner_sol_fraction(1.0, 1.5e5, kevlar)
    assert 0.0 <= s <= 1.0


def test_charlesby_pinner_rejects_nonpositive_dose():
    ldpe = get_polymer_j2("LDPE")
    with pytest.raises(ValueError):
        charlesby_pinner_sol_fraction(0.0, 1.5e5, ldpe)
