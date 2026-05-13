"""H₂ outgassing and steady-state in shield water (§4.7 of J2 scope).

For pure water shield loops, the dominant concern at mission scale is
H₂ generation from radiolysis. The simple mass balance with a first-
order recombiner sink `k_rec` is

    d[H₂]/dt = r_H2(Ḋ) − k_rec [H₂]                           [mol/(m³·s)]

which reaches steady state at

    [H₂]_ss = r_H2 / k_rec                                    [mol/m³]

with r_H2 supplied by :func:`molar_production_rate`.

The total outgassing rate into the water loop is r_H2·V, where V is
the shield water volume.
"""

from __future__ import annotations

from .g_values import (
    G_VALUE_LOW_LET_WATER,
    molar_production_rate,
)


def hydrogen_outgas_rate_mol_s(
    dose_rate_gy_s: float,
    water_volume_m3: float,
    water_density_kg_m3: float = 997.0,  # NIST SRD 23 at 293 K
    g_h2_molec_per_100_ev: float = G_VALUE_LOW_LET_WATER["H2"],
) -> float:
    """Total H₂ source rate into a shield-water compartment [mol/s].

    r_H2_total = r_H2 · V                                    [mol/s]
               = G(H₂) · Ḋ · ρ_w · V / (100 eV · N_A)

    Defaults to low-LET ⁶⁰Co γ G(H₂) = 0.45 (Spinks & Woods 1990).
    Callers with higher-LET proton/HZE spectra should pre-compute the
    effective G(H₂) via :func:`g_value_hydrogen_let` and pass it in.
    """
    if water_volume_m3 <= 0.0:
        raise ValueError("water_volume_m3 must be positive")
    r_h2 = molar_production_rate(
        g_molec_per_100_ev=g_h2_molec_per_100_ev,
        dose_rate_gy_s=dose_rate_gy_s,
        density_kg_m3=water_density_kg_m3,
    )
    return r_h2 * water_volume_m3


def hydrogen_steady_state_concentration(
    dose_rate_gy_s: float,
    recombiner_rate_1_s: float,
    water_density_kg_m3: float = 997.0,
    g_h2_molec_per_100_ev: float = G_VALUE_LOW_LET_WATER["H2"],
) -> float:
    """Steady-state [H₂] in shield water with a first-order sink.

    [H₂]_ss = r_H2 / k_rec                                    [mol/m³]

    Raises ValueError if `k_rec ≤ 0` since the linear model has no
    bounded steady state without a sink.
    """
    if recombiner_rate_1_s <= 0.0:
        raise ValueError("recombiner_rate_1_s must be positive")
    r_h2 = molar_production_rate(
        g_molec_per_100_ev=g_h2_molec_per_100_ev,
        dose_rate_gy_s=dose_rate_gy_s,
        density_kg_m3=water_density_kg_m3,
    )
    return r_h2 / recombiner_rate_1_s
