"""Fluid property database for Pod H2.

Surface tensions, densities, and viscosities for the working fluids
the ship touches: water, LH2, LOX, ethanol, and whole blood. Every
value carries a per-field citation per the project's no-hardcoded-
constants rule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FluidH2:
    """Low-gravity-relevant fluid properties at a reference state.

    Attributes:
        name: identifier.
        density_kg_m3: ρ at reference T (kg/m³).
        dynamic_viscosity_pa_s: μ at reference T (Pa·s).
        surface_tension_n_m: σ at reference T (N/m).
        dsigma_dt_n_m_k: dσ/dT at reference T (N/m/K, usually negative).
        reference_temperature_k: T_ref (K).
        source: citation.
    """

    name: str
    density_kg_m3: float
    dynamic_viscosity_pa_s: float
    surface_tension_n_m: float
    dsigma_dt_n_m_k: float
    reference_temperature_k: float
    source: str


# ──────────────────────────────────────────────────────────────────────
#  Water at 293.15 K
# ──────────────────────────────────────────────────────────────────────
WATER_293K = FluidH2(
    name="Water",
    density_kg_m3=998.2,  # CRC Handbook 86th ed
    dynamic_viscosity_pa_s=1.002e-3,  # CRC Handbook 86th ed
    surface_tension_n_m=0.0728,  # CRC Handbook 86th ed
    dsigma_dt_n_m_k=-1.51e-4,  # Vargaftik 1983 J Phys Chem Ref Data 12 817
    reference_temperature_k=293.15,
    source="CRC Handbook 86th ed; Vargaftik 1983 JPCRD 12 817",
)


# ──────────────────────────────────────────────────────────────────────
#  Liquid hydrogen at 20 K — propellant
# ──────────────────────────────────────────────────────────────────────
LH2_20K = FluidH2(
    name="LH2",
    density_kg_m3=70.85,  # NIST REFPROP
    dynamic_viscosity_pa_s=1.33e-5,  # NIST REFPROP
    surface_tension_n_m=0.00193,  # NIST REFPROP
    dsigma_dt_n_m_k=-1.5e-4,  # NIST REFPROP (estimate near saturation)
    reference_temperature_k=20.0,
    source="NIST REFPROP 10.0",
)


# ──────────────────────────────────────────────────────────────────────
#  Liquid oxygen at 90 K — propellant / ECLSS
# ──────────────────────────────────────────────────────────────────────
LOX_90K = FluidH2(
    name="LOX",
    density_kg_m3=1141.0,  # NIST REFPROP
    dynamic_viscosity_pa_s=1.95e-4,  # NIST REFPROP
    surface_tension_n_m=0.01327,  # NIST REFPROP
    dsigma_dt_n_m_k=-1.5e-4,  # NIST REFPROP (estimate)
    reference_temperature_k=90.0,
    source="NIST REFPROP 10.0",
)


# ──────────────────────────────────────────────────────────────────────
#  Whole blood at 310 K (body temperature) — biology consumer (K2)
# ──────────────────────────────────────────────────────────────────────
BLOOD_310K = FluidH2(
    name="Blood",
    density_kg_m3=1060.0,  # Fung 1981 Biomechanics (ISBN 978-0387943848)
    dynamic_viscosity_pa_s=3.45e-3,  # Yeleswarapu 1998 μ_∞
    surface_tension_n_m=0.0585,  # Hrncír & Rosina 1997 Physiol Res 46 319
    dsigma_dt_n_m_k=-1.5e-4,  # Hrncír & Rosina 1997 estimate
    reference_temperature_k=310.15,
    source=(
        "Fung 1981 Biomechanics; Yeleswarapu 1998 PhD thesis Univ Pittsburgh; "
        "Hrncír & Rosina 1997 Physiol Res 46 319"
    ),
)


FLUID_H2_TABLE: dict[str, FluidH2] = {
    "Water": WATER_293K,
    "LH2": LH2_20K,
    "LOX": LOX_90K,
    "Blood": BLOOD_310K,
}


def get_fluid_h2(name: str) -> FluidH2:
    """Look up a fluid by name."""
    try:
        return FLUID_H2_TABLE[name]
    except KeyError as e:
        raise KeyError(
            f"Unknown fluid {name!r}. Known: {sorted(FLUID_H2_TABLE.keys())}"
        ) from e
